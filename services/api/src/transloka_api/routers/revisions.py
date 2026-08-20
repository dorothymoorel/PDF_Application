import base64
import binascii
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Annotated, Any, Never, cast
from uuid import uuid4

from fastapi import APIRouter, Depends, Query, Request, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import and_, or_, select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.orm import Session, sessionmaker
from transloka_api.exception_handlers import TransLokaError
from transloka_api.middleware import get_request_id
from transloka_api.routers.pages import _segment_response
from transloka_api.schemas import ErrorResponse
from transloka_api.schemas.pages import PageEditorSegmentResponse
from transloka_api.schemas.projects import ResponseMeta
from transloka_core.database import transaction_scope
from transloka_core.database.models.document_ir import (
    DocumentSegment,
    ReviewStatus,
    SegmentStatus,
)
from transloka_core.database.models.revisions import SegmentRevision, SegmentRevisionType

_ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    403: {
        "description": "The request was rejected by the local security policy.",
        "model": ErrorResponse,
    },
    404: {"description": "The segment or revision was not found.", "model": ErrorResponse},
    409: {"description": "The segment revision is stale.", "model": ErrorResponse},
    422: {"description": "The request contains invalid values.", "model": ErrorResponse},
    423: {"description": "The segment is locked.", "model": ErrorResponse},
    500: {"description": "An unexpected server error was normalized.", "model": ErrorResponse},
}

router = APIRouter(tags=["Segments"])


class CursorPagination(BaseModel):
    limit: int
    next_cursor: str | None
    has_more: bool


class RevisionCollectionMeta(ResponseMeta):
    pagination: CursorPagination


class SegmentRevisionResponse(BaseModel):
    id: str
    segment_id: str
    revision_number: int = Field(ge=1)
    revision_type: SegmentRevisionType
    previous_text: str | None
    new_text: str
    source_translation_id: str | None
    reason: str | None
    metadata_json: str | None
    created_at: str


class SegmentRevisionListResponse(BaseModel):
    data: list[SegmentRevisionResponse]
    meta: RevisionCollectionMeta


class SegmentRevisionDataResponse(BaseModel):
    data: SegmentRevisionResponse
    meta: ResponseMeta


class RestoreRevisionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    revision_id: str = Field(min_length=1)
    expected_revision: int = Field(ge=0)


class RestoreRevisionResponse(BaseModel):
    data: PageEditorSegmentResponse
    meta: ResponseMeta


def get_revision_session(request: Request) -> Iterator[Session]:
    try:
        factory = request.app.state.session_factory
    except AttributeError as exc:
        raise RuntimeError("The revision database is not configured.") from exc
    if not callable(factory):
        raise RuntimeError("The revision database is not configured.")
    with transaction_scope(cast(sessionmaker[Session], factory)) as session:
        yield session


RevisionSession = Annotated[Session, Depends(get_revision_session)]


@router.get(
    "/api/v1/segments/{segment_id}/revisions",
    operation_id="list_segment_revisions",
    response_model=SegmentRevisionListResponse,
    responses=_ERROR_RESPONSES,
)
def list_segment_revisions(
    segment_id: str,
    session: RevisionSession,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    cursor: Annotated[str | None, Query(min_length=1, max_length=1024)] = None,
) -> SegmentRevisionListResponse:
    _get_segment(session, segment_id)
    statement = select(SegmentRevision).where(SegmentRevision.segment_id == segment_id)
    if cursor is not None:
        revision_number, revision_id = _decode_cursor(cursor)
        statement = statement.where(
            or_(
                SegmentRevision.revision_number < revision_number,
                and_(
                    SegmentRevision.revision_number == revision_number,
                    SegmentRevision.id < revision_id,
                ),
            )
        )

    rows = list(
        session.scalars(
            statement.order_by(
                SegmentRevision.revision_number.desc(),
                SegmentRevision.id.desc(),
            ).limit(limit + 1)
        )
    )
    has_more = len(rows) > limit
    page = rows[:limit]
    return SegmentRevisionListResponse(
        data=[_revision_response(row) for row in page],
        meta=RevisionCollectionMeta(
            request_id=_request_id(),
            pagination=CursorPagination(
                limit=limit,
                next_cursor=_encode_cursor(page[-1]) if has_more else None,
                has_more=has_more,
            ),
        ),
    )


@router.get(
    "/api/v1/segment-revisions/{revision_id}",
    operation_id="get_segment_revision",
    response_model=SegmentRevisionDataResponse,
    responses=_ERROR_RESPONSES,
)
def get_segment_revision(revision_id: str, session: RevisionSession) -> SegmentRevisionDataResponse:
    row = session.get(SegmentRevision, revision_id)
    if row is None:
        _raise_revision_not_found()
    return SegmentRevisionDataResponse(
        data=_revision_response(row),
        meta=ResponseMeta(request_id=_request_id()),
    )


