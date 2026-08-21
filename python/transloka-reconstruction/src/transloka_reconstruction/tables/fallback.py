"""Safe image fallback for tables outside simple reconstruction scope."""

from __future__ import annotations

import hashlib
import math
import os
from dataclasses import dataclass
from enum import StrEnum
from io import BytesIO
from pathlib import Path
from typing import cast

from PIL import Image, UnidentifiedImageError

from transloka_reconstruction.assets import (
    CaptionPlacement,
    CaptionRelation,
    CaptionSpec,
    ImageAsset,
    ImageFit,
    ImagePlacement,
    ImagePosition,
    ImageRect,
    preserve_image,
)

from .models import TableError, TableRect


class ComplexTableFallbackError(TableError):
    """Base error for invalid complex-table fallback input."""


class ComplexTableKind(StrEnum):
    """Reasons a table is not safe for editable reconstruction."""

    NESTED = "NESTED"
    IRREGULAR = "IRREGULAR"
    DIAGRAM_LIKE = "DIAGRAM_LIKE"
    MERGED = "MERGED"
    UNKNOWN = "UNKNOWN"


class FallbackStrategy(StrEnum):
    """Explicit strategy marker persisted in the result."""

    PRESERVE_AS_IMAGE = "PRESERVE_AS_IMAGE"
    MANUAL_REVIEW = "MANUAL_REVIEW"


class FallbackWarningCode(StrEnum):
    """Stable warning codes for complex-table fallback decisions."""

    COMPLEX_TABLE_PRESERVED_AS_IMAGE = "COMPLEX_TABLE_PRESERVED_AS_IMAGE"
    TABLE_IMAGE_MISSING = "TABLE_IMAGE_MISSING"
    TABLE_IMAGE_INVALID = "TABLE_IMAGE_INVALID"
    CAPTION_NOT_TRANSLATED = "CAPTION_NOT_TRANSLATED"


class FallbackWarningSeverity(StrEnum):
    INFO = "INFO"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


def _text(value: object, field_name: str) -> str:
    if type(value) is not str or not value.strip():
        raise ComplexTableFallbackError(f"{field_name} must be a non-empty string.")
    return value


def _finite(value: object, field_name: str, *, positive: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ComplexTableFallbackError(f"{field_name} must be a finite number.")
    converted = float(value)
    if not math.isfinite(converted) or (positive and converted <= 0):
        qualifier = "positive " if positive else ""
        raise ComplexTableFallbackError(f"{field_name} must be a finite {qualifier}number.")
    return converted


@dataclass(frozen=True, slots=True)
class FallbackWarning:
    """One auditable reason the fallback was selected or degraded."""

    code: FallbackWarningCode
    message: str
    severity: FallbackWarningSeverity
    table_id: str
    page_id: str


@dataclass(frozen=True, slots=True)
class ComplexTableFallbackRequest:
    """Input required to preserve a complex table as its source image."""

    table_id: str
    page_id: str
    source: bytes | bytearray | memoryview | str | os.PathLike[str] | Image.Image | None
    kind: ComplexTableKind | str = ComplexTableKind.UNKNOWN
    target: TableRect | None = None
    source_width_px: int | None = None
    source_height_px: int | None = None
    caption_source: str | None = None
    caption_translation: str | None = None
    caption_relation: CaptionRelation | str = CaptionRelation.BELOW
    caption_block_id: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "table_id", _text(self.table_id, "table_id"))
        object.__setattr__(self, "page_id", _text(self.page_id, "page_id"))
        if not isinstance(self.kind, ComplexTableKind):
            try:
                object.__setattr__(self, "kind", ComplexTableKind(self.kind))
            except ValueError as exc:
                raise ComplexTableFallbackError("kind must be a known complex table kind.") from exc
        if self.source_width_px is not None:
            if isinstance(self.source_width_px, bool) or not isinstance(self.source_width_px, int):
                raise ComplexTableFallbackError("source_width_px must be a positive integer.")
            if self.source_width_px <= 0:
                raise ComplexTableFallbackError("source_width_px must be a positive integer.")
        if self.source_height_px is not None:
            if isinstance(self.source_height_px, bool) or not isinstance(
                self.source_height_px, int
            ):
                raise ComplexTableFallbackError("source_height_px must be a positive integer.")
            if self.source_height_px <= 0:
                raise ComplexTableFallbackError("source_height_px must be a positive integer.")
        if self.caption_source is not None:
            object.__setattr__(self, "caption_source", _text(self.caption_source, "caption_source"))
        if self.caption_translation is not None:
            object.__setattr__(
                self,
                "caption_translation",
                _text(self.caption_translation, "caption_translation"),
            )
        if not isinstance(self.caption_relation, CaptionRelation):
            try:
                object.__setattr__(self, "caption_relation", CaptionRelation(self.caption_relation))
            except ValueError as exc:
                raise ComplexTableFallbackError(
                    "caption_relation must be a known caption relation."
                ) from exc
        if self.caption_block_id is not None:
            object.__setattr__(
                self, "caption_block_id", _text(self.caption_block_id, "caption_block_id")
            )


