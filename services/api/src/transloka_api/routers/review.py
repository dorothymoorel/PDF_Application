from collections.abc import Iterator
from typing import Annotated, Any, Never, cast

from fastapi import APIRouter, Depends, Query, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import and_, false, or_, select
from sqlalchemy.orm import Session, sessionmaker
from transloka_api.exception_handlers import TransLokaError
from transloka_api.middleware import get_request_id
from transloka_api.routers.pages import _segment_response
from transloka_api.schemas import ErrorResponse
from transloka_api.schemas.pages import PageEditorSegmentResponse, PageEditorWarningResponse
from transloka_api.schemas.projects import ResponseMeta
from transloka_core.database import transaction_scope
from transloka_core.database.models.document_ir import (
    DocumentBlock,
    DocumentSection,
    DocumentSegment,
    ReviewStatus,
    SegmentStatus,
)
from transloka_core.database.models.documents import Document
from transloka_core.database.models.pages import DocumentPage
from transloka_core.database.models.projects import Project

_ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    403: {
        "description": "The request was rejected by the local security policy.",
        "model": ErrorResponse,
    },
    404: {"description": "The project was not found.", "model": ErrorResponse},
    422: {"description": "The request contains invalid values.", "model": ErrorResponse},
    500: {"description": "An unexpected server error was normalized.", "model": ErrorResponse},
}

_QUEUE_REVIEW_STATUSES = (
    ReviewStatus.NOT_REVIEWED.value,
    ReviewStatus.REVIEW_REQUIRED.value,
    ReviewStatus.IN_REVIEW.value,
    ReviewStatus.REJECTED.value,
)
_QUEUE_SEGMENT_STATUSES = (
    SegmentStatus.NEEDS_REVIEW.value,
    SegmentStatus.TRANSLATION_FAILED.value,
)

router = APIRouter(prefix="/api/v1/projects", tags=["Review"])


class ReviewQueueSourceContext(BaseModel):
    previous_segment: str | None
    next_segment: str | None
    heading: str | None


class ReviewQueueItem(BaseModel):
    page_id: str
    segment: PageEditorSegmentResponse
    warnings: list[PageEditorWarningResponse] = Field(default_factory=list)
    source_context: ReviewQueueSourceContext


class ReviewQueuePagination(BaseModel):
    limit: int
    next_cursor: str | None
    has_more: bool


class ReviewQueueMeta(ResponseMeta):
    pagination: ReviewQueuePagination


class ReviewQueueResponse(BaseModel):
    data: list[ReviewQueueItem]
    meta: ReviewQueueMeta


def get_review_session(request: Request) -> Iterator[Session]:
    try:
        factory = request.app.state.session_factory
    except AttributeError as exc:
        raise RuntimeError("The review queue database is not configured.") from exc
    if not callable(factory):
        raise RuntimeError("The review queue database is not configured.")
    with transaction_scope(cast(sessionmaker[Session], factory)) as session:
        yield session


ReviewSession = Annotated[Session, Depends(get_review_session)]


@router.get(
    "/{project_id}/review-queue",
    operation_id="list_review_queue",
    response_model=ReviewQueueResponse,
    responses=_ERROR_RESPONSES,
)
def list_review_queue(
    project_id: str,
    session: ReviewSession,
    severity: Annotated[str | None, Query(min_length=1)] = None,
    warning_type: Annotated[str | None, Query(min_length=1)] = None,
    warning: bool | None = None,
    confidence_max: Annotated[float | None, Query(ge=0.0, le=1.0)] = None,
    page_id: Annotated[str | None, Query(min_length=1)] = None,
    section_id: Annotated[str | None, Query(min_length=1)] = None,
    segment_status: Annotated[str | None, Query(alias="status", min_length=1)] = None,
    review_status: ReviewStatus | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    cursor: Annotated[str | None, Query(min_length=1)] = None,
) -> ReviewQueueResponse:
    if session.get(Project, project_id) is None:
        _raise_project_not_found()

    offset = _cursor_offset(cursor)
    statement = (
        select(
            DocumentSegment,
            DocumentBlock.page_id,
            DocumentPage.source_page_number,
            DocumentSection.source_summary,
        )
        .join(DocumentBlock, DocumentSegment.block_id == DocumentBlock.id)
        .join(DocumentPage, DocumentBlock.page_id == DocumentPage.id)
        .join(Document, DocumentPage.document_id == Document.id)
        .outerjoin(DocumentSection, DocumentSegment.section_id == DocumentSection.id)
        .where(
            Document.project_id == project_id,
            or_(
                DocumentSegment.review_status.in_(_QUEUE_REVIEW_STATUSES),
                DocumentSegment.status.in_(_QUEUE_SEGMENT_STATUSES),
            ),
        )
        .order_by(
            DocumentPage.source_page_number,
            DocumentSegment.global_order.is_(None),
            DocumentSegment.global_order,
            DocumentSegment.segment_order,
            DocumentSegment.id,
        )
    )

    if severity is not None or warning_type is not None:
        # The warning table is not part of the current migration head. Keep the
        # documented filters safe and deterministic until warning persistence lands.
        statement = statement.where(false())
    if warning is True:
        statement = statement.where(
            or_(
                DocumentSegment.review_status == ReviewStatus.REVIEW_REQUIRED.value,
                DocumentSegment.status == SegmentStatus.NEEDS_REVIEW.value,
            )
        )
    elif warning is False:
        statement = statement.where(
            and_(
                DocumentSegment.review_status != ReviewStatus.REVIEW_REQUIRED.value,
                DocumentSegment.status != SegmentStatus.NEEDS_REVIEW.value,
            )
        )
    if confidence_max is not None:
        statement = statement.where(
            DocumentSegment.confidence_overall.is_not(None),
            DocumentSegment.confidence_overall <= confidence_max,
        )
    if page_id is not None:
        statement = statement.where(DocumentBlock.page_id == page_id)
    if section_id is not None:
        statement = statement.where(DocumentSegment.section_id == section_id)
    if segment_status is not None:
        statement = statement.where(
            or_(
                DocumentSegment.status == segment_status,
                DocumentSegment.review_status == segment_status,
            )
        )
    if review_status is not None:
        statement = statement.where(DocumentSegment.review_status == review_status.value)

    rows = list(session.execute(statement))
    total = len(rows)
    page = rows[offset : offset + limit]
    items = [
        ReviewQueueItem(
            page_id=row[1],
            segment=_segment_response(row[0]),
            source_context=_source_context(rows, index),
        )
        for index, row in enumerate(page, start=offset)
    ]
    next_offset = offset + len(page)
    return ReviewQueueResponse(
        data=items,
        meta=ReviewQueueMeta(
            request_id=_request_id(),
            pagination=ReviewQueuePagination(
                limit=limit,
                next_cursor=str(next_offset) if next_offset < total else None,
                has_more=next_offset < total,
            ),
        ),
    )


def _source_context(rows: list[Any], index: int) -> ReviewQueueSourceContext:
    previous = rows[index - 1][0].source_text if index > 0 else None
    following = rows[index + 1][0].source_text if index + 1 < len(rows) else None
    heading = rows[index][3]
    return ReviewQueueSourceContext(
        previous_segment=previous,
        next_segment=following,
        heading=heading,
    )


def _cursor_offset(cursor: str | None) -> int:
    if cursor is None:
        return 0
    if not cursor.isdecimal():
        _raise_validation_error()
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


def _raise_validation_error() -> Never:
    raise TransLokaError(
        code="VALIDATION_ERROR",
        message="The review queue cursor is invalid.",
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
    )
