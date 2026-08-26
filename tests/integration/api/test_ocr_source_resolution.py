import json
from collections.abc import Iterator
from pathlib import Path
from typing import cast
from uuid import UUID

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker
from transloka_api.app import create_app
from transloka_api.middleware import (
    CLIENT_HEADER,
    CLIENT_HEADER_VALUE,
    CLIENT_VERSION_HEADER,
    CLIENT_VERSION_VALUE,
    REQUEST_ID_HEADER,
)
from transloka_api.services.source_resolution import (
    ResolveSource,
    SourceResolutionService,
)
from transloka_core.database import transaction_scope
from transloka_core.database.models.document_ir import (
    BlockType,
    DocumentBlock,
    DocumentSegment,
    ReviewStatus,
    SegmentStatus,
    SemanticRole,
)
from transloka_core.database.models.documents import Document, DocumentClass, DocumentStatus
from transloka_core.database.models.files import FileRole, FileStatus, StoredFile
from transloka_core.database.models.pages import DocumentPage, PageType
from transloka_core.database.models.projects import DocumentType
from transloka_core.database.models.revisions import SegmentRevision
from transloka_core.storage import resolve_local_data_directories


def _id(prefix: str, value: int) -> str:
    return f"{prefix}{UUID(int=value)}"


REPOSITORY_ROOT = Path(__file__).parents[3]
ALEMBIC_CONFIGURATION = REPOSITORY_ROOT / "alembic.ini"
CREATED_AT = "2026-08-20T00:00:00.000Z"
DOCUMENT_ID = _id("doc_", 2)
PAGE_ID = _id("pag_", 3)
FILE_ID = _id("fil_", 4)
BLOCK_ID = _id("blk_", 5)
SEGMENT_ID = _id("seg_", 6)
CLIENT_HEADERS = {
    CLIENT_HEADER: CLIENT_HEADER_VALUE,
    CLIENT_VERSION_HEADER: CLIENT_VERSION_VALUE,
}


