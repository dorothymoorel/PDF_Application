from dataclasses import dataclass

import pytest
from transloka_reconstruction.fonts import (
    FontCategory,
    FontDescriptor,
    FontResolver,
)
from transloka_reconstruction.layout.measurement import (
    FontMetrics,
    TextMeasurer,
    TextStyle,
)


@dataclass(frozen=True)
class FakeFontMetrics:
    advance: float
    ink_height: float = 10.0

    def getlength(self, text: str) -> float:
        return len(text) * self.advance

    def getbbox(self, text: str) -> tuple[float, float, float, float]:
        return (0.0, 0.0, self.getlength(text), self.ink_height)


def _font(name: str = "Test Sans") -> FontDescriptor:
    return FontDescriptor(family_name=name, category=FontCategory.SANS_SERIF)


def _measurer() -> TextMeasurer:
    def loader(font: FontDescriptor, style: TextStyle) -> FontMetrics:
        factor = 1.1 if style.bold else 1.0
        factor *= 1.05 if style.italic else 1.0
        return FakeFontMetrics(advance=5.0 * factor, ink_height=style.font_size_pt)

    return TextMeasurer(font_loader=loader)


def test_short_text_uses_actual_font_metrics() -> None:
    result = _measurer().measure("Hello", font=_font(), font_size_pt=10)

    assert result.width_pt == 25.0
    assert result.height_pt == 12.0
    assert result.line_height_pt == 12.0
    assert result.line_count == 1
    assert result.lines == ("Hello",)


def test_long_text_wraps_without_losing_content() -> None:
    result = _measurer().measure(
        "one two three four",
        font=_font(),
        max_width_pt=40,
    )

    assert result.line_count == 3
    assert " ".join(result.lines) == "one two three four"
    assert result.width_pt <= 40
    assert result.wrapped is True


def test_bold_and_italic_styles_use_style_specific_metrics() -> None:
    measurer = _measurer()
    normal = measurer.measure("Hello", font=_font())
    styled = measurer.measure("Hello", font=_font(), bold=True, italic=True)

    assert styled.style.bold is True
    assert styled.style.italic is True
    assert styled.width_pt > normal.width_pt


def test_font_fallback_resolution_is_measured_with_selected_font() -> None:
    resolution = FontResolver().resolve(
        "Unavailable",
        category=FontCategory.MONOSPACE,
        text="code",
    )
    result = _measurer().measure("code", font=resolution)

    assert result.font is resolution.font
    assert result.font_family == "Noto Sans Mono"


def test_explicit_line_breaks_are_preserved() -> None:
    result = _measurer().measure("first\nsecond\n", font=_font())

    assert result.lines == ("first", "second", "")
    assert result.line_count == 3
    assert result.paragraph_count == 3


def test_paragraph_spacing_contributes_to_height() -> None:
    result = _measurer().measure(
        "first\nsecond",
        font=_font(),
        style=TextStyle(font_size_pt=10, paragraph_spacing_pt=3),
    )

    assert result.height_pt == pytest.approx(27.0)


def test_measurement_is_deterministic_and_serializable() -> None:
    measurer = _measurer()
    first = measurer.measure("same text", font=_font(), max_width_pt=50)
    second = measurer.measure("same text", font=_font(), max_width_pt=50)

    assert first == second
    assert first.to_dict() == second.to_dict()


def test_invalid_measurement_inputs_are_rejected() -> None:
    with pytest.raises(ValueError, match="max_width_pt"):
        _measurer().measure("text", font=_font(), max_width_pt=0)
    with pytest.raises(ValueError, match="line_height_multiplier"):
        TextStyle(line_height_multiplier=0.9)
    with pytest.raises(ValueError, match="font_size_pt"):
        TextStyle(font_size_pt=0)
