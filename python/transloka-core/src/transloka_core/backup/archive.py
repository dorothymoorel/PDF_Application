"""Create verified backup archives with explicit content selection."""

import hashlib
import os
import shutil
import sqlite3
import tempfile
from contextlib import closing
from dataclasses import dataclass
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path
from typing import IO, BinaryIO
from zipfile import ZIP_DEFLATED, ZipFile

from transloka_core.backup.database import InsufficientBackupSpaceError
from transloka_core.backup.manifest import (
    PRIVATE_DATA_WARNING,
    BackupManifest,
    BackupManifestError,
    BackupType,
    build_manifest,
    verify_manifest,
)
from transloka_core.database import DATABASE_FILENAME
from transloka_core.storage import (
    LocalDataDirectories,
    LocalDataDirectoryError,
    ensure_local_data_directories,
    get_free_disk_bytes,
)

_APPLICATION_PACKAGE = "transloka-core"
_DATABASE_ARCHIVE_PATH = f"database/{DATABASE_FILENAME}"
_QUEUE_DATABASE_ARCHIVE_PATH = "database/tasks.db"
_WARNING_ARCHIVE_PATH = "backup-warning.txt"
_SAFETY_MARGIN_BYTES = 16 * 1024 * 1024
_CHUNK_SIZE = 1024 * 1024
_METADATA_FILENAMES = frozenset({"manifest.json", "metadata.json", "project.json"})
_SUPPORTED_TYPES = frozenset(
    {BackupType.DATABASE_ONLY, BackupType.METADATA, BackupType.FULL_PROJECTS}
)


class BackupArchiveError(RuntimeError):
    """Raised when a selected backup archive cannot be created safely."""


class UnsupportedBackupTypeError(BackupArchiveError):
    """Raised when a later backup scope is requested before its task is ready."""


@dataclass(frozen=True, slots=True)
class BackupArchiveArtifact:
    """A final archive that passed manifest and archive-entry verification."""

    backup_type: BackupType
    storage_key: str
    checksum_sha256: str
    size_bytes: int
    created_at: str
    manifest: BackupManifest

    @property
    def included_content(self) -> tuple[str, ...]:
        return self.manifest.included_content

    @property
    def privacy_warning(self) -> str:
        return self.manifest.privacy_warning


def create_backup(
    directories: LocalDataDirectories,
    backup_type: BackupType | str,
    *,
    include_queue_database: bool = False,
    include_temporary: bool = False,
) -> BackupArchiveArtifact:
    """Create a database-only, metadata, or full-project backup.

    Model files, existing backup archives, and the temporary staging directory are
    excluded by default. The Huey queue database is also excluded by default and
    is included only when ``include_queue_database=True`` is explicitly selected.
    """

    _validate_boolean(include_queue_database, "include_queue_database")
    _validate_boolean(include_temporary, "include_temporary")
    selected_type = _coerce_backup_type(backup_type)
    if selected_type not in _SUPPORTED_TYPES:
        raise UnsupportedBackupTypeError(
            f"Backup type {selected_type.value} is not implemented by this task."
        )

    staging_root: Path | None = None
    temporary_archive: Path | None = None
    try:
        ensure_local_data_directories(directories)
        source_database = _regular_file(directories.database / DATABASE_FILENAME)
        source_paths = _select_source_paths(
            directories,
            selected_type,
            include_queue_database=include_queue_database,
            include_temporary=include_temporary,
        )
        source_paths.insert(0, (_DATABASE_ARCHIVE_PATH, source_database))
        required_bytes = sum(path.stat().st_size for _relative, path in source_paths)
        required_bytes = required_bytes * 2 + _SAFETY_MARGIN_BYTES
        if get_free_disk_bytes(directories) < required_bytes:
            raise InsufficientBackupSpaceError(
                "There is insufficient disk space to create the selected backup."
            )

        staging_root = Path(
            tempfile.mkdtemp(
                prefix="transloka-backup-stage-",
                dir=directories.temporary,
            )
        )
        for relative_path, source_path in source_paths:
            destination = _safe_stage_path(staging_root, relative_path)
            if relative_path in {_DATABASE_ARCHIVE_PATH, _QUEUE_DATABASE_ARCHIVE_PATH}:
                _copy_sqlite_database(source_path, destination)
            else:
                _copy_regular_file(source_path, destination)

        warning_path = _safe_stage_path(staging_root, _WARNING_ARCHIVE_PATH)
        _write_warning(warning_path)
        included_content = tuple(
            sorted(relative_path for relative_path, _source_path in source_paths)
            + [_WARNING_ARCHIVE_PATH]
        )
        created_at = _timestamp()
        schema_revision = _schema_revision(staging_root / _DATABASE_ARCHIVE_PATH)
        manifest = build_manifest(
            backup_type=selected_type,
            application_version=version(_APPLICATION_PACKAGE),
            database_schema_version=schema_revision,
            root=staging_root,
            included_content=list(included_content),
            created_at=created_at,
        )
        verified_manifest = verify_manifest(manifest, staging_root)

        temporary_archive = _temporary_archive_path(directories.temporary)
        _write_archive(temporary_archive, staging_root, verified_manifest)
        _verify_archive(temporary_archive, verified_manifest)
        archive_size = temporary_archive.stat().st_size
        archive_checksum = _sha256_file(temporary_archive)
        archive_name = _archive_name(selected_type, created_at)
        final_archive = directories.backups / archive_name
        if final_archive.exists() or final_archive.is_symlink():
            raise BackupArchiveError("The backup destination is already occupied.")
        os.replace(temporary_archive, final_archive)
        temporary_archive = None

        return BackupArchiveArtifact(
            backup_type=selected_type,
            storage_key=(Path("backups") / archive_name).as_posix(),
            checksum_sha256=archive_checksum,
            size_bytes=archive_size,
            created_at=created_at,
            manifest=verified_manifest,
        )
    except (BackupArchiveError, InsufficientBackupSpaceError):
        raise
    except (
        BackupManifestError,
        LocalDataDirectoryError,
        OSError,
        sqlite3.Error,
        ValueError,
    ) as exc:
        raise BackupArchiveError("The backup archive could not be created safely.") from exc
    finally:
        _remove_tree(staging_root)
        _remove_file(temporary_archive)


