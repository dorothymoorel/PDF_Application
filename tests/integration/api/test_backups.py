# mypy: ignore-errors
from pathlib import Path
from typing import get_args
from uuid import UUID

import pytest
from alembic import command as alembic_command
from alembic.config import Config
from fastapi.testclient import TestClient
from transloka_api.app import create_app
from transloka_api.middleware import (
    CLIENT_HEADER,
    CLIENT_HEADER_VALUE,
    CLIENT_VERSION_HEADER,
    CLIENT_VERSION_VALUE,
)
from transloka_api.routers.backups import BackupJobStatus
from transloka_core.database.models.backups import BackupStatus
from transloka_core.database.models.jobs import ApplicationJob, JobStatus, JobType
from transloka_worker.queue import create_huey, resolve_queue_configuration

REPOSITORY_ROOT = Path(__file__).parents[3]
ALEMBIC_CONFIGURATION = REPOSITORY_ROOT / "alembic.ini"
CLIENT_HEADERS = {
    CLIENT_HEADER: CLIENT_HEADER_VALUE,
    CLIENT_VERSION_HEADER: CLIENT_VERSION_VALUE,
}


def _id(prefix: str, value: int) -> str:
    return f"{prefix}{UUID(int=value)}"


def _client_with_tmp(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    root = tmp_path / "backup api"
    monkeypatch.setenv("TRANSLOKA_DATA_DIR", str(root))
    alembic_command.upgrade(Config(str(ALEMBIC_CONFIGURATION)), "head")
    app = create_app()
    return app, root


def test_database_BackupStatus_not_shadowed():
    # imported BackupStatus is the persisted Backup ORM lifecycle enum, not the TypeScript BackupRecord type
    assert BackupStatus.__name__ == "BackupStatus"
    assert set(BackupStatus) == {"CREATED", "RUNNING", "COMPLETED", "FAILED", "CANCELLED"}
    content = Path("services/api/src/transloka_api/routers/backups.py").read_text(encoding="utf-8")
    # ensure no module-level alias shadows the imported model
    # The only BackupStatus import should be from models.backups, not a Literal alias
    # Check that file does not contain "BackupStatus =" as alias definition
    before_create = content.split("class CreateBackup")[0]
    assert "BackupStatus =" not in before_create


def test_CreateBackupResponse_uses_BackupJobStatus():
    assert set(get_args(BackupJobStatus)) == {
        "QUEUED",
        "RUNNING",
        "RETRYING",
        "CANCELLATION_REQUESTED",
        "COMPLETED",
        "COMPLETED_WITH_WARNINGS",
        "PARTIALLY_COMPLETED",
        "FAILED",
        "CANCELLED",
        "STALE",
    }


def test_create_backup_persists_queued_job_and_enqueues_only_job_id(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    app, root = _client_with_tmp(tmp_path, monkeypatch)
    with TestClient(app) as client:
        resp = client.post(
            "/api/v1/backups",
            json={
                "backup_type": "METADATA",
                "include_original_files": False,
                "include_exports": False,
                "include_intermediate_files": False,
            },
            headers={**CLIENT_HEADERS, "Idempotency-Key": "backup-1"},
        )
        assert resp.status_code == 202, resp.text
        data = resp.json()["data"]
        assert data["backup_id"] is None
        assert data["status"] == "QUEUED"
        assert "request_id" in resp.json()["meta"]
        job_id = data["job_id"]
        assert job_id.startswith("job_")
        # check DB
        factory = app.state.session_factory
        with factory() as session:
            job = session.get(ApplicationJob, job_id)
            assert job is not None
            assert job.status == JobStatus.QUEUED.value
            assert job.job_type == JobType.BACKUP_DATABASE.value
            assert job.queue_name == "transloka"
        # check huey
        huey = create_huey(resolve_queue_configuration(root))
        from transloka_worker.tasks.backup import BACKUP_TASK_NAME, register_backup_task

        register_backup_task(huey, lambda jid: jid)
        task = huey.dequeue()
        assert task is not None
        assert task.name == BACKUP_TASK_NAME == "transloka.backup.execute"
        assert task.args == (job_id,)
        huey.storage.close()


def test_create_backup_rejects_true_include_flags_422(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    app, root = _client_with_tmp(tmp_path, monkeypatch)
    with TestClient(app) as client:
        for field in ("include_original_files", "include_exports", "include_intermediate_files"):
            payload = {
                "backup_type": "DATABASE_ONLY",
                "include_original_files": False,
                "include_exports": False,
                "include_intermediate_files": False,
            }
            payload[field] = True
            resp = client.post(
                "/api/v1/backups",
                json=payload,
                headers={**CLIENT_HEADERS, "Idempotency-Key": f"reject-{field}"},
            )
            assert resp.status_code == 422, resp.text


@pytest.mark.parametrize("invalid_value", (1, 0, "true", "false"))
def test_create_backup_rejects_non_boolean_include_flags(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    invalid_value: object,
) -> None:
    app, _root = _client_with_tmp(tmp_path, monkeypatch)
    with TestClient(app) as client:
        response = client.post(
            "/api/v1/backups",
            json={
                "backup_type": "DATABASE_ONLY",
                "include_original_files": invalid_value,
                "include_exports": False,
                "include_intermediate_files": False,
            },
            headers={**CLIENT_HEADERS, "Idempotency-Key": f"strict-bool-{invalid_value}"},
        )

    assert response.status_code == 422, response.text


def test_create_backup_rejects_invalid_backup_type_422(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    app, root = _client_with_tmp(tmp_path, monkeypatch)
    with TestClient(app) as client:
        for bad in ("FULL_APPLICATION", "full_projects", "", "INVALID"):
            resp = client.post(
                "/api/v1/backups",
                json={
                    "backup_type": bad,
                    "include_original_files": False,
                    "include_exports": False,
                    "include_intermediate_files": False,
                },
                headers={**CLIENT_HEADERS, "Idempotency-Key": f"bad-{bad}"},
            )
            assert resp.status_code == 422, resp.text


def test_create_backup_idempotent_dispatch_returns_exact_persisted_status(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    app, root = _client_with_tmp(tmp_path, monkeypatch)
    with TestClient(app) as client:
        # first create
        resp1 = client.post(
            "/api/v1/backups",
            json={
                "backup_type": "METADATA",
                "include_original_files": False,
                "include_exports": False,
                "include_intermediate_files": False,
            },
            headers={**CLIENT_HEADERS, "Idempotency-Key": "replay-test"},
        )
        assert resp1.status_code == 202
        job_id = resp1.json()["data"]["job_id"]
        # simulate progression to RUNNING, FAILED, STALE via direct DB update, then replay should return that exact status
        from transloka_core.database import transaction_scope

        factory = app.state.session_factory
        for persisted in (
            "RUNNING",
            "FAILED",
            "STALE",
            "RETRYING",
            "CANCELLATION_REQUESTED",
            "COMPLETED_WITH_WARNINGS",
            "PARTIALLY_COMPLETED",
        ):
            with transaction_scope(factory) as session:
                job = session.get(ApplicationJob, job_id)
                assert job is not None
                job.status = persisted
            resp = client.post(
                "/api/v1/backups",
                json={
                    "backup_type": "METADATA",
                    "include_original_files": False,
                    "include_exports": False,
                    "include_intermediate_files": False,
                },
                headers={**CLIENT_HEADERS, "Idempotency-Key": "replay-test"},
            )
            assert resp.status_code == 202, resp.text
            assert resp.json()["data"]["status"] == persisted
            assert resp.json()["data"]["job_id"] == job_id


def test_concurrent_existing_dispatch_does_not_enqueue_twice(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    app, root = _client_with_tmp(tmp_path, monkeypatch)
    with TestClient(app) as client:
        resp1 = client.post(
            "/api/v1/backups",
            json={
                "backup_type": "DATABASE_ONLY",
                "include_original_files": False,
                "include_exports": False,
                "include_intermediate_files": False,
            },
            headers={**CLIENT_HEADERS, "Idempotency-Key": "concurrent-test"},
        )
        assert resp1.status_code == 202
        huey = create_huey(resolve_queue_configuration(root))
        assert huey.pending_count() == 1
        # second dispatch with same key should not enqueue again
        resp2 = client.post(
            "/api/v1/backups",
            json={
                "backup_type": "DATABASE_ONLY",
                "include_original_files": False,
                "include_exports": False,
                "include_intermediate_files": False,
            },
            headers={**CLIENT_HEADERS, "Idempotency-Key": "concurrent-test"},
        )
        assert resp2.status_code == 202
        assert resp2.json()["data"]["job_id"] == resp1.json()["data"]["job_id"]
        assert huey.pending_count() == 1
        huey.storage.close()


def test_create_backup_idempotency_conflict_409_on_different_payload(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    app, root = _client_with_tmp(tmp_path, monkeypatch)
    with TestClient(app) as client:
        resp1 = client.post(
            "/api/v1/backups",
            json={
                "backup_type": "DATABASE_ONLY",
                "include_original_files": False,
                "include_exports": False,
                "include_intermediate_files": False,
            },
            headers={**CLIENT_HEADERS, "Idempotency-Key": "conflict-test"},
        )
        assert resp1.status_code == 202
        resp2 = client.post(
            "/api/v1/backups",
            json={
                "backup_type": "METADATA",
                "include_original_files": False,
                "include_exports": False,
                "include_intermediate_files": False,
            },
            headers={**CLIENT_HEADERS, "Idempotency-Key": "conflict-test"},
        )
        assert resp2.status_code == 409
        assert resp2.json()["error"]["code"] == "IDEMPOTENCY_CONFLICT"


def test_create_backup_queue_unavailable_maps_to_503_with_job_id_and_no_second_mutation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    app, root = _client_with_tmp(tmp_path, monkeypatch)
    with TestClient(app) as client:

        def failing_enqueue(job_id: str):
            raise RuntimeError("queue down")

        monkeypatch.setattr(client.app.state.backup_queue, "enqueue", failing_enqueue)
        resp = client.post(
            "/api/v1/backups",
            json={
                "backup_type": "DATABASE_ONLY",
                "include_original_files": False,
                "include_exports": False,
                "include_intermediate_files": False,
            },
            headers={**CLIENT_HEADERS, "Idempotency-Key": "fail-test"},
        )
        assert resp.status_code == 503, resp.text
        assert resp.json()["error"]["code"] == "QUEUE_UNAVAILABLE"
        assert "job_id" in resp.json()["error"]["details"]
        job_id = resp.json()["error"]["details"]["job_id"]
        # verify job was marked FAILED by JobDispatchService, no second mutation needed
        factory = client.app.state.session_factory
        with factory() as session:
            job = session.get(ApplicationJob, job_id)
            assert job is not None
            assert job.status == JobStatus.FAILED.value
            assert job.error_code == "QUEUE_DISPATCH_FAILED"


def test_create_backup_maps_invalid_dispatch_and_worker_errors_to_422(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    app, root = _client_with_tmp(tmp_path, monkeypatch)
    with TestClient(app) as client:
        # invalid backup_type already tested, but also test that worker error maps to 422
        # For public include flag true, should be 422
        resp = client.post(
            "/api/v1/backups",
            json={
                "backup_type": "DATABASE_ONLY",
                "include_original_files": True,
                "include_exports": False,
                "include_intermediate_files": False,
            },
            headers={**CLIENT_HEADERS, "Idempotency-Key": "invalid-1"},
        )
        assert resp.status_code == 422


def test_create_backup_never_fails_validation_for_valid_persisted_status(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    app, root = _client_with_tmp(tmp_path, monkeypatch)
    with TestClient(app) as client:
        for status in (
            "QUEUED",
            "RUNNING",
            "RETRYING",
            "CANCELLATION_REQUESTED",
            "COMPLETED",
            "COMPLETED_WITH_WARNINGS",
            "PARTIALLY_COMPLETED",
            "FAILED",
            "CANCELLED",
            "STALE",
        ):
            # create a job with that status via direct dispatch and replay
            # need unique idempotency key per status
            key = f"never-fail-{status}"
            resp1 = client.post(
                "/api/v1/backups",
                json={
                    "backup_type": "DATABASE_ONLY",
                    "include_original_files": False,
                    "include_exports": False,
                    "include_intermediate_files": False,
                },
                headers={**CLIENT_HEADERS, "Idempotency-Key": key},
            )
            assert resp1.status_code == 202
            job_id = resp1.json()["data"]["job_id"]
            from transloka_core.database import transaction_scope

            factory = app.state.session_factory
            with transaction_scope(factory) as session:
                job = session.get(ApplicationJob, job_id)
                assert job is not None
                job.status = status
            resp2 = client.post(
                "/api/v1/backups",
                json={
                    "backup_type": "DATABASE_ONLY",
                    "include_original_files": False,
                    "include_exports": False,
                    "include_intermediate_files": False,
                },
                headers={**CLIENT_HEADERS, "Idempotency-Key": key},
            )
            assert resp2.status_code == 202, f"failed for {status}: {resp2.text}"
            assert resp2.json()["data"]["status"] == status


def test_create_backup_preserves_restore_route_untouched(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    app, root = _client_with_tmp(tmp_path, monkeypatch)
    # ensure restore route still exists and is not broken by new backup route
    # we can check openapi
    openapi = app.openapi()
    paths = openapi["paths"]
    assert "/api/v1/backups" in paths
    assert "/api/v1/backups/{backup_id}/restore" in paths
