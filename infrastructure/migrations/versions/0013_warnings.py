"""Create durable quality warning records.

Revision ID: 0013_warnings
Revises: 0012_segment_revisions
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0013_warnings"
down_revision: str | Sequence[str] | None = "0012_segment_revisions"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_WARNING_TYPES = (
    "'TEXT_EXTRACTION_FAILED', 'READING_ORDER_UNCERTAIN', 'UNKNOWN_CHARACTER', "
    "'FONT_MAPPING_FAILED', 'LOW_OCR_CONFIDENCE', 'OCR_TEXT_CONFLICT', "
    "'UNREADABLE_REGION', 'ROTATION_UNCERTAIN', 'TRANSLATION_FAILED', "
    "'LOW_TRANSLATION_CONFIDENCE', 'UNTRANSLATED_TEXT', 'TARGET_LANGUAGE_MISMATCH', "
    "'POSSIBLE_HALLUCINATION', 'SOURCE_MEANING_DRIFT', 'GLOSSARY_NOT_APPLIED', "
    "'TERM_INCONSISTENT', 'PLACEHOLDER_MISSING', 'PLACEHOLDER_DUPLICATED', "
    "'CASE_MISMATCH', 'NUMBER_CHANGED', 'DATE_CHANGED', 'UNIT_CHANGED', 'URL_CHANGED', "
    "'CITATION_CHANGED', 'CODE_CHANGED', 'TEXT_OVERFLOW', 'TEXT_CLIPPED', 'TEXT_OVERLAP', "
    "'MISSING_TRANSLATED_SEGMENT', 'PLACEHOLDER_RESTORATION_FAILED', "
    "'OUTPUT_PDF_CORRUPTED', 'ORIGINAL_FILE_CHECKSUM_MISMATCH', 'PATH_TRAVERSAL_DETECTED', "
    "'TABLE_STRUCTURE_CORRUPTED_CRITICAL', 'CRITICAL_TEXT_CLIPPING', "
    "'CRITICAL_LAYOUT_COLLISION', 'IMAGE_OVERLAP', 'MISSING_IMAGE', 'TABLE_OVERFLOW', "
    "'FONT_TOO_SMALL', 'PAGE_ADDED', 'LAYOUT_SHIFT', 'HEADING_LEVEL_CHANGED', "
    "'LIST_NUMBERING_CHANGED', 'TABLE_STRUCTURE_CHANGED', 'FOOTNOTE_LINK_BROKEN', "
    "'READING_ORDER_CHANGED'"
)
_SEVERITIES = "'INFO', 'LOW', 'MEDIUM', 'HIGH', 'CRITICAL'"
_STATUSES = "'OPEN', 'RESOLVED', 'ACCEPTED', 'FALSE_POSITIVE', 'IGNORED_BY_POLICY'"
_RESOLUTION_TYPES = (
    "'AUTO_FIXED', 'USER_FIXED', 'USER_ACCEPTED', 'FALSE_POSITIVE', "
    "'IGNORED_BY_POLICY', 'REQUIRES_REPROCESSING'"
)


def upgrade() -> None:
    op.create_table(
        "warnings",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("project_id", sa.Text(), nullable=False),
        sa.Column("document_id", sa.Text(), nullable=True),
        sa.Column("page_id", sa.Text(), nullable=True),
        sa.Column("block_id", sa.Text(), nullable=True),
        sa.Column("segment_id", sa.Text(), nullable=True),
        sa.Column("job_id", sa.Text(), nullable=True),
        sa.Column("warning_type", sa.Text(), nullable=False),
        sa.Column("severity", sa.Text(), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("details_json", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("resolution_type", sa.Text(), nullable=True),
        sa.Column("resolution_note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("resolved_at", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "length(id) = 40 AND substr(id, 1, 4) = 'wrn_' "
            "AND substr(id, 13, 1) = '-' AND substr(id, 18, 1) = '-' "
            "AND substr(id, 23, 1) = '-' AND substr(id, 28, 1) = '-'",
            name="ck_warnings_prefixed_uuid",
        ),
        sa.CheckConstraint(f"warning_type IN ({_WARNING_TYPES})", name="ck_warnings_type"),
        sa.CheckConstraint(f"severity IN ({_SEVERITIES})", name="ck_warnings_severity"),
        sa.CheckConstraint(f"status IN ({_STATUSES})", name="ck_warnings_status"),
        sa.CheckConstraint(
            f"resolution_type IS NULL OR resolution_type IN ({_RESOLUTION_TYPES})",
            name="ck_warnings_resolution_type",
        ),
        sa.CheckConstraint("trim(message) <> ''", name="ck_warnings_message"),
        sa.CheckConstraint(
            "details_json IS NULL OR json_valid(details_json)",
            name="ck_warnings_details_json_valid",
        ),
        sa.CheckConstraint(
            "trim(created_at) <> '' AND (resolved_at IS NULL OR trim(resolved_at) <> '')",
            name="ck_warnings_timestamps",
        ),
        sa.CheckConstraint(
            "(status = 'OPEN' AND resolved_at IS NULL AND resolution_type IS NULL) OR "
            "(status <> 'OPEN' AND resolved_at IS NOT NULL AND resolution_type IS NOT NULL)",
            name="ck_warnings_resolution_consistency",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name="fk_warnings_project_id_projects",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
            name="fk_warnings_document_id_documents",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["page_id"],
            ["document_pages.id"],
            name="fk_warnings_page_id_document_pages",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["block_id"],
            ["document_blocks.id"],
            name="fk_warnings_block_id_document_blocks",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["segment_id"],
            ["document_segments.id"],
            name="fk_warnings_segment_id_document_segments",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["job_id"],
            ["application_jobs.id"],
            name="fk_warnings_job_id_application_jobs",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sqlite_strict=True,
    )
    op.create_index(
        "ix_warnings_project_open",
        "warnings",
        ["project_id", "status", "severity"],
    )
    op.create_index("ix_warnings_segment", "warnings", ["segment_id"])
    op.create_index("ix_warnings_page", "warnings", ["page_id"])


def downgrade() -> None:
    op.drop_index("ix_warnings_page", table_name="warnings")
    op.drop_index("ix_warnings_segment", table_name="warnings")
    op.drop_index("ix_warnings_project_open", table_name="warnings")
    op.drop_table("warnings")
