import sqlite3
from collections.abc import Iterator
from contextlib import closing
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from transloka_api.app import create_app
from transloka_api.middleware import (
    CLIENT_HEADER,
    CLIENT_HEADER_VALUE,
    CLIENT_VERSION_HEADER,
    CLIENT_VERSION_VALUE,
)
from transloka_core.backup.archive import create_full_project_backup
from transloka_core.backup.restore import (
    RestoreConfirmationError,
    RestoreError,
    RestoreWorkflow,
)
from transloka_core.storage import LocalDataDirectories, resolve_local_data_directories

REPOSITORY_ROOT = Path(__file__).parents[2]
ALEMBIC_CONFIGURATION = REPOSITORY_ROOT / "alembic.ini"


class RecordingCoordinator:
    def __init__(self, *, fail_restart: bool = False) -> None:
        self.events: list[str] = []
        self.fail_restart = fail_restart

    def enter_maintenance(self) -> None:
        self.events.append("enter")

    def pause_worker(self) -> None:
        self.events.append("pause")

    def close_database(self) -> None:
        self.events.append("close")

    def reopen_database(self) -> None:
        self.events.append("reopen")

    def restart_checks(self) -> None:
        self.events.append("restart")
        if self.fail_restart:
            raise RuntimeError("restart failed")

    def resume_worker(self) -> None:
        self.events.append("resume")

    def exit_maintenance(self) -> None:
        self.events.append("exit")


@pytest.fixture
def restore_source(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> Iterator[tuple[LocalDataDirectories, Path]]:
    directories = resolve_local_data_directories(tmp_path / "restore data")
    monkeypatch.setenv("TRANSLOKA_DATA_DIR", str(directories.root))
    command.upgrade(Config(str(ALEMBIC_CONFIGURATION)), "head")

    with closing(sqlite3.connect(directories.database / "transloka.db")) as connection:
        connection.execute("CREATE TABLE restore_marker (value TEXT NOT NULL)")
        connection.execute("INSERT INTO restore_marker VALUES ('original')")
        connection.commit()

    project = directories.projects / "project-1"
    project.mkdir(parents=True)
    (project / "metadata.json").write_text('{"name":"Original"}', encoding="utf-8")
    (project / "source.bin").write_bytes(b"original project")
    artifact = create_full_project_backup(directories)

    with closing(sqlite3.connect(directories.database / "transloka.db")) as connection:
        connection.execute("UPDATE restore_marker SET value = 'changed'")
        connection.commit()
    (project / "metadata.json").write_text('{"name":"Changed"}', encoding="utf-8")
    yield directories, directories.root / Path(artifact.storage_key)


def _marker_value(directories: LocalDataDirectories) -> str:
    with closing(sqlite3.connect(directories.database / "transloka.db")) as connection:
        return str(connection.execute("SELECT value FROM restore_marker").fetchone()[0])


def test_restore_requires_explicit_confirmation(
    restore_source: tuple[LocalDataDirectories, Path],
) -> None:
    directories, archive_path = restore_source
    coordinator = RecordingCoordinator()

    with pytest.raises(RestoreConfirmationError):
        RestoreWorkflow(directories, coordinator=coordinator).restore(
            archive_path,
            confirmation="yes",
        )

    assert coordinator.events == []
    assert _marker_value(directories) == "changed"


def test_restore_validates_before_replacement_and_creates_pre_restore_backup(
    restore_source: tuple[LocalDataDirectories, Path],
) -> None:
    directories, archive_path = restore_source
    coordinator = RecordingCoordinator()

    result = RestoreWorkflow(directories, coordinator=coordinator).restore(
        archive_path,
        confirmation="RESTORE",
    )

    assert _marker_value(directories) == "original"
    assert (directories.projects / "project-1" / "metadata.json").read_text(
        encoding="utf-8"
    ) == '{"name":"Original"}'
    assert result.pre_restore_backup.storage_key.startswith("backups/")
    assert (directories.root / Path(result.pre_restore_backup.storage_key)).is_file()
    assert coordinator.events == [
        "enter",
        "pause",
        "close",
        "reopen",
        "restart",
        "resume",
        "exit",
    ]


def test_invalid_archive_never_replaces_active_database(
    restore_source: tuple[LocalDataDirectories, Path],
) -> None:
    directories, _archive_path = restore_source
    invalid_archive = directories.backups / "invalid.zip"
    invalid_archive.write_bytes(b"not a zip archive")
    coordinator = RecordingCoordinator()

    with pytest.raises(RestoreError):
        RestoreWorkflow(directories, coordinator=coordinator).restore(
            invalid_archive,
            confirmation="RESTORE",
        )

    assert _marker_value(directories) == "changed"
    assert "close" not in coordinator.events
    assert coordinator.events == ["enter", "pause", "resume", "exit"]


def test_restart_failure_rolls_back_database_and_projects(
    restore_source: tuple[LocalDataDirectories, Path],
) -> None:
    directories, archive_path = restore_source
    coordinator = RecordingCoordinator(fail_restart=True)

    with pytest.raises(RestoreError):
        RestoreWorkflow(directories, coordinator=coordinator).restore(
            archive_path,
            confirmation="RESTORE",
        )

    assert _marker_value(directories) == "changed"
    assert (directories.projects / "project-1" / "metadata.json").read_text(
        encoding="utf-8"
    ) == '{"name":"Changed"}'
    assert coordinator.events == [
        "enter",
        "pause",
        "close",
        "reopen",
        "restart",
        "reopen",
        "resume",
        "exit",
    ]


def test_restore_api_rejects_missing_archive_without_exposing_paths(
    restore_source: tuple[LocalDataDirectories, Path],
) -> None:
    directories, _archive_path = restore_source
    headers = {
        CLIENT_HEADER: CLIENT_HEADER_VALUE,
        CLIENT_VERSION_HEADER: CLIENT_VERSION_VALUE,
    }

    with TestClient(create_app()) as client:
        response = client.post(
            "/api/v1/backups/restore",
            headers=headers,
            json={"storage_key": "backups/missing.zip", "confirmation": "RESTORE"},
        )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "RESTORE_ARCHIVE_INVALID"
    assert str(directories.root) not in response.text


def test_restore_api_runs_the_full_lifecycle(
    restore_source: tuple[LocalDataDirectories, Path],
) -> None:
    directories, archive_path = restore_source
    headers = {
        CLIENT_HEADER: CLIENT_HEADER_VALUE,
        CLIENT_VERSION_HEADER: CLIENT_VERSION_VALUE,
    }
    storage_key = archive_path.relative_to(directories.root).as_posix()

    with TestClient(create_app()) as client:
        response = client.post(
            "/api/v1/backups/restore",
            headers=headers,
            json={"storage_key": storage_key, "confirmation": "RESTORE"},
        )

    assert response.status_code == 200
    assert response.json()["data"]["archive_storage_key"] == storage_key
    assert response.json()["data"]["pre_restore_storage_key"].startswith("backups/")
    assert _marker_value(directories) == "original"
