from collections.abc import Iterator
from typing import Annotated, Any, Literal, Never, cast

from fastapi import APIRouter, Depends, Query, Request, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session, sessionmaker
from transloka_api.exception_handlers import TransLokaError
from transloka_api.middleware import get_request_id
from transloka_api.schemas import ErrorResponse
from transloka_api.schemas.projects import ResponseMeta
from transloka_core.database import transaction_scope
from transloka_core.database.models.projects import Project
from transloka_core.database.models.warnings import (
    WarningResolutionType,
    WarningSeverity,
    WarningStatus,
    WarningType,
)
from transloka_core.repositories.warnings import (
    CriticalWarningPolicyError,
    InvalidWarningError,
    WarningAlreadyResolvedError,
    WarningNotFoundError,
    WarningRecord,
    WarningsRepository,
)

_ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    403: {
        "description": "The warning resolution is blocked by the quality policy.",
        "model": ErrorResponse,
    },
    404: {"description": "The project or warning was not found.", "model": ErrorResponse},
    409: {"description": "The warning has already been resolved.", "model": ErrorResponse},
    422: {"description": "The request contains invalid values.", "model": ErrorResponse},
    500: {"description": "An unexpected server error was normalized.", "model": ErrorResponse},
}

router = APIRouter(tags=["Warnings"])


class WarningResponse(BaseModel):
    id: str
    project_id: str
    document_id: str | None
    page_id: str | None
    segment_id: str | None
    warning_type: WarningType
    severity: WarningSeverity
    message: str
    details: dict[str, Any]
    status: WarningStatus
    resolution_type: WarningResolutionType | None
    resolution_note: str | None
    created_at: str
    resolved_at: str | None


class WarningPagination(BaseModel):
    limit: int
    next_cursor: str | None
    has_more: bool


class WarningListMeta(ResponseMeta):
    pagination: WarningPagination


class WarningListResponse(BaseModel):
    data: list[WarningResponse]
    meta: WarningListMeta


class WarningDataResponse(BaseModel):
    data: WarningResponse
    meta: ResponseMeta


class ResolveWarningRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    resolution_type: Literal["USER_FIXED"]
    resolution_note: str | None = Field(default=None, max_length=2000)


class WarningNoteRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    resolution_note: str | None = Field(default=None, max_length=2000)


def get_warning_session(request: Request) -> Iterator[Session]:
    try:
        factory = request.app.state.session_factory
    except AttributeError as exc:
        raise RuntimeError("The warning database is not configured.") from exc
    if not callable(factory):
        raise RuntimeError("The warning database is not configured.")
    with transaction_scope(cast(sessionmaker[Session], factory)) as session:
        yield session


WarningSession = Annotated[Session, Depends(get_warning_session)]


