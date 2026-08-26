from importlib.util import module_from_spec, spec_from_file_location
from pathlib import Path
from typing import Any, cast

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker
from transloka_api.middleware import REQUEST_ID_HEADER
from transloka_core.database.models.projects import Project

_PAGE_EDITOR_SPEC = spec_from_file_location(
    "transloka_page_editor_fixtures",
    Path(__file__).with_name("test_page_editor_view.py"),
)
assert _PAGE_EDITOR_SPEC is not None and _PAGE_EDITOR_SPEC.loader is not None
_PAGE_EDITOR_MODULE = module_from_spec(_PAGE_EDITOR_SPEC)
_PAGE_EDITOR_SPEC.loader.exec_module(_PAGE_EDITOR_MODULE)
PAGE_ID = _PAGE_EDITOR_MODULE.PAGE_ID
page_editor_api = _PAGE_EDITOR_MODULE.page_editor_api

CLIENT_HEADERS = {REQUEST_ID_HEADER: "review-queue-test"}


@pytest.fixture
def review_queue_client(
    page_editor_api: tuple[TestClient, Any],
) -> tuple[TestClient, str]:
    client, _data_root = page_editor_api
    factory = cast(sessionmaker[Session], cast(Any, client.app).state.session_factory)
    with factory() as session:
        project_id = cast(str | None, session.scalar(select(Project.id)))
    assert project_id is not None
    return client, project_id


def test_review_queue_orders_segments_and_returns_context(
    review_queue_client: tuple[TestClient, str],
) -> None:
    client, project_id = review_queue_client

    response = client.get(
        f"/api/v1/projects/{project_id}/review-queue",
        headers=CLIENT_HEADERS,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["meta"]["request_id"] == "review-queue-test"
    assert [item["segment"]["source_text"] for item in body["data"]] == [
        "Early segment.",
        "First late segment.",
        "Second late segment.",
    ]
    assert body["data"][0]["source_context"] == {
        "previous_segment": None,
        "next_segment": "First late segment.",
        "heading": None,
    }


def test_review_queue_filters_by_confidence_status_page_and_section(
    review_queue_client: tuple[TestClient, str],
) -> None:
    client, project_id = review_queue_client

    response = client.get(
        f"/api/v1/projects/{project_id}/review-queue",
        params={
            "confidence_max": "0.95",
            "status": "NOT_REVIEWED",
            "page_id": PAGE_ID,
            "section_id": "sec_missing",
        },
        headers=CLIENT_HEADERS,
    )

    assert response.status_code == 200
    assert response.json()["data"] == []


def test_review_queue_returns_empty_for_warning_filter_without_persisted_warnings(
    review_queue_client: tuple[TestClient, str],
) -> None:
    client, project_id = review_queue_client

    response = client.get(
        f"/api/v1/projects/{project_id}/review-queue",
        params={"warning": "true"},
        headers=CLIENT_HEADERS,
    )

    assert response.status_code == 200
    assert response.json()["data"] == []
