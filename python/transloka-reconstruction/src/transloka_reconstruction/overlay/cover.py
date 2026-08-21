"""Source-text cover strategies for fixed-layout overlay reconstruction."""

from __future__ import annotations

import io
import math
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from os import PathLike
from pathlib import Path
from statistics import median
from typing import BinaryIO, cast

from pypdf import PdfReader

from .generator import OverlayDependencyError, OverlayPageGenerator
from .types import CoverRegion


class CoverStrategy(StrEnum):
    """Available source-region cover strategies."""

    SOLID_BACKGROUND = "SOLID_BACKGROUND"
    RASTER_BACKGROUND = "RASTER_BACKGROUND"
    PRESERVE_WITH_WARNING = "PRESERVE_WITH_WARNING"


class CoverWarningCode(StrEnum):
    """Stable warning codes emitted when source coverage is uncertain."""

    UNCOVERED_SOURCE_TEXT = "UNCOVERED_SOURCE_TEXT"
    SOURCE_PRESERVED = "SOURCE_PRESERVED"


@dataclass(frozen=True, slots=True)
class CoverWarning:
    """Auditable warning attached to a cover result."""

    code: CoverWarningCode
    message: str
    region_id: str | None = None


@dataclass(frozen=True, slots=True)
class CoverResult:
    """New PDF page plus the strategy and warnings used to create it."""

    pdf_bytes: bytes
    strategy: CoverStrategy
    warnings: tuple[CoverWarning, ...] = ()
    rasterized: bool = False

    @property
    def has_warnings(self) -> bool:
        return bool(self.warnings)

    @property
    def source_text_covered(self) -> bool:
        return not any(
            warning.code
            in {CoverWarningCode.UNCOVERED_SOURCE_TEXT, CoverWarningCode.SOURCE_PRESERVED}
            for warning in self.warnings
        )

    @property
    def pdf(self) -> bytes:
        """Compatibility alias for callers treating the result as a PDF value."""

        return self.pdf_bytes


type SourceInput = bytes | bytearray | BinaryIO | str | PathLike[str]


class SourceTextCover:
    """Apply solid or raster source-text covers without touching the input."""

    def solid_background(
        self,
        source: SourceInput,
        regions: Sequence[CoverRegion],
        *,
        page_index: int = 0,
    ) -> CoverResult:
        values = _regions(regions)
        if not values:
            return self._preserved(source, page_index=page_index)
        geometry_values = _geometry_regions(values)
        output = OverlayPageGenerator().generate(
            source,
            page_index=page_index,
            covers=geometry_values,
        )
        warnings = _coverage_warnings(values, output)
        return CoverResult(output, CoverStrategy.SOLID_BACKGROUND, warnings)

    def raster_background(
        self,
        source: SourceInput,
        regions: Sequence[CoverRegion],
        *,
        page_index: int = 0,
        dpi: float = 144.0,
    ) -> CoverResult:
        values = _regions(regions)
        if not values:
            return self._preserved(source, page_index=page_index)
        output = _raster_fallback(source, values, page_index=page_index, dpi=dpi)
        return CoverResult(output, CoverStrategy.RASTER_BACKGROUND, rasterized=True)

    def cover(
        self,
        source: SourceInput,
        regions: Sequence[CoverRegion],
        *,
        strategy: CoverStrategy = CoverStrategy.SOLID_BACKGROUND,
        page_index: int = 0,
        dpi: float = 144.0,
    ) -> CoverResult:
        """Dispatch one explicit strategy; never silently preserve source text."""

        resolved = _strategy(strategy)
        if resolved is CoverStrategy.SOLID_BACKGROUND:
            return self.solid_background(source, regions, page_index=page_index)
        if resolved is CoverStrategy.RASTER_BACKGROUND:
            return self.raster_background(source, regions, page_index=page_index, dpi=dpi)
        return self._preserved(source, page_index=page_index)

    def _preserved(self, source: SourceInput, *, page_index: int) -> CoverResult:
        source_bytes = _read_bytes(source)
        reader = PdfReader(io.BytesIO(source_bytes), strict=False)
        if page_index < 0 or page_index >= len(reader.pages):
            raise ValueError("page_index must refer to an existing page.")
        writer = PdfReader(io.BytesIO(source_bytes), strict=False)
        page = writer.pages[page_index]
        output = _copy_single_page(page)
        warning = CoverWarning(
            CoverWarningCode.UNCOVERED_SOURCE_TEXT,
            "Source text was preserved because no cover region was supplied.",
        )
        return CoverResult(output, CoverStrategy.PRESERVE_WITH_WARNING, (warning,))


