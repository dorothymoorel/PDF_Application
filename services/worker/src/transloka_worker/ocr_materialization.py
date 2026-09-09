from __future__ import annotations

import json
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import select
from sqlalchemy.orm import Session
from transloka_core.database.models.document_ir import (
    BlockType,
    DocumentBlock,
    DocumentSegment,
    ReviewStatus,
    SegmentStatus,
    SemanticRole,
)
from transloka_core.database.models.documents import Document, DocumentStatus
from transloka_core.database.models.pages import DocumentPage
from transloka_core.database.models.projects import Project
from transloka_documents.ocr import OCRGeometry
from transloka_documents.ocr.normalization import normalize_ocr_result
from transloka_documents.ocr.orchestration import OCRJobRequest, OCRPageOutput, OCRRunResult


class OCRMaterializationError(RuntimeError):
    pass


def materialize_ocr_outputs(
    session: Session,
    request: OCRJobRequest,
    result: OCRRunResult,
    *,
    now: str,
) -> None:
    # Standalone OCR requests have no document IR to populate.
    if request.document_id is None or not result.outputs:
        return
    document = session.get(Document, request.document_id)
    project = session.get(Project, request.project_id)
    if (
        document is None
        or project is None
        or document.project_id != project.id
        or project.active_document_id != document.id
    ):
        raise OCRMaterializationError("The OCR document is no longer active.")

    pages = {
        page.source_page_number: page
        for page in session.scalars(
            select(DocumentPage).where(DocumentPage.document_id == document.id)
        )
    }
    seen: set[int] = set()
    added = False
    for output in result.outputs:
        page = pages.get(output.page_number)
        if (
            page is None
            or output.page_number not in request.page_numbers
            or output.page_number in seen
            or output.result.page_number != output.page_number
            or output.render.dpi != request.dpi
        ):
            raise OCRMaterializationError("The OCR output page is inconsistent.")
        seen.add(output.page_number)
        # Re-OCR must never overwrite native extraction or user-reviewed source.
        if session.scalar(
            select(DocumentBlock.id).where(DocumentBlock.page_id == page.id).limit(1)
        ):
            continue
        added = _materialize_page(session, page, project, output, now=now) or added

    session.flush()
    if added:
        _order_document(session, document.id, now=now)


def _materialize_page(
    session: Session,
    page: DocumentPage,
    project: Project,
    output: OCRPageOutput,
    *,
    now: str,
) -> bool:
    normalized = normalize_ocr_result(output.result)
    if normalized.normalized_text.strip() and not normalized.segments:
        raise OCRMaterializationError("OCR text has no usable block geometry.")

    block_ids: dict[str, str] = {}
    for block in normalized.blocks:
        block_id = f"blk_{uuid5(NAMESPACE_URL, f'transloka:ocr:{page.id}:{block.block_id}')}"
        block_ids[block.block_id] = block_id
        session.add(
            DocumentBlock(
                id=block_id,
                page_id=page.id,
                section_id=None,
                parent_block_id=None,
                block_type=BlockType.PARAGRAPH.value,
                semantic_role=SemanticRole.BODY_TEXT.value,
                page_reading_order=block.reading_order,
                global_reading_order=None,
                source_text=block.source_text,
                normalized_source_text=block.normalized_source_text,
                source_geometry_json=_geometry_json(block.geometry, page, dpi=output.render.dpi),
                target_geometry_json=None,
                style_json=None,
                detail_json=json.dumps(
                    {
                        "source": "OCR",
                        "raw_file_id": output.raw_output.file_id,
                        "raw_checksum_sha256": output.raw_output.checksum_sha256,
                    }
                ),
                status=DocumentStatus.STRUCTURED.value,
                confidence=block.confidence,
                created_at=now,
                updated_at=now,
            )
        )
    session.flush()
    for segment in normalized.segments:
        session.add(
            DocumentSegment(
                id=f"seg_{uuid5(NAMESPACE_URL, f'transloka:ocr:{page.id}:{segment.segment_id}')}",
                block_id=block_ids[segment.block_id],
                section_id=None,
                segment_order=segment.segment_order,
                global_order=None,
                source_text=segment.source_text,
                native_text=None,
                ocr_text=segment.source_text,
                resolved_source_text=segment.normalized_source_text,
                normalized_source_text=segment.normalized_source_text,
                protected_source_text=None,
                machine_translation=None,
                reviewed_translation=None,
                final_text=None,
                source_language=project.source_language,
                target_language=project.target_language,
                status=SegmentStatus.READY_FOR_TRANSLATION.value,
                review_status=(
                    ReviewStatus.REVIEW_REQUIRED.value
                    if segment.is_low_confidence
                    else ReviewStatus.NOT_REVIEWED.value
                ),
                is_locked=0,
                current_revision=0,
                confidence_overall=segment.confidence,
                confidence_json=None,
                translation_settings_hash=None,
                created_at=now,
                updated_at=now,
            )
        )
    page.status = DocumentStatus.STRUCTURED.value
    page.ocr_confidence = normalized.confidence
    page.structure_confidence = normalized.confidence
    page.column_count = normalized.column_count
    page.updated_at = now
    return bool(normalized.blocks)


def _geometry_json(geometry: OCRGeometry, page: DocumentPage, *, dpi: int) -> str:
    if geometry.coordinate_system == "PIXEL_TOP_LEFT":
        scale = 72.0 / dpi
    elif geometry.coordinate_system == "PDF_POINT_TOP_LEFT":
        scale = 1.0
    else:
        raise OCRMaterializationError("The OCR coordinate system is unsupported.")
    x, y = geometry.x * scale, geometry.y * scale
    width, height = geometry.width * scale, geometry.height * scale
    # Raster dimensions round up to a pixel; keep only that edge tolerance.
    tolerance = 72.0 / dpi if geometry.coordinate_system == "PIXEL_TOP_LEFT" else 0.1
    if (
        x >= page.width_points
        or y >= page.height_points
        or x + width > page.width_points + tolerance
        or y + height > page.height_points + tolerance
    ):
        raise OCRMaterializationError("The OCR geometry is outside its page.")
    return json.dumps(
        {
            "x": x,
            "y": y,
            "width": min(width, page.width_points - x),
            "height": min(height, page.height_points - y),
            "coordinate_system": "PDF_POINT_TOP_LEFT",
        },
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _order_document(session: Session, document_id: str, *, now: str) -> None:
    blocks = session.scalars(
        select(DocumentBlock)
        .join(DocumentPage, DocumentPage.id == DocumentBlock.page_id)
        .where(DocumentPage.document_id == document_id)
        .order_by(
            DocumentPage.source_page_number, DocumentBlock.page_reading_order, DocumentBlock.id
        )
    )
    for order, block in enumerate(blocks, start=1):
        if block.global_reading_order != order:
            block.global_reading_order = order
            block.updated_at = now
    segments = session.scalars(
        select(DocumentSegment)
        .join(DocumentBlock, DocumentBlock.id == DocumentSegment.block_id)
        .join(DocumentPage, DocumentPage.id == DocumentBlock.page_id)
        .where(DocumentPage.document_id == document_id)
        .order_by(
            DocumentPage.source_page_number,
            DocumentBlock.page_reading_order,
            DocumentBlock.id,
            DocumentSegment.segment_order,
            DocumentSegment.id,
        )
    )
    for order, segment in enumerate(segments, start=1):
        if segment.global_order != order:
            segment.global_order = order
            segment.updated_at = now
