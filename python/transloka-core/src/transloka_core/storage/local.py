import hashlib
import os
import stat
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO

from transloka_core.storage.directories import (
    LocalDataDirectories,
    LocalDataDirectoryError,
    ensure_local_data_directories,
)

_CHUNK_SIZE = 1024 * 1024
_INVALID_WINDOWS_CHARACTERS = frozenset('<>:"\\|?*')
_RESERVED_WINDOWS_NAMES = frozenset(
    {"CON", "PRN", "AUX", "NUL"}
    | {f"COM{number}" for number in range(1, 10)}
    | {f"LPT{number}" for number in range(1, 10)}
)


class LocalFileStorageError(RuntimeError):
    """Raised when a managed file operation cannot be completed safely."""


class UnsafeStorageKeyError(LocalFileStorageError):
    pass


class StoredFileExistsError(LocalFileStorageError):
    pass


class StoredFileNotFoundError(LocalFileStorageError):
    pass


class ImmutableStoredFileError(LocalFileStorageError):
    pass


@dataclass(frozen=True, slots=True)
class TemporaryStoredFile:
    path: Path
    checksum_sha256: str
    size_bytes: int


@dataclass(frozen=True, slots=True)
class StoredFileArtifact:
    storage_key: str
    checksum_sha256: str
    size_bytes: int
    is_immutable: bool


class LocalFileStorage:
    def __init__(self, directories: LocalDataDirectories) -> None:
        self._directories = directories
        self._root = directories.root.resolve(strict=False)
        self._temporary_root = directories.temporary.resolve(strict=False)

    def write_temporary(self, stream: BinaryIO) -> TemporaryStoredFile:
        try:
            ensure_local_data_directories(self._directories)
            descriptor, raw_path = tempfile.mkstemp(
                prefix="transloka-file-",
                suffix=".tmp",
                dir=self._temporary_root,
            )
        except (LocalDataDirectoryError, OSError) as exc:
            raise LocalFileStorageError("A temporary managed file could not be created.") from exc

        path = Path(raw_path)
        checksum = hashlib.sha256()
        size_bytes = 0
        try:
            with os.fdopen(descriptor, "wb") as destination:
                for chunk in iter(lambda: stream.read(_CHUNK_SIZE), b""):
                    if not isinstance(chunk, bytes):
                        raise TypeError
                    destination.write(chunk)
                    checksum.update(chunk)
                    size_bytes += len(chunk)
                destination.flush()
                os.fsync(destination.fileno())
        except Exception as exc:
            _unlink_quietly(path)
            raise LocalFileStorageError("The temporary managed file could not be written.") from exc

        return TemporaryStoredFile(
            path=path,
            checksum_sha256=checksum.hexdigest(),
            size_bytes=size_bytes,
        )

    def commit(
        self,
        temporary: TemporaryStoredFile,
        storage_key: str,
        *,
        immutable: bool = False,
    ) -> StoredFileArtifact:
        if not isinstance(immutable, bool):
            raise LocalFileStorageError("The immutable flag is invalid.")

        owned_temporary: Path | None = None
        destination: Path | None = None
        published = False
        try:
            owned_temporary = self._validate_temporary(temporary)
            destination = self._resolve_storage_key(storage_key)
            self._ensure_parent_directories(destination)
            if destination.exists() or destination.is_symlink():
                raise StoredFileExistsError("The managed file already exists.")
            if (
                owned_temporary.stat().st_size != temporary.size_bytes
                or _checksum_path(owned_temporary) != temporary.checksum_sha256
            ):
                raise LocalFileStorageError("The temporary managed file failed validation.")

            # ponytail: hard-link publication is atomic and refuses overwrite;
            # temp and destination are guaranteed to share the data root.
            os.link(owned_temporary, destination)
            published = True
            try:
                owned_temporary.unlink()
            except OSError:
                destination.unlink(missing_ok=True)
                raise
            owned_temporary = None

            if immutable:
                _mark_immutable(destination)

            return StoredFileArtifact(
                storage_key=storage_key,
                checksum_sha256=temporary.checksum_sha256,
                size_bytes=temporary.size_bytes,
                is_immutable=immutable,
            )
        except StoredFileExistsError:
            raise
        except LocalFileStorageError:
            raise
        except FileExistsError as exc:
            raise StoredFileExistsError("The managed file already exists.") from exc
        except OSError as exc:
            if published and destination is not None:
                _unlink_quietly(destination)
            raise LocalFileStorageError("The managed file could not be committed safely.") from exc
        finally:
            if owned_temporary is not None:
                _unlink_quietly(owned_temporary)

    def open_read(self, storage_key: str) -> BinaryIO:
        path = self._existing_file(storage_key)
        try:
            return path.open("rb")
        except OSError as exc:
            raise LocalFileStorageError("The managed file could not be opened.") from exc

    def checksum(self, storage_key: str) -> str:
        try:
            with self.open_read(storage_key) as source:
                checksum = hashlib.sha256()
                for chunk in iter(lambda: source.read(_CHUNK_SIZE), b""):
                    checksum.update(chunk)
                return checksum.hexdigest()
        except LocalFileStorageError:
            raise
        except OSError as exc:
            raise LocalFileStorageError(
                "The managed file checksum could not be calculated."
            ) from exc

    def delete(self, storage_key: str) -> None:
        path = self._existing_file(storage_key)
        if _is_immutable(path):
            raise ImmutableStoredFileError("An immutable managed file cannot be deleted.")
        try:
            path.unlink()
        except OSError as exc:
            raise LocalFileStorageError("The managed file could not be deleted.") from exc

    def _validate_temporary(self, temporary: TemporaryStoredFile) -> Path:
        if not isinstance(temporary, TemporaryStoredFile):
            raise LocalFileStorageError("The temporary managed file is invalid.")
        path = temporary.path
        if (
            not path.is_absolute()
            or path.parent != self._temporary_root
            or not path.name.startswith("transloka-file-")
            or path.is_symlink()
            or not path.is_file()
            or path.resolve(strict=True) != path
        ):
            raise LocalFileStorageError("The temporary managed file is invalid.")
        return path

    def _resolve_storage_key(self, storage_key: str) -> Path:
        parts = _validate_storage_key(storage_key)
        candidate = self._root.joinpath(*parts)
        _reject_symlinks(self._root, candidate)
        resolved = candidate.resolve(strict=False)
        if not resolved.is_relative_to(self._root):
            raise UnsafeStorageKeyError("The storage key escapes the managed data root.")
        return candidate

    def _ensure_parent_directories(self, destination: Path) -> None:
        current = self._root
        for part in destination.relative_to(self._root).parts[:-1]:
            current /= part
            if current.is_symlink():
                raise UnsafeStorageKeyError("A managed path contains a symbolic link.")
            if current.exists():
                if not current.is_dir():
                    raise LocalFileStorageError("A managed directory is occupied by a file.")
                continue
            try:
                current.mkdir()
            except OSError as exc:
                raise LocalFileStorageError("A managed directory could not be created.") from exc

    def _existing_file(self, storage_key: str) -> Path:
        path = self._resolve_storage_key(storage_key)
        if not path.is_file() or path.is_symlink():
            raise StoredFileNotFoundError("The managed file was not found.")
        return path


