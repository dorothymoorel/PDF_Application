from __future__ import annotations

import asyncio
import json
import os
from email.message import Message
from http.client import HTTPResponse
from ipaddress import ip_address
from json import JSONDecodeError
from typing import IO, cast
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit, urlunsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

from .base import (
    LocalModel,
    ProviderErrorCode,
    ProviderHealth,
    ProviderHealthStatus,
    TranslationProviderError,
)

DEFAULT_OLLAMA_BASE_URL = "http://127.0.0.1:11434"
DEFAULT_OLLAMA_TIMEOUT_SECONDS = 2.0
_MAX_RESPONSE_BYTES = 1024 * 1024
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
        timeout_seconds: float = DEFAULT_OLLAMA_TIMEOUT_SECONDS,
    ) -> None:
        if not 0 < timeout_seconds <= 60:
            raise ValueError("Ollama timeout must be greater than zero and at most 60 seconds.")
        configured_url = (
            base_url
            if base_url is not None
            else os.environ.get("TRANSLOKA_OLLAMA_URL", DEFAULT_OLLAMA_BASE_URL)
        )
        self._base_url = validate_ollama_base_url(configured_url)
        self._timeout_seconds = timeout_seconds

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

    async def _get_json(self, path: str) -> dict[str, object]:
        return await asyncio.to_thread(self._get_json_sync, path)

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
            raise TranslationProviderError(
                ProviderErrorCode.PROVIDER_UNAVAILABLE,
                "The local Ollama service returned an unsuccessful response.",
                retryable=exc.code >= 500,
            ) from exc
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
