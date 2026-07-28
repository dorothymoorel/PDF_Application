from collections.abc import Iterator
from typing import Annotated, Any, Never, cast

from fastapi import APIRouter, Depends, Query, Request, status
from sqlalchemy.orm import Session, sessionmaker
from transloka_api.exception_handlers import TransLokaError
from transloka_api.middleware import get_request_id
from transloka_api.schemas import ErrorResponse
from transloka_api.schemas.projects import (
    CollectionMeta,
    CreateProjectRequest,
    OffsetPagination,
    ProjectDataResponse,
    ProjectListResponse,
    ProjectResponse,
    ProjectSortField,
    ResponseMeta,
    SortOrder,
    UpdateProjectRequest,
)
from transloka_api.services.projects import CreateProject, ProjectService, UpdateProject
from transloka_core.database import transaction_scope
from transloka_core.database.models.projects import ProjectStatus
from transloka_core.repositories.projects import (
    CorruptProjectError,
    InvalidProjectIdError,
    InvalidProjectStateError,
    InvalidProjectValueError,
    ProjectAlreadyExistsError,
    ProjectNotFoundError,
    ProjectRecord,
    ProjectRepositoryError,
    ProjectsRepository,
)

_ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    403: {
        "description": "The request was rejected by the local security policy.",
        "model": ErrorResponse,
    },
    404: {"description": "The project was not found.", "model": ErrorResponse},
    409: {
        "description": "The project state does not allow this operation.",
        "model": ErrorResponse,
    },
    422: {"description": "The request contains invalid values.", "model": ErrorResponse},
    500: {"description": "An unexpected server error was normalized.", "model": ErrorResponse},
}

router = APIRouter(prefix="/api/v1/projects", tags=["Projects"])


def get_project_session(request: Request) -> Iterator[Session]:
    try:
        factory = request.app.state.session_factory
    except AttributeError as exc:
        raise RuntimeError("The project database is not configured.") from exc
    if not callable(factory):
        raise RuntimeError("The project database is not configured.")
    with transaction_scope(cast(sessionmaker[Session], factory)) as session:
        yield session


ProjectSession = Annotated[Session, Depends(get_project_session)]


@router.post(
    "",
    operation_id="create_project",
    response_model=ProjectDataResponse,
    responses=_ERROR_RESPONSES,
    status_code=status.HTTP_201_CREATED,
)
def create_project(payload: CreateProjectRequest, session: ProjectSession) -> ProjectDataResponse:
    try:
        record = ProjectService(ProjectsRepository(session)).create(
            CreateProject(
                name=payload.name,
                description=payload.description,
                source_language=payload.source_language,
                target_language=payload.target_language,
                document_type=payload.document_type,
                translation_style=payload.translation_style,
                reconstruction_mode=payload.reconstruction_mode,
            )
        )
    except ProjectRepositoryError as exc:
        _raise_project_error(exc)
    return _data_response(record)


