from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from transloka_api.app import create_app
from transloka_api.middleware import (
    CLIENT_HEADER,
    CLIENT_HEADER_VALUE,
    CLIENT_VERSION_HEADER,
    CLIENT_VERSION_VALUE,
    REQUEST_ID_HEADER,
    validate_client_headers,
)

VALID_CLIENT_HEADERS = {
    CLIENT_HEADER: CLIENT_HEADER_VALUE,
    CLIENT_VERSION_HEADER: CLIENT_VERSION_VALUE,
}


def _test_app() -> FastAPI:
    app = create_app()

    @app.api_route(
        "/api/v1/_test/resource",
        methods=["GET", "HEAD", "POST", "PUT", "PATCH", "DELETE"],
    )
    def resource(request: Request) -> dict[str, str]:
        return {"method": request.method}

    return app


@pytest.mark.parametrize("method", ["GET", "HEAD"])
def test_read_only_methods_do_not_require_client_headers(method: str) -> None:
    response = TestClient(_test_app()).request(method, "/api/v1/_test/resource")

    assert response.status_code == 200


def test_approved_preflight_does_not_require_client_header_values() -> None:
    response = TestClient(_test_app()).options(
        "/api/v1/_test/resource",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": (f"{CLIENT_HEADER}, {CLIENT_VERSION_HEADER}"),
        },
    )

    allowed_headers = response.headers["Access-Control-Allow-Headers"].lower()
    assert response.status_code == 200
    assert CLIENT_HEADER.lower() in allowed_headers
    assert CLIENT_VERSION_HEADER.lower() in allowed_headers
    assert "*" not in allowed_headers


@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE"])
def test_mutation_without_client_headers_is_rejected(method: str) -> None:
    response = TestClient(_test_app()).request(
        method,
        "/api/v1/_test/resource",
        headers={REQUEST_ID_HEADER: f"missing-{method.lower()}"},
    )

    assert response.status_code == 403
    assert response.headers[REQUEST_ID_HEADER] == f"missing-{method.lower()}"
    assert response.json() == {
        "error": {
            "code": "CLIENT_HEADER_REQUIRED",
            "message": "TransLoka client headers are required.",
            "details": {},
            "request_id": f"missing-{method.lower()}",
        }
    }


@pytest.mark.parametrize(
    ("client_value", "version_value"),
    [
        ("", CLIENT_VERSION_VALUE),
        (" ", CLIENT_VERSION_VALUE),
        ("Web", CLIENT_VERSION_VALUE),
        ("WEB", CLIENT_VERSION_VALUE),
        ("web-app", CLIENT_VERSION_VALUE),
        ("browser", CLIENT_VERSION_VALUE),
        ("frontend", CLIENT_VERSION_VALUE),
        ("*", CLIENT_VERSION_VALUE),
        (CLIENT_HEADER_VALUE, ""),
        (CLIENT_HEADER_VALUE, "0.2.0"),
    ],
)
def test_invalid_client_header_values_are_rejected(client_value: str, version_value: str) -> None:
    response = TestClient(_test_app()).post(
        "/api/v1/_test/resource",
        headers={
            CLIENT_HEADER: client_value,
            CLIENT_VERSION_HEADER: version_value,
            REQUEST_ID_HEADER: "invalid-client",
        },
    )

    assert response.status_code == 403
    assert response.headers[REQUEST_ID_HEADER] == "invalid-client"
    assert response.json() == {
        "error": {
            "code": "CLIENT_HEADER_INVALID",
            "message": "The TransLoka client headers are invalid.",
            "details": {},
            "request_id": "invalid-client",
        }
    }


def test_duplicate_and_control_character_values_are_invalid() -> None:
    assert (
        validate_client_headers(
            [CLIENT_HEADER_VALUE, CLIENT_HEADER_VALUE],
            [CLIENT_VERSION_VALUE],
        )
        == "CLIENT_HEADER_INVALID"
    )
    assert (
        validate_client_headers(
            [f"{CLIENT_HEADER_VALUE}\n"],
            [CLIENT_VERSION_VALUE],
        )
        == "CLIENT_HEADER_INVALID"
    )


