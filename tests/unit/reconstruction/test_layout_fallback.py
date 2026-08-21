from __future__ import annotations

from dataclasses import dataclass

import pytest
from transloka_reconstruction.fonts import FontCategory, FontDescriptor
from transloka_reconstruction.layout.fallback import (
    FallbackWarningCode,
    LayoutBlock,
    LayoutFallbackEngine,
    LayoutFallbackRequest,
    LayoutFallbackSettings,
    LayoutFallbackStep,
)
from transloka_reconstruction.layout.measurement import FontMetrics, TextMeasurer, TextStyle
from transloka_reconstruction.layout.overflow import BoundingBox


@dataclass(frozen=True)
class FakeFontMetrics:
    font_size_pt: float

    def getlength(self, text: str) -> float:
        return len(text) * self.font_size_pt * 0.5

    def getbbox(self, text: str) -> tuple[float, float, float, float]:
        return (0.0, 0.0, self.getlength(text), self.font_size_pt)


def _font() -> FontDescriptor:
    return FontDescriptor(family_name="Fallback Sans", category=FontCategory.SANS_SERIF)


def _measurer() -> TextMeasurer:
    def loader(font: FontDescriptor, style: TextStyle) -> FontMetrics:
        return FakeFontMetrics(style.font_size_pt)

    return TextMeasurer(font_loader=loader)


def _request(
    text: str,
    bounds: BoundingBox,
    *,
    page_bounds: BoundingBox | None = None,
    safe_bounds: BoundingBox | None = None,
    style: TextStyle | None = None,
    settings: LayoutFallbackSettings | None = None,
    following_blocks: tuple[LayoutBlock, ...] = (),
    next_page_bounds: BoundingBox | None = None,
    next_page_id: str | None = None,
) -> LayoutFallbackRequest:
    return LayoutFallbackRequest(
        block_id="block-1",
        text=text,
        bounds=bounds,
        page_bounds=page_bounds,
        safe_bounds=safe_bounds,
        style=style or TextStyle(font_size_pt=10, line_height_multiplier=1.0),
        font=_font(),
        settings=settings or LayoutFallbackSettings(),
        following_blocks=following_blocks,
        next_page_bounds=next_page_bounds,
        next_page_id=next_page_id,
        measurer=_measurer(),
    )


def test_wrap_is_the_first_successful_fallback_step() -> None:
    result = LayoutFallbackEngine().resolve(_request("short", BoundingBox(0, 0, 100, 20)))

    assert result.resolved
    assert result.step is LayoutFallbackStep.WRAP
    assert result.text_preserved
    assert [attempt.step for attempt in result.attempts] == [LayoutFallbackStep.WRAP]


def test_expand_box_resolves_before_spacing_or_font_changes() -> None:
    result = LayoutFallbackEngine().resolve(
        _request(
            "one two",
            BoundingBox(0, 0, 20, 10),
            page_bounds=BoundingBox(0, 0, 100, 50),
            settings=LayoutFallbackSettings(max_box_expansion_ratio=3),
        )
    )

    assert result.resolved
    assert result.step is LayoutFallbackStep.EXPAND_BOX
    assert result.bounds.height > 10
    assert result.style.font_size_pt == 10


def test_reduce_spacing_preserves_font_and_text() -> None:
    result = LayoutFallbackEngine().resolve(
        _request(
            "one\ntwo",
            BoundingBox(0, 0, 30, 22),
            settings=LayoutFallbackSettings(max_box_expansion_ratio=1),
            style=TextStyle(
                font_size_pt=10,
                line_height_multiplier=1.0,
                paragraph_spacing_pt=10,
            ),
        )
    )

    assert result.resolved
    assert result.step is LayoutFallbackStep.REDUCE_SPACING
    assert result.style.paragraph_spacing_pt == 0
    assert result.text_preserved


def test_reduce_font_respects_configured_reduction_and_minimum() -> None:
    result = LayoutFallbackEngine().resolve(
        _request(
            "one two",
            BoundingBox(0, 0, 30, 18),
            settings=LayoutFallbackSettings(
                max_box_expansion_ratio=1,
                max_font_reduction=0.20,
                minimum_font_size_pt=8,
            ),
        )
    )

    assert result.resolved
    assert result.step is LayoutFallbackStep.REDUCE_FONT
    assert result.font_size_pt == pytest.approx(8)
    assert all(
        attempt.style.font_size_pt >= 8
        for attempt in result.attempts
        if attempt.measurement is not None
    )


