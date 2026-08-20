"""Deterministic text measurement for reconstruction layout decisions."""

from __future__ import annotations

import math
import re
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from transloka_reconstruction.fonts import FontDescriptor, FontResolution


class FontMetrics(Protocol):
    """Minimal actual-font interface needed by the measurement engine."""

    def getlength(self, text: str) -> float:
        """Return the advance width of ``text`` in points."""

    def getbbox(self, text: str) -> tuple[float, float, float, float] | None:
        """Return the ink bounding box of ``text`` in points."""


@dataclass(frozen=True, slots=True)
class TextStyle:
    """Style and spacing inputs used for one text run."""

    font_size_pt: float = 12.0
    bold: bool = False
    italic: bool = False
    line_height_multiplier: float = 1.2
    paragraph_spacing_pt: float = 0.0

    def __post_init__(self) -> None:
        if isinstance(self.font_size_pt, bool) or not isinstance(self.font_size_pt, (int, float)):
            raise ValueError("font_size_pt must be a finite positive number.")
        if not math.isfinite(float(self.font_size_pt)) or self.font_size_pt <= 0:
            raise ValueError("font_size_pt must be a finite positive number.")
        for field_name in ("bold", "italic"):
            if type(getattr(self, field_name)) is not bool:
                raise ValueError(f"{field_name} must be a boolean.")
        if (
            isinstance(self.line_height_multiplier, bool)
            or not isinstance(self.line_height_multiplier, (int, float))
            or not math.isfinite(float(self.line_height_multiplier))
            or self.line_height_multiplier < 1.0
        ):
            raise ValueError("line_height_multiplier must be finite and at least 1.0.")
        if (
            isinstance(self.paragraph_spacing_pt, bool)
            or not isinstance(self.paragraph_spacing_pt, (int, float))
            or not math.isfinite(float(self.paragraph_spacing_pt))
            or self.paragraph_spacing_pt < 0
        ):
            raise ValueError("paragraph_spacing_pt must be finite and non-negative.")
        object.__setattr__(self, "font_size_pt", float(self.font_size_pt))
        object.__setattr__(self, "line_height_multiplier", float(self.line_height_multiplier))
        object.__setattr__(self, "paragraph_spacing_pt", float(self.paragraph_spacing_pt))


@dataclass(frozen=True, slots=True)
class TextMeasurement:
    """Measured output geometry and the exact lines used to calculate it."""

    text: str
    font: FontDescriptor
    style: TextStyle
    lines: tuple[str, ...]
    width_pt: float
    height_pt: float
    line_height_pt: float
    line_count: int
    paragraph_count: int
    available_width_pt: float | None

    @property
    def wrapped(self) -> bool:
        return len(self.lines) > self.text.replace("\r\n", "\n").replace("\r", "\n").count("\n") + 1

    @property
    def font_family(self) -> str:
        return self.font.family_name

    def to_dict(self) -> dict[str, object]:
        """Return a stable JSON-compatible measurement snapshot."""

        return {
            "font_family": self.font.family_name,
            "font_size_pt": self.style.font_size_pt,
            "bold": self.style.bold,
            "italic": self.style.italic,
            "lines": list(self.lines),
            "width_pt": self.width_pt,
            "height_pt": self.height_pt,
            "line_height_pt": self.line_height_pt,
            "line_count": self.line_count,
            "paragraph_count": self.paragraph_count,
            "available_width_pt": self.available_width_pt,
        }


FontInput = FontDescriptor | FontResolution | str
FontLoader = Callable[[FontDescriptor, TextStyle], FontMetrics]


