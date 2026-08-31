"""ReportLab overlay rendering and pypdf page composition."""

from __future__ import annotations

import io
import math
from collections.abc import Sequence
from os import PathLike
from pathlib import Path
from typing import BinaryIO, Protocol, cast

from pypdf import PdfReader, PdfWriter
from pypdf._page import PageObject
from pypdf.generic import ContentStream

from .types import CoverRegion, OverlayText, TextAlignment


class OverlayError(ValueError):
    """Base error for invalid or unsafe overlay requests."""


class OverlayDependencyError(OverlayError):
    """Raised when the optional ReportLab renderer is unavailable."""


class OverlayLayoutError(OverlayError):
    """Raised when translated text cannot fit its declared region."""


class _Canvas(Protocol):
    def saveState(self) -> None: ...

    def restoreState(self) -> None: ...

    def setFillColorRGB(self, red: float, green: float, blue: float) -> None: ...

    def setFillAlpha(self, alpha: float) -> None: ...

    def rect(
        self, x: float, y: float, width: float, height: float, fill: int, stroke: int
    ) -> None: ...

    def setFont(self, name: str, size: float) -> None: ...

    def drawString(self, x: float, y: float, text: str) -> None: ...

    def stringWidth(self, text: str, name: str, size: float) -> float: ...

    def showPage(self) -> None: ...

    def save(self) -> None: ...


type SourceInput = bytes | bytearray | BinaryIO | str | PathLike[str]


class OverlayPageGenerator:
    """Generate one safe overlay page without modifying the source input."""

    def build_overlay(
        self,
        page_width: float,
        page_height: float,
        *,
        texts: Sequence[OverlayText] = (),
        covers: Sequence[CoverRegion] = (),
    ) -> bytes:
        """Render transparent page content with covers and selectable text."""

        width = _positive(page_width, "page_width")
        height = _positive(page_height, "page_height")
        values = tuple(texts)
        cover_values = tuple(covers)
        if any(type(text) is not OverlayText for text in values):
            raise TypeError("texts must contain OverlayText values.")
        if any(type(cover) is not CoverRegion for cover in cover_values):
            raise TypeError("covers must contain CoverRegion values.")

        return _render_canvas(width, height, values, cover_values)

    def generate(
        self,
        source: SourceInput,
        *,
        page_index: int = 0,
        texts: Sequence[OverlayText] = (),
        covers: Sequence[CoverRegion] = (),
    ) -> bytes:
        """Copy, sanitize, cover, overlay, and return a new one-page PDF."""

        reader = PdfReader(_source_stream(source), strict=False)
        index = _page_index(page_index, len(reader.pages))
        writer = PdfWriter()
        writer.add_page(reader.pages[index])
        page = writer.pages[0]
        _sanitize_page(page)
        cover_values = tuple(covers)
        _remove_covered_text(page, cover_values, reader)
        page_width, page_height = _page_dimensions(page)
        overlay_pdf = self.build_overlay(
            page_width,
            page_height,
            texts=texts,
            covers=cover_values,
        )
        overlay_page = PdfReader(io.BytesIO(overlay_pdf), strict=False).pages[0]
        _assert_same_dimensions(page, overlay_page)
        page.merge_page(overlay_page)
        return _writer_bytes(writer)

    def merge(
        self,
        source: SourceInput,
        overlay: SourceInput,
        *,
        page_index: int = 0,
        covers: Sequence[CoverRegion] = (),
    ) -> bytes:
        """Merge an already-rendered overlay onto a sanitized source page."""

        source_reader = PdfReader(_source_stream(source), strict=False)
        overlay_reader = PdfReader(_source_stream(overlay), strict=False)
        index = _page_index(page_index, len(source_reader.pages))
        if not overlay_reader.pages:
            raise OverlayError("overlay PDF must contain at least one page.")
        writer = PdfWriter()
        writer.add_page(source_reader.pages[index])
        page = writer.pages[0]
        _sanitize_page(page)
        cover_values = tuple(covers)
        if any(type(cover) is not CoverRegion for cover in cover_values):
            raise TypeError("covers must contain CoverRegion values.")
        _remove_covered_text(page, cover_values, source_reader)
        overlay_page = overlay_reader.pages[0]
        _assert_same_dimensions(page, overlay_page)
        page.merge_page(overlay_page)
        return _writer_bytes(writer)

    def _draw_text(self, canvas: _Canvas, text: OverlayText) -> None:
        from reportlab.pdfbase.pdfmetrics import getDescent  # type: ignore[import-untyped]

        canvas.saveState()
        canvas.setFillColorRGB(*text.color)
        canvas.setFont(text.font_name, text.font_size_pt)
        leading = text.leading_pt or text.font_size_pt * 1.2
        lines = _wrap_text(canvas, text)
        required_height = text.font_size_pt + (len(lines) - 1) * leading
        if text.height is not None and required_height > text.height + 0.01:
            raise OverlayLayoutError(
                f"Text {text.text_id or '<anonymous>'} exceeds its declared height."
            )
        baseline = (
            text.y + text.height - text.font_size_pt - getDescent(text.font_name, text.font_size_pt)
            if text.height is not None
            else text.y
        )
        for line in lines:
            line_width = canvas.stringWidth(line, text.font_name, text.font_size_pt)
            if text.width is not None and line_width > text.width + 0.01:
                raise OverlayLayoutError(
                    f"Text {text.text_id or '<anonymous>'} exceeds its declared width."
                )
            offset = 0.0
            if text.width is not None and text.alignment is TextAlignment.CENTER:
                offset = (text.width - line_width) / 2
            elif text.width is not None and text.alignment is TextAlignment.RIGHT:
                offset = text.width - line_width
            canvas.drawString(text.x + offset, baseline, line)
            baseline -= leading
        canvas.restoreState()


