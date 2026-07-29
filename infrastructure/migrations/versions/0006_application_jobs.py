"""Create application job persistence tables.

Revision ID: 0006_application_jobs
Revises: 0005_documents
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006_application_jobs"
down_revision: str | Sequence[str] | None = "0005_documents"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_JOB_TYPES = (
    "'IMPORT_DOCUMENT', 'ANALYZE_DOCUMENT', 'OCR_DOCUMENT', 'DETECT_TERMS', "
    "'TRANSLATE_DOCUMENT', 'RECONSTRUCT_DOCUMENT', 'EXPORT_DOCUMENT', "
    "'BENCHMARK_MODEL', 'BACKUP_DATABASE', 'RESTORE_DATABASE', 'MAINTENANCE'"
)
_JOB_STATUSES = (
    "'CREATED', 'QUEUED', 'RUNNING', 'RETRYING', 'COMPLETED', "
    "'COMPLETED_WITH_WARNINGS', 'PARTIALLY_COMPLETED', 'FAILED', "
    "'CANCELLATION_REQUESTED', 'CANCELLED', 'STALE'"
)
_ATTEMPT_STATUSES = (
    "'RUNNING', 'COMPLETED', 'COMPLETED_WITH_WARNINGS', "
    "'PARTIALLY_COMPLETED', 'FAILED', 'CANCELLED', 'STALE'"
)
_DEPENDENCY_TYPES = "'REQUIRED', 'OPTIONAL', 'ORDER_ONLY'"


def upgrade() -> None:
    op.create_table(
        "application_jobs",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("project_id", sa.Text(), nullable=True),
        sa.Column("document_id", sa.Text(), nullable=True),
        sa.Column("parent_job_id", sa.Text(), nullable=True),
        sa.Column("job_type", sa.Text(), nullable=False),
        sa.Column("queue_name", sa.Text(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("progress", sa.REAL(), nullable=False),
        sa.Column("current_stage", sa.Text(), nullable=True),
        sa.Column("idempotency_key", sa.Text(), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.Column("result_json", sa.Text(), nullable=True),
        sa.Column("retry_count", sa.Integer(), nullable=False),
        sa.Column("max_retries", sa.Integer(), nullable=False),
        sa.Column("error_code", sa.Text(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.Text(), nullable=False),
        sa.Column("queued_at", sa.Text(), nullable=True),
        sa.Column("started_at", sa.Text(), nullable=True),
        sa.Column("completed_at", sa.Text(), nullable=True),
        sa.Column("cancelled_at", sa.Text(), nullable=True),
        sa.Column("heartbeat_at", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "length(id) = 40 AND substr(id, 1, 4) = 'job_' "
            "AND substr(id, 13, 1) = '-' AND substr(id, 18, 1) = '-' "
            "AND substr(id, 23, 1) = '-' AND substr(id, 28, 1) = '-'",
            name="ck_application_jobs_prefixed_uuid",
        ),
        sa.CheckConstraint(
            f"job_type IN ({_JOB_TYPES})",
            name="ck_application_jobs_type",
        ),
        sa.CheckConstraint(
            f"status IN ({_JOB_STATUSES})",
            name="ck_application_jobs_status",
        ),
        sa.CheckConstraint(
            "progress >= 0.0 AND progress <= 1.0",
            name="ck_application_jobs_progress",
        ),
        sa.CheckConstraint(
            "retry_count >= 0",
            name="ck_application_jobs_retry_count",
        ),
        sa.CheckConstraint(
            "max_retries >= 0",
            name="ck_application_jobs_max_retries",
        ),
        sa.CheckConstraint(
            "json_valid(payload_json)",
            name="ck_application_jobs_payload_json_valid",
        ),
        sa.CheckConstraint(
            "result_json IS NULL OR json_valid(result_json)",
            name="ck_application_jobs_result_json_valid",
        ),
        sa.ForeignKeyConstraint(
            ["project_id"],
            ["projects.id"],
            name="fk_application_jobs_project_id_projects",
        ),
        sa.ForeignKeyConstraint(
            ["document_id"],
            ["documents.id"],
            name="fk_application_jobs_document_id_documents",
        ),
        sa.PrimaryKeyConstraint("id"),
        sqlite_strict=True,
    )
    op.create_index(
        "uq_application_jobs_idempotency_key",
        "application_jobs",
        ["idempotency_key"],
        unique=True,
    )
    op.create_index(
        "ix_application_jobs_project_status",
        "application_jobs",
        ["project_id", "status"],
    )
    op.create_index(
        "ix_application_jobs_type_status",
        "application_jobs",
        ["job_type", "status"],
    )
    op.create_index(
        "ix_application_jobs_heartbeat",
        "application_jobs",
        ["status", "heartbeat_at"],
    )

    op.create_table(
        "job_attempts",
        sa.Column("id", sa.Text(), nullable=False),
        sa.Column("job_id", sa.Text(), nullable=False),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("worker_identifier", sa.Text(), nullable=True),
        sa.Column("started_at", sa.Text(), nullable=False),
        sa.Column("completed_at", sa.Text(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("error_code", sa.Text(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("details_json", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "attempt_number >= 1",
            name="ck_job_attempts_number",
        ),
        sa.CheckConstraint(
            f"status IN ({_ATTEMPT_STATUSES})",
            name="ck_job_attempts_status",
        ),
        sa.CheckConstraint(
            "duration_ms IS NULL OR duration_ms >= 0",
            name="ck_job_attempts_duration",
        ),
        sa.CheckConstraint(
            "details_json IS NULL OR json_valid(details_json)",
            name="ck_job_attempts_details_json_valid",
        ),
        sa.ForeignKeyConstraint(
            ["job_id"],
            ["application_jobs.id"],
            name="fk_job_attempts_job_id_application_jobs",
        ),
        sa.PrimaryKeyConstraint("id"),
        sqlite_strict=True,
    )
    op.create_index(
        "uq_job_attempts_number",
        "job_attempts",
        ["job_id", "attempt_number"],
        unique=True,
    )

    op.create_table(
        "job_dependencies",
        sa.Column("job_id", sa.Text(), nullable=False),
        sa.Column("depends_on_job_id", sa.Text(), nullable=False),
        sa.Column("dependency_type", sa.Text(), nullable=False),
        sa.CheckConstraint(
            f"dependency_type IN ({_DEPENDENCY_TYPES})",
            name="ck_job_dependencies_type",
        ),
        sa.ForeignKeyConstraint(
            ["job_id"],
            ["application_jobs.id"],
            name="fk_job_dependencies_job_id_application_jobs",
        ),
        sa.ForeignKeyConstraint(
            ["depends_on_job_id"],
            ["application_jobs.id"],
            name="fk_job_dependencies_depends_on_job_id_application_jobs",
        ),
        sa.PrimaryKeyConstraint("job_id", "depends_on_job_id"),
        sqlite_strict=True,
    )


def downgrade() -> None:
    op.drop_table("job_dependencies")
    op.drop_index("uq_job_attempts_number", table_name="job_attempts")
    op.drop_table("job_attempts")
    op.drop_index("ix_application_jobs_heartbeat", table_name="application_jobs")
    op.drop_index("ix_application_jobs_type_status", table_name="application_jobs")
    op.drop_index("ix_application_jobs_project_status", table_name="application_jobs")
    op.drop_index("uq_application_jobs_idempotency_key", table_name="application_jobs")
    op.drop_table("application_jobs")