class TextMeasurer:
    """Measure text with the selected output font and deterministic wrapping."""

    def __init__(self, font_loader: FontLoader | None = None) -> None:
        self._font_loader = font_loader or _load_actual_font

    def measure(
        self,
        text: str,
        *,
        font: FontInput,
        style: TextStyle | None = None,
        font_size_pt: float | None = None,
        max_width_pt: float | None = None,
        bold: bool | None = None,
        italic: bool | None = None,
        line_height_multiplier: float | None = None,
        paragraph_spacing_pt: float | None = None,
    ) -> TextMeasurement:
        """Measure text, preserving explicit line breaks and source content."""

        if type(text) is not str:
            raise ValueError("text must be a string.")
        descriptor = _font_descriptor(font)
        base_style = style or TextStyle()
        resolved_style = _override_style(
            base_style,
            font_size_pt=font_size_pt,
            bold=bold,
            italic=italic,
            line_height_multiplier=line_height_multiplier,
            paragraph_spacing_pt=paragraph_spacing_pt,
        )
        if max_width_pt is not None:
            _positive_finite(max_width_pt, "max_width_pt")

        metrics = self._font_loader(descriptor, resolved_style)
        normalized_text = text.replace("\r\n", "\n").replace("\r", "\n")
        paragraphs = normalized_text.split("\n")
        lines: list[str] = []
        for paragraph in paragraphs:
            lines.extend(_wrap_paragraph(paragraph, metrics, max_width_pt))
        if not lines:
            lines.append("")

        widths = tuple(_width(metrics, line) for line in lines)
        width_pt = max(widths, default=0.0)
        ink_height = _ink_height(metrics, resolved_style.font_size_pt)
        line_height_pt = max(
            ink_height,
            resolved_style.font_size_pt * resolved_style.line_height_multiplier,
        )
        paragraph_spacing = max(0, len(paragraphs) - 1) * resolved_style.paragraph_spacing_pt
        height_pt = len(lines) * line_height_pt + paragraph_spacing
        return TextMeasurement(
            text=text,
            font=descriptor,
            style=resolved_style,
            lines=tuple(lines),
            width_pt=width_pt,
            height_pt=height_pt,
            line_height_pt=line_height_pt,
            line_count=len(lines),
            paragraph_count=len(paragraphs),
            available_width_pt=max_width_pt,
        )


TextMeasurementEngine = TextMeasurer


def measure_text(
    text: str,
    *,
    font: FontInput,
    style: TextStyle | None = None,
    font_size_pt: float | None = None,
    max_width_pt: float | None = None,
    bold: bool | None = None,
    italic: bool | None = None,
    line_height_multiplier: float | None = None,
    paragraph_spacing_pt: float | None = None,
) -> TextMeasurement:
    """Convenience wrapper using the default actual-font loader."""

    return TextMeasurer().measure(
        text,
        font=font,
        style=style,
        font_size_pt=font_size_pt,
        max_width_pt=max_width_pt,
        bold=bold,
        italic=italic,
        line_height_multiplier=line_height_multiplier,
        paragraph_spacing_pt=paragraph_spacing_pt,
    )


def _font_descriptor(font: FontInput) -> FontDescriptor:
    if isinstance(font, FontResolution):
        return font.font
    if isinstance(font, FontDescriptor):
        return font
    if type(font) is str and font.strip():
        return FontDescriptor(family_name=font.strip())
    raise TypeError("font must be a FontDescriptor, FontResolution, or family name.")


def _override_style(
    style: TextStyle,
    *,
    font_size_pt: float | None,
    bold: bool | None,
    italic: bool | None,
    line_height_multiplier: float | None,
    paragraph_spacing_pt: float | None,
) -> TextStyle:
    return TextStyle(
        font_size_pt=style.font_size_pt if font_size_pt is None else font_size_pt,
        bold=style.bold if bold is None else bold,
        italic=style.italic if italic is None else italic,
        line_height_multiplier=(
            style.line_height_multiplier
            if line_height_multiplier is None
            else line_height_multiplier
        ),
        paragraph_spacing_pt=(
            style.paragraph_spacing_pt if paragraph_spacing_pt is None else paragraph_spacing_pt
        ),
    )


def _positive_finite(value: float, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field_name} must be a finite positive number.")
    converted = float(value)
    if not math.isfinite(converted) or converted <= 0:
        raise ValueError(f"{field_name} must be a finite positive number.")
    return converted


def _width(metrics: FontMetrics, text: str) -> float:
    width = float(metrics.getlength(text))
    if not math.isfinite(width) or width < 0:
        raise ValueError("Font metrics returned an invalid width.")
    return width


def _ink_height(metrics: FontMetrics, font_size_pt: float) -> float:
    bbox = metrics.getbbox("Ag")
    if bbox is None:
        return font_size_pt
    top, bottom = float(bbox[1]), float(bbox[3])
    height = bottom - top
    return height if math.isfinite(height) and height > 0 else font_size_pt


