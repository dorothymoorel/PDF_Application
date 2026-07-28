import hashlib
import json
import os
import sqlite3
import tempfile
from contextlib import closing
from dataclasses import dataclass
from datetime import UTC, datetime
from importlib.metadata import version
from pathlib import Path
from typing import Any
from zipfile import ZIP_DEFLATED, BadZipFile, ZipFile

from transloka_core.database import DATABASE_FILENAME
from transloka_core.storage import (
    LocalDataDirectories,
    LocalDataDirectoryError,
    ensure_local_data_directories,
    get_free_disk_bytes,
)

_APPLICATION_PACKAGE = "transloka-core"
_BACKUP_FORMAT_VERSION = 1
_DATABASE_ARCHIVE_PATH = f"database/{DATABASE_FILENAME}"
_MANIFEST_ARCHIVE_PATH = "manifest.json"
_SAFETY_MARGIN_BYTES = 16 * 1024 * 1024


class DatabaseBackupError(RuntimeError):
    """Raised when a verified database backup cannot be created."""


class InsufficientBackupSpaceError(DatabaseBackupError):
    """Raised before backup work starts when available disk space is insufficient."""


@dataclass(frozen=True, slots=True)
class DatabaseBackupArtifact:
    storage_key: str
    checksum_sha256: str
    database_checksum_sha256: str
    schema_revision: str
    size_bytes: int
    created_at: str


def create_database_backup(directories: LocalDataDirectories) -> DatabaseBackupArtifact:
    temporary_database: Path | None = None
    temporary_archive: Path | None = None
    try:
        ensure_local_data_directories(directories)
        source_database = directories.database / DATABASE_FILENAME
        if not source_database.is_file():
            raise DatabaseBackupError("The application database is unavailable.")

        required_bytes = source_database.stat().st_size * 2 + _SAFETY_MARGIN_BYTES
        if get_free_disk_bytes(directories) < required_bytes:
            raise InsufficientBackupSpaceError(
                "There is insufficient disk space to create a database backup."
            )

        temporary_database = _temporary_path(directories.temporary, ".db")
        temporary_archive = _temporary_path(directories.temporary, ".zip")
        _copy_with_sqlite_backup(source_database, temporary_database)
        schema_revision = _verify_database(temporary_database)
        database_checksum = _sha256_file(temporary_database)

        now = datetime.now(UTC)
        created_at = now.isoformat(timespec="milliseconds").replace("+00:00", "Z")
        archive_name = f"transloka-backup-{now.strftime('%Y%m%dT%H%M%S%fZ')}.zip"
        final_archive = directories.backups / archive_name
        if final_archive.exists():
            raise DatabaseBackupError("The backup destination is already occupied.")

        manifest = _manifest(
            created_at=created_at,
            schema_revision=schema_revision,
            database_checksum=database_checksum,
            database_size=temporary_database.stat().st_size,
        )
        _write_archive(temporary_archive, temporary_database, manifest)
        _verify_archive(temporary_archive, manifest)
        archive_checksum = _sha256_file(temporary_archive)
        archive_size = temporary_archive.stat().st_size
        os.replace(temporary_archive, final_archive)
        temporary_archive = None

        return DatabaseBackupArtifact(
            storage_key=(Path("backups") / archive_name).as_posix(),
            checksum_sha256=archive_checksum,
            database_checksum_sha256=database_checksum,
            schema_revision=schema_revision,
            size_bytes=archive_size,
            created_at=created_at,
        )
    except DatabaseBackupError:
        raise
    except (BadZipFile, LocalDataDirectoryError, OSError, sqlite3.Error, ValueError) as exc:
        raise DatabaseBackupError("The database backup could not be created safely.") from exc
    finally:
        _remove_temporary_database(temporary_database)
        _remove_temporary_file(temporary_archive)


def _temporary_path(directory: Path, suffix: str) -> Path:
    descriptor, raw_path = tempfile.mkstemp(
        prefix="transloka-backup-",
        suffix=f"{suffix}.tmp",
        dir=directory,
    )
    os.close(descriptor)
    return Path(raw_path)


