import base64
import binascii
from collections.abc import Iterator
from typing import Annotated, Any, Never, cast

from fastapi import APIRouter, Depends, Header, Query, Request, Response, status
from sqlalchemy import and_, or_, select
from sqlalchemy.orm import Session, sessionmaker
from transloka_api.config import Settings
from transloka_api.exception_handlers import TransLokaError
from transloka_api.middleware import get_request_id
from transloka_api.schemas import ErrorResponse
from transloka_api.schemas.jobs import (
    CancelJobRequest,
    CursorPagination,
    JobAttemptErrorResponse,
    JobAttemptListResponse,
    JobAttemptResponse,
    JobCollectionMeta,
    JobDataResponse,
    JobErrorResponse,
    JobListResponse,
    JobResponse,
    RetryJobRequest,
)
from transloka_api.schemas.projects import ResponseMeta
from transloka_core.database.models.jobs import (
    ApplicationJob,
    JobAttempt,
    JobAttemptStatus,
    JobStatus,
    JobType,
)
from transloka_core.jobs.cancellation import (
    CancellationJobNotFoundError,
    JobCancellationService,
    JobCannotBeCancelledError,
)
from transloka_core.jobs.retry import (
    InvalidJobRetryError,
    JobNotRetryableError,
    JobRetryLimitError,
    JobRetryService,
    RetryIdempotencyConflictError,
    RetryJobNotFoundError,
)

_ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    403: {
        "description": "The request was rejected by the local security policy.",
        "model": ErrorResponse,
    },
    404: {"description": "The job was not found.", "model": ErrorResponse},
    422: {"description": "The request contains invalid values.", "model": ErrorResponse},
    500: {"description": "An unexpected server error was normalized.", "model": ErrorResponse},
}
_CANCEL_ERROR_RESPONSES = {
    **_ERROR_RESPONSES,
    409: {
        "description": "The job state does not allow cancellation.",
        "model": ErrorResponse,
    },
}
_RETRY_ERROR_RESPONSES = {
    **_ERROR_RESPONSES,
    409: {
        "description": "The job state, retry limit, or idempotency key prevents retry.",
        "model": ErrorResponse,
    },
}
_FAST_POLL_STATUSES = {JobStatus.RUNNING, JobStatus.CANCELLATION_REQUESTED}
_SLOW_POLL_STATUSES = {JobStatus.CREATED, JobStatus.QUEUED, JobStatus.RETRYING}

router = APIRouter(prefix="/api/v1/jobs", tags=["Jobs"])


def get_job_session(request: Request) -> Iterator[Session]:
    try:
        factory = request.app.state.session_factory
    except AttributeError as exc:
        raise RuntimeError("The job database is not configured.") from exc
    if not callable(factory):
        raise RuntimeError("The job database is not configured.")
    with cast(sessionmaker[Session], factory)() as session:
        yield session


JobSession = Annotated[Session, Depends(get_job_session)]


@router.get(
    "",
    operation_id="list_jobs",
    response_model=JobListResponse,
    responses=_ERROR_RESPONSES,
)
def list_jobs(
    session: JobSession,
    project_id: str | None = None,
    document_id: str | None = None,
    job_type: JobType | None = None,
    job_status: Annotated[JobStatus | None, Query(alias="status")] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    cursor: Annotated[str | None, Query(min_length=1, max_length=1024)] = None,
) -> JobListResponse:
    statement = select(ApplicationJob)
    if project_id is not None:
        statement = statement.where(ApplicationJob.project_id == project_id)
    if document_id is not None:
        statement = statement.where(ApplicationJob.document_id == document_id)
    if job_type is not None:
        statement = statement.where(ApplicationJob.job_type == job_type.value)
    if job_status is not None:
        statement = statement.where(ApplicationJob.status == job_status.value)
    if cursor is not None:
        created_at, job_id = _decode_cursor(cursor)
        statement = statement.where(
            or_(
                ApplicationJob.created_at < created_at,
                and_(ApplicationJob.created_at == created_at, ApplicationJob.id < job_id),
            )
        )

    rows = list(
        session.scalars(
            statement.order_by(ApplicationJob.created_at.desc(), ApplicationJob.id.desc()).limit(
                limit + 1
            )
        )
    )
    has_more = len(rows) > limit
    page = rows[:limit]
    next_cursor = _encode_cursor(page[-1]) if has_more else None
    return JobListResponse(
        data=[_job_response(row) for row in page],
        meta=JobCollectionMeta(
            request_id=_request_id(),
            pagination=CursorPagination(
                limit=limit,
                next_cursor=next_cursor,
                has_more=has_more,
            ),
        ),
    )