def _wrap_paragraph(
    paragraph: str,
    metrics: FontMetrics,
    max_width_pt: float | None,
) -> list[str]:
    if max_width_pt is None or _width(metrics, paragraph) <= max_width_pt:
        return [paragraph]
    if not paragraph:
        return [""]

    lines: list[str] = []
    current = ""
    for token in re.findall(r"\S+|\s+", paragraph):
        if token.isspace():
            if not current:
                continue
            candidate = current + token
            if _width(metrics, candidate.rstrip()) <= max_width_pt:
                current = candidate
            else:
                lines.append(current.rstrip())
                current = ""
            continue

        if not current and _width(metrics, token) > max_width_pt:
            chunks = _split_long_token(token, metrics, max_width_pt)
            lines.extend(chunks[:-1])
            current = chunks[-1]
            continue

        candidate = current + token
        if current and _width(metrics, candidate) > max_width_pt:
            lines.append(current.rstrip())
            current = token
            if _width(metrics, current) > max_width_pt:
                chunks = _split_long_token(current, metrics, max_width_pt)
                lines.extend(chunks[:-1])
                current = chunks[-1]
        else:
            current = candidate
    if current or not lines:
        lines.append(current.rstrip())
    return lines


def _split_long_token(token: str, metrics: FontMetrics, max_width_pt: float) -> list[str]:
    chunks: list[str] = []
    remaining = token
    while remaining:
        low, high = 1, len(remaining)
        best = 1
        while low <= high:
            middle = (low + high) // 2
            if _width(metrics, remaining[:middle]) <= max_width_pt:
                best = middle
                low = middle + 1
            else:
                high = middle - 1
        chunks.append(remaining[:best])
        remaining = remaining[best:]
    return chunks


class _PillowFontLike(Protocol):
    def getlength(self, text: str) -> float: ...

    def getbbox(self, text: str) -> tuple[float, float, float, float] | None: ...


class _PillowFontMetrics:
    def __init__(self, font: _PillowFontLike) -> None:
        self._font = font

    def getlength(self, text: str) -> float:
        return float(self._font.getlength(text))

    def getbbox(self, text: str) -> tuple[float, float, float, float] | None:
        bbox = self._font.getbbox(text)
        if bbox is None:
            return None
        return (float(bbox[0]), float(bbox[1]), float(bbox[2]), float(bbox[3]))


class _DeterministicFallbackMetrics:
    """Last-resort metrics used only when Pillow cannot load a font face."""

    def __init__(self, font_size_pt: float, *, bold: bool, italic: bool) -> None:
        style_factor = 1.02 if bold else 1.0
        style_factor *= 1.01 if italic else 1.0
        self._advance = font_size_pt * 0.5 * style_factor
        self._height = font_size_pt

    def getlength(self, text: str) -> float:
        return len(text) * self._advance

    def getbbox(self, text: str) -> tuple[float, float, float, float]:
        return (0.0, 0.0, self.getlength(text), self._height)


def _load_actual_font(font: FontDescriptor, style: TextStyle) -> FontMetrics:
    """Load the resolved face through Pillow without changing the source file."""

    try:
        from PIL import ImageFont
    except ImportError:
        return _DeterministicFallbackMetrics(
            style.font_size_pt,
            bold=style.bold,
            italic=style.italic,
        )

    size = max(1, round(style.font_size_pt))
    paths = _font_variant_paths(font.path, bold=style.bold, italic=style.italic)
    for path in paths:
        try:
            return _PillowFontMetrics(ImageFont.truetype(str(path), size=size))
        except (OSError, TypeError):
            continue
    try:
        return _PillowFontMetrics(ImageFont.truetype(font.family_name, size=size))
    except (OSError, TypeError):
        try:
            return _PillowFontMetrics(ImageFont.load_default(size=size))
        except TypeError:
            return _PillowFontMetrics(ImageFont.load_default())


def _font_variant_paths(
    path: Path | None,
    *,
    bold: bool,
    italic: bool,
) -> tuple[Path, ...]:
    if path is None:
        return ()
    suffix = "bi" if bold and italic else "bd" if bold else "i" if italic else ""
    candidates = [path]
    if suffix:
        candidates.insert(0, path.with_name(f"{path.stem}{suffix}{path.suffix}"))
    return tuple(candidate for candidate in candidates if candidate.is_file())
