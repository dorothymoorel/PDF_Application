from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass

type TokenEstimator = Callable[[str], int]


class TranslationBatchError(ValueError):
    """Raised when translation batch input or limits are invalid."""


class DuplicateSegmentError(TranslationBatchError):
    """Raised when one segment is submitted more than once."""


@dataclass(frozen=True, slots=True)
class BatchContext:
    heading: str | None = None
    previous_text: str | None = None
    next_text: str | None = None

    def __post_init__(self) -> None:
        for field_name in ("heading", "previous_text", "next_text"):
            value = getattr(self, field_name)
            if value is not None and (type(value) is not str or not value.strip()):
                raise TranslationBatchError(
                    f"Batch context {field_name} must be a non-empty string or None."
                )

    @property
    def text_parts(self) -> tuple[str, ...]:
        return tuple(
            value
            for value in (self.heading, self.previous_text, self.next_text)
            if value is not None
        )


@dataclass(frozen=True, slots=True)
class BatchSegment:
    segment_id: str
    section_id: str | None
    section_order: int
    page_order: int
    block_order: int
    segment_order: int
    source_text: str
    context: BatchContext = BatchContext()
    locked: bool = False

    def __post_init__(self) -> None:
        if type(self.segment_id) is not str or not self.segment_id.strip():
            raise TranslationBatchError("Batch segment ID must be a non-empty string.")
        if self.section_id is not None and (
            type(self.section_id) is not str or not self.section_id.strip()
        ):
            raise TranslationBatchError("Batch section ID must be a non-empty string or None.")
        for field_name in ("section_order", "page_order", "block_order", "segment_order"):
            value = getattr(self, field_name)
            if type(value) is not int or value < 0:
                raise TranslationBatchError(f"Batch segment {field_name} must be non-negative.")
        if type(self.source_text) is not str or not self.source_text.strip():
            raise TranslationBatchError("Batch source text must be a non-empty string.")
        if type(self.context) is not BatchContext:
            raise TranslationBatchError("Batch segment context must be a BatchContext.")
        if type(self.locked) is not bool:
            raise TranslationBatchError("Batch segment locked flag must be boolean.")

    @property
    def order_key(self) -> tuple[int, int, int, int, str]:
        return (
            self.section_order,
            self.page_order,
            self.block_order,
            self.segment_order,
            self.segment_id,
        )

    @property
    def section_key(self) -> tuple[int, str | None]:
        return (self.section_order, self.section_id)


@dataclass(frozen=True, slots=True)
class BatchLimits:
    max_segments: int = 20
    max_input_tokens: int = 6000
    max_context_tokens: int | None = None

    def __post_init__(self) -> None:
        if type(self.max_segments) is not int or self.max_segments < 1:
            raise TranslationBatchError("max_segments must be a positive integer.")
        if type(self.max_input_tokens) is not int or self.max_input_tokens < 1:
            raise TranslationBatchError("max_input_tokens must be a positive integer.")
        if self.max_context_tokens is not None and (
            type(self.max_context_tokens) is not int or self.max_context_tokens < 0
        ):
            raise TranslationBatchError(
                "max_context_tokens must be a non-negative integer or None."
            )


@dataclass(frozen=True, slots=True)
class TranslationBatch:
    batch_index: int
    section_id: str | None
    segments: tuple[BatchSegment, ...]
    estimated_input_tokens: int
    estimated_context_tokens: int
    exceeds_input_limit: bool
    exceeds_context_limit: bool

    def __post_init__(self) -> None:
        if type(self.batch_index) is not int or self.batch_index < 0:
            raise TranslationBatchError("Batch index must be non-negative.")
        if type(self.segments) is not tuple or not self.segments:
            raise TranslationBatchError("Translation batch must contain segments.")
        if any(type(segment) is not BatchSegment for segment in self.segments):
            raise TranslationBatchError("Translation batch contains an invalid segment.")
        if any(segment.locked for segment in self.segments):
            raise TranslationBatchError("Translation batch cannot contain locked segments.")
        if any(segment.section_id != self.section_id for segment in self.segments):
            raise TranslationBatchError("Translation batch cannot mix sections.")
        if tuple(sorted(self.segments, key=lambda segment: segment.order_key)) != self.segments:
            raise TranslationBatchError("Translation batch segments must be ordered.")
        if len(self.segment_ids) != len(set(self.segment_ids)):
            raise DuplicateSegmentError("Translation batch contains duplicate segment IDs.")
        for field_name in ("estimated_input_tokens", "estimated_context_tokens"):
            value = getattr(self, field_name)
            if type(value) is not int or value < 0:
                raise TranslationBatchError(f"{field_name} must be non-negative.")
        if (
            type(self.exceeds_input_limit) is not bool
            or type(self.exceeds_context_limit) is not bool
        ):
            raise TranslationBatchError("Translation batch overflow flags must be boolean.")

    @property
    def segment_ids(self) -> tuple[str, ...]:
        return tuple(segment.segment_id for segment in self.segments)


@dataclass(frozen=True, slots=True)
class TranslationBatchPlan:
    batches: tuple[TranslationBatch, ...]
    excluded_locked_segment_ids: tuple[str, ...]

    @property
    def segment_ids(self) -> tuple[str, ...]:
        return tuple(segment_id for batch in self.batches for segment_id in batch.segment_ids)


@dataclass(frozen=True, slots=True)
class _EstimatedSegment:
    segment: BatchSegment
    source_tokens: int
    context_tokens: int

    @property
    def input_tokens(self) -> int:
        return self.source_tokens + self.context_tokens


