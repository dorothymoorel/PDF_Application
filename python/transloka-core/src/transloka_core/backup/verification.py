"""Verify backup archives without performing an unsafe extraction."""

from __future__ import annotations

import hashlib
import math
import os
import re
import sqlite3
import stat
import tempfile
import zlib
from collections.abc import Iterable
from contextlib import closing
from dataclasses import dataclass, replace
from pathlib import Path, PurePosixPath
from typing import IO, BinaryIO
from zipfile import BadZipFile, ZipFile, ZipInfo

from transloka_core.backup.manifest import (
    BackupManifest,
    BackupManifestError,
    BackupManifestFile,
)
from transloka_core.database import DATABASE_FILENAME

MANIFEST_ARCHIVE_PATH = "manifest.json"
DATABASE_ARCHIVE_PATH = f"database/{DATABASE_FILENAME}"
_CHUNK_SIZE = 1024 * 1024
_MANIFEST_MAX_BYTES = 8 * 1024 * 1024
_MIN_RATIO_CHECK_BYTES = 64 * 1024
_UNSAFE_UNICODE_SEPARATORS = frozenset({"\u2044", "\u2215", "\u29f8", "\uff0f"})
_WINDOWS_RESERVED_NAMES = frozenset(
    {"CON", "PRN", "AUX", "NUL"}
    | {f"COM{index}" for index in range(1, 10)}
    | {f"LPT{index}" for index in range(1, 10)}
)
_SHA256_PATTERN = re.compile(r"[0-9a-f]{64}\Z")


class BackupVerificationError(RuntimeError):
    """Raised when a backup cannot be proven safe and internally consistent."""


class BackupArchiveCorruptionError(BackupVerificationError):
    """Raised when ZIP structure or CRC validation fails."""


class BackupArchiveBombError(BackupVerificationError):
    """Raised when archive expansion exceeds safe resource limits."""


class BackupChecksumError(BackupVerificationError):
    """Raised when an archive or manifest checksum does not match."""


class BackupManifestMissingError(BackupVerificationError):
    """Raised when a backup has no manifest entry."""


class BackupManifestVerificationError(BackupVerificationError):
    """Raised when a manifest is malformed or disagrees with ZIP entries."""


class BackupPathError(BackupVerificationError):
    """Raised when an archive entry is not a safe relative POSIX path."""


class BackupSymlinkError(BackupVerificationError):
    """Raised when an archive entry is marked as a symbolic link."""


class BackupSchemaError(BackupVerificationError):
    """Raised when the backed-up SQLite schema is invalid or unexpected."""


@dataclass(frozen=True, slots=True)
class BackupVerificationLimits:
    """Resource limits applied before and during ZIP decompression."""

    max_entries: int = 10_000
    max_file_uncompressed_bytes: int = 1024 * 1024 * 1024
    max_total_uncompressed_bytes: int = 4 * 1024 * 1024 * 1024
    max_compression_ratio: float = 200.0

    def __post_init__(self) -> None:
        for value, name in (
            (self.max_entries, "max_entries"),
            (self.max_file_uncompressed_bytes, "max_file_uncompressed_bytes"),
            (self.max_total_uncompressed_bytes, "max_total_uncompressed_bytes"),
        ):
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise ValueError(f"{name} must be a positive integer.")
        if (
            isinstance(self.max_compression_ratio, bool)
            or not isinstance(self.max_compression_ratio, (int, float))
            or not math.isfinite(self.max_compression_ratio)
            or self.max_compression_ratio <= 0
        ):
            raise ValueError("max_compression_ratio must be a positive finite number.")


@dataclass(frozen=True, slots=True)
class BackupVerificationResult:
    """Evidence returned only after every selected verification gate passes."""

    archive_path: Path
    checksum_sha256: str
    size_bytes: int
    manifest: BackupManifest
    verified_files: tuple[str, ...]


