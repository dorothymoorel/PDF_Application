import hashlib
import sqlite3
from collections.abc import Iterator
from contextlib import closing
from pathlib import Path
from threading import Event, Thread

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
    FileRestoreCoordinator,
    RestoreConfirmationError,
    RestoreError,
    RestoreWorkflow,
)
from transloka_core.storage import LocalDataDirectories, resolve_local_data_directories

REPOSITORY_ROOT = Path(__file__).parents[2]
ALEMBIC_CONFIGURATION = REPOSITORY_ROOT / "alembic.ini"
BACKUP_ID = "bkp_00000000-0000-0000-0000-000000000001"
OTHER_BACKUP_ID = "bkp_00000000-0000-0000-0000-000000000002"
BACKUP_FILE_ID = "fil_00000000-0000-0000-0000-000000000001"


class RecordingCoordinator:
    def __init__(
        self,
        *,
        fail_restart: bool = False,
        interrupt_restart: bool = False,
    ) -> None:
        self.events: list[str] = []
        self.fail_restart = fail_restart
        self.interrupt_restart = interrupt_restart

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
        if self.interrupt_restart:
            raise KeyboardInterrupt
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


def _record_backup(directories: LocalDataDirectories, archive_path: Path) -> None:
    storage_key = archive_path.relative_to(directories.root).as_posix()
    checksum = hashlib.sha256(archive_path.read_bytes()).hexdigest()
    created_at = "2026-08-22T00:00:00.000Z"
    with closing(sqlite3.connect(directories.database / "transloka.db")) as connection:
        connection.execute(
            """
            INSERT INTO stored_files (
                id, project_id, document_id, file_role, storage_key,
                original_filename, safe_filename, mime_type, size_bytes,
                checksum_sha256, is_immutable, status, metadata_json,
                created_at, deleted_at
            ) VALUES (?, NULL, NULL, 'BACKUP', ?, NULL, ?, 'application/zip', ?, ?, 1,
                      'VALIDATED', NULL, ?, NULL)
            """,
            (
                BACKUP_FILE_ID,
                storage_key,
                archive_path.name,
                archive_path.stat().st_size,
                checksum,
                created_at,
            ),
        )
        connection.execute(
            """
            INSERT INTO backups (
                id, backup_type, file_id, application_version,
                database_schema_version, status, size_bytes, checksum_sha256,
                included_content_json, created_at, completed_at, error_code
            ) VALUES (?, 'FULL_PROJECTS', ?, '0.1.0', '0017_backups', 'COMPLETED',
                      ?, ?, '[]', ?, ?, NULL)
            """,
            (
                BACKUP_ID,
                BACKUP_FILE_ID,
                archive_path.stat().st_size,
                checksum,
                created_at,
                created_at,
            ),
        )
        connection.commit()


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


def test_restore_can_leave_project_files_untouched(
    restore_source: tuple[LocalDataDirectories, Path],
) -> None:
    directories, archive_path = restore_source

    RestoreWorkflow(directories, coordinator=RecordingCoordinator()).restore(
        archive_path,
        confirmation="RESTORE",
        restore_files=False,
    )

    assert _marker_value(directories) == "original"
    assert (directories.projects / "project-1" / "metadata.json").read_text(
        encoding="utf-8"
    ) == '{"name":"Changed"}'


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
        "close",
        "reopen",
        "resume",
        "exit",
    ]


def test_keyboard_interrupt_rolls_back_database_and_projects(
    restore_source: tuple[LocalDataDirectories, Path],
) -> None:
    directories, archive_path = restore_source
    coordinator = RecordingCoordinator(interrupt_restart=True)

    with pytest.raises(KeyboardInterrupt):
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
        "close",
        "reopen",
        "resume",
        "exit",
    ]


def test_missing_referenced_file_fails_restart_check_and_rolls_back(
    restore_source: tuple[LocalDataDirectories, Path],
) -> None:
    directories, _archive_path = restore_source
    with closing(sqlite3.connect(directories.database / "transloka.db")) as connection:
        connection.execute(
            """
            INSERT INTO stored_files (
                id, project_id, document_id, file_role, storage_key,
                original_filename, safe_filename, mime_type, size_bytes,
                checksum_sha256, is_immutable, status, metadata_json,
                created_at, deleted_at
            ) VALUES (
                'fil_00000000-0000-0000-0000-000000000099', NULL, NULL,
                'ORIGINAL', 'projects/missing/original.pdf', 'original.pdf',
                'original.pdf', 'application/pdf', 7,
                'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa',
                1, 'VALIDATED', NULL, '2026-08-22T00:00:00.000Z', NULL
            )
            """
        )
        connection.commit()
    artifact = create_full_project_backup(directories)
    with closing(sqlite3.connect(directories.database / "transloka.db")) as connection:
        connection.execute("UPDATE restore_marker SET value = 'integrity-current'")
        connection.commit()

    with pytest.raises(RestoreError):
        RestoreWorkflow(directories).restore(
            artifact.storage_key,
            confirmation="RESTORE",
        )

    assert _marker_value(directories) == "integrity-current"