def create_metadata_backup(
    directories: LocalDataDirectories,
    *,
    include_queue_database: bool = False,
) -> BackupArchiveArtifact:
    """Create a database plus project metadata backup."""

    return create_backup(
        directories,
        BackupType.METADATA,
        include_queue_database=include_queue_database,
    )


def create_full_project_backup(
    directories: LocalDataDirectories,
    *,
    include_queue_database: bool = False,
    include_temporary: bool = False,
) -> BackupArchiveArtifact:
    """Create a database plus all managed project files backup."""

    return create_backup(
        directories,
        BackupType.FULL_PROJECTS,
        include_queue_database=include_queue_database,
        include_temporary=include_temporary,
    )


def _coerce_backup_type(value: BackupType | str) -> BackupType:
    try:
        return value if isinstance(value, BackupType) else BackupType(value)
    except (TypeError, ValueError) as exc:
        raise UnsupportedBackupTypeError("The backup type is unsupported.") from exc


def _select_source_paths(
    directories: LocalDataDirectories,
    backup_type: BackupType,
    *,
    include_queue_database: bool,
    include_temporary: bool,
) -> list[tuple[str, Path]]:
    selected: list[tuple[str, Path]] = []
    if include_queue_database:
        queue_database = directories.database / "tasks.db"
        if queue_database.exists():
            selected.append((_QUEUE_DATABASE_ARCHIVE_PATH, _regular_file(queue_database)))

    if backup_type is BackupType.METADATA:
        selected.extend(_project_metadata_files(directories.projects))
    elif backup_type is BackupType.FULL_PROJECTS:
        selected.extend(_tree_files(directories.projects, directories.root))

    if include_temporary:
        selected.extend(_tree_files(directories.temporary, directories.root))
    return _deduplicate_sources(selected)


def _project_metadata_files(root: Path) -> list[tuple[str, Path]]:
    return [
        (relative_path, path)
        for relative_path, path in _tree_files(root, root.parent)
        if path.name.casefold() in _METADATA_FILENAMES
    ]


def _tree_files(root: Path, data_root: Path) -> list[tuple[str, Path]]:
    if not root.exists():
        return []
    if root.is_symlink() or not root.is_dir():
        raise BackupArchiveError(f"The backup source directory is invalid: {root.name}.")
    files: list[tuple[str, Path]] = []
    for current_root, directory_names, file_names in os.walk(root, followlinks=False):
        current = Path(current_root)
        directory_names[:] = [name for name in directory_names if not (current / name).is_symlink()]
        for name in sorted(file_names):
            path = current / name
            if path.is_symlink():
                continue
            if not path.is_file():
                continue
            files.append((path.relative_to(data_root).as_posix(), path))
    return sorted(files)


def _deduplicate_sources(sources: list[tuple[str, Path]]) -> list[tuple[str, Path]]:
    deduplicated: dict[str, Path] = {}
    for relative_path, source_path in sources:
        if relative_path in deduplicated:
            continue
        deduplicated[relative_path] = source_path
    return sorted(deduplicated.items())


def _regular_file(path: Path) -> Path:
    if path.is_symlink() or not path.is_file():
        raise BackupArchiveError(f"The backup source file is unavailable: {path.name}.")
    return path


def _safe_stage_path(root: Path, relative_path: str) -> Path:
    candidate = (root / Path(*relative_path.split("/"))).resolve(strict=False)
    if not candidate.is_relative_to(root.resolve(strict=True)):
        raise BackupArchiveError("A backup path escapes the staging directory.")
    candidate.parent.mkdir(parents=True, exist_ok=True)
    return candidate


def _copy_regular_file(source: Path, destination: Path) -> None:
    with source.open("rb") as source_file, destination.open("wb") as destination_file:
        _copy_stream(source_file, destination_file)
        destination_file.flush()
        os.fsync(destination_file.fileno())


