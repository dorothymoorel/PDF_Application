import logging
from collections.abc import Mapping

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

from transloka_api.exception_handlers.exceptions import TransLokaError
from transloka_api.schemas import (
    ErrorBody,
    ErrorDetails,
    ErrorResponse,
)

logger = logging.getLogger(__name__)


def _request_id(request: Request) -> str:
    value = getattr(request.state, "request_id", None)
    return value if isinstance(value, str) else "unavailable"


def _error_response(
    request: Request,
    *,
    status_code: int,
    code: str,
    message: str,
    details: ErrorDetails | None = None,
    headers: Mapping[str, str] | None = None,
) -> JSONResponse:
    payload = ErrorResponse(
        error=ErrorBody(
            code=code,
            message=message,
            details=details or {},
            request_id=_request_id(request),
        )
    )
    return JSONResponse(
        status_code=status_code,
        content=payload.model_dump(mode="json"),
        headers=headers,
    )


async def transloka_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    if not isinstance(exc, TransLokaError):
        raise exc
    return _error_response(
        request,
        status_code=exc.status_code,
        code=exc.code,
        message=exc.message,
        details=exc.details,
    )


async def request_validation_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    if not isinstance(exc, RequestValidationError):
        raise exc
    fields: list[object] = []
    for error in exc.errors():
        location = error.get("loc", ())
        path = ".".join(str(part) for part in location)
        error_type = error.get("type", "validation_error")
        field: ErrorDetails = {
            "path": path,
            "message": "Invalid value.",
            "type": str(error_type),
        }
        fields.append(field)

    return _error_response(
        request,
        status_code=422,
        code="VALIDATION_ERROR",
        message="The request contains invalid values.",
        details={"fields": fields},
    )


async def http_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    if not isinstance(exc, HTTPException):
        raise exc
    if exc.status_code == 404:
        code = "RESOURCE_NOT_FOUND"
        message = "The requested resource was not found."
    else:
        code = "OPERATION_NOT_ALLOWED"
        message = "The request could not be completed."

    return _error_response(
        request,
        status_code=exc.status_code,
        code=code,
        message=message,
        headers=exc.headers,
    )


async def unexpected_exception_handler(request: Request, _exc: Exception) -> JSONResponse:
    request_id = _request_id(request)
    logger.error(
        "Unhandled API exception",
        extra={
            "exception_category": type(_exc).__name__,
            "request_id": request_id,
        },
    )
    return _error_response(
        request,
        status_code=500,
        code="INTERNAL_ERROR",
        message="An internal server error occurred.",
    )
