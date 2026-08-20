from __future__ import annotations

import math
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol, runtime_checkable


class OCRHealthStatus(StrEnum):
    AVAILABLE = "AVAILABLE"
    DEGRADED = "DEGRADED"
    UNAVAILABLE = "UNAVAILABLE"


@dataclass(frozen=True, slots=True)
class OCRHealth:
    status: OCRHealthStatus
    provider: str = "ocr"
    version: str | None = None
    detail: str | None = None


class OCRProviderErrorCode(StrEnum):
    TIMEOUT = "TIMEOUT"
    PROVIDER_UNAVAILABLE = "PROVIDER_UNAVAILABLE"
    INVALID_REQUEST = "INVALID_REQUEST"
    INVALID_RESPONSE = "INVALID_RESPONSE"
    OCR_FAILED = "OCR_FAILED"


class OCRProviderError(RuntimeError):
    def __init__(
        self,
        code: OCRProviderErrorCode,
        message: str,
        *,
        retryable: bool | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.retryable = (
            retryable
            if retryable is not None
            else code in {OCRProviderErrorCode.TIMEOUT, OCRProviderErrorCode.PROVIDER_UNAVAILABLE}
        )


@dataclass(frozen=True, slots=True)
class OCRSettings:
    language: str = "en"
    detect_tables: bool = True
    detect_formulas: bool = True
    timeout_seconds: float = 30.0
    low_confidence_threshold: float = 0.75

    def __post_init__(self) -> None:
        if not self.language.strip():
            raise ValueError("OCR language must not be empty.")
        if not math.isfinite(self.timeout_seconds) or self.timeout_seconds <= 0:
            raise ValueError("OCR timeout must be finite and greater than zero.")
        if (
            not math.isfinite(self.low_confidence_threshold)
            or not 0.0 <= self.low_confidence_threshold <= 1.0
        ):
            raise ValueError("OCR confidence threshold must be between 0 and 1.")


@dataclass(frozen=True, slots=True)
class OCRPage:
    page_number: int
    width_px: int
    height_px: int
    image: bytes

    def __post_init__(self) -> None:
        if self.page_number < 1:
            raise ValueError("OCR page number must be at least 1.")
        if self.width_px <= 0 or self.height_px <= 0:
            raise ValueError("OCR page dimensions must be positive.")
        if not self.image:
            raise ValueError("OCR page image must not be empty.")


@dataclass(frozen=True, slots=True)
class OCRGeometry:
    x: float
    y: float
    width: float
    height: float
    coordinate_system: str = "PIXEL_TOP_LEFT"

    def __post_init__(self) -> None:
        values = (self.x, self.y, self.width, self.height)
        if any(not math.isfinite(value) for value in values):
            raise ValueError("OCR geometry values must be finite.")
        if self.x < 0 or self.y < 0 or self.width <= 0 or self.height <= 0:
            raise ValueError("OCR geometry must have non-negative origin and positive size.")
        if not self.coordinate_system.strip():
            raise ValueError("OCR geometry coordinate system must not be empty.")


@dataclass(frozen=True, slots=True)
class OCRTextBlock:
    text: str
    geometry: OCRGeometry
    confidence: float = 0.0

    def __post_init__(self) -> None:
        if not math.isfinite(self.confidence) or not 0.0 <= self.confidence <= 1.0:
            raise ValueError("OCR block confidence must be between 0 and 1.")


@dataclass(frozen=True, slots=True)
class OCRResult:
    page_number: int
    text: str
    blocks: tuple[OCRTextBlock, ...] = ()
    confidence: float = 0.0
    settings: OCRSettings = OCRSettings()
    provider: str = "unknown"

    def __post_init__(self) -> None:
        if self.page_number < 1:
            raise ValueError("OCR result page number must be at least 1.")
        if not math.isfinite(self.confidence) or not 0.0 <= self.confidence <= 1.0:
            raise ValueError("OCR result confidence must be between 0 and 1.")
        if not self.provider.strip():
            raise ValueError("OCR result provider must not be empty.")

    @property
    def is_empty(self) -> bool:
        return not self.text.strip() and not self.blocks

    @property
    def is_low_confidence(self) -> bool:
        return self.confidence < self.settings.low_confidence_threshold

    @property
    def geometry(self) -> OCRGeometry | None:
        if not self.blocks:
            return None
        coordinate_systems = {block.geometry.coordinate_system for block in self.blocks}
        if len(coordinate_systems) != 1:
            raise ValueError("OCR result blocks must use one coordinate system.")
        x = min(block.geometry.x for block in self.blocks)
        y = min(block.geometry.y for block in self.blocks)
        right = max(block.geometry.x + block.geometry.width for block in self.blocks)
        bottom = max(block.geometry.y + block.geometry.height for block in self.blocks)
        return OCRGeometry(
            x=x,
            y=y,
            width=right - x,
            height=bottom - y,
            coordinate_system=next(iter(coordinate_systems)),
        )


@runtime_checkable
class OCRProvider(Protocol):
    def health_check(self) -> OCRHealth: ...

    def analyze_page(
        self,
        page: OCRPage,
        *,
        settings: OCRSettings | None = None,
    ) -> OCRResult: ...


# Compatibility aliases keep the contract readable at call sites that use
# provider-oriented names instead of the shorter OCR names.
OCRProviderHealth = OCRHealth
OCRPageResult = OCRResult
OCRBlock = OCRTextBlock
OCRPageInput = OCRPage
