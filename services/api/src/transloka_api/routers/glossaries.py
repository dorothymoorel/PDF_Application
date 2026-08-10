from collections.abc import Iterator
from typing import Annotated, Any, Never, cast

from fastapi import APIRouter, Depends, Query, Request, Response
from fastapi import status as http_status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session, sessionmaker
from transloka_api.exception_handlers import TransLokaError
from transloka_api.middleware import get_request_id
from transloka_api.schemas import ErrorResponse
from transloka_core.database import transaction_scope
from transloka_core.database.models.glossary import (
    GlossaryMatchMode,
    GlossaryRuleType,
    GlossaryScope,
)
from transloka_glossary import (
    CorruptGlossaryError,
    CreateGlossary,
    CreateTerm,
    DuplicateTermError,
    GlossaryAlreadyExistsError,
    GlossaryNotFoundError,
    GlossaryRecord,
    GlossaryRepository,
    GlossaryRepositoryError,
    GlossaryService,
    GlossaryStatus,
    GlossaryTermStatus,
    InvalidGlossaryIdError,
    InvalidGlossaryStateError,
    InvalidGlossaryValueError,
    InvalidTermIdError,
    InvalidTermStateError,
    RevisionConflictError,
    TargetRequiredError,
    TermNotFoundError,
    TermRecord,
    UpdateGlossary,
    UpdateTerm,
)

_ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    403: {
        "description": "The request was rejected by the local security policy.",
        "model": ErrorResponse,
    },
    404: {"description": "The glossary resource was not found.", "model": ErrorResponse},
    409: {
        "description": "The glossary operation conflicts with current state.",
        "model": ErrorResponse,
    },
    422: {"description": "The request contains invalid glossary values.", "model": ErrorResponse},
    500: {"description": "Stored glossary data is invalid.", "model": ErrorResponse},
}

router = APIRouter(tags=["Glossaries"])


class _RequestModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CreateGlossaryRequest(_RequestModel):
    project_id: str | None = None
    name: str = Field(min_length=1)
    description: str | None = None
    source_language: str = Field(min_length=1)
    target_language: str = Field(min_length=1)
    scope: GlossaryScope
    domain: str | None = None
    is_default: bool = False


class UpdateGlossaryRequest(_RequestModel):
    name: str | None = Field(default=None, min_length=1)
    description: str | None = None
    expected_version: int = Field(ge=1)


class CreateTermRequest(_RequestModel):
    source_term: str = Field(min_length=1)
    rule_type: GlossaryRuleType
    target_term: str | None = None
    scope: GlossaryScope
    scope_reference_id: str | None = None
    priority: int = Field(default=100, ge=0)
    case_sensitive: bool = False
    whole_word: bool = True
    match_mode: GlossaryMatchMode = GlossaryMatchMode.PHRASE
    capitalization_policy: str = Field(default="MATCH_SENTENCE_POSITION", min_length=1)
    inflection_policy: str = Field(default="USE_BASE_TERM", min_length=1)
    first_use_policy: str = Field(default="NONE", min_length=1)
    confidence: float | None = Field(default=1.0, ge=0.0, le=1.0)
    notes: str | None = None


class UpdateTermRequest(_RequestModel):
    source_term: str | None = Field(default=None, min_length=1)
    rule_type: GlossaryRuleType | None = None
    target_term: str | None = None
    scope: GlossaryScope | None = None
    scope_reference_id: str | None = None
    priority: int | None = Field(default=None, ge=0)
    case_sensitive: bool | None = None
    whole_word: bool | None = None
    match_mode: GlossaryMatchMode | None = None
    capitalization_policy: str | None = Field(default=None, min_length=1)
    inflection_policy: str | None = Field(default=None, min_length=1)
    first_use_policy: str | None = Field(default=None, min_length=1)
    confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    notes: str | None = None
    expected_revision: int = Field(ge=1)
    reason: str | None = None


class ResponseMeta(BaseModel):
    request_id: str