@router.post(
    "/api/v1/segments/{segment_id}/restore-revision",
    operation_id="restore_segment_revision",
    response_model=RestoreRevisionResponse,
    responses=_ERROR_RESPONSES,
)
def restore_segment_revision(
    segment_id: str,
    payload: RestoreRevisionRequest,
    session: RevisionSession,
) -> RestoreRevisionResponse:
    segment = _get_segment(session, segment_id)
    if segment.is_locked:
        _raise_segment_locked()
    if segment.current_revision != payload.expected_revision:
        _raise_revision_conflict(payload.expected_revision, segment.current_revision)

    revision = session.scalar(
        select(SegmentRevision).where(
            SegmentRevision.id == payload.revision_id,
            SegmentRevision.segment_id == segment_id,
        )
    )
    if revision is None:
        _raise_revision_not_found()

    next_revision = payload.expected_revision + 1
    now = _utc_now()
    result = cast(
        CursorResult[Any],
        session.execute(
            update(DocumentSegment)
            .where(
                DocumentSegment.id == segment_id,
                DocumentSegment.current_revision == payload.expected_revision,
                DocumentSegment.is_locked == 0,
            )
            .values(
                reviewed_translation=revision.new_text,
                final_text=revision.new_text,
                status=SegmentStatus.USER_EDITED.value,
                review_status=ReviewStatus.EDITED.value,
                current_revision=next_revision,
                updated_at=now,
            )
        ),
    )
    if result.rowcount != 1:
        current = session.get(DocumentSegment, segment_id)
        if current is None:
            _raise_segment_not_found()
        if current.is_locked:
            _raise_segment_locked()
        _raise_revision_conflict(payload.expected_revision, current.current_revision)

    session.add(
        SegmentRevision(
            id=f"rev_{uuid4()}",
            segment_id=segment_id,
            revision_number=next_revision,
            revision_type=SegmentRevisionType.RESTORE_VERSION.value,
            previous_text=segment.final_text,
            new_text=revision.new_text,
            source_translation_id=revision.source_translation_id,
            reason=f"Restored revision {revision.id}.",
            metadata_json=None,
            created_at=now,
        )
    )
    session.flush()
    updated = session.get(DocumentSegment, segment_id)
    if updated is None:
        _raise_segment_not_found()
    return RestoreRevisionResponse(
        data=_segment_response(updated),
        meta=ResponseMeta(request_id=_request_id()),
    )


def _get_segment(session: Session, segment_id: str) -> DocumentSegment:
    row = session.get(DocumentSegment, segment_id)
    if row is None:
        _raise_segment_not_found()
    return row


def _revision_response(row: SegmentRevision) -> SegmentRevisionResponse:
    return SegmentRevisionResponse(
        id=row.id,
        segment_id=row.segment_id,
        revision_number=row.revision_number,
        revision_type=SegmentRevisionType(row.revision_type),
        previous_text=row.previous_text,
        new_text=row.new_text,
        source_translation_id=row.source_translation_id,
        reason=row.reason,
        metadata_json=row.metadata_json,
        created_at=row.created_at,
    )


def _encode_cursor(row: SegmentRevision) -> str:
    value = f"{row.revision_number}\0{row.id}".encode()
    return base64.urlsafe_b64encode(value).decode().rstrip("=")


def _decode_cursor(value: str) -> tuple[int, str]:
    try:
        decoded = base64.b64decode(
            value + "=" * (-len(value) % 4),
            altchars=b"-_",
            validate=True,
        ).decode()
        revision_number_text, revision_id = decoded.split("\0", maxsplit=1)
        revision_number = int(revision_number_text)
    except (binascii.Error, UnicodeDecodeError, ValueError):
        _raise_validation_error()
    if revision_number < 1 or not revision_id.startswith("rev_"):
        _raise_validation_error()
    return revision_number, revision_id


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _request_id() -> str:
    request_id = get_request_id()
    if request_id is None:
        raise RuntimeError("The request identifier is unavailable.")
    return request_id


def _raise_segment_not_found() -> Never:
    raise TransLokaError(
        code="SEGMENT_NOT_FOUND",
        message="The requested segment was not found.",
        status_code=status.HTTP_404_NOT_FOUND,
    )


def _raise_revision_not_found() -> Never:
    raise TransLokaError(
        code="REVISION_NOT_FOUND",
        message="The requested segment revision was not found.",
        status_code=status.HTTP_404_NOT_FOUND,
    )


def _raise_segment_locked() -> Never:
    raise TransLokaError(
        code="SEGMENT_LOCKED",
        message="The segment is locked and cannot be restored.",
        status_code=status.HTTP_423_LOCKED,
    )


def _raise_revision_conflict(expected_revision: int, current_revision: int) -> Never:
    raise TransLokaError(
        code="REVISION_CONFLICT",
        message="The segment was changed after it was loaded.",
        status_code=status.HTTP_409_CONFLICT,
        details={
            "expected_revision": expected_revision,
            "current_revision": current_revision,
        },
    )


def _raise_validation_error() -> Never:
    raise TransLokaError(
        code="VALIDATION_ERROR",
        message="The request contains invalid values.",
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
    )
