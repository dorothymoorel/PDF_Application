from collections.abc import Callable
from typing import Any, cast

import pytest
from pydantic import ValidationError
from transloka_document_ir import (
    Annotation,
    AnnotationType,
    Asset,
    AssetType,
    Block,
    Cell,
    CellRole,
    CoordinateSystem,
    Document,
    DocumentStatus,
    EntityIdPrefix,
    Geometry,
    Page,
    Relationship,
    RelationshipType,
    Section,
    SectionType,
    Segment,
    SegmentStatus,
    Table,
    Warning,
    WarningSeverity,
    WarningStatus,
    WarningType,
    new_entity_id,
)

DOCUMENT_ID = "doc_00000000-0000-4000-8000-000000000001"
PAGE_ID = "pag_00000000-0000-4000-8000-000000000004"
BLOCK_ID = "blk_00000000-0000-4000-8000-000000000005"
SEGMENT_ID = "seg_00000000-0000-4000-8000-000000000006"
TABLE_ID = "tbl_00000000-0000-4000-8000-000000000007"
CELL_ID = "cel_00000000-0000-4000-8000-000000000008"
RELATIONSHIP_ID = "rel_00000000-0000-4000-8000-000000000009"
ASSET_ID = "ast_00000000-0000-4000-8000-000000000010"
ANNOTATION_ID = "ann_00000000-0000-4000-8000-000000000011"
SECTION_ID = "sec_00000000-0000-4000-8000-000000000012"
WARNING_ID = "wrn_00000000-0000-4000-8000-000000000013"


def test_document_rejects_missing_required_field(minimal_document: Document) -> None:
    payload = minimal_document.model_dump()
    del payload["document_id"]

    with pytest.raises(ValidationError, match="document_id"):
        Document.model_validate(payload)


@pytest.mark.parametrize(
    "geometry_factory",
    [
        lambda: Geometry(
            coordinate_system=CoordinateSystem.NORMALIZED_TOP_LEFT,
            x=0.8,
            y=0.1,
            width=0.3,
            height=0.2,
        ),
        lambda: Geometry(
            coordinate_system=CoordinateSystem.PDF_POINT_TOP_LEFT,
            x=-1.0,
            y=0.0,
            width=1.0,
            height=1.0,
        ),
    ],
)
def test_geometry_rejects_invalid_bounds(
    geometry_factory: Callable[[], Geometry],
) -> None:
    with pytest.raises(ValidationError):
        geometry_factory()


def test_page_rejects_source_geometry_outside_page(minimal_document: Document) -> None:
    page_payload = minimal_document.pages[0].model_dump()
    page_payload["width"] = 100.0

    with pytest.raises(ValidationError, match="Source geometry"):
        type(minimal_document.pages[0]).model_validate(page_payload)


def test_source_and_target_content_remain_separate_and_frozen(
    minimal_document: Document,
) -> None:
    source = minimal_document.pages[0].blocks[0].source_geometry
    target = Geometry(
        coordinate_system=CoordinateSystem.PDF_POINT_TOP_LEFT,
        x=75.0,
        y=125.0,
        width=320.0,
        height=45.0,
    )
    segment = Segment(
        segment_id=SEGMENT_ID,
        block_id=BLOCK_ID,
        segment_order=0,
        source_text="Original text",
        normalized_source_text="Original text",
        machine_translation="Teks mesin",
        reviewed_translation="Teks ulasan",
        final_text="Teks ulasan",
        status=SegmentStatus.APPROVED,
    )
    block_payload = minimal_document.pages[0].blocks[0].model_dump()
    block_payload.update(target_geometry=target, segments=(segment,))
    block = Block.model_validate(block_payload)

    assert block.source_geometry == source
    assert block.target_geometry == target
    assert block.segments[0].source_text == "Original text"
    assert block.segments[0].final_text == "Teks ulasan"
    with pytest.raises(ValidationError, match="frozen"):
        cast(Any, block.segments[0]).source_text = "Changed"


def test_segment_rejects_invalid_final_text(minimal_document: Document) -> None:
    payload = minimal_document.pages[0].blocks[0].segments[0].model_dump()
    payload.update(
        machine_translation="Terjemahan benar",
        final_text="Nilai yang tidak terkait",
        status=SegmentStatus.MACHINE_TRANSLATED,
    )

    with pytest.raises(ValidationError, match="resolution rule"):
        Segment.model_validate(payload)


def test_table_rejects_cell_outside_bounds(source_geometry: Geometry) -> None:
    cell = Cell(
        cell_id=CELL_ID,
        table_id=TABLE_ID,
        row_index=0,
        column_index=0,
        row_span=2,
        source_geometry=source_geometry,
        cell_role=CellRole.DATA,
    )

    with pytest.raises(ValidationError, match="table bounds"):
        Table(
            table_id=TABLE_ID,
            block_id=BLOCK_ID,
            source_geometry=source_geometry,
            row_count=1,
            column_count=1,
            has_header_row=False,
            has_header_column=False,
            cells=(cell,),
            status=DocumentStatus.EXTRACTED,
        )