@dataclass(frozen=True, slots=True)
class ComplexTableFallbackResult:
    """Image-preserved result; ``reconstructed`` is always false by contract."""

    table_id: str
    page_id: str
    kind: ComplexTableKind
    strategy: FallbackStrategy
    image_data: bytes | None
    mime_type: str | None
    width_px: int | None
    height_px: int | None
    checksum_sha256: str | None
    target: TableRect | None
    placement: ImagePlacement | None
    caption: CaptionPlacement | None
    caption_text: str | None
    caption_translated: bool
    warnings: tuple[FallbackWarning, ...]
    reconstructed: bool = False

    @property
    def preserved_as_image(self) -> bool:
        return self.image_data is not None and self.strategy is FallbackStrategy.PRESERVE_AS_IMAGE

    @property
    def claims_reconstructed(self) -> bool:
        """Guard used by export code and tests against a false success claim."""

        return self.reconstructed

    @property
    def complete(self) -> bool:
        return self.preserved_as_image and not any(
            warning.severity is FallbackWarningSeverity.CRITICAL for warning in self.warnings
        )


class ComplexTableFallback:
    """Preserve complex table bytes and metadata without editable reflow."""

    def preserve(self, request: ComplexTableFallbackRequest) -> ComplexTableFallbackResult:
        warnings: list[FallbackWarning] = [
            FallbackWarning(
                code=FallbackWarningCode.COMPLEX_TABLE_PRESERVED_AS_IMAGE,
                message=(
                    "Complex table was preserved as an image; editable reconstruction was not claimed."
                ),
                severity=FallbackWarningSeverity.INFO,
                table_id=request.table_id,
                page_id=request.page_id,
            )
        ]
        caption_text, caption_translated, caption_warning = _caption_state(request)
        if caption_warning is not None:
            warnings.append(caption_warning)

        raw = _read_source(request.source)
        if raw is None:
            warnings.append(
                _fallback_warning(
                    request,
                    FallbackWarningCode.TABLE_IMAGE_MISSING,
                    "Complex table image is missing; no synthetic replacement was generated.",
                    FallbackWarningSeverity.CRITICAL,
                )
            )
            return ComplexTableFallbackResult(
                table_id=request.table_id,
                page_id=request.page_id,
                kind=cast(ComplexTableKind, request.kind),
                strategy=FallbackStrategy.PRESERVE_AS_IMAGE,
                image_data=None,
                mime_type=None,
                width_px=None,
                height_px=None,
                checksum_sha256=None,
                target=request.target,
                placement=None,
                caption=None,
                caption_text=caption_text,
                caption_translated=caption_translated,
                warnings=tuple(warnings),
            )

        try:
            width_px, height_px, mime_type = _inspect_image(raw)
        except (OSError, UnidentifiedImageError, ValueError):
            warnings.append(
                _fallback_warning(
                    request,
                    FallbackWarningCode.TABLE_IMAGE_INVALID,
                    "Complex table source is not a supported readable image.",
                    FallbackWarningSeverity.CRITICAL,
                )
            )
            return ComplexTableFallbackResult(
                table_id=request.table_id,
                page_id=request.page_id,
                kind=cast(ComplexTableKind, request.kind),
                strategy=FallbackStrategy.PRESERVE_AS_IMAGE,
                image_data=None,
                mime_type=None,
                width_px=None,
                height_px=None,
                checksum_sha256=None,
                target=request.target,
                placement=None,
                caption=None,
                caption_text=caption_text,
                caption_translated=caption_translated,
                warnings=tuple(warnings),
            )

        target = request.target or TableRect(0, 0, width_px, height_px)
        caption_spec = _caption_spec(request, caption_text)
        placement = preserve_image(
            ImageAsset(
                asset_id=request.table_id,
                page_id=request.page_id,
                width_px=width_px,
                height_px=height_px,
                source=raw,
            ),
            ImageRect(target.x, target.y, target.width, target.height),
            fit=ImageFit.CONTAIN,
            position=ImagePosition.CENTER,
            caption=caption_spec,
        )
        return ComplexTableFallbackResult(
            table_id=request.table_id,
            page_id=request.page_id,
            kind=cast(ComplexTableKind, request.kind),
            strategy=FallbackStrategy.PRESERVE_AS_IMAGE,
            image_data=raw,
            mime_type=mime_type,
            width_px=width_px,
            height_px=height_px,
            checksum_sha256=hashlib.sha256(raw).hexdigest(),
            target=target,
            placement=placement,
            caption=placement.caption,
            caption_text=caption_text,
            caption_translated=caption_translated,
            warnings=tuple(warnings),
        )


