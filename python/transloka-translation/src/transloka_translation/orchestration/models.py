from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from transloka_translation.batching import BatchContext, BatchLimits
from transloka_translation.schemas import (
    TranslationContext,
    TranslationGlossaryEntry,
    TranslationStyle,
)
from transloka_translation.validation import ValidationCode


class TranslationRunStatus(StrEnum):
    CREATED = "CREATED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    COMPLETED_WITH_WARNINGS = "COMPLETED_WITH_WARNINGS"
    PARTIALLY_COMPLETED = "PARTIALLY_COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class SegmentRunStatus(StrEnum):
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    LOCKED = "LOCKED"
    CANCELLED = "CANCELLED"


@dataclass(frozen=True, slots=True)
class TranslationSegmentInput:
    segment_id: str
    source_text: str
    section_id: str | None = None
    section_order: int = 0
    page_order: int = 0
    block_order: int = 0
    segment_order: int = 0
    context: BatchContext = BatchContext()
    locked: bool = False
    expected_revision: int | None = None

    def __post_init__(self) -> None:
        if type(self.segment_id) is not str or not self.segment_id.strip():
            raise ValueError("segment_id must be a non-empty string.")
        if type(self.source_text) is not str or not self.source_text.strip():
            raise ValueError("source_text must be a non-empty string.")
        if self.section_id is not None and (
            type(self.section_id) is not str or not self.section_id.strip()
        ):
            raise ValueError("section_id must be a non-empty string or None.")
        if any(
            type(value) is not int or value < 0
            for value in (
                self.section_order,
                self.page_order,
                self.block_order,
                self.segment_order,
            )
        ):
            raise ValueError("Segment order values must be non-negative integers.")
        if type(self.context) is not BatchContext or type(self.locked) is not bool:
            raise TypeError("Invalid segment context or locked value.")
        if self.expected_revision is not None and (
            type(self.expected_revision) is not int or self.expected_revision < 0
        ):
            raise ValueError("expected_revision must be a non-negative integer or None.")


@dataclass(frozen=True, slots=True)
class TranslationOperation:
    project_id: str
    document_id: str
    section_id: str | None
    glossary_snapshot_id: str
    provider_type: str
    model_id: str
    idempotency_key: str
    context: TranslationContext
    segments: tuple[TranslationSegmentInput, ...]
    glossary: tuple[TranslationGlossaryEntry, ...] = ()
    style: TranslationStyle = TranslationStyle.PROFESSIONAL
    prompt_version: str = "translation_prompt_0.1"
    pipeline_version: str = "translation_pipeline_0.1"
    batch_order: int = 0
    settings_json: str = "{}"
    batch_limits: BatchLimits = BatchLimits()

    def __post_init__(self) -> None:
        for name in (
            "project_id",
            "document_id",
            "glossary_snapshot_id",
            "provider_type",
            "model_id",
            "idempotency_key",
            "prompt_version",
            "pipeline_version",
        ):
            value = getattr(self, name)
            if type(value) is not str or not value.strip():
                raise ValueError(f"{name} must be a non-empty string.")
        if self.section_id is not None and (
            type(self.section_id) is not str or not self.section_id.strip()
        ):
            raise ValueError("section_id must be a non-empty string or None.")
        if type(self.context) is not TranslationContext:
            raise TypeError("context must be TranslationContext.")
        if type(self.segments) is not tuple or not self.segments:
            raise ValueError("segments must be a non-empty tuple.")
        if any(type(segment) is not TranslationSegmentInput for segment in self.segments):
            raise TypeError("segments must contain TranslationSegmentInput values.")
        identifiers = tuple(segment.segment_id for segment in self.segments)
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("segments must not contain duplicate IDs.")
        if type(self.glossary) is not tuple or any(
            type(entry) is not TranslationGlossaryEntry for entry in self.glossary
        ):
            raise TypeError("glossary must contain TranslationGlossaryEntry values.")
        if type(self.style) is not TranslationStyle:
            raise TypeError("style must be TranslationStyle.")
        if type(self.batch_order) is not int or self.batch_order < 0:
            raise ValueError("batch_order must be a non-negative integer.")
        if type(self.settings_json) is not str or not self.settings_json.strip():
            raise ValueError("settings_json must be non-empty JSON text.")
        if type(self.batch_limits) is not BatchLimits:
            raise TypeError("batch_limits must be BatchLimits.")


@dataclass(frozen=True, slots=True)
class SegmentFailure:
    segment_id: str
    code: str
    message: str
    validation_codes: tuple[ValidationCode, ...] = ()


@dataclass(frozen=True, slots=True)
class TranslationRunResult:
    run_id: str
    idempotency_key: str
    status: TranslationRunStatus
    completed_segment_ids: tuple[str, ...]
    failed_segment_ids: tuple[str, ...]
    locked_segment_ids: tuple[str, ...]
    cancelled_segment_ids: tuple[str, ...]
    failures: tuple[SegmentFailure, ...] = ()
    warnings: tuple[str, ...] = ()
    attempt_count: int = 0
    unattempted_segment_ids: tuple[str, ...] = ()
    provider_error_code: str | None = None
    retry_after_seconds: float | None = None

    @property
    def successful(self) -> bool:
        return self.status in {
            TranslationRunStatus.COMPLETED,
            TranslationRunStatus.COMPLETED_WITH_WARNINGS,
        }
