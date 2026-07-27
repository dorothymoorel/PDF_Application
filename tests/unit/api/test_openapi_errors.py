import json

from fastapi.testclient import TestClient
from transloka_api.app import create_app
from transloka_api.middleware import REQUEST_ID_HEADER
from transloka_api.schemas import ErrorResponse

ERROR_RESPONSE_REF = "#/components/schemas/ErrorResponse"
HEALTH_PATHS = ("/health", "/api/v1/system/health")


def test_openapi_exposes_normalized_error_contract() -> None:
    schema = create_app().openapi()
    schemas = schema["components"]["schemas"]

    assert "ErrorResponse" in schemas
    assert schemas["ErrorResponse"]["required"] == ["error"]
    assert set(schemas["ErrorBody"]["required"]) == {
        "code",
        "message",
        "details",
        "request_id",
    }
    assert set(schemas["ErrorBody"]["properties"]) == {
        "code",
        "message",
        "details",
        "request_id",
    }
    assert schemas["ErrorBody"]["properties"]["details"]["$ref"].endswith("/ErrorDetails")
    assert "HTTPValidationError" not in schemas
    assert "ValidationError" not in schemas


def test_health_operations_reference_normalized_errors() -> None:
    schema = create_app().openapi()

    for path in HEALTH_PATHS:
        operation = schema["paths"][path]["get"]
        assert set(operation["responses"]) == {"200", "403", "500"}
        for status in ("403", "500"):
            response_schema = operation["responses"][status]["content"]["application/json"][
                "schema"
            ]
            assert response_schema["$ref"] == ERROR_RESPONSE_REF


def test_openapi_operation_ids_and_security_remain_stable() -> None:
    schema = create_app().openapi()

    assert schema["paths"]["/health"]["get"]["operationId"] == "get_health"
    assert schema["paths"]["/api/v1/system/health"]["get"]["operationId"] == "get_system_health"
    assert "securitySchemes" not in schema.get("components", {})
    assert "security" not in schema["paths"]["/health"]["get"]
    assert "security" not in schema["paths"]["/api/v1/system/health"]["get"]


def test_repeated_openapi_calls_are_equivalent_and_path_free() -> None:
    app = create_app()
    first = app.openapi()
    second = app.openapi()
    serialized = json.dumps(first, sort_keys=True)

    assert first == second
    assert "F:\\PDF_Application" not in serialized
    assert "C:\\Users\\" not in serialized
    assert "traceback" not in serialized.casefold()


def test_origin_rejection_matches_canonical_error_model() -> None:
    response = TestClient(create_app()).get(
        "/health",
        headers={
            "Origin": "http://example.com:3000",
            REQUEST_ID_HEADER: "openapi-origin",
        },
    )
    payload = ErrorResponse.model_validate(response.json())

    assert response.status_code == 403
    assert response.headers[REQUEST_ID_HEADER] == payload.error.request_id
    assert payload.error.code == "ORIGIN_NOT_ALLOWED"
