"""Immutable inputs shared by the overlay renderer."""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import StrEnum

Color = tuple[float, float, float]


class TextAlignment(StrEnum):
    """Horizontal alignment inside an optional text box."""

    LEFT = "LEFT"
    CENTER = "CENTER"
    RIGHT = "RIGHT"


def _finite(value: object, field_name: str, *, positive: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field_name} must be a finite number.")
    converted = float(value)
    if not math.isfinite(converted) or (positive and converted <= 0):
        qualifier = "positive " if positive else ""
        raise ValueError(f"{field_name} must be a finite {qualifier}number.")
    return converted


def _color(value: object, field_name: str) -> Color:
    if not isinstance(value, tuple) or len(value) != 3:
        raise ValueError(f"{field_name} must be an RGB tuple with three values.")
    values = tuple(_finite(component, field_name) for component in value)
    if any(component < 0 or component > 1 for component in values):
        raise ValueError(f"{field_name} components must be between 0 and 1.")
    return (values[0], values[1], values[2])


@dataclass(frozen=True, slots=True)
class CoverRegion:
    """A source-text region to paint over before drawing translated text.

    Coordinates use the PDF user space (origin at the lower-left corner).
    ``source_text`` is optional evidence used to remove matching text-show
    operations from the copied source page.
    """

    x: float
    y: float
    width: float
    height: float
    fill_color: Color = (1.0, 1.0, 1.0)
    source_text: str | None = None
    region_id: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "x", _finite(self.x, "x"))
        object.__setattr__(self, "y", _finite(self.y, "y"))
        object.__setattr__(self, "width", _finite(self.width, "width", positive=True))
        object.__setattr__(self, "height", _finite(self.height, "height", positive=True))
        object.__setattr__(self, "fill_color", _color(self.fill_color, "fill_color"))
        if self.source_text is not None and type(self.source_text) is not str:
            raise ValueError("source_text must be a string or None.")
        if self.region_id is not None and (
            type(self.region_id) is not str or not self.region_id.strip()
        ):
            raise ValueError("region_id must be a non-empty string or None.")

    @property
    def right(self) -> float:
        return self.x + self.width

    @property
    def top(self) -> float:
        return self.y + self.height

    def contains_point(self, x: float, y: float, *, tolerance: float = 0.5) -> bool:
        return (
            self.x - tolerance <= x <= self.right + tolerance
            and self.y - tolerance <= y <= self.top + tolerance
        )


@dataclass(frozen=True, slots=True)
class OverlayText:
    """One selectable translated text block placed on the overlay page."""

    text: str
    x: float
    y: float
    width: float | None = None
    height: float | None = None
    font_name: str = "Helvetica"
    font_size_pt: float = 12.0
    color: Color = (0.0, 0.0, 0.0)
    leading_pt: float | None = None
    alignment: TextAlignment = TextAlignment.LEFT
    text_id: str | None = None

    def __post_init__(self) -> None:
        if type(self.text) is not str or not self.text.strip():
            raise ValueError("text must be a non-empty string.")
        object.__setattr__(self, "x", _finite(self.x, "x"))
        object.__setattr__(self, "y", _finite(self.y, "y"))
        if self.width is not None:
            object.__setattr__(self, "width", _finite(self.width, "width", positive=True))
        if self.height is not None:
            object.__setattr__(self, "height", _finite(self.height, "height", positive=True))
        object.__setattr__(
            self, "font_size_pt", _finite(self.font_size_pt, "font_size_pt", positive=True)
        )
        if self.leading_pt is not None:
            object.__setattr__(
                self,
                "leading_pt",
                _finite(self.leading_pt, "leading_pt", positive=True),
            )
        if type(self.font_name) is not str or not self.font_name.strip():
            raise ValueError("font_name must be a non-empty string.")
        object.__setattr__(self, "color", _color(self.color, "color"))
        if not isinstance(self.alignment, TextAlignment):
            try:
                object.__setattr__(self, "alignment", TextAlignment(self.alignment))
            except ValueError as exc:
                raise ValueError("alignment must be a known text alignment.") from exc
        if self.text_id is not None and (type(self.text_id) is not str or not self.text_id.strip()):
            raise ValueError("text_id must be a non-empty string or None.")


# Descriptive aliases keep the public API readable for callers that model a
# translated region rather than a text run.
TextRegion = OverlayText
SourceTextRegion = CoverRegion