def generate_overlay_page(
    source: SourceInput,
    *,
    page_index: int = 0,
    texts: Sequence[OverlayText] = (),
    covers: Sequence[CoverRegion] = (),
) -> bytes:
    """Convenience wrapper for :class:`OverlayPageGenerator.generate`."""

    return OverlayPageGenerator().generate(
        source,
        page_index=page_index,
        texts=texts,
        covers=covers,
    )


def merge_overlay_page(
    source: SourceInput,
    overlay: SourceInput,
    *,
    page_index: int = 0,
    covers: Sequence[CoverRegion] = (),
) -> bytes:
    """Convenience wrapper for merging an overlay PDF onto a source page."""

    return OverlayPageGenerator().merge(
        source,
        overlay,
        page_index=page_index,
        covers=covers,
    )


def _render_canvas(
    width: float,
    height: float,
    texts: Sequence[OverlayText],
    covers: Sequence[CoverRegion],
) -> bytes:
    try:
        from reportlab.pdfgen.canvas import Canvas  # type: ignore[import-untyped]
    except ImportError as exc:
        raise OverlayDependencyError(
            "ReportLab is required for overlay generation. Install the reconstruction extras."
        ) from exc
    output = io.BytesIO()
    canvas = cast(_Canvas, Canvas(output, pagesize=(width, height), pageCompression=1))
    for cover in covers:
        canvas.saveState()
        canvas.setFillColorRGB(*cover.fill_color)
        canvas.rect(cover.x, cover.y, cover.width, cover.height, fill=1, stroke=0)
        canvas.restoreState()
    for text in texts:
        # Draw through the same implementation used by the public builder.
        OverlayPageGenerator()._draw_text(canvas, text)
    canvas.showPage()
    canvas.save()
    return output.getvalue()


