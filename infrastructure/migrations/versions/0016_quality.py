"""Create quality report and quality check tables.

Revision ID: 0016_quality
Revises: 0015_exports
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0016_quality"
down_revision: str | Sequence[str] | None = "0015_exports"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_REPORT_TYPES = (
    "'EXTRACTION', 'OCR', 'TRANSLATION', 'TERMINOLOGY', 'RECONSTRUCTION', 'FINAL_EXPORT'"
)
_REPORT_STATUSES = "'NOT_RUN', 'RUNNING', 'PASSED', 'PASSED_WITH_WARNINGS', 'FAILED', 'SKIPPED'"
_CHECK_STATUSES = _REPORT_STATUSES


def upgrade() -> None:
    op.create_table(
        "quality_reports",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("project_id", sa.Text(), nullable=False),
        sa.Column("document_id", sa.Text(), nullable=False),
        sa.Column("report_type", sa.Text(), nullable=False),
        sa.Column("version", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("overall_score", sa.REAL(), nullable=True),
        sa.Column("critical_warning_count", sa.Integer(), nullable=False),
        sa.Column("high_warning_count", sa.Integer(), nullable=False),
        sa.Column("medium_warning_count", sa.Integer(), nullable=False),
        sa.Column("low_warning_count", sa.Integer(), nullable=False),
        sa.Column("summary_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.CheckConstraint("trim(id) <> ''", name="ck_quality_reports_id"),
        sa.CheckConstraint(
            f"report_type IN ({_REPORT_TYPES})",
            name="ck_quality_reports_type",
        ),
        sa.CheckConstraint(
            f"status IN ({_REPORT_STATUSES})",
            name="ck_quality_reports_status",
        ),
        sa.CheckConstraint(
            "overall_score IS NULL OR overall_score BETWEEN 0.0 AND 1.0",
            name="ck_quality_reports_score",
        ),
        sa.CheckConstraint(
            "critical_warning_count >= 0 AND high_warning_count >= 0 AND "
            "medium_warning_count >= 0 AND low_warning_count >= 0",
            name="ck_quality_reports_warning_counts",
        ),
        sa.CheckConstraint(
            "summary_json IS NULL OR json_valid(summary_json)",
            name="ck_quality_reports_summary_json_valid",
        ),
        sa.CheckConstraint("trim(version) <> ''", name="ck_quality_reports_version"),
        sa.CheckConstraint("trim(created_at) <> ''", name="ck_quality_reports_created_at"),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name="fk_quality_reports_project_id_projects",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
            name="fk_quality_reports_document_id_documents",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sqlite_strict=True,
    )

    op.create_table(
        "quality_checks",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("report_id", sa.Text(), nullable=False),
        sa.Column("check_type", sa.Text(), nullable=False),
        sa.Column("scope_type", sa.Text(), nullable=False),
        sa.Column("scope_id", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("score", sa.REAL(), nullable=True),
        sa.Column("details_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.CheckConstraint("trim(id) <> ''", name="ck_quality_checks_id"),
        sa.CheckConstraint("trim(check_type) <> ''", name="ck_quality_checks_type"),
        sa.CheckConstraint("trim(scope_type) <> ''", name="ck_quality_checks_scope_type"),
        sa.CheckConstraint("trim(scope_id) <> ''", name="ck_quality_checks_scope_id"),
        sa.CheckConstraint(
            f"status IN ({_CHECK_STATUSES})",
            name="ck_quality_checks_status",
        ),
        sa.CheckConstraint(
            "score IS NULL OR score BETWEEN 0.0 AND 1.0",
            name="ck_quality_checks_score",
        ),
        sa.CheckConstraint(
            "details_json IS NULL OR json_valid(details_json)",
            name="ck_quality_checks_details_json_valid",
        ),
        sa.CheckConstraint("trim(created_at) <> ''", name="ck_quality_checks_created_at"),
        sa.ForeignKeyConstraint(
            ["report_id"],
            ["quality_reports.id"],
            name="fk_quality_checks_report_id_quality_reports",
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sqlite_strict=True,
    )

    op.create_index(
        "ix_quality_reports_project_status",
        "quality_reports",
        ["project_id", "status"],
    )
    op.create_index(
        "ix_quality_reports_project_type",
        "quality_reports",
        ["project_id", "report_type"],
    )
    op.create_index(
        "ix_quality_checks_report_status",
        "quality_checks",
        ["report_id", "status"],
    )
    op.create_index(
        "ix_quality_checks_scope",
        "quality_checks",
        ["scope_type", "scope_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_quality_checks_scope", table_name="quality_checks")
    op.drop_index("ix_quality_checks_report_status", table_name="quality_checks")
    op.drop_index("ix_quality_reports_project_type", table_name="quality_reports")
    op.drop_index("ix_quality_reports_project_status", table_name="quality_reports")
    op.drop_table("quality_checks")
    op.drop_table("quality_reports")