ComplexTableFallbackEngine = ComplexTableFallback


def _fallback_warning(
    request: ComplexTableFallbackRequest,
    code: FallbackWarningCode,
    message: str,
    severity: FallbackWarningSeverity,
) -> FallbackWarning:
    return FallbackWarning(
        code=code,
        message=message,
        severity=severity,
        table_id=request.table_id,
        page_id=request.page_id,
    )


def _read_source(source: object | None) -> bytes | None:
    if source is None:
        return None
    if isinstance(source, bytes):
        return source
    if isinstance(source, (bytearray, memoryview)):
        return bytes(source)
    if isinstance(source, (str, os.PathLike)):
        try:
            return Path(source).read_bytes()
        except (FileNotFoundError, IsADirectoryError, OSError):
            return None
    if isinstance(source, Image.Image):
        output = BytesIO()
        source.save(output, format="PNG", optimize=False, compress_level=9)
        return output.getvalue()
    return None


def _inspect_image(raw: bytes) -> tuple[int, int, str]:
    with Image.open(BytesIO(raw)) as image:
        image.load()
        width, height = image.size
        image_format = (image.format or "").upper()
    mime_types = {"PNG": "image/png", "JPEG": "image/jpeg"}
    if image_format not in mime_types or width <= 0 or height <= 0:
        raise ValueError("Only PNG and JPEG table fallback images are supported.")
    return width, height, mime_types[image_format]


def _caption_state(
    request: ComplexTableFallbackRequest,
) -> tuple[str | None, bool, FallbackWarning | None]:
    if request.caption_translation is not None:
        return request.caption_translation, True, None
    if request.caption_source is None:
        return None, False, None
    return (
        request.caption_source,
        False,
        _fallback_warning(
            request,
            FallbackWarningCode.CAPTION_NOT_TRANSLATED,
            "Caption translation was unavailable; source caption was retained.",
            FallbackWarningSeverity.WARNING,
        ),
    )


def _caption_spec(
    request: ComplexTableFallbackRequest,
    caption_text: str | None,
) -> CaptionSpec | None:
    if caption_text is None or request.caption_relation is CaptionRelation.NONE:
        return None
    return CaptionSpec(
        caption_text,
        relation=cast(CaptionRelation, request.caption_relation),
        block_id=request.caption_block_id,
    )


def preserve_complex_table_as_image(
    request: ComplexTableFallbackRequest,
) -> ComplexTableFallbackResult:
    """Convenience wrapper for :meth:`ComplexTableFallback.preserve`."""

    return ComplexTableFallback().preserve(request)


fallback_complex_table = preserve_complex_table_as_image
