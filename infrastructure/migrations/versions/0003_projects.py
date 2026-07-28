"""Create the projects table.

Revision ID: 0003_projects
Revises: 0002_application_settings
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_projects"
down_revision: str | Sequence[str] | None = "0002_application_settings"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_STATUSES = (
    "'CREATED', 'IMPORTING', 'ANALYZING', 'WAITING_FOR_SETTINGS', 'EXTRACTING', "
    "'OCR_PROCESSING', 'TERMS_DETECTED', 'WAITING_FOR_GLOSSARY', 'TRANSLATING', "
    "'READY_FOR_REVIEW', 'REVIEWING', 'RECONSTRUCTING', 'READY_FOR_EXPORT', "
    "'COMPLETED', 'PARTIALLY_COMPLETED', 'FAILED', 'CANCELLED', 'ARCHIVED', "
    "'DELETION_QUEUED'"
)
_DOCUMENT_TYPES = (
    "'ACADEMIC_PAPER', 'ACADEMIC_BOOK', 'TECHNICAL_BOOK', 'USER_MANUAL', "
    "'BUSINESS_REPORT', 'LEGAL_DOCUMENT', 'FICTION_BOOK', 'NONFICTION_BOOK', "
    "'PRESENTATION_EXPORT', 'BROCHURE', 'FORM', 'COMIC_OR_GRAPHIC_BOOK', "
    "'GENERAL_DOCUMENT', 'UNKNOWN'"
)
_TRANSLATION_STYLES = "'LITERAL', 'PROFESSIONAL', 'ACADEMIC', 'NATURAL'"
_RECONSTRUCTION_MODES = "'OVERLAY', 'REFLOW', 'HYBRID'"


def upgrade() -> None:
    op.create_table(
        "projects",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("source_language", sa.Text(), nullable=False),
        sa.Column("target_language", sa.Text(), nullable=False),
        sa.Column("document_type", sa.Text(), nullable=False),
        sa.Column("translation_style", sa.Text(), nullable=False),
        sa.Column("reconstruction_mode", sa.Text(), nullable=False),
        sa.Column("progress", sa.REAL(), nullable=False),
        sa.Column("active_document_id", sa.Text(), nullable=True),
        sa.Column("settings_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("updated_at", sa.Text(), nullable=False),
        sa.Column("archived_at", sa.Text(), nullable=True),
        sa.Column("deleted_at", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "length(id) = 40 AND substr(id, 1, 4) = 'prj_' "
            "AND substr(id, 13, 1) = '-' AND substr(id, 18, 1) = '-' "
            "AND substr(id, 23, 1) = '-' AND substr(id, 28, 1) = '-'",
            name="ck_projects_prefixed_uuid",
        ),
        sa.CheckConstraint("trim(name) <> ''", name="ck_projects_name"),
        sa.CheckConstraint(f"status IN ({_STATUSES})", name="ck_projects_status"),
        sa.CheckConstraint(
            "trim(source_language) <> ''",
            name="ck_projects_source_language",
        ),
        sa.CheckConstraint(
            "trim(target_language) <> ''",
            name="ck_projects_target_language",
        ),
        sa.CheckConstraint(
            f"document_type IN ({_DOCUMENT_TYPES})",
            name="ck_projects_document_type",
        ),
        sa.CheckConstraint(
            f"translation_style IN ({_TRANSLATION_STYLES})",
            name="ck_projects_translation_style",
        ),
        sa.CheckConstraint(
            f"reconstruction_mode IN ({_RECONSTRUCTION_MODES})",
            name="ck_projects_reconstruction_mode",
        ),
        sa.CheckConstraint(
            "progress >= 0.0 AND progress <= 1.0",
            name="ck_projects_progress",
        ),
        sa.CheckConstraint(
            "json_valid(settings_json)",
            name="ck_projects_settings_json_valid",
        ),
        sa.PrimaryKeyConstraint("id"),
        sqlite_strict=True,
    )
    op.create_index("ix_projects_status", "projects", ["status"])
    op.create_index(
        "ix_projects_updated_at",
        "projects",
        [sa.text("updated_at DESC")],
    )


def downgrade() -> None:
    op.drop_index("ix_projects_updated_at", table_name="projects")
    op.drop_index("ix_projects_status", table_name="projects")
    op.drop_table("projects")