@router.get(
    "/api/v1/projects/{project_id}/warnings",
    operation_id="list_warnings",
    response_model=WarningListResponse,
    responses=_ERROR_RESPONSES,
)
def list_warnings(
    project_id: str,
    session: WarningSession,
    warning_status: Annotated[WarningStatus | None, Query(alias="status")] = None,
    severity: WarningSeverity | None = None,
    warning_type: WarningType | None = None,
    page_id: Annotated[str | None, Query(min_length=1)] = None,
    segment_id: Annotated[str | None, Query(min_length=1)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    cursor: Annotated[str | None, Query(min_length=1)] = None,
) -> WarningListResponse:
    _get_project(session, project_id)
    offset = _cursor_offset(cursor)
    repository = WarningsRepository(session)
    try:
        records, has_more = repository.list(
            project_id=project_id,
            status=warning_status,
            severity=severity,
            warning_type=warning_type,
            page_id=page_id,
            segment_id=segment_id,
            offset=offset,
            limit=limit,
        )
    except InvalidWarningError as exc:
        _raise_validation_error(str(exc))
    next_cursor = str(offset + len(records)) if has_more else None
    return WarningListResponse(
        data=[_warning_response(record) for record in records],
        meta=WarningListMeta(
            request_id=_request_id(),
            pagination=WarningPagination(
                limit=limit,
                next_cursor=next_cursor,
                has_more=has_more,
            ),
        ),
    )


@router.get(
    "/api/v1/warnings/{warning_id}",
    operation_id="get_warning",
    response_model=WarningDataResponse,
    responses=_ERROR_RESPONSES,
)
def get_warning(warning_id: str, session: WarningSession) -> WarningDataResponse:
    try:
        record = WarningsRepository(session).get(warning_id)
    except WarningNotFoundError:
        _raise_warning_not_found()
    return WarningDataResponse(
        data=_warning_response(record),
        meta=ResponseMeta(request_id=_request_id()),
    )


@router.post(
    "/api/v1/warnings/{warning_id}/resolve",
    operation_id="resolve_warning",
    response_model=WarningDataResponse,
    responses=_ERROR_RESPONSES,
)
def resolve_warning(
    warning_id: str,
    payload: ResolveWarningRequest,
    session: WarningSession,
) -> WarningDataResponse:
    return _mutate_warning(
        session,
        warning_id,
        lambda repository: repository.resolve(warning_id, note=payload.resolution_note),
    )


@router.post(
    "/api/v1/warnings/{warning_id}/accept",
    operation_id="accept_warning",
    response_model=WarningDataResponse,
    responses=_ERROR_RESPONSES,
)
def accept_warning(
    warning_id: str,
    payload: WarningNoteRequest,
    session: WarningSession,
) -> WarningDataResponse:
    return _mutate_warning(
        session,
        warning_id,
        lambda repository: repository.accept(warning_id, note=payload.resolution_note),
    )


@router.post(
    "/api/v1/warnings/{warning_id}/false-positive",
    operation_id="mark_warning_false_positive",
    response_model=WarningDataResponse,
    responses=_ERROR_RESPONSES,
)
def mark_warning_false_positive(
    warning_id: str,
    payload: WarningNoteRequest,
    session: WarningSession,
) -> WarningDataResponse:
    return _mutate_warning(
        session,
        warning_id,
        lambda repository: repository.false_positive(warning_id, note=payload.resolution_note),
    )


def _mutate_warning(
    session: Session,
    warning_id: str,
    mutation: Any,
) -> WarningDataResponse:
    try:
        record = mutation(WarningsRepository(session))
    except WarningNotFoundError:
        _raise_warning_not_found()
    except WarningAlreadyResolvedError as exc:
        _raise_conflict(str(exc))
    except CriticalWarningPolicyError as exc:
        _raise_policy_blocked(str(exc))
    except InvalidWarningError as exc:
        _raise_validation_error(str(exc))
    return WarningDataResponse(
        data=_warning_response(record),
        meta=ResponseMeta(request_id=_request_id()),
    )


def _warning_response(record: WarningRecord) -> WarningResponse:
    return WarningResponse(
        id=record.id,
        project_id=record.project_id,
        document_id=record.document_id,
        page_id=record.page_id,
        segment_id=record.segment_id,
        warning_type=record.warning_type,
        severity=record.severity,
        message=record.message,
        details=record.details,
        status=record.status,
        resolution_type=record.resolution_type,
        resolution_note=record.resolution_note,
        created_at=record.created_at,
        resolved_at=record.resolved_at,
    )


def _get_project(session: Session, project_id: str) -> Project:
    project = session.get(Project, project_id)
    if project is None:
        _raise_project_not_found()
    return project


def _cursor_offset(cursor: str | None) -> int:
    if cursor is None:
        return 0
    if not cursor.isdecimal():
        _raise_validation_error("The warning cursor is invalid.")
    return int(cursor)


def _request_id() -> str:
    request_id = get_request_id()
    if request_id is None:
        raise RuntimeError("The request identifier is unavailable.")
    return request_id


def _raise_project_not_found() -> Never:
    raise TransLokaError(
        code="PROJECT_NOT_FOUND",
        message="The requested project was not found.",
        status_code=status.HTTP_404_NOT_FOUND,
    )


def _raise_warning_not_found() -> Never:
    raise TransLokaError(
        code="WARNING_NOT_FOUND",
        message="The requested warning was not found.",
        status_code=status.HTTP_404_NOT_FOUND,
    )


def _raise_conflict(message: str) -> Never:
    raise TransLokaError(
        code="WARNING_ALREADY_RESOLVED",
        message=message,
        status_code=status.HTTP_409_CONFLICT,
    )


def _raise_policy_blocked(message: str) -> Never:
    raise TransLokaError(
        code="WARNING_POLICY_BLOCKED",
        message=message,
        status_code=status.HTTP_403_FORBIDDEN,
    )


def _raise_validation_error(message: str = "The request contains invalid values.") -> Never:
    raise TransLokaError(
        code="VALIDATION_ERROR",
        message=message,
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
    )