@router.get(
    "/{job_id}/attempts",
    operation_id="get_job_attempts",
    response_model=JobAttemptListResponse,
    responses=_ERROR_RESPONSES,
)
def get_job_attempts(job_id: str, session: JobSession) -> JobAttemptListResponse:
    _get_job(session, job_id)
    attempts = session.scalars(
        select(JobAttempt).where(JobAttempt.job_id == job_id).order_by(JobAttempt.attempt_number)
    ).all()
    return JobAttemptListResponse(
        data=[_attempt_response(attempt) for attempt in attempts],
        meta=ResponseMeta(request_id=_request_id()),
    )


@router.get(
    "/{job_id}",
    operation_id="get_job",
    response_model=JobDataResponse,
    responses=_ERROR_RESPONSES,
)
def get_job(job_id: str, session: JobSession, response: Response) -> JobDataResponse:
    row = _get_job(session, job_id)
    status = _job_status(row)
    if status in _FAST_POLL_STATUSES:
        response.headers["Retry-After"] = "2"
    elif status in _SLOW_POLL_STATUSES:
        response.headers["Retry-After"] = "5"
    return JobDataResponse(
        data=_job_response(row),
        meta=ResponseMeta(request_id=_request_id()),
    )


@router.post(
    "/{job_id}/cancel",
    operation_id="cancel_job",
    response_model=JobDataResponse,
    responses=_CANCEL_ERROR_RESPONSES,
)
def cancel_job(
    job_id: str,
    payload: CancelJobRequest,
    request: Request,
    session: JobSession,
) -> JobDataResponse:
    factory = _session_factory(request)
    settings = cast(Settings, request.app.state.settings)
    try:
        JobCancellationService(factory, settings.data_directories.temporary).request(
            job_id,
            reason=payload.reason,
        )
    except CancellationJobNotFoundError:
        _raise_job_not_found()
    except JobCannotBeCancelledError:
        _raise_job_state_invalid()

    return JobDataResponse(
        data=_job_response(_get_job(session, job_id)),
        meta=ResponseMeta(request_id=_request_id()),
    )


@router.post(
    "/{job_id}/retry",
    operation_id="retry_job",
    response_model=JobDataResponse,
    responses=_RETRY_ERROR_RESPONSES,
    status_code=status.HTTP_202_ACCEPTED,
)
def retry_job(
    job_id: str,
    payload: RetryJobRequest,
    request: Request,
    session: JobSession,
    idempotency_key: Annotated[
        str,
        Header(alias="Idempotency-Key", min_length=1, max_length=200),
    ],
) -> JobDataResponse:
    try:
        JobRetryService(_session_factory(request)).request(
            job_id,
            idempotency_key=idempotency_key,
            retry_failed_items_only=payload.retry_failed_items_only,
            reason="USER_REQUESTED",
        )
    except RetryJobNotFoundError:
        _raise_job_not_found()
    except JobRetryLimitError:
        _raise_retry_error(
            "JOB_RETRY_LIMIT_REACHED",
            "The job retry limit has been reached.",
        )
    except JobNotRetryableError:
        _raise_retry_error(
            "JOB_STATE_INVALID",
            "The job state does not allow retry.",
        )
    except RetryIdempotencyConflictError:
        _raise_retry_error(
            "IDEMPOTENCY_CONFLICT",
            "The idempotency key belongs to a different retry request.",
        )
    except InvalidJobRetryError as exc:
        raise TransLokaError(
            code="VALIDATION_ERROR",
            message="The request contains invalid values.",
            status_code=422,
        ) from exc

    return JobDataResponse(
        data=_job_response(_get_job(session, job_id)),
        meta=ResponseMeta(request_id=_request_id()),
    )