def test_document_rejects_missing_relationship_endpoint(
    minimal_document: Document,
) -> None:
    relationship = Relationship(
        relationship_id=RELATIONSHIP_ID,
        relationship_type=RelationshipType.PRECEDES,
        source_entity_id=BLOCK_ID,
        target_entity_id="seg_00000000-0000-4000-8000-000000000099",
    )
    payload = minimal_document.model_dump()
    payload["relationships"] = (relationship,)

    with pytest.raises(ValidationError, match="endpoints must exist"):
        Document.model_validate(payload)


def test_prefixed_ids_are_valid_unique_and_stable(minimal_document: Document) -> None:
    first_id = new_entity_id(EntityIdPrefix.SEGMENT)
    second_id = new_entity_id(EntityIdPrefix.SEGMENT)
    source_segment = minimal_document.pages[0].blocks[0].segments[0]
    changed_payload = source_segment.model_dump()
    changed_payload.update(
        source_text="Updated source text",
        normalized_source_text="Updated source text",
    )
    changed_segment = Segment.model_validate(changed_payload)

    assert first_id.startswith("seg_")
    assert first_id != second_id
    assert changed_segment.segment_id == source_segment.segment_id


def test_identifier_rejects_wrong_prefix(minimal_document: Document) -> None:
    payload = minimal_document.pages[0].blocks[0].segments[0].model_dump()
    payload["segment_id"] = PAGE_ID

    with pytest.raises(ValidationError, match="segment_id"):
        Segment.model_validate(payload)


def test_document_graph_accepts_all_required_entity_types(
    minimal_document: Document,
    source_geometry: Geometry,
) -> None:
    cell = Cell(
        cell_id=CELL_ID,
        table_id=TABLE_ID,
        row_index=0,
        column_index=0,
        source_geometry=source_geometry,
        cell_role=CellRole.DATA,
        segment_ids=(SEGMENT_ID,),
    )
    table = Table(
        table_id=TABLE_ID,
        block_id=BLOCK_ID,
        source_geometry=source_geometry,
        row_count=1,
        column_count=1,
        has_header_row=False,
        has_header_column=False,
        cells=(cell,),
        status=DocumentStatus.EXTRACTED,
    )
    asset = Asset(
        asset_id=ASSET_ID,
        page_id=PAGE_ID,
        asset_type=AssetType.RASTER_IMAGE,
        source_geometry=source_geometry,
        storage_key="assets/image.png",
        mime_type="image/png",
        checksum_sha256="a" * 64,
    )
    annotation = Annotation(
        annotation_id=ANNOTATION_ID,
        page_id=PAGE_ID,
        annotation_type=AnnotationType.HYPERLINK,
        source_geometry=source_geometry,
        target="https://example.com",
        preserve=True,
    )
    page_payload = minimal_document.pages[0].model_dump()
    page_payload.update(tables=(table,), assets=(asset,), annotations=(annotation,))
    page = Page.model_validate(page_payload)
    section = Section(
        section_id=SECTION_ID,
        document_id=DOCUMENT_ID,
        section_type=SectionType.SECTION,
        title_segment_id=SEGMENT_ID,
        level=1,
        order=0,
        start_page_id=PAGE_ID,
        end_page_id=PAGE_ID,
        block_ids=(BLOCK_ID,),
    )
    relationship = Relationship(
        relationship_id=RELATIONSHIP_ID,
        relationship_type=RelationshipType.CAPTION_OF,
        source_entity_id=BLOCK_ID,
        target_entity_id=ASSET_ID,
    )
    warning = Warning(
        warning_id=WARNING_ID,
        scope_type="DOCUMENT",
        scope_id=DOCUMENT_ID,
        warning_type=WarningType.READING_ORDER_UNCERTAIN,
        severity=WarningSeverity.LOW,
        message="Reading order needs review.",
        status=WarningStatus.OPEN,
        created_by="SYSTEM",
        created_at=minimal_document.created_at,
    )
    document_payload = minimal_document.model_dump()
    document_payload.update(
        pages=(page,),
        sections=(section,),
        relationships=(relationship,),
        warnings=(warning,),
    )

    complete_document = Document.model_validate(document_payload)

    assert complete_document.sections == (section,)
    assert complete_document.pages[0].tables == (table,)
    assert complete_document.pages[0].assets == (asset,)
    assert complete_document.pages[0].annotations == (annotation,)
    assert complete_document.relationships == (relationship,)
    assert complete_document.warnings == (warning,)
