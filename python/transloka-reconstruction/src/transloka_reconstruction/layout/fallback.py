"""Deterministic text-layout fallback chain.

The fallback engine never drops or clips text.  Every automatic result carries
the original text in one or more fragments; when no safe placement exists it
returns an explicit manual-review result instead of pretending that the block
was rendered successfully.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field, replace
from enum import StrEnum
from typing import cast

from .measurement import FontInput, TextMeasurement, TextMeasurer, TextStyle
from .overflow import BoundingBox


class LayoutFallbackError(ValueError):
    """Base error for invalid layout-fallback input."""


class LayoutFallbackStep(StrEnum):
    """Ordered strategies used to fit one translated text block."""

    WRAP = "WRAP"
    EXPAND_BOX = "EXPAND_BOX"
    REDUCE_SPACING = "REDUCE_SPACING"
    REDUCE_FONT = "REDUCE_FONT"
    MOVE_BLOCK = "MOVE_BLOCK"
    REFLOW = "REFLOW"
    NEXT_PAGE = "NEXT_PAGE"
    ADD_PAGE = "ADD_PAGE"
    MANUAL_REVIEW = "MANUAL_REVIEW"


FallbackStep = LayoutFallbackStep
LayoutFallbackStage = LayoutFallbackStep
FallbackAction = LayoutFallbackStep


class FallbackWarningCode(StrEnum):
    """Stable warning codes emitted by the fallback chain."""

    SIGNIFICANT_LAYOUT_SHIFT = "SIGNIFICANT_LAYOUT_SHIFT"
    PAGE_ADDED_DUE_TO_TRANSLATION_EXPANSION = "PAGE_ADDED_DUE_TO_TRANSLATION_EXPANSION"
    MINIMUM_FONT_REACHED = "MINIMUM_FONT_REACHED"
    TEXT_OVERFLOW_UNRESOLVED = "TEXT_OVERFLOW_UNRESOLVED"
    MANUAL_REVIEW_REQUIRED = "MANUAL_REVIEW_REQUIRED"


class FallbackWarningSeverity(StrEnum):
    INFO = "INFO"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


def _text(value: object, field_name: str, *, allow_empty: bool = False) -> str:
    if type(value) is not str or (not allow_empty and not value.strip()):
        qualifier = "string" if allow_empty else "non-empty string"
        raise LayoutFallbackError(f"{field_name} must be a {qualifier}.")
    return value


def _positive(value: object, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise LayoutFallbackError(f"{field_name} must be a finite positive number.")
    converted = float(value)
    if not math.isfinite(converted) or converted <= 0:
        raise LayoutFallbackError(f"{field_name} must be a finite positive number.")
    return converted


def _non_negative(value: object, field_name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise LayoutFallbackError(f"{field_name} must be a finite non-negative number.")
    converted = float(value)
    if not math.isfinite(converted) or converted < 0:
        raise LayoutFallbackError(f"{field_name} must be a finite non-negative number.")
    return converted


def _box(value: object, field_name: str) -> BoundingBox:
    if type(value) is not BoundingBox:
        raise LayoutFallbackError(f"{field_name} must be a BoundingBox.")
    if value.width <= 0 or value.height <= 0:
        raise LayoutFallbackError(f"{field_name} must have positive width and height.")
    return value


@dataclass(frozen=True, slots=True)
class LayoutBlock:
    """A following block that may be moved to make room for expanded text."""

    block_id: str
    bounds: BoundingBox
    fixed: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "block_id", _text(self.block_id, "block_id"))
        object.__setattr__(self, "bounds", _box(self.bounds, "bounds"))
        if type(self.fixed) is not bool:
            raise LayoutFallbackError("fixed must be a boolean.")


FollowingBlock = LayoutBlock


@dataclass(frozen=True, slots=True)
class LayoutFallbackSettings:
    """Safety limits for automatic layout adjustments."""

    max_box_expansion_ratio: float = 2.0
    max_font_reduction: float = 0.10
    minimum_font_size_pt: float = 8.0
    minimum_line_height_multiplier: float = 1.0
    minimum_paragraph_spacing_pt: float = 0.0
    max_move_points: float = 72.0
    allow_reflow: bool = True
    allow_next_page: bool = True
    allow_page_addition: bool = True
    max_added_pages: int = 3

    def __post_init__(self) -> None:
        expansion = _positive(self.max_box_expansion_ratio, "max_box_expansion_ratio")
        if expansion < 1.0:
            raise LayoutFallbackError("max_box_expansion_ratio must be at least 1.")
        reduction = _non_negative(self.max_font_reduction, "max_font_reduction")
        if reduction > 1.0:
            raise LayoutFallbackError("max_font_reduction must not exceed 1.")
        minimum_font = _positive(self.minimum_font_size_pt, "minimum_font_size_pt")
        minimum_line = _positive(
            self.minimum_line_height_multiplier, "minimum_line_height_multiplier"
        )
        if minimum_line < 1.0:
            raise LayoutFallbackError("minimum_line_height_multiplier must be at least 1.")
        minimum_spacing = _non_negative(
            self.minimum_paragraph_spacing_pt, "minimum_paragraph_spacing_pt"
        )
        max_move = _non_negative(self.max_move_points, "max_move_points")
        if type(self.max_added_pages) is not int or self.max_added_pages < 0:
            raise LayoutFallbackError("max_added_pages must be a non-negative integer.")
        for field_name in ("allow_reflow", "allow_next_page", "allow_page_addition"):
            if type(getattr(self, field_name)) is not bool:
                raise LayoutFallbackError(f"{field_name} must be a boolean.")
        object.__setattr__(self, "max_box_expansion_ratio", expansion)
        object.__setattr__(self, "max_font_reduction", reduction)
        object.__setattr__(self, "minimum_font_size_pt", minimum_font)
        object.__setattr__(self, "minimum_line_height_multiplier", minimum_line)
        object.__setattr__(self, "minimum_paragraph_spacing_pt", minimum_spacing)
        object.__setattr__(self, "max_move_points", max_move)

    @property
    def min_font_size_pt(self) -> float:
        """Short alias used by callers configuring a readable font floor."""

        return self.minimum_font_size_pt


@dataclass(frozen=True, slots=True)
class LayoutFallbackRequest:
    """Input for one deterministic fallback-chain evaluation."""

    block_id: str
    text: str
    bounds: BoundingBox | None = None
    page_bounds: BoundingBox | None = None
    font: FontInput = "Noto Sans"
    style: TextStyle = field(default_factory=TextStyle)
    safe_bounds: BoundingBox | None = None
    following_blocks: tuple[LayoutBlock, ...] = ()
    next_page_id: str | None = None
    next_page_bounds: BoundingBox | None = None
    settings: LayoutFallbackSettings = field(default_factory=LayoutFallbackSettings)
    measurer: TextMeasurer | None = None
    box: BoundingBox | None = None
    font_size_pt: float | None = None
    page_id: str = "page-1"

    def __post_init__(self) -> None:
        object.__setattr__(self, "block_id", _text(self.block_id, "block_id"))
        object.__setattr__(self, "text", _text(self.text, "text", allow_empty=True))
        object.__setattr__(self, "page_id", _text(self.page_id, "page_id"))
        resolved_bounds = self.bounds or self.box
        if resolved_bounds is None:
            raise LayoutFallbackError("bounds or box must be provided.")
        if self.bounds is not None and self.box is not None and self.bounds != self.box:
            raise LayoutFallbackError("bounds and box must describe the same region.")
        resolved_bounds = _box(resolved_bounds, "bounds")
        object.__setattr__(self, "bounds", resolved_bounds)
        object.__setattr__(self, "box", resolved_bounds)
        page_bounds = self.page_bounds or resolved_bounds
        safe_bounds = self.safe_bounds or page_bounds
        object.__setattr__(self, "page_bounds", _box(page_bounds, "page_bounds"))
        object.__setattr__(self, "safe_bounds", _box(safe_bounds, "safe_bounds"))
        if type(self.style) is not TextStyle:
            raise LayoutFallbackError("style must be a TextStyle.")
        if self.font_size_pt is not None:
            object.__setattr__(
                self,
                "style",
                replace(self.style, font_size_pt=_positive(self.font_size_pt, "font_size_pt")),
            )
        if type(self.settings) is not LayoutFallbackSettings:
            raise LayoutFallbackError("settings must be a LayoutFallbackSettings.")
        blocks = tuple(self.following_blocks)
        if any(type(block) is not LayoutBlock for block in blocks):
            raise LayoutFallbackError("following_blocks must contain LayoutBlock values.")
        if len({block.block_id for block in blocks}) != len(blocks):
            raise LayoutFallbackError("following_blocks must have unique block IDs.")
        object.__setattr__(self, "following_blocks", blocks)
        for field_name in ("next_page_bounds",):
            value = getattr(self, field_name)
            if value is not None:
                object.__setattr__(self, field_name, _box(value, field_name))
        if self.next_page_id is not None:
            object.__setattr__(self, "next_page_id", _text(self.next_page_id, "next_page_id"))
        if self.measurer is not None and type(self.measurer) is not TextMeasurer:
            raise LayoutFallbackError("measurer must be a TextMeasurer or None.")


@dataclass(frozen=True, slots=True)
class FallbackWarning:
    """One auditable consequence of a fallback decision."""

    code: FallbackWarningCode
    message: str
    severity: FallbackWarningSeverity
    block_id: str

    def __post_init__(self) -> None:
        if not isinstance(self.code, FallbackWarningCode):
            object.__setattr__(self, "code", FallbackWarningCode(self.code))
        if not isinstance(self.severity, FallbackWarningSeverity):
            object.__setattr__(self, "severity", FallbackWarningSeverity(self.severity))
        object.__setattr__(self, "message", _text(self.message, "message"))
        object.__setattr__(self, "block_id", _text(self.block_id, "block_id"))


@dataclass(frozen=True, slots=True)
class LayoutFragment:
    """A page-local fragment whose text is never silently discarded."""

    page_id: str
    text: str
    bounds: BoundingBox
    step: LayoutFallbackStep
    fragment_order: int = 1
    renderable: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(self, "page_id", _text(self.page_id, "page_id"))
        object.__setattr__(self, "text", _text(self.text, "text", allow_empty=True))
        object.__setattr__(self, "bounds", _box(self.bounds, "bounds"))
        if not isinstance(self.step, LayoutFallbackStep):
            object.__setattr__(self, "step", LayoutFallbackStep(self.step))
        if type(self.fragment_order) is not int or self.fragment_order < 1:
            raise LayoutFallbackError("fragment_order must be a positive integer.")
        if type(self.renderable) is not bool:
            raise LayoutFallbackError("renderable must be a boolean.")


TextFragment = LayoutFragment


@dataclass(frozen=True, slots=True)
class FallbackAttempt:
    """Evidence for one step in the fallback chain."""

    step: LayoutFallbackStep
    resolved: bool
    page_id: str
    bounds: BoundingBox
    style: TextStyle
    measurement: TextMeasurement | None
    reason: str

    def __post_init__(self) -> None:
        if not isinstance(self.step, LayoutFallbackStep):
            object.__setattr__(self, "step", LayoutFallbackStep(self.step))
        if type(self.resolved) is not bool:
            raise LayoutFallbackError("resolved must be a boolean.")
        object.__setattr__(self, "page_id", _text(self.page_id, "page_id"))
        object.__setattr__(self, "bounds", _box(self.bounds, "bounds"))
        if type(self.style) is not TextStyle:
            raise LayoutFallbackError("style must be a TextStyle.")
        object.__setattr__(self, "reason", _text(self.reason, "reason"))


@dataclass(frozen=True, slots=True)
class LayoutFallbackResult:
    """Final fallback decision, evidence, fragments, and warnings."""

    block_id: str
    text: str
    step: LayoutFallbackStep
    resolved: bool
    page_id: str
    bounds: BoundingBox
    style: TextStyle
    measurement: TextMeasurement | None
    fragments: tuple[LayoutFragment, ...]
    attempts: tuple[FallbackAttempt, ...]
    moved_blocks: tuple[LayoutBlock, ...]
    warnings: tuple[FallbackWarning, ...]

    @property
    def final_step(self) -> LayoutFallbackStep:
        return self.step

    @property
    def needs_review(self) -> bool:
        return not self.resolved or any(
            warning.severity is FallbackWarningSeverity.CRITICAL for warning in self.warnings
        )

    @property
    def text_preserved(self) -> bool:
        return "".join(fragment.text for fragment in self.fragments) == self.text

    @property
    def complete(self) -> bool:
        return self.resolved and self.text_preserved and not self.needs_review

    @property
    def blocks_export(self) -> bool:
        return self.needs_review

    @property
    def font_size_pt(self) -> float:
        return self.style.font_size_pt

    def to_dict(self) -> dict[str, object]:
        return {
            "block_id": self.block_id,
            "step": self.step.value,
            "resolved": self.resolved,
            "page_id": self.page_id,
            "text_preserved": self.text_preserved,
            "needs_review": self.needs_review,
            "fragment_count": len(self.fragments),
            "warnings": [warning.code.value for warning in self.warnings],
        }


class LayoutFallbackEngine:
    """Apply the documented fallback chain without clipping translated text."""

    _TOLERANCE = 1e-9
    _SIGNIFICANT_SHIFT_POINTS = 24.0

    def __init__(self, measurer: TextMeasurer | None = None) -> None:
        if measurer is not None and type(measurer) is not TextMeasurer:
            raise LayoutFallbackError("measurer must be a TextMeasurer or None.")
        self._measurer = measurer or TextMeasurer()

    def resolve(self, request: LayoutFallbackRequest) -> LayoutFallbackResult:
        if type(request) is not LayoutFallbackRequest:
            raise LayoutFallbackError("request must be a LayoutFallbackRequest.")
        measurer = request.measurer or self._measurer
        settings = request.settings
        attempts: list[FallbackAttempt] = []
        warnings: list[FallbackWarning] = []
        current_box = cast(BoundingBox, request.bounds)
        current_style = request.style
        current_page = request.page_id
        moved_blocks: tuple[LayoutBlock, ...] = ()

        def evaluate(
            step: LayoutFallbackStep,
            box: BoundingBox,
            style: TextStyle,
            *,
            page_id: str,
            reason: str,
            moved: tuple[LayoutBlock, ...] = (),
        ) -> tuple[bool, TextMeasurement]:
            try:
                measurement = measurer.measure(
                    request.text,
                    font=request.font,
                    style=style,
                    max_width_pt=box.width,
                )
            except (TypeError, ValueError) as exc:
                raise LayoutFallbackError("Text measurement failed for fallback input.") from exc
            fits = _fits(measurement, box)
            attempts.append(
                FallbackAttempt(
                    step=step,
                    resolved=fits,
                    page_id=page_id,
                    bounds=box,
                    style=style,
                    measurement=measurement,
                    reason=reason,
                )
            )
            return fits, measurement

        def finish(
            step: LayoutFallbackStep,
            *,
            resolved: bool,
            page_id: str,
            box: BoundingBox,
            style: TextStyle,
            measurement: TextMeasurement | None,
            fragments: tuple[LayoutFragment, ...],
            moved: tuple[LayoutBlock, ...] = (),
        ) -> LayoutFallbackResult:
            return LayoutFallbackResult(
                block_id=request.block_id,
                text=request.text,
                step=step,
                resolved=resolved,
                page_id=page_id,
                bounds=box,
                style=style,
                measurement=measurement,
                fragments=fragments,
                attempts=tuple(attempts),
                moved_blocks=moved,
                warnings=tuple(warnings),
            )

        fits, measurement = evaluate(
            LayoutFallbackStep.WRAP,
            current_box,
            current_style,
            page_id=current_page,
            reason="Text was wrapped inside the source box.",
        )
        if fits:
            return finish(
                LayoutFallbackStep.WRAP,
                resolved=True,
                page_id=current_page,
                box=current_box,
                style=current_style,
                measurement=measurement,
                fragments=_fragment(request, current_page, current_box, LayoutFallbackStep.WRAP),
            )

        expanded_box = _expand_box(
            current_box,
            cast(BoundingBox, request.safe_bounds),
            settings.max_box_expansion_ratio,
        )
        fits, measurement = evaluate(
            LayoutFallbackStep.EXPAND_BOX,
            expanded_box,
            current_style,
            page_id=current_page,
            reason="The text box was expanded only inside the safe region.",
        )
        if fits:
            return finish(
                LayoutFallbackStep.EXPAND_BOX,
                resolved=True,
                page_id=current_page,
                box=expanded_box,
                style=current_style,
                measurement=measurement,
                fragments=_fragment(
                    request, current_page, expanded_box, LayoutFallbackStep.EXPAND_BOX
                ),
            )
        current_box = expanded_box

        spacing_style = replace(
            current_style,
            line_height_multiplier=min(
                current_style.line_height_multiplier,
                settings.minimum_line_height_multiplier,
            ),
            paragraph_spacing_pt=min(
                current_style.paragraph_spacing_pt,
                settings.minimum_paragraph_spacing_pt,
            ),
        )
        fits, measurement = evaluate(
            LayoutFallbackStep.REDUCE_SPACING,
            current_box,
            spacing_style,
            page_id=current_page,
            reason="Line height and paragraph spacing were reduced to configured floors.",
        )
        if fits:
            return finish(
                LayoutFallbackStep.REDUCE_SPACING,
                resolved=True,
                page_id=current_page,
                box=current_box,
                style=spacing_style,
                measurement=measurement,
                fragments=_fragment(
                    request, current_page, current_box, LayoutFallbackStep.REDUCE_SPACING
                ),
            )
        current_style = spacing_style

        original_font_size = request.style.font_size_pt
        font_floor = min(
            current_style.font_size_pt,
            max(
                settings.minimum_font_size_pt,
                original_font_size * (1.0 - settings.max_font_reduction),
            ),
        )
        font_style = replace(current_style, font_size_pt=font_floor)
        fits, measurement = evaluate(
            LayoutFallbackStep.REDUCE_FONT,
            current_box,
            font_style,
            page_id=current_page,
            reason="Font size was reduced without crossing the configured safety floor.",
        )
        if fits:
            return finish(
                LayoutFallbackStep.REDUCE_FONT,
                resolved=True,
                page_id=current_page,
                box=current_box,
                style=font_style,
                measurement=measurement,
                fragments=_fragment(
                    request, current_page, current_box, LayoutFallbackStep.REDUCE_FONT
                ),
            )
        if font_floor <= settings.minimum_font_size_pt + self._TOLERANCE:
            warnings.append(
                _warning(
                    request,
                    FallbackWarningCode.MINIMUM_FONT_REACHED,
                    "The minimum readable font size was reached before the text fit.",
                    FallbackWarningSeverity.WARNING,
                )
            )
        current_style = font_style

        required_move = max(0.0, measurement.height_pt - current_box.height)
        moved, move_distance = _move_following_blocks(
            request.following_blocks,
            required_move,
            cast(BoundingBox, request.page_bounds),
            settings.max_move_points,
        )
        moved_box = _heightened_box(
            current_box,
            required_move,
            cast(BoundingBox, request.safe_bounds),
        )
        move_fits = required_move > 0 and moved is not None and moved_box is not None
        if move_fits:
            assert moved is not None and moved_box is not None
            fits, measurement = evaluate(
                LayoutFallbackStep.MOVE_BLOCK,
                moved_box,
                current_style,
                page_id=current_page,
                reason="Following movable blocks were shifted to make room.",
                moved=moved,
            )
            if fits:
                if move_distance > self._SIGNIFICANT_SHIFT_POINTS:
                    warnings.append(
                        _warning(
                            request,
                            FallbackWarningCode.SIGNIFICANT_LAYOUT_SHIFT,
                            "Following content moved by a significant distance.",
                            FallbackWarningSeverity.WARNING,
                        )
                    )
                return finish(
                    LayoutFallbackStep.MOVE_BLOCK,
                    resolved=True,
                    page_id=current_page,
                    box=moved_box,
                    style=current_style,
                    measurement=measurement,
                    fragments=_fragment(
                        request, current_page, moved_box, LayoutFallbackStep.MOVE_BLOCK
                    ),
                    moved=moved,
                )
        else:
            attempts.append(
                FallbackAttempt(
                    step=LayoutFallbackStep.MOVE_BLOCK,
                    resolved=False,
                    page_id=current_page,
                    bounds=current_box,
                    style=current_style,
                    measurement=measurement,
                    reason="No safe movable following block could make room.",
                )
            )

        if settings.allow_reflow:
            reflow_box = cast(BoundingBox, request.safe_bounds)
            fits, measurement = evaluate(
                LayoutFallbackStep.REFLOW,
                reflow_box,
                current_style,
                page_id=current_page,
                reason="The block was reflowed inside the safe page region.",
            )
            if fits:
                return finish(
                    LayoutFallbackStep.REFLOW,
                    resolved=True,
                    page_id=current_page,
                    box=reflow_box,
                    style=current_style,
                    measurement=measurement,
                    fragments=_fragment(
                        request, current_page, reflow_box, LayoutFallbackStep.REFLOW
                    ),
                )
        else:
            attempts.append(
                FallbackAttempt(
                    step=LayoutFallbackStep.REFLOW,
                    resolved=False,
                    page_id=current_page,
                    bounds=current_box,
                    style=current_style,
                    measurement=measurement,
                    reason="Reflow was disabled by settings.",
                )
            )

        if settings.allow_next_page:
            next_bounds = request.next_page_bounds
            if next_bounds is not None:
                next_page_id = request.next_page_id or f"{current_page}-next"
                fits, measurement = evaluate(
                    LayoutFallbackStep.NEXT_PAGE,
                    next_bounds,
                    current_style,
                    page_id=next_page_id,
                    reason="The complete block was moved to the next available page.",
                )
                if fits:
                    return finish(
                        LayoutFallbackStep.NEXT_PAGE,
                        resolved=True,
                        page_id=next_page_id,
                        box=next_bounds,
                        style=current_style,
                        measurement=measurement,
                        fragments=_fragment(
                            request, next_page_id, next_bounds, LayoutFallbackStep.NEXT_PAGE
                        ),
                    )
            else:
                _unresolved_attempt(
                    attempts,
                    LayoutFallbackStep.NEXT_PAGE,
                    current_page,
                    current_box,
                    current_style,
                    measurement,
                    "No next-page bounds were provided.",
                )
        else:
            _unresolved_attempt(
                attempts,
                LayoutFallbackStep.NEXT_PAGE,
                current_page,
                current_box,
                current_style,
                measurement,
                "Next-page fallback was disabled by settings.",
            )

        if settings.allow_page_addition and settings.max_added_pages > 0:
            page_template = cast(BoundingBox, request.next_page_bounds or request.page_bounds)
            page_id_prefix = request.next_page_id or current_page
            paginated = _paginate_text(
                request.text,
                page_template,
                page_id_prefix,
                request.font,
                current_style,
                measurer,
                settings.max_added_pages,
            )
            if paginated is not None:
                fragments, final_measurement = paginated
                warnings.append(
                    _warning(
                        request,
                        FallbackWarningCode.PAGE_ADDED_DUE_TO_TRANSLATION_EXPANSION,
                        "Additional page(s) were added to preserve all translated text.",
                        FallbackWarningSeverity.INFO,
                    )
                )
                return finish(
                    LayoutFallbackStep.ADD_PAGE,
                    resolved=True,
                    page_id=fragments[0].page_id,
                    box=fragments[0].bounds,
                    style=current_style,
                    measurement=final_measurement,
                    fragments=fragments,
                )
        else:
            _unresolved_attempt(
                attempts,
                LayoutFallbackStep.ADD_PAGE,
                current_page,
                current_box,
                current_style,
                measurement,
                "Page addition was disabled or exhausted its configured limit.",
            )

        warnings.extend(
            (
                _warning(
                    request,
                    FallbackWarningCode.TEXT_OVERFLOW_UNRESOLVED,
                    "Translated text still exceeds every configured layout region.",
                    FallbackWarningSeverity.CRITICAL,
                ),
                _warning(
                    request,
                    FallbackWarningCode.MANUAL_REVIEW_REQUIRED,
                    "Automatic placement stopped; manual review is required.",
                    FallbackWarningSeverity.CRITICAL,
                ),
            )
        )
        manual_fragment = LayoutFragment(
            page_id=current_page,
            text=request.text,
            bounds=current_box,
            step=LayoutFallbackStep.MANUAL_REVIEW,
            renderable=False,
        )
        return finish(
            LayoutFallbackStep.MANUAL_REVIEW,
            resolved=False,
            page_id=current_page,
            box=current_box,
            style=current_style,
            measurement=measurement,
            fragments=(manual_fragment,),
            moved=moved_blocks,
        )

    def apply(self, request: LayoutFallbackRequest) -> LayoutFallbackResult:
        """Alias for callers that describe the chain as an applied policy."""

        return self.resolve(request)

    def run(self, request: LayoutFallbackRequest) -> LayoutFallbackResult:
        """Alias for pipeline runners that use ``run`` as their entrypoint."""

        return self.resolve(request)


LayoutFallbackChain = LayoutFallbackEngine
FallbackEngine = LayoutFallbackEngine
FallbackResult = LayoutFallbackResult


def resolve_layout_fallback(
    request: LayoutFallbackRequest,
    *,
    engine: LayoutFallbackEngine | None = None,
) -> LayoutFallbackResult:
    """Resolve one request using the documented fallback order."""

    return (engine or LayoutFallbackEngine()).resolve(request)


apply_layout_fallback = resolve_layout_fallback
fallback_layout = resolve_layout_fallback


def _fits(measurement: TextMeasurement, box: BoundingBox) -> bool:
    return (
        measurement.width_pt <= box.width + LayoutFallbackEngine._TOLERANCE
        and measurement.height_pt <= box.height + LayoutFallbackEngine._TOLERANCE
    )


def _expand_box(
    current: BoundingBox,
    safe: BoundingBox,
    ratio: float,
) -> BoundingBox:
    x = max(safe.x, min(current.x, safe.right - current.width))
    y = max(safe.y, min(current.y, safe.bottom - current.height))
    width = min(safe.right - x, max(current.width, current.width * ratio))
    height = min(safe.bottom - y, max(current.height, current.height * ratio))
    return BoundingBox(x, y, max(current.width, width), max(current.height, height))


def _heightened_box(
    current: BoundingBox,
    extra_height: float,
    safe: BoundingBox,
) -> BoundingBox | None:
    if extra_height <= 0:
        return None
    height = current.height + extra_height
    if current.y < safe.y or current.y + height > safe.bottom + LayoutFallbackEngine._TOLERANCE:
        return None
    return BoundingBox(current.x, current.y, current.width, height)


def _move_following_blocks(
    blocks: tuple[LayoutBlock, ...],
    required: float,
    page: BoundingBox,
    max_move: float,
) -> tuple[tuple[LayoutBlock, ...] | None, float]:
    if required <= 0 or required > max_move or not blocks:
        return None, 0.0
    moved: list[LayoutBlock] = []
    for block in blocks:
        if block.fixed:
            return None, 0.0
        shifted = BoundingBox(
            block.bounds.x,
            block.bounds.y - required,
            block.bounds.width,
            block.bounds.height,
        )
        if not page.contains(shifted):
            return None, 0.0
        moved.append(LayoutBlock(block.block_id, shifted, fixed=block.fixed))
    return tuple(moved), required


def _fragment(
    request: LayoutFallbackRequest,
    page_id: str,
    bounds: BoundingBox,
    step: LayoutFallbackStep,
) -> tuple[LayoutFragment, ...]:
    return (
        LayoutFragment(
            page_id=page_id,
            text=request.text,
            bounds=bounds,
            step=step,
        ),
    )


def _warning(
    request: LayoutFallbackRequest,
    code: FallbackWarningCode,
    message: str,
    severity: FallbackWarningSeverity,
) -> FallbackWarning:
    return FallbackWarning(code, message, severity, request.block_id)


def _unresolved_attempt(
    attempts: list[FallbackAttempt],
    step: LayoutFallbackStep,
    page_id: str,
    bounds: BoundingBox,
    style: TextStyle,
    measurement: TextMeasurement | None,
    reason: str,
) -> None:
    attempts.append(
        FallbackAttempt(
            step=step,
            resolved=False,
            page_id=page_id,
            bounds=bounds,
            style=style,
            measurement=measurement,
            reason=reason,
        )
    )


def _paginate_text(
    text: str,
    page_bounds: BoundingBox,
    page_id_prefix: str,
    font: FontInput,
    style: TextStyle,
    measurer: TextMeasurer,
    max_pages: int,
) -> tuple[tuple[LayoutFragment, ...], TextMeasurement] | None:
    if max_pages < 1:
        return None
    remaining = text
    fragments: list[LayoutFragment] = []
    final_measurement: TextMeasurement | None = None
    for page_number in range(1, max_pages + 1):
        page_id = f"{page_id_prefix}-added-{page_number}"
        if not remaining:
            break
        measurement = measurer.measure(
            remaining,
            font=font,
            style=style,
            max_width_pt=page_bounds.width,
        )
        if _fits(measurement, page_bounds):
            piece = remaining
        else:
            cut = _largest_fitting_prefix(
                remaining,
                page_bounds,
                font,
                style,
                measurer,
            )
            if cut <= 0:
                return None
            piece = remaining[:cut]
        piece_measurement = measurer.measure(
            piece,
            font=font,
            style=style,
            max_width_pt=page_bounds.width,
        )
        if not _fits(piece_measurement, page_bounds):
            return None
        fragments.append(
            LayoutFragment(
                page_id=page_id,
                text=piece,
                bounds=page_bounds,
                step=LayoutFallbackStep.ADD_PAGE,
                fragment_order=page_number,
            )
        )
        final_measurement = piece_measurement
        remaining = remaining[len(piece) :]
    if remaining or not fragments or final_measurement is None:
        return None
    return tuple(fragments), final_measurement


def _largest_fitting_prefix(
    text: str,
    bounds: BoundingBox,
    font: FontInput,
    style: TextStyle,
    measurer: TextMeasurer,
) -> int:
    low, high = 1, len(text)
    best = 0
    while low <= high:
        middle = (low + high) // 2
        measurement = measurer.measure(
            text[:middle],
            font=font,
            style=style,
            max_width_pt=bounds.width,
        )
        if _fits(measurement, bounds):
            best = middle
            low = middle + 1
        else:
            high = middle - 1
    if best <= 0:
        return 0
    boundary = max(
        (index for index in range(1, best + 1) if text[index - 1].isspace()),
        default=best,
    )
    return boundary or best