class OffsetPagination(BaseModel):
    limit: int
    offset: int
    total: int
    has_more: bool


class CollectionMeta(ResponseMeta):
    pagination: OffsetPagination


class GlossaryResponse(BaseModel):
    id: str
    project_id: str | None
    name: str
    description: str | None
    source_language: str
    target_language: str
    scope: GlossaryScope
    domain: str | None
    status: GlossaryStatus
    version: int
    is_default: bool
    term_count: int
    created_at: str
    updated_at: str


class GlossaryDataResponse(BaseModel):
    data: GlossaryResponse
    meta: ResponseMeta


class GlossaryListResponse(BaseModel):
    data: list[GlossaryResponse]
    meta: CollectionMeta


class TermResponse(BaseModel):
    id: str
    glossary_id: str
    source_term: str
    normalized_source_term: str
    rule_type: GlossaryRuleType
    target_term: str | None
    scope: GlossaryScope
    scope_reference_id: str | None
    priority: int
    case_sensitive: bool
    whole_word: bool
    match_mode: GlossaryMatchMode
    capitalization_policy: str
    inflection_policy: str
    first_use_policy: str
    status: GlossaryTermStatus
    term_source: str
    confidence: float | None
    notes: str | None
    current_revision: int
    occurrence_count: int
    created_at: str
    updated_at: str


class TermDataResponse(BaseModel):
    data: TermResponse
    meta: ResponseMeta


class TermListResponse(BaseModel):
    data: list[TermResponse]
    meta: CollectionMeta


def get_glossary_session(request: Request) -> Iterator[Session]:
    try:
        factory = request.app.state.session_factory
    except AttributeError as exc:
        raise RuntimeError("The glossary database is not configured.") from exc
    if not callable(factory):
        raise RuntimeError("The glossary database is not configured.")
    with transaction_scope(cast(sessionmaker[Session], factory)) as session:
        yield session


GlossarySession = Annotated[Session, Depends(get_glossary_session)]


@router.post(
    "/api/v1/glossaries",
    operation_id="create_glossary",
    response_model=GlossaryDataResponse,
    responses=_ERROR_RESPONSES,
    status_code=http_status.HTTP_201_CREATED,
)
def create_glossary(
    payload: CreateGlossaryRequest,
    session: GlossarySession,
) -> GlossaryDataResponse:
    try:
        record = _service(session).create_glossary(
            CreateGlossary(
                project_id=payload.project_id,
                name=payload.name,
                description=payload.description,
                source_language=payload.source_language,
                target_language=payload.target_language,
                scope=payload.scope,
                domain=payload.domain,
                is_default=payload.is_default,
            )
        )
    except GlossaryRepositoryError as exc:
        _raise_glossary_error(exc)
    return _glossary_data_response(record)