def _get_job(session: Session, job_id: str) -> ApplicationJob:
    row = session.get(ApplicationJob, job_id)
    if row is None:
        _raise_job_not_found()
    return row


def _job_response(row: ApplicationJob) -> JobResponse:
    return JobResponse(
        id=row.id,
        job_type=_job_type(row),
        status=_job_status(row),
        progress=row.progress,
        current_stage=row.current_stage,
        project_id=row.project_id,
        document_id=row.document_id,
        retry_count=row.retry_count,
        max_retries=row.max_retries,
        created_at=row.created_at,
        started_at=row.started_at,
        completed_at=row.completed_at,
        error=_job_error(row),
    )


def _attempt_response(row: JobAttempt) -> JobAttemptResponse:
    try:
        status = JobAttemptStatus(row.status)
    except ValueError:
        raise RuntimeError("The stored job attempt status is invalid.") from None
    return JobAttemptResponse(
        attempt_number=row.attempt_number,
        status=status,
        started_at=row.started_at,
        completed_at=row.completed_at,
        duration_ms=row.duration_ms,
        error=_attempt_error(row),
    )


def _job_type(row: ApplicationJob) -> JobType:
    try:
        return JobType(row.job_type)
    except ValueError:
        raise RuntimeError("The stored job type is invalid.") from None


def _job_status(row: ApplicationJob) -> JobStatus:
    try:
        return JobStatus(row.status)
    except ValueError:
        raise RuntimeError("The stored job status is invalid.") from None


def _job_error(row: ApplicationJob) -> JobErrorResponse | None:
    if row.error_code is None and row.error_message is None:
        return None
    if row.error_code is None or row.error_message is None:
        raise RuntimeError("The stored job error is invalid.")
    return JobErrorResponse(code=row.error_code, message=row.error_message)


def _attempt_error(row: JobAttempt) -> JobAttemptErrorResponse | None:
    if row.error_code is None and row.error_message is None:
        return None
    if row.error_code is None or row.error_message is None:
        raise RuntimeError("The stored job attempt error is invalid.")
    return JobAttemptErrorResponse(code=row.error_code, message=row.error_message)


def _encode_cursor(row: ApplicationJob) -> str:
    value = f"{row.created_at}\0{row.id}".encode()
    return base64.urlsafe_b64encode(value).decode().rstrip("=")


def _decode_cursor(value: str) -> tuple[str, str]:
    try:
        decoded = base64.b64decode(
            value + "=" * (-len(value) % 4),
            altchars=b"-_",
            validate=True,
        ).decode()
        created_at, job_id = decoded.split("\0", maxsplit=1)
    except (binascii.Error, UnicodeDecodeError, ValueError):
        _raise_invalid_cursor()
    if not created_at or not job_id.startswith("job_"):
        _raise_invalid_cursor()
    return created_at, job_id


def _request_id() -> str:
    request_id = get_request_id()
    if request_id is None:
        raise RuntimeError("The request identifier is unavailable.")
    return request_id


def _session_factory(request: Request) -> sessionmaker[Session]:
    try:
        factory = request.app.state.session_factory
    except AttributeError as exc:
        raise RuntimeError("The job database is not configured.") from exc
    if not callable(factory):
        raise RuntimeError("The job database is not configured.")
    return cast(sessionmaker[Session], factory)


def _raise_job_not_found() -> Never:
    raise TransLokaError(
        code="JOB_NOT_FOUND",
        message="The requested job was not found.",
        status_code=404,
    )


def _raise_invalid_cursor() -> Never:
    raise TransLokaError(
        code="VALIDATION_ERROR",
        message="The request contains invalid values.",
        status_code=422,
    )


def _raise_job_state_invalid() -> Never:
    raise TransLokaError(
        code="JOB_STATE_INVALID",
        message="The job state does not allow cancellation.",
        status_code=409,
    )


def _raise_retry_error(code: str, message: str) -> Never:
    raise TransLokaError(
        code=code,
        message=message,
        status_code=409,
    )