def test_exact_client_headers_allow_mutation() -> None:
    response = TestClient(_test_app()).post(
        "/api/v1/_test/resource",
        headers=VALID_CLIENT_HEADERS,
    )

    assert response.status_code == 200
    assert response.json() == {"method": "POST"}


def test_approved_origin_mutation_still_requires_client_headers() -> None:
    response = TestClient(_test_app()).post(
        "/api/v1/_test/resource",
        headers={
            "Origin": "http://localhost:3000",
            REQUEST_ID_HEADER: "approved-origin-missing-client",
        },
    )

    assert response.status_code == 403
    assert response.headers["Access-Control-Allow-Origin"] == "http://localhost:3000"
    assert response.json()["error"]["code"] == "CLIENT_HEADER_REQUIRED"


def test_approved_origin_mutation_with_client_headers_succeeds() -> None:
    response = TestClient(_test_app()).post(
        "/api/v1/_test/resource",
        headers={
            **VALID_CLIENT_HEADERS,
            "Origin": "http://localhost:3000",
        },
    )

    assert response.status_code == 200
    assert response.headers["Access-Control-Allow-Origin"] == "http://localhost:3000"


def test_mutation_without_origin_still_requires_client_headers() -> None:
    response = TestClient(_test_app()).post("/api/v1/_test/resource")

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "CLIENT_HEADER_REQUIRED"


def test_unapproved_origin_wins_even_with_valid_client_headers() -> None:
    response = TestClient(_test_app()).post(
        "/api/v1/_test/resource",
        headers={
            **VALID_CLIENT_HEADERS,
            "Origin": "http://example.com:3000",
            REQUEST_ID_HEADER: "foreign-origin",
        },
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "ORIGIN_NOT_ALLOWED"
    assert response.headers[REQUEST_ID_HEADER] == "foreign-origin"


def test_health_endpoints_are_exempt_from_client_headers() -> None:
    client = TestClient(create_app())

    root_health = client.post("/health")
    system_health = client.post("/api/v1/system/health")

    assert root_health.status_code == 405
    assert root_health.json()["error"]["code"] == "OPERATION_NOT_ALLOWED"
    assert system_health.status_code == 405
    assert system_health.json()["error"]["code"] == "OPERATION_NOT_ALLOWED"


def test_guard_does_not_consume_multipart_request_body() -> None:
    response = TestClient(_test_app()).post(
        "/api/v1/_test/resource",
        headers=VALID_CLIENT_HEADERS,
        files={"document": ("sample.pdf", b"%PDF-test", "application/pdf")},
    )

    assert response.status_code == 200


def test_sequential_requests_do_not_leak_validation_state() -> None:
    client = TestClient(_test_app())

    accepted = client.post(
        "/api/v1/_test/resource",
        headers=VALID_CLIENT_HEADERS,
    )
    rejected = client.post("/api/v1/_test/resource")
    accepted_again = client.post(
        "/api/v1/_test/resource",
        headers=VALID_CLIENT_HEADERS,
    )

    assert accepted.status_code == 200
    assert rejected.status_code == 403
    assert accepted_again.status_code == 200


def test_concurrent_requests_do_not_leak_validation_state() -> None:
    app = _test_app()
    cases = [(index, index % 2 == 0) for index in range(8)]

    def send_request(case: tuple[int, bool]) -> tuple[bool, int]:
        _, is_valid = case
        headers = VALID_CLIENT_HEADERS if is_valid else {}
        response = TestClient(app).post(
            "/api/v1/_test/resource",
            headers=headers,
        )
        return is_valid, response.status_code

    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(executor.map(send_request, cases))

    for is_valid, status_code in results:
        assert status_code == (200 if is_valid else 403)
