"""Create immutable export metadata and versioning table.

Revision ID: 0015_exports
Revises: 0014_reconstruction
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0015_exports"
down_revision: str | Sequence[str] | None = "0014_reconstruction"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_EXPORT_TYPES = (
    "'TRANSLATED_PDF', 'BILINGUAL_PDF', 'QUALITY_REPORT', 'GLOSSARY_CSV', 'DOCUMENT_IR_PACKAGE'"
)
_EXPORT_STATUSES = (
    "'CREATED', 'RUNNING', 'COMPLETED', 'COMPLETED_WITH_WARNINGS', "
    "'PARTIALLY_COMPLETED', 'FAILED', 'CANCELLED'"
)


def upgrade() -> None:
    op.create_table(
        "exports",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("project_id", sa.Text(), nullable=False),
        sa.Column("document_id", sa.Text(), nullable=False),
        sa.Column("reconstruction_job_id", sa.Text(), nullable=True),
        sa.Column("file_id", sa.Text(), nullable=True),
        sa.Column("export_type", sa.Text(), nullable=False),
        sa.Column("output_profile", sa.Text(), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("page_count", sa.Integer(), nullable=True),
        sa.Column("size_bytes", sa.Integer(), nullable=True),
        sa.Column("checksum_sha256", sa.Text(), nullable=True),
        sa.Column("validation_report_id", sa.Text(), nullable=True),
        sa.Column("settings_json", sa.Text(), nullable=False),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("completed_at", sa.Text(), nullable=True),
        sa.Column("error_code", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "length(id) = 40 AND substr(id, 1, 4) = 'exp_' "
            "AND substr(id, 13, 1) = '-' AND substr(id, 18, 1) = '-' "
            "AND substr(id, 23, 1) = '-' AND substr(id, 28, 1) = '-'",
            name="ck_exports_prefixed_uuid",
        ),
        sa.CheckConstraint(
            f"export_type IN ({_EXPORT_TYPES})",
            name="ck_exports_type",
        ),
        sa.CheckConstraint("trim(output_profile) <> ''", name="ck_exports_profile"),
        sa.CheckConstraint("version_number >= 1", name="ck_exports_version"),
        sa.CheckConstraint(
            f"status IN ({_EXPORT_STATUSES})",
            name="ck_exports_status",
        ),
        sa.CheckConstraint(
            "page_count IS NULL OR page_count >= 0",
            name="ck_exports_page_count",
        ),
        sa.CheckConstraint(
            "size_bytes IS NULL OR size_bytes >= 0",
            name="ck_exports_size",
        ),
        sa.CheckConstraint(
            "checksum_sha256 IS NULL OR "
            "(length(checksum_sha256) = 64 AND checksum_sha256 NOT GLOB '*[^0-9a-f]*')",
            name="ck_exports_checksum",
        ),
        sa.CheckConstraint(
            "validation_report_id IS NULL OR trim(validation_report_id) <> ''",
            name="ck_exports_validation_report",
        ),
        sa.CheckConstraint(
            "json_valid(settings_json)",
            name="ck_exports_settings_json_valid",
        ),
        sa.CheckConstraint(
            "trim(created_at) <> '' AND (completed_at IS NULL OR trim(completed_at) <> '')",
            name="ck_exports_timestamps",
        ),
        sa.CheckConstraint(
            "status NOT IN ('COMPLETED', 'COMPLETED_WITH_WARNINGS') OR "
            "(file_id IS NOT NULL AND page_count IS NOT NULL AND size_bytes IS NOT NULL "
            "AND checksum_sha256 IS NOT NULL AND completed_at IS NOT NULL)",
            name="ck_exports_completed_requirements",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name="fk_exports_project_id_projects",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
            name="fk_exports_document_id_documents",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["reconstruction_job_id"],
            ["reconstruction_jobs.id"],
            name="fk_exports_reconstruction_job_id_reconstruction_jobs",
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(
            ["file_id"],
            ["stored_files.id"],
            name="fk_exports_file_id_stored_files",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sqlite_strict=True,
    )
    op.create_index(
        "uq_exports_project_type_version",
        "exports",
        ["project_id", "export_type", "version_number"],
        unique=True,
    )
    op.create_index(
        "ix_exports_project_status",
        "exports",
        ["project_id", "status"],
    )


def downgrade() -> None:
    op.drop_index("ix_exports_project_status", table_name="exports")
    op.drop_index("uq_exports_project_type_version", table_name="exports")
    op.drop_table("exports")