class TranslationBatchBuilder:
    def __init__(
        self,
        limits: BatchLimits | None = None,
        *,
        token_estimator: TokenEstimator | None = None,
    ) -> None:
        self._limits = limits if limits is not None else BatchLimits()
        if type(self._limits) is not BatchLimits:
            raise TypeError("Translation batch limits must be BatchLimits.")
        self._token_estimator = token_estimator or estimate_tokens
        if not callable(self._token_estimator):
            raise TypeError("Token estimator must be callable.")

    @property
    def limits(self) -> BatchLimits:
        return self._limits

    def build(self, segments: Iterable[BatchSegment]) -> TranslationBatchPlan:
        if isinstance(segments, (str, bytes)):
            raise TypeError("Translation batch input must be an iterable of BatchSegment.")
        try:
            candidates = tuple(segments)
        except TypeError as error:
            raise TypeError(
                "Translation batch input must be an iterable of BatchSegment."
            ) from error
        if any(type(segment) is not BatchSegment for segment in candidates):
            raise TypeError("Translation batch input must contain only BatchSegment values.")

        _reject_duplicate_ids(candidates)
        _validate_section_order(candidates)
        ordered = tuple(sorted(candidates, key=lambda segment: segment.order_key))
        excluded = tuple(segment.segment_id for segment in ordered if segment.locked)
        eligible = tuple(segment for segment in ordered if not segment.locked)
        estimated = tuple(self._estimate(segment) for segment in eligible)

        batches: list[TranslationBatch] = []
        current: list[_EstimatedSegment] = []
        for item in estimated:
            if self._must_isolate(item):
                self._flush(current, batches)
                batches.append(self._make_batch((item,), len(batches)))
                continue
            if current and self._cannot_append(current, item):
                self._flush(current, batches)
            current.append(item)
        self._flush(current, batches)

        return TranslationBatchPlan(
            batches=tuple(batches),
            excluded_locked_segment_ids=excluded,
        )

    def _estimate(self, segment: BatchSegment) -> _EstimatedSegment:
        source_tokens = self._estimate_text(segment.source_text)
        context_tokens = sum(self._estimate_text(part) for part in segment.context.text_parts)
        return _EstimatedSegment(
            segment=segment,
            source_tokens=source_tokens,
            context_tokens=context_tokens,
        )

    def _estimate_text(self, text: str) -> int:
        value = self._token_estimator(text)
        if type(value) is not int or value < 0:
            raise TranslationBatchError("Token estimator must return a non-negative integer.")
        return value

    def _must_isolate(self, item: _EstimatedSegment) -> bool:
        return item.input_tokens > self._limits.max_input_tokens or (
            self._limits.max_context_tokens is not None
            and item.context_tokens > self._limits.max_context_tokens
        )

    def _cannot_append(
        self,
        current: list[_EstimatedSegment],
        item: _EstimatedSegment,
    ) -> bool:
        if current[0].segment.section_key != item.segment.section_key:
            return True
        if len(current) >= self._limits.max_segments:
            return True
        if sum(candidate.input_tokens for candidate in current) + item.input_tokens > (
            self._limits.max_input_tokens
        ):
            return True
        return self._limits.max_context_tokens is not None and (
            sum(candidate.context_tokens for candidate in current) + item.context_tokens
            > self._limits.max_context_tokens
        )

    def _flush(
        self,
        current: list[_EstimatedSegment],
        batches: list[TranslationBatch],
    ) -> None:
        if not current:
            return
        batches.append(self._make_batch(tuple(current), len(batches)))
        current.clear()

    def _make_batch(
        self,
        items: tuple[_EstimatedSegment, ...],
        batch_index: int,
    ) -> TranslationBatch:
        input_tokens = sum(item.input_tokens for item in items)
        context_tokens = sum(item.context_tokens for item in items)
        return TranslationBatch(
            batch_index=batch_index,
            section_id=items[0].segment.section_id,
            segments=tuple(item.segment for item in items),
            estimated_input_tokens=input_tokens,
            estimated_context_tokens=context_tokens,
            exceeds_input_limit=input_tokens > self._limits.max_input_tokens,
            exceeds_context_limit=(
                self._limits.max_context_tokens is not None
                and context_tokens > self._limits.max_context_tokens
            ),
        )


def estimate_tokens(text: str) -> int:
    if type(text) is not str:
        raise TypeError("Token estimation requires text.")
    if not text:
        return 0
    return max(1, (len(text.encode("utf-8")) + 3) // 4)


def build_translation_batches(
    segments: Iterable[BatchSegment],
    *,
    limits: BatchLimits | None = None,
    token_estimator: TokenEstimator | None = None,
) -> TranslationBatchPlan:
    return TranslationBatchBuilder(limits, token_estimator=token_estimator).build(segments)


def _reject_duplicate_ids(segments: tuple[BatchSegment, ...]) -> None:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for segment in segments:
        if segment.segment_id in seen:
            duplicates.add(segment.segment_id)
        seen.add(segment.segment_id)
    if duplicates:
        raise DuplicateSegmentError(
            "Translation batch input contains duplicate segment ID(s): "
            + ", ".join(sorted(duplicates))
            + "."
        )


def _validate_section_order(segments: tuple[BatchSegment, ...]) -> None:
    section_orders: dict[str | None, int] = {}
    order_sections: dict[int, str | None] = {}
    for segment in segments:
        previous = section_orders.setdefault(segment.section_id, segment.section_order)
        if previous != segment.section_order:
            raise TranslationBatchError(
                f"Section {segment.section_id!r} has inconsistent section order."
            )
        previous_section = order_sections.setdefault(segment.section_order, segment.section_id)
        if previous_section != segment.section_id:
            raise TranslationBatchError(
                f"Section order {segment.section_order} is assigned to multiple sections."
            )
