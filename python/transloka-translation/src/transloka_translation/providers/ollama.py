from __future__ import annotations

import asyncio
import json
import os
from email.message import Message
from http.client import HTTPResponse
from ipaddress import ip_address
from json import JSONDecodeError
from math import isfinite
from numbers import Real
from typing import IO, cast
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit, urlunsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

from transloka_translation.prompts import (
    TranslationPrompt,
    build_translation_prompt,
)
from transloka_translation.schemas import TranslationRequest

from .base import (
    CancellationSignal,
    LocalModel,
    ProviderErrorCode,
    ProviderHealth,
    ProviderHealthStatus,
    TranslationProviderError,
)

DEFAULT_OLLAMA_BASE_URL = "http://127.0.0.1:11434"
DEFAULT_OLLAMA_TIMEOUT_SECONDS = 2.0
_MAX_RESPONSE_BYTES = 1024 * 1024
_MAX_REQUEST_BYTES = 1024 * 1024
_LOCAL_ONLY_ERROR = "REMOTE_OLLAMA_BLOCKED: Ollama endpoint must be a local HTTP URL."


class RemoteOllamaEndpointError(ValueError):
    pass


class _RejectRedirects(HTTPRedirectHandler):
    def redirect_request(
        self,
        request: Request,
        file_pointer: IO[bytes],
        code: int,
        message: str,
        headers: Message,
        new_url: str,
    ) -> Request | None:
        return None


def validate_ollama_base_url(value: str) -> str:
    if not isinstance(value, str) or not value.isprintable():
        raise RemoteOllamaEndpointError(_LOCAL_ONLY_ERROR)

    candidate = value.strip()
    if not candidate or "%" in candidate:
        raise RemoteOllamaEndpointError(_LOCAL_ONLY_ERROR)

    try:
        parsed = urlsplit(candidate)
        hostname = parsed.hostname
        port = parsed.port
    except ValueError:
        raise RemoteOllamaEndpointError(_LOCAL_ONLY_ERROR) from None

    if (
        parsed.scheme.casefold() != "http"
        or not parsed.netloc
        or hostname is None
        or port is None
        or not 1 <= port <= 65535
        or parsed.username is not None
        or parsed.password is not None
        or parsed.path not in ("", "/")
        or parsed.query
        or parsed.fragment
    ):
        raise RemoteOllamaEndpointError(_LOCAL_ONLY_ERROR)

    normalized_hostname = hostname.casefold()
    if normalized_hostname != "localhost":
        try:
            address = ip_address(normalized_hostname)
        except ValueError:
            raise RemoteOllamaEndpointError(_LOCAL_ONLY_ERROR) from None
        if not address.is_loopback:
            raise RemoteOllamaEndpointError(_LOCAL_ONLY_ERROR)
        normalized_hostname = str(address)

    if ":" in normalized_hostname:
        normalized_hostname = f"[{normalized_hostname}]"
    return urlunsplit(("http", f"{normalized_hostname}:{port}", "", "", ""))