def verify_backup_archive(
    archive_path: str | os.PathLike[str],
    *,
    expected_checksum_sha256: str | None = None,
    data_root: str | os.PathLike[str] | None = None,
    limits: BackupVerificationLimits | None = None,
) -> BackupVerificationResult:
    """Verify a backup archive without extracting its entries into application data.

    Only the primary SQLite database (and any additional database entry under the
    archive's ``database/`` directory) is copied to a private temporary file for
    SQLite integrity checks. All other content is read directly from the ZIP and
    discarded after its checksum, size, and CRC have been verified.
    """

    selected_limits = limits or BackupVerificationLimits()
    path = _validated_archive_path(archive_path, data_root)
    archive_checksum = _sha256_file(path)
    if expected_checksum_sha256 is not None:
        _validate_checksum_text(expected_checksum_sha256, "expected archive checksum")
        if archive_checksum != expected_checksum_sha256:
            raise BackupChecksumError("The backup archive checksum does not match.")

    try:
        with ZipFile(path, mode="r") as archive:
            entries = _inspect_entries(archive.infolist(), selected_limits)
            if MANIFEST_ARCHIVE_PATH not in entries:
                raise BackupManifestMissingError("The backup manifest is missing.")
            manifest = _read_manifest(archive, entries[MANIFEST_ARCHIVE_PATH], selected_limits)
            _validate_manifest_entries(manifest, entries)
            _verify_manifest_files(archive, manifest.files, entries, selected_limits)
            _verify_sqlite_entries(archive, manifest, entries, selected_limits)
            manifest = replace(manifest, verified=True)
    except BackupVerificationError:
        raise
    except BackupManifestError as exc:
        raise BackupManifestVerificationError("The backup manifest is invalid.") from exc
    except (BadZipFile, EOFError, OSError, RuntimeError, ValueError, zlib.error) as exc:
        raise BackupArchiveCorruptionError("The backup archive is corrupt or unreadable.") from exc

    return BackupVerificationResult(
        archive_path=path,
        checksum_sha256=archive_checksum,
        size_bytes=path.stat().st_size,
        manifest=manifest,
        verified_files=tuple(manifest.included_content),
    )


def verify_backup(
    archive_path: str | os.PathLike[str],
    *,
    expected_checksum_sha256: str | None = None,
    data_root: str | os.PathLike[str] | None = None,
    limits: BackupVerificationLimits | None = None,
) -> BackupVerificationResult:
    """Compatibility alias for :func:`verify_backup_archive`."""

    return verify_backup_archive(
        archive_path,
        expected_checksum_sha256=expected_checksum_sha256,
        data_root=data_root,
        limits=limits,
    )


def _validated_archive_path(
    archive_path: str | os.PathLike[str],
    data_root: str | os.PathLike[str] | None,
) -> Path:
    try:
        raw_path = os.fspath(archive_path)
    except TypeError as exc:
        raise BackupPathError("The backup archive path is invalid.") from exc
    path = Path(raw_path)
    if not path.is_absolute() or path.is_symlink() or not path.is_file():
        raise BackupPathError("The backup archive must be an absolute regular file.")
    try:
        canonical_path = path.resolve(strict=True)
    except OSError as exc:
        raise BackupPathError("The backup archive path cannot be resolved.") from exc
    if data_root is not None:
        root = Path(data_root)
        if not root.is_absolute() or root.is_symlink() or not root.is_dir():
            raise BackupPathError("The backup data root is invalid.")
        try:
            if not canonical_path.is_relative_to(root.resolve(strict=True)):
                raise BackupPathError("The backup archive is outside the data root.")
        except OSError as exc:
            raise BackupPathError("The backup data root cannot be resolved.") from exc
    return canonical_path


def _inspect_entries(
    infos: list[ZipInfo],
    limits: BackupVerificationLimits,
) -> dict[str, ZipInfo]:
    if not infos:
        raise BackupArchiveCorruptionError("The backup archive is empty.")
    if len(infos) > limits.max_entries:
        raise BackupArchiveBombError("The backup archive contains too many entries.")

    entries: dict[str, ZipInfo] = {}
    total_size = 0
    for info in infos:
        name = _safe_entry_name(info.filename)
        if name in entries:
            raise BackupArchiveCorruptionError("The backup archive contains duplicate entries.")
        if _is_symlink(info):
            raise BackupSymlinkError(f"The backup archive contains a symlink: {name}.")
        if info.is_dir():
            raise BackupPathError("Directory entries are not allowed in backup archives.")
        if info.flag_bits & 0x1:
            raise BackupArchiveCorruptionError("Encrypted backup entries are not supported.")
        if info.file_size > limits.max_file_uncompressed_bytes:
            raise BackupArchiveBombError(f"The backup entry is too large: {name}.")
        total_size += info.file_size
        if total_size > limits.max_total_uncompressed_bytes:
            raise BackupArchiveBombError("The backup archive expands beyond the safe limit.")
        if (
            info.file_size >= _MIN_RATIO_CHECK_BYTES
            and info.file_size / max(info.compress_size, 1) > limits.max_compression_ratio
        ):
            raise BackupArchiveBombError(
                f"The backup entry has an unsafe compression ratio: {name}."
            )
        entries[name] = info
    return entries