def _positive(value: float, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise OverlayError(f"{field_name} must be a finite positive number.")
    converted = float(value)
    if not math.isfinite(converted) or converted <= 0:
        raise OverlayError(f"{field_name} must be a finite positive number.")
    return converted


def _page_index(value: int, page_count: int) -> int:
    if type(value) is not int or value < 0 or value >= page_count:
        raise OverlayError("page_index must refer to an existing page.")
    return value


def _source_stream(source: SourceInput) -> BinaryIO:
    if isinstance(source, (bytes, bytearray)):
        return io.BytesIO(bytes(source))
    if isinstance(source, (str, PathLike)):
        return Path(source).open("rb")
    if hasattr(source, "read"):
        return source
    raise TypeError("source must be PDF bytes, a path, or a binary stream.")


def _writer_bytes(writer: PdfWriter) -> bytes:
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()


def _page_dimensions(page: PageObject) -> tuple[float, float]:
    mediabox = page.mediabox
    width = float(mediabox.width)
    height = float(mediabox.height)
    return _positive(width, "page width"), _positive(height, "page height")


def _assert_same_dimensions(first: PageObject, second: PageObject) -> None:
    first_width, first_height = _page_dimensions(first)
    second_width, second_height = _page_dimensions(second)
    if not math.isclose(first_width, second_width, abs_tol=0.01) or not math.isclose(
        first_height,
        second_height,
        abs_tol=0.01,
    ):
        raise OverlayError("Overlay and source page dimensions must match.")


def _sanitize_page(page: PageObject) -> None:
    # A fresh writer prevents catalog-level actions from being copied.  Page
    # annotations and additional actions are removed explicitly as well.
    for key in ("/Annots", "/AA", "/OpenAction", "/PieceInfo"):
        if key in page:
            del page[key]


def _wrap_text(canvas: _Canvas, text: OverlayText) -> tuple[str, ...]:
    normalized = text.text.replace("\r\n", "\n").replace("\r", "\n")
    paragraphs = normalized.split("\n")
    if text.width is None:
        return tuple(paragraphs)
    lines = _wrap_paragraphs(canvas, text, paragraphs)
    if text.height is None or len(paragraphs) < 2 or any(not item.strip() for item in paragraphs):
        return lines
    leading = text.leading_pt or text.font_size_pt * 1.2
    maximum_lines = max(1, math.floor((text.height - text.font_size_pt + 0.01) / leading) + 1)
    if len(lines) <= maximum_lines:
        return lines
    rebalanced = _wrap_paragraphs(canvas, text, (" ".join(paragraphs),))
    return rebalanced if len(rebalanced) <= maximum_lines else lines


def _wrap_paragraphs(
    canvas: _Canvas,
    text: OverlayText,
    paragraphs: Sequence[str],
) -> tuple[str, ...]:
    assert text.width is not None
    lines: list[str] = []
    for paragraph in paragraphs:
        words = paragraph.split()
        if not words:
            lines.append("")
            continue
        current = words[0]
        for word in words[1:]:
            candidate = f"{current} {word}"
            if canvas.stringWidth(candidate, text.font_name, text.font_size_pt) <= text.width:
                current = candidate
            else:
                lines.append(current)
                current = word
        if canvas.stringWidth(current, text.font_name, text.font_size_pt) > text.width:
            raise OverlayLayoutError(
                f"Text {text.text_id or '<anonymous>'} contains a word wider than its box."
            )
        lines.append(current)
    return tuple(lines)


def _remove_covered_text(
    page: PageObject,
    covers: Sequence[CoverRegion],
    reader: PdfReader,
) -> None:
    if not covers:
        return
    contents = page.get_contents()
    if contents is None:
        return
    content = ContentStream(contents, reader)
    content.operations = _filtered_operations(content.operations, tuple(covers))
    page.replace_contents(content)


def _filtered_operations(
    operations: list[tuple[list[object], bytes]],
    covers: tuple[CoverRegion, ...],
) -> list[tuple[list[object], bytes]]:
    text_matrix = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)
    line_matrix = text_matrix
    ctm = text_matrix
    ctm_stack: list[tuple[float, float, float, float, float, float]] = []
    leading = 0.0
    filtered: list[tuple[list[object], bytes]] = []
    for operands, operator in operations:
        name = operator.decode("latin-1")
        if name == "q":
            ctm_stack.append(ctm)
        elif name == "Q" and ctm_stack:
            ctm = ctm_stack.pop()
        elif name == "cm" and len(operands) == 6:
            values = _matrix_values(operands)
            if values is not None:
                ctm = _matrix_multiply(ctm, values)
        elif name == "BT":
            text_matrix = line_matrix = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)
        elif name == "Tm" and len(operands) == 6:
            values = _matrix_values(operands)
            if values is not None:
                text_matrix = line_matrix = values
        elif name in {"Td", "TD"} and len(operands) == 2:
            tx, ty = _number(operands[0]), _number(operands[1])
            if name == "TD":
                leading = -ty
            line_matrix = _translate(line_matrix, tx, ty)
            text_matrix = line_matrix
        elif name == "TL" and operands:
            leading = _number(operands[0])
        elif name == "T*":
            line_matrix = _translate(line_matrix, 0.0, -leading)
            text_matrix = line_matrix

        show_operands = _show_operands(name, operands)
        if show_operands is not None:
            if name in {"'", '"'}:
                line_matrix = _translate(line_matrix, 0.0, -leading)
                text_matrix = line_matrix
            point = _transform_point(ctm, text_matrix[4], text_matrix[5])
            source_text = _show_text(show_operands)
            if _covered(point[0], point[1], source_text, covers):
                continue
        filtered.append((operands, operator))
    return filtered


