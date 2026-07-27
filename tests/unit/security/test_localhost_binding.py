import importlib
import sys

import pytest
import uvicorn
from pydantic import ValidationError
from transloka_api.config import Settings, validate_api_host


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("127.0.0.1", "127.0.0.1"),
        ("localhost", "localhost"),
        ("LOCALHOST", "localhost"),
        ("::1", "::1"),
        ("127.0.0.2", "127.0.0.2"),
        (" 127.0.0.1 ", "127.0.0.1"),
    ],
)
def test_loopback_hosts_are_accepted(value: str, expected: str) -> None:
    assert validate_api_host(value) == expected
    assert Settings(host=value).host == expected


@pytest.mark.parametrize(
    "value",
    [
        "0.0.0.0",
        "::",
        "*",
        "192.168.1.10",
        "10.0.0.5",
        "172.16.0.5",
        "8.8.8.8",
        "example.com",
        "host.docker.internal",
        "",
        " ",
        "http://127.0.0.1",
        "127.0.0.1:8000",
        "not-an-ip",
        "127.0.0.1\ninjected",
        "127.0.0.1\t",
        "::1%1",
    ],
)
def test_unsafe_hosts_are_rejected(value: str) -> None:
    with pytest.raises(ValueError, match="STARTUP_BLOCKED_NON_LOCAL_BIND"):
        validate_api_host(value)

    with pytest.raises(ValidationError, match="STARTUP_BLOCKED_NON_LOCAL_BIND"):
        Settings(host=value)


def test_default_host_uses_transloka_environment_prefix(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("TRANSLOKA_API_HOST", raising=False)
    monkeypatch.delenv("TRANSLOKA_API_PORT", raising=False)

    settings = Settings()

    assert settings.host == "127.0.0.1"
    assert settings.port == 8000


def test_environment_host_is_validated(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("TRANSLOKA_API_HOST", "0.0.0.0")

    with pytest.raises(ValidationError) as error:
        Settings()

    assert "STARTUP_BLOCKED_NON_LOCAL_BIND" in str(error.value)
    assert "0.0.0.0" not in str(error.value)


def test_supported_launcher_uses_validated_host(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from transloka_api import main

    settings = Settings(host="LOCALHOST", port=8123)
    calls: list[tuple[object, str, int]] = []

    def capture_run(app: object, *, host: str, port: int) -> None:
        calls.append((app, host, port))

    monkeypatch.setattr(main, "settings", settings)
    monkeypatch.setattr(uvicorn, "run", capture_run)

    main.run()

    assert calls == [(main.app, "localhost", 8123)]


def test_importing_application_does_not_start_server(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_run(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("Importing the application started Uvicorn.")

    monkeypatch.delenv("TRANSLOKA_API_HOST", raising=False)
    monkeypatch.setattr(uvicorn, "run", fail_run)
    monkeypatch.delitem(sys.modules, "transloka_api.main", raising=False)

    imported = importlib.import_module("transloka_api.main")

    assert imported.app.title == "TransLoka"