def _safe_entry_name(name: str) -> str:
    if (
        not name
        or "\x00" in name
        or "\\" in name
        or ":" in name
        or any(character in _UNSAFE_UNICODE_SEPARATORS for character in name)
        or any(ord(character) < 32 for character in name)
    ):
        raise BackupPathError("Backup entries must use safe relative POSIX paths.")
    path = PurePosixPath(name)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise BackupPathError(f"Unsafe backup entry path: {name}.")
    normalised = path.as_posix()
    if normalised != name:
        raise BackupPathError(f"Backup entry path is not canonical: {name}.")
    for part in path.parts:
        if part.endswith((".", " ")):
            raise BackupPathError(f"Backup entry path is unsafe on Windows: {name}.")
        stem = part.rstrip(" .").partition(".")[0].upper()
        if stem in _WINDOWS_RESERVED_NAMES:
            raise BackupPathError(f"Backup entry path is reserved on Windows: {name}.")
    return normalised


def _is_symlink(info: ZipInfo) -> bool:
    mode = (info.external_attr >> 16) & 0xFFFF
    return stat.S_ISLNK(mode)


def _read_manifest(
    archive: ZipFile,
    info: ZipInfo,
    limits: BackupVerificationLimits,
) -> BackupManifest:
    if info.file_size > _MANIFEST_MAX_BYTES:
        raise BackupManifestVerificationError("The backup manifest is too large.")
    try:
        with archive.open(info, mode="r") as source:
            payload = _read_bounded(source, _MANIFEST_MAX_BYTES)
        return BackupManifest.from_json(payload)
    except BackupManifestError as exc:
        raise BackupManifestVerificationError("The backup manifest is invalid.") from exc
    except (BadZipFile, EOFError, OSError, RuntimeError, ValueError, zlib.error) as exc:
        raise BackupArchiveCorruptionError("The backup manifest cannot be read safely.") from exc


def _validate_manifest_entries(
    manifest: BackupManifest,
    entries: dict[str, ZipInfo],
) -> None:
    if MANIFEST_ARCHIVE_PATH in manifest.included_content:
        raise BackupManifestVerificationError(
            "The backup manifest cannot include the manifest entry itself."
        )
    expected_names = set(manifest.included_content) | {MANIFEST_ARCHIVE_PATH}
    if set(entries) != expected_names:
        raise BackupManifestVerificationError(
            "The backup manifest does not match the archive entries."
        )
    if DATABASE_ARCHIVE_PATH not in manifest.included_content:
        raise BackupSchemaError("The backup manifest does not include the application database.")


def _verify_manifest_files(
    archive: ZipFile,
    files: Iterable[BackupManifestFile],
    entries: dict[str, ZipInfo],
    limits: BackupVerificationLimits,
) -> None:
    actual_total = 0
    for expected in files:
        info = entries.get(expected.path)
        if info is None:
            raise BackupManifestVerificationError(
                f"The manifest entry is missing: {expected.path}."
            )
        if info.file_size != expected.size_bytes:
            raise BackupChecksumError(f"The backup entry size does not match: {expected.path}.")
        actual_size, actual_checksum = _digest_entry(
            archive,
            info,
            max_bytes=limits.max_file_uncompressed_bytes,
        )
        actual_total += actual_size
        if actual_total > limits.max_total_uncompressed_bytes:
            raise BackupArchiveBombError("The backup archive expands beyond the safe limit.")
        if actual_size != expected.size_bytes or actual_checksum != expected.checksum_sha256:
            raise BackupChecksumError(f"The backup entry checksum does not match: {expected.path}.")


def _verify_sqlite_entries(
    archive: ZipFile,
    manifest: BackupManifest,
    entries: dict[str, ZipInfo],
    limits: BackupVerificationLimits,
) -> None:
    database_paths = [
        path
        for path in manifest.included_content
        if path.startswith("database/")
        and Path(path).suffix.casefold() in {".db", ".sqlite", ".sqlite3"}
    ]
    if DATABASE_ARCHIVE_PATH not in database_paths:
        raise BackupSchemaError("The application database entry is invalid.")
    for path in database_paths:
        _verify_sqlite_entry(archive, entries[path], manifest, path, limits)


