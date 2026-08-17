from enum import StrEnum

from sqlalchemy import REAL, CheckConstraint, ForeignKey, Index, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column
from transloka_core.database.models.application import Base
from transloka_core.database.models.document_ir import DocumentSection, DocumentSegment
from transloka_core.database.models.documents import Document
from transloka_core.database.models.glossary import GlossarySnapshot
from transloka_core.database.models.projects import Project

_PARENT_MODELS = (Project, Document, DocumentSection, DocumentSegment, GlossarySnapshot)


class TranslationBatchStatus(StrEnum):
    CREATED = "CREATED"
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    RETRYING = "RETRYING"
    COMPLETED = "COMPLETED"
    COMPLETED_WITH_WARNINGS = "COMPLETED_WITH_WARNINGS"
    PARTIALLY_COMPLETED = "PARTIALLY_COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class TranslationAttemptStatus(StrEnum):
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    COMPLETED_WITH_WARNINGS = "COMPLETED_WITH_WARNINGS"
    PARTIALLY_COMPLETED = "PARTIALLY_COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    STALE = "STALE"


class SegmentTranslationStatus(StrEnum):
    MACHINE_TRANSLATED = "MACHINE_TRANSLATED"
    TRANSLATION_FAILED = "TRANSLATION_FAILED"
    NEEDS_REVIEW = "NEEDS_REVIEW"
    USER_EDITED = "USER_EDITED"
    APPROVED = "APPROVED"


class TranslationValidationStatus(StrEnum):
    NOT_RUN = "NOT_RUN"
    PASSED = "PASSED"
    PASSED_WITH_WARNINGS = "PASSED_WITH_WARNINGS"
    RETRY_REQUIRED = "RETRY_REQUIRED"
    FALLBACK_REQUIRED = "FALLBACK_REQUIRED"
    MANUAL_REVIEW_REQUIRED = "MANUAL_REVIEW_REQUIRED"
    FAILED = "FAILED"


class ValidatorType(StrEnum):
    SEGMENT_MAPPING = "SEGMENT_MAPPING"
    PLACEHOLDER_INTEGRITY = "PLACEHOLDER_INTEGRITY"
    NUMERICAL_INTEGRITY = "NUMERICAL_INTEGRITY"
    URL_INTEGRITY = "URL_INTEGRITY"
    CODE_INTEGRITY = "CODE_INTEGRITY"
    CITATION_INTEGRITY = "CITATION_INTEGRITY"
    LANGUAGE = "LANGUAGE"
    TERMINOLOGY = "TERMINOLOGY"
    SEMANTIC = "SEMANTIC"
    LENGTH_RATIO = "LENGTH_RATIO"
    HALLUCINATION = "HALLUCINATION"


def _sql_values(enum_type: type[StrEnum]) -> str:
    return ", ".join(f"'{member.value}'" for member in enum_type)


def _prefixed_uuid(prefix: str, table_name: str) -> CheckConstraint:
    return CheckConstraint(
        f"length(id) = 40 AND substr(id, 1, 4) = '{prefix}' "
        "AND substr(id, 13, 1) = '-' AND substr(id, 18, 1) = '-' "
        "AND substr(id, 23, 1) = '-' AND substr(id, 28, 1) = '-'",
        name=f"ck_{table_name}_prefixed_uuid",
    )


