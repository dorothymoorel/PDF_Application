import pytest
from fastapi.testclient import TestClient
from transloka_api.app import create_app
from transloka_api.config import Settings


def test_app_creation() -> None:
    settings = Settings(host="127.0.0.1", port=8000)
    app = create_app(settings)

    assert app.title == "TransLoka"
    assert app.version == "0.1.0"
    assert app.debug is False
    assert app.state.settings is settings


def test_default_bind_is_loopback(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("APP_HOST", raising=False)
    monkeypatch.delenv("APP_PORT", raising=False)

    settings = Settings()

    assert settings.host == "127.0.0.1"
    assert settings.port == 8000


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
