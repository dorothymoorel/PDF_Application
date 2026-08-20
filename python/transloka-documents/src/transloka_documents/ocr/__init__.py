from .base import (
    OCRBlock,
    OCRGeometry,
    OCRHealth,
    OCRHealthStatus,
    OCRPage,
    OCRPageInput,
    OCRPageResult,
    OCRProvider,
    OCRProviderError,
    OCRProviderErrorCode,
    OCRProviderHealth,
    OCRResult,
    OCRSettings,
    OCRTextBlock,
)
from .fake import FakeOCRProvider
from .paddle import PaddleOCRBackend, PaddleOCRProvider

__all__ = [
    "FakeOCRProvider",
    "OCRBlock",
    "OCRGeometry",
    "OCRHealth",
    "OCRHealthStatus",
    "OCRPage",
    "OCRPageInput",
    "OCRPageResult",
    "OCRProvider",
    "OCRProviderError",
    "OCRProviderErrorCode",
    "OCRProviderHealth",
    "OCRResult",
    "OCRSettings",
    "OCRTextBlock",
    "PaddleOCRBackend",
    "PaddleOCRProvider",
]
