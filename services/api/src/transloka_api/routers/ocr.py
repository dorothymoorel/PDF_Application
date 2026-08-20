from collections.abc import Iterator
from typing import Annotated, Any, Literal, Never, cast

from fastapi import APIRouter, Depends, Request, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker
from transloka_api.exception_handlers import TransLokaError
from transloka_api.middleware import get_request_id
from transloka_api.routers.pages import _segment_response
from transloka_api.schemas import ErrorResponse
from transloka_api.schemas.pages import PageEditorSegmentResponse
from transloka_api.schemas.projects import ResponseMeta
from transloka_api.services.source_resolution import (
    EmptyResolvedSourceError,
    InvalidResolutionSourceError,
    ResolveSource,
    SourceResolutionService,
    SourceRevisionConflictError,
    SourceSegmentLockedError,
    SourceSegmentNotFoundError,
)
from transloka_core.database import transaction_scope
from transloka_core.database.models.document_ir import DocumentBlock, DocumentSegment
from transloka_core.database.models.pages import DocumentPage

_ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    403: {
        "description": "The request was rejected by the local security policy.",
        "model": ErrorResponse,
    },
    404: {"description": "The OCR page or segment was not found.", "model": ErrorResponse},
    409: {"description": "The segment revision is stale.", "model": ErrorResponse},
    422: {"description": "The request contains invalid values.", "model": ErrorResponse},
    423: {"description": "The segment is locked.", "model": ErrorResponse},
    500: {"description": "An unexpected server error was normalized.", "model": ErrorResponse},
}

router = APIRouter(tags=["OCR"])


class OCRPageSegmentResponse(PageEditorSegmentResponse):
    raw_ocr_text: str | None
    normalized_source_text: str


class OCRPageData(BaseModel):
    page_id: str
    raw_text: str
    resolved_source_text: str
    ocr_confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    segments: list[OCRPageSegmentResponse]


class OCRPageResponse(BaseModel):
    data: OCRPageData
    meta: ResponseMeta


class SourceResolutionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    resolved_source_text: str = Field(min_length=1)
    resolution_source: Literal["AUTO", "AUTOMATIC", "MANUAL", "NATIVE", "OCR"] = "MANUAL"
    expected_revision: int = Field(ge=0)
    reason: str | None = Field(default=None, max_length=2000)


class SourceResolutionSegmentResponse(OCRPageSegmentResponse):
    resolution_source: str


class SourceResolutionResponse(BaseModel):
    data: SourceResolutionSegmentResponse
    meta: ResponseMeta


def get_ocr_session(request: Request) -> Iterator[Session]:
    try:
        factory = request.app.state.session_factory
    except AttributeError as exc:
        raise RuntimeError("The OCR database is not configured.") from exc
    if not callable(factory):
        raise RuntimeError("The OCR database is not configured.")
    with transaction_scope(cast(sessionmaker[Session], factory)) as session:
        yield session


OCRSession = Annotated[Session, Depends(get_ocr_session)]


@router.get(
    "/api/v1/pages/{page_id}/ocr",
    operation_id="get_page_ocr",
    response_model=OCRPageResponse,
    responses=_ERROR_RESPONSES,
)
def get_page_ocr(page_id: str, session: OCRSession) -> OCRPageResponse:
    page = session.get(DocumentPage, page_id)
    if page is None:
        _raise_page_not_found()

    rows = list(
        session.scalars(
            select(DocumentSegment)
            .join(DocumentBlock, DocumentSegment.block_id == DocumentBlock.id)
            .where(DocumentBlock.page_id == page_id)
            .order_by(
                DocumentBlock.page_reading_order,
                DocumentBlock.id,
                DocumentSegment.segment_order,
                DocumentSegment.id,
            )
        )
    )
    return OCRPageResponse(
        data=OCRPageData(
            page_id=page_id,
            raw_text="\n".join(
                row.ocr_text for row in rows if row.ocr_text and row.ocr_text.strip()
            ),
            resolved_source_text="\n".join(row.resolved_source_text for row in rows),
            ocr_confidence=page.ocr_confidence,
            segments=[_ocr_segment_response(row) for row in rows],
        ),
        meta=ResponseMeta(request_id=_request_id()),
    )


@router.patch(
    "/api/v1/segments/{segment_id}/source-resolution",
    operation_id="resolve_segment_source",
    response_model=SourceResolutionResponse,
    responses=_ERROR_RESPONSES,
)
def resolve_segment_source(
    segment_id: str,
    payload: SourceResolutionRequest,
    session: OCRSession,
) -> SourceResolutionResponse:
    try:
        row = SourceResolutionService(session).resolve(
            segment_id,
            ResolveSource(
                resolved_source_text=payload.resolved_source_text,
                expected_revision=payload.expected_revision,
                resolution_source=payload.resolution_source,
                reason=payload.reason,
            ),
        )
    except SourceSegmentNotFoundError as exc:
        _raise_segment_not_found(str(exc))
    except SourceSegmentLockedError as exc:
        _raise_segment_locked(str(exc))
    except SourceRevisionConflictError as exc:
        _raise_revision_conflict(exc.expected_revision, exc.current_revision)
    except (EmptyResolvedSourceError, InvalidResolutionSourceError) as exc:
        _raise_validation_error(str(exc))

    return SourceResolutionResponse(
        data=SourceResolutionSegmentResponse(
            **_ocr_segment_response(row).model_dump(),
            resolution_source=payload.resolution_source,
        ),
        meta=ResponseMeta(request_id=_request_id()),
    )


def _ocr_segment_response(row: DocumentSegment) -> OCRPageSegmentResponse:
    return OCRPageSegmentResponse(
        **_segment_response(row).model_dump(),
        raw_ocr_text=row.ocr_text,
        normalized_source_text=row.normalized_source_text,
    )


def _request_id() -> str:
    request_id = get_request_id()
    if request_id is None:
        raise RuntimeError("The request ID middleware is not configured.")
    return request_id


def _raise_page_not_found() -> Never:
    raise TransLokaError(
        code="PAGE_NOT_FOUND",
        message="The requested OCR page was not found.",
        status_code=status.HTTP_404_NOT_FOUND,
    )


def _raise_segment_not_found(message: str = "The segment was not found.") -> Never:
    raise TransLokaError(
        code="SEGMENT_NOT_FOUND",
        message=message,
        status_code=status.HTTP_404_NOT_FOUND,
    )


def _raise_segment_locked(message: str = "The segment is locked.") -> Never:
    raise TransLokaError(
        code="SEGMENT_LOCKED",
        message=message,
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


def _raise_validation_error(message: str = "The request contains invalid values.") -> Never:
    raise TransLokaError(
        code="VALIDATION_ERROR",
        message=message,
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
    )
