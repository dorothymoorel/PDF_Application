from collections.abc import Iterator
from pathlib import Path
from typing import cast

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
    REQUEST_ID_HEADER,
)

REPOSITORY_ROOT = Path(__file__).parents[3]
ALEMBIC_CONFIGURATION = REPOSITORY_ROOT / "alembic.ini"
CLIENT_HEADERS = {
    CLIENT_HEADER: CLIENT_HEADER_VALUE,
    CLIENT_VERSION_HEADER: CLIENT_VERSION_VALUE,
}
PROJECT = {
    "name": "System Design Book",
    "description": None,
    "source_language": "en",
    "target_language": "id",
    "document_type": "TECHNICAL_BOOK",
    "translation_style": "PROFESSIONAL",
    "reconstruction_mode": "HYBRID",
}


@pytest.fixture
def project_api(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> Iterator[TestClient]:
    root = tmp_path / "project api"
    monkeypatch.setenv("TRANSLOKA_DATA_DIR", str(root))
    command.upgrade(Config(str(ALEMBIC_CONFIGURATION)), "head")
    with TestClient(create_app()) as client:
        yield client


def _create(client: TestClient, **changes: object) -> dict[str, object]:
    payload = {**PROJECT, **changes}
    response = client.post("/api/v1/projects", headers=CLIENT_HEADERS, json=payload)
    assert response.status_code == 201
    return cast(dict[str, object], response.json()["data"])


def test_valid_project_flow_and_request_envelopes(project_api: TestClient) -> None:
    request_id = "project-create"
    created_response = project_api.post(
        "/api/v1/projects",
        headers={**CLIENT_HEADERS, REQUEST_ID_HEADER: request_id},
        json=PROJECT,
    )

    assert created_response.status_code == 201
    assert created_response.headers[REQUEST_ID_HEADER] == request_id
    assert created_response.json()["meta"] == {"request_id": request_id}
    created = created_response.json()["data"]
    assert created == {
        "id": created["id"],
        "name": "System Design Book",
        "description": None,
        "status": "CREATED",
        "source_language": "en",
        "target_language": "id",
        "document_type": "TECHNICAL_BOOK",
        "translation_style": "PROFESSIONAL",
        "reconstruction_mode": "HYBRID",
        "progress": 0.0,
        "active_document_id": None,
        "settings": {},
        "created_at": created["created_at"],
        "updated_at": created["updated_at"],
    }
    project_id = created["id"]

    fetched = project_api.get(f"/api/v1/projects/{project_id}")
    updated = project_api.patch(
        f"/api/v1/projects/{project_id}",
        headers=CLIENT_HEADERS,
        json={
            "name": "Updated Name",
            "translation_style": "ACADEMIC",
            "reconstruction_mode": "REFLOW",
        },
    )
    archived = project_api.post(
        f"/api/v1/projects/{project_id}/archive",
        headers=CLIENT_HEADERS,
    )
    archived_list = project_api.get(
        "/api/v1/projects",
        params={"status": "ARCHIVED", "search": "updated", "sort": "name", "order": "asc"},
    )
    restored = project_api.post(
        f"/api/v1/projects/{project_id}/unarchive",
        headers=CLIENT_HEADERS,
    )

    assert fetched.json()["data"]["id"] == project_id
    assert updated.json()["data"]["name"] == "Updated Name"
    assert updated.json()["data"]["translation_style"] == "ACADEMIC"
    assert archived.json()["data"]["status"] == "ARCHIVED"
    assert archived_list.json()["data"] == [archived.json()["data"]]
    assert archived_list.json()["meta"]["pagination"] == {
        "limit": 20,
        "offset": 0,
        "total": 1,
        "has_more": False,
    }
    assert restored.json()["data"]["status"] == "CREATED"
    assert str(REPOSITORY_ROOT) not in created_response.text


def test_list_projects_supports_sorting_and_offset_pagination(
    project_api: TestClient,
) -> None:
    _create(project_api, name="Beta")
    _create(project_api, name="Alpha")

    response = project_api.get(
        "/api/v1/projects",
        params={"sort": "name", "order": "asc", "limit": 1, "offset": 1},
    )

    assert response.status_code == 200
    assert [item["name"] for item in response.json()["data"]] == ["Beta"]
    assert response.json()["meta"]["pagination"] == {
        "limit": 1,
        "offset": 1,
        "total": 2,
        "has_more": False,
    }


def test_missing_and_archived_projects_return_normalized_errors(
    project_api: TestClient,
) -> None:
    missing = project_api.get("/api/v1/projects/prj_00000000-0000-0000-0000-000000000000")
    project = _create(project_api)
    project_id = project["id"]
    project_api.post(f"/api/v1/projects/{project_id}/archive", headers=CLIENT_HEADERS)

    archived = project_api.patch(
        f"/api/v1/projects/{project_id}",
        headers=CLIENT_HEADERS,
        json={"name": "Rejected"},
    )
    project_api.post(f"/api/v1/projects/{project_id}/unarchive", headers=CLIENT_HEADERS)
    invalid_state = project_api.post(
        f"/api/v1/projects/{project_id}/unarchive",
        headers=CLIENT_HEADERS,
    )

    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "PROJECT_NOT_FOUND"
    assert archived.status_code == 409
    assert archived.json()["error"]["code"] == "PROJECT_ARCHIVED"
    assert invalid_state.status_code == 409
    assert invalid_state.json()["error"]["code"] == "PROJECT_STATE_INVALID"


@pytest.mark.parametrize(
    ("method", "path", "payload"),
    [
        ("post", "/api/v1/projects", {**PROJECT, "document_type": "INVALID"}),
        ("post", "/api/v1/projects", {**PROJECT, "path": "C:\\private\\document.pdf"}),
        ("patch", "/api/v1/projects/prj_00000000-0000-0000-0000-000000000000", {}),
        (
            "patch",
            "/api/v1/projects/prj_00000000-0000-0000-0000-000000000000",
            {"name": None},
        ),
    ],
)
def test_project_validation_is_closed_and_normalized(
    method: str,
    path: str,
    payload: dict[str, object],
    project_api: TestClient,
) -> None:
    response = project_api.request(method, path, headers=CLIENT_HEADERS, json=payload)

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"
    assert "C:\\private\\document.pdf" not in response.text


def test_mutations_require_client_headers(project_api: TestClient) -> None:
    response = project_api.post("/api/v1/projects", json=PROJECT)

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "CLIENT_HEADER_REQUIRED"


def test_project_openapi_contract_is_registered() -> None:
    schema = create_app().openapi()
    operations = {
        ("/api/v1/projects", "post"): "create_project",
        ("/api/v1/projects", "get"): "list_projects",
        ("/api/v1/projects/{project_id}", "get"): "get_project",
        ("/api/v1/projects/{project_id}", "patch"): "update_project",
        ("/api/v1/projects/{project_id}/archive", "post"): "archive_project",
        ("/api/v1/projects/{project_id}/unarchive", "post"): "unarchive_project",
    }

    for (path, method), operation_id in operations.items():
        operation = schema["paths"][path][method]
        assert operation["operationId"] == operation_id
        for status_code in ("403", "404", "409", "422", "500"):
            response_schema = operation["responses"][status_code]["content"]["application/json"][
                "schema"
            ]
            assert response_schema["$ref"] == "#/components/schemas/ErrorResponse"