def solid_background_cover(
    source: SourceInput,
    regions: Sequence[CoverRegion],
    *,
    page_index: int = 0,
) -> CoverResult:
    """Convenience wrapper for the solid-background strategy."""

    return SourceTextCover().solid_background(source, regions, page_index=page_index)


def raster_background_fallback(
    source: SourceInput,
    regions: Sequence[CoverRegion],
    *,
    page_index: int = 0,
    dpi: float = 144.0,
) -> CoverResult:
    """Convenience wrapper for raster fallback covering."""

    return SourceTextCover().raster_background(
        source,
        regions,
        page_index=page_index,
        dpi=dpi,
    )


def cover_source_text(
    source: SourceInput,
    regions: Sequence[CoverRegion],
    *,
    strategy: CoverStrategy = CoverStrategy.SOLID_BACKGROUND,
    page_index: int = 0,
    dpi: float = 144.0,
) -> CoverResult:
    """Apply a selected source-text cover strategy."""

    return SourceTextCover().cover(
        source,
        regions,
        strategy=strategy,
        page_index=page_index,
        dpi=dpi,
    )


def _regions(regions: Sequence[CoverRegion]) -> tuple[CoverRegion, ...]:
    values = tuple(regions)
    if any(type(region) is not CoverRegion for region in values):
        raise TypeError("regions must contain CoverRegion values.")
    return values


def _geometry_regions(regions: tuple[CoverRegion, ...]) -> tuple[CoverRegion, ...]:
    """Keep source-text evidence local to verification, not global deletion."""

    return tuple(
        CoverRegion(
            region.x,
            region.y,
            region.width,
            region.height,
            fill_color=region.fill_color,
            region_id=region.region_id,
        )
        for region in regions
    )


def _strategy(value: object) -> CoverStrategy:
    if isinstance(value, CoverStrategy):
        return value
    if type(value) is not str:
        raise ValueError("strategy must be a known cover strategy.")
    try:
        return CoverStrategy(value)
    except ValueError as exc:
        raise ValueError("strategy must be a known cover strategy.") from exc


def _read_bytes(source: SourceInput) -> bytes:
    if isinstance(source, (bytes, bytearray)):
        return bytes(source)
    if isinstance(source, (str, PathLike)):
        return Path(source).read_bytes()
    if hasattr(source, "read"):
        value = source.read()
        if not isinstance(value, bytes):
            raise TypeError("PDF streams must return bytes.")
        return value
    raise TypeError("source must be PDF bytes, a path, or a binary stream.")


def _copy_single_page(page: object) -> bytes:
    from pypdf import PdfWriter

    writer = PdfWriter()
    writer.add_page(page)  # type: ignore[arg-type]
    copied = writer.pages[0]
    for key in ("/Annots", "/AA", "/OpenAction", "/PieceInfo"):
        if key in copied:
            del copied[key]
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()


def _coverage_warnings(
    regions: tuple[CoverRegion, ...],
    output: bytes,
) -> tuple[CoverWarning, ...]:
    extracted = ""
    try:
        extracted = PdfReader(io.BytesIO(output), strict=False).pages[0].extract_text() or ""
    except Exception:
        return (
            CoverWarning(
                CoverWarningCode.UNCOVERED_SOURCE_TEXT,
                "Covered source text could not be verified after writing the PDF.",
            ),
        )
    warnings: list[CoverWarning] = []
    for region in regions:
        if region.source_text and region.source_text in extracted:
            warnings.append(
                CoverWarning(
                    CoverWarningCode.UNCOVERED_SOURCE_TEXT,
                    "The declared source text remains searchable after covering.",
                    region.region_id,
                )
            )
    return tuple(warnings)


