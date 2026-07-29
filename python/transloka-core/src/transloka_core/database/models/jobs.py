from enum import StrEnum

from sqlalchemy import REAL, CheckConstraint, ForeignKey, Index, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column
from transloka_core.database.models.application import Base


class JobType(StrEnum):
    IMPORT_DOCUMENT = "IMPORT_DOCUMENT"
    ANALYZE_DOCUMENT = "ANALYZE_DOCUMENT"
    OCR_DOCUMENT = "OCR_DOCUMENT"
    DETECT_TERMS = "DETECT_TERMS"
    TRANSLATE_DOCUMENT = "TRANSLATE_DOCUMENT"
    RECONSTRUCT_DOCUMENT = "RECONSTRUCT_DOCUMENT"
    EXPORT_DOCUMENT = "EXPORT_DOCUMENT"
    BENCHMARK_MODEL = "BENCHMARK_MODEL"
    BACKUP_DATABASE = "BACKUP_DATABASE"
    RESTORE_DATABASE = "RESTORE_DATABASE"
    MAINTENANCE = "MAINTENANCE"


class JobStatus(StrEnum):
    CREATED = "CREATED"
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    RETRYING = "RETRYING"
    COMPLETED = "COMPLETED"
    COMPLETED_WITH_WARNINGS = "COMPLETED_WITH_WARNINGS"
    PARTIALLY_COMPLETED = "PARTIALLY_COMPLETED"
    FAILED = "FAILED"
    CANCELLATION_REQUESTED = "CANCELLATION_REQUESTED"
    CANCELLED = "CANCELLED"
    STALE = "STALE"


class JobAttemptStatus(StrEnum):
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    COMPLETED_WITH_WARNINGS = "COMPLETED_WITH_WARNINGS"
    PARTIALLY_COMPLETED = "PARTIALLY_COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    STALE = "STALE"


class JobDependencyType(StrEnum):
    REQUIRED = "REQUIRED"
    OPTIONAL = "OPTIONAL"
    ORDER_ONLY = "ORDER_ONLY"


def _sql_values(enum_type: type[StrEnum]) -> str:
    return ", ".join(f"'{member.value}'" for member in enum_type)


class ApplicationJob(Base):
    __tablename__ = "application_jobs"
    __table_args__ = (
        CheckConstraint(
            "length(id) = 40 AND substr(id, 1, 4) = 'job_' "
            "AND substr(id, 13, 1) = '-' AND substr(id, 18, 1) = '-' "
            "AND substr(id, 23, 1) = '-' AND substr(id, 28, 1) = '-'",
            name="ck_application_jobs_prefixed_uuid",
        ),
        CheckConstraint(
            f"job_type IN ({_sql_values(JobType)})",
            name="ck_application_jobs_type",
        ),
        CheckConstraint(
            f"status IN ({_sql_values(JobStatus)})",
            name="ck_application_jobs_status",
        ),
        CheckConstraint(
            "progress >= 0.0 AND progress <= 1.0",
            name="ck_application_jobs_progress",
        ),
        CheckConstraint("retry_count >= 0", name="ck_application_jobs_retry_count"),
        CheckConstraint("max_retries >= 0", name="ck_application_jobs_max_retries"),
        CheckConstraint(
            "json_valid(payload_json)",
            name="ck_application_jobs_payload_json_valid",
        ),
        CheckConstraint(
            "result_json IS NULL OR json_valid(result_json)",
            name="ck_application_jobs_result_json_valid",
        ),
        {"sqlite_strict": True},
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    project_id: Mapped[str | None] = mapped_column(
        Text,
        ForeignKey("projects.id"),
        nullable=True,
    )
    document_id: Mapped[str | None] = mapped_column(
        Text,
        ForeignKey("documents.id"),
        nullable=True,
    )
    parent_job_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    job_type: Mapped[str] = mapped_column(Text, nullable=False)
    queue_name: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    progress: Mapped[float] = mapped_column(REAL, nullable=False)
    current_stage: Mapped[str | None] = mapped_column(Text, nullable=True)
    idempotency_key: Mapped[str] = mapped_column(Text, nullable=False)
    payload_json: Mapped[str] = mapped_column(Text, nullable=False)
    result_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, nullable=False)
    max_retries: Mapped[int] = mapped_column(Integer, nullable=False)
    error_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[str] = mapped_column(Text, nullable=False)
    queued_at: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[str | None] = mapped_column(Text, nullable=True)
    completed_at: Mapped[str | None] = mapped_column(Text, nullable=True)
    cancelled_at: Mapped[str | None] = mapped_column(Text, nullable=True)
    heartbeat_at: Mapped[str | None] = mapped_column(Text, nullable=True)


class JobAttempt(Base):
    __tablename__ = "job_attempts"
    __table_args__ = (
        CheckConstraint(
            "attempt_number >= 1",
            name="ck_job_attempts_number",
        ),
        CheckConstraint(
            f"status IN ({_sql_values(JobAttemptStatus)})",
            name="ck_job_attempts_status",
        ),
        CheckConstraint(
            "duration_ms IS NULL OR duration_ms >= 0",
            name="ck_job_attempts_duration",
        ),
        CheckConstraint(
            "details_json IS NULL OR json_valid(details_json)",
            name="ck_job_attempts_details_json_valid",
        ),
        {"sqlite_strict": True},
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    job_id: Mapped[str] = mapped_column(
        Text,
        ForeignKey("application_jobs.id"),
        nullable=False,
    )
    attempt_number: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    worker_identifier: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[str] = mapped_column(Text, nullable=False)
    completed_at: Mapped[str | None] = mapped_column(Text, nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_code: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    details_json: Mapped[str | None] = mapped_column(Text, nullable=True)


class JobDependency(Base):
    __tablename__ = "job_dependencies"
    __table_args__ = (
        CheckConstraint(
            f"dependency_type IN ({_sql_values(JobDependencyType)})",
            name="ck_job_dependencies_type",
        ),
        {"sqlite_strict": True},
    )

    job_id: Mapped[str] = mapped_column(
        Text,
        ForeignKey("application_jobs.id"),
        primary_key=True,
    )
    depends_on_job_id: Mapped[str] = mapped_column(
        Text,
        ForeignKey("application_jobs.id"),
        primary_key=True,
    )
    dependency_type: Mapped[str] = mapped_column(Text, nullable=False)


Index(
    "uq_application_jobs_idempotency_key",
    ApplicationJob.idempotency_key,
    unique=True,
)
Index(
    "ix_application_jobs_project_status",
    ApplicationJob.project_id,
    ApplicationJob.status,
)
Index(
    "ix_application_jobs_type_status",
    ApplicationJob.job_type,
    ApplicationJob.status,
)
Index(
    "ix_application_jobs_heartbeat",
    ApplicationJob.status,
    ApplicationJob.heartbeat_at,
)
Index(
    "uq_job_attempts_number",
    JobAttempt.job_id,
    JobAttempt.attempt_number,
    unique=True,
)
