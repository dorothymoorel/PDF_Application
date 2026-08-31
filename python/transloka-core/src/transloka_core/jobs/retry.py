import json
from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker
from transloka_core.database import transaction_scope
from transloka_core.database.models.jobs import (
    ApplicationJob,
    JobAttempt,
    JobAttemptStatus,
    JobStatus,
)

_MAX_IDEMPOTENCY_KEY_LENGTH = 200
_MAX_REASON_LENGTH = 200
_RETRYABLE_STATUSES = {
    JobStatus.CANCELLED,
    JobStatus.COMPLETED_WITH_WARNINGS,
    JobStatus.FAILED,
    JobStatus.PARTIALLY_COMPLETED,
    JobStatus.STALE,
}
_ATTEMPT_STATUS_BY_JOB_STATUS = {
    JobStatus.CANCELLED: JobAttemptStatus.CANCELLED,
    JobStatus.COMPLETED_WITH_WARNINGS: JobAttemptStatus.COMPLETED_WITH_WARNINGS,
    JobStatus.FAILED: JobAttemptStatus.FAILED,
    JobStatus.PARTIALLY_COMPLETED: JobAttemptStatus.PARTIALLY_COMPLETED,
    JobStatus.STALE: JobAttemptStatus.STALE,
}


class JobRetryError(RuntimeError):
    pass


class RetryJobNotFoundError(JobRetryError):
    pass


class JobNotRetryableError(JobRetryError):
    pass


class JobRetryLimitError(JobRetryError):
    pass


class RetryIdempotencyConflictError(JobRetryError):
    pass


class JobAttemptHistoryError(JobRetryError):
    pass


class InvalidJobRetryError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class JobRetryResult:
    job_id: str
    status: JobStatus
    retry_count: int
    attempt_id: str
    attempt_number: int
    created: bool


class JobRetryService:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def request(
        self,
        job_id: str,
        *,
        idempotency_key: str,
        retry_failed_items_only: bool,
        reason: str,
        replacement_payload_json: str | None = None,
    ) -> JobRetryResult:
        _validate_text(idempotency_key, "Idempotency key", _MAX_IDEMPOTENCY_KEY_LENGTH)
        _validate_text(reason, "Retry reason", _MAX_REASON_LENGTH)
        if not isinstance(retry_failed_items_only, bool):
            raise InvalidJobRetryError("The failed-items-only option is invalid.")
        _validate_replacement_payload_json(replacement_payload_json)

        attempt_id = _retry_attempt_id(job_id, idempotency_key)
        details_json = _retry_details_json(
            idempotency_key=idempotency_key,
            retry_failed_items_only=retry_failed_items_only,
            reason=reason,
        )
        now = _utc_now()
        with transaction_scope(self._session_factory) as session:
            row = _get_job(session, job_id)
            existing = session.get(JobAttempt, attempt_id)
            if existing is not None:
                if existing.job_id != job_id or existing.details_json != details_json:
                    raise RetryIdempotencyConflictError(
                        "The idempotency key belongs to a different retry request."
                    )
                return _result(row, existing, created=False)

            status = _job_status(row)
            if status not in _RETRYABLE_STATUSES:
                raise JobNotRetryableError("The job state does not allow retry.")
            if row.retry_count >= row.max_retries:
                raise JobRetryLimitError("The job retry limit has been reached.")

            attempts = list(
                session.scalars(
                    select(JobAttempt)
                    .where(JobAttempt.job_id == job_id)
                    .order_by(JobAttempt.attempt_number)
                )
            )
            _validate_attempt_history(attempts)
            if not attempts:
                attempts.append(_historical_attempt(row, status, now))
                session.add(attempts[-1])
            elif _attempt_status(attempts[-1]) == JobAttemptStatus.RUNNING:
                _finalize_attempt(attempts[-1], row, status, now)

            attempt = JobAttempt(
                id=attempt_id,
                job_id=job_id,
                attempt_number=attempts[-1].attempt_number + 1,
                status=JobAttemptStatus.RUNNING.value,
                worker_identifier=None,
                started_at=now,
                completed_at=None,
                duration_ms=None,
                error_code=None,
                error_message=None,
                details_json=details_json,
            )
            session.add(attempt)
            row.status = JobStatus.RETRYING.value
            row.retry_count += 1
            row.current_stage = JobStatus.RETRYING.value
            row.queued_at = None
            row.started_at = None
            row.completed_at = None
            row.cancelled_at = None
            row.heartbeat_at = None
            if replacement_payload_json is not None:
                row.payload_json = replacement_payload_json
            session.flush()
            return _result(row, attempt, created=True)