class OllamaTranslationProvider:
    def __init__(
        self,
        base_url: str | None = None,
        *,
        model_name: str | None = None,
        temperature: float = 0.1,
        timeout_seconds: float = DEFAULT_OLLAMA_TIMEOUT_SECONDS,
        translation_timeout_seconds: float = 120.0,
    ) -> None:
        if not 0 < timeout_seconds <= 60:
            raise ValueError("Ollama timeout must be greater than zero and at most 60 seconds.")
        if model_name is not None and (
            type(model_name) is not str
            or not model_name.strip()
            or not model_name.isprintable()
            or len(model_name.strip()) > 200
        ):
            raise ValueError(
                "Ollama model name must be a printable string of at most 200 characters."
            )
        if (
            isinstance(temperature, bool)
            or not isinstance(temperature, Real)
            or not isfinite(float(temperature))
            or not 0 <= temperature <= 2
        ):
            raise ValueError("Ollama temperature must be between zero and two.")
        if (
            isinstance(translation_timeout_seconds, bool)
            or not isinstance(translation_timeout_seconds, Real)
            or not isfinite(float(translation_timeout_seconds))
            or not 0 < translation_timeout_seconds <= 600
        ):
            raise ValueError(
                "Ollama translation timeout must be greater than zero and at most 600 seconds."
            )
        configured_url = (
            base_url
            if base_url is not None
            else os.environ.get("TRANSLOKA_OLLAMA_URL", DEFAULT_OLLAMA_BASE_URL)
        )
        self._base_url: str = validate_ollama_base_url(configured_url)
        self._model_name: str | None = model_name.strip() if model_name is not None else None
        self._temperature: float = float(temperature)
        self._timeout_seconds: float = timeout_seconds
        self._translation_timeout_seconds: float = float(translation_timeout_seconds)

    @property
    def base_url(self) -> str:
        return self._base_url

    async def health_check(self) -> ProviderHealth:
        try:
            payload = await self._get_json("/api/version")
            raw_version = payload.get("version", "unknown")
            if not isinstance(raw_version, str):
                raise self._invalid_response()
            version = raw_version.strip() or "unknown"
        except TranslationProviderError as exc:
            return ProviderHealth(
                status=ProviderHealthStatus.UNAVAILABLE,
                detail=exc.code.value,
            )
        return ProviderHealth(status=ProviderHealthStatus.AVAILABLE, version=version)

    async def list_models(self) -> list[LocalModel]:
        payload = await self._get_json("/api/tags")
        raw_models = payload.get("models")
        if not isinstance(raw_models, list):
            raise self._invalid_response()

        models: list[LocalModel] = []
        for raw_model in raw_models:
            if not isinstance(raw_model, dict):
                raise self._invalid_response()
            name = raw_model.get("name")
            size = raw_model.get("size")
            if (
                not isinstance(name, str)
                or not name.strip()
                or not name.isprintable()
                or (size is not None and (type(size) is not int or size < 0))
            ):
                raise self._invalid_response()
            models.append(LocalModel(name=name.strip(), size_bytes=size))
        return models

    async def translate(
        self,
        request: object,
        *,
        cancellation: CancellationSignal | None = None,
    ) -> str:
        if cancellation is not None and cancellation.is_cancelled:
            raise asyncio.CancelledError
        prompt = self._translation_prompt(request)
        response_schema = self._response_schema(prompt)
        payload = await self._post_json(
            "/api/chat",
            {
                "model": self._require_model_name(),
                "stream": False,
                "think": False,
                "format": response_schema,
                "messages": [message.to_dict() for message in prompt.messages],
                "options": {"temperature": self._temperature},
            },
            cancellation=cancellation,
        )
        message = payload.get("message")
        if not isinstance(message, dict):
            raise self._invalid_response()
        content = message.get("content")
        if not isinstance(content, str) or not content:
            raise self._invalid_response()
        if cancellation is not None and cancellation.is_cancelled:
            raise asyncio.CancelledError
        return content

    @staticmethod
    def _translation_prompt(request: object) -> TranslationPrompt:
        if isinstance(request, TranslationPrompt):
            return request
        if isinstance(request, TranslationRequest):
            return build_translation_prompt(request)
        raise TranslationProviderError(
            ProviderErrorCode.INVALID_REQUEST,
            "The translation request is invalid.",
        )

    def _require_model_name(self) -> str:
        if self._model_name is None:
            raise TranslationProviderError(
                ProviderErrorCode.INVALID_REQUEST,
                "A local Ollama model must be selected before translation.",
            )
        return self._model_name

    @staticmethod
    def _response_schema(prompt: TranslationPrompt) -> dict[str, object]:
        try:
            return cast(dict[str, object], prompt.response_schema)
        except ValueError:
            raise TranslationProviderError(
                ProviderErrorCode.INVALID_REQUEST,
                "The translation request is invalid.",
            ) from None

    async def _get_json(self, path: str) -> dict[str, object]:
        return await asyncio.to_thread(self._get_json_sync, path)

    async def _post_json(
        self,
        path: str,
        payload: dict[str, object],
        *,
        cancellation: CancellationSignal | None,
    ) -> dict[str, object]:
        if cancellation is not None and cancellation.is_cancelled:
            raise asyncio.CancelledError

        operation = asyncio.create_task(asyncio.to_thread(self._post_json_sync, path, payload))
        try:
            while not operation.done():
                await asyncio.wait({operation}, timeout=0.05)
                if cancellation is not None and cancellation.is_cancelled:
                    operation.cancel()
                    raise asyncio.CancelledError
            return await operation
        except asyncio.CancelledError:
            operation.cancel()
            raise

    def _post_json_sync(self, path: str, payload: dict[str, object]) -> dict[str, object]:
        try:
            body = json.dumps(
                payload,
                ensure_ascii=False,
                allow_nan=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        except (TypeError, ValueError) as exc:
            raise TranslationProviderError(
                ProviderErrorCode.INVALID_REQUEST,
                "The translation request is invalid.",
            ) from exc
        if len(body) > _MAX_REQUEST_BYTES:
            raise TranslationProviderError(
                ProviderErrorCode.INVALID_REQUEST,
                "The translation request is too large.",
            )

        request = Request(
            f"{self._base_url}{path}",
            data=body,
            headers={"Accept": "application/json", "Content-Type": "application/json"},
            method="POST",
        )
        opener = build_opener(ProxyHandler({}), _RejectRedirects())
        try:
            with cast(
                HTTPResponse,
                opener.open(request, timeout=self._translation_timeout_seconds),
            ) as response:
                response_body = response.read(_MAX_RESPONSE_BYTES + 1)
        except HTTPError as exc:
            status_code = exc.code
            exc.close()
            raise self._http_error(status_code) from None
        except URLError as exc:
            if isinstance(exc.reason, TimeoutError):
                raise self._timeout_error() from exc
            raise TranslationProviderError(
                ProviderErrorCode.PROVIDER_UNAVAILABLE,
                "The local Ollama service is unavailable.",
                retryable=True,
            ) from exc
        except TimeoutError as exc:
            raise self._timeout_error() from exc
        except OSError as exc:
            raise TranslationProviderError(
                ProviderErrorCode.PROVIDER_UNAVAILABLE,
                "The local Ollama service is unavailable.",
                retryable=True,
            ) from exc

        return self._decode_response(response_body)

    def _get_json_sync(self, path: str) -> dict[str, object]:
        request = Request(
            f"{self._base_url}{path}",
            headers={"Accept": "application/json"},
            method="GET",
        )
        opener = build_opener(ProxyHandler({}), _RejectRedirects())
        try:
            with cast(
                HTTPResponse,
                opener.open(request, timeout=self._timeout_seconds),
            ) as response:
                body = response.read(_MAX_RESPONSE_BYTES + 1)
        except HTTPError as exc:
            status_code = exc.code
            exc.close()
            raise TranslationProviderError(
                ProviderErrorCode.PROVIDER_UNAVAILABLE,
                "The local Ollama service returned an unsuccessful response.",
                retryable=status_code >= 500,
            ) from None
        except URLError as exc:
            if isinstance(exc.reason, TimeoutError):
                raise self._timeout_error() from exc
            raise TranslationProviderError(
                ProviderErrorCode.PROVIDER_UNAVAILABLE,
                "The local Ollama service is unavailable.",
                retryable=True,
            ) from exc
        except TimeoutError as exc:
            raise self._timeout_error() from exc
        except OSError as exc:
            raise TranslationProviderError(
                ProviderErrorCode.PROVIDER_UNAVAILABLE,
                "The local Ollama service is unavailable.",
                retryable=True,
            ) from exc

        return self._decode_response(body)

    def _decode_response(self, body: bytes) -> dict[str, object]:
        if len(body) > _MAX_RESPONSE_BYTES:
            raise self._invalid_response()
        try:
            payload = json.loads(body.decode("utf-8"))
        except (JSONDecodeError, UnicodeDecodeError) as exc:
            raise self._invalid_response() from exc
        if not isinstance(payload, dict):
            raise self._invalid_response()
        return cast(dict[str, object], payload)

    @staticmethod
    def _http_error(status_code: int) -> TranslationProviderError:
        if status_code in (400, 404):
            return TranslationProviderError(
                ProviderErrorCode.INVALID_REQUEST,
                "The local Ollama service rejected the translation request.",
            )
        if status_code == 429:
            return TranslationProviderError(
                ProviderErrorCode.RATE_LIMIT,
                "The local Ollama service is temporarily busy.",
                retryable=True,
            )
        return TranslationProviderError(
            ProviderErrorCode.PROVIDER_UNAVAILABLE,
            "The local Ollama service returned an unsuccessful response.",
            retryable=status_code >= 500,
        )

    @staticmethod
    def _timeout_error() -> TranslationProviderError:
        return TranslationProviderError(
            ProviderErrorCode.TIMEOUT,
            "The local Ollama service timed out.",
            retryable=True,
        )

    @staticmethod
    def _invalid_response() -> TranslationProviderError:
        return TranslationProviderError(
            ProviderErrorCode.INVALID_RESPONSE,
            "The local Ollama service returned an invalid response.",
        )
