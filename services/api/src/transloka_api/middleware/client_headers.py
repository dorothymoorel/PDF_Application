from collections.abc import Sequence

from starlette.datastructures import Headers
from starlette.requests import Request
from starlette.types import ASGIApp, Receive, Scope, Send

from transloka_api import __version__
from transloka_api.exception_handlers import TransLokaError, transloka_exception_handler

CLIENT_HEADER = "X-TransLoka-Client"
CLIENT_HEADER_VALUE = "web"
CLIENT_VERSION_HEADER = "X-TransLoka-Client-Version"
CLIENT_VERSION_VALUE = __version__
MUTATION_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
_EXEMPT_PATHS = frozenset({"/health", "/api/v1/system/health"})


def validate_client_headers(
    client_values: Sequence[str],
    version_values: Sequence[str],
) -> str | None:
    if not client_values or not version_values:
        return "CLIENT_HEADER_REQUIRED"
    if (
        len(client_values) != 1
        or len(version_values) != 1
        or client_values[0] != CLIENT_HEADER_VALUE
        or version_values[0] != CLIENT_VERSION_VALUE
    ):
        return "CLIENT_HEADER_INVALID"
    return None


class ClientHeaderMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or not self._requires_client_headers(scope):
            await self.app(scope, receive, send)
            return

        request_headers = Headers(scope=scope)
        error_code = validate_client_headers(
            request_headers.getlist(CLIENT_HEADER),
            request_headers.getlist(CLIENT_VERSION_HEADER),
        )
        if error_code is None:
            await self.app(scope, receive, send)
            return

        message = (
            "TransLoka client headers are required."
            if error_code == "CLIENT_HEADER_REQUIRED"
            else "The TransLoka client headers are invalid."
        )
        request = Request(scope, receive=receive)
        error = TransLokaError(
            code=error_code,
            message=message,
            status_code=403,
        )
        response = await transloka_exception_handler(request, error)
        await response(scope, receive, send)

    @staticmethod
    def _requires_client_headers(scope: Scope) -> bool:
        method = scope["method"]
        path = scope["path"]
        return (
            method in MUTATION_METHODS
            and path not in _EXEMPT_PATHS
            and (path == "/api/v1" or path.startswith("/api/v1/"))
        )