def _raster_fallback(
    source: SourceInput,
    regions: tuple[CoverRegion, ...],
    *,
    page_index: int,
    dpi: float,
) -> bytes:
    if isinstance(dpi, bool) or not isinstance(dpi, (int, float)):
        raise ValueError("dpi must be a finite positive number.")
    scale = float(dpi) / 72.0
    if not math.isfinite(scale) or scale <= 0:
        raise ValueError("dpi must be a finite positive number.")
    try:
        import pypdfium2 as pdfium  # type: ignore[import-untyped]
        from PIL import Image, ImageDraw
        from reportlab.lib.utils import ImageReader  # type: ignore[import-untyped]
        from reportlab.pdfgen.canvas import Canvas  # type: ignore[import-untyped]
    except ImportError as exc:
        raise OverlayDependencyError(
            "Raster fallback requires pypdfium2, Pillow, and ReportLab."
        ) from exc

    document = pdfium.PdfDocument(_read_bytes(source))
    if page_index < 0 or page_index >= len(document):
        raise ValueError("page_index must refer to an existing page.")
    page = document[page_index]
    page_width, page_height = page.get_size()
    image = page.render(scale=scale).to_pil().convert("RGB")
    draw = ImageDraw.Draw(image)
    for region in regions:
        left = round(region.x * scale)
        right = round(region.right * scale)
        top = round((page_height - region.top) * scale)
        bottom = round((page_height - region.y) * scale)
        fill = _sample_background(image, (left, top, right, bottom), region.fill_color)
        draw.rectangle((left, top, right, bottom), fill=fill)

    # pypdfium2 returns top-left image coordinates; ReportLab places the first
    # image row at the bottom of the PDF page.
    flipped = image.transpose(Image.Transpose.FLIP_TOP_BOTTOM)
    output = io.BytesIO()
    canvas = cast(object, Canvas(output, pagesize=(page_width, page_height), pageCompression=1))
    canvas.drawImage(  # type: ignore[attr-defined]
        ImageReader(flipped),
        0,
        0,
        width=page_width,
        height=page_height,
        preserveAspectRatio=False,
        mask="auto",
    )
    canvas.showPage()  # type: ignore[attr-defined]
    canvas.save()  # type: ignore[attr-defined]
    return output.getvalue()


def _sample_background(
    image: object,
    bounds: tuple[int, int, int, int],
    fallback: tuple[float, float, float],
) -> tuple[int, int, int]:
    width = image.width  # type: ignore[attr-defined]
    height = image.height  # type: ignore[attr-defined]
    left, top, right, bottom = bounds
    samples: list[tuple[int, int, int]] = []
    for x in range(max(0, left - 2), min(width, right + 3)):
        for y in (max(0, top - 2), min(height - 1, bottom + 2)):
            pixel = image.getpixel((x, y))  # type: ignore[attr-defined]
            if isinstance(pixel, tuple) and len(pixel) >= 3:
                samples.append((int(pixel[0]), int(pixel[1]), int(pixel[2])))
    for y in range(max(0, top - 2), min(height, bottom + 3)):
        for x in (max(0, left - 2), min(width - 1, right + 2)):
            pixel = image.getpixel((x, y))  # type: ignore[attr-defined]
            if isinstance(pixel, tuple) and len(pixel) >= 3:
                samples.append((int(pixel[0]), int(pixel[1]), int(pixel[2])))
    if samples:
        return (
            int(median(sample[0] for sample in samples)),
            int(median(sample[1] for sample in samples)),
            int(median(sample[2] for sample in samples)),
        )
    return tuple(round(channel * 255) for channel in fallback)  # type: ignore[return-value]
