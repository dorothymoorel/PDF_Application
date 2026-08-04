import json
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol
from uuid import UUID, uuid4

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker
from transloka_core.database import transaction_scope
from transloka_core.database.models.documents import Document
from transloka_core.database.models.files import StoredFile
from transloka_core.database.models.jobs import ApplicationJob, JobStatus, JobType
from transloka_core.database.models.projects import Project

QUEUE_DISPATCH_FAILED = "QUEUE_DISPATCH_FAILED"
_MAX_IDEMPOTENCY_KEY_LENGTH = 200

# SQLAlchemy needs all foreign-key target tables registered when this module is imported alone.
_JOB_MODEL_DEPENDENCIES = (Document, Project, StoredFile)


class JobQueue(Protocol):
    @property
    def name(self) -> str: ...

    def enqueue(self, job_id: str) -> None: ...


class JobDispatchError(RuntimeError):
    pass


class InvalidJobDispatchError(ValueError):
    pass


class JobIdempotencyConflictError(JobDispatchError):
    pass


class JobQueueUnavailableError(JobDispatchError):
    def __init__(self, job_id: str) -> None:
        self.job_id = job_id
        super().__init__("The job queue is unavailable.")


@dataclass(frozen=True, slots=True)
class JobDispatchResult:
    job_id: str
    status: JobStatus
    created: bool


class JobDispatchService:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        queue: JobQueue,
    ) -> None:
        _validate_text(queue.name, "Queue name")
        self._session_factory = session_factory
        self._queue = queue
        self._queue_name = queue.name

    def dispatch(
        self,
        *,
        job_type: JobType,
        idempotency_key: str,
        project_id: str | None = None,
        document_id: str | None = None,
        page_ids: Sequence[str] = (),
        max_retries: int = 3,
    ) -> JobDispatchResult:
        payload_json = _validate_and_serialize_request(
            job_type=job_type,
            idempotency_key=idempotency_key,
            project_id=project_id,
            document_id=document_id,
            page_ids=page_ids,
            max_retries=max_retries,
        )
        existing = self._existing_job(idempotency_key)
        if existing is not None:
            if not _matches_request(
                existing,
                job_type=job_type,
                project_id=project_id,
                document_id=document_id,
                queue_name=self._queue_name,
                payload_json=payload_json,
                max_retries=max_retries,
            ):
                raise JobIdempotencyConflictError(
                    "The idempotency key belongs to a different job request."
                )
            return JobDispatchResult(existing.id, _status(existing), created=False)

        job_id = f"job_{uuid4()}"
        created_at = _utc_now()
        with transaction_scope(self._session_factory) as session:
            session.add(
                ApplicationJob(
                    id=job_id,
                    project_id=project_id,
                    document_id=document_id,
                    parent_job_id=None,
                    job_type=job_type.value,
                    queue_name=self._queue_name,
                    status=JobStatus.CREATED.value,
                    progress=0.0,
                    current_stage=None,
                    idempotency_key=idempotency_key,
                    payload_json=payload_json,
                    result_json=None,
                    retry_count=0,
                    max_retries=max_retries,
                    error_code=None,
                    error_message=None,
                    created_at=created_at,
                    queued_at=None,
                    started_at=None,
                    completed_at=None,
                    cancelled_at=None,
                    heartbeat_at=None,
                )
            )
            session.flush()

        try:
            self._queue.enqueue(job_id)
        except Exception as exc:
            self._mark_dispatch_failed(job_id)
            raise JobQueueUnavailableError(job_id) from exc

        queued_at = _utc_now()
        with transaction_scope(self._session_factory) as session:
            row = _created_job(session, job_id)
            row.status = JobStatus.QUEUED.value
            row.queued_at = queued_at
            session.flush()
        return JobDispatchResult(job_id, JobStatus.QUEUED, created=True)

    def _existing_job(self, idempotency_key: str) -> ApplicationJob | None:
        with self._session_factory() as session:
            return session.scalar(
                select(ApplicationJob).where(ApplicationJob.idempotency_key == idempotency_key)
            )

    def _mark_dispatch_failed(self, job_id: str) -> None:
        failed_at = _utc_now()
        with transaction_scope(self._session_factory) as session:
            row = _created_job(session, job_id)
            row.status = JobStatus.FAILED.value
            row.error_code = QUEUE_DISPATCH_FAILED
            row.error_message = "The job could not be queued."
            row.completed_at = failed_at
            session.flush()


def _validate_and_serialize_request(
    *,
    job_type: JobType,
    idempotency_key: str,
    project_id: str | None,
    document_id: str | None,
    page_ids: Sequence[str],
    max_retries: int,
) -> str:
    if not isinstance(job_type, JobType):
        raise InvalidJobDispatchError("The job type is invalid.")
    _validate_text(idempotency_key, "Idempotency key", _MAX_IDEMPOTENCY_KEY_LENGTH)
    _validate_optional_identifier(project_id, "prj_")
    _validate_optional_identifier(document_id, "doc_")
    if isinstance(page_ids, (str, bytes)) or not isinstance(page_ids, Sequence):
        raise InvalidJobDispatchError("Page identifiers are invalid.")
    for page_id in page_ids:
        _validate_identifier(page_id, "pag_")
    if isinstance(max_retries, bool) or not isinstance(max_retries, int) or max_retries < 0:
        raise InvalidJobDispatchError("Maximum retries must be a non-negative integer.")
    return json.dumps(
        {
            "document_id": document_id,
            "page_ids": list(page_ids),
            "project_id": project_id,
        },
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def _matches_request(
    row: ApplicationJob,
    *,
    job_type: JobType,
    project_id: str | None,
    document_id: str | None,
    queue_name: str,
    payload_json: str,
    max_retries: int,
) -> bool:
    return (
        row.job_type == job_type.value
        and row.project_id == project_id
        and row.document_id == document_id
        and row.queue_name == queue_name
        and row.payload_json == payload_json
        and row.max_retries == max_retries
    )


def _created_job(session: Session, job_id: str) -> ApplicationJob:
    row = session.get(ApplicationJob, job_id)
    if row is None or row.status != JobStatus.CREATED.value:
        raise JobDispatchError("The created job is unavailable or has an invalid status.")
    return row


def _status(row: ApplicationJob) -> JobStatus:
    try:
        return JobStatus(row.status)
    except ValueError:
        raise JobDispatchError("The stored job status is invalid.") from None


def _validate_optional_identifier(value: str | None, prefix: str) -> None:
    if value is not None:
        _validate_identifier(value, prefix)


def _validate_identifier(value: str, prefix: str) -> None:
    if not isinstance(value, str) or not value.startswith(prefix):
        raise InvalidJobDispatchError("A job identifier is invalid.")
    try:
        parsed = UUID(value[len(prefix) :])
    except (ValueError, AttributeError):
        raise InvalidJobDispatchError("A job identifier is invalid.") from None
    if value != f"{prefix}{parsed}":
        raise InvalidJobDispatchError("A job identifier is invalid.")


def _validate_text(value: str, label: str, max_length: int | None = None) -> None:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or not value.isprintable()
        or (max_length is not None and len(value) > max_length)
    ):
        raise InvalidJobDispatchError(f"{label} is invalid.")


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")