def _verify_sqlite_entry(
    archive: ZipFile,
    info: ZipInfo,
    manifest: BackupManifest,
    path: str,
    limits: BackupVerificationLimits,
) -> None:
    if info.file_size > limits.max_file_uncompressed_bytes:
        raise BackupArchiveBombError(f"The SQLite entry is too large: {path}.")
    descriptor, raw_path = tempfile.mkstemp(prefix="transloka-verify-", suffix=".db")
    os.close(descriptor)
    temporary_path = Path(raw_path)
    try:
        try:
            with archive.open(info, mode="r") as source, temporary_path.open("wb") as target:
                _copy_bounded(source, target, limits.max_file_uncompressed_bytes)
                target.flush()
                os.fsync(target.fileno())
        except (BadZipFile, EOFError, OSError, RuntimeError, ValueError, zlib.error) as exc:
            raise BackupArchiveCorruptionError(f"The SQLite entry cannot be read: {path}.") from exc
        _verify_sqlite_file(
            temporary_path,
            expected_schema=manifest.database_schema_version
            if path == DATABASE_ARCHIVE_PATH
            else None,
        )
    finally:
        try:
            temporary_path.unlink(missing_ok=True)
        except OSError:
            pass


def _verify_sqlite_file(path: Path, expected_schema: str | None) -> None:
    database_uri = f"{path.as_uri()}?mode=ro"
    try:
        with closing(sqlite3.connect(database_uri, uri=True)) as connection:
            integrity = tuple(
                str(row[0]).casefold() for row in connection.execute("PRAGMA integrity_check")
            )
            if integrity != ("ok",):
                raise BackupSchemaError("The backed-up SQLite database failed integrity_check.")
            if tuple(connection.execute("PRAGMA foreign_key_check")):
                raise BackupSchemaError("The backed-up SQLite database has foreign-key violations.")
            if expected_schema is None:
                return
            revisions = tuple(
                str(row[0]) for row in connection.execute("SELECT version_num FROM alembic_version")
            )
    except BackupVerificationError:
        raise
    except sqlite3.Error as exc:
        raise BackupSchemaError("The backed-up SQLite database schema is unreadable.") from exc
    if len(revisions) != 1 or revisions[0] != expected_schema:
        raise BackupSchemaError("The backed-up SQLite schema revision does not match the manifest.")


def _digest_entry(
    archive: ZipFile,
    info: ZipInfo,
    *,
    max_bytes: int,
) -> tuple[int, str]:
    digest = hashlib.sha256()
    size = 0
    try:
        with archive.open(info, mode="r") as source:
            for chunk in iter(lambda: source.read(_CHUNK_SIZE), b""):
                size += len(chunk)
                if size > max_bytes:
                    raise BackupArchiveBombError(
                        f"The backup entry expands beyond the safe limit: {info.filename}."
                    )
                digest.update(chunk)
    except (BadZipFile, EOFError, OSError, RuntimeError, ValueError, zlib.error) as exc:
        raise BackupArchiveCorruptionError(
            f"The backup entry cannot be read: {info.filename}."
        ) from exc
    return size, digest.hexdigest()


def _read_bounded(source: IO[bytes], limit: int) -> bytes:
    chunks: list[bytes] = []
    size = 0
    read = source.read
    while True:
        chunk = read(_CHUNK_SIZE)
        if not isinstance(chunk, bytes):
            raise BackupArchiveCorruptionError("The backup entry returned invalid data.")
        if not chunk:
            break
        size += len(chunk)
        if size > limit:
            raise BackupArchiveBombError("The backup manifest expands beyond the safe limit.")
        chunks.append(chunk)
    return b"".join(chunks)


def _copy_bounded(source: IO[bytes], target: BinaryIO, limit: int) -> int:
    read = source.read
    write = target.write
    size = 0
    for chunk in iter(lambda: read(_CHUNK_SIZE), b""):
        if not isinstance(chunk, bytes):
            raise BackupArchiveCorruptionError("The backup entry returned invalid data.")
        size += len(chunk)
        if size > limit:
            raise BackupArchiveBombError("The backup entry expands beyond the safe limit.")
        write(chunk)
    return size


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as source:
            for chunk in iter(lambda: source.read(_CHUNK_SIZE), b""):
                digest.update(chunk)
    except OSError as exc:
        raise BackupVerificationError("The backup archive checksum could not be read.") from exc
    return digest.hexdigest()


def _validate_checksum_text(value: str, name: str) -> None:
    if _SHA256_PATTERN.fullmatch(value) is None:
        raise BackupChecksumError(f"The {name} must be a lowercase SHA-256 digest.")


__all__ = [
    "BackupArchiveBombError",
    "BackupArchiveCorruptionError",
    "BackupChecksumError",
    "BackupManifestMissingError",
    "BackupManifestVerificationError",
    "BackupPathError",
    "BackupSchemaError",
    "BackupSymlinkError",
    "BackupVerificationError",
    "BackupVerificationLimits",
    "BackupVerificationResult",
    "DATABASE_ARCHIVE_PATH",
    "MANIFEST_ARCHIVE_PATH",
    "verify_backup",
    "verify_backup_archive",
]
