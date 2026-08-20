from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from typing import Any, cast
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker
from transloka_api.middleware import (
    CLIENT_HEADER,
    CLIENT_HEADER_VALUE,
    CLIENT_VERSION_HEADER,
    CLIENT_VERSION_VALUE,
    REQUEST_ID_HEADER,
)
from transloka_api.routers.warnings import router as warnings_router
from transloka_core.database import transaction_scope
from transloka_core.database.models.projects import Project
from transloka_core.database.models.warnings import WarningSeverity, WarningType
from transloka_core.repositories.warnings import WarningsRepository

_PAGE_EDITOR_SPEC = spec_from_file_location(
    "transloka_page_editor_fixtures_for_warnings",
    Path(__file__).with_name("test_page_editor_view.py"),
)
assert _PAGE_EDITOR_SPEC is not None and _PAGE_EDITOR_SPEC.loader is not None
_PAGE_EDITOR_MODULE = module_from_spec(_PAGE_EDITOR_SPEC)
_PAGE_EDITOR_SPEC.loader.exec_module(_PAGE_EDITOR_MODULE)
page_editor_api = _PAGE_EDITOR_MODULE.page_editor_api

CLIENT_HEADERS = {
    CLIENT_HEADER: CLIENT_HEADER_VALUE,
    CLIENT_VERSION_HEADER: CLIENT_VERSION_VALUE,
    REQUEST_ID_HEADER: "warnings-test",
}
WARNING_ID = f"wrn_{UUID(int=100)}"
CRITICAL_WARNING_ID = f"wrn_{UUID(int=101)}"


@pytest.fixture
def warnings_client(page_editor_api: tuple[TestClient, Any]) -> tuple[TestClient, str]:
    client, _data_root = page_editor_api
    cast(Any, client.app).include_router(warnings_router)
    factory = cast(sessionmaker[Session], cast(Any, client.app).state.session_factory)
    with factory() as session:
        project_id = cast(str | None, session.scalar(select(Project.id)))
    assert project_id is not None
    with transaction_scope(factory) as session:
        repository = WarningsRepository(session)
        repository.create(
            warning_id=WARNING_ID,
            project_id=project_id,
            warning_type=WarningType.TERM_INCONSISTENT,
            severity=WarningSeverity.MEDIUM,
            message="The protected term is inconsistent.",
            details={"term": "SQLite"},
            created_at="2026-08-20T00:00:00.000Z",
        )
        repository.create(
            warning_id=CRITICAL_WARNING_ID,
            project_id=project_id,
            warning_type=WarningType.PATH_TRAVERSAL_DETECTED,
            severity=WarningSeverity.CRITICAL,
            message="Unsafe path detected.",
            details={},
            created_at="2026-08-20T00:00:01.000Z",
        )
    return client, project_id


def test_resolve_warning_preserves_history(warnings_client: tuple[TestClient, str]) -> None:
    client, project_id = warnings_client

    response = client.post(
        f"/api/v1/warnings/{WARNING_ID}/resolve",
        headers=CLIENT_HEADERS,
        json={
            "resolution_type": "USER_FIXED",
            "resolution_note": "Translation manually corrected.",
        },
    )

    assert response.status_code == 200
    assert response.json()["data"]["status"] == "RESOLVED"
    assert response.json()["data"]["resolution_type"] == "USER_FIXED"
    history = client.get(
        f"/api/v1/projects/{project_id}/warnings",
        headers=CLIENT_HEADERS,
    )
    assert history.status_code == 200
    assert [row["id"] for row in history.json()["data"]] == [CRITICAL_WARNING_ID, WARNING_ID]
    assert history.json()["data"][1]["resolution_note"] == "Translation manually corrected."


def test_accept_warning_updates_status(warnings_client: tuple[TestClient, str]) -> None:
    client, _project_id = warnings_client

    response = client.post(
        f"/api/v1/warnings/{WARNING_ID}/accept",
        headers=CLIENT_HEADERS,
        json={"resolution_note": "This wording is intentional."},
    )

    assert response.status_code == 200
    assert response.json()["data"]["status"] == "ACCEPTED"
    assert response.json()["data"]["resolution_type"] == "USER_ACCEPTED"


def test_non_overrideable_critical_warning_blocks_accept_and_false_positive(
    warnings_client: tuple[TestClient, str],
) -> None:
    client, _project_id = warnings_client

    accept = client.post(
        f"/api/v1/warnings/{CRITICAL_WARNING_ID}/accept",
        headers=CLIENT_HEADERS,
        json={"resolution_note": "Override attempt."},
    )
    false_positive = client.post(
        f"/api/v1/warnings/{CRITICAL_WARNING_ID}/false-positive",
        headers=CLIENT_HEADERS,
        json={"resolution_note": "False positive attempt."},
    )

    assert accept.status_code == 403
    assert false_positive.status_code == 403
    warning = client.get(
        f"/api/v1/warnings/{CRITICAL_WARNING_ID}",
        headers=CLIENT_HEADERS,
    )
    assert warning.status_code == 200
    assert warning.json()["data"]["status"] == "OPEN"


def test_resolved_warning_cannot_be_resolved_again(warnings_client: tuple[TestClient, str]) -> None:
    client, _project_id = warnings_client
    payload = {"resolution_type": "USER_FIXED"}

    first = client.post(
        f"/api/v1/warnings/{WARNING_ID}/resolve",
        headers=CLIENT_HEADERS,
        json=payload,
    )
    second = client.post(
        f"/api/v1/warnings/{WARNING_ID}/resolve",
        headers=CLIENT_HEADERS,
        json=payload,
    )

    assert first.status_code == 200
    assert second.status_code == 409
