from __future__ import annotations

import asyncio
import json
import math
import os
from datetime import UTC, datetime
from email.message import Message
from email.utils import parsedate_to_datetime
from http.client import HTTPException, HTTPResponse
from threading import Event
from time import monotonic
from typing import IO, cast
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

from transloka_translation.prompts import TranslationPrompt, build_translation_prompt
from transloka_translation.schemas import TranslationRequest, TranslationResponse

from .base import (
    CancellationSignal,
    LocalModel,
    ProviderErrorCode,
    ProviderHealth,
    ProviderHealthStatus,
    TranslationProviderError,
)

GROQ_MODELS = ("qwen/qwen3.8-27b", "openai/gpt-oss-120b")
_BASE_URL = "https://api.groq.com/openai/v1"
_MAX_BYTES = 1024 * 1024


def _error(code: ProviderErrorCode, *, retryable: bool = False) -> TranslationProviderError:
    return TranslationProviderError(
        code, f"Groq request failed: {code.value}.", retryable=retryable
    )


class _RejectRedirects(HTTPRedirectHandler):
    def redirect_request(
        self, req: Request, fp: IO[bytes], code: int, msg: str, headers: Message, newurl: str
    ) -> Request | None:
        return None


class GroqTranslationProvider:
    """Opt-in text adapter. Runtime owns consent snapshots, pacing and retries."""

    def __init__(
        self,
        *,
        enabled: bool = False,
        cloud_consent: bool = False,
        model_name: str | None = None,
        timeout_seconds: float = 30.0,
    ) -> None:
        if type(enabled) is not bool or type(cloud_consent) is not bool:
            raise ValueError("Cloud configuration must use boolean values.")
        if model_name is not None and model_name not in GROQ_MODELS:
            raise ValueError("Select an allowlisted Groq model.")
        if (
            isinstance(timeout_seconds, bool)
            or not isinstance(timeout_seconds, (int, float))
            or not math.isfinite(timeout_seconds)
            or not 0 < timeout_seconds <= 120
        ):
            raise ValueError("Groq timeout must be finite, greater than zero and at most 120s.")
        self._enabled = enabled
        self._cloud_consent = cloud_consent
        self._model_name = model_name
        self._timeout = float(timeout_seconds)

    async def health_check(self) -> ProviderHealth:
        try:
            models = await self.list_models()
        except TranslationProviderError as exc:
            return ProviderHealth(ProviderHealthStatus.UNAVAILABLE, detail=exc.code.value)
        available = bool(models) and (
            self._model_name is None or any(model.name == self._model_name for model in models)
        )
        return ProviderHealth(
            ProviderHealthStatus.AVAILABLE if available else ProviderHealthStatus.UNAVAILABLE
        )

    async def list_models(self) -> list[LocalModel]:
        payload = await self._request("/models")
        records = payload.get("data")
        if not isinstance(records, list) or any(
            not isinstance(record, dict) or not isinstance(record.get("id"), str)
            for record in records
        ):
            raise _error(ProviderErrorCode.INVALID_RESPONSE)
        names = {record["id"] for record in records if record.get("active", True) is True}
        return [LocalModel(name=name) for name in GROQ_MODELS if name in names]

    async def translate(
        self, request: object, *, cancellation: CancellationSignal | None = None
    ) -> str:
        _check_cancelled(cancellation)
        if not self._enabled or not self._cloud_consent or self._model_name is None:
            raise _error(ProviderErrorCode.INVALID_REQUEST)
        try:
            if isinstance(request, TranslationRequest):
                prompt = build_translation_prompt(request)
            elif isinstance(request, TranslationPrompt):
                prompt = request
            else:
                raise ValueError
            source = prompt.source_data["source_data"]
            if not isinstance(source, dict):
                raise ValueError
            validated = TranslationRequest.from_dict(source)
            ids = tuple(segment.segment_id for segment in validated.segments)
            schema = TranslationResponse.json_schema(known_segment_ids=ids)
        except (KeyError, TypeError, ValueError, RecursionError):
            raise _error(ProviderErrorCode.INVALID_REQUEST) from None
        payload = await self._request(
            "/chat/completions",
            {
                "model": self._model_name,
                "messages": [message.to_dict() for message in prompt.messages],
                "stream": False,
                "max_completion_tokens": 4096,
                "reasoning_effort": "none" if self._model_name.startswith("qwen/") else "low",
                "response_format": {
                    "type": "json_schema",
                    "json_schema": {"name": "translation", "strict": True, "schema": schema},
                },
            },
            cancellation=cancellation,
        )
        try:
            choices = payload["choices"]
            if not isinstance(choices, list) or len(choices) != 1:
                raise ValueError
            choice = choices[0]
            message = choice["message"]
            if message.get("refusal") or choice.get("finish_reason") == "content_filter":
                raise _error(ProviderErrorCode.CONTENT_REJECTED)
            if choice["finish_reason"] != "stop" or message.get("tool_calls"):
                raise ValueError
            content = message["content"]
            if not isinstance(content, str):
                raise ValueError
            response = TranslationResponse.from_dict(
                _decode(content.encode()), known_segment_ids=ids
            )
        except (KeyError, TypeError, ValueError, AttributeError, RecursionError):
            raise _error(ProviderErrorCode.INVALID_RESPONSE) from None
        _check_cancelled(cancellation)
        return json.dumps(response.to_dict(), ensure_ascii=False, allow_nan=False)

    async def _request(
        self,
        path: str,
        payload: dict[str, object] | None = None,
        *,
        cancellation: CancellationSignal | None = None,
    ) -> dict[str, object]:
        _check_cancelled(cancellation)
        if not self._enabled:
            raise _error(ProviderErrorCode.INVALID_REQUEST)
        key = os.environ.get("GROQ_API_KEY", "")
        if not key or len(key) > 512 or any(not 33 <= ord(char) <= 126 for char in key):
            raise _error(ProviderErrorCode.AUTHENTICATION_FAILED)
        try:
            body = None if payload is None else json.dumps(payload, allow_nan=False).encode()
        except (TypeError, ValueError, RecursionError):
            raise _error(ProviderErrorCode.INVALID_REQUEST) from None
        if body is not None and len(body) > _MAX_BYTES:
            raise _error(ProviderErrorCode.INVALID_REQUEST)
        stopped = Event()
        deadline = monotonic() + self._timeout
        operation = asyncio.create_task(
            asyncio.to_thread(self._send, path, body, key, stopped, deadline)
        )
        try:
            async with asyncio.timeout(self._timeout):
                while not operation.done():
                    await asyncio.wait({operation}, timeout=0.05)
                    _check_cancelled(cancellation)
                _check_cancelled(cancellation)
                return await operation
        except TimeoutError:
            raise _error(ProviderErrorCode.TIMEOUT, retryable=True) from None
        finally:
            stopped.set()
            operation.cancel()

    def _send(
        self, path: str, body: bytes | None, key: str, stopped: Event, deadline: float
    ) -> dict[str, object]:
        # Fixed host; urllib redirects/proxies are explicitly disabled.
        if path not in ("/models", "/chat/completions"):
            raise _error(ProviderErrorCode.INVALID_REQUEST)
        request = Request(
            _BASE_URL + path,
            data=body,
            headers={
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )
        opener = build_opener(ProxyHandler({}), _RejectRedirects())
        try:
            if stopped.is_set():
                raise _error(ProviderErrorCode.TIMEOUT)
            with cast(HTTPResponse, opener.open(request, timeout=self._timeout)) as response:
                data = bytearray()
                while True:
                    if stopped.is_set() or monotonic() >= deadline:
                        raise _error(ProviderErrorCode.TIMEOUT, retryable=True)
                    chunk = response.read1(min(65536, _MAX_BYTES + 1 - len(data)))
                    if not chunk:
                        break
                    data.extend(chunk)
                    if len(data) > _MAX_BYTES:
                        raise _error(ProviderErrorCode.INVALID_RESPONSE)
                return _decode(bytes(data))
        except HTTPError as exc:
            code = exc.code
            retry_after = _retry_after(exc.headers.get("Retry-After"))
            exc.close()
            mapped = (
                ProviderErrorCode.AUTHENTICATION_FAILED
                if code in (401, 403)
                else ProviderErrorCode.RATE_LIMIT
                if code == 429
                else ProviderErrorCode.INVALID_REQUEST
                if code in (400, 404, 413, 422)
                else ProviderErrorCode.PROVIDER_UNAVAILABLE
            )
            error = _error(mapped, retryable=code == 429 or 500 <= code < 600)
            error.retry_after_seconds = retry_after if error.retryable else None
            raise error from None
        except (TimeoutError, URLError, OSError, HTTPException) as exc:
            timed_out = isinstance(exc, TimeoutError) or (
                isinstance(exc, URLError) and isinstance(exc.reason, TimeoutError)
            )
            raise _error(
                ProviderErrorCode.TIMEOUT if timed_out else ProviderErrorCode.PROVIDER_UNAVAILABLE,
                retryable=True,
            ) from None


def _check_cancelled(signal: CancellationSignal | None) -> None:
    if signal is not None and signal.is_cancelled:
        raise asyncio.CancelledError


def _decode(data: bytes) -> dict[str, object]:
    def pairs(items: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, value in items:
            if key in result:
                raise ValueError
            result[key] = value
        return result

    def invalid_constant(value: str) -> object:
        raise ValueError

    try:
        if len(data) > _MAX_BYTES:
            raise ValueError
        result = json.loads(data, object_pairs_hook=pairs, parse_constant=invalid_constant)
        if not isinstance(result, dict):
            raise ValueError
        return cast(dict[str, object], result)
    except (ValueError, UnicodeError, RecursionError):
        raise _error(ProviderErrorCode.INVALID_RESPONSE) from None


def _retry_after(value: str | None) -> float | None:
    if value is None or len(value) > 128:
        return None
    try:
        seconds = float(value)
    except ValueError:
        try:
            date = parsedate_to_datetime(value)
            if date.tzinfo is None:
                return None
            seconds = (date - datetime.now(UTC)).total_seconds()
        except (TypeError, ValueError, OverflowError):
            return None
    return min(86400.0, max(0.0, seconds)) if math.isfinite(seconds) else None
