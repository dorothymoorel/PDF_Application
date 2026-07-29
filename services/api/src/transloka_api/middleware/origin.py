from collections.abc import Sequence

from starlette.datastructures import Headers
from starlette.requests import Request
from starlette.types import ASGIApp, Receive, Scope, Send

from transloka_api.exception_handlers import TransLokaError, transloka_exception_handler
from transloka_api.middleware.client_headers import CLIENT_HEADER, CLIENT_VERSION_HEADER

CORS_ALLOWED_METHODS = ("GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS")
CORS_ALLOWED_HEADERS = (
    "Accept",
    "Content-Type",
    "Idempotency-Key",
    "X-Request-ID",
    CLIENT_HEADER,
    CLIENT_VERSION_HEADER,
)
CORS_EXPOSE_HEADERS = ("X-Request-ID",)


class OriginValidationMiddleware:
    def __init__(self, app: ASGIApp, allowed_origins: Sequence[str]) -> None:
        self.app = app
        self.allowed_origins = frozenset(allowed_origins)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        origins = Headers(scope=scope).getlist("origin")
        if origins and (len(origins) != 1 or origins[0] not in self.allowed_origins):
            request = Request(scope, receive=receive)
            error = TransLokaError(
                code="ORIGIN_NOT_ALLOWED",
                message="The request origin is not allowed.",
                status_code=403,
            )
            response = await transloka_exception_handler(request, error)
            await response(scope, receive, send)
            return

        await self.app(scope, receive, send)
