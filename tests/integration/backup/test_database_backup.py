import hashlib
import json
import os
import shutil
import sqlite3
from collections.abc import Iterator
from pathlib import Path
from zipfile import ZipFile

import pytest
from alembic import command
from alembic.config import Config
from transloka_core.backup import (
    DatabaseBackupError,
    InsufficientBackupSpaceError,
    create_database_backup,
)
from transloka_core.database import DATABASE_FILENAME
from transloka_core.storage import LocalDataDirectories, resolve_local_data_directories

REPOSITORY_ROOT = Path(__file__).parents[3]
ALEMBIC_CONFIGURATION = REPOSITORY_ROOT / "alembic.ini"
DATABASE_ARCHIVE_PATH = f"database/{DATABASE_FILENAME}"


@pytest.fixture
def backup_source(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> Iterator[tuple[LocalDataDirectories, sqlite3.Connection]]:
    directories = resolve_local_data_directories(tmp_path / "data")
    monkeypatch.setenv("TRANSLOKA_DATA_DIR", str(directories.root))
    command.upgrade(Config(str(ALEMBIC_CONFIGURATION)), "head")
    database_path = directories.database / DATABASE_FILENAME
    writer = sqlite3.connect(database_path)
    writer.execute("PRAGMA journal_mode = WAL")
    writer.execute(
        "INSERT INTO app_metadata (key, value, updated_at) VALUES (?, ?, ?)",
        ("backup-test", "preserved", "2026-07-28T00:00:00.000Z"),
    )
    writer.commit()
    yield directories, writer
    writer.close()


def _artifact_path(directories: LocalDataDirectories, storage_key: str) -> Path:
    return directories.root / Path(storage_key)


def test_database_backup_is_valid_and_does_not_modify_original(
    backup_source: tuple[LocalDataDirectories, sqlite3.Connection],
) -> None:
    directories, _writer = backup_source
    database_path = directories.database / DATABASE_FILENAME
    source_checksum = hashlib.sha256(database_path.read_bytes()).digest()
    assert Path(f"{database_path}-wal").is_file()

    artifact = create_database_backup(directories)
    archive_path = _artifact_path(directories, artifact.storage_key)

    assert archive_path.is_file()
    assert artifact.storage_key.startswith("backups/transloka-backup-")
    assert artifact.size_bytes == archive_path.stat().st_size
    assert hashlib.sha256(database_path.read_bytes()).digest() == source_checksum
    assert list(directories.temporary.iterdir()) == []


def test_database_backup_can_be_restored_into_temporary_database(
    backup_source: tuple[LocalDataDirectories, sqlite3.Connection],
    tmp_path: Path,
) -> None:
    directories, _writer = backup_source
    artifact = create_database_backup(directories)
    archive_path = _artifact_path(directories, artifact.storage_key)
    restored_database = tmp_path / "restored.db"

    with ZipFile(archive_path) as archive:
        with archive.open(DATABASE_ARCHIVE_PATH) as source:
            with restored_database.open("wb") as destination:
                shutil.copyfileobj(source, destination)

    with sqlite3.connect(restored_database) as connection:
        assert connection.execute("PRAGMA integrity_check").fetchone() == ("ok",)
        assert connection.execute(
            "SELECT value FROM app_metadata WHERE key = ?",
            ("backup-test",),
        ).fetchone() == ("preserved",)


def test_database_backup_checksums_and_manifest_match_archive(
    backup_source: tuple[LocalDataDirectories, sqlite3.Connection],
) -> None:
    directories, _writer = backup_source
    artifact = create_database_backup(directories)
    archive_path = _artifact_path(directories, artifact.storage_key)

    assert hashlib.sha256(archive_path.read_bytes()).hexdigest() == artifact.checksum_sha256
    with ZipFile(archive_path) as archive:
        database_bytes = archive.read(DATABASE_ARCHIVE_PATH)
        manifest = json.loads(archive.read("manifest.json"))

    assert hashlib.sha256(database_bytes).hexdigest() == artifact.database_checksum_sha256
    assert manifest["backup_type"] == "DATABASE_ONLY"
    assert manifest["format_version"] == 1
    assert manifest["application_version"]
    assert manifest["database_schema_version"] == artifact.schema_revision
    assert manifest["created_at"] == artifact.created_at
    assert manifest["included_content"] == [DATABASE_ARCHIVE_PATH]
    assert manifest["files"][0]["checksum_sha256"] == artifact.database_checksum_sha256
    assert all(":\\" not in json.dumps(value) for value in manifest.values())


def test_interrupted_backup_leaves_no_final_or_temporary_file(
    monkeypatch: pytest.MonkeyPatch,
    backup_source: tuple[LocalDataDirectories, sqlite3.Connection],
) -> None:
    directories, _writer = backup_source

    def interrupt_replace(_source: os.PathLike[str], _destination: os.PathLike[str]) -> None:
        raise OSError("simulated interruption")

    monkeypatch.setattr("transloka_core.backup.database.os.replace", interrupt_replace)

    with pytest.raises(DatabaseBackupError):
        create_database_backup(directories)

    assert list(directories.backups.iterdir()) == []
    assert list(directories.temporary.iterdir()) == []


def test_insufficient_disk_fails_before_creating_backup_files(
    monkeypatch: pytest.MonkeyPatch,
    backup_source: tuple[LocalDataDirectories, sqlite3.Connection],
) -> None:
    directories, _writer = backup_source
    monkeypatch.setattr("transloka_core.backup.database.get_free_disk_bytes", lambda _dirs: 0)

    with pytest.raises(InsufficientBackupSpaceError):
        create_database_backup(directories)

    assert list(directories.backups.iterdir()) == []
    assert list(directories.temporary.iterdir()) == []
