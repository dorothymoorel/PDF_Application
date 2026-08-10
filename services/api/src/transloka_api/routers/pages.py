import json
from collections.abc import Iterator
from typing import Annotated, Any, Never, cast

from fastapi import APIRouter, Depends, Request
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker
from transloka_api.exception_handlers import TransLokaError
from transloka_api.middleware import get_request_id
from transloka_api.schemas import ErrorResponse
from transloka_api.schemas.pages import (
    GeometryResponse,
    PageConfidenceResponse,
    PageEditorBlockResponse,
    PageEditorPageResponse,
    PageEditorSegmentResponse,
    PageEditorViewData,
    PageEditorViewResponse,
    PagePreviewResponse,
    SegmentConfidenceResponse,
)
from transloka_api.schemas.projects import ResponseMeta
from transloka_core.database.models.document_ir import (
    BlockType,
    DocumentBlock,
    DocumentSegment,
    ReviewStatus,
    SegmentStatus,
    SemanticRole,
)
from transloka_core.database.models.documents import DocumentStatus
from transloka_core.database.models.pages import DocumentPage, PageType

_ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    403: {
        "description": "The request was rejected by the local security policy.",
        "model": ErrorResponse,
    },
    404: {"description": "The page was not found.", "model": ErrorResponse},
    422: {"description": "The request contains invalid values.", "model": ErrorResponse},
    500: {"description": "An unexpected server error was normalized.", "model": ErrorResponse},
}

router = APIRouter(prefix="/api/v1/pages", tags=["Pages"])


def get_page_session(request: Request) -> Iterator[Session]:
    try:
        factory = request.app.state.session_factory
    except AttributeError as exc:
        raise RuntimeError("The page database is not configured.") from exc
    if not callable(factory):
        raise RuntimeError("The page database is not configured.")
    with cast(sessionmaker[Session], factory)() as session:
        yield session


PageSession = Annotated[Session, Depends(get_page_session)]


@router.get(
    "/{page_id}/editor-view",
    operation_id="get_page_editor_view",
    response_model=PageEditorViewResponse,
    responses=_ERROR_RESPONSES,
)
def get_page_editor_view(page_id: str, session: PageSession) -> PageEditorViewResponse:
    page = session.get(DocumentPage, page_id)
    if page is None:
        _raise_page_not_found()

    blocks = list(
        session.scalars(
            select(DocumentBlock)
            .where(DocumentBlock.page_id == page_id)
            .order_by(DocumentBlock.page_reading_order, DocumentBlock.id)
        )
    )
    segments = list(
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

    return PageEditorViewResponse(
        data=PageEditorViewData(
            page=_page_response(page),
            blocks=[_block_response(block) for block in blocks],
            segments=[_segment_response(segment) for segment in segments],
            warnings=[],
        ),
        meta=ResponseMeta(request_id=_request_id()),
    )


def _page_response(row: DocumentPage) -> PageEditorPageResponse:
    page_url = f"/api/v1/pages/{row.id}"
    return PageEditorPageResponse(
        id=row.id,
        document_id=row.document_id,
        source_page_number=row.source_page_number,
        logical_page_number=row.logical_page_number,
        width_points=row.width_points,
        height_points=row.height_points,
        rotation_degrees=row.rotation_degrees,
        page_type=PageType(row.page_type),
        page_classification=row.page_classification,
        column_count=row.column_count,
        reading_direction=row.reading_direction,
        status=DocumentStatus(row.status),
        confidence=PageConfidenceResponse(
            native_extraction=row.native_extraction_confidence,
            ocr=row.ocr_confidence,
            structure=row.structure_confidence,
        ),
        preview=PagePreviewResponse(
            thumbnail_url=f"{page_url}/thumbnail" if row.thumbnail_file_id else None,
            render_url=f"{page_url}/render" if row.render_file_id else None,
        ),
    )


def _block_response(row: DocumentBlock) -> PageEditorBlockResponse:
    return PageEditorBlockResponse(
        id=row.id,
        page_id=row.page_id,
        section_id=row.section_id,
        parent_block_id=row.parent_block_id,
        block_type=BlockType(row.block_type),
        semantic_role=SemanticRole(row.semantic_role) if row.semantic_role else None,
        page_reading_order=row.page_reading_order,
        global_reading_order=row.global_reading_order,
        source_text=row.source_text,
        normalized_source_text=row.normalized_source_text,
        source_geometry=_geometry(row.source_geometry_json),
        target_geometry=_geometry(row.target_geometry_json) if row.target_geometry_json else None,
        status=DocumentStatus(row.status),
        confidence=row.confidence,
    )


def _segment_response(row: DocumentSegment) -> PageEditorSegmentResponse:
    return PageEditorSegmentResponse(
        id=row.id,
        block_id=row.block_id,
        section_id=row.section_id,
        segment_order=row.segment_order,
        global_order=row.global_order,
        source_text=row.source_text,
        resolved_source_text=row.resolved_source_text,
        machine_translation=row.machine_translation,
        reviewed_translation=row.reviewed_translation,
        final_text=row.final_text,
        source_language=row.source_language,
        target_language=row.target_language,
        status=SegmentStatus(row.status),
        review_status=ReviewStatus(row.review_status),
        is_locked=bool(row.is_locked),
        current_revision=row.current_revision,
        confidence=SegmentConfidenceResponse(overall=row.confidence_overall),
        warning_count=0,
    )


def _geometry(value: str) -> GeometryResponse:
    try:
        return GeometryResponse.model_validate(json.loads(value))
    except (json.JSONDecodeError, TypeError, ValidationError) as exc:
        raise RuntimeError("Stored page geometry is invalid.") from exc


def _request_id() -> str:
    request_id = get_request_id()
    if request_id is None:
        raise RuntimeError("The request ID middleware is not configured.")
    return request_id


def _raise_page_not_found() -> Never:
    raise TransLokaError(
        code="PAGE_NOT_FOUND",
        message="The requested page was not found.",
        status_code=404,
    )
