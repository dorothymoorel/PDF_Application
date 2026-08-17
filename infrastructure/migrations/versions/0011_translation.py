"""Create translation persistence tables.

Revision ID: 0011_translation
Revises: 0010_local_models
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0011_translation"
down_revision: str | Sequence[str] | None = "0010_local_models"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_VALIDATOR_TYPES = (
    "'SEGMENT_MAPPING', 'PLACEHOLDER_INTEGRITY', 'NUMERICAL_INTEGRITY', "
    "'URL_INTEGRITY', 'CODE_INTEGRITY', 'CITATION_INTEGRITY', 'LANGUAGE', "
    "'TERMINOLOGY', 'SEMANTIC', 'LENGTH_RATIO', 'HALLUCINATION'"
)


def upgrade() -> None:
    op.create_table(
        "translation_batches",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("project_id", sa.Text(), nullable=False),
        sa.Column("document_id", sa.Text(), nullable=False),
        sa.Column("section_id", sa.Text(), nullable=True),
        sa.Column("glossary_snapshot_id", sa.Text(), nullable=False),
        sa.Column("provider_type", sa.Text(), nullable=False),
        sa.Column("model_id", sa.Text(), nullable=False),
        sa.Column("prompt_version", sa.Text(), nullable=False),
        sa.Column("pipeline_version", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("segment_count", sa.Integer(), nullable=False),
        sa.Column("source_character_count", sa.Integer(), nullable=False),
        sa.Column("estimated_input_tokens", sa.Integer(), nullable=True),
        sa.Column("actual_input_tokens", sa.Integer(), nullable=True),
        sa.Column("actual_output_tokens", sa.Integer(), nullable=True),
        sa.Column("batch_order", sa.Integer(), nullable=False),
        sa.Column("idempotency_key", sa.Text(), nullable=False),
        sa.Column("settings_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("started_at", sa.Text(), nullable=True),
        sa.Column("completed_at", sa.Text(), nullable=True),
        sa.Column("error_code", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "length(id) = 40 AND substr(id, 1, 4) = 'tbt_' "
            "AND substr(id, 13, 1) = '-' AND substr(id, 18, 1) = '-' "
            "AND substr(id, 23, 1) = '-' AND substr(id, 28, 1) = '-'",
            name="ck_translation_batches_prefixed_uuid",
        ),
        sa.CheckConstraint("trim(provider_type) <> ''", name="ck_translation_batches_provider"),
        sa.CheckConstraint("trim(model_id) <> ''", name="ck_translation_batches_model"),
        sa.CheckConstraint("trim(prompt_version) <> ''", name="ck_translation_batches_prompt"),
        sa.CheckConstraint("trim(pipeline_version) <> ''", name="ck_translation_batches_pipeline"),
        sa.CheckConstraint("trim(status) <> ''", name="ck_translation_batches_status"),
        sa.CheckConstraint("segment_count >= 0", name="ck_translation_batches_segment_count"),
        sa.CheckConstraint(
            "source_character_count >= 0",
            name="ck_translation_batches_source_character_count",
        ),
        sa.CheckConstraint(
            "estimated_input_tokens IS NULL OR estimated_input_tokens >= 0",
            name="ck_translation_batches_estimated_tokens",
        ),
        sa.CheckConstraint(
            "actual_input_tokens IS NULL OR actual_input_tokens >= 0",
            name="ck_translation_batches_input_tokens",
        ),
        sa.CheckConstraint(
            "actual_output_tokens IS NULL OR actual_output_tokens >= 0",
            name="ck_translation_batches_output_tokens",
        ),
        sa.CheckConstraint("batch_order >= 0", name="ck_translation_batches_order"),
        sa.CheckConstraint(
            "trim(idempotency_key) <> ''", name="ck_translation_batches_idempotency"
        ),
        sa.CheckConstraint(
            "json_valid(settings_json)",
            name="ck_translation_batches_settings_json_valid",
        ),
        sa.CheckConstraint("trim(created_at) <> ''", name="ck_translation_batches_created_at"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["section_id"], ["document_sections.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["glossary_snapshot_id"], ["glossary_snapshots.id"]),
        sa.PrimaryKeyConstraint("id"),
        sqlite_strict=True,
    )
    op.create_index(
        "uq_translation_batches_idempotency_key",
        "translation_batches",
        ["idempotency_key"],
        unique=True,
    )
    op.create_index(
        "ix_translation_batches_project_status",
        "translation_batches",
        ["project_id", "status"],
    )
    op.create_index(
        "ix_translation_batches_document_order",
        "translation_batches",
        ["document_id", "batch_order"],
    )

    op.create_table(
        "translation_batch_segments",
        sa.Column("batch_id", sa.Text(), nullable=False),
        sa.Column("segment_id", sa.Text(), nullable=False),
        sa.Column("segment_order", sa.Integer(), nullable=False),
        sa.CheckConstraint("segment_order >= 0", name="ck_translation_batch_segments_order"),
        sa.ForeignKeyConstraint(["batch_id"], ["translation_batches.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["segment_id"], ["document_segments.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("batch_id", "segment_id"),
        sqlite_strict=True,
    )
    op.create_index(
        "uq_translation_batch_segments_order",
        "translation_batch_segments",
        ["batch_id", "segment_order"],
        unique=True,
    )

    op.create_table(
        "translation_attempts",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("batch_id", sa.Text(), nullable=False),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("provider_type", sa.Text(), nullable=False),
        sa.Column("model_id", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("request_hash", sa.Text(), nullable=False),
        sa.Column("response_hash", sa.Text(), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("retry_reason", sa.Text(), nullable=True),
        sa.Column("error_code", sa.Text(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("provider_metadata_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("completed_at", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "length(id) = 40 AND substr(id, 1, 4) = 'tat_' "
            "AND substr(id, 13, 1) = '-' AND substr(id, 18, 1) = '-' "
            "AND substr(id, 23, 1) = '-' AND substr(id, 28, 1) = '-'",
            name="ck_translation_attempts_prefixed_uuid",
        ),
        sa.CheckConstraint("attempt_number >= 1", name="ck_translation_attempts_number"),
        sa.CheckConstraint("trim(provider_type) <> ''", name="ck_translation_attempts_provider"),
        sa.CheckConstraint("trim(model_id) <> ''", name="ck_translation_attempts_model"),
        sa.CheckConstraint("trim(status) <> ''", name="ck_translation_attempts_status"),
        sa.CheckConstraint("trim(request_hash) <> ''", name="ck_translation_attempts_request_hash"),
        sa.CheckConstraint(
            "latency_ms IS NULL OR latency_ms >= 0",
            name="ck_translation_attempts_latency",
        ),
        sa.CheckConstraint(
            "input_tokens IS NULL OR input_tokens >= 0",
            name="ck_translation_attempts_input_tokens",
        ),
        sa.CheckConstraint(
            "output_tokens IS NULL OR output_tokens >= 0",
            name="ck_translation_attempts_output_tokens",
        ),
        sa.CheckConstraint(
            "provider_metadata_json IS NULL OR json_valid(provider_metadata_json)",
            name="ck_translation_attempts_metadata_json_valid",
        ),
        sa.CheckConstraint("trim(created_at) <> ''", name="ck_translation_attempts_created_at"),
        sa.ForeignKeyConstraint(["batch_id"], ["translation_batches.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sqlite_strict=True,
    )
    op.create_index(
        "uq_translation_attempts_number",
        "translation_attempts",
        ["batch_id", "attempt_number"],
        unique=True,
    )

    op.create_table(
        "segment_translations",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("segment_id", sa.Text(), nullable=False),
        sa.Column("batch_id", sa.Text(), nullable=False),
        sa.Column("attempt_id", sa.Text(), nullable=False),
        sa.Column("translated_text_raw", sa.Text(), nullable=False),
        sa.Column("translated_text_restored", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("confidence_overall", sa.REAL(), nullable=True),
        sa.Column("confidence_json", sa.Text(), nullable=True),
        sa.Column("validation_status", sa.Text(), nullable=False),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.CheckConstraint(
            "trim(translated_text_raw) <> ''", name="ck_segment_translations_raw_text"
        ),
        sa.CheckConstraint("trim(status) <> ''", name="ck_segment_translations_status"),
        sa.CheckConstraint(
            "confidence_overall IS NULL OR confidence_overall BETWEEN 0 AND 1",
            name="ck_segment_translations_confidence",
        ),
        sa.CheckConstraint(
            "confidence_json IS NULL OR json_valid(confidence_json)",
            name="ck_segment_translations_confidence_json_valid",
        ),
        sa.CheckConstraint(
            "trim(validation_status) <> ''", name="ck_segment_translations_validation"
        ),
        sa.CheckConstraint("trim(created_at) <> ''", name="ck_segment_translations_created_at"),
        sa.ForeignKeyConstraint(["segment_id"], ["document_segments.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["batch_id"], ["translation_batches.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["attempt_id"], ["translation_attempts.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sqlite_strict=True,
    )
    op.create_index(
        "ix_segment_translations_segment",
        "segment_translations",
        ["segment_id", sa.text("created_at DESC")],
    )

    op.create_table(
        "translation_validations",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("segment_translation_id", sa.Text(), nullable=False),
        sa.Column("validator_type", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("score", sa.REAL(), nullable=True),
        sa.Column("details_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.CheckConstraint(
            f"validator_type IN ({_VALIDATOR_TYPES})",
            name="ck_translation_validations_type",
        ),
        sa.CheckConstraint("trim(status) <> ''", name="ck_translation_validations_status"),
        sa.CheckConstraint(
            "score IS NULL OR score BETWEEN 0 AND 1",
            name="ck_translation_validations_score",
        ),
        sa.CheckConstraint(
            "details_json IS NULL OR json_valid(details_json)",
            name="ck_translation_validations_details_json_valid",
        ),
        sa.CheckConstraint("trim(created_at) <> ''", name="ck_translation_validations_created_at"),
        sa.ForeignKeyConstraint(
            ["segment_translation_id"], ["segment_translations.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sqlite_strict=True,
    )
    op.create_index(
        "uq_translation_validations_type",
        "translation_validations",
        ["segment_translation_id", "validator_type"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_index("uq_translation_validations_type", table_name="translation_validations")
    op.drop_table("translation_validations")
    op.drop_index("ix_segment_translations_segment", table_name="segment_translations")
    op.drop_table("segment_translations")
    op.drop_index("uq_translation_attempts_number", table_name="translation_attempts")
    op.drop_table("translation_attempts")
    op.drop_index("uq_translation_batch_segments_order", table_name="translation_batch_segments")
    op.drop_table("translation_batch_segments")
    op.drop_index("ix_translation_batches_document_order", table_name="translation_batches")
    op.drop_index("ix_translation_batches_project_status", table_name="translation_batches")
    op.drop_index("uq_translation_batches_idempotency_key", table_name="translation_batches")
    op.drop_table("translation_batches")
