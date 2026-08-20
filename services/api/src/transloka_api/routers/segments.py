from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Annotated, Any, Never, cast
from uuid import uuid4

from fastapi import APIRouter, Depends, Request, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select, update
from sqlalchemy.engine import CursorResult
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
    invalidate_reconstruction_cache,
)
from transloka_core.database import transaction_scope
from transloka_core.database.models.document_ir import (
    DocumentSegment,
    ReviewStatus,
    SegmentStatus,
)
from transloka_core.database.models.revisions import SegmentRevision, SegmentRevisionType
from transloka_core.database.models.translation import SegmentTranslation

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


class ApproveSegmentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_revision: int = Field(ge=0)
    lock_after_approval: bool = False


class UnapproveSegmentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

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


@router.post(
    "/{segment_id}/approve",
    operation_id="approve_segment",
    response_model=SegmentDataResponse,
    responses=_ERROR_RESPONSES,
)
def approve_segment(
    segment_id: str,
    payload: ApproveSegmentRequest,
    session: SegmentSession,
) -> SegmentDataResponse:
    try:
        row = _change_review_state(
            session,
            segment_id,
            expected_revision=payload.expected_revision,
            revision_type=SegmentRevisionType.APPROVE,
            lock_after_approval=payload.lock_after_approval,
        )
    except SegmentServiceError as exc:
        _raise_segment_error(exc)
    return SegmentDataResponse(
        data=_segment_response(row),
        meta=ResponseMeta(request_id=_request_id()),
    )


@router.post(
    "/{segment_id}/unapprove",
    operation_id="unapprove_segment",
    response_model=SegmentDataResponse,
    responses=_ERROR_RESPONSES,
)
def unapprove_segment(
    segment_id: str,
    payload: UnapproveSegmentRequest,
    session: SegmentSession,
) -> SegmentDataResponse:
    try:
        row = _change_review_state(
            session,
            segment_id,
            expected_revision=payload.expected_revision,
            revision_type=SegmentRevisionType.UNAPPROVE,
            reason=payload.reason,
        )
    except SegmentServiceError as exc:
        _raise_segment_error(exc)
    return SegmentDataResponse(
        data=_segment_response(row),
        meta=ResponseMeta(request_id=_request_id()),
    )


def _change_review_state(
    session: Session,
    segment_id: str,
    *,
    expected_revision: int,
    revision_type: SegmentRevisionType,
    lock_after_approval: bool = False,
    reason: str | None = None,
) -> DocumentSegment:
    row = session.get(DocumentSegment, segment_id)
    if row is None:
        raise SegmentNotFoundError("The segment was not found.")
    if row.is_locked:
        raise SegmentLockedError("The segment is locked.")
    if row.current_revision != expected_revision:
        raise SegmentRevisionConflictError(expected_revision, row.current_revision)

    if revision_type is SegmentRevisionType.APPROVE:
        if row.review_status == ReviewStatus.APPROVED.value:
            raise SegmentReviewStateError("The segment is already approved.")
        new_text = next(
            (
                value.strip()
                for value in (row.reviewed_translation, row.final_text, row.machine_translation)
                if value and value.strip()
            ),
            None,
        )
        if new_text is None:
            raise SegmentReviewStateError("A translated value is required before approval.")
        new_status = (
            SegmentStatus.LOCKED.value if lock_after_approval else SegmentStatus.APPROVED.value
        )
        new_review_status = ReviewStatus.APPROVED.value
        new_is_locked = 1 if lock_after_approval else 0
        reviewed_translation = new_text
    else:
        if row.review_status != ReviewStatus.APPROVED.value:
            raise SegmentReviewStateError("Only an approved segment can be unapproved.")
        new_text = row.final_text or row.reviewed_translation or row.machine_translation
        if not new_text or not new_text.strip():
            raise SegmentReviewStateError("The approved segment has no translatable value.")
        new_status = SegmentStatus.USER_EDITED.value
        new_review_status = ReviewStatus.EDITED.value
        new_is_locked = 0
        reviewed_translation = row.reviewed_translation or new_text

    next_revision = expected_revision + 1
    now = _utc_now()
    result = cast(
        CursorResult[Any],
        session.execute(
            update(DocumentSegment)
            .where(
                DocumentSegment.id == segment_id,
                DocumentSegment.current_revision == expected_revision,
                DocumentSegment.is_locked == 0,
            )
            .values(
                reviewed_translation=reviewed_translation,
                final_text=new_text.strip(),
                status=new_status,
                review_status=new_review_status,
                is_locked=new_is_locked,
                current_revision=next_revision,
                updated_at=now,
            )
        ),
    )
    if result.rowcount != 1:
        current = session.get(DocumentSegment, segment_id)
        if current is None:
            raise SegmentNotFoundError("The segment was not found.")
        if current.is_locked:
            raise SegmentLockedError("The segment is locked.")
        raise SegmentRevisionConflictError(expected_revision, current.current_revision)

    session.add(
        SegmentRevision(
            id=f"rev_{uuid4()}",
            segment_id=segment_id,
            revision_number=next_revision,
            revision_type=revision_type.value,
            previous_text=row.final_text,
            new_text=new_text.strip(),
            source_translation_id=_latest_translation_id(session, segment_id),
            reason=reason.strip() if reason else None,
            metadata_json=None,
            created_at=now,
        )
    )
    session.flush()
    invalidate_reconstruction_cache(segment_id)
    updated = session.get(DocumentSegment, segment_id)
    if updated is None:
        raise SegmentNotFoundError("The segment was not found after review update.")
    return updated


def _latest_translation_id(session: Session, segment_id: str) -> str | None:
    return session.scalar(
        select(SegmentTranslation.id)
        .where(SegmentTranslation.segment_id == segment_id)
        .order_by(SegmentTranslation.created_at.desc(), SegmentTranslation.id.desc())
        .limit(1)
    )


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


class SegmentReviewStateError(SegmentServiceError):
    pass


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
    if isinstance(exc, SegmentReviewStateError):
        raise TransLokaError(
            code="SEGMENT_STATE_INVALID",
            message="The segment review state does not allow this operation.",
            status_code=status.HTTP_409_CONFLICT,
        ) from exc
    raise TransLokaError(
        code="VALIDATION_ERROR",
        message="The segment edit is invalid.",
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
    ) from exc
