import re
import unicodedata
from collections import Counter
from collections.abc import Iterable
from dataclasses import dataclass, field
from enum import StrEnum

_WORD_PATTERN = re.compile(r"[^\W\d_][\w]*(?:['\N{RIGHT SINGLE QUOTATION MARK}-][^\W\d_][\w]*)?")
_TECHNICAL_IDENTIFIER_PATTERN = re.compile(
    r"(?<![\w])(?:"
    r"[A-Za-z][A-Za-z0-9]*_[A-Za-z0-9_]+"
    r"|[a-z]+(?:[A-Z][A-Za-z0-9]*)+"
    r"|[A-Z][a-z0-9]+(?:[A-Z][A-Za-z0-9]*)+"
    r"|[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)+"
    r"|[A-Z]{2,}[A-Z0-9]*"
    r")(?:\(\))?(?![\w])"
)
_CONTIGUOUS_WORD_GAP = re.compile(r"[\s-]+")

_DEFAULT_COMMON_WORDS = frozenset(
    {
        "a",
        "an",
        "and",
        "atau",
        "dalam",
        "dan",
        "dari",
        "di",
        "for",
        "from",
        "in",
        "is",
        "itu",
        "ke",
        "of",
        "on",
        "or",
        "pada",
        "the",
        "to",
        "untuk",
        "yang",
    }
)


class CandidateType(StrEnum):
    REPEATED_PHRASE = "REPEATED_PHRASE"
    NAMED_ENTITY = "NAMED_ENTITY"
    TECHNICAL_IDENTIFIER = "TECHNICAL_IDENTIFIER"


class InvalidCandidateDetectionInputError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class CandidateSourceSegment:
    segment_id: str
    source_text: str

    def __post_init__(self) -> None:
        if (
            not isinstance(self.segment_id, str)
            or not self.segment_id.strip()
            or self.segment_id != self.segment_id.strip()
            or not self.segment_id.isprintable()
        ):
            raise InvalidCandidateDetectionInputError(
                "Candidate detection requires a stable segment identifier."
            )
        if not isinstance(self.source_text, str):
            raise InvalidCandidateDetectionInputError(
                "Candidate detection requires source text for every segment."
            )


@dataclass(frozen=True, slots=True)
class CandidateOccurrence:
    segment_id: str
    start_offset: int
    end_offset: int
    matched_text: str

    def __post_init__(self) -> None:
        if self.start_offset < 0 or self.end_offset <= self.start_offset:
            raise InvalidCandidateDetectionInputError("Candidate occurrence offsets are invalid.")
        if not self.matched_text or not self.matched_text.strip():
            raise InvalidCandidateDetectionInputError("Candidate occurrence text is invalid.")


@dataclass(frozen=True, slots=True)
class TermCandidate:
    source_term: str
    normalized_source_term: str
    candidate_type: CandidateType
    occurrence_count: int
    confidence: float
    occurrences: tuple[CandidateOccurrence, ...]

    def __post_init__(self) -> None:
        if not self.source_term or not self.normalized_source_term:
            raise InvalidCandidateDetectionInputError("Candidate source terms cannot be empty.")
        if self.occurrence_count != len(self.occurrences) or self.occurrence_count < 1:
            raise InvalidCandidateDetectionInputError("Candidate occurrence count is inconsistent.")
        if not 0.0 <= self.confidence <= 1.0:
            raise InvalidCandidateDetectionInputError("Candidate confidence is invalid.")


@dataclass(frozen=True, slots=True)
class _Word:
    value: str
    start_offset: int
    end_offset: int


@dataclass(slots=True)
class _CandidateAccumulator:
    variants: Counter[str] = field(default_factory=Counter)
    signals: set[CandidateType] = field(default_factory=set)
    occurrences: dict[tuple[str, int, int], CandidateOccurrence] = field(default_factory=dict)


