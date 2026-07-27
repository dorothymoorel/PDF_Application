import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from transloka_api.app import create_app
from transloka_api.config import DEFAULT_WEB_ORIGINS, Settings, parse_web_origins
from transloka_api.middleware import REQUEST_ID_HEADER


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("http://127.0.0.1:3000", ("http://127.0.0.1:3000",)),
        ("http://localhost:3000", ("http://localhost:3000",)),
        ("HTTP://LOCALHOST:3000", ("http://localhost:3000",)),
        ("http://[::1]:3000", ("http://[::1]:3000",)),
        (
            "http://localhost:3000,http://localhost:3000",
            ("http://localhost:3000",),
        ),
    ],
)
def test_web_origins_are_parsed_and_normalized(value: str, expected: tuple[str, ...]) -> None:
    assert parse_web_origins(value) == expected


@pytest.mark.parametrize(
    "value",
    [
        "*",
        "null",
        "http://0.0.0.0:3000",
        "http://192.168.1.10:3000",
        "http://10.0.0.5:3000",
        "http://example.com:3000",
        "https://example.com:3000",
        "file:///",
        "http://localhost",
        "http://localhost:0",
        "http://localhost:70000",
        "http://user:pass@localhost:3000",
        "http://localhost:3000/path",
        "http://localhost:3000?query=value",
        "http://localhost:3000#fragment",
        "",
        " ",
        "http://localhost:3000,",
        "http://*.localhost:3000",
        "http://localhost:3000\nhttp://example.com:3000",
    ],
)
def test_unsafe_web_origins_are_rejected(value: str) -> None:
    with pytest.raises(ValueError, match="only local HTTP origins"):
        parse_web_origins(value)


def test_default_origins_are_immutable_and_use_existing_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("TRANSLOKA_WEB_ORIGINS", raising=False)

    settings = Settings()

    assert settings.web_origins == DEFAULT_WEB_ORIGINS
    assert isinstance(settings.web_origins, tuple)


def test_configured_origins_are_loaded_and_deduplicated(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "TRANSLOKA_WEB_ORIGINS",
        "http://LOCALHOST:3000,http://localhost:3000,http://127.0.0.1:3000",
    )

    assert Settings().web_origins == (
        "http://localhost:3000",
        "http://127.0.0.1:3000",
    )


def test_invalid_environment_origin_fails_closed(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TRANSLOKA_WEB_ORIGINS", "http://example.com:3000")

    with pytest.raises(ValidationError) as error:
        Settings()

    assert "only local HTTP origins" in str(error.value)
    assert "example.com" not in str(error.value)


def test_approved_simple_request_receives_exact_cors_headers() -> None:
    response = TestClient(create_app()).get(
        "/health",
        headers={
            "Origin": "http://localhost:3000",
            REQUEST_ID_HEADER: "cors-approved",
        },
    )

    assert response.status_code == 200
    assert response.headers["Access-Control-Allow-Origin"] == "http://localhost:3000"
    assert response.headers["Access-Control-Expose-Headers"] == REQUEST_ID_HEADER
    assert response.headers[REQUEST_ID_HEADER] == "cors-approved"
    assert "Origin" in response.headers["Vary"]
    assert "Access-Control-Allow-Credentials" not in response.headers


def test_approved_origin_receives_cors_headers_on_normalized_internal_error() -> None:
    app = create_app()

    @app.get("/_test/internal-error")
    def internal_error() -> None:
        raise RuntimeError("private detail")

    response = TestClient(app).get(
        "/_test/internal-error",
        headers={
            "Origin": "http://localhost:3000",
            REQUEST_ID_HEADER: "cors-internal-error",
        },
    )

    assert response.status_code == 500
    assert response.headers["Access-Control-Allow-Origin"] == "http://localhost:3000"
    assert response.headers[REQUEST_ID_HEADER] == "cors-internal-error"
    assert response.json()["error"]["code"] == "INTERNAL_ERROR"
    assert "private detail" not in response.text


@pytest.mark.parametrize("origin", ["http://example.com:3000", "null"])
def test_unapproved_simple_request_is_normalized(origin: str) -> None:
    response = TestClient(create_app()).get(
        "/health",
        headers={"Origin": origin, REQUEST_ID_HEADER: "cors-rejected"},
    )

    assert response.status_code == 403
    assert response.headers[REQUEST_ID_HEADER] == "cors-rejected"
    assert "Access-Control-Allow-Origin" not in response.headers
    assert origin not in response.text
    assert response.json() == {
        "error": {
            "code": "ORIGIN_NOT_ALLOWED",
            "message": "The request origin is not allowed.",
            "details": {},
            "request_id": "cors-rejected",
        }
    }


def test_approved_preflight_uses_explicit_policy() -> None:
    response = TestClient(create_app()).options(
        "/health",
        headers={
            "Origin": "http://127.0.0.1:3000",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "Content-Type, X-Request-ID",
            REQUEST_ID_HEADER: "preflight-approved",
        },
    )

    methods = {
        method.strip() for method in response.headers["Access-Control-Allow-Methods"].split(",")
    }
    headers = {
        header.strip().lower()
        for header in response.headers["Access-Control-Allow-Headers"].split(",")
    }

    assert response.status_code == 200
    assert response.headers["Access-Control-Allow-Origin"] == "http://127.0.0.1:3000"
    assert methods == {"GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"}
    assert {"accept", "content-type", "x-request-id"} <= headers
    assert "*" not in response.headers["Access-Control-Allow-Methods"]
    assert "*" not in response.headers["Access-Control-Allow-Headers"]
    assert "x-transloka-client" in headers
    assert "x-transloka-client-version" in headers
    assert "Access-Control-Allow-Credentials" not in response.headers
    assert response.headers[REQUEST_ID_HEADER] == "preflight-approved"


def test_unapproved_preflight_is_rejected_without_cors_headers() -> None:
    response = TestClient(create_app()).options(
        "/health",
        headers={
            "Origin": "http://example.com:3000",
            "Access-Control-Request-Method": "POST",
            REQUEST_ID_HEADER: "preflight-rejected",
        },
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "ORIGIN_NOT_ALLOWED"
    assert response.headers[REQUEST_ID_HEADER] == "preflight-rejected"
    assert "Access-Control-Allow-Origin" not in response.headers
    assert "Access-Control-Allow-Methods" not in response.headers


def test_request_without_origin_is_allowed_without_cors_headers() -> None:
    response = TestClient(create_app()).get("/health", headers={REQUEST_ID_HEADER: "no-origin"})

    assert response.status_code == 200
    assert response.headers[REQUEST_ID_HEADER] == "no-origin"
    assert "Access-Control-Allow-Origin" not in response.headers


def test_origin_state_does_not_leak_between_requests() -> None:
    client = TestClient(create_app())

    approved = client.get("/health", headers={"Origin": "http://localhost:3000"})
    absent = client.get("/health")
    rejected = client.get("/health", headers={"Origin": "http://example.com:3000"})

    assert approved.status_code == 200
    assert approved.headers["Access-Control-Allow-Origin"] == "http://localhost:3000"
    assert absent.status_code == 200
    assert "Access-Control-Allow-Origin" not in absent.headers
    assert rejected.status_code == 403
