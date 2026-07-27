import asyncio
import re
from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from pydantic import BaseModel, Field
from transloka_api.app import create_app
from transloka_api.exception_handlers import NotFoundError
from transloka_api.middleware import REQUEST_ID_HEADER, get_request_id
from transloka_api.schemas import ErrorResponse

GENERATED_REQUEST_ID = re.compile(r"req_[0-9a-f]{32}")


class ValidationPayload(BaseModel):
    quantity: int = Field(gt=0)


def _test_app() -> FastAPI:
    app = create_app()

    @app.get("/_test/context")
    async def request_context(request: Request) -> dict[str, str]:
        await asyncio.sleep(0.01)
        context_request_id = get_request_id()
        assert context_request_id is not None
        return {
            "context": context_request_id,
            "state": request.state.request_id,
        }

    @app.get("/_test/not-found")
    def controlled_not_found() -> None:
        raise NotFoundError

    @app.post("/_test/validation")
    def validate_payload(payload: ValidationPayload) -> ValidationPayload:
        return payload

    @app.get("/_test/internal-error")
    def internal_error() -> None:
        raise RuntimeError("private-input C:\\Users\\person\\document.txt")

    return app


def test_generated_request_id_is_added_to_success_response() -> None:
    response = TestClient(_test_app()).get("/health")

    assert response.status_code == 200
    assert GENERATED_REQUEST_ID.fullmatch(response.headers[REQUEST_ID_HEADER])


def test_valid_client_request_id_is_preserved() -> None:
    response = TestClient(_test_app()).get(
        "/health", headers={REQUEST_ID_HEADER: "client.request-123"}
    )

    assert response.headers[REQUEST_ID_HEADER] == "client.request-123"


def test_invalid_client_request_id_is_replaced() -> None:
    response = TestClient(_test_app()).get("/health", headers={REQUEST_ID_HEADER: "<invalid>"})

    request_id = response.headers[REQUEST_ID_HEADER]
    assert request_id != "<invalid>"
    assert GENERATED_REQUEST_ID.fullmatch(request_id)


def test_overlong_client_request_id_is_replaced() -> None:
    response = TestClient(_test_app()).get("/health", headers={REQUEST_ID_HEADER: "a" * 129})

    assert GENERATED_REQUEST_ID.fullmatch(response.headers[REQUEST_ID_HEADER])


def test_generated_request_ids_do_not_leak_between_sequential_requests() -> None:
    client = TestClient(_test_app())

    first = client.get("/health").headers[REQUEST_ID_HEADER]
    second = client.get("/health").headers[REQUEST_ID_HEADER]

    assert first != second


def test_request_id_is_available_in_context_and_request_state() -> None:
    response = TestClient(_test_app()).get(
        "/_test/context", headers={REQUEST_ID_HEADER: "context-id"}
    )

    assert response.json() == {"context": "context-id", "state": "context-id"}


def test_controlled_error_uses_standard_envelope() -> None:
    response = TestClient(_test_app()).get(
        "/_test/not-found", headers={REQUEST_ID_HEADER: "controlled-id"}
    )

    assert response.status_code == 404
    assert response.headers[REQUEST_ID_HEADER] == "controlled-id"
    assert ErrorResponse.model_validate(response.json()).error.request_id == "controlled-id"
    assert response.json() == {
        "error": {
            "code": "RESOURCE_NOT_FOUND",
            "message": "The requested resource was not found.",
            "details": {},
            "request_id": "controlled-id",
        }
    }


def test_validation_error_is_structured_and_does_not_echo_input() -> None:
    response = TestClient(_test_app()).post(
        "/_test/validation",
        headers={REQUEST_ID_HEADER: "validation-id"},
        json={"quantity": "private-input"},
    )

    assert response.status_code == 422
    assert response.headers[REQUEST_ID_HEADER] == "validation-id"
    assert ErrorResponse.model_validate(response.json()).error.code == "VALIDATION_ERROR"
    assert response.json() == {
        "error": {
            "code": "VALIDATION_ERROR",
            "message": "The request contains invalid values.",
            "details": {
                "fields": [
                    {
                        "path": "body.quantity",
                        "message": "Invalid value.",
                        "type": "int_parsing",
                    }
                ]
            },
            "request_id": "validation-id",
        }
    }
    assert "private-input" not in response.text


def test_unknown_route_is_normalized() -> None:
    response = TestClient(_test_app()).get(
        "/does-not-exist", headers={REQUEST_ID_HEADER: "route-id"}
    )

    assert response.status_code == 404
    assert response.json() == {
        "error": {
            "code": "RESOURCE_NOT_FOUND",
            "message": "The requested resource was not found.",
            "details": {},
            "request_id": "route-id",
        }
    }


def test_unexpected_error_is_sanitized(caplog: pytest.LogCaptureFixture) -> None:
    response = TestClient(_test_app()).get(
        "/_test/internal-error", headers={REQUEST_ID_HEADER: "internal-id"}
    )

    assert response.status_code == 500
    assert response.headers[REQUEST_ID_HEADER] == "internal-id"
    assert ErrorResponse.model_validate(response.json()).error.request_id == "internal-id"
    assert response.json() == {
        "error": {
            "code": "INTERNAL_ERROR",
            "message": "An internal server error occurred.",
            "details": {},
            "request_id": "internal-id",
        }
    }
    assert "private-input" not in response.text
    assert "C:\\Users" not in response.text
    assert "traceback" not in response.text.lower()
    record = caplog.records[-1]
    assert record.message == "Unhandled API exception"
    assert record.__dict__["request_id"] == "internal-id"
    assert record.__dict__["exception_category"] == "RuntimeError"
    assert "private-input" not in caplog.text
    assert "C:\\Users" not in caplog.text


def test_request_ids_do_not_leak_between_concurrent_requests() -> None:
    app = _test_app()
    request_ids = [f"concurrent-{index}" for index in range(8)]

    def send_request(request_id: str) -> tuple[str, dict[str, str], str]:
        response = TestClient(app).get("/_test/context", headers={REQUEST_ID_HEADER: request_id})
        return request_id, response.json(), response.headers[REQUEST_ID_HEADER]

    with ThreadPoolExecutor(max_workers=8) as executor:
        results = list(executor.map(send_request, request_ids))

    for request_id, body, header in results:
        assert body == {"context": request_id, "state": request_id}
        assert header == request_id