def _copy_sqlite_database(source: Path, destination: Path) -> None:
    source_uri = f"{source.as_uri()}?mode=ro"
    destination.parent.mkdir(parents=True, exist_ok=True)
    with (
        closing(sqlite3.connect(source_uri, uri=True)) as source_connection,
        closing(sqlite3.connect(destination)) as destination_connection,
    ):
        source_connection.backup(destination_connection)
        journal_mode = destination_connection.execute("PRAGMA journal_mode = DELETE").fetchone()
        if journal_mode is None or str(journal_mode[0]).casefold() != "delete":
            raise BackupArchiveError("The staged database could not be finalized safely.")
        destination_connection.commit()


def _schema_revision(database_path: Path) -> str:
    with closing(sqlite3.connect(f"{database_path.as_uri()}?mode=ro", uri=True)) as connection:
        integrity = connection.execute("PRAGMA integrity_check").fetchone()
        if integrity != ("ok",):
            raise BackupArchiveError("The staged database failed integrity verification.")
        if tuple(connection.execute("PRAGMA foreign_key_check")):
            raise BackupArchiveError("The staged database has foreign key violations.")
        revisions = tuple(
            str(row[0]) for row in connection.execute("SELECT version_num FROM alembic_version")
        )
        if len(revisions) != 1:
            raise BackupArchiveError("The staged database schema revision is invalid.")
        return revisions[0]


def _write_warning(path: Path) -> None:
    with path.open("w", encoding="utf-8", newline="\n") as warning_file:
        warning_file.write(f"{PRIVATE_DATA_WARNING}\n")
        warning_file.flush()
        os.fsync(warning_file.fileno())


def _write_archive(path: Path, staging_root: Path, manifest: BackupManifest) -> None:
    with path.open("w+b") as archive_file:
        with ZipFile(
            archive_file,
            mode="w",
            compression=ZIP_DEFLATED,
            compresslevel=9,
        ) as archive:
            for relative_path in manifest.included_content:
                archive.write(staging_root / Path(*relative_path.split("/")), relative_path)
            archive.writestr("manifest.json", manifest.to_json())
        archive_file.flush()
        os.fsync(archive_file.fileno())


def _verify_archive(path: Path, expected_manifest: BackupManifest) -> None:
    with ZipFile(path, mode="r") as archive:
        expected_names = set(expected_manifest.included_content) | {"manifest.json"}
        if set(archive.namelist()) != expected_names:
            raise BackupArchiveError("The backup archive contents are incomplete or unexpected.")
        if archive.testzip() is not None:
            raise BackupArchiveError("The backup archive failed ZIP checksum verification.")
        actual_manifest = BackupManifest.from_json(archive.read("manifest.json"))
        if actual_manifest.to_dict() != expected_manifest.to_dict():
            raise BackupArchiveError("The backup manifest failed verification.")
        for entry in expected_manifest.files:
            with archive.open(entry.path) as source:
                actual_size, actual_checksum = _stream_digest(source)
            if actual_size != entry.size_bytes or actual_checksum != entry.checksum_sha256:
                raise BackupArchiveError(f"The archived file failed verification: {entry.path}.")


def _temporary_archive_path(directory: Path) -> Path:
    descriptor, raw_path = tempfile.mkstemp(
        prefix="transloka-backup-",
        suffix=".zip.tmp",
        dir=directory,
    )
    os.close(descriptor)
    return Path(raw_path)


def _archive_name(backup_type: BackupType, created_at: str) -> str:
    stamp = created_at.replace("-", "").replace(":", "").replace(".", "")
    stamp = stamp.replace("Z", "")
    return f"transloka-backup-{backup_type.value.lower()}-{stamp}.zip"


def _timestamp() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _validate_boolean(value: bool, name: str) -> None:
    if not isinstance(value, bool):
        raise BackupArchiveError(f"The {name} option must be a boolean.")


def _copy_stream(source: BinaryIO, destination: BinaryIO) -> None:
    for chunk in iter(lambda: source.read(_CHUNK_SIZE), b""):
        destination.write(chunk)


def _stream_digest(source: IO[bytes]) -> tuple[int, str]:
    digest = hashlib.sha256()
    size = 0
    for chunk in iter(lambda: source.read(_CHUNK_SIZE), b""):
        size += len(chunk)
        digest.update(chunk)
    return size, digest.hexdigest()


def _sha256_file(path: Path) -> str:
    with path.open("rb") as source:
        return _stream_digest(source)[1]


def _remove_file(path: Path | None) -> None:
    if path is None:
        return
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass


def _remove_tree(path: Path | None) -> None:
    if path is None:
        return
    try:
        shutil.rmtree(path, ignore_errors=True)
    except OSError:
        pass


__all__ = [
    "BackupArchiveArtifact",
    "BackupArchiveError",
    "InsufficientBackupSpaceError",
    "UnsupportedBackupTypeError",
    "create_backup",
    "create_full_project_backup",
    "create_metadata_backup",
]