@pytest.fixture
def ocr_api(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> Iterator[tuple[TestClient, Path]]:
    data_root = tmp_path / "ocr source resolution data"
    monkeypatch.setenv("TRANSLOKA_DATA_DIR", str(data_root))
    command.upgrade(Config(str(ALEMBIC_CONFIGURATION)), "head")
    application = create_app()

    with TestClient(application) as client:
        project_response = client.post(
            "/api/v1/projects",
            headers=CLIENT_HEADERS,
            json={
                "name": "OCR Source Resolution",
                "description": None,
                "source_language": "en",
                "target_language": "id",
                "document_type": "TECHNICAL_BOOK",
                "translation_style": "PROFESSIONAL",
                "reconstruction_mode": "HYBRID",
            },
        )
        assert project_response.status_code == 201, project_response.text
        project_id = cast(str, project_response.json()["data"]["id"])
        factory = cast(sessionmaker[Session], application.state.session_factory)
        _seed_ocr_segment(factory, project_id)
        yield client, data_root


def _seed_ocr_segment(factory: sessionmaker[Session], project_id: str) -> None:
    with transaction_scope(factory) as session:
        session.add(
            StoredFile(
                id=FILE_ID,
                project_id=project_id,
                document_id=None,
                file_role=FileRole.ORIGINAL.value,
                storage_key=f"projects/{project_id}/original/source.pdf",
                original_filename="source.pdf",
                safe_filename="source.pdf",
                mime_type="application/pdf",
                size_bytes=10,
                checksum_sha256="a" * 64,
                is_immutable=1,
                status=FileStatus.AVAILABLE.value,
                metadata_json=None,
                created_at=CREATED_AT,
                deleted_at=None,
            )
        )
        session.flush()
        session.add(
            Document(
                id=DOCUMENT_ID,
                project_id=project_id,
                original_file_id=FILE_ID,
                ir_version="0.1",
                title="OCR document",
                author=None,
                document_type=DocumentType.TECHNICAL_BOOK.value,
                document_class=DocumentClass.SCANNED_PDF.value,
                source_language="en",
                target_language="id",
                page_count=1,
                word_count_estimate=3,
                has_text_layer=0,
                scanned_page_count=1,
                image_count=0,
                table_count=0,
                status=DocumentStatus.STRUCTURED.value,
                metadata_json=None,
                analysis_json=None,
                created_at=CREATED_AT,
                updated_at=CREATED_AT,
            )
        )
        session.flush()
        session.add(
            DocumentPage(
                id=PAGE_ID,
                document_id=DOCUMENT_ID,
                source_page_number=1,
                logical_page_number="1",
                width_points=595.28,
                height_points=841.89,
                rotation_degrees=0.0,
                page_type=PageType.SCANNED.value,
                page_classification="SINGLE_COLUMN",
                column_count=1,
                reading_direction="LTR",
                status=DocumentStatus.STRUCTURED.value,
                render_file_id=None,
                thumbnail_file_id=None,
                native_extraction_confidence=None,
                ocr_confidence=0.61,
                structure_confidence=0.70,
                metadata_json=None,
                created_at=CREATED_AT,
                updated_at=CREATED_AT,
            )
        )
        session.flush()
        session.add(
            DocumentBlock(
                id=BLOCK_ID,
                page_id=PAGE_ID,
                section_id=None,
                parent_block_id=None,
                block_type=BlockType.PARAGRAPH.value,
                semantic_role=SemanticRole.BODY_TEXT.value,
                page_reading_order=0,
                global_reading_order=0,
                source_text="Raw OCR text",
                normalized_source_text="Raw OCR text",
                source_geometry_json=(
                    '{"coordinate_system":"PIXEL_TOP_LEFT","x":1.0,"y":2.0,'
                    '"width":100.0,"height":20.0}'
                ),
                target_geometry_json=None,
                style_json=None,
                detail_json=None,
                status=DocumentStatus.READY_FOR_TRANSLATION.value,
                confidence=0.61,
                created_at=CREATED_AT,
                updated_at=CREATED_AT,
            )
        )
        session.flush()
        session.add(
            DocumentSegment(
                id=SEGMENT_ID,
                block_id=BLOCK_ID,
                section_id=None,
                segment_order=0,
                global_order=0,
                source_text="Raw OCR text",
                native_text=None,
                ocr_text="Raw   OCR text",
                resolved_source_text="Raw OCR text",
                normalized_source_text="Raw OCR text",
                protected_source_text="protected source",
                machine_translation="Terjemahan lama",
                reviewed_translation="Terjemahan ditinjau",
                final_text="Terjemahan ditinjau",
                source_language="en",
                target_language="id",
                status=SegmentStatus.MACHINE_TRANSLATED.value,
                review_status=ReviewStatus.EDITED.value,
                is_locked=0,
                current_revision=1,
                confidence_overall=0.61,
                confidence_json=None,
                translation_settings_hash="settings-hash",
                created_at=CREATED_AT,
                updated_at=CREATED_AT,
            )
        )


def _factory(data_root: Path) -> sessionmaker[Session]:
    from transloka_core.database import create_session_factory, create_sqlite_engine

    engine = create_sqlite_engine(resolve_local_data_directories(data_root))
    factory = create_session_factory(engine)
    engine.dispose()
    return factory


def test_get_page_ocr_exposes_raw_and_resolved_source(ocr_api: tuple[TestClient, Path]) -> None:
    client, _data_root = ocr_api

    response = client.get(
        f"/api/v1/pages/{PAGE_ID}/ocr",
        headers={**CLIENT_HEADERS, REQUEST_ID_HEADER: "ocr-read"},
    )

    assert response.status_code == 200, response.text
    assert response.headers[REQUEST_ID_HEADER] == "ocr-read"
    data = response.json()["data"]
    assert data["raw_text"] == "Raw   OCR text"
    assert data["resolved_source_text"] == "Raw OCR text"
    assert data["ocr_confidence"] == 0.61
    assert data["segments"][0]["raw_ocr_text"] == "Raw   OCR text"
    assert data["segments"][0]["resolved_source_text"] == "Raw OCR text"


def test_source_correction_creates_revision_and_invalidates_translation(
    ocr_api: tuple[TestClient, Path],
) -> None:
    client, data_root = ocr_api

    response = client.patch(
        f"/api/v1/segments/{SEGMENT_ID}/source-resolution",
        headers={**CLIENT_HEADERS, REQUEST_ID_HEADER: "ocr-correction"},
        json={
            "resolved_source_text": "Corrected   OCR source.",
            "resolution_source": "MANUAL",
            "expected_revision": 1,
            "reason": "Fixed OCR spelling.",
        },
    )

    assert response.status_code == 200, response.text
    assert response.headers[REQUEST_ID_HEADER] == "ocr-correction"
    data = response.json()["data"]
    assert data["raw_ocr_text"] == "Raw   OCR text"
    assert data["resolved_source_text"] == "Corrected   OCR source."
    assert data["normalized_source_text"] == "Corrected OCR source."
    assert data["machine_translation"] is None
    assert data["reviewed_translation"] is None
    assert data["final_text"] is None
    assert data["status"] == "READY_FOR_TRANSLATION"
    assert data["review_status"] == "NOT_REVIEWED"
    assert data["current_revision"] == 2
    assert data["resolution_source"] == "MANUAL"

    factory = _factory(data_root)
    with factory() as session:
        segment = session.get(DocumentSegment, SEGMENT_ID)
        assert segment is not None
        assert segment.ocr_text == "Raw   OCR text"
        assert segment.source_text == "Raw OCR text"
        assert segment.current_revision == 2
        revision = session.scalar(
            select(SegmentRevision).where(
                SegmentRevision.segment_id == SEGMENT_ID,
                SegmentRevision.revision_number == 2,
            )
        )
        assert revision is not None
        assert revision.revision_type == "USER_EDIT"
        assert revision.previous_text == "Raw OCR text"
        assert revision.new_text == "Corrected   OCR source."
        assert revision.reason == "Fixed OCR spelling."
        assert json.loads(cast(str, revision.metadata_json)) == {
            "event": "SOURCE_CORRECTION",
            "raw_ocr_preserved": True,
            "resolution_source": "MANUAL",
            "translation_invalidated": True,
        }


def test_source_correction_rejects_stale_revision(ocr_api: tuple[TestClient, Path]) -> None:
    client, _data_root = ocr_api
    first = client.patch(
        f"/api/v1/segments/{SEGMENT_ID}/source-resolution",
        headers=CLIENT_HEADERS,
        json={"resolved_source_text": "First correction", "expected_revision": 1},
    )
    stale = client.patch(
        f"/api/v1/segments/{SEGMENT_ID}/source-resolution",
        headers=CLIENT_HEADERS,
        json={"resolved_source_text": "Stale correction", "expected_revision": 1},
    )

    assert first.status_code == 200
    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "REVISION_CONFLICT"
    assert stale.json()["error"]["details"] == {
        "expected_revision": 1,
        "current_revision": 2,
    }


def test_source_correction_rejects_locked_segment(ocr_api: tuple[TestClient, Path]) -> None:
    _client, data_root = ocr_api
    factory = _factory(data_root)
    with transaction_scope(factory) as session:
        segment = session.get(DocumentSegment, SEGMENT_ID)
        assert segment is not None
        segment.is_locked = 1
        segment.status = SegmentStatus.LOCKED.value

    client, _data_root = ocr_api
    response = client.patch(
        f"/api/v1/segments/{SEGMENT_ID}/source-resolution",
        headers=CLIENT_HEADERS,
        json={"resolved_source_text": "Blocked correction", "expected_revision": 1},
    )

    assert response.status_code == 423
    assert response.json()["error"]["code"] == "SEGMENT_LOCKED"


def test_source_resolution_service_invokes_translation_invalidator(
    ocr_api: tuple[TestClient, Path],
) -> None:
    _client, data_root = ocr_api
    invalidated: list[str] = []
    factory = _factory(data_root)
    with transaction_scope(factory) as session:
        updated = SourceResolutionService(
            session,
            invalidate_translation=invalidated.append,
        ).resolve(
            SEGMENT_ID,
            ResolveSource(
                resolved_source_text="Callback correction",
                expected_revision=1,
            ),
        )
        assert updated.current_revision == 2

    assert invalidated == [SEGMENT_ID]