@router.get(
    "",
    operation_id="list_projects",
    response_model=ProjectListResponse,
    responses=_ERROR_RESPONSES,
)
def list_projects(
    session: ProjectSession,
    project_status: Annotated[ProjectStatus | None, Query(alias="status")] = None,
    search: Annotated[str | None, Query(min_length=1)] = None,
    sort: ProjectSortField = "updated_at",
    order: SortOrder = "desc",
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> ProjectListResponse:
    try:
        records = ProjectService(ProjectsRepository(session)).list(project_status)
    except ProjectRepositoryError as exc:
        _raise_project_error(exc)

    if search is not None:
        candidate = search.casefold()
        records = [
            record
            for record in records
            if candidate in record.name.casefold()
            or (record.description is not None and candidate in record.description.casefold())
        ]
    records.sort(key=lambda record: record.id)
    records.sort(
        key=lambda record: _sort_value(record, sort),
        reverse=order == "desc",
    )
    total = len(records)
    page = records[offset : offset + limit]
    return ProjectListResponse(
        data=[_project_response(record) for record in page],
        meta=CollectionMeta(
            request_id=_request_id(),
            pagination=OffsetPagination(
                limit=limit,
                offset=offset,
                total=total,
                has_more=offset + len(page) < total,
            ),
        ),
    )


@router.get(
    "/{project_id}",
    operation_id="get_project",
    response_model=ProjectDataResponse,
    responses=_ERROR_RESPONSES,
)
def get_project(project_id: str, session: ProjectSession) -> ProjectDataResponse:
    try:
        record = ProjectService(ProjectsRepository(session)).get(project_id)
    except ProjectRepositoryError as exc:
        _raise_project_error(exc)
    return _data_response(record)


@router.patch(
    "/{project_id}",
    operation_id="update_project",
    response_model=ProjectDataResponse,
    responses=_ERROR_RESPONSES,
)
def update_project(
    project_id: str,
    payload: UpdateProjectRequest,
    session: ProjectSession,
) -> ProjectDataResponse:
    if not payload.model_fields_set or any(
        getattr(payload, field) is None for field in payload.model_fields_set
    ):
        _raise_validation_error()
    try:
        record = ProjectService(ProjectsRepository(session)).update(
            project_id,
            UpdateProject(
                name=payload.name,
                translation_style=payload.translation_style,
                reconstruction_mode=payload.reconstruction_mode,
            ),
        )
    except ProjectRepositoryError as exc:
        _raise_project_error(exc, invalid_state_code="PROJECT_ARCHIVED")
    return _data_response(record)


@router.post(
    "/{project_id}/archive",
    operation_id="archive_project",
    response_model=ProjectDataResponse,
    responses=_ERROR_RESPONSES,
)
def archive_project(project_id: str, session: ProjectSession) -> ProjectDataResponse:
    try:
        record = ProjectService(ProjectsRepository(session)).archive(project_id)
    except ProjectRepositoryError as exc:
        _raise_project_error(exc, invalid_state_code="PROJECT_ARCHIVED")
    return _data_response(record)


@router.post(
    "/{project_id}/unarchive",
    operation_id="unarchive_project",
    response_model=ProjectDataResponse,
    responses=_ERROR_RESPONSES,
)
def unarchive_project(project_id: str, session: ProjectSession) -> ProjectDataResponse:
    try:
        record = ProjectService(ProjectsRepository(session)).unarchive(project_id)
    except ProjectRepositoryError as exc:
        _raise_project_error(exc)
    return _data_response(record)


def _project_response(record: ProjectRecord) -> ProjectResponse:
    return ProjectResponse(
        id=record.id,
        name=record.name,
        description=record.description,
        status=record.status,
        source_language=record.source_language,
        target_language=record.target_language,
        document_type=record.document_type,
        translation_style=record.translation_style,
        reconstruction_mode=record.reconstruction_mode,
        progress=record.progress,
        active_document_id=record.active_document_id,
        settings=record.settings,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def _data_response(record: ProjectRecord) -> ProjectDataResponse:
    return ProjectDataResponse(
        data=_project_response(record),
        meta=ResponseMeta(request_id=_request_id()),
    )


def _request_id() -> str:
    request_id = get_request_id()
    if request_id is None:
        raise RuntimeError("The request identifier is unavailable.")
    return request_id


def _sort_value(record: ProjectRecord, field: ProjectSortField) -> str | float:
    if field == "name":
        return record.name.casefold()
    if field == "status":
        return record.status.value
    if field == "progress":
        return record.progress
    return record.updated_at


def _raise_validation_error() -> Never:
    raise TransLokaError(
        code="VALIDATION_ERROR",
        message="The request contains invalid values.",
        status_code=422,
    )


def _raise_project_error(
    exc: ProjectRepositoryError,
    *,
    invalid_state_code: str = "PROJECT_STATE_INVALID",
) -> Never:
    if isinstance(exc, (InvalidProjectIdError, ProjectNotFoundError)):
        code, message, status_code = (
            "PROJECT_NOT_FOUND",
            "The requested project was not found.",
            404,
        )
    elif isinstance(exc, InvalidProjectStateError):
        code, message, status_code = (
            invalid_state_code,
            "The project state does not allow this operation.",
            409,
        )
    elif isinstance(exc, InvalidProjectValueError):
        code, message, status_code = (
            "VALIDATION_ERROR",
            "The request contains invalid values.",
            422,
        )
    elif isinstance(exc, ProjectAlreadyExistsError):
        code, message, status_code = (
            "PROJECT_STATE_INVALID",
            "The project state does not allow this operation.",
            409,
        )
    elif isinstance(exc, CorruptProjectError):
        code, message, status_code = (
            "INTERNAL_ERROR",
            "An internal server error occurred.",
            500,
        )
    else:
        code, message, status_code = (
            "INTERNAL_ERROR",
            "An internal server error occurred.",
            500,
        )
    raise TransLokaError(code=code, message=message, status_code=status_code) from exc