def test_move_block_shifts_only_movable_following_content() -> None:
    following = LayoutBlock("block-2", BoundingBox(0, 20, 30, 10))
    result = LayoutFallbackEngine().resolve(
        _request(
            "one two",
            BoundingBox(0, 50, 30, 10),
            page_bounds=BoundingBox(0, 0, 100, 100),
            settings=LayoutFallbackSettings(max_box_expansion_ratio=1, max_font_reduction=0),
            following_blocks=(following,),
        )
    )

    assert result.resolved
    assert result.step is LayoutFallbackStep.MOVE_BLOCK
    assert result.moved_blocks[0].bounds.y == 10


def test_reflow_uses_the_safe_region_before_paging() -> None:
    result = LayoutFallbackEngine().resolve(
        _request(
            "one two three four five",
            BoundingBox(0, 0, 20, 10),
            page_bounds=BoundingBox(0, 0, 100, 100),
            safe_bounds=BoundingBox(0, 0, 100, 100),
            settings=LayoutFallbackSettings(max_box_expansion_ratio=1),
        )
    )

    assert result.resolved
    assert result.step is LayoutFallbackStep.REFLOW
    assert result.bounds.width == 100


def test_next_page_keeps_the_same_block_text_and_page_identity() -> None:
    result = LayoutFallbackEngine().resolve(
        _request(
            "one two three four",
            BoundingBox(0, 0, 30, 15),
            page_bounds=BoundingBox(0, 0, 30, 15),
            next_page_bounds=BoundingBox(0, 0, 100, 100),
            next_page_id="page-2",
            settings=LayoutFallbackSettings(max_box_expansion_ratio=1),
        )
    )

    assert result.resolved
    assert result.step is LayoutFallbackStep.NEXT_PAGE
    assert result.page_id == "page-2"
    assert result.fragments[0].page_id == "page-2"
    assert result.text_preserved


def test_page_addition_splits_text_without_loss() -> None:
    text = "one two three four five six seven eight nine ten eleven twelve"
    result = LayoutFallbackEngine().resolve(
        _request(
            text,
            BoundingBox(0, 0, 30, 15),
            page_bounds=BoundingBox(0, 0, 30, 15),
            settings=LayoutFallbackSettings(max_box_expansion_ratio=1, max_added_pages=15),
        )
    )

    assert result.resolved
    assert result.step is LayoutFallbackStep.ADD_PAGE
    assert len(result.fragments) > 1
    assert "".join(fragment.text for fragment in result.fragments) == text
    assert any(
        warning.code is FallbackWarningCode.PAGE_ADDED_DUE_TO_TRANSLATION_EXPANSION
        for warning in result.warnings
    )


def test_unresolved_overflow_requires_critical_manual_review() -> None:
    result = LayoutFallbackEngine().resolve(
        _request(
            "one two three four five six",
            BoundingBox(0, 0, 20, 5),
            page_bounds=BoundingBox(0, 0, 20, 5),
            settings=LayoutFallbackSettings(
                max_box_expansion_ratio=1,
                max_font_reduction=0,
                allow_reflow=False,
                allow_next_page=False,
                allow_page_addition=False,
                max_added_pages=0,
            ),
        )
    )

    assert result.resolved is False
    assert result.step is LayoutFallbackStep.MANUAL_REVIEW
    assert result.needs_review
    assert result.blocks_export
    assert result.text_preserved
    assert result.fragments[0].renderable is False
    assert {attempt.step for attempt in result.attempts} == {
        LayoutFallbackStep.WRAP,
        LayoutFallbackStep.EXPAND_BOX,
        LayoutFallbackStep.REDUCE_SPACING,
        LayoutFallbackStep.REDUCE_FONT,
        LayoutFallbackStep.MOVE_BLOCK,
        LayoutFallbackStep.REFLOW,
        LayoutFallbackStep.NEXT_PAGE,
        LayoutFallbackStep.ADD_PAGE,
    }
    assert any(
        warning.code is FallbackWarningCode.TEXT_OVERFLOW_UNRESOLVED for warning in result.warnings
    )