def _validate_storage_key(storage_key: str) -> tuple[str, ...]:
    if not isinstance(storage_key, str) or not storage_key or not storage_key.isprintable():
        raise UnsafeStorageKeyError("The storage key is invalid.")
    parts = tuple(storage_key.split("/"))
    if len(parts) < 2 or parts[0] != "projects":
        raise UnsafeStorageKeyError("The storage key is outside the managed project namespace.")
    for part in parts:
        _validate_path_component(part)
    return parts


def _validate_path_component(component: str) -> None:
    reserved_stem = component.split(".", 1)[0].upper()
    if (
        not component
        or component in {".", ".."}
        or component != component.strip()
        or component.endswith(".")
        or len(component) > 255
        or any(character in _INVALID_WINDOWS_CHARACTERS for character in component)
        or reserved_stem in _RESERVED_WINDOWS_NAMES
    ):
        raise UnsafeStorageKeyError("The storage key contains an unsafe filename.")


def _reject_symlinks(root: Path, candidate: Path) -> None:
    current = root
    for part in candidate.relative_to(root).parts:
        current /= part
        if current.is_symlink():
            raise UnsafeStorageKeyError("A managed path contains a symbolic link.")


def _checksum_path(path: Path) -> str:
    checksum = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(_CHUNK_SIZE), b""):
            checksum.update(chunk)
    return checksum.hexdigest()


def _mark_immutable(path: Path) -> None:
    mode = stat.S_IMODE(path.stat().st_mode)
    path.chmod(mode & ~(stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH))


def _is_immutable(path: Path) -> bool:
    return not bool(path.stat().st_mode & (stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH))


def _unlink_quietly(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass
