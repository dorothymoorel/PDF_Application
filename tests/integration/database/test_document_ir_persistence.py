import os
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path
from uuid import UUID

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, func, inspect, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker
from transloka_core.database import (
    create_session_factory,
    create_sqlite_engine,
    transaction_scope,
)
from transloka_core.database.models.document_ir import (
    AnnotationType,
    AssetPreservationPolicy,
    AssetType,
    BlockType,
    CellRole,
    DocumentAnnotation,
    DocumentAsset,
    DocumentBlock,
    DocumentRelationship,
    DocumentSection,
    DocumentSegment,
    DocumentTable,
    DocumentTableCell,
    RelationshipType,
    ReviewStatus,
    SectionType,
    SegmentStatus,
    SemanticRole,
    TableComplexity,
)
from transloka_core.database.models.documents import (
    Document,
    DocumentClass,
    DocumentStatus,
)
from transloka_core.database.models.files import FileRole, FileStatus
from transloka_core.database.models.pages import DocumentPage, PageType
from transloka_core.database.models.projects import (
    DocumentType,
    ReconstructionMode,
    TranslationStyle,
)
from transloka_core.repositories.files import StoredFilesRepository
from transloka_core.repositories.projects import ProjectsRepository
from transloka_core.storage import resolve_local_data_directories

REPOSITORY_ROOT = Path(__file__).parents[3]
ALEMBIC_CONFIGURATION = REPOSITORY_ROOT / "alembic.ini"
PARENT_REVISION = "0007_document_pages"
CREATED_AT = "2026-08-10T00:00:00.000Z"
SOURCE_GEOMETRY = (
    '{"coordinate_system":"PDF_POINT_TOP_LEFT","x":72.0,"y":120.0,"width":200.0,"height":40.0}'
)
TARGET_GEOMETRY = (
    '{"coordinate_system":"PDF_POINT_TOP_LEFT","x":72.0,"y":120.0,"width":220.0,"height":44.0}'
)


def _id(prefix: str, value: int) -> str:
    return f"{prefix}{UUID(int=value)}"


PROJECT_ID = _id("prj_", 1)
ORIGINAL_FILE_ID = _id("fil_", 2)
DOCUMENT_ID = _id("doc_", 3)
PAGE_ID = _id("pag_", 4)
ASSET_FILE_ID = _id("fil_", 5)
SECTION_ID = _id("sec_", 6)
BLOCK_ID = _id("blk_", 7)
SEGMENT_ID = _id("seg_", 8)
ASSET_ID = _id("ast_", 9)
TABLE_ID = _id("tbl_", 10)
CELL_ID = _id("cel_", 11)
ANNOTATION_ID = _id("ann_", 12)
RELATIONSHIP_ID = _id("rel_", 13)

IR_TABLES = {
    "document_annotations",
    "document_assets",
    "document_blocks",
    "document_relationships",
    "document_sections",
    "document_segments",
    "document_table_cells",
    "document_tables",
}


@pytest.fixture
def ir_database(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> Iterator[tuple[Path, Engine, sessionmaker[Session]]]:
    root = tmp_path / "Document IR Data_日本語"
    monkeypatch.setenv("TRANSLOKA_DATA_DIR", str(root))
    command.upgrade(Config(str(ALEMBIC_CONFIGURATION)), "head")
    engine = create_sqlite_engine(resolve_local_data_directories(root))
    factory = create_session_factory(engine)
    with transaction_scope(factory) as session:
        ProjectsRepository(session).create(
            project_id=PROJECT_ID,
            name="Document IR Project",
            description=None,
            source_language="en",
            target_language="id",
            document_type=DocumentType.TECHNICAL_BOOK,
            translation_style=TranslationStyle.PROFESSIONAL,
            reconstruction_mode=ReconstructionMode.HYBRID,
            created_at=CREATED_AT,
        )
        repository = StoredFilesRepository(session)
        repository.create(
            file_id=ORIGINAL_FILE_ID,
            project_id=PROJECT_ID,
            document_id=None,
            file_role=FileRole.ORIGINAL,
            storage_key=f"projects/{PROJECT_ID}/original/{ORIGINAL_FILE_ID}.pdf",
            original_filename="source.pdf",
            safe_filename=f"{ORIGINAL_FILE_ID}.pdf",
            mime_type="application/pdf",
            size_bytes=100,
            checksum_sha256="a" * 64,
            is_immutable=True,
            status=FileStatus.VALIDATED,
            metadata=None,
            created_at=CREATED_AT,
        )
        session.add(
            Document(
                id=DOCUMENT_ID,
                project_id=PROJECT_ID,
                original_file_id=ORIGINAL_FILE_ID,
                ir_version="0.1",
                title="Document IR",
                author=None,
                document_type=DocumentType.TECHNICAL_BOOK.value,
                document_class=DocumentClass.DIGITAL_PDF.value,
                source_language="en",
                target_language="id",
                page_count=1,
                word_count_estimate=10,
                has_text_layer=1,
                scanned_page_count=0,
                image_count=1,
                table_count=1,
                status=DocumentStatus.STRUCTURED.value,
                metadata_json=None,
                analysis_json=None,
                created_at=CREATED_AT,
                updated_at=CREATED_AT,
            )
        )
        session.flush()
        repository.create(
            file_id=ASSET_FILE_ID,
            project_id=PROJECT_ID,
            document_id=DOCUMENT_ID,
            file_role=FileRole.EXTRACTED_ASSET,
            storage_key=f"projects/{PROJECT_ID}/assets/{ASSET_FILE_ID}.png",
            original_filename=None,
            safe_filename=f"{ASSET_FILE_ID}.png",
            mime_type="image/png",
            size_bytes=50,
            checksum_sha256="b" * 64,
            is_immutable=False,
            status=FileStatus.AVAILABLE,
            metadata=None,
            created_at=CREATED_AT,
        )
        session.add(
            DocumentPage(
                id=PAGE_ID,
                document_id=DOCUMENT_ID,
                source_page_number=1,
                logical_page_number="1",
                width_points=595.28,
                height_points=841.89,
                rotation_degrees=0.0,
                page_type=PageType.DIGITAL.value,
                page_classification="SINGLE_COLUMN",
                column_count=1,
                reading_direction="LTR",
                status=DocumentStatus.STRUCTURED.value,
                render_file_id=None,
                thumbnail_file_id=None,
                native_extraction_confidence=0.99,
                ocr_confidence=None,
                structure_confidence=0.95,
                metadata_json=None,
                created_at=CREATED_AT,
                updated_at=CREATED_AT,
            )
        )
    yield root, engine, factory
    engine.dispose()


def _section(index: int = 1, **overrides: object) -> DocumentSection:
    values: dict[str, object] = {
        "id": SECTION_ID if index == 1 else _id("sec_", 100 + index),
        "document_id": DOCUMENT_ID,
        "parent_section_id": None,
        "section_type": SectionType.SECTION.value,
        "level": 1,
        "section_order": index - 1,
        "title_segment_id": SEGMENT_ID,
        "start_page_id": PAGE_ID,
        "end_page_id": PAGE_ID,
        "source_summary": "Authentication overview",
        "context_json": '{"domain":"technical"}',
        "created_at": CREATED_AT,
        "updated_at": CREATED_AT,
    }
    values.update(overrides)
    return DocumentSection(**values)


def _block(index: int = 1, **overrides: object) -> DocumentBlock:
    values: dict[str, object] = {
        "id": BLOCK_ID if index == 1 else _id("blk_", 200 + index),
        "page_id": PAGE_ID,
        "section_id": SECTION_ID,
        "parent_block_id": None,
        "block_type": BlockType.PARAGRAPH.value,
        "semantic_role": SemanticRole.BODY_TEXT.value,
        "page_reading_order": index - 1,
        "global_reading_order": index - 1,
        "source_text": "The workflow begins after authentication.",
        "normalized_source_text": "The workflow begins after authentication.",
        "source_geometry_json": SOURCE_GEOMETRY,
        "target_geometry_json": TARGET_GEOMETRY,
        "style_json": '{"font_size":11}',
        "detail_json": '{"line_count":1}',
        "status": DocumentStatus.READY_FOR_TRANSLATION.value,
        "confidence": 0.98,
        "created_at": CREATED_AT,
        "updated_at": CREATED_AT,
    }
    values.update(overrides)
    return DocumentBlock(**values)


def _segment(index: int = 1, **overrides: object) -> DocumentSegment:
    values: dict[str, object] = {
        "id": SEGMENT_ID if index == 1 else _id("seg_", 300 + index),
        "block_id": BLOCK_ID,
        "section_id": SECTION_ID,
        "segment_order": index - 1,
        "global_order": index - 1,
        "source_text": "The workflow begins after authentication.",
        "native_text": "The workflow begins after authentication.",
        "ocr_text": None,
        "resolved_source_text": "The workflow begins after authentication.",
        "normalized_source_text": "The workflow begins after authentication.",
        "protected_source_text": "The __TERM_1__ begins after authentication.",
        "machine_translation": "Workflow dimulai setelah autentikasi.",
        "reviewed_translation": None,
        "final_text": "Workflow dimulai setelah autentikasi.",
        "source_language": "en",
        "target_language": "id",
        "status": SegmentStatus.MACHINE_TRANSLATED.value,
        "review_status": ReviewStatus.NOT_REVIEWED.value,
        "is_locked": 0,
        "current_revision": 0,
        "confidence_overall": 0.96,
        "confidence_json": '{"translation":0.96}',
        "translation_settings_hash": "settings-v1",
        "created_at": CREATED_AT,
        "updated_at": CREATED_AT,
    }
    values.update(overrides)
    return DocumentSegment(**values)


def _asset(**overrides: object) -> DocumentAsset:
    values: dict[str, object] = {
        "id": ASSET_ID,
        "document_id": DOCUMENT_ID,
        "page_id": PAGE_ID,
        "file_id": ASSET_FILE_ID,
        "asset_type": AssetType.RASTER_IMAGE.value,
        "source_geometry_json": SOURCE_GEOMETRY,
        "target_geometry_json": TARGET_GEOMETRY,
        "width_pixels": 1200,
        "height_pixels": 800,
        "dpi": 300.0,
        "rotation_degrees": 0.0,
        "z_index": 1,
        "caption_block_id": BLOCK_ID,
        "preservation_policy": AssetPreservationPolicy.KEEP_UNCHANGED.value,
        "metadata_json": '{"color_space":"RGB"}',
        "created_at": CREATED_AT,
        "updated_at": CREATED_AT,
    }
    values.update(overrides)
    return DocumentAsset(**values)


def _table(**overrides: object) -> DocumentTable:
    values: dict[str, object] = {
        "id": TABLE_ID,
        "block_id": BLOCK_ID,
        "row_count": 1,
        "column_count": 1,
        "complexity": TableComplexity.SIMPLE.value,
        "has_header_row": 0,
        "has_header_column": 0,
        "source_geometry_json": SOURCE_GEOMETRY,
        "target_geometry_json": TARGET_GEOMETRY,
        "continuation_of_table_id": None,
        "status": DocumentStatus.EXTRACTED.value,
        "confidence": 0.94,
        "metadata_json": None,
        "created_at": CREATED_AT,
        "updated_at": CREATED_AT,
    }
    values.update(overrides)
    return DocumentTable(**values)


def _cell(index: int = 1, **overrides: object) -> DocumentTableCell:
    values: dict[str, object] = {
        "id": CELL_ID if index == 1 else _id("cel_", 400 + index),
        "table_id": TABLE_ID,
        "row_index": index - 1,
        "column_index": 0,
        "row_span": 1,
        "column_span": 1,
        "cell_role": CellRole.DATA.value,
        "source_text": "Workflow",
        "segment_id": SEGMENT_ID,
        "source_geometry_json": SOURCE_GEOMETRY,
        "target_geometry_json": TARGET_GEOMETRY,
        "style_json": None,
        "created_at": CREATED_AT,
        "updated_at": CREATED_AT,
    }
    values.update(overrides)
    return DocumentTableCell(**values)


def _annotation(**overrides: object) -> DocumentAnnotation:
    values: dict[str, object] = {
        "id": ANNOTATION_ID,
        "page_id": PAGE_ID,
        "annotation_type": AnnotationType.HYPERLINK.value,
        "source_geometry_json": SOURCE_GEOMETRY,
        "target_geometry_json": TARGET_GEOMETRY,
        "visible_text": "Documentation",
        "target_value": "https://example.com",
        "preservation_policy": "KEEP_UNCHANGED",
        "status": "PRESERVED",
        "metadata_json": None,
        "created_at": CREATED_AT,
        "updated_at": CREATED_AT,
    }
    values.update(overrides)
    return DocumentAnnotation(**values)


def _relationship(**overrides: object) -> DocumentRelationship:
    values: dict[str, object] = {
        "id": RELATIONSHIP_ID,
        "document_id": DOCUMENT_ID,
        "relationship_type": RelationshipType.CAPTION_OF.value,
        "source_entity_type": "BLOCK",
        "source_entity_id": BLOCK_ID,
        "target_entity_type": "ASSET",
        "target_entity_id": ASSET_ID,
        "confidence": 0.99,
        "metadata_json": None,
        "created_at": CREATED_AT,
    }
    values.update(overrides)
    return DocumentRelationship(**values)


def _persist_ir_graph(factory: sessionmaker[Session]) -> None:
    with transaction_scope(factory) as session:
        session.add(_section())
        session.flush()
        session.add(_block())
        session.flush()
        session.add(_segment())
        session.flush()
        session.add(_asset())
        session.add(_table())
        session.flush()
        session.add(_cell())
        session.add(_annotation())
        session.add(_relationship())


def test_migration_creates_exact_strict_tables_foreign_keys_and_indexes(
    ir_database: tuple[Path, Engine, sessionmaker[Session]],
) -> None:
    _root, engine, _factory = ir_database
    database = inspect(engine)

    assert IR_TABLES <= set(database.get_table_names())
    expected_columns = {
        "document_sections": [
            "id",
            "document_id",
            "parent_section_id",
            "section_type",
            "level",
            "section_order",
            "title_segment_id",
            "start_page_id",
            "end_page_id",
            "source_summary",
            "context_json",
            "created_at",
            "updated_at",
        ],
        "document_blocks": [
            "id",
            "page_id",
            "section_id",
            "parent_block_id",
            "block_type",
            "semantic_role",
            "page_reading_order",
            "global_reading_order",
            "source_text",
            "normalized_source_text",
            "source_geometry_json",
            "target_geometry_json",
            "style_json",
            "detail_json",
            "status",
            "confidence",
            "created_at",
            "updated_at",
        ],
        "document_segments": [
            "id",
            "block_id",
            "section_id",
            "segment_order",
            "global_order",
            "source_text",
            "native_text",
            "ocr_text",
            "resolved_source_text",
            "normalized_source_text",
            "protected_source_text",
            "machine_translation",
            "reviewed_translation",
            "final_text",
            "source_language",
            "target_language",
            "status",
            "review_status",
            "is_locked",
            "current_revision",
            "confidence_overall",
            "confidence_json",
            "translation_settings_hash",
            "created_at",
            "updated_at",
        ],
        "document_assets": [
            "id",
            "document_id",
            "page_id",
            "file_id",
            "asset_type",
            "source_geometry_json",
            "target_geometry_json",
            "width_pixels",
            "height_pixels",
            "dpi",
            "rotation_degrees",
            "z_index",
            "caption_block_id",
            "preservation_policy",
            "metadata_json",
            "created_at",
            "updated_at",
        ],
        "document_tables": [
            "id",
            "block_id",
            "row_count",
            "column_count",
            "complexity",
            "has_header_row",
            "has_header_column",
            "source_geometry_json",
            "target_geometry_json",
            "continuation_of_table_id",
            "status",
            "confidence",
            "metadata_json",
            "created_at",
            "updated_at",
        ],
        "document_table_cells": [
            "id",
            "table_id",
            "row_index",
            "column_index",
            "row_span",
            "column_span",
            "cell_role",
            "source_text",
            "segment_id",
            "source_geometry_json",
            "target_geometry_json",
            "style_json",
            "created_at",
            "updated_at",
        ],
        "document_annotations": [
            "id",
            "page_id",
            "annotation_type",
            "source_geometry_json",
            "target_geometry_json",
            "visible_text",
            "target_value",
            "preservation_policy",
            "status",
            "metadata_json",
            "created_at",
            "updated_at",
        ],
        "document_relationships": [
            "id",
            "document_id",
            "relationship_type",
            "source_entity_type",
            "source_entity_id",
            "target_entity_type",
            "target_entity_id",
            "confidence",
            "metadata_json",
            "created_at",
        ],
    }
    for table_name, columns in expected_columns.items():
        assert [column["name"] for column in database.get_columns(table_name)] == columns

    expected_foreign_keys = {
        "document_sections": {
            ("document_id", "documents"),
            ("parent_section_id", "document_sections"),
        },
        "document_blocks": {
            ("page_id", "document_pages"),
            ("section_id", "document_sections"),
            ("parent_block_id", "document_blocks"),
        },
        "document_segments": {
            ("block_id", "document_blocks"),
            ("section_id", "document_sections"),
        },
        "document_assets": {
            ("document_id", "documents"),
            ("page_id", "document_pages"),
            ("file_id", "stored_files"),
        },
        "document_tables": {("block_id", "document_blocks")},
        "document_table_cells": {
            ("table_id", "document_tables"),
            ("segment_id", "document_segments"),
        },
        "document_annotations": {("page_id", "document_pages")},
        "document_relationships": {("document_id", "documents")},
    }
    for table_name, expected in expected_foreign_keys.items():
        assert {
            (foreign_key["constrained_columns"][0], foreign_key["referred_table"])
            for foreign_key in database.get_foreign_keys(table_name)
        } == expected

    assert {
        index["name"]: index["unique"] for index in database.get_indexes("document_blocks")
    } == {
        "ix_document_blocks_page_type": 0,
        "ix_document_blocks_section": 0,
        "uq_document_blocks_page_order": 1,
    }
    assert {
        index["name"]: index["unique"] for index in database.get_indexes("document_segments")
    } == {
        "ix_document_segments_block": 0,
        "ix_document_segments_review_status": 0,
        "ix_document_segments_section_order": 0,
        "ix_document_segments_status": 0,
        "uq_document_segments_block_order": 1,
    }
    assert database.get_unique_constraints("document_tables") == [
        {"name": "uq_document_tables_block", "column_names": ["block_id"]}
    ]
    with engine.connect() as connection:
        definitions = {
            str(name): str(sql)
            for name, sql in connection.exec_driver_sql(
                "SELECT name, sql FROM sqlite_master WHERE type = 'table'"
            ).tuples()
            if name in IR_TABLES
        }
    assert set(definitions) == IR_TABLES
    assert all(definition.rstrip().endswith("STRICT") for definition in definitions.values())
    assert all(
        "BLOB" not in str(column["type"]).upper()
        for table_name in IR_TABLES
        for column in database.get_columns(table_name)
    )


def test_complete_document_ir_structure_persists_source_and_target_separately(
    ir_database: tuple[Path, Engine, sessionmaker[Session]],
) -> None:
    _root, _engine, factory = ir_database
    _persist_ir_graph(factory)

    with factory() as session:
        section = session.get(DocumentSection, SECTION_ID)
        block = session.get(DocumentBlock, BLOCK_ID)
        segment = session.get(DocumentSegment, SEGMENT_ID)
        asset = session.get(DocumentAsset, ASSET_ID)
        table = session.get(DocumentTable, TABLE_ID)
        cell = session.get(DocumentTableCell, CELL_ID)
        annotation = session.get(DocumentAnnotation, ANNOTATION_ID)
        relationship = session.get(DocumentRelationship, RELATIONSHIP_ID)

    assert section is not None and section.document_id == DOCUMENT_ID
    assert block is not None and block.source_geometry_json == SOURCE_GEOMETRY
    assert block.target_geometry_json == TARGET_GEOMETRY
    assert segment is not None and segment.source_text.startswith("The workflow")
    assert segment.machine_translation == "Workflow dimulai setelah autentikasi."
    assert asset is not None and asset.file_id == ASSET_FILE_ID
    assert table is not None and (table.row_count, table.column_count) == (1, 1)
    assert cell is not None and cell.segment_id == SEGMENT_ID
    assert annotation is not None and annotation.target_value == "https://example.com"
    assert relationship is not None and relationship.target_entity_id == ASSET_ID


@pytest.mark.parametrize(
    "rows",
    (
        (_block(), _block(2, page_reading_order=0)),
        (_segment(), _segment(2, segment_order=0)),
    ),
)
def test_reading_and_segment_order_are_unique(
    rows: tuple[object, object],
    ir_database: tuple[Path, Engine, sessionmaker[Session]],
) -> None:
    _root, _engine, factory = ir_database
    with factory() as session, pytest.raises(IntegrityError):
        session.add(_section())
        session.flush()
        if isinstance(rows[0], DocumentSegment):
            session.add(_block())
            session.flush()
        session.add_all(rows)
        session.flush()


def test_table_cell_position_is_unique(
    ir_database: tuple[Path, Engine, sessionmaker[Session]],
) -> None:
    _root, _engine, factory = ir_database
    with factory() as session, pytest.raises(IntegrityError):
        session.add(_section())
        session.flush()
        session.add(_block())
        session.flush()
        session.add(_segment())
        session.flush()
        session.add(_table())
        session.flush()
        session.add_all((_cell(), _cell(2, row_index=0, column_index=0)))
        session.flush()


def test_missing_foreign_key_and_invalid_values_are_rejected(
    ir_database: tuple[Path, Engine, sessionmaker[Session]],
) -> None:
    _root, _engine, factory = ir_database
    invalid_rows = (
        _block(page_id=_id("pag_", 999)),
        _section(level=-1),
        _relationship(confidence=1.01),
        _annotation(source_geometry_json="{invalid"),
        _asset(width_pixels=-1),
    )
    for row in invalid_rows:
        with factory() as session, pytest.raises(IntegrityError):
            session.add(row)
            session.flush()


def test_document_delete_cascades_through_entire_ir_graph(
    ir_database: tuple[Path, Engine, sessionmaker[Session]],
) -> None:
    _root, _engine, factory = ir_database
    _persist_ir_graph(factory)

    with transaction_scope(factory) as session:
        document = session.get(Document, DOCUMENT_ID)
        assert document is not None
        session.delete(document)

    with factory() as session:
        assert session.get(Document, DOCUMENT_ID) is None
        assert session.get(DocumentPage, PAGE_ID) is None
        for model in (
            DocumentSection,
            DocumentBlock,
            DocumentSegment,
            DocumentAsset,
            DocumentTable,
            DocumentTableCell,
            DocumentAnnotation,
            DocumentRelationship,
        ):
            assert session.scalar(select(func.count()).select_from(model)) == 0


def test_migration_downgrades_only_document_ir_tables_and_reupgrades(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "Document IR migration"
    monkeypatch.setenv("TRANSLOKA_DATA_DIR", str(root))
    configuration = Config(str(ALEMBIC_CONFIGURATION))
    command.upgrade(configuration, "head")
    command.downgrade(configuration, PARENT_REVISION)

    engine = create_sqlite_engine(resolve_local_data_directories(root))
    try:
        tables = set(inspect(engine).get_table_names())
        assert not IR_TABLES.intersection(tables)
        assert {"documents", "document_pages", "stored_files"} <= tables
    finally:
        engine.dispose()

    command.upgrade(configuration, "head")
    command.upgrade(configuration, "head")
    engine = create_sqlite_engine(resolve_local_data_directories(root))
    try:
        assert IR_TABLES <= set(inspect(engine).get_table_names())
    finally:
        engine.dispose()


def test_document_ir_model_import_creates_no_database(tmp_path: Path) -> None:
    root = tmp_path / "document-ir-import"
    environment = os.environ.copy()
    environment["TRANSLOKA_DATA_DIR"] = str(root)

    result = subprocess.run(
        [sys.executable, "-c", "import transloka_core.database.models.document_ir"],
        cwd=REPOSITORY_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert not root.exists()
