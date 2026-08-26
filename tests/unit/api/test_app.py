import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from transloka_api.app import create_app
from transloka_api.config import DEFAULT_MAX_UPLOAD_BYTES, Settings


def test_app_creation() -> None:
    settings = Settings(host="127.0.0.1", port=8000)
    app = create_app(settings)

    assert app.title == "TransLoka"
    assert app.version == "0.1.0"
    assert app.debug is False
    assert app.state.settings is settings


def test_production_app_registers_all_canonical_router_groups() -> None:
    paths = create_app().openapi()["paths"]

    assert {
        "/api/v1/glossaries",
        "/api/v1/models",
        "/api/v1/models/{model_id}/benchmarks/quick",
        "/api/v1/pages/{page_id}/ocr",
        "/api/v1/projects/{project_id}/reconstruction/start",
        "/api/v1/projects/{project_id}/review-queue",
        "/api/v1/projects/{project_id}/warnings",
        "/api/v1/segments/{segment_id}/translation",
        "/api/v1/segments/{segment_id}/revisions",
        "/api/v1/settings",
    } <= set(paths)

    operation_ids = [
        operation["operationId"]
        for path in paths.values()
        for operation in path.values()
        if isinstance(operation, dict) and "operationId" in operation
    ]
    assert len(operation_ids) == len(set(operation_ids))


def test_default_bind_is_loopback(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("APP_HOST", raising=False)
    monkeypatch.delenv("APP_PORT", raising=False)

    settings = Settings()

    assert settings.host == "127.0.0.1"
    assert settings.port == 8000


def test_upload_limit_has_safe_default_and_environment_override(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("MAX_UPLOAD_BYTES", raising=False)
    assert Settings().max_upload_bytes == DEFAULT_MAX_UPLOAD_BYTES

    monkeypatch.setenv("MAX_UPLOAD_BYTES", "1048576")
    assert Settings().max_upload_bytes == 1024 * 1024
    assert Settings(max_upload_bytes=2048).max_upload_bytes == 2048


@pytest.mark.parametrize("value", ("0", "-1", "not-a-number"))
def test_invalid_upload_limit_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
    value: str,
) -> None:
    monkeypatch.setenv("MAX_UPLOAD_BYTES", value)

    with pytest.raises(ValidationError):
        Settings()


def test_health_responses() -> None:
    client = TestClient(create_app(Settings(host="127.0.0.1", port=8000)))

    health = client.get("/health")
    system_health = client.get("/api/v1/system/health")

    assert health.status_code == 200
    assert health.json() == {
        "status": "ok",
        "service": "transloka-api",
        "version": "0.1.0",
    }
    assert system_health.status_code == 200
    assert system_health.json() == {
        "data": {
            "status": "DEGRADED",
            "components": {
                "database": {"status": "UNAVAILABLE"},
                "filesystem": {"status": "UNAVAILABLE"},
                "worker": {"status": "UNAVAILABLE"},
                "ollama": {"status": "UNAVAILABLE"},
                "ocr": {"status": "UNAVAILABLE"},
            },
        }
    }


def test_not_found_response_has_no_debug_details() -> None:
    response = TestClient(create_app()).get("/does-not-exist")
    body = response.text.lower()

    assert response.status_code == 404
    assert "traceback" not in body
    assert "stack trace" not in body
