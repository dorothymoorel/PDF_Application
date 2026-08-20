"""Safe PDF overlay generation for fixed-layout reconstruction."""

from .generator import (
    OverlayDependencyError,
    OverlayError,
    OverlayLayoutError,
    OverlayPageGenerator,
    generate_overlay_page,
    merge_overlay_page,
)
from .types import CoverRegion, OverlayText, SourceTextRegion, TextAlignment, TextRegion

__all__ = [
    "CoverRegion",
    "OverlayDependencyError",
    "OverlayError",
    "OverlayLayoutError",
    "OverlayPageGenerator",
    "OverlayText",
    "SourceTextRegion",
    "TextAlignment",
    "TextRegion",
    "generate_overlay_page",
    "merge_overlay_page",
]