def test_restore_api_rejects_missing_backup_without_exposing_paths(
    restore_source: tuple[LocalDataDirectories, Path],
) -> None:
    directories, _archive_path = restore_source
    headers = {
        CLIENT_HEADER: CLIENT_HEADER_VALUE,
        CLIENT_VERSION_HEADER: CLIENT_VERSION_VALUE,
    }

    with TestClient(create_app()) as client:
        response = client.post(
            f"/api/v1/backups/{BACKUP_ID}/restore",
            headers={**headers, "Idempotency-Key": "restore-missing-backup"},
            json={
                "confirmation": "RESTORE",
                "create_pre_restore_backup": True,
                "restore_files": True,
            },
        )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "BACKUP_NOT_FOUND"
    assert str(directories.root) not in response.text


def test_restore_api_matches_contract_and_hides_storage_paths(
    restore_source: tuple[LocalDataDirectories, Path],
) -> None:
    directories, archive_path = restore_source
    headers = {
        CLIENT_HEADER: CLIENT_HEADER_VALUE,
        CLIENT_VERSION_HEADER: CLIENT_VERSION_VALUE,
        "Idempotency-Key": "restore-backup-1",
    }
    _record_backup(directories, archive_path)

    with TestClient(create_app()) as client:
        response = client.post(
            f"/api/v1/backups/{BACKUP_ID}/restore",
            headers=headers,
            json={
                "confirmation": "RESTORE",
                "create_pre_restore_backup": True,
                "restore_files": True,
            },
        )

    assert response.status_code == 202, response.text
    assert response.json()["data"]["backup_id"] == BACKUP_ID
    assert response.json()["data"]["job_id"].startswith("job_")
    assert response.json()["data"]["pre_restore_backup_id"].startswith("bkp_")
    assert response.json()["data"]["status"] == "COMPLETED"
    assert "storage_key" not in response.text
    assert str(directories.root) not in response.text
    assert _marker_value(directories) == "original"


def test_restore_api_reuses_idempotent_result_and_rejects_conflict(
    restore_source: tuple[LocalDataDirectories, Path],
) -> None:
    directories, archive_path = restore_source
    headers = {
        CLIENT_HEADER: CLIENT_HEADER_VALUE,
        CLIENT_VERSION_HEADER: CLIENT_VERSION_VALUE,
        "Idempotency-Key": "restore-backup-idempotent",
    }
    payload = {
        "confirmation": "RESTORE",
        "create_pre_restore_backup": True,
        "restore_files": True,
    }
    _record_backup(directories, archive_path)

    with TestClient(create_app()) as client:
        first = client.post(
            f"/api/v1/backups/{BACKUP_ID}/restore",
            headers=headers,
            json=payload,
        )
        duplicate = client.post(
            f"/api/v1/backups/{BACKUP_ID}/restore",
            headers=headers,
            json=payload,
        )
        conflict = client.post(
            f"/api/v1/backups/{OTHER_BACKUP_ID}/restore",
            headers=headers,
            json=payload,
        )

    assert first.status_code == 202, first.text
    assert duplicate.status_code == 202
    assert duplicate.json() == first.json()
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "IDEMPOTENCY_CONFLICT"


def test_api_blocks_mutations_but_keeps_health_and_job_reads_available(
    restore_source: tuple[LocalDataDirectories, Path],
) -> None:
    directories, _archive_path = restore_source
    headers = {
        CLIENT_HEADER: CLIENT_HEADER_VALUE,
        CLIENT_VERSION_HEADER: CLIENT_VERSION_VALUE,
    }
    coordinator = FileRestoreCoordinator(directories)

    with TestClient(create_app()) as client:
        coordinator.enter_maintenance()
        try:
            mutation = client.post("/api/v1/projects", headers=headers, json={})
            health = client.get("/health")
            job = client.get("/api/v1/jobs/job_missing", headers=headers)
        finally:
            coordinator.exit_maintenance()

    assert mutation.status_code == 503
    assert mutation.json()["error"]["code"] == "APPLICATION_IN_MAINTENANCE_MODE"
    assert health.status_code == 200
    assert job.status_code == 404


def test_restore_waits_for_inflight_api_mutation(
    restore_source: tuple[LocalDataDirectories, Path],
) -> None:
    directories, _archive_path = restore_source
    headers = {
        CLIENT_HEADER: CLIENT_HEADER_VALUE,
        CLIENT_VERSION_HEADER: CLIENT_VERSION_VALUE,
    }
    mutation_started = Event()
    release_mutation = Event()
    maintenance_entered = Event()
    application = create_app()

    @application.post("/api/v1/test-mutation")
    def test_mutation() -> dict[str, bool]:
        mutation_started.set()
        assert release_mutation.wait(2.0) is True
        return {"completed": True}

    def enter_maintenance() -> None:
        coordinator.enter_maintenance()
        maintenance_entered.set()

    coordinator = FileRestoreCoordinator(directories)
    with TestClient(application) as client:
        mutation_thread = Thread(
            target=lambda: client.post("/api/v1/test-mutation", headers=headers),
            daemon=True,
        )
        mutation_thread.start()
        assert mutation_started.wait(2.0) is True

        maintenance_thread = Thread(target=enter_maintenance, daemon=True)
        maintenance_thread.start()
        try:
            assert maintenance_entered.wait(0.1) is False
            release_mutation.set()
            assert maintenance_entered.wait(2.0) is True
        finally:
            release_mutation.set()
            coordinator.exit_maintenance()
            mutation_thread.join(timeout=2.0)
            maintenance_thread.join(timeout=2.0)