@router.get(
    "/api/v1/glossaries",
    operation_id="list_glossaries",
    response_model=GlossaryListResponse,
    responses=_ERROR_RESPONSES,
)
def list_glossaries(
    session: GlossarySession,
    project_id: str | None = None,
    scope: GlossaryScope | None = None,
    glossary_status: Annotated[GlossaryStatus | None, Query(alias="status")] = None,
    search: Annotated[str | None, Query(min_length=1)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> GlossaryListResponse:
    try:
        records = _service(session).list_glossaries(
            project_id=project_id,
            scope=scope,
            status=glossary_status,
            search=search,
        )
    except GlossaryRepositoryError as exc:
        _raise_glossary_error(exc)
    total = len(records)
    page = records[offset : offset + limit]
    return GlossaryListResponse(
        data=[_glossary_response(record) for record in page],
        meta=_collection_meta(limit, offset, total, len(page)),
    )


@router.get(
    "/api/v1/glossaries/{glossary_id}",
    operation_id="get_glossary",
    response_model=GlossaryDataResponse,
    responses=_ERROR_RESPONSES,
)
def get_glossary(glossary_id: str, session: GlossarySession) -> GlossaryDataResponse:
    try:
        record = _service(session).get_glossary(glossary_id)
    except GlossaryRepositoryError as exc:
        _raise_glossary_error(exc)
    return _glossary_data_response(record)


@router.patch(
    "/api/v1/glossaries/{glossary_id}",
    operation_id="update_glossary",
    response_model=GlossaryDataResponse,
    responses=_ERROR_RESPONSES,
)
def update_glossary(
    glossary_id: str,
    payload: UpdateGlossaryRequest,
    session: GlossarySession,
) -> GlossaryDataResponse:
    values = payload.model_dump(
        mode="python",
        exclude_unset=True,
        exclude={"expected_version"},
    )
    if "name" in values and values["name"] is None:
        _raise_validation_error()
    try:
        record = _service(session).update_glossary(
            glossary_id,
            UpdateGlossary(expected_version=payload.expected_version, values=values),
        )
    except GlossaryRepositoryError as exc:
        _raise_glossary_error(exc)
    return _glossary_data_response(record)


@router.post(
    "/api/v1/glossaries/{glossary_id}/deactivate",
    operation_id="deactivate_glossary",
    response_model=GlossaryDataResponse,
    responses=_ERROR_RESPONSES,
)
def deactivate_glossary(glossary_id: str, session: GlossarySession) -> GlossaryDataResponse:
    try:
        record = _service(session).deactivate_glossary(glossary_id)
    except GlossaryRepositoryError as exc:
        _raise_glossary_error(exc)
    return _glossary_data_response(record)


@router.post(
    "/api/v1/glossaries/{glossary_id}/activate",
    operation_id="activate_glossary",
    response_model=GlossaryDataResponse,
    responses=_ERROR_RESPONSES,
)
def activate_glossary(glossary_id: str, session: GlossarySession) -> GlossaryDataResponse:
    try:
        record = _service(session).activate_glossary(glossary_id)
    except GlossaryRepositoryError as exc:
        _raise_glossary_error(exc)
    return _glossary_data_response(record)


@router.delete(
    "/api/v1/glossaries/{glossary_id}",
    operation_id="delete_glossary",
    responses=_ERROR_RESPONSES,
    status_code=http_status.HTTP_204_NO_CONTENT,
)
def delete_glossary(glossary_id: str, session: GlossarySession) -> Response:
    try:
        _service(session).delete_glossary(glossary_id)
    except GlossaryRepositoryError as exc:
        _raise_glossary_error(exc)
    return Response(status_code=http_status.HTTP_204_NO_CONTENT)


@router.post(
    "/api/v1/glossaries/{glossary_id}/terms",
    operation_id="create_glossary_term",
    response_model=TermDataResponse,
    responses=_ERROR_RESPONSES,
    status_code=http_status.HTTP_201_CREATED,
)
def create_glossary_term(
    glossary_id: str,
    payload: CreateTermRequest,
    session: GlossarySession,
) -> TermDataResponse:
    try:
        record = _service(session).create_term(
            glossary_id,
            CreateTerm(
                source_term=payload.source_term,
                rule_type=payload.rule_type,
                target_term=payload.target_term,
                scope=payload.scope,
                scope_reference_id=payload.scope_reference_id,
                priority=payload.priority,
                case_sensitive=payload.case_sensitive,
                whole_word=payload.whole_word,
                match_mode=payload.match_mode,
                capitalization_policy=payload.capitalization_policy,
                inflection_policy=payload.inflection_policy,
                first_use_policy=payload.first_use_policy,
                confidence=payload.confidence,
                notes=payload.notes,
            ),
        )
    except GlossaryRepositoryError as exc:
        _raise_glossary_error(exc)
    return _term_data_response(record)


@router.get(
    "/api/v1/glossaries/{glossary_id}/terms",
    operation_id="list_glossary_terms",
    response_model=TermListResponse,
    responses=_ERROR_RESPONSES,
)
def list_glossary_terms(
    glossary_id: str,
    session: GlossarySession,
    search: Annotated[str | None, Query(min_length=1)] = None,
    rule_type: GlossaryRuleType | None = None,
    term_status: Annotated[GlossaryTermStatus | None, Query(alias="status")] = None,
    source: Annotated[str | None, Query(min_length=1)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> TermListResponse:
    try:
        records = _service(session).list_terms(
            glossary_id,
            search=search,
            rule_type=rule_type,
            status=term_status,
            source=source,
        )
    except GlossaryRepositoryError as exc:
        _raise_glossary_error(exc)
    total = len(records)
    page = records[offset : offset + limit]
    return TermListResponse(
        data=[_term_response(record) for record in page],
        meta=_collection_meta(limit, offset, total, len(page)),
    )


@router.get(
    "/api/v1/glossary-terms/{term_id}",
    operation_id="get_glossary_term",
    response_model=TermDataResponse,
    responses=_ERROR_RESPONSES,
)
def get_glossary_term(term_id: str, session: GlossarySession) -> TermDataResponse:
    try:
        record = _service(session).get_term(term_id)
    except GlossaryRepositoryError as exc:
        _raise_glossary_error(exc)
    return _term_data_response(record)


@router.patch(
    "/api/v1/glossary-terms/{term_id}",
    operation_id="update_glossary_term",
    response_model=TermDataResponse,
    responses=_ERROR_RESPONSES,
)
def update_glossary_term(
    term_id: str,
    payload: UpdateTermRequest,
    session: GlossarySession,
) -> TermDataResponse:
    values = payload.model_dump(
        mode="python",
        exclude_unset=True,
        exclude={"expected_revision", "reason"},
    )
    non_nullable = {
        "source_term",
        "rule_type",
        "scope",
        "priority",
        "case_sensitive",
        "whole_word",
        "match_mode",
        "capitalization_policy",
        "inflection_policy",
        "first_use_policy",
    }
    if any(values.get(field) is None for field in non_nullable & values.keys()):
        _raise_validation_error()
    try:
        record = _service(session).update_term(
            term_id,
            UpdateTerm(
                expected_revision=payload.expected_revision,
                values=values,
                reason=payload.reason,
            ),
        )
    except GlossaryRepositoryError as exc:
        _raise_glossary_error(exc)
    return _term_data_response(record)


@router.post(
    "/api/v1/glossary-terms/{term_id}/deactivate",
    operation_id="deactivate_glossary_term",
    response_model=TermDataResponse,
    responses=_ERROR_RESPONSES,
)
def deactivate_glossary_term(term_id: str, session: GlossarySession) -> TermDataResponse:
    try:
        record = _service(session).deactivate_term(term_id)
    except GlossaryRepositoryError as exc:
        _raise_glossary_error(exc)
    return _term_data_response(record)


@router.delete(
    "/api/v1/glossary-terms/{term_id}",
    operation_id="archive_glossary_term",
    response_model=TermDataResponse,
    responses=_ERROR_RESPONSES,
)
def archive_glossary_term(term_id: str, session: GlossarySession) -> TermDataResponse:
    try:
        record = _service(session).archive_term(term_id)
    except GlossaryRepositoryError as exc:
        _raise_glossary_error(exc)
    return _term_data_response(record)


def _service(session: Session) -> GlossaryService:
    return GlossaryService(GlossaryRepository(session))


def _glossary_response(record: GlossaryRecord) -> GlossaryResponse:
    return GlossaryResponse(
        id=record.id,
        project_id=record.project_id,
        name=record.name,
        description=record.description,
        source_language=record.source_language,
        target_language=record.target_language,
        scope=record.scope,
        domain=record.domain,
        status=record.status,
        version=record.version,
        is_default=record.is_default,
        term_count=record.term_count,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def _term_response(record: TermRecord) -> TermResponse:
    return TermResponse(
        id=record.id,
        glossary_id=record.glossary_id,
        source_term=record.source_term,
        normalized_source_term=record.normalized_source_term,
        rule_type=record.rule_type,
        target_term=record.target_term,
        scope=record.scope,
        scope_reference_id=record.scope_reference_id,
        priority=record.priority,
        case_sensitive=record.case_sensitive,
        whole_word=record.whole_word,
        match_mode=record.match_mode,
        capitalization_policy=record.capitalization_policy,
        inflection_policy=record.inflection_policy,
        first_use_policy=record.first_use_policy,
        status=record.status,
        term_source=record.term_source,
        confidence=record.confidence,
        notes=record.notes,
        current_revision=record.current_revision,
        occurrence_count=record.occurrence_count,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def _glossary_data_response(record: GlossaryRecord) -> GlossaryDataResponse:
    return GlossaryDataResponse(
        data=_glossary_response(record),
        meta=ResponseMeta(request_id=_request_id()),
    )


def _term_data_response(record: TermRecord) -> TermDataResponse:
    return TermDataResponse(
        data=_term_response(record),
        meta=ResponseMeta(request_id=_request_id()),
    )


def _collection_meta(limit: int, offset: int, total: int, page_size: int) -> CollectionMeta:
    return CollectionMeta(
        request_id=_request_id(),
        pagination=OffsetPagination(
            limit=limit,
            offset=offset,
            total=total,
            has_more=offset + page_size < total,
        ),
    )


def _request_id() -> str:
    request_id = get_request_id()
    if request_id is None:
        raise RuntimeError("The request identifier is unavailable.")
    return request_id


def _raise_validation_error() -> Never:
    raise TransLokaError(
        code="VALIDATION_ERROR",
        message="The request contains invalid values.",
        status_code=422,
    )


def _raise_glossary_error(exc: GlossaryRepositoryError) -> Never:
    details: dict[str, object] = {}
    if isinstance(exc, GlossaryNotFoundError | InvalidGlossaryIdError):
        code, message, status_code = (
            "GLOSSARY_NOT_FOUND",
            "The requested glossary was not found.",
            404,
        )
    elif isinstance(exc, TermNotFoundError | InvalidTermIdError):
        code, message, status_code = (
            "TERM_NOT_FOUND",
            "The requested glossary term was not found.",
            404,
        )
    elif isinstance(exc, DuplicateTermError):
        code, message, status_code = (
            "DUPLICATE_TERM",
            "An active term with the same identity already exists.",
            409,
        )
    elif isinstance(exc, GlossaryAlreadyExistsError):
        code, message, status_code = (
            "GLOSSARY_CONFLICT",
            "A glossary with the same identity already exists.",
            409,
        )
    elif isinstance(exc, RevisionConflictError):
        code, message, status_code = (
            "REVISION_CONFLICT",
            "The resource was changed after it was loaded.",
            409,
        )
        details = {
            "expected_revision": exc.expected_revision,
            "current_revision": exc.current_revision,
        }
    elif isinstance(exc, InvalidGlossaryStateError | InvalidTermStateError):
        code, message, status_code = (
            "GLOSSARY_STATE_INVALID",
            "The glossary resource state does not allow this operation.",
            409,
        )
    elif isinstance(exc, TargetRequiredError):
        code, message, status_code = (
            "TARGET_REQUIRED",
            "The selected glossary rule requires a target term.",
            422,
        )
    elif isinstance(exc, InvalidGlossaryValueError):
        code, message, status_code = (
            "VALIDATION_ERROR",
            "The request contains invalid values.",
            422,
        )
    elif isinstance(exc, CorruptGlossaryError):
        code, message, status_code = (
            "INTERNAL_ERROR",
            "An internal server error occurred.",
            500,
        )
    else:
        code, message, status_code = (
            "GLOSSARY_OPERATION_FAILED",
            "The glossary operation could not be completed.",
            409,
        )
    raise TransLokaError(
        code=code,
        message=message,
        status_code=status_code,
        details=details,
    ) from exc
