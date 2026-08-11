from itertools import permutations
from typing import Any, cast

import pytest
from transloka_glossary.candidates import (
    CandidateSourceSegment,
    CandidateType,
    InvalidCandidateDetectionInputError,
    TermCandidate,
    TermCandidateDetector,
)


def _segment(segment_id: str, source_text: str) -> CandidateSourceSegment:
    return CandidateSourceSegment(segment_id=segment_id, source_text=source_text)


def _candidate_by_term(
    source_segments: list[CandidateSourceSegment],
    term: str,
    *,
    minimum_occurrences: int = 2,
) -> TermCandidate:
    candidates = TermCandidateDetector(minimum_occurrences=minimum_occurrences).detect(
        source_segments
    )
    return next(candidate for candidate in candidates if candidate.normalized_source_term == term)


def test_repeated_phrase_records_every_occurrence_and_confidence() -> None:
    segments = [
        _segment("seg_1", "A machine learning workflow starts here."),
        _segment("seg_2", "The machine learning workflow continues."),
        _segment("seg_3", "This machine learning workflow is deterministic."),
    ]

    candidate = _candidate_by_term(segments, "machine learning workflow")

    assert candidate.source_term == "machine learning workflow"
    assert candidate.candidate_type is CandidateType.REPEATED_PHRASE
    assert candidate.occurrence_count == 3
    assert 0.0 < candidate.confidence <= 1.0
    assert [occurrence.segment_id for occurrence in candidate.occurrences] == [
        "seg_1",
        "seg_2",
        "seg_3",
    ]
    assert all(
        segment.source_text[occurrence.start_offset : occurrence.end_offset]
        == occurrence.matched_text
        for segment, occurrence in zip(segments, candidate.occurrences, strict=True)
    )


def test_common_words_are_filtered_even_when_repeated() -> None:
    segments = [
        _segment("seg_1", "in the and of to"),
        _segment("seg_2", "in the and of to"),
        _segment("seg_3", "in the and of to"),
    ]

    candidates = TermCandidateDetector().detect(segments)

    assert candidates == ()


def test_code_identifier_is_a_technical_candidate() -> None:
    segments = [
        _segment("seg_1", "Call parse_document() before rendering."),
        _segment("seg_2", "The worker retries parse_document()."),
    ]

    candidate = _candidate_by_term(segments, "parse_document()")

    assert candidate.candidate_type is CandidateType.TECHNICAL_IDENTIFIER
    assert candidate.occurrence_count == 2
    assert [occurrence.matched_text for occurrence in candidate.occurrences] == [
        "parse_document()",
        "parse_document()",
    ]


def test_repeated_capitalized_phrase_is_a_named_entity_candidate() -> None:
    segments = [
        _segment("seg_1", "The Open Source Initiative published guidance."),
        _segment("seg_2", "The Open Source Initiative welcomed members."),
    ]

    candidate = _candidate_by_term(segments, "open source initiative")

    assert candidate.source_term == "Open Source Initiative"
    assert candidate.candidate_type is CandidateType.NAMED_ENTITY
    assert candidate.confidence > 0.7


def test_minimum_occurrence_threshold_is_enforced() -> None:
    detector = TermCandidateDetector(minimum_occurrences=3)
    twice = [
        _segment("seg_1", "A deterministic workflow exists."),
        _segment("seg_2", "The deterministic workflow continues."),
    ]

    assert not any(
        candidate.normalized_source_term == "deterministic workflow"
        for candidate in detector.detect(twice)
    )

    three_times = [*twice, _segment("seg_3", "Reuse the deterministic workflow.")]
    assert (
        _candidate_by_term(
            three_times,
            "deterministic workflow",
            minimum_occurrences=3,
        ).occurrence_count
        == 3
    )


def test_detection_is_deterministic_and_does_not_create_glossary_rules() -> None:
    segments = [
        _segment("seg_b", "Use PDF with the translation memory."),
        _segment("seg_a", "Keep PDF in the translation memory."),
    ]
    detector = TermCandidateDetector()
    expected = detector.detect(segments)

    for ordering in permutations(segments):
        assert detector.detect(ordering) == expected

    assert {candidate.candidate_type for candidate in expected} == {
        CandidateType.REPEATED_PHRASE,
        CandidateType.TECHNICAL_IDENTIFIER,
    }
    assert all(not hasattr(candidate, "target_term") for candidate in expected)


@pytest.mark.parametrize(
    "values",
    [
        {"minimum_occurrences": 0},
        {"minimum_occurrences": True},
        {"minimum_phrase_words": 1},
        {"maximum_phrase_words": 1},
    ],
)
def test_invalid_configuration_is_rejected(values: dict[str, object]) -> None:
    with pytest.raises(InvalidCandidateDetectionInputError):
        cast(Any, TermCandidateDetector)(**values)


def test_invalid_or_duplicate_source_segments_are_rejected() -> None:
    with pytest.raises(InvalidCandidateDetectionInputError):
        cast(Any, CandidateSourceSegment)(segment_id="", source_text="text")
    with pytest.raises(InvalidCandidateDetectionInputError):
        cast(Any, CandidateSourceSegment)(segment_id="seg_1", source_text=123)
    with pytest.raises(InvalidCandidateDetectionInputError):
        TermCandidateDetector().detect(
            [_segment("seg_1", "first text"), _segment("seg_1", "second text")]
        )
