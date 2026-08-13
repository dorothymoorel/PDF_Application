from __future__ import annotations

import asyncio
from collections.abc import Sequence

from .base import (
    CancellationSignal,
    LocalModel,
    ProviderHealth,
    ProviderHealthStatus,
    TranslationProviderError,
)


class FakeTranslationProvider[RequestT, ResponseT]:
    def __init__(
        self,
        *,
        response: ResponseT,
        models: Sequence[LocalModel] = (),
        health: ProviderHealth | None = None,
        failure: TranslationProviderError | None = None,
    ) -> None:
        self._response = response
        self._models = tuple(models)
        self._health = health or ProviderHealth(
            status=ProviderHealthStatus.AVAILABLE,
            version="fake",
        )
        self._failure = failure
        self._requests: list[RequestT] = []

    @property
    def requests(self) -> tuple[RequestT, ...]:
        return tuple(self._requests)

    async def health_check(self) -> ProviderHealth:
        return self._health

    async def list_models(self) -> list[LocalModel]:
        return list(self._models)

    async def translate(
        self,
        request: RequestT,
        *,
        cancellation: CancellationSignal | None = None,
    ) -> ResponseT:
        self._raise_if_cancelled(cancellation)
        await asyncio.sleep(0)
        self._raise_if_cancelled(cancellation)

        self._requests.append(request)
        if self._failure is not None:
            raise TranslationProviderError(
                self._failure.code,
                str(self._failure),
                retryable=self._failure.retryable,
            )
        return self._response

    @staticmethod
    def _raise_if_cancelled(cancellation: CancellationSignal | None) -> None:
        if cancellation is not None and cancellation.is_cancelled:
            raise asyncio.CancelledError
