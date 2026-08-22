import json
import os
import sqlite3
from collections.abc import Iterator
from pathlib import Path
from zipfile import ZipFile

import pytest
from alembic import command
from alembic.config import Config
from transloka_core.backup import (
    BackupArchiveError,
    BackupType,
    InsufficientBackupSpaceError,
    create_backup,
    create_full_project_backup,
    create_metadata_backup,
)
from transloka_core.storage import LocalDataDirectories, resolve_local_data_directories

REPOSITORY_ROOT = Path(__file__).parents[3]
ALEMBIC_CONFIGURATION = REPOSITORY_ROOT / "alembic.ini"


@pytest.fixture
def archive_source(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> Iterator[LocalDataDirectories]:
    directories = resolve_local_data_directories(tmp_path / "backup data")
    monkeypatch.setenv("TRANSLOKA_DATA_DIR", str(directories.root))
    command.upgrade(Config(str(ALEMBIC_CONFIGURATION)), "head")
    project_root = directories.projects / "prj_demo"
    (project_root / "original").mkdir(parents=True)
    (project_root / "metadata.json").write_text('{"name":"Demo"}', encoding="utf-8")
    (project_root / "manifest.json").write_text('{"version":1}', encoding="utf-8")
    (project_root / "original" / "source.pdf").write_bytes(b"source")
    (project_root / "assets" / "image.bin").parent.mkdir()
    (project_root / "assets" / "image.bin").write_bytes(b"asset")
    (directories.models / "model.gguf").write_bytes(b"model")
    (directories.temporary / "unfinished.tmp").write_bytes(b"temporary")
    with sqlite3.connect(directories.database / "tasks.db") as queue:
        queue.execute("CREATE TABLE queue_marker (value TEXT NOT NULL)")
        queue.execute("INSERT INTO queue_marker VALUES ('queue')")
    yield directories


def _archive_path(directories: LocalDataDirectories, storage_key: str) -> Path:
    return directories.root / Path(storage_key)


def _names(archive_path: Path) -> set[str]:
    with ZipFile(archive_path) as archive:
        return set(archive.namelist())


def test_metadata_backup_includes_metadata_and_private_data_warning(
    archive_source: LocalDataDirectories,
) -> None:
    artifact = create_metadata_backup(archive_source)
    archive_path = _archive_path(archive_source, artifact.storage_key)

    names = _names(archive_path)
    assert names == {
        "database/transloka.db",
        "projects/prj_demo/manifest.json",
        "projects/prj_demo/metadata.json",
        "backup-warning.txt",
        "manifest.json",
    }
    with ZipFile(archive_path) as archive:
        manifest = json.loads(archive.read("manifest.json"))
        warning = archive.read("backup-warning.txt").decode("utf-8")
    assert "private" in manifest["privacy_warning"].casefold()
    assert "sensitive" in warning.casefold()
    assert artifact.manifest.is_verified is True


def test_full_project_backup_includes_project_files_and_excludes_unsafe_defaults(
    archive_source: LocalDataDirectories,
) -> None:
    artifact = create_full_project_backup(archive_source)
    names = _names(_archive_path(archive_source, artifact.storage_key))

    assert "projects/prj_demo/original/source.pdf" in names
    assert "projects/prj_demo/assets/image.bin" in names
    assert "models/model.gguf" not in names
    assert "temp/unfinished.tmp" not in names
    assert "database/tasks.db" not in names


def test_explicit_queue_database_inclusion_is_available(
    archive_source: LocalDataDirectories,
) -> None:
    artifact = create_backup(
        archive_source,
        BackupType.FULL_PROJECTS,
        include_queue_database=True,
    )

    assert "database/tasks.db" in _names(_archive_path(archive_source, artifact.storage_key))


def test_large_project_file_list_is_streamed_and_complete(
    archive_source: LocalDataDirectories,
) -> None:
    large_root = archive_source.projects / "prj_large" / "assets"
    large_root.mkdir(parents=True)
    for index in range(1000):
        (large_root / f"asset-{index:04d}.bin").write_bytes(f"{index}".encode())

    artifact = create_full_project_backup(archive_source)
    names = _names(_archive_path(archive_source, artifact.storage_key))
    assert sum(name.startswith("projects/prj_large/assets/") for name in names) == 1000
    assert artifact.size_bytes > 0


def test_interrupted_archive_leaves_no_final_or_temporary_files(
    monkeypatch: pytest.MonkeyPatch,
    archive_source: LocalDataDirectories,
) -> None:
    def interrupt_replace(_source: os.PathLike[str], _destination: os.PathLike[str]) -> None:
        raise OSError("simulated interruption")

    monkeypatch.setattr("transloka_core.backup.archive.os.replace", interrupt_replace)

    with pytest.raises(BackupArchiveError):
        create_full_project_backup(archive_source)

    assert list(archive_source.backups.iterdir()) == []
    assert [path.name for path in archive_source.temporary.iterdir()] == ["unfinished.tmp"]


def test_insufficient_disk_fails_before_staging(
    monkeypatch: pytest.MonkeyPatch,
    archive_source: LocalDataDirectories,
) -> None:
    monkeypatch.setattr("transloka_core.backup.archive.get_free_disk_bytes", lambda _dirs: 0)

    with pytest.raises(InsufficientBackupSpaceError):
        create_full_project_backup(archive_source)

    assert list(archive_source.backups.iterdir()) == []
    assert [path.name for path in archive_source.temporary.iterdir()] == ["unfinished.tmp"]


def test_later_backup_types_are_not_silently_implemented(
    archive_source: LocalDataDirectories,
) -> None:
    with pytest.raises(BackupArchiveError, match="not implemented"):
        create_backup(archive_source, BackupType.FULL_APPLICATION)