def _show_operands(name: str, operands: list[object]) -> list[object] | None:
    if name in {"Tj", "TJ", "'"}:
        return operands
    if name == '"':
        return operands[-1:] if operands else None
    return None


def _show_text(operands: list[object]) -> str:
    values: list[str] = []
    for operand in operands:
        if isinstance(operand, (list, tuple)):
            values.append(_show_text(list(operand)))
        elif isinstance(operand, (str, bytes)):
            values.append(operand.decode("latin-1") if isinstance(operand, bytes) else operand)
    return "".join(values)


def _covered(x: float, y: float, source_text: str, covers: tuple[CoverRegion, ...]) -> bool:
    return any(
        cover.contains_point(x, y)
        or (cover.source_text is not None and cover.source_text in source_text)
        for cover in covers
    )


def _translate(
    matrix: tuple[float, float, float, float, float, float],
    tx: float,
    ty: float,
) -> tuple[float, float, float, float, float, float]:
    a, b, c, d, e, f = matrix
    return (a, b, c, d, e + tx * a + ty * c, f + tx * b + ty * d)


def _matrix_multiply(
    first: tuple[float, float, float, float, float, float],
    second: tuple[float, float, float, float, float, float],
) -> tuple[float, float, float, float, float, float]:
    a, b, c, d, e, f = first
    g, h, i, j, k, last_translation_y = second
    return (
        a * g + c * h,
        b * g + d * h,
        a * i + c * j,
        b * i + d * j,
        a * k + c * last_translation_y + e,
        b * k + d * last_translation_y + f,
    )


def _number(value: object) -> float:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return float(value)
    raise OverlayError("PDF content contains a non-numeric geometry operand.")


def _matrix_values(
    values: list[object],
) -> tuple[float, float, float, float, float, float] | None:
    if len(values) != 6:
        return None
    return (
        _number(values[0]),
        _number(values[1]),
        _number(values[2]),
        _number(values[3]),
        _number(values[4]),
        _number(values[5]),
    )


def _transform_point(
    matrix: tuple[float, float, float, float, float, float],
    x: float,
    y: float,
) -> tuple[float, float]:
    a, b, c, d, e, f = matrix
    return (a * x + c * y + e, b * x + d * y + f)
