from collections.abc import Iterator
from pathlib import Path
from typing import cast
from uuid import UUID

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker
from transloka_api.app import create_app
from transloka_api.middleware import (
    CLIENT_HEADER,
    CLIENT_HEADER_VALUE,
    CLIENT_VERSION_HEADER,
    CLIENT_VERSION_VALUE,
)
from transloka_core.database import transaction_scope
from transloka_core.database.models.jobs import (
    ApplicationJob,
    JobAttempt,
    JobAttemptStatus,
    JobStatus,
    JobType,
)
from transloka_core.jobs.dispatch import JobDispatchService
from transloka_core.jobs.progress import JobProgressService

REPOSITORY_ROOT = Path(__file__).parents[3]
ALEMBIC_CONFIGURATION = REPOSITORY_ROOT / "alembic.ini"
CLIENT_HEADERS = {
    CLIENT_HEADER: CLIENT_HEADER_VALUE,
    CLIENT_VERSION_HEADER: CLIENT_VERSION_VALUE,
}
PROJECT = {
    "name": "Job API Project",
    "description": None,
    "source_language": "en",
    "target_language": "id",
    "document_type": "TECHNICAL_BOOK",
    "translation_style": "PROFESSIONAL",
    "reconstruction_mode": "HYBRID",
}


class RecordingQueue:
    name = "test-jobs"

    def enqueue(self, _job_id: str) -> None:
        pass


