from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy.orm import Session, sessionmaker
from transloka_core.database import transaction_scope
from transloka_core.database.models.jobs import ApplicationJob, JobStatus

_IDEMPOTENT_STATUSES = {
    JobStatus.CANCELLATION_REQUESTED,
    JobStatus.CANCELLED,
}
_MAX_REASON_LENGTH = 500


class JobCancellationError(RuntimeError):
    pass


class CancellationJobNotFoundError(JobCancellationError):
    pass


class JobCannotBeCancelledError(JobCancellationError):
    pass


class CancellationCleanupError(JobCancellationError):
    pass


class InvalidCancellationReasonError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class JobCancellationSnapshot:
    job_id: str
    status: JobStatus
    cancelled_at: str | None


class JobCancellationService:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        temporary_root: Path,
    ) -> None:
        if not temporary_root.is_absolute():
            raise ValueError("The temporary output root must be absolute.")
        self._session_factory = session_factory
        self._temporary_root = temporary_root.resolve(strict=False)

    def request(self, job_id: str, *, reason: str) -> JobCancellationSnapshot:
        _validate_reason(reason)
        now = _utc_now()
        with transaction_scope(self._session_factory) as session:
            row = _get_job(session, job_id)
            status = _job_status(row)
            if status == JobStatus.QUEUED:
                row.status = JobStatus.CANCELLED.value
                row.current_stage = JobStatus.CANCELLED.value
                row.cancelled_at = now
                row.completed_at = now
            elif status == JobStatus.RUNNING:
                row.status = JobStatus.CANCELLATION_REQUESTED.value
            elif status not in _IDEMPOTENT_STATUSES:
                raise JobCannotBeCancelledError("The job can no longer be cancelled.")
            session.flush()
            return _snapshot(row)

    def checkpoint(
        self,
        job_id: str,
        *,
        incomplete_outputs: Iterable[Path] = (),
    ) -> bool:
        status = self._read_status(job_id)
        if status not in _IDEMPOTENT_STATUSES:
            return False

        outputs = tuple(self._controlled_output(path) for path in incomplete_outputs)
        self._remove_incomplete_outputs(outputs)
        if status == JobStatus.CANCELLED:
            return True

        now = _utc_now()
        with transaction_scope(self._session_factory) as session:
            row = _get_job(session, job_id)
            current_status = _job_status(row)
            if current_status == JobStatus.CANCELLED:
                return True
            if current_status != JobStatus.CANCELLATION_REQUESTED:
                raise JobCannotBeCancelledError("The job can no longer be cancelled.")
            row.status = JobStatus.CANCELLED.value
            row.current_stage = JobStatus.CANCELLED.value
            row.cancelled_at = now
            row.completed_at = now
        return True

    def _read_status(self, job_id: str) -> JobStatus:
        with self._session_factory() as session:
            return _job_status(_get_job(session, job_id))

    def _controlled_output(self, path: Path) -> Path:
        if not isinstance(path, Path) or not path.is_absolute():
            raise CancellationCleanupError("Incomplete outputs must use absolute paths.")
        resolved = path.resolve(strict=False)
        if resolved == self._temporary_root or not resolved.is_relative_to(self._temporary_root):
            raise CancellationCleanupError("Incomplete outputs must remain in temporary storage.")
        if path.is_symlink() or (path.exists() and not path.is_file()):
            raise CancellationCleanupError("Incomplete output cleanup only accepts regular files.")
        return resolved

    @staticmethod
    def _remove_incomplete_outputs(outputs: tuple[Path, ...]) -> None:
        try:
            for path in outputs:
                path.unlink(missing_ok=True)
        except OSError as exc:
            raise CancellationCleanupError("An incomplete output could not be removed.") from exc


def _get_job(session: Session, job_id: str) -> ApplicationJob:
    row = session.get(ApplicationJob, job_id)
    if row is None:
        raise CancellationJobNotFoundError("The requested job was not found.")
    return row


def _job_status(row: ApplicationJob) -> JobStatus:
    try:
        return JobStatus(row.status)
    except ValueError:
        raise JobCancellationError("The stored job status is invalid.") from None


def _snapshot(row: ApplicationJob) -> JobCancellationSnapshot:
    return JobCancellationSnapshot(
        job_id=row.id,
        status=_job_status(row),
        cancelled_at=row.cancelled_at,
    )


def _validate_reason(value: str) -> None:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or not value.isprintable()
        or len(value) > _MAX_REASON_LENGTH
    ):
        raise InvalidCancellationReasonError("The cancellation reason is invalid.")


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")
