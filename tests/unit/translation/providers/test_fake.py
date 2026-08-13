import asyncio
from dataclasses import dataclass

import pytest
from transloka_translation.providers import (
    FakeTranslationProvider,
    ProviderErrorCode,
    TranslationProviderError,
)


@dataclass(frozen=True)
class Request:
    text: str


@dataclass(frozen=True)
class Response:
    text: str


@dataclass(frozen=True)
class Cancellation:
    is_cancelled: bool


def test_fake_translation_returns_configured_response_and_records_request() -> None:
    response = Response(text="Terjemahan")
    request = Request(text="Translation")
    provider = FakeTranslationProvider[Request, Response](response=response)

    result = asyncio.run(provider.translate(request))

    assert result is response
    assert provider.requests == (request,)


def test_fake_translation_raises_configured_normalized_failure() -> None:
    provider = FakeTranslationProvider[Request, Response](
        response=Response(text="unused"),
        failure=TranslationProviderError(
            ProviderErrorCode.PROVIDER_UNAVAILABLE,
            "Fake provider is unavailable.",
            retryable=True,
        ),
    )

    with pytest.raises(TranslationProviderError) as raised:
        asyncio.run(provider.translate(Request(text="Translation")))

    assert raised.value.code is ProviderErrorCode.PROVIDER_UNAVAILABLE
    assert raised.value.retryable is True
    assert provider.requests == (Request(text="Translation"),)


def test_fake_translation_honors_cancellation_before_dispatch() -> None:
    provider = FakeTranslationProvider[Request, Response](
        response=Response(text="unused"),
    )

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(
            provider.translate(
                Request(text="Translation"),
                cancellation=Cancellation(is_cancelled=True),
            )
        )

    assert provider.requests == ()
