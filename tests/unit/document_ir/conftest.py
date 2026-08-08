from datetime import UTC, datetime

import pytest
from transloka_document_ir import (
    CURRENT_IR_VERSION,
    Block,
    BlockType,
    CoordinateSystem,
    Document,
    DocumentStatus,
    DocumentType,
    Geometry,
    Page,
    PageType,
    Segment,
    SegmentStatus,
    SemanticRole,
)

DOCUMENT_ID = "doc_00000000-0000-4000-8000-000000000001"
PROJECT_ID = "prj_00000000-0000-4000-8000-000000000002"
FILE_ID = "fil_00000000-0000-4000-8000-000000000003"
PAGE_ID = "pag_00000000-0000-4000-8000-000000000004"
BLOCK_ID = "blk_00000000-0000-4000-8000-000000000005"
SEGMENT_ID = "seg_00000000-0000-4000-8000-000000000006"


@pytest.fixture
def source_geometry() -> Geometry:
    return Geometry(
        coordinate_system=CoordinateSystem.PDF_POINT_TOP_LEFT,
        x=72.0,
        y=120.0,
        width=300.0,
        height=40.0,
    )


@pytest.fixture
def minimal_segment() -> Segment:
    return Segment(
        segment_id=SEGMENT_ID,
        block_id=BLOCK_ID,
        segment_order=0,
        source_text="The workflow begins after authentication.",
        normalized_source_text="The workflow begins after authentication.",
        status=SegmentStatus.READY_FOR_TRANSLATION,
    )


@pytest.fixture
def minimal_document(source_geometry: Geometry, minimal_segment: Segment) -> Document:
    block = Block(
        block_id=BLOCK_ID,
        page_id=PAGE_ID,
        block_type=BlockType.PARAGRAPH,
        semantic_role=SemanticRole.BODY_TEXT,
        source_geometry=source_geometry,
        reading_order=0,
        source_text=minimal_segment.source_text,
        normalized_source_text=minimal_segment.normalized_source_text,
        segments=(minimal_segment,),
        status=DocumentStatus.READY_FOR_TRANSLATION,
    )
    page = Page(
        page_id=PAGE_ID,
        document_id=DOCUMENT_ID,
        source_page_number=1,
        width=595.28,
        height=841.89,
        rotation=0.0,
        page_type=PageType.DIGITAL,
        status=DocumentStatus.STRUCTURED,
        blocks=(block,),
    )
    timestamp = datetime(2026, 7, 26, 8, 0, tzinfo=UTC)
    return Document(
        ir_version=CURRENT_IR_VERSION,
        document_id=DOCUMENT_ID,
        project_id=PROJECT_ID,
        source_file_id=FILE_ID,
        source_language="en",
        target_language="id",
        document_type=DocumentType.USER_MANUAL,
        page_count=1,
        status=DocumentStatus.READY_FOR_TRANSLATION,
        revision=1,
        created_at=timestamp,
        updated_at=timestamp,
        pages=(page,),
    )