class TranslationBatch(Base):
    __tablename__ = "translation_batches"
    __table_args__ = (
        _prefixed_uuid("tbt_", "translation_batches"),
        CheckConstraint("trim(provider_type) <> ''", name="ck_translation_batches_provider"),
        CheckConstraint("trim(model_id) <> ''", name="ck_translation_batches_model"),
        CheckConstraint("trim(prompt_version) <> ''", name="ck_translation_batches_prompt"),
        CheckConstraint("trim(pipeline_version) <> ''", name="ck_translation_batches_pipeline"),
        CheckConstraint("trim(status) <> ''", name="ck_translation_batches_status"),
        CheckConstraint("segment_count >= 0", name="ck_translation_batches_segment_count"),
        CheckConstraint(
            "source_character_count >= 0",
            name="ck_translation_batches_source_character_count",
        ),
        CheckConstraint(
            "estimated_input_tokens IS NULL OR estimated_input_tokens >= 0",
            name="ck_translation_batches_estimated_tokens",
        ),
        CheckConstraint(
            "actual_input_tokens IS NULL OR actual_input_tokens >= 0",
            name="ck_translation_batches_input_tokens",
        ),
        CheckConstraint(
            "actual_output_tokens IS NULL OR actual_output_tokens >= 0",
            name="ck_translation_batches_output_tokens",
        ),
        CheckConstraint("batch_order >= 0", name="ck_translation_batches_order"),
        CheckConstraint("trim(idempotency_key) <> ''", name="ck_translation_batches_idempotency"),
        CheckConstraint(
            "json_valid(settings_json)",
            name="ck_translation_batches_settings_json_valid",
        ),
        CheckConstraint("trim(created_at) <> ''", name="ck_translation_batches_created_at"),
        {"sqlite_strict": True},
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    project_id: Mapped[str] = mapped_column(
        Text, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False
    )
    document_id: Mapped[str] = mapped_column(
        Text, ForeignKey("documents.id", ondelete="CASCADE"), nullable=False
    )
    section_id: Mapped[str | None] = mapped_column(
        Text, ForeignKey("document_sections.id", ondelete="SET NULL"), nullable=True
    )
    glossary_snapshot_id: Mapped[str] = mapped_column(
        Text, ForeignKey("glossary_snapshots.id"), nullable=False
    )
    provider_type: Mapped[str] = mapped_column(Text, nullable=False)
    model_id: Mapped[str] = mapped_column(Text, nullable=False)
    prompt_version: Mapped[str] = mapped_column(Text, nullable=False)
    pipeline_version: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    segment_count: Mapped[int] = mapped_column(Integer, nullable=False)
    source_character_count: Mapped[int] = mapped_column(Integer, nullable=False)
    estimated_input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    actual_input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    actual_output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    batch_order: Mapped[int] = mapped_column(Integer, nullable=False)
    idempotency_key: Mapped[str] = mapped_column(Text, nullable=False)
    settings_json: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[str] = mapped_column(Text, nullable=False)
    started_at: Mapped[str | None] = mapped_column(Text, nullable=True)
    completed_at: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_code: Mapped[str | None] = mapped_column(Text, nullable=True)


class TranslationBatchSegment(Base):
    __tablename__ = "translation_batch_segments"
    __table_args__ = (
        CheckConstraint("segment_order >= 0", name="ck_translation_batch_segments_order"),
        {"sqlite_strict": True},
    )

    batch_id: Mapped[str] = mapped_column(
        Text, ForeignKey("translation_batches.id", ondelete="CASCADE"), primary_key=True
    )
    segment_id: Mapped[str] = mapped_column(
        Text, ForeignKey("document_segments.id", ondelete="CASCADE"), primary_key=True
    )
    segment_order: Mapped[int] = mapped_column(Integer, nullable=False)


class TranslationAttempt(Base):
    __tablename__ = "translation_attempts"
    __table_args__ = (
        _prefixed_uuid("tat_", "translation_attempts"),
        CheckConstraint("attempt_number >= 1", name="ck_translation_attempts_number"),
        CheckConstraint("trim(provider_type) <> ''", name="ck_translation_attempts_provider"),
        CheckConstraint("trim(model_id) <> ''", name="ck_translation_attempts_model"),
        CheckConstraint("trim(status) <> ''", name="ck_translation_attempts_status"),
        CheckConstraint("trim(request_hash) <> ''", name="ck_translation_attempts_request_hash"),
        CheckConstraint(
            "latency_ms IS NULL OR latency_ms >= 0",
            name="ck_translation_attempts_latency",
        ),
        CheckConstraint(
            "input_tokens IS NULL OR input_tokens >= 0",
            name="ck_translation_attempts_input_tokens",
        ),
        CheckConstraint(
            "output_tokens IS NULL OR output_tokens >= 0",
            name="ck_translation_attempts_output_tokens",
        ),
        CheckConstraint(
            "provider_metadata_json IS NULL OR json_valid(provider_metadata_json)",
            name="ck_translation_attempts_metadata_json_valid",
        ),
        CheckConstraint("trim(created_at) <> ''", name="ck_translation_attempts_created_at"),
        {"sqlite_strict": True},
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    batch_id: Mapped[str] = mapped_column(
        Text, ForeignKey("translation_batches.id", ondelete="CASCADE"), nullable=False
    )
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False)
    provider_type: Mapped[str] = mapped_column(Text, nullable=False)
    model_id: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    request_hash: Mapped[str] = mapped_column(Text, nullable=False)
    response_hash: Mapped[str | None] = mapped_column(Text, nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    input_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    output_tokens: Mapped[int | None] = mapped_column(Integer, nullable=True)
    retry_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    provider_metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[str] = mapped_column(Text, nullable=False)
    completed_at: Mapped[str | None] = mapped_column(Text, nullable=True)


class SegmentTranslation(Base):
    __tablename__ = "segment_translations"
    __table_args__ = (
        CheckConstraint("trim(translated_text_raw) <> ''", name="ck_segment_translations_raw_text"),
        CheckConstraint("trim(status) <> ''", name="ck_segment_translations_status"),
        CheckConstraint(
            "confidence_overall IS NULL OR confidence_overall BETWEEN 0 AND 1",
            name="ck_segment_translations_confidence",
        ),
        CheckConstraint(
            "confidence_json IS NULL OR json_valid(confidence_json)",
            name="ck_segment_translations_confidence_json_valid",
        ),
        CheckConstraint("trim(validation_status) <> ''", name="ck_segment_translations_validation"),
        CheckConstraint("trim(created_at) <> ''", name="ck_segment_translations_created_at"),
        {"sqlite_strict": True},
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    segment_id: Mapped[str] = mapped_column(
        Text, ForeignKey("document_segments.id", ondelete="CASCADE"), nullable=False
    )
    batch_id: Mapped[str] = mapped_column(
        Text, ForeignKey("translation_batches.id", ondelete="CASCADE"), nullable=False
    )
    attempt_id: Mapped[str] = mapped_column(
        Text, ForeignKey("translation_attempts.id", ondelete="CASCADE"), nullable=False
    )
    translated_text_raw: Mapped[str] = mapped_column(Text, nullable=False)
    translated_text_restored: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    confidence_overall: Mapped[float | None] = mapped_column(REAL, nullable=True)
    confidence_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    validation_status: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[str] = mapped_column(Text, nullable=False)


class TranslationValidation(Base):
    __tablename__ = "translation_validations"
    __table_args__ = (
        CheckConstraint(
            f"validator_type IN ({_sql_values(ValidatorType)})",
            name="ck_translation_validations_type",
        ),
        CheckConstraint("trim(status) <> ''", name="ck_translation_validations_status"),
        CheckConstraint(
            "score IS NULL OR score BETWEEN 0 AND 1",
            name="ck_translation_validations_score",
        ),
        CheckConstraint(
            "details_json IS NULL OR json_valid(details_json)",
            name="ck_translation_validations_details_json_valid",
        ),
        CheckConstraint("trim(created_at) <> ''", name="ck_translation_validations_created_at"),
        {"sqlite_strict": True},
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    segment_translation_id: Mapped[str] = mapped_column(
        Text,
        ForeignKey("segment_translations.id", ondelete="CASCADE"),
        nullable=False,
    )
    validator_type: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    score: Mapped[float | None] = mapped_column(REAL, nullable=True)
    details_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[str] = mapped_column(Text, nullable=False)


Index(
    "ix_translation_batches_project_status",
    TranslationBatch.project_id,
    TranslationBatch.status,
)
Index(
    "ix_translation_batches_document_order",
    TranslationBatch.document_id,
    TranslationBatch.batch_order,
)
Index(
    "uq_translation_batches_idempotency_key",
    TranslationBatch.idempotency_key,
    unique=True,
)
Index(
    "uq_translation_batch_segments_order",
    TranslationBatchSegment.batch_id,
    TranslationBatchSegment.segment_order,
    unique=True,
)
Index(
    "uq_translation_attempts_number",
    TranslationAttempt.batch_id,
    TranslationAttempt.attempt_number,
    unique=True,
)
Index(
    "ix_segment_translations_segment",
    SegmentTranslation.segment_id,
    SegmentTranslation.created_at.desc(),
)
Index(
    "uq_translation_validations_type",
    TranslationValidation.segment_translation_id,
    TranslationValidation.validator_type,
    unique=True,
)