class TermCandidateDetector:
    def __init__(
        self,
        *,
        minimum_occurrences: int = 2,
        minimum_phrase_words: int = 2,
        maximum_phrase_words: int = 4,
        common_words: Iterable[str] = _DEFAULT_COMMON_WORDS,
    ) -> None:
        if (
            isinstance(minimum_occurrences, bool)
            or not isinstance(minimum_occurrences, int)
            or minimum_occurrences < 1
        ):
            raise InvalidCandidateDetectionInputError(
                "Minimum candidate occurrences must be a positive integer."
            )
        if (
            isinstance(minimum_phrase_words, bool)
            or not isinstance(minimum_phrase_words, int)
            or minimum_phrase_words < 2
        ):
            raise InvalidCandidateDetectionInputError(
                "Minimum phrase length must be at least two words."
            )
        if (
            isinstance(maximum_phrase_words, bool)
            or not isinstance(maximum_phrase_words, int)
            or maximum_phrase_words < minimum_phrase_words
        ):
            raise InvalidCandidateDetectionInputError(
                "Maximum phrase length must not be below the minimum."
            )

        normalized_common_words = frozenset(
            _normalize_term(word) for word in common_words if isinstance(word, str) and word.strip()
        )
        self._minimum_occurrences = minimum_occurrences
        self._minimum_phrase_words = minimum_phrase_words
        self._maximum_phrase_words = maximum_phrase_words
        self._common_words = normalized_common_words

    def detect(self, segments: Iterable[CandidateSourceSegment]) -> tuple[TermCandidate, ...]:
        materialized = tuple(segments)
        if not all(isinstance(segment, CandidateSourceSegment) for segment in materialized):
            raise InvalidCandidateDetectionInputError(
                "Every candidate detection input must be a CandidateSourceSegment."
            )

        segment_ids = [segment.segment_id for segment in materialized]
        if len(segment_ids) != len(set(segment_ids)):
            raise InvalidCandidateDetectionInputError(
                "Candidate source segment IDs must be unique."
            )

        accumulators: dict[str, _CandidateAccumulator] = {}
        for segment in sorted(materialized, key=lambda item: item.segment_id):
            self._collect_segment_candidates(segment, accumulators)

        candidates: list[TermCandidate] = []
        for normalized_term, accumulator in accumulators.items():
            occurrences = tuple(
                sorted(
                    accumulator.occurrences.values(),
                    key=lambda item: (item.segment_id, item.start_offset, item.end_offset),
                )
            )
            if len(occurrences) < self._minimum_occurrences:
                continue

            candidate_type = min(accumulator.signals, key=_candidate_type_priority)
            source_term = min(
                accumulator.variants,
                key=lambda value: (-accumulator.variants[value], value.casefold(), value),
            )
            candidates.append(
                TermCandidate(
                    source_term=source_term,
                    normalized_source_term=normalized_term,
                    candidate_type=candidate_type,
                    occurrence_count=len(occurrences),
                    confidence=_confidence(candidate_type, len(occurrences), source_term),
                    occurrences=occurrences,
                )
            )

        return tuple(
            sorted(
                candidates,
                key=lambda item: (
                    _candidate_type_priority(item.candidate_type),
                    -item.confidence,
                    -item.occurrence_count,
                    item.normalized_source_term,
                    item.source_term,
                ),
            )
        )

    def _collect_segment_candidates(
        self,
        segment: CandidateSourceSegment,
        accumulators: dict[str, _CandidateAccumulator],
    ) -> None:
        text = segment.source_text
        words = tuple(
            _Word(match.group(0), match.start(), match.end())
            for match in _WORD_PATTERN.finditer(text)
        )

        for start_index in range(len(words)):
            maximum_end = min(len(words), start_index + self._maximum_phrase_words)
            for end_index in range(start_index + self._minimum_phrase_words, maximum_end + 1):
                phrase_words = words[start_index:end_index]
                if not _words_are_contiguous(text, phrase_words):
                    break
                normalized_words = tuple(_normalize_term(word.value) for word in phrase_words)
                if self._is_common_phrase(normalized_words):
                    continue
                self._record(
                    segment,
                    phrase_words[0].start_offset,
                    phrase_words[-1].end_offset,
                    CandidateType.REPEATED_PHRASE,
                    accumulators,
                )

        for match in _TECHNICAL_IDENTIFIER_PATTERN.finditer(text):
            self._record(
                segment,
                match.start(),
                match.end(),
                CandidateType.TECHNICAL_IDENTIFIER,
                accumulators,
            )

        for start_offset, end_offset in _named_entity_spans(text, words, self._common_words):
            self._record(
                segment,
                start_offset,
                end_offset,
                CandidateType.NAMED_ENTITY,
                accumulators,
            )

    def _record(
        self,
        segment: CandidateSourceSegment,
        start_offset: int,
        end_offset: int,
        candidate_type: CandidateType,
        accumulators: dict[str, _CandidateAccumulator],
    ) -> None:
        matched_text = segment.source_text[start_offset:end_offset]
        normalized_term = _normalize_term(matched_text)
        if not normalized_term or normalized_term in self._common_words:
            return

        accumulator = accumulators.setdefault(normalized_term, _CandidateAccumulator())
        accumulator.signals.add(candidate_type)
        occurrence_key = (segment.segment_id, start_offset, end_offset)
        if occurrence_key not in accumulator.occurrences:
            accumulator.variants[matched_text] += 1
        occurrence = CandidateOccurrence(
            segment_id=segment.segment_id,
            start_offset=start_offset,
            end_offset=end_offset,
            matched_text=matched_text,
        )
        accumulator.occurrences[occurrence_key] = occurrence

    def _is_common_phrase(self, normalized_words: tuple[str, ...]) -> bool:
        return (
            not normalized_words
            or normalized_words[0] in self._common_words
            or normalized_words[-1] in self._common_words
            or all(word in self._common_words for word in normalized_words)
        )