def _copy_with_sqlite_backup(source_path: Path, destination_path: Path) -> None:
    source_uri = f"{source_path.as_uri()}?mode=ro"
    with (
        closing(sqlite3.connect(source_uri, uri=True)) as source,
        closing(sqlite3.connect(destination_path)) as destination,
        destination,
    ):
        source.backup(destination)
        journal_mode = destination.execute("PRAGMA journal_mode = DELETE").fetchone()
        if journal_mode is None or str(journal_mode[0]).casefold() != "delete":
            raise DatabaseBackupError("The temporary database could not be finalized safely.")


def _verify_database(database_path: Path) -> str:
    database_uri = f"{database_path.as_uri()}?mode=ro"
    with closing(sqlite3.connect(database_uri, uri=True)) as connection:
        integrity = tuple(
            str(row[0]).casefold() for row in connection.execute("PRAGMA integrity_check")
        )
        if integrity != ("ok",):
            raise DatabaseBackupError("The temporary database failed integrity verification.")
        if tuple(connection.execute("PRAGMA foreign_key_check")):
            raise DatabaseBackupError("The temporary database has foreign key violations.")
        revisions = tuple(
            str(row[0]) for row in connection.execute("SELECT version_num FROM alembic_version")
        )
        if len(revisions) != 1:
            raise DatabaseBackupError("The temporary database schema revision is invalid.")
        return revisions[0]


def _manifest(
    *,
    created_at: str,
    schema_revision: str,
    database_checksum: str,
    database_size: int,
) -> dict[str, Any]:
    return {
        "format_version": _BACKUP_FORMAT_VERSION,
        "backup_type": "DATABASE_ONLY",
        "application_version": version(_APPLICATION_PACKAGE),
        "database_schema_version": schema_revision,
        "created_at": created_at,
        "included_content": [_DATABASE_ARCHIVE_PATH],
        "files": [
            {
                "path": _DATABASE_ARCHIVE_PATH,
                "size_bytes": database_size,
                "checksum_sha256": database_checksum,
            }
        ],
    }


def _write_archive(
    archive_path: Path,
    database_path: Path,
    manifest: dict[str, Any],
) -> None:
    with archive_path.open("w+b") as archive_file:
        with ZipFile(
            archive_file,
            mode="w",
            compression=ZIP_DEFLATED,
            compresslevel=9,
        ) as archive:
            archive.write(database_path, _DATABASE_ARCHIVE_PATH)
            archive.writestr(
                _MANIFEST_ARCHIVE_PATH,
                json.dumps(manifest, sort_keys=True, separators=(",", ":")),
            )
        archive_file.flush()
        os.fsync(archive_file.fileno())


def _verify_archive(archive_path: Path, expected_manifest: dict[str, Any]) -> None:
    with ZipFile(archive_path, mode="r") as archive:
        if set(archive.namelist()) != {_DATABASE_ARCHIVE_PATH, _MANIFEST_ARCHIVE_PATH}:
            raise DatabaseBackupError("The backup archive contents are invalid.")
        if archive.testzip() is not None:
            raise DatabaseBackupError("The backup archive failed checksum verification.")
        manifest = json.loads(archive.read(_MANIFEST_ARCHIVE_PATH))
        if manifest != expected_manifest:
            raise DatabaseBackupError("The backup manifest failed verification.")
        with archive.open(_DATABASE_ARCHIVE_PATH) as database_file:
            archived_checksum = _sha256_stream(database_file)
        if archived_checksum != expected_manifest["files"][0]["checksum_sha256"]:
            raise DatabaseBackupError("The archived database checksum is invalid.")


def _sha256_file(path: Path) -> str:
    with path.open("rb") as file:
        return _sha256_stream(file)


def _sha256_stream(stream: Any) -> str:
    checksum = hashlib.sha256()
    for chunk in iter(lambda: stream.read(1024 * 1024), b""):
        checksum.update(chunk)
    return checksum.hexdigest()


def _remove_temporary_file(path: Path | None) -> None:
    if path is None:
        return
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass


def _remove_temporary_database(path: Path | None) -> None:
    if path is None:
        return
    _remove_temporary_file(path)
    _remove_temporary_file(Path(f"{path}-wal"))
    _remove_temporary_file(Path(f"{path}-shm"))
