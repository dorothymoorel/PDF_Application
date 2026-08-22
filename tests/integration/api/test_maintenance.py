import os
import time
from collections.abc import Iterator
from pathlib import Path

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
from transloka_core.database.models.jobs import ApplicationJob, JobStatus

REPOSITORY_ROOT = Path(__file__).parents[3]
ALEMBIC_CONFIGURATION = REPOSITORY_ROOT / "alembic.ini"
CLIENT_HEADERS = {
    CLIENT_HEADER: CLIENT_HEADER_VALUE,
    CLIENT_VERSION_HEADER: CLIENT_VERSION_VALUE,
}


@pytest.fixture
def maintenance_api(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> Iterator[tuple[TestClient, sessionmaker[Session], Path]]:
    root = tmp_path / "maintenance api"
    monkeypatch.setenv("TRANSLOKA_DATA_DIR", str(root))
    command.upgrade(Config(str(ALEMBIC_CONFIGURATION)), "head")
    application = create_app()
    with TestClient(application) as client:
        yield client, application.state.session_factory, root


def test_database_integrity_endpoint_returns_job_report(
    maintenance_api: tuple[TestClient, sessionmaker[Session], Path],
) -> None:
    client, factory, root = maintenance_api

    response = client.post(
        "/api/v1/maintenance/database-integrity-check",
        headers=CLIENT_HEADERS,
    )

    assert response.status_code == 202
    body = response.json()
    assert body["data"]["operation"] == "DATABASE_INTEGRITY_CHECK"
    assert body["data"]["status"] == "COMPLETED"
    assert body["data"]["healthy"] is True
    assert body["data"]["job_id"].startswith("job_")
    assert body["meta"]["request_id"]
    assert str(root) not in response.text
    with factory() as session:
        job = session.get(ApplicationJob, body["data"]["job_id"])
        assert job is not None
        assert job.status == JobStatus.COMPLETED.value


def test_temp_cleanup_endpoint_honors_dry_run(
    maintenance_api: tuple[TestClient, sessionmaker[Session], Path],
) -> None:
    client, _factory, root = maintenance_api
    temporary = root / "temp" / "candidate.tmp"
    temporary.write_bytes(b"candidate")
    old_timestamp = time.time() - (2 * 24 * 60 * 60)
    os.utime(temporary, (old_timestamp, old_timestamp))

    response = client.post(
        "/api/v1/maintenance/temp-cleanup",
        headers=CLIENT_HEADERS,
        json={"older_than_days": 1, "dry_run": True},
    )

    assert response.status_code == 202
    assert response.json()["data"]["operation"] == "TEMP_CLEANUP"
    assert response.json()["data"]["dry_run"] is True
    assert response.json()["data"]["deleted"] == []
    assert temporary.is_file()


def test_temp_cleanup_endpoint_can_apply_after_dry_run(
    maintenance_api: tuple[TestClient, sessionmaker[Session], Path],
) -> None:
    client, _factory, root = maintenance_api
    temporary = root / "temp" / "candidate.tmp"
    temporary.write_bytes(b"candidate")
    old_timestamp = time.time() - (2 * 24 * 60 * 60)
    os.utime(temporary, (old_timestamp, old_timestamp))

    response = client.post(
        "/api/v1/maintenance/temp-cleanup",
        headers=CLIENT_HEADERS,
        json={"older_than_days": 1, "dry_run": False},
    )

    assert response.status_code == 202, response.text
    assert response.json()["data"]["deleted"] == ["temp/candidate.tmp"]
    assert not temporary.exists()


def test_database_vacuum_endpoint_completes_dry_run(
    maintenance_api: tuple[TestClient, sessionmaker[Session], Path],
) -> None:
    client, _factory, _root = maintenance_api

    response = client.post(
        "/api/v1/maintenance/database-vacuum",
        headers=CLIENT_HEADERS,
        json={"dry_run": True},
    )

    assert response.status_code == 202, response.text
    assert response.json()["data"]["operation"] == "VACUUM"
    assert response.json()["data"]["dry_run"] is True


def test_maintenance_openapi_contract_includes_all_actions() -> None:
    schema = create_app().openapi()
    paths = {
        "/api/v1/maintenance/database-integrity-check",
        "/api/v1/maintenance/file-integrity-check",
        "/api/v1/maintenance/orphan-file-scan",
        "/api/v1/maintenance/temp-cleanup",
        "/api/v1/maintenance/cache-cleanup",
        "/api/v1/maintenance/database-vacuum",
    }
    assert paths <= set(schema["paths"])
    assert all(schema["paths"][path]["post"]["operationId"] for path in paths)