def _named_entity_spans(
    text: str,
    words: tuple[_Word, ...],
    common_words: frozenset[str],
) -> tuple[tuple[int, int], ...]:
    spans: list[tuple[int, int]] = []
    start_index = 0
    while start_index < len(words):
        if not _is_title_case(words[start_index].value):
            start_index += 1
            continue

        end_index = start_index + 1
        while (
            end_index < len(words)
            and _is_title_case(words[end_index].value)
            and _words_are_contiguous(text, words[end_index - 1 : end_index + 1])
        ):
            end_index += 1

        entity_start = start_index
        while (
            end_index - entity_start > 2
            and _normalize_term(words[entity_start].value) in common_words
        ):
            entity_start += 1

        if end_index - entity_start >= 2:
            spans.append((words[entity_start].start_offset, words[end_index - 1].end_offset))
        start_index = end_index
    return tuple(spans)


def _is_title_case(value: str) -> bool:
    letters = tuple(character for character in value if character.isalpha())
    return (
        bool(letters) and letters[0].isupper() and all(letter.islower() for letter in letters[1:])
    )


def _words_are_contiguous(text: str, words: tuple[_Word, ...]) -> bool:
    return all(
        _CONTIGUOUS_WORD_GAP.fullmatch(text[left.end_offset : right.start_offset]) is not None
        for left, right in zip(words, words[1:], strict=False)
    )


def _normalize_term(value: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", value).split()).casefold()


def _candidate_type_priority(candidate_type: CandidateType) -> int:
    return {
        CandidateType.TECHNICAL_IDENTIFIER: 0,
        CandidateType.NAMED_ENTITY: 1,
        CandidateType.REPEATED_PHRASE: 2,
    }[candidate_type]


def _confidence(candidate_type: CandidateType, occurrence_count: int, source_term: str) -> float:
    base = {
        CandidateType.REPEATED_PHRASE: 0.55,
        CandidateType.NAMED_ENTITY: 0.75,
        CandidateType.TECHNICAL_IDENTIFIER: 0.85,
    }[candidate_type]
    occurrence_bonus = min(0.12, max(0, occurrence_count - 2) * 0.03)
    length_bonus = min(0.04, max(0, len(source_term.split()) - 1) * 0.02)
    return round(min(0.99, base + occurrence_bonus + length_bonus), 3)
