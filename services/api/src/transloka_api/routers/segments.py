from collections.abc import Iterator
from typing import Annotated, Any, Never, cast

from fastapi import APIRouter, Depends, Request, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session, sessionmaker
from transloka_api.exception_handlers import TransLokaError
from transloka_api.middleware import get_request_id
from transloka_api.routers.pages import _segment_response
from transloka_api.schemas import ErrorResponse
from transloka_api.schemas.pages import PageEditorSegmentResponse
from transloka_api.schemas.projects import ResponseMeta
from transloka_api.services.segments import (
    EditSegmentTranslation,
    EmptySegmentTranslationError,
    SegmentLockedError,
    SegmentNotFoundError,
    SegmentRevisionConflictError,
    SegmentService,
    SegmentServiceError,
)
from transloka_core.database import transaction_scope

_ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    403: {
        "description": "The request was rejected by the local security policy.",
        "model": ErrorResponse,
    },
    404: {"description": "The segment was not found.", "model": ErrorResponse},
    409: {"description": "The segment revision is stale.", "model": ErrorResponse},
    422: {"description": "The request contains invalid values.", "model": ErrorResponse},
    423: {"description": "The segment is locked.", "model": ErrorResponse},
    500: {"description": "An unexpected server error was normalized.", "model": ErrorResponse},
}

router = APIRouter(prefix="/api/v1/segments", tags=["Segments"])


class EditSegmentTranslationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    reviewed_translation: str = Field(min_length=1)
    expected_revision: int = Field(ge=0)
    reason: str | None = Field(default=None, max_length=500)


class SegmentDataResponse(BaseModel):
    data: PageEditorSegmentResponse
    meta: ResponseMeta


def get_segment_session(request: Request) -> Iterator[Session]:
    try:
        factory = request.app.state.session_factory
    except AttributeError as exc:
        raise RuntimeError("The segment database is not configured.") from exc
    if not callable(factory):
        raise RuntimeError("The segment database is not configured.")
    with transaction_scope(cast(sessionmaker[Session], factory)) as session:
        yield session


SegmentSession = Annotated[Session, Depends(get_segment_session)]


@router.patch(
    "/{segment_id}/translation",
    operation_id="edit_segment_translation",
    response_model=SegmentDataResponse,
    responses=_ERROR_RESPONSES,
)
def edit_segment_translation(
    segment_id: str,
    payload: EditSegmentTranslationRequest,
    session: SegmentSession,
) -> SegmentDataResponse:
    try:
        row = SegmentService(session).edit_translation(
            segment_id,
            EditSegmentTranslation(
                reviewed_translation=payload.reviewed_translation,
                expected_revision=payload.expected_revision,
                reason=payload.reason,
            ),
        )
    except SegmentServiceError as exc:
        _raise_segment_error(exc)
    return SegmentDataResponse(
        data=_segment_response(row),
        meta=ResponseMeta(request_id=_request_id()),
    )


def _request_id() -> str:
    request_id = get_request_id()
    if request_id is None:
        raise RuntimeError("The request identifier is unavailable.")
    return request_id


def _raise_segment_error(exc: SegmentServiceError) -> Never:
    if isinstance(exc, SegmentNotFoundError):
        raise TransLokaError(
            code="SEGMENT_NOT_FOUND",
            message="The requested segment was not found.",
            status_code=status.HTTP_404_NOT_FOUND,
        ) from exc
    if isinstance(exc, SegmentLockedError):
        raise TransLokaError(
            code="SEGMENT_LOCKED",
            message="The segment is locked and cannot be edited.",
            status_code=status.HTTP_423_LOCKED,
        ) from exc
    if isinstance(exc, SegmentRevisionConflictError):
        raise TransLokaError(
            code="REVISION_CONFLICT",
            message="The segment was changed after it was loaded.",
            status_code=status.HTTP_409_CONFLICT,
            details={
                "expected_revision": exc.expected_revision,
                "current_revision": exc.current_revision,
            },
        ) from exc
    if isinstance(exc, EmptySegmentTranslationError):
        raise TransLokaError(
            code="VALIDATION_ERROR",
            message="The reviewed translation cannot be empty.",
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        ) from exc
    raise TransLokaError(
        code="VALIDATION_ERROR",
        message="The segment edit is invalid.",
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
    ) from exc
