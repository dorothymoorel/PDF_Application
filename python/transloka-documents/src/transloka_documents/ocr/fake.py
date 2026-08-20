from __future__ import annotations

from dataclasses import replace

from .base import (
    OCRHealth,
    OCRHealthStatus,
    OCRPage,
    OCRProviderError,
    OCRProviderErrorCode,
    OCRResult,
    OCRSettings,
)


class FakeOCRProvider:
    def __init__(
        self,
        *,
        result: OCRResult | None = None,
        response: OCRResult | None = None,
        health: OCRHealth | None = None,
        failure: OCRProviderError | None = None,
        delay_seconds: float = 0.0,
        timeout_seconds: float | None = None,
    ) -> None:
        if result is not None and response is not None:
            raise ValueError("Configure either result or response, not both.")
        if delay_seconds < 0:
            raise ValueError("Fake OCR delay must not be negative.")
        if timeout_seconds is not None and timeout_seconds <= 0:
            raise ValueError("Fake OCR timeout must be greater than zero.")
        self._result = result if result is not None else response
        self._health = health or OCRHealth(
            status=OCRHealthStatus.AVAILABLE,
            provider="fake",
            version="fake",
        )
        self._failure = failure
        self._delay_seconds = delay_seconds
        self._timeout_seconds = timeout_seconds
        self._requests: list[OCRPage] = []

    @property
    def requests(self) -> tuple[OCRPage, ...]:
        return tuple(self._requests)

    def health_check(self) -> OCRHealth:
        return self._health

    def health(self) -> OCRHealth:
        return self.health_check()

    def analyze_page(
        self,
        page: OCRPage,
        *,
        settings: OCRSettings | None = None,
    ) -> OCRResult:
        self._requests.append(page)
        effective_settings = settings or OCRSettings()
        if self._failure is not None:
            raise OCRProviderError(
                self._failure.code,
                str(self._failure),
                retryable=self._failure.retryable,
            )
        if self._timeout_seconds is not None and self._delay_seconds > self._timeout_seconds:
            raise OCRProviderError(
                OCRProviderErrorCode.TIMEOUT,
                "The fake OCR provider timed out.",
                retryable=True,
            )
        if self._result is None:
            return OCRResult(
                page_number=page.page_number,
                text="",
                blocks=(),
                confidence=0.0,
                settings=effective_settings,
                provider="fake",
            )
        if self._result.page_number != page.page_number:
            raise OCRProviderError(
                OCRProviderErrorCode.INVALID_RESPONSE,
                "Fake OCR result page number does not match the request.",
            )
        if self._result.settings is not effective_settings:
            return replace(self._result, settings=effective_settings)
        return self._result

    def analyze(
        self,
        page: OCRPage,
        *,
        settings: OCRSettings | None = None,
    ) -> OCRResult:
        return self.analyze_page(page, settings=settings)


__all__ = ["FakeOCRProvider"]
