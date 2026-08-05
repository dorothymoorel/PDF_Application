import math
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy.orm import Session, sessionmaker
from transloka_core.database import transaction_scope
from transloka_core.database.models.jobs import ApplicationJob, JobStatus

_ACTIVE_STATUSES = {
    JobStatus.QUEUED,
    JobStatus.RUNNING,
    JobStatus.CANCELLATION_REQUESTED,
}


class JobProgressError(RuntimeError):
    pass


class JobNotFoundError(JobProgressError):
    pass


class JobNotActiveError(JobProgressError):
    pass


class InvalidJobProgressError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class JobProgressSnapshot:
    job_id: str
    status: JobStatus
    progress: float
    current_stage: str | None
    heartbeat_at: str | None


class JobProgressService:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def update(
        self,
        job_id: str,
        *,
        progress: float,
        current_stage: str,
    ) -> JobProgressSnapshot:
        _validate_progress(progress)
        _validate_stage(current_stage)
        now = _utc_now()
        with transaction_scope(self._session_factory) as session:
            row = _active_job(session, job_id)
            if row.status == JobStatus.QUEUED.value:
                row.status = JobStatus.RUNNING.value
                row.started_at = now
            row.progress = progress
            row.current_stage = current_stage
            row.heartbeat_at = now
            session.flush()
            return _snapshot(row)

    def heartbeat(self, job_id: str) -> JobProgressSnapshot:
        now = _utc_now()
        with transaction_scope(self._session_factory) as session:
            row = _active_job(session, job_id, allow_queued=False)
            row.heartbeat_at = now
            session.flush()
            return _snapshot(row)


def _active_job(
    session: Session,
    job_id: str,
    *,
    allow_queued: bool = True,
) -> ApplicationJob:
    row = session.get(ApplicationJob, job_id)
    if row is None:
        raise JobNotFoundError("The requested job was not found.")
    try:
        status = JobStatus(row.status)
    except ValueError:
        raise JobProgressError("The stored job status is invalid.") from None
    allowed = _ACTIVE_STATUSES if allow_queued else _ACTIVE_STATUSES - {JobStatus.QUEUED}
    if status not in allowed:
        raise JobNotActiveError("The job is no longer active.")
    return row


def _snapshot(row: ApplicationJob) -> JobProgressSnapshot:
    return JobProgressSnapshot(
        job_id=row.id,
        status=JobStatus(row.status),
        progress=row.progress,
        current_stage=row.current_stage,
        heartbeat_at=row.heartbeat_at,
    )


def _validate_progress(value: float) -> None:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(value)
        or not 0.0 <= value <= 1.0
    ):
        raise InvalidJobProgressError("Job progress must be between 0 and 1.")


def _validate_stage(value: str) -> None:
    if not isinstance(value, str) or not value or value != value.strip() or not value.isprintable():
        raise InvalidJobProgressError("The current job stage is invalid.")


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")