@pytest.fixture
def job_api(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> Iterator[tuple[TestClient, sessionmaker[Session], str]]:
    root = tmp_path / "job api"
    monkeypatch.setenv("TRANSLOKA_DATA_DIR", str(root))
    command.upgrade(Config(str(ALEMBIC_CONFIGURATION)), "head")
    application = create_app()
    with TestClient(application) as client:
        project_response = client.post(
            "/api/v1/projects",
            headers=CLIENT_HEADERS,
            json=PROJECT,
        )
        assert project_response.status_code == 201
        project_id = cast(str, project_response.json()["data"]["id"])
        yield client, cast(sessionmaker[Session], application.state.session_factory), project_id


def _dispatch(
    factory: sessionmaker[Session],
    project_id: str,
    key: str,
    job_type: JobType = JobType.MAINTENANCE,
) -> str:
    return (
        JobDispatchService(factory, RecordingQueue())
        .dispatch(
            job_type=job_type,
            idempotency_key=key,
            project_id=project_id,
        )
        .job_id
    )


def test_get_job_returns_latest_safe_resource_and_poll_hint(
    job_api: tuple[TestClient, sessionmaker[Session], str],
) -> None:
    client, factory, project_id = job_api
    job_id = _dispatch(factory, project_id, "get-running")
    JobProgressService(factory).update(job_id, progress=0.4, current_stage="EXTRACT_TEXT")

    response = client.get(
        f"/api/v1/jobs/{job_id}",
        headers={"Origin": "http://localhost:3000"},
    )

    assert response.status_code == 200
    assert response.headers["Retry-After"] == "2"
    assert "Retry-After" in response.headers["Access-Control-Expose-Headers"]
    assert response.json()["data"] == {
        "id": job_id,
        "job_type": "MAINTENANCE",
        "status": "RUNNING",
        "progress": 0.4,
        "current_stage": "EXTRACT_TEXT",
        "project_id": project_id,
        "document_id": None,
        "retry_count": 0,
        "max_retries": 3,
        "created_at": response.json()["data"]["created_at"],
        "started_at": response.json()["data"]["started_at"],
        "completed_at": None,
        "error": None,
    }
    assert response.json()["meta"]["request_id"]
    for internal_field in (
        "queue_name",
        "idempotency_key",
        "payload_json",
        "result_json",
        "heartbeat_at",
        "huey_id",
    ):
        assert internal_field not in response.text


def test_list_jobs_supports_filters_and_opaque_cursor(
    job_api: tuple[TestClient, sessionmaker[Session], str],
) -> None:
    client, factory, project_id = job_api
    first = _dispatch(factory, project_id, "list-first")
    second = _dispatch(factory, project_id, "list-second")
    _dispatch(factory, project_id, "list-other", JobType.BACKUP_DATABASE)
    with transaction_scope(factory) as session:
        first_row = session.get(ApplicationJob, first)
        second_row = session.get(ApplicationJob, second)
        assert first_row is not None
        assert second_row is not None
        first_row.created_at = "2026-08-08T01:00:00.000Z"
        second_row.created_at = "2026-08-08T02:00:00.000Z"

    first_page = client.get(
        "/api/v1/jobs",
        params={
            "project_id": project_id,
            "job_type": "MAINTENANCE",
            "status": "QUEUED",
            "limit": 1,
        },
    )

    assert first_page.status_code == 200
    assert [row["id"] for row in first_page.json()["data"]] == [second]
    pagination = first_page.json()["meta"]["pagination"]
    assert pagination["has_more"] is True
    assert pagination["next_cursor"]

    second_page = client.get(
        "/api/v1/jobs",
        params={
            "project_id": project_id,
            "job_type": "MAINTENANCE",
            "status": "QUEUED",
            "limit": 1,
            "cursor": pagination["next_cursor"],
        },
    )
    no_document_match = client.get(
        "/api/v1/jobs",
        params={"document_id": "doc_00000000-0000-4000-8000-000000000001"},
    )

    assert [row["id"] for row in second_page.json()["data"]] == [first]
    assert second_page.json()["meta"]["pagination"] == {
        "limit": 1,
        "next_cursor": None,
        "has_more": False,
    }
    assert no_document_match.json()["data"] == []


def test_missing_job_and_invalid_cursor_return_normalized_errors(
    job_api: tuple[TestClient, sessionmaker[Session], str],
) -> None:
    client, _factory, _project_id = job_api

    missing = client.get("/api/v1/jobs/job_00000000-0000-4000-8000-000000000001")
    invalid_cursor = client.get("/api/v1/jobs", params={"cursor": "not-base64!"})

    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "JOB_NOT_FOUND"
    assert invalid_cursor.status_code == 422
    assert invalid_cursor.json()["error"]["code"] == "VALIDATION_ERROR"


def test_job_attempts_are_ordered_and_hide_worker_details(
    job_api: tuple[TestClient, sessionmaker[Session], str],
) -> None:
    client, factory, project_id = job_api
    job_id = _dispatch(factory, project_id, "attempts")
    with transaction_scope(factory) as session:
        session.add_all(
            (
                JobAttempt(
                    id=str(UUID(int=2)),
                    job_id=job_id,
                    attempt_number=2,
                    status=JobAttemptStatus.FAILED.value,
                    worker_identifier="private-worker",
                    started_at="2026-08-08T02:00:00.000Z",
                    completed_at="2026-08-08T02:00:02.000Z",
                    duration_ms=2000,
                    error_code="MODEL_TIMEOUT",
                    error_message="The local model timed out.",
                    details_json='{"private":"detail"}',
                ),
                JobAttempt(
                    id=str(UUID(int=1)),
                    job_id=job_id,
                    attempt_number=1,
                    status=JobAttemptStatus.COMPLETED.value,
                    worker_identifier=None,
                    started_at="2026-08-08T01:00:00.000Z",
                    completed_at="2026-08-08T01:00:01.000Z",
                    duration_ms=1000,
                    error_code=None,
                    error_message=None,
                    details_json=None,
                ),
            )
        )

    response = client.get(f"/api/v1/jobs/{job_id}/attempts")

    assert response.status_code == 200
    assert [attempt["attempt_number"] for attempt in response.json()["data"]] == [1, 2]
    assert response.json()["data"][1]["error"] == {
        "code": "MODEL_TIMEOUT",
        "message": "The local model timed out.",
    }
    assert "private-worker" not in response.text
    assert '"private":"detail"' not in response.text


def test_cancel_queued_job_is_immediate_and_repeated_requests_are_idempotent(
    job_api: tuple[TestClient, sessionmaker[Session], str],
) -> None:
    client, factory, project_id = job_api
    job_id = _dispatch(factory, project_id, "cancel-queued")

    first = client.post(
        f"/api/v1/jobs/{job_id}/cancel",
        headers=CLIENT_HEADERS,
        json={"reason": "Cancelled by user."},
    )
    second = client.post(
        f"/api/v1/jobs/{job_id}/cancel",
        headers=CLIENT_HEADERS,
        json={"reason": "Cancelled again."},
    )

    assert first.status_code == 200
    assert first.json()["data"]["status"] == "CANCELLED"
    assert first.json()["data"]["completed_at"] is not None
    assert second.status_code == 200
    assert second.json()["data"] == first.json()["data"]


def test_cancel_running_job_requests_cooperative_checkpoint(
    job_api: tuple[TestClient, sessionmaker[Session], str],
) -> None:
    client, factory, project_id = job_api
    job_id = _dispatch(factory, project_id, "cancel-running")
    JobProgressService(factory).update(job_id, progress=0.4, current_stage="ATOMIC_UNIT")

    response = client.post(
        f"/api/v1/jobs/{job_id}/cancel",
        headers=CLIENT_HEADERS,
        json={"reason": "Cancelled by user."},
    )

    assert response.status_code == 200
    assert response.json()["data"]["status"] == "CANCELLATION_REQUESTED"
    assert response.json()["data"]["progress"] == 0.4
    assert response.json()["data"]["current_stage"] == "ATOMIC_UNIT"
    assert response.json()["data"]["completed_at"] is None


def test_completed_job_cannot_be_cancelled(
    job_api: tuple[TestClient, sessionmaker[Session], str],
) -> None:
    client, factory, project_id = job_api
    job_id = _dispatch(factory, project_id, "cancel-completed")
    with transaction_scope(factory) as session:
        row = session.get(ApplicationJob, job_id)
        assert row is not None
        row.status = JobStatus.COMPLETED.value
        row.progress = 1.0
        row.completed_at = "2026-08-08T00:00:00.000Z"

    response = client.post(
        f"/api/v1/jobs/{job_id}/cancel",
        headers=CLIENT_HEADERS,
        json={"reason": "Too late."},
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "JOB_STATE_INVALID"


def test_job_openapi_contract_includes_cancel_without_future_retry() -> None:
    schema = create_app().openapi()
    operations = {
        ("/api/v1/jobs", "get"): "list_jobs",
        ("/api/v1/jobs/{job_id}", "get"): "get_job",
        ("/api/v1/jobs/{job_id}/attempts", "get"): "get_job_attempts",
        ("/api/v1/jobs/{job_id}/cancel", "post"): "cancel_job",
    }

    for (path, method), operation_id in operations.items():
        operation = schema["paths"][path][method]
        assert operation["operationId"] == operation_id
        for status_code in ("403", "404", "422", "500"):
            response_schema = operation["responses"][status_code]["content"]["application/json"][
                "schema"
            ]
            assert response_schema["$ref"] == "#/components/schemas/ErrorResponse"
    cancel = schema["paths"]["/api/v1/jobs/{job_id}/cancel"]["post"]
    assert (
        cancel["responses"]["409"]["content"]["application/json"]["schema"]["$ref"]
        == "#/components/schemas/ErrorResponse"
    )
    assert "/api/v1/jobs/{job_id}/retry" not in schema["paths"]
