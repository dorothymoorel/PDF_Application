from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol, TypeVar, runtime_checkable


class ProviderHealthStatus(StrEnum):
    AVAILABLE = "AVAILABLE"
    DEGRADED = "DEGRADED"
    UNAVAILABLE = "UNAVAILABLE"


@dataclass(frozen=True, slots=True)
class ProviderHealth:
    status: ProviderHealthStatus
    version: str | None = None
    detail: str | None = None


@dataclass(frozen=True, slots=True)
class LocalModel:
    name: str
    size_bytes: int | None = None


class ProviderErrorCode(StrEnum):
    TIMEOUT = "TIMEOUT"
    RATE_LIMIT = "RATE_LIMIT"
    AUTHENTICATION_FAILED = "AUTHENTICATION_FAILED"
    INVALID_REQUEST = "INVALID_REQUEST"
    INVALID_RESPONSE = "INVALID_RESPONSE"
    CONTENT_REJECTED = "CONTENT_REJECTED"
    PROVIDER_UNAVAILABLE = "PROVIDER_UNAVAILABLE"
    CONTEXT_LIMIT_EXCEEDED = "CONTEXT_LIMIT_EXCEEDED"
    UNKNOWN_PROVIDER_ERROR = "UNKNOWN_PROVIDER_ERROR"


class TranslationProviderError(RuntimeError):
    def __init__(
        self,
        code: ProviderErrorCode,
        message: str,
        *,
        retryable: bool = False,
        retry_after_seconds: float | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.retryable = retryable
        self.retry_after_seconds = retry_after_seconds


@runtime_checkable
class CancellationSignal(Protocol):
    @property
    def is_cancelled(self) -> bool: ...


RequestT_contra = TypeVar("RequestT_contra", contravariant=True)
ResponseT_co = TypeVar("ResponseT_co", covariant=True)


@runtime_checkable
class TranslationProvider(Protocol[RequestT_contra, ResponseT_co]):
    async def health_check(self) -> ProviderHealth: ...

    async def list_models(self) -> list[LocalModel]: ...

    async def translate(
        self,
        request: RequestT_contra,
        *,
        cancellation: CancellationSignal | None = None,
    ) -> ResponseT_co: ...