def _get_job(session: Session, job_id: str) -> ApplicationJob:
    row = session.get(ApplicationJob, job_id)
    if row is None:
        raise RetryJobNotFoundError("The requested job was not found.")
    return row


def _historical_attempt(
    row: ApplicationJob,
    status: JobStatus,
    now: str,
) -> JobAttempt:
    return JobAttempt(
        id=str(uuid5(NAMESPACE_URL, f"transloka:job-attempt:{row.id}:1")),
        job_id=row.id,
        attempt_number=1,
        status=_ATTEMPT_STATUS_BY_JOB_STATUS[status].value,
        worker_identifier=None,
        started_at=row.started_at or row.created_at,
        completed_at=row.completed_at or row.cancelled_at or now,
        duration_ms=None,
        error_code=row.error_code,
        error_message=row.error_message,
        details_json=None,
    )


def _finalize_attempt(
    attempt: JobAttempt,
    row: ApplicationJob,
    status: JobStatus,
    now: str,
) -> None:
    attempt.status = _ATTEMPT_STATUS_BY_JOB_STATUS[status].value
    attempt.completed_at = row.completed_at or row.cancelled_at or now
    attempt.error_code = row.error_code
    attempt.error_message = row.error_message


def _validate_attempt_history(attempts: list[JobAttempt]) -> None:
    numbers = [attempt.attempt_number for attempt in attempts]
    if numbers != list(range(1, len(attempts) + 1)):
        raise JobAttemptHistoryError("The stored job attempt history is incomplete.")
    for attempt in attempts[:-1]:
        if _attempt_status(attempt) == JobAttemptStatus.RUNNING:
            raise JobAttemptHistoryError("The stored job attempt history is invalid.")


def _job_status(row: ApplicationJob) -> JobStatus:
    try:
        return JobStatus(row.status)
    except ValueError:
        raise JobRetryError("The stored job status is invalid.") from None


def _attempt_status(row: JobAttempt) -> JobAttemptStatus:
    try:
        return JobAttemptStatus(row.status)
    except ValueError:
        raise JobAttemptHistoryError("The stored job attempt status is invalid.") from None


def _result(
    job: ApplicationJob,
    attempt: JobAttempt,
    *,
    created: bool,
) -> JobRetryResult:
    return JobRetryResult(
        job_id=job.id,
        status=_job_status(job),
        retry_count=job.retry_count,
        attempt_id=attempt.id,
        attempt_number=attempt.attempt_number,
        created=created,
    )


def _retry_attempt_id(job_id: str, idempotency_key: str) -> str:
    return str(uuid5(NAMESPACE_URL, f"transloka:job-retry:{job_id}:{idempotency_key}"))


def _retry_details_json(
    *,
    idempotency_key: str,
    retry_failed_items_only: bool,
    reason: str,
) -> str:
    return json.dumps(
        {
            "retry": {
                "failed_items_only": retry_failed_items_only,
                "idempotency_key": idempotency_key,
                "reason": reason,
            }
        },
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def _validate_text(value: str, label: str, max_length: int) -> None:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or not value.isprintable()
        or len(value) > max_length
    ):
        raise InvalidJobRetryError(f"{label} is invalid.")


def _validate_replacement_payload_json(value: str | None) -> None:
    if value is None:
        return
    if type(value) is not str or not value:
        raise InvalidJobRetryError("The replacement job payload is invalid.")
    try:
        decoded = json.loads(value)
    except (TypeError, ValueError):
        raise InvalidJobRetryError("The replacement job payload is invalid.") from None
    if not isinstance(decoded, dict):
        raise InvalidJobRetryError("The replacement job payload is invalid.")


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")
