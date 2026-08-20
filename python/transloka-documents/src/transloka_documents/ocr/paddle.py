from __future__ import annotations

from typing import Protocol, runtime_checkable

from .base import OCRHealth, OCRPage, OCRProvider, OCRResult, OCRSettings


@runtime_checkable
class PaddleOCRProvider(OCRProvider, Protocol):
    """Contract for an OCR provider backed by a local PaddleOCR adapter.

    The protocol intentionally contains no Paddle import. M9-T02 can provide
    the local implementation without coupling pipeline code to Paddle types.
    """


@runtime_checkable
class PaddleOCRBackend(Protocol):
    def health_check(self) -> OCRHealth: ...

    def analyze_page(
        self,
        page: OCRPage,
        *,
        settings: OCRSettings,
    ) -> OCRResult: ...
