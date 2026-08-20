"""Validated, immutable settings for document reconstruction.

The reconstruction engine deliberately keeps its settings small and explicit.
Profiles select a strategy for editable layout; they never opt out of the
protected-content guarantees enforced by the translation pipeline.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Self, cast


class ReconstructionMode(StrEnum):
    """Strategy used to place translated content on a page."""

    OVERLAY = "OVERLAY"
    REFLOW = "REFLOW"
    HYBRID = "HYBRID"


class ReconstructionProfile(StrEnum):
    """User-facing balance between source geometry and readability."""

    PRESERVE_LAYOUT = "PRESERVE_LAYOUT"
    BALANCED = "BALANCED"
    READABILITY_FIRST = "READABILITY_FIRST"


class TableComplexityFallback(StrEnum):
    """Fallback used when a table cannot be safely reconstructed."""

    PRESERVE_AS_IMAGE = "PRESERVE_AS_IMAGE"
    MANUAL_REVIEW = "MANUAL_REVIEW"


class ImageQuality(StrEnum):
    """Image export quality requested for the output document."""

    STANDARD = "STANDARD"
    HIGH = "HIGH"


class OutputProfile(StrEnum):
    """Output encoding profile described by the reconstruction specification."""

    STANDARD = "STANDARD"
    HIGH_QUALITY = "HIGH_QUALITY"
    COMPACT = "COMPACT"
    BILINGUAL = "BILINGUAL"


def _enum_value[EnumValue: StrEnum](
    enum_type: type[EnumValue], value: object, field_name: str
) -> EnumValue:
    if isinstance(value, enum_type):
        return value
    if type(value) is not str:
        allowed = ", ".join(member.value for member in enum_type)
        raise ValueError(f"{field_name} must be one of: {allowed}.")
    try:
        return enum_type(value)
    except ValueError as exc:
        allowed = ", ".join(member.value for member in enum_type)
        raise ValueError(f"{field_name} must be one of: {allowed}.") from exc


def _bool_value(value: object, field_name: str) -> bool:
    if type(value) is not bool:
        raise ValueError(f"{field_name} must be a boolean.")
    return value


def _finite_number(value: object, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{field_name} must be a finite number.")
    result = float(value)
    if not math.isfinite(result):
        raise ValueError(f"{field_name} must be a finite number.")
    return result


@dataclass(frozen=True, slots=True)
class ReconstructionSettings:
    """Validated settings snapshot for one reconstruction run.

    The defaults mirror the reconstruction engine's documented schema.  The
    object is frozen so a run can retain an immutable settings snapshot.  No
    profile changes protected content: protected regions remain governed by
    the protection/restoration pipeline rather than these layout preferences.
    """

    mode: ReconstructionMode = ReconstructionMode.HYBRID
    profile: ReconstructionProfile = ReconstructionProfile.BALANCED
    preserve_page_size: bool = True
    preserve_images: bool = True
    preserve_headers: bool = True
    preserve_footers: bool = True
    preserve_page_numbers: bool = True
    translate_captions: bool = True
    minimum_body_font_pt: float = 8.0
    maximum_font_reduction_percent: float = 10.0
    allow_page_addition: bool = True
    allow_single_column_fallback: bool = False
    allow_column_change: bool = False
    table_complexity_fallback: TableComplexityFallback = TableComplexityFallback.PRESERVE_AS_IMAGE
    image_quality: ImageQuality = ImageQuality.STANDARD
    output_profile: OutputProfile = OutputProfile.STANDARD
    block_export_on_critical_errors: bool = True
    show_layout_warnings: bool = True

    def __post_init__(self) -> None:
        mode = _enum_value(ReconstructionMode, self.mode, "mode")
        profile = _enum_value(ReconstructionProfile, self.profile, "profile")
        table_fallback = _enum_value(
            TableComplexityFallback,
            self.table_complexity_fallback,
            "table_complexity_fallback",
        )
        image_quality = _enum_value(ImageQuality, self.image_quality, "image_quality")
        output_profile = _enum_value(OutputProfile, self.output_profile, "output_profile")
        object.__setattr__(self, "mode", mode)
        object.__setattr__(self, "profile", profile)
        object.__setattr__(self, "table_complexity_fallback", table_fallback)
        object.__setattr__(self, "image_quality", image_quality)
        object.__setattr__(self, "output_profile", output_profile)

        boolean_fields = (
            "preserve_page_size",
            "preserve_images",
            "preserve_headers",
            "preserve_footers",
            "preserve_page_numbers",
            "translate_captions",
            "allow_page_addition",
            "allow_single_column_fallback",
            "allow_column_change",
            "block_export_on_critical_errors",
            "show_layout_warnings",
        )
        for field_name in boolean_fields:
            _bool_value(getattr(self, field_name), field_name)

        minimum_font = _finite_number(self.minimum_body_font_pt, "minimum_body_font_pt")
        if not 6.0 <= minimum_font <= 72.0:
            raise ValueError("minimum_body_font_pt must be between 6 and 72 points.")
        object.__setattr__(self, "minimum_body_font_pt", minimum_font)

        reduction = _finite_number(
            self.maximum_font_reduction_percent,
            "maximum_font_reduction_percent",
        )
        if not 0.0 <= reduction <= 50.0:
            raise ValueError("maximum_font_reduction_percent must be between 0 and 50.")
        object.__setattr__(self, "maximum_font_reduction_percent", reduction)

        if mode is ReconstructionMode.OVERLAY and (
            not self.preserve_page_size
            or self.allow_column_change
            or self.allow_single_column_fallback
        ):
            raise ValueError(
                "OVERLAY mode requires preserve_page_size=True and layout-changing fallbacks disabled."
            )
        if profile is ReconstructionProfile.PRESERVE_LAYOUT and (
            not self.preserve_page_size
            or self.allow_column_change
            or self.allow_single_column_fallback
        ):
            raise ValueError(
                "PRESERVE_LAYOUT requires preserve_page_size=True and layout-changing fallbacks disabled."
            )

    @classmethod
    def from_dict(cls, value: Mapping[str, object]) -> Self:
        """Build settings from a JSON-compatible mapping.

        Unknown keys are rejected so a typo cannot silently weaken a safety
        setting.  Omitted keys use the documented defaults.
        """

        if not isinstance(value, Mapping):
            raise ValueError("Reconstruction settings must be a mapping.")
        allowed = frozenset(cls.__dataclass_fields__)
        unknown = set(value) - allowed
        if unknown:
            names = ", ".join(sorted(str(name) for name in unknown))
            raise ValueError(f"Unknown reconstruction setting(s): {names}.")
        return cls(
            mode=cast(ReconstructionMode, value.get("mode", ReconstructionMode.HYBRID)),
            profile=cast(
                ReconstructionProfile, value.get("profile", ReconstructionProfile.BALANCED)
            ),
            preserve_page_size=cast(bool, value.get("preserve_page_size", True)),
            preserve_images=cast(bool, value.get("preserve_images", True)),
            preserve_headers=cast(bool, value.get("preserve_headers", True)),
            preserve_footers=cast(bool, value.get("preserve_footers", True)),
            preserve_page_numbers=cast(bool, value.get("preserve_page_numbers", True)),
            translate_captions=cast(bool, value.get("translate_captions", True)),
            minimum_body_font_pt=cast(float, value.get("minimum_body_font_pt", 8.0)),
            maximum_font_reduction_percent=cast(
                float,
                value.get("maximum_font_reduction_percent", 10.0),
            ),
            allow_page_addition=cast(bool, value.get("allow_page_addition", True)),
            allow_single_column_fallback=cast(
                bool,
                value.get("allow_single_column_fallback", False),
            ),
            allow_column_change=cast(bool, value.get("allow_column_change", False)),
            table_complexity_fallback=cast(
                TableComplexityFallback,
                value.get("table_complexity_fallback", TableComplexityFallback.PRESERVE_AS_IMAGE),
            ),
            image_quality=cast(ImageQuality, value.get("image_quality", ImageQuality.STANDARD)),
            output_profile=cast(OutputProfile, value.get("output_profile", OutputProfile.STANDARD)),
            block_export_on_critical_errors=cast(
                bool,
                value.get("block_export_on_critical_errors", True),
            ),
            show_layout_warnings=cast(bool, value.get("show_layout_warnings", True)),
        )

    def to_dict(self) -> dict[str, object]:
        """Return a JSON-compatible settings snapshot."""

        return {
            "mode": self.mode.value,
            "profile": self.profile.value,
            "preserve_page_size": self.preserve_page_size,
            "preserve_images": self.preserve_images,
            "preserve_headers": self.preserve_headers,
            "preserve_footers": self.preserve_footers,
            "preserve_page_numbers": self.preserve_page_numbers,
            "translate_captions": self.translate_captions,
            "minimum_body_font_pt": self.minimum_body_font_pt,
            "maximum_font_reduction_percent": self.maximum_font_reduction_percent,
            "allow_page_addition": self.allow_page_addition,
            "allow_single_column_fallback": self.allow_single_column_fallback,
            "allow_column_change": self.allow_column_change,
            "table_complexity_fallback": self.table_complexity_fallback.value,
            "image_quality": self.image_quality.value,
            "output_profile": self.output_profile.value,
            "block_export_on_critical_errors": self.block_export_on_critical_errors,
            "show_layout_warnings": self.show_layout_warnings,
        }

    @property
    def preserves_protected_content(self) -> bool:
        """Protected content is always preserved independently of the profile."""

        return True
