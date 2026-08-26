from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine
from sqlalchemy.orm import Session, sessionmaker
from transloka_api.app import create_app
from transloka_api.middleware import (
    CLIENT_HEADER,
    CLIENT_HEADER_VALUE,
    CLIENT_VERSION_HEADER,
    CLIENT_VERSION_VALUE,
    REQUEST_ID_HEADER,
)
from transloka_core.database import (
    create_session_factory,
    create_sqlite_engine,
    transaction_scope,
)
from transloka_core.repositories.settings import SettingsRepository
from transloka_core.storage import resolve_local_data_directories

REPOSITORY_ROOT = Path(__file__).parents[3]
ALEMBIC_CONFIGURATION = REPOSITORY_ROOT / "alembic.ini"
CLIENT_HEADERS = {
    CLIENT_HEADER: CLIENT_HEADER_VALUE,
    CLIENT_VERSION_HEADER: CLIENT_VERSION_VALUE,
}


@pytest.fixture
def settings_api(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> Iterator[tuple[TestClient, Engine, sessionmaker[Session]]]:
    root = tmp_path / "api settings"
    monkeypatch.setenv("TRANSLOKA_DATA_DIR", str(root))
    command.upgrade(Config(str(ALEMBIC_CONFIGURATION)), "head")
    engine = create_sqlite_engine(resolve_local_data_directories(root))
    factory = create_session_factory(engine)
    app = create_app()
    app.state.session_factory = factory
    yield TestClient(app), engine, factory
    engine.dispose()


def _seed(factory: sessionmaker[Session]) -> None:
    with transaction_scope(factory) as session:
        repository = SettingsRepository(session)
        repository.create("translation_batch_size", 5)
        repository.create("ocr_concurrency", 1)


def test_router_is_registered_by_production_app() -> None:
    assert "/api/v1/settings" in create_app().openapi()["paths"]


def test_list_get_and_category_filter(
    settings_api: tuple[TestClient, Engine, sessionmaker[Session]],
) -> None:
    client, _engine, factory = settings_api
    _seed(factory)

    listed = client.get("/api/v1/settings")
    filtered = client.get("/api/v1/settings", params={"category": "OCR"})
    fetched = client.get("/api/v1/settings/translation_batch_size")

    assert listed.status_code == 200
    assert [item["key"] for item in listed.json()["data"]] == [
        "ocr_concurrency",
        "translation_batch_size",
    ]
    assert filtered.json()["data"][0]["key"] == "ocr_concurrency"
    assert fetched.json()["data"]["value"] == 5
    assert fetched.json()["data"]["category"] == "TRANSLATION"


def test_patch_requires_client_headers_and_preserves_request_id(
    settings_api: tuple[TestClient, Engine, sessionmaker[Session]],
) -> None:
    client, _engine, factory = settings_api
    _seed(factory)

    rejected = client.patch(
        "/api/v1/settings/translation_batch_size",
        headers={REQUEST_ID_HEADER: "settings-missing-client"},
        json={"value": 10},
    )
    accepted = client.patch(
        "/api/v1/settings/translation_batch_size",
        headers={**CLIENT_HEADERS, REQUEST_ID_HEADER: "settings-update"},
        json={"value": 10},
    )

    assert rejected.status_code == 403
    assert rejected.json()["error"]["code"] == "CLIENT_HEADER_REQUIRED"
    assert accepted.status_code == 200
    assert accepted.headers[REQUEST_ID_HEADER] == "settings-update"
    assert accepted.json()["data"]["value"] == 10
    with factory() as session:
        assert SettingsRepository(session).get("translation_batch_size").value == 10


@pytest.mark.parametrize("key", ["unknown", "password", "api_key", "access_token"])
def test_unknown_and_secret_keys_return_safe_normalized_error(
    key: str,
    settings_api: tuple[TestClient, Engine, sessionmaker[Session]],
) -> None:
    client, _engine, _factory = settings_api
    private_value = "private-value"

    response = client.patch(
        f"/api/v1/settings/{key}",
        headers=CLIENT_HEADERS,
        json={"value": private_value},
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "SETTING_KEY_NOT_ALLOWED"
    assert private_value not in response.text
    assert key not in response.text


def test_invalid_value_and_arbitrary_category_are_rejected(
    settings_api: tuple[TestClient, Engine, sessionmaker[Session]],
) -> None:
    client, _engine, factory = settings_api
    _seed(factory)

    invalid = client.patch(
        "/api/v1/settings/ocr_concurrency",
        headers=CLIENT_HEADERS,
        json={"value": 9},
    )
    category_override = client.patch(
        "/api/v1/settings/ocr_concurrency",
        headers=CLIENT_HEADERS,
        json={"value": 2, "category": "SECRETS"},
    )
    unknown_category = client.get("/api/v1/settings", params={"category": "SECRETS"})

    assert invalid.status_code == 422
    assert invalid.json()["error"]["code"] == "SETTING_VALUE_INVALID"
    assert category_override.status_code == 422
    assert category_override.json()["error"]["code"] == "VALIDATION_ERROR"
    assert unknown_category.status_code == 422
    assert unknown_category.json()["error"]["code"] == "VALIDATION_ERROR"


def test_validate_endpoint_accepts_only_closed_valid_settings(
    settings_api: tuple[TestClient, Engine, sessionmaker[Session]],
) -> None:
    client, _engine, _factory = settings_api

    valid = client.post(
        "/api/v1/settings/validate",
        headers=CLIENT_HEADERS,
        json={"settings": {"translation_batch_size": 5, "ocr_concurrency": 1}},
    )
    invalid = client.post(
        "/api/v1/settings/validate",
        headers=CLIENT_HEADERS,
        json={"settings": {"custom.setting": 1}},
    )

    assert valid.status_code == 200
    assert valid.json() == {"data": {"valid": True}}
    assert invalid.status_code == 400
    assert invalid.json()["error"]["code"] == "SETTING_KEY_NOT_ALLOWED"


def test_known_but_uninitialized_setting_returns_not_found(
    settings_api: tuple[TestClient, Engine, sessionmaker[Session]],
) -> None:
    client, _engine, _factory = settings_api

    response = client.get(
        "/api/v1/settings/ocr_concurrency",
        headers={REQUEST_ID_HEADER: "settings-not-found"},
    )

    assert response.status_code == 404
    assert response.headers[REQUEST_ID_HEADER] == "settings-not-found"
    assert response.json()["error"]["code"] == "RESOURCE_NOT_FOUND"


def test_router_openapi_contract_is_stable_and_normalized() -> None:
    app: FastAPI = create_app()
    schema = app.openapi()

    expected_operations = {
        ("/api/v1/settings", "get"): "list_settings",
        ("/api/v1/settings/{key}", "get"): "get_setting",
        ("/api/v1/settings/{key}", "patch"): "update_setting",
        ("/api/v1/settings/validate", "post"): "validate_settings",
    }
    for (path, method), operation_id in expected_operations.items():
        operation = schema["paths"][path][method]
        assert operation["operationId"] == operation_id
        for status_code in ("400", "404", "422", "500"):
            response_schema = operation["responses"][status_code]["content"]["application/json"][
                "schema"
            ]
            assert response_schema["$ref"] == "#/components/schemas/ErrorResponse"
