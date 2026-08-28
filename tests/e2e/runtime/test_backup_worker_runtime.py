import json
from pathlib import Path
from typing import cast

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker
from transloka_api.app import create_app
from transloka_api.middleware import (
    CLIENT_HEADER,
    CLIENT_HEADER_VALUE,
    CLIENT_VERSION_HEADER,
    CLIENT_VERSION_VALUE,
)
from transloka_core.backup.verification import verify_backup_archive
from transloka_core.database import transaction_scope
from transloka_core.database.models.backups import Backup, BackupStatus
from transloka_core.database.models.files import FileRole, FileStatus, StoredFile
from transloka_core.database.models.jobs import ApplicationJob, JobAttempt, JobStatus
from transloka_worker.app import create_queue_worker
from transloka_worker.backup import DatabaseBackupRequestLoader, ProductionBackupJobRunner
from transloka_worker.queue import resolve_queue_configuration
from transloka_worker.tasks.backup import BACKUP_TASK_NAME

REPOSITORY_ROOT = Path(__file__).parents[3]
ALEMBIC_CONFIGURATION = REPOSITORY_ROOT / "alembic.ini"
CLIENT_HEADERS = {
    CLIENT_HEADER: CLIENT_HEADER_VALUE,
    CLIENT_VERSION_HEADER: CLIENT_VERSION_VALUE,
}


def _database_artifacts() -> frozenset[Path]:
    return frozenset(
        path
        for path in REPOSITORY_ROOT.rglob("*")
        if path.is_file() and path.suffix.casefold() in {".db", ".sqlite", ".sqlite3"}
    )


def test_backup_app_to_tasksdb_to_worker_completes_and_publishes(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    initial_artifacts = _database_artifacts()
    data_root = tmp_path / "backup-runtime-e2e"
    monkeypatch.setenv("TRANSLOKA_DATA_DIR", str(data_root))
    command.upgrade(Config(str(ALEMBIC_CONFIGURATION)), "head")

    application = create_app()
    with TestClient(application) as client:
        with transaction_scope(application.state.session_factory) as session:
            session.add(
                StoredFile(
                    id="fil_00000000-0000-0000-0000-000000000001",
                    project_id=None,
                    document_id=None,
                    file_role=FileRole.ORIGINAL.value,
                    storage_key="documents/seed.pdf",
                    original_filename="seed.pdf",
                    safe_filename="seed.pdf",
                    mime_type="application/pdf",
                    size_bytes=0,
                    checksum_sha256="0" * 64,
                    is_immutable=1,
                    status=FileStatus.AVAILABLE.value,
                    metadata_json=None,
                    created_at="2026-08-28T00:00:00.000Z",
                    deleted_at=None,
                )
            )
        resp = client.post(
            "/api/v1/backups",
            headers={**CLIENT_HEADERS, "Idempotency-Key": "e2e-backup-1"},
            json={
                "backup_type": "METADATA",
                "include_original_files": False,
                "include_exports": False,
                "include_intermediate_files": False,
            },
        )
        assert resp.status_code == 202, resp.text
        body = resp.json()["data"]
        assert body["backup_id"] is None
        assert body["status"] == "QUEUED"
        job_id = cast(str, body["job_id"])
        assert application.state.backup_queue_owner.huey.pending_count() == 1

    # prove tasks.db contains single task
    configuration = resolve_queue_configuration(data_root)
    monkeypatch.setenv("TRANSLOKA_DATA_DIR", str(tmp_path / "decoy-data-root"))
    worker = create_queue_worker(configuration, worker_identifier="backup-runtime-e2e")
    try:
        huey = worker._consumer.huey  # type: ignore[attr-defined]
        task = huey.dequeue()
        assert task is not None
        assert task.name == BACKUP_TASK_NAME
        assert task.data == ((job_id,), {})
        huey.execute(task)
        assert huey.pending_count() == 0
    finally:
        worker.close_resources()
        worker.close_resources()

    # verify DB rows and archive via new app instance
    monkeypatch.setenv("TRANSLOKA_DATA_DIR", str(data_root))
    status_application = create_app()
    with TestClient(status_application) as client:
        # idempotent replay via same key should return COMPLETED
        replay = client.post(
            "/api/v1/backups",
            headers={**CLIENT_HEADERS, "Idempotency-Key": "e2e-backup-1"},
            json={
                "backup_type": "METADATA",
                "include_original_files": False,
                "include_exports": False,
                "include_intermediate_files": False,
            },
        )
        assert replay.status_code == 202
        assert replay.json()["data"]["status"] == "COMPLETED"
        assert replay.json()["data"]["job_id"] == job_id

        # GET /jobs/{job_id}
        job_resp = client.get(f"/api/v1/jobs/{job_id}", headers=CLIENT_HEADERS)
        assert job_resp.status_code == 200
        assert job_resp.json()["data"]["status"] == "COMPLETED"

        factory2 = cast(sessionmaker[Session], status_application.state.session_factory)
        with factory2() as session:
            job = session.get(ApplicationJob, job_id)
            assert job is not None
            assert job.status == JobStatus.COMPLETED.value
            assert job.progress == 1.0
            assert json.loads(job.result_json or "null")["schema"] == "transloka.backup.job.v1"
            attempt = session.scalar(select(JobAttempt).where(JobAttempt.job_id == job_id))
            assert attempt is not None
            assert attempt.status == "COMPLETED"
            stored = session.scalar(
                select(StoredFile).where(StoredFile.file_role == FileRole.BACKUP.value)
            )
            assert stored is not None
            assert stored.storage_key.startswith("backups/")
            backup = session.scalar(select(Backup).where(Backup.file_id == stored.id))
            assert backup is not None
            assert backup.status == BackupStatus.COMPLETED.value
            assert backup.file_id == stored.id
            assert Path(configuration.directories.root / stored.storage_key).is_file()
            # verify archive
            v = verify_backup_archive(
                configuration.directories.root / stored.storage_key,
                data_root=configuration.directories.root,
            )
            assert v.manifest.backup_type.value == "METADATA"
            assert "backup-warning.txt" in v.verified_files
            assert tuple(json.loads(backup.included_content_json)) == v.manifest.included_content

        # re-execution idempotent
        runner2 = ProductionBackupJobRunner(
            DatabaseBackupRequestLoader(factory2),
            factory2,
            configuration.directories,
            worker_identifier="backup-runtime-e2e",
        )
        second = runner2.run(job_id)
        assert second.status == JobStatus.COMPLETED
        # ensure no second archive
        with factory2() as session:
            count = len(session.scalars(select(Backup)).all())
            assert count == 1

    assert _database_artifacts() == initial_artifacts
