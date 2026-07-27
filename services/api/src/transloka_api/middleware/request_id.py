import re
from contextvars import ContextVar, Token
from uuid import uuid4

from starlette.datastructures import Headers, MutableHeaders
from starlette.requests import Request
from starlette.types import ASGIApp, Message, Receive, Scope, Send

REQUEST_ID_HEADER = "X-Request-ID"
_REQUEST_ID_PATTERN = re.compile(r"[A-Za-z0-9._-]{1,128}")
_request_id: ContextVar[str | None] = ContextVar("request_id", default=None)


def get_request_id() -> str | None:
    return _request_id.get()


def _resolve_request_id(value: str | None) -> str:
    if value is not None:
        candidate = value.strip()
        if _REQUEST_ID_PATTERN.fullmatch(candidate):
            return candidate
    return f"req_{uuid4().hex}"


class RequestIdMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = _resolve_request_id(Headers(scope=scope).get(REQUEST_ID_HEADER))
        request = Request(scope, receive=receive)
        request.state.request_id = request_id
        token = _request_id.set(request_id)
        response_started = False

        async def send_with_request_id(message: Message) -> None:
            nonlocal response_started
            if message["type"] == "http.response.start":
                response_started = True
                MutableHeaders(scope=message)[REQUEST_ID_HEADER] = request_id
            await send(message)

        try:
            await self.app(scope, receive, send_with_request_id)
        except Exception as exc:
            if response_started:
                raise
            from transloka_api.exception_handlers import unexpected_exception_handler

            response = await unexpected_exception_handler(request, exc)
            await response(scope, receive, send_with_request_id)
        finally:
            self._reset_request_id(token)

    @staticmethod
    def _reset_request_id(token: Token[str | None]) -> None:
        _request_id.reset(token)
