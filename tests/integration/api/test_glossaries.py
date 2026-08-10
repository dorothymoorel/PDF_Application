from collections.abc import Iterator
from pathlib import Path
from typing import cast

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
    REQUEST_ID_HEADER,
)
from transloka_api.routers.glossaries import router
from transloka_glossary import GlossaryRepository

REPOSITORY_ROOT = Path(__file__).parents[3]
ALEMBIC_CONFIGURATION = REPOSITORY_ROOT / "alembic.ini"
CLIENT_HEADERS = {
    CLIENT_HEADER: CLIENT_HEADER_VALUE,
    CLIENT_VERSION_HEADER: CLIENT_VERSION_VALUE,
}
PROJECT = {
    "name": "Glossary Project",
    "description": None,
    "source_language": "en",
    "target_language": "id",
    "document_type": "TECHNICAL_BOOK",
    "translation_style": "PROFESSIONAL",
    "reconstruction_mode": "HYBRID",
}


@pytest.fixture
def glossary_api(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> Iterator[tuple[TestClient, sessionmaker[Session]]]:
    root = tmp_path / "glossary api"
    monkeypatch.setenv("TRANSLOKA_DATA_DIR", str(root))
    command.upgrade(Config(str(ALEMBIC_CONFIGURATION)), "head")
    application = create_app()
    application.include_router(router)
    with TestClient(application) as client:
        factory = cast(sessionmaker[Session], application.state.session_factory)
        yield client, factory


def _create_project(client: TestClient) -> str:
    response = client.post(
        "/api/v1/projects",
        headers=CLIENT_HEADERS,
        json=PROJECT,
    )
    assert response.status_code == 201
    return cast(str, response.json()["data"]["id"])


def _create_glossary(
    client: TestClient, project_id: str, *, name: str = "Project Terms"
) -> dict[str, object]:
    response = client.post(
        "/api/v1/glossaries",
        headers=CLIENT_HEADERS,
        json={
            "project_id": project_id,
            "name": name,
            "description": None,
            "source_language": "en",
            "target_language": "id",
            "scope": "PROJECT",
            "domain": "SOFTWARE_ENGINEERING",
            "is_default": True,
        },
    )
    assert response.status_code == 201, response.text
    return cast(dict[str, object], response.json()["data"])


def _term_payload(project_id: str, **changes: object) -> dict[str, object]:
    values: dict[str, object] = {
        "source_term": "workflow",
        "rule_type": "KEEP_ORIGINAL",
        "target_term": None,
        "scope": "PROJECT",
        "scope_reference_id": project_id,
        "priority": 100,
        "case_sensitive": False,
        "whole_word": True,
        "match_mode": "PHRASE",
        "capitalization_policy": "MATCH_SENTENCE_POSITION",
        "inflection_policy": "USE_BASE_TERM",
        "first_use_policy": "NONE",
    }
    values.update(changes)
    return values


def _create_term(
    client: TestClient,
    glossary_id: str,
    project_id: str,
    **changes: object,
) -> dict[str, object]:
    response = client.post(
        f"/api/v1/glossaries/{glossary_id}/terms",
        headers=CLIENT_HEADERS,
        json=_term_payload(project_id, **changes),
    )
    assert response.status_code == 201, response.text
    return cast(dict[str, object], response.json()["data"])


def test_glossary_crud_filtering_activation_and_soft_delete(
    glossary_api: tuple[TestClient, sessionmaker[Session]],
) -> None:
    client, _factory = glossary_api
    project_id = _create_project(client)
    created = _create_glossary(client, project_id)
    glossary_id = cast(str, created["id"])

    fetched = client.get(f"/api/v1/glossaries/{glossary_id}")
    listed = client.get(
        "/api/v1/glossaries",
        params={"project_id": project_id, "scope": "PROJECT", "search": "terms"},
    )
    updated = client.patch(
        f"/api/v1/glossaries/{glossary_id}",
        headers={**CLIENT_HEADERS, REQUEST_ID_HEADER: "glossary-update"},
        json={
            "name": "Updated Terms",
            "description": "Technical terminology.",
            "expected_version": 1,
        },
    )
    deactivated = client.post(
        f"/api/v1/glossaries/{glossary_id}/deactivate",
        headers=CLIENT_HEADERS,
    )
    activated = client.post(
        f"/api/v1/glossaries/{glossary_id}/activate",
        headers=CLIENT_HEADERS,
    )
    deleted = client.delete(
        f"/api/v1/glossaries/{glossary_id}",
        headers=CLIENT_HEADERS,
    )

    assert created["status"] == "ACTIVE"
    assert created["version"] == 1
    assert created["term_count"] == 0
    assert fetched.json()["data"]["id"] == glossary_id
    assert listed.json()["data"] == [created]
    assert listed.json()["meta"]["pagination"]["total"] == 1
    assert updated.status_code == 200
    assert updated.headers[REQUEST_ID_HEADER] == "glossary-update"
    assert updated.json()["data"]["version"] == 2
    assert updated.json()["data"]["name"] == "Updated Terms"
    assert deactivated.json()["data"]["status"] == "INACTIVE"
    assert deactivated.json()["data"]["version"] == 3
    assert activated.json()["data"]["status"] == "ACTIVE"
    assert activated.json()["data"]["version"] == 4
    assert deleted.status_code == 204
    assert client.get(f"/api/v1/glossaries/{glossary_id}").status_code == 404


def test_term_crud_creates_append_only_revisions_and_archives(
    glossary_api: tuple[TestClient, sessionmaker[Session]],
) -> None:
    client, factory = glossary_api
    project_id = _create_project(client)
    glossary = _create_glossary(client, project_id)
    glossary_id = cast(str, glossary["id"])
    created = _create_term(client, glossary_id, project_id)
    term_id = cast(str, created["id"])

    listed = client.get(f"/api/v1/glossaries/{glossary_id}/terms")
    fetched = client.get(f"/api/v1/glossary-terms/{term_id}")
    updated = client.patch(
        f"/api/v1/glossary-terms/{term_id}",
        headers=CLIENT_HEADERS,
        json={
            "rule_type": "TRANSLATE_AS",
            "target_term": "alur kerja",
            "expected_revision": 1,
            "reason": "Approved translation.",
        },
    )
    deactivated = client.post(
        f"/api/v1/glossary-terms/{term_id}/deactivate",
        headers=CLIENT_HEADERS,
    )
    archived = client.delete(
        f"/api/v1/glossary-terms/{term_id}",
        headers=CLIENT_HEADERS,
    )
    default_list = client.get(f"/api/v1/glossaries/{glossary_id}/terms")
    archived_list = client.get(
        f"/api/v1/glossaries/{glossary_id}/terms",
        params={"status": "ARCHIVED"},
    )

    assert created["current_revision"] == 1
    assert created["normalized_source_term"] == "workflow"
    assert listed.json()["data"] == [created]
    assert fetched.json()["data"] == created
    assert updated.json()["data"]["current_revision"] == 2
    assert updated.json()["data"]["target_term"] == "alur kerja"
    assert deactivated.json()["data"]["status"] == "INACTIVE"
    assert deactivated.json()["data"]["current_revision"] == 3
    assert archived.json()["data"]["status"] == "ARCHIVED"
    assert archived.json()["data"]["current_revision"] == 4
    assert default_list.json()["data"] == []
    assert archived_list.json()["data"] == [archived.json()["data"]]

    with factory() as session:
        repository = GlossaryRepository(session)
        revisions = repository.list_revisions(term_id)
        persisted_glossary = repository.get_glossary(glossary_id)
    assert [revision.revision_number for revision in revisions] == [1, 2, 3, 4]
    assert [revision.revision_type.value for revision in revisions] == [
        "CREATE_TERM",
        "EDIT_TERM",
        "DEACTIVATE",
        "DEACTIVATE",
    ]
    assert revisions[1].previous_value is not None
    assert revisions[1].previous_value["target_term"] is None
    assert revisions[1].new_value["target_term"] == "alur kerja"
    assert persisted_glossary.version == 5


def test_duplicate_term_is_rejected_but_archived_identity_can_be_reused(
    glossary_api: tuple[TestClient, sessionmaker[Session]],
) -> None:
    client, _factory = glossary_api
    project_id = _create_project(client)
    glossary_id = cast(str, _create_glossary(client, project_id)["id"])
    first = _create_term(client, glossary_id, project_id, source_term="Workflow")

    duplicate = client.post(
        f"/api/v1/glossaries/{glossary_id}/terms",
        headers=CLIENT_HEADERS,
        json=_term_payload(project_id, source_term="workflow"),
    )
    client.delete(
        f"/api/v1/glossary-terms/{first['id']}",
        headers=CLIENT_HEADERS,
    )
    replacement = client.post(
        f"/api/v1/glossaries/{glossary_id}/terms",
        headers=CLIENT_HEADERS,
        json=_term_payload(project_id, source_term="workflow"),
    )

    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "DUPLICATE_TERM"
    assert replacement.status_code == 201
    assert replacement.json()["data"]["id"] != first["id"]


def test_glossary_and_term_revision_conflicts_return_current_revision(
    glossary_api: tuple[TestClient, sessionmaker[Session]],
) -> None:
    client, _factory = glossary_api
    project_id = _create_project(client)
    glossary = _create_glossary(client, project_id)
    glossary_id = cast(str, glossary["id"])
    term = _create_term(client, glossary_id, project_id)
    term_id = cast(str, term["id"])

    first_glossary_update = client.patch(
        f"/api/v1/glossaries/{glossary_id}",
        headers=CLIENT_HEADERS,
        json={"name": "First Update", "expected_version": 2},
    )
    stale_glossary_update = client.patch(
        f"/api/v1/glossaries/{glossary_id}",
        headers=CLIENT_HEADERS,
        json={"name": "Stale Update", "expected_version": 2},
    )
    first_term_update = client.patch(
        f"/api/v1/glossary-terms/{term_id}",
        headers=CLIENT_HEADERS,
        json={"priority": 200, "expected_revision": 1},
    )
    stale_term_update = client.patch(
        f"/api/v1/glossary-terms/{term_id}",
        headers=CLIENT_HEADERS,
        json={"priority": 300, "expected_revision": 1},
    )

    assert first_glossary_update.status_code == 200
    assert stale_glossary_update.status_code == 409
    assert stale_glossary_update.json()["error"]["code"] == "REVISION_CONFLICT"
    assert stale_glossary_update.json()["error"]["details"] == {
        "expected_revision": 2,
        "current_revision": 3,
    }
    assert first_term_update.status_code == 200
    assert stale_term_update.status_code == 409
    assert stale_term_update.json()["error"]["details"] == {
        "expected_revision": 1,
        "current_revision": 2,
    }
    assert client.get(f"/api/v1/glossary-terms/{term_id}").json()["data"]["priority"] == 200


def test_failed_duplicate_update_rolls_back_term_and_revision(
    glossary_api: tuple[TestClient, sessionmaker[Session]],
) -> None:
    client, factory = glossary_api
    project_id = _create_project(client)
    glossary_id = cast(str, _create_glossary(client, project_id)["id"])
    _create_term(client, glossary_id, project_id, source_term="workflow")
    second = _create_term(client, glossary_id, project_id, source_term="process")
    second_id = cast(str, second["id"])

    response = client.patch(
        f"/api/v1/glossary-terms/{second_id}",
        headers=CLIENT_HEADERS,
        json={"source_term": "WORKFLOW", "expected_revision": 1},
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "DUPLICATE_TERM"
    persisted = client.get(f"/api/v1/glossary-terms/{second_id}").json()["data"]
    assert persisted["source_term"] == "process"
    assert persisted["current_revision"] == 1
    with factory() as session:
        assert len(GlossaryRepository(session).list_revisions(second_id)) == 1


def test_deactivated_glossary_and_archived_term_reject_mutation(
    glossary_api: tuple[TestClient, sessionmaker[Session]],
) -> None:
    client, _factory = glossary_api
    project_id = _create_project(client)
    glossary_id = cast(str, _create_glossary(client, project_id)["id"])
    term = _create_term(client, glossary_id, project_id)
    term_id = cast(str, term["id"])
    client.delete(f"/api/v1/glossary-terms/{term_id}", headers=CLIENT_HEADERS)
    client.post(
        f"/api/v1/glossaries/{glossary_id}/deactivate",
        headers=CLIENT_HEADERS,
    )

    archived_update = client.patch(
        f"/api/v1/glossary-terms/{term_id}",
        headers=CLIENT_HEADERS,
        json={"notes": "Rejected", "expected_revision": 2},
    )
    inactive_create = client.post(
        f"/api/v1/glossaries/{glossary_id}/terms",
        headers=CLIENT_HEADERS,
        json=_term_payload(project_id, source_term="new term"),
    )

    assert archived_update.status_code == 409
    assert archived_update.json()["error"]["code"] == "GLOSSARY_STATE_INVALID"
    assert inactive_create.status_code == 409
    assert inactive_create.json()["error"]["code"] == "GLOSSARY_STATE_INVALID"


def test_target_required_validation_and_mutation_security(
    glossary_api: tuple[TestClient, sessionmaker[Session]],
) -> None:
    client, _factory = glossary_api
    project_id = _create_project(client)
    glossary_id = cast(str, _create_glossary(client, project_id)["id"])

    target_missing = client.post(
        f"/api/v1/glossaries/{glossary_id}/terms",
        headers=CLIENT_HEADERS,
        json=_term_payload(project_id, rule_type="TRANSLATE_AS", target_term=None),
    )
    missing_headers = client.post(
        f"/api/v1/glossaries/{glossary_id}/terms",
        json=_term_payload(project_id),
    )

    assert target_missing.status_code == 422
    assert target_missing.json()["error"]["code"] == "TARGET_REQUIRED"
    assert missing_headers.status_code == 403
    assert missing_headers.json()["error"]["code"] == "CLIENT_HEADER_REQUIRED"


def test_glossary_router_openapi_is_stable_and_task_scoped() -> None:
    assert "/api/v1/glossaries" not in create_app().openapi()["paths"]
    application = create_app()
    application.include_router(router)
    schema = application.openapi()
    operations = {
        ("/api/v1/glossaries", "post"): "create_glossary",
        ("/api/v1/glossaries", "get"): "list_glossaries",
        ("/api/v1/glossaries/{glossary_id}", "get"): "get_glossary",
        ("/api/v1/glossaries/{glossary_id}", "patch"): "update_glossary",
        ("/api/v1/glossaries/{glossary_id}/deactivate", "post"): "deactivate_glossary",
        ("/api/v1/glossaries/{glossary_id}/activate", "post"): "activate_glossary",
        ("/api/v1/glossaries/{glossary_id}/terms", "post"): "create_glossary_term",
        ("/api/v1/glossaries/{glossary_id}/terms", "get"): "list_glossary_terms",
        ("/api/v1/glossary-terms/{term_id}", "get"): "get_glossary_term",
        ("/api/v1/glossary-terms/{term_id}", "patch"): "update_glossary_term",
        ("/api/v1/glossary-terms/{term_id}/deactivate", "post"): ("deactivate_glossary_term"),
        ("/api/v1/glossary-terms/{term_id}", "delete"): "archive_glossary_term",
    }
    for (path, method), operation_id in operations.items():
        operation = schema["paths"][path][method]
        assert operation["operationId"] == operation_id
        for status_code in ("403", "404", "409", "422", "500"):
            response_schema = operation["responses"][status_code]["content"]["application/json"][
                "schema"
            ]
            assert response_schema["$ref"] == "#/components/schemas/ErrorResponse"
