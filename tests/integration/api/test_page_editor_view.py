from collections.abc import Iterator
from pathlib import Path
from typing import cast
from uuid import UUID

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session, sessionmaker
from transloka_api.app import create_app
from transloka_api.middleware import (
    CLIENT_HEADER,
    CLIENT_HEADER_VALUE,
    CLIENT_VERSION_HEADER,
    CLIENT_VERSION_VALUE,
    REQUEST_ID_HEADER,
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
from transloka_core.database.models.documents import (
    Document,
    DocumentClass,
    DocumentStatus,
)
from transloka_core.database.models.files import FileRole, FileStatus, StoredFile
from transloka_core.database.models.pages import DocumentPage, PageType
from transloka_core.database.models.projects import DocumentType

REPOSITORY_ROOT = Path(__file__).parents[3]
ALEMBIC_CONFIGURATION = REPOSITORY_ROOT / "alembic.ini"
CLIENT_HEADERS = {
    CLIENT_HEADER: CLIENT_HEADER_VALUE,
    CLIENT_VERSION_HEADER: CLIENT_VERSION_VALUE,
}
CREATED_AT = "2026-08-11T00:00:00.000Z"
SOURCE_GEOMETRY = (
    '{"coordinate_system":"PDF_POINT_TOP_LEFT","x":72.0,"y":120.0,"width":200.0,"height":40.0}'
)
TARGET_GEOMETRY = (
    '{"coordinate_system":"PDF_POINT_TOP_LEFT","x":72.0,"y":120.0,"width":220.0,"height":44.0}'
)


def _id(prefix: str, value: int) -> str:
    return f"{prefix}{UUID(int=value)}"


ORIGINAL_FILE_ID = _id("fil_", 2)
DOCUMENT_ID = _id("doc_", 3)
PAGE_ID = _id("pag_", 4)
RENDER_FILE_ID = _id("fil_", 5)
THUMBNAIL_FILE_ID = _id("fil_", 6)
EARLY_BLOCK_ID = _id("blk_", 7)
LATE_BLOCK_ID = _id("blk_", 8)
EARLY_SEGMENT_ID = _id("seg_", 9)
LATE_SEGMENT_FIRST_ID = _id("seg_", 10)
LATE_SEGMENT_SECOND_ID = _id("seg_", 11)


@pytest.fixture
def page_editor_api(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> Iterator[tuple[TestClient, Path]]:
    data_root = tmp_path / "private page editor data"
    monkeypatch.setenv("TRANSLOKA_DATA_DIR", str(data_root))
    command.upgrade(Config(str(ALEMBIC_CONFIGURATION)), "head")
    application = create_app()

    with TestClient(application) as client:
        project_response = client.post(
            "/api/v1/projects",
            headers=CLIENT_HEADERS,
            json={
                "name": "Page Editor Project",
                "description": None,
                "source_language": "en",
                "target_language": "id",
                "document_type": "TECHNICAL_BOOK",
                "translation_style": "PROFESSIONAL",
                "reconstruction_mode": "HYBRID",
            },
        )
        assert project_response.status_code == 201
        project_id = cast(str, project_response.json()["data"]["id"])
        factory = cast(sessionmaker[Session], application.state.session_factory)
        _seed_editor_view(factory, project_id, data_root)
        yield client, data_root


def _stored_file(
    *,
    file_id: str,
    project_id: str,
    role: FileRole,
    storage_key: str,
) -> StoredFile:
    return StoredFile(
        id=file_id,
        project_id=project_id,
        document_id=DOCUMENT_ID if role is not FileRole.ORIGINAL else None,
        file_role=role.value,
        storage_key=storage_key,
        original_filename="private-source.pdf" if role is FileRole.ORIGINAL else None,
        safe_filename=storage_key.rsplit("/", maxsplit=1)[-1],
        mime_type="application/pdf" if role is FileRole.ORIGINAL else "image/webp",
        size_bytes=100,
        checksum_sha256=f"{file_id[-1]}" * 64,
        is_immutable=1,
        status=FileStatus.AVAILABLE.value,
        metadata_json=None,
        created_at=CREATED_AT,
        deleted_at=None,
    )


def _seed_editor_view(
    factory: sessionmaker[Session],
    project_id: str,
    data_root: Path,
) -> None:
    with transaction_scope(factory) as session:
        session.add(
            _stored_file(
                file_id=ORIGINAL_FILE_ID,
                project_id=project_id,
                role=FileRole.ORIGINAL,
                storage_key=f"projects/{project_id}/original/private-source.pdf",
            )
        )
        session.flush()
        session.add(
            Document(
                id=DOCUMENT_ID,
                project_id=project_id,
                original_file_id=ORIGINAL_FILE_ID,
                ir_version="0.1",
                title="Editor document",
                author=None,
                document_type=DocumentType.TECHNICAL_BOOK.value,
                document_class=DocumentClass.DIGITAL_PDF.value,
                source_language="en",
                target_language="id",
                page_count=1,
                word_count_estimate=8,
                has_text_layer=1,
                scanned_page_count=0,
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
        session.add_all(
            (
                _stored_file(
                    file_id=RENDER_FILE_ID,
                    project_id=project_id,
                    role=FileRole.PAGE_RENDER,
                    storage_key=f"projects/{project_id}/renders/page-1.webp",
                ),
                _stored_file(
                    file_id=THUMBNAIL_FILE_ID,
                    project_id=project_id,
                    role=FileRole.THUMBNAIL,
                    storage_key=f"projects/{project_id}/thumbnails/page-1.webp",
                ),
            )
        )
        session.flush()
        session.add(
            DocumentPage(
                id=PAGE_ID,
                document_id=DOCUMENT_ID,
                source_page_number=1,
                logical_page_number="i",
                width_points=595.28,
                height_points=841.89,
                rotation_degrees=0.0,
                page_type=PageType.DIGITAL.value,
                page_classification="SINGLE_COLUMN",
                column_count=1,
                reading_direction="LTR",
                status=DocumentStatus.STRUCTURED.value,
                render_file_id=RENDER_FILE_ID,
                thumbnail_file_id=THUMBNAIL_FILE_ID,
                native_extraction_confidence=0.99,
                ocr_confidence=None,
                structure_confidence=0.95,
                metadata_json=f'{{"private_path":"{data_root.as_posix()}"}}',
                created_at=CREATED_AT,
                updated_at=CREATED_AT,
            )
        )
        session.flush()
        session.add_all(
            (
                _block(
                    block_id=LATE_BLOCK_ID,
                    page_order=1,
                    global_order=11,
                    text="Second block.",
                ),
                _block(
                    block_id=EARLY_BLOCK_ID,
                    page_order=0,
                    global_order=10,
                    text="First block.",
                ),
            )
        )
        session.flush()
        session.add_all(
            (
                _segment(
                    segment_id=LATE_SEGMENT_SECOND_ID,
                    block_id=LATE_BLOCK_ID,
                    segment_order=1,
                    global_order=12,
                    text="Second late segment.",
                ),
                _segment(
                    segment_id=EARLY_SEGMENT_ID,
                    block_id=EARLY_BLOCK_ID,
                    segment_order=0,
                    global_order=10,
                    text="Early segment.",
                ),
                _segment(
                    segment_id=LATE_SEGMENT_FIRST_ID,
                    block_id=LATE_BLOCK_ID,
                    segment_order=0,
                    global_order=11,
                    text="First late segment.",
                ),
            )
        )


def _block(
    *,
    block_id: str,
    page_order: int,
    global_order: int,
    text: str,
) -> DocumentBlock:
    return DocumentBlock(
        id=block_id,
        page_id=PAGE_ID,
        section_id=None,
        parent_block_id=None,
        block_type=BlockType.PARAGRAPH.value,
        semantic_role=SemanticRole.BODY_TEXT.value,
        page_reading_order=page_order,
        global_reading_order=global_order,
        source_text=text,
        normalized_source_text=text,
        source_geometry_json=SOURCE_GEOMETRY,
        target_geometry_json=TARGET_GEOMETRY,
        style_json=None,
        detail_json=None,
        status=DocumentStatus.READY_FOR_TRANSLATION.value,
        confidence=0.98,
        created_at=CREATED_AT,
        updated_at=CREATED_AT,
    )


def _segment(
    *,
    segment_id: str,
    block_id: str,
    segment_order: int,
    global_order: int,
    text: str,
) -> DocumentSegment:
    return DocumentSegment(
        id=segment_id,
        block_id=block_id,
        section_id=None,
        segment_order=segment_order,
        global_order=global_order,
        source_text=text,
        native_text=text,
        ocr_text=None,
        resolved_source_text=text,
        normalized_source_text=text,
        protected_source_text=None,
        machine_translation=f"Terjemahan: {text}",
        reviewed_translation=None,
        final_text=f"Terjemahan: {text}",
        source_language="en",
        target_language="id",
        status=SegmentStatus.MACHINE_TRANSLATED.value,
        review_status=ReviewStatus.NOT_REVIEWED.value,
        is_locked=0,
        current_revision=1,
        confidence_overall=0.96,
        confidence_json=None,
        translation_settings_hash=None,
        created_at=CREATED_AT,
        updated_at=CREATED_AT,
    )


def test_page_editor_view_returns_complete_page_model_in_one_request(
    page_editor_api: tuple[TestClient, Path],
) -> None:
    client, _data_root = page_editor_api

    response = client.get(
        f"/api/v1/pages/{PAGE_ID}/editor-view",
        headers={REQUEST_ID_HEADER: "page-editor-view"},
    )

    assert response.status_code == 200
    assert response.json()["meta"] == {"request_id": "page-editor-view"}
    data = response.json()["data"]
    assert data["page"] == {
        "id": PAGE_ID,
        "document_id": DOCUMENT_ID,
        "source_page_number": 1,
        "logical_page_number": "i",
        "width_points": 595.28,
        "height_points": 841.89,
        "rotation_degrees": 0.0,
        "page_type": "DIGITAL",
        "page_classification": "SINGLE_COLUMN",
        "column_count": 1,
        "reading_direction": "LTR",
        "status": "STRUCTURED",
        "confidence": {"native_extraction": 0.99, "ocr": None, "structure": 0.95},
        "preview": {
            "thumbnail_url": f"/api/v1/pages/{PAGE_ID}/thumbnail",
            "render_url": f"/api/v1/pages/{PAGE_ID}/render",
        },
    }
    assert len(data["blocks"]) == 2
    assert len(data["segments"]) == 3
    assert data["warnings"] == []
    assert data["blocks"][0]["source_geometry"] == {
        "coordinate_system": "PDF_POINT_TOP_LEFT",
        "x": 72.0,
        "y": 120.0,
        "width": 200.0,
        "height": 40.0,
    }
    assert data["segments"][0]["warning_count"] == 0


def test_page_editor_view_returns_stable_block_and_segment_order(
    page_editor_api: tuple[TestClient, Path],
) -> None:
    client, _data_root = page_editor_api

    response = client.get(f"/api/v1/pages/{PAGE_ID}/editor-view")

    assert response.status_code == 200
    data = response.json()["data"]
    assert [block["id"] for block in data["blocks"]] == [EARLY_BLOCK_ID, LATE_BLOCK_ID]
    assert [segment["id"] for segment in data["segments"]] == [
        EARLY_SEGMENT_ID,
        LATE_SEGMENT_FIRST_ID,
        LATE_SEGMENT_SECOND_ID,
    ]


def test_page_editor_view_does_not_expose_paths_or_file_records(
    page_editor_api: tuple[TestClient, Path],
) -> None:
    client, data_root = page_editor_api

    response = client.get(f"/api/v1/pages/{PAGE_ID}/editor-view")

    assert response.status_code == 200
    for private_value in (
        str(data_root),
        data_root.as_posix(),
        "private-source.pdf",
        "projects/",
        ORIGINAL_FILE_ID,
        RENDER_FILE_ID,
        THUMBNAIL_FILE_ID,
    ):
        assert private_value not in response.text


def test_page_editor_view_returns_normalized_error_for_missing_page(
    page_editor_api: tuple[TestClient, Path],
) -> None:
    client, _data_root = page_editor_api
    missing_page_id = _id("pag_", 999)

    response = client.get(f"/api/v1/pages/{missing_page_id}/editor-view")

    assert response.status_code == 404
    error = response.json()["error"]
    assert error["code"] == "PAGE_NOT_FOUND"
    assert error["message"] == "The requested page was not found."
    assert error["details"] == {}
    assert error["request_id"]


def test_page_editor_view_is_registered_with_stable_openapi_contract() -> None:
    schema = create_app().openapi()
    operation = schema["paths"]["/api/v1/pages/{page_id}/editor-view"]["get"]

    assert operation["operationId"] == "get_page_editor_view"
    assert set(operation["responses"]) >= {"200", "403", "404", "500"}
