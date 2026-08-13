import random

import pytest
from transloka_translation.batching import (
    BatchContext,
    BatchLimits,
    BatchSegment,
    DuplicateSegmentError,
    TranslationBatchBuilder,
    TranslationBatchError,
    build_translation_batches,
    estimate_tokens,
)


def make_segment(
    index: int,
    *,
    section_id: str = "section_001",
    section_order: int = 0,
    source_text: str | None = None,
    context: BatchContext | None = None,
    locked: bool = False,
) -> BatchSegment:
    return BatchSegment(
        segment_id=f"segment_{index:03d}",
        section_id=section_id,
        section_order=section_order,
        page_order=index // 5,
        block_order=index,
        segment_order=0,
        source_text=source_text or f"Source segment {index}.",
        context=context or BatchContext(),
        locked=locked,
    )


@pytest.mark.parametrize("count", [1, 5, 10, 20])
def test_supported_batch_sizes_remain_in_one_ordered_batch(count: int) -> None:
    segments = tuple(make_segment(index) for index in range(count))

    plan = build_translation_batches(
        reversed(segments),
        limits=BatchLimits(max_segments=20, max_input_tokens=10_000),
    )

    assert len(plan.batches) == 1
    assert plan.batches[0].segment_ids == tuple(segment.segment_id for segment in segments)
    assert plan.batches[0].batch_index == 0


def test_maximum_segment_count_splits_without_changing_order() -> None:
    segments = tuple(make_segment(index) for index in range(21))

    plan = build_translation_batches(
        segments,
        limits=BatchLimits(max_segments=20, max_input_tokens=10_000),
    )

    assert [len(batch.segments) for batch in plan.batches] == [20, 1]
    assert plan.segment_ids == tuple(segment.segment_id for segment in segments)


def test_long_segment_is_isolated_and_marked_as_input_overflow() -> None:
    def estimator(text: str) -> int:
        return len(text)

    segments = (
        make_segment(0, source_text="short"),
        make_segment(1, source_text="x" * 101),
        make_segment(2, source_text="short"),
    )

    plan = build_translation_batches(
        segments,
        limits=BatchLimits(max_segments=20, max_input_tokens=100),
        token_estimator=estimator,
    )

    assert [batch.segment_ids for batch in plan.batches] == [
        ("segment_000",),
        ("segment_001",),
        ("segment_002",),
    ]
    assert [batch.exceeds_input_limit for batch in plan.batches] == [False, True, False]


def test_locked_segments_are_excluded_and_reported_in_document_order() -> None:
    segments = (
        make_segment(2),
        make_segment(0, locked=True),
        make_segment(1),
        make_segment(3, locked=True),
    )

    plan = build_translation_batches(segments)

    assert plan.segment_ids == ("segment_001", "segment_002")
    assert plan.excluded_locked_segment_ids == ("segment_000", "segment_003")
    assert all(not segment.locked for batch in plan.batches for segment in batch.segments)


def test_mixed_sections_form_separate_batches_in_section_order() -> None:
    segments = (
        make_segment(3, section_id="section_b", section_order=1),
        make_segment(1, section_id="section_a", section_order=0),
        make_segment(2, section_id="section_b", section_order=1),
        make_segment(0, section_id="section_a", section_order=0),
    )

    plan = build_translation_batches(segments)

    assert [batch.section_id for batch in plan.batches] == ["section_a", "section_b"]
    assert [batch.segment_ids for batch in plan.batches] == [
        ("segment_000", "segment_001"),
        ("segment_002", "segment_003"),
    ]


def test_input_token_estimate_splits_before_overflow() -> None:
    segments = tuple(make_segment(index, source_text="x" * 6) for index in range(3))

    plan = build_translation_batches(
        segments,
        limits=BatchLimits(max_segments=20, max_input_tokens=10),
        token_estimator=len,
    )

    assert [batch.estimated_input_tokens for batch in plan.batches] == [6, 6, 6]
    assert not any(batch.exceeds_input_limit for batch in plan.batches)


def test_context_length_contributes_to_estimate_and_batch_split() -> None:
    context = BatchContext(heading="head", previous_text="before", next_text="after")
    segments = tuple(make_segment(index, source_text="text", context=context) for index in range(2))

    plan = build_translation_batches(
        segments,
        limits=BatchLimits(
            max_segments=20,
            max_input_tokens=100,
            max_context_tokens=20,
        ),
        token_estimator=len,
    )

    assert [batch.estimated_context_tokens for batch in plan.batches] == [15, 15]
    assert [batch.estimated_input_tokens for batch in plan.batches] == [19, 19]
    assert not any(batch.exceeds_context_limit for batch in plan.batches)


def test_single_context_overflow_is_isolated_and_explicit() -> None:
    context = BatchContext(previous_text="x" * 11)

    plan = build_translation_batches(
        (make_segment(0, context=context), make_segment(1)),
        limits=BatchLimits(
            max_segments=20,
            max_input_tokens=100,
            max_context_tokens=10,
        ),
        token_estimator=len,
    )

    assert plan.batches[0].segment_ids == ("segment_000",)
    assert plan.batches[0].exceeds_context_limit is True
    assert plan.batches[1].segment_ids == ("segment_001",)


def test_duplicate_segment_id_is_rejected_even_when_one_copy_is_locked() -> None:
    duplicate = make_segment(1)
    locked_duplicate = make_segment(1, locked=True)

    with pytest.raises(DuplicateSegmentError, match="segment_001"):
        build_translation_batches((duplicate, locked_duplicate))


def test_batch_order_is_deterministic_for_arbitrary_input_order() -> None:
    segments = [make_segment(index) for index in range(20)]
    expected = build_translation_batches(segments)

    random.Random(20260813).shuffle(segments)
    actual = build_translation_batches(segments)

    assert actual == expected


def test_token_estimator_is_deterministic_and_utf8_aware() -> None:
    assert estimate_tokens("") == 0
    assert estimate_tokens("abcd") == 1
    assert estimate_tokens("日本語") == 3
    assert estimate_tokens("日本語") == estimate_tokens("日本語")


def test_invalid_estimator_result_is_rejected() -> None:
    builder = TranslationBatchBuilder(token_estimator=lambda _text: -1)

    with pytest.raises(TranslationBatchError, match="non-negative integer"):
        builder.build((make_segment(0),))


def test_inconsistent_or_duplicate_section_order_is_rejected() -> None:
    inconsistent = (
        make_segment(0, section_id="section_a", section_order=0),
        make_segment(1, section_id="section_a", section_order=1),
    )
    duplicate_order = (
        make_segment(0, section_id="section_a", section_order=0),
        make_segment(1, section_id="section_b", section_order=0),
    )

    with pytest.raises(TranslationBatchError, match="inconsistent section order"):
        build_translation_batches(inconsistent)
    with pytest.raises(TranslationBatchError, match="multiple sections"):
        build_translation_batches(duplicate_order)
