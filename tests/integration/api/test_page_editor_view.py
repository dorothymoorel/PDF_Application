from collections.abc import Iterator
from pathlib import Path
from typing import cast
from uuid import UUID

import pytest
from alembic import command
from alembic.config import Config
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session, sessionmaker
from transloka_api.app import create_app
from transloka_api.middleware import (
    CLIENT_HEADER,
    CLIENT_HEADER_VALUE,
    CLIENT_VERSION_HEADER,
    CLIENT_VERSION_VALUE,
    REQUEST_ID_HEADER,
)
from transloka_api.services.segments import (
    EmptyUnlockReasonError,
    LockSegment,
    SegmentLockStateError,
    SegmentRevisionConflictError,
    SegmentService,
    UnlockSegment,
)
from transloka_core.database import (
    create_session_factory,
    create_sqlite_engine,
    transaction_scope,
)
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
from transloka_core.database.models.jobs import ApplicationJob
from transloka_core.database.models.pages import DocumentPage, PageType
from transloka_core.database.models.projects import DocumentType
from transloka_core.database.models.revisions import SegmentRevision
from transloka_core.storage import resolve_local_data_directories

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


class RecordingQueue:
    name = "translation"

    def enqueue(self, _job_id: str) -> None:
        pass


@pytest.fixture
def page_editor_api(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> Iterator[tuple[TestClient, Path]]:
    data_root = tmp_path / "private page editor data"
    monkeypatch.setenv("TRANSLOKA_DATA_DIR", str(data_root))
    command.upgrade(Config(str(ALEMBIC_CONFIGURATION)), "head")
    application = create_app()
    application.state.translation_queue = RecordingQueue()

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


def _database_factory(data_root: Path) -> tuple[Engine, sessionmaker[Session]]:
    engine = create_sqlite_engine(resolve_local_data_directories(data_root))
    return engine, create_session_factory(engine)


def test_segment_translation_edit_updates_final_text_and_creates_revision(
    page_editor_api: tuple[TestClient, Path],
) -> None:
    client, data_root = page_editor_api
    response = client.patch(
        f"/api/v1/segments/{EARLY_SEGMENT_ID}/translation",
        headers={**CLIENT_HEADERS, REQUEST_ID_HEADER: "segment-edit"},
        json={
            "reviewed_translation": "Terjemahan final yang ditinjau.",
            "expected_revision": 1,
            "reason": "Improved naturalness.",
        },
    )

    assert response.status_code == 200, response.text
    assert response.headers[REQUEST_ID_HEADER] == "segment-edit"
    data = response.json()["data"]
    assert data["reviewed_translation"] == "Terjemahan final yang ditinjau."
    assert data["final_text"] == "Terjemahan final yang ditinjau."
    assert data["status"] == "USER_EDITED"
    assert data["review_status"] == "EDITED"
    assert data["current_revision"] == 2

    engine, factory = _database_factory(data_root)
    try:
        with factory() as session:
            revision = session.scalar(
                select(SegmentRevision).where(
                    SegmentRevision.segment_id == EARLY_SEGMENT_ID,
                    SegmentRevision.revision_number == 2,
                )
            )
            assert revision is not None
            assert revision.previous_text == "Terjemahan: Early segment."
            assert revision.new_text == "Terjemahan final yang ditinjau."
            assert revision.reason == "Improved naturalness."
    finally:
        engine.dispose()


def test_segment_translation_edit_rejects_stale_revision(
    page_editor_api: tuple[TestClient, Path],
) -> None:
    client, _data_root = page_editor_api
    first = client.patch(
        f"/api/v1/segments/{EARLY_SEGMENT_ID}/translation",
        headers=CLIENT_HEADERS,
        json={"reviewed_translation": "First edit", "expected_revision": 1},
    )
    stale = client.patch(
        f"/api/v1/segments/{EARLY_SEGMENT_ID}/translation",
        headers=CLIENT_HEADERS,
        json={"reviewed_translation": "Stale edit", "expected_revision": 1},
    )

    assert first.status_code == 200
    assert stale.status_code == 409
    assert stale.json()["error"]["code"] == "REVISION_CONFLICT"
    assert stale.json()["error"]["details"] == {
        "expected_revision": 1,
        "current_revision": 2,
    }


def test_segment_translation_edit_rejects_locked_segment(
    page_editor_api: tuple[TestClient, Path],
) -> None:
    client, data_root = page_editor_api
    engine, factory = _database_factory(data_root)
    try:
        with transaction_scope(factory) as session:
            row = session.get(DocumentSegment, EARLY_SEGMENT_ID)
            assert row is not None
            row.is_locked = 1
            row.status = SegmentStatus.LOCKED.value
    finally:
        engine.dispose()

    response = client.patch(
        f"/api/v1/segments/{EARLY_SEGMENT_ID}/translation",
        headers=CLIENT_HEADERS,
        json={"reviewed_translation": "Blocked edit", "expected_revision": 1},
    )

    assert response.status_code == 423
    assert response.json()["error"]["code"] == "SEGMENT_LOCKED"


def test_segment_translation_edit_rejects_empty_translation(
    page_editor_api: tuple[TestClient, Path],
) -> None:
    client, _data_root = page_editor_api
    response = client.patch(
        f"/api/v1/segments/{EARLY_SEGMENT_ID}/translation",
        headers=CLIENT_HEADERS,
        json={"reviewed_translation": "   ", "expected_revision": 1},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_segment_translation_edit_invokes_cache_invalidator(
    page_editor_api: tuple[TestClient, Path],
) -> None:
    from transloka_api.services.segments import EditSegmentTranslation, SegmentService

    _client, data_root = page_editor_api
    invalidated: list[str] = []
    engine, factory = _database_factory(data_root)
    try:
        with transaction_scope(factory) as session:
            updated = SegmentService(
                session,
                invalidate_cache=invalidated.append,
            ).edit_translation(
                EARLY_SEGMENT_ID,
                EditSegmentTranslation(
                    reviewed_translation="Callback edit",
                    expected_revision=1,
                ),
            )
            assert updated.current_revision == 2
    finally:
        engine.dispose()

    assert invalidated == [EARLY_SEGMENT_ID]


def test_segment_approval_makes_reviewed_text_final_and_creates_revision(
    page_editor_api: tuple[TestClient, Path],
) -> None:
    client, data_root = page_editor_api
    response = client.post(
        f"/api/v1/segments/{EARLY_SEGMENT_ID}/approve",
        headers={**CLIENT_HEADERS, REQUEST_ID_HEADER: "segment-approve"},
        json={"expected_revision": 1, "lock_after_approval": False},
    )

    assert response.status_code == 200, response.text
    assert response.headers[REQUEST_ID_HEADER] == "segment-approve"
    data = response.json()["data"]
    assert data["reviewed_translation"] == "Terjemahan: Early segment."
    assert data["final_text"] == "Terjemahan: Early segment."
    assert data["status"] == "APPROVED"
    assert data["review_status"] == "APPROVED"
    assert data["is_locked"] is False
    assert data["current_revision"] == 2

    engine, factory = _database_factory(data_root)
    try:
        with factory() as session:
            revision = session.scalar(
                select(SegmentRevision).where(
                    SegmentRevision.segment_id == EARLY_SEGMENT_ID,
                    SegmentRevision.revision_number == 2,
                )
            )
            assert revision is not None
            assert revision.revision_type == "APPROVE"
            assert revision.new_text == "Terjemahan: Early segment."
    finally:
        engine.dispose()


def test_segment_unapproval_returns_segment_to_editable_review_state(
    page_editor_api: tuple[TestClient, Path],
) -> None:
    client, data_root = page_editor_api
    approved = client.post(
        f"/api/v1/segments/{EARLY_SEGMENT_ID}/approve",
        headers=CLIENT_HEADERS,
        json={"expected_revision": 1},
    )
    response = client.post(
        f"/api/v1/segments/{EARLY_SEGMENT_ID}/unapprove",
        headers=CLIENT_HEADERS,
        json={"expected_revision": 2, "reason": "Needs terminology revision."},
    )

    assert approved.status_code == 200
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["status"] == "USER_EDITED"
    assert data["review_status"] == "EDITED"
    assert data["final_text"] == "Terjemahan: Early segment."
    assert data["current_revision"] == 3

    engine, factory = _database_factory(data_root)
    try:
        with factory() as session:
            revision = session.scalar(
                select(SegmentRevision).where(
                    SegmentRevision.segment_id == EARLY_SEGMENT_ID,
                    SegmentRevision.revision_number == 3,
                )
            )
            assert revision is not None
            assert revision.revision_type == "UNAPPROVE"
            assert revision.reason == "Needs terminology revision."
    finally:
        engine.dispose()


def test_segment_approval_supports_optional_lock_after_approval(
    page_editor_api: tuple[TestClient, Path],
) -> None:
    client, _data_root = page_editor_api
    response = client.post(
        f"/api/v1/segments/{EARLY_SEGMENT_ID}/approve",
        headers=CLIENT_HEADERS,
        json={"expected_revision": 1, "lock_after_approval": True},
    )

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["status"] == "LOCKED"
    assert data["review_status"] == "APPROVED"
    assert data["is_locked"] is True


def test_segment_lock_protects_approved_segment_and_creates_revision(
    page_editor_api: tuple[TestClient, Path],
) -> None:
    client, data_root = page_editor_api
    approved = client.post(
        f"/api/v1/segments/{EARLY_SEGMENT_ID}/approve",
        headers=CLIENT_HEADERS,
        json={"expected_revision": 1},
    )
    assert approved.status_code == 200

    engine, factory = _database_factory(data_root)
    try:
        with transaction_scope(factory) as session:
            locked = SegmentService(session).lock(
                EARLY_SEGMENT_ID,
                LockSegment(expected_revision=2),
            )
            assert locked.status == SegmentStatus.LOCKED.value
            assert locked.review_status == ReviewStatus.APPROVED.value
            assert locked.is_locked == 1
            assert locked.current_revision == 3
    finally:
        engine.dispose()

    blocked_edit = client.patch(
        f"/api/v1/segments/{EARLY_SEGMENT_ID}/translation",
        headers=CLIENT_HEADERS,
        json={"reviewed_translation": "Blocked edit", "expected_revision": 3},
    )
    assert blocked_edit.status_code == 423
    assert blocked_edit.json()["error"]["code"] == "SEGMENT_LOCKED"

    engine, factory = _database_factory(data_root)
    try:
        with factory() as session:
            revision = session.scalar(
                select(SegmentRevision).where(
                    SegmentRevision.segment_id == EARLY_SEGMENT_ID,
                    SegmentRevision.revision_number == 3,
                )
            )
            assert revision is not None
            assert revision.revision_type == "LOCK"
            assert revision.previous_text == "Terjemahan: Early segment."
            assert revision.new_text == "Terjemahan: Early segment."
    finally:
        engine.dispose()


def test_segment_lock_rejects_stale_revision(
    page_editor_api: tuple[TestClient, Path],
) -> None:
    client, data_root = page_editor_api
    approved = client.post(
        f"/api/v1/segments/{EARLY_SEGMENT_ID}/approve",
        headers=CLIENT_HEADERS,
        json={"expected_revision": 1},
    )
    assert approved.status_code == 200

    engine, factory = _database_factory(data_root)
    try:
        with transaction_scope(factory) as session:
            with pytest.raises(SegmentRevisionConflictError) as error:
                SegmentService(session).lock(
                    EARLY_SEGMENT_ID,
                    LockSegment(expected_revision=1),
                )
            assert error.value.expected_revision == 1
            assert error.value.current_revision == 2
    finally:
        engine.dispose()


def test_segment_unlock_requires_reason_and_creates_revision(
    page_editor_api: tuple[TestClient, Path],
) -> None:
    client, data_root = page_editor_api
    approved = client.post(
        f"/api/v1/segments/{EARLY_SEGMENT_ID}/approve",
        headers=CLIENT_HEADERS,
        json={"expected_revision": 1},
    )
    assert approved.status_code == 200

    engine, factory = _database_factory(data_root)
    try:
        with transaction_scope(factory) as session:
            SegmentService(session).lock(
                EARLY_SEGMENT_ID,
                LockSegment(expected_revision=2),
            )
    finally:
        engine.dispose()

    engine, factory = _database_factory(data_root)
    try:
        with transaction_scope(factory) as session:
            with pytest.raises(EmptyUnlockReasonError):
                SegmentService(session).unlock(
                    EARLY_SEGMENT_ID,
                    UnlockSegment(expected_revision=3, reason="  "),
                )
    finally:
        engine.dispose()

    engine, factory = _database_factory(data_root)
    try:
        with transaction_scope(factory) as session:
            unlocked = SegmentService(session).unlock(
                EARLY_SEGMENT_ID,
                UnlockSegment(expected_revision=3, reason="Glossary update requires review."),
            )
            assert unlocked.status == SegmentStatus.APPROVED.value
            assert unlocked.review_status == ReviewStatus.APPROVED.value
            assert unlocked.is_locked == 0
            assert unlocked.current_revision == 4
    finally:
        engine.dispose()

    engine, factory = _database_factory(data_root)
    try:
        with factory() as session:
            revision = session.scalar(
                select(SegmentRevision).where(
                    SegmentRevision.segment_id == EARLY_SEGMENT_ID,
                    SegmentRevision.revision_number == 4,
                )
            )
            assert revision is not None
            assert revision.revision_type == "UNLOCK"
            assert revision.reason == "Glossary update requires review."
    finally:
        engine.dispose()


def test_segment_unlock_rejects_unlocked_segment(
    page_editor_api: tuple[TestClient, Path],
) -> None:
    _client, data_root = page_editor_api
    engine, factory = _database_factory(data_root)
    try:
        with transaction_scope(factory) as session:
            with pytest.raises(SegmentLockStateError):
                SegmentService(session).unlock(
                    EARLY_SEGMENT_ID,
                    UnlockSegment(expected_revision=1, reason="Review again."),
                )
    finally:
        engine.dispose()


def test_segment_revisions_list_get_and_cursor_order(
    page_editor_api: tuple[TestClient, Path],
) -> None:
    client, _data_root = page_editor_api
    for expected_revision, text in enumerate(("Version one", "Version two", "Version three"), 1):
        response = client.patch(
            f"/api/v1/segments/{EARLY_SEGMENT_ID}/translation",
            headers=CLIENT_HEADERS,
            json={"reviewed_translation": text, "expected_revision": expected_revision},
        )
        assert response.status_code == 200, response.text

    first_page = client.get(
        f"/api/v1/segments/{EARLY_SEGMENT_ID}/revisions",
        headers=CLIENT_HEADERS,
        params={"limit": 2},
    )
    assert first_page.status_code == 200, first_page.text
    first_data = first_page.json()
    assert [item["revision_number"] for item in first_data["data"]] == [
        4,
        3,
    ]
    assert first_data["meta"]["pagination"]["has_more"] is True
    cursor = first_data["meta"]["pagination"]["next_cursor"]
    assert cursor

    second_page = client.get(
        f"/api/v1/segments/{EARLY_SEGMENT_ID}/revisions",
        headers=CLIENT_HEADERS,
        params={"limit": 2, "cursor": cursor},
    )
    assert second_page.status_code == 200, second_page.text
    second_data = second_page.json()
    assert [item["revision_number"] for item in second_data["data"]] == [2]
    assert second_data["meta"]["pagination"] == {
        "limit": 2,
        "next_cursor": None,
        "has_more": False,
    }

    revision_id = first_data["data"][0]["id"]
    detail = client.get(
        f"/api/v1/segment-revisions/{revision_id}",
        headers=CLIENT_HEADERS,
    )
    assert detail.status_code == 200, detail.text
    assert detail.json()["data"] == first_data["data"][0]


def test_segment_revision_restore_appends_without_deleting_later_revisions(
    page_editor_api: tuple[TestClient, Path],
) -> None:
    client, _data_root = page_editor_api
    for expected_revision, text in enumerate(("Version one", "Version two", "Version three"), 1):
        response = client.patch(
            f"/api/v1/segments/{EARLY_SEGMENT_ID}/translation",
            headers=CLIENT_HEADERS,
            json={"reviewed_translation": text, "expected_revision": expected_revision},
        )
        assert response.status_code == 200, response.text

    history = client.get(
        f"/api/v1/segments/{EARLY_SEGMENT_ID}/revisions",
        headers=CLIENT_HEADERS,
        params={"limit": 100},
    )
    assert history.status_code == 200
    revisions_before = history.json()["data"]
    target = next(item for item in revisions_before if item["revision_number"] == 2)

    restored = client.post(
        f"/api/v1/segments/{EARLY_SEGMENT_ID}/restore-revision",
        headers=CLIENT_HEADERS,
        json={"revision_id": target["id"], "expected_revision": 4},
    )
    assert restored.status_code == 200, restored.text
    restored_data = restored.json()["data"]
    assert restored_data["final_text"] == "Version one"
    assert restored_data["reviewed_translation"] == "Version one"
    assert restored_data["status"] == "USER_EDITED"
    assert restored_data["review_status"] == "EDITED"
    assert restored_data["current_revision"] == 5

    history_after = client.get(
        f"/api/v1/segments/{EARLY_SEGMENT_ID}/revisions",
        headers=CLIENT_HEADERS,
        params={"limit": 100},
    )
    assert history_after.status_code == 200
    revisions_after = history_after.json()["data"]
    assert [item["revision_number"] for item in revisions_after] == [5, 4, 3, 2]
    assert revisions_after[0]["revision_type"] == "RESTORE_VERSION"
    assert revisions_after[0]["new_text"] == "Version one"
    assert any(item["id"] == target["id"] for item in revisions_after)


def test_segment_revision_api_rejects_invalid_revision_and_stale_restore(
    page_editor_api: tuple[TestClient, Path],
) -> None:
    client, _data_root = page_editor_api
    missing = client.get(
        "/api/v1/segment-revisions/rev_missing",
        headers=CLIENT_HEADERS,
    )
    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "REVISION_NOT_FOUND"

    edited = client.patch(
        f"/api/v1/segments/{EARLY_SEGMENT_ID}/translation",
        headers=CLIENT_HEADERS,
        json={"reviewed_translation": "Current text", "expected_revision": 1},
    )
    assert edited.status_code == 200
    revisions = client.get(
        f"/api/v1/segments/{EARLY_SEGMENT_ID}/revisions",
        headers=CLIENT_HEADERS,
        params={"limit": 100},
    )
    target_id = revisions.json()["data"][0]["id"]

    conflict = client.post(
        f"/api/v1/segments/{EARLY_SEGMENT_ID}/restore-revision",
        headers=CLIENT_HEADERS,
        json={"revision_id": target_id, "expected_revision": 1},
    )
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "REVISION_CONFLICT"
    assert conflict.json()["error"]["details"] == {
        "expected_revision": 1,
        "current_revision": 2,
    }


def test_segment_review_rejects_invalid_state_and_stale_revision(
    page_editor_api: tuple[TestClient, Path],
) -> None:
    client, _data_root = page_editor_api
    invalid_unapprove = client.post(
        f"/api/v1/segments/{EARLY_SEGMENT_ID}/unapprove",
        headers=CLIENT_HEADERS,
        json={"expected_revision": 1},
    )
    stale_approve = client.post(
        f"/api/v1/segments/{EARLY_SEGMENT_ID}/approve",
        headers=CLIENT_HEADERS,
        json={"expected_revision": 0},
    )

    assert invalid_unapprove.status_code == 409
    assert invalid_unapprove.json()["error"]["code"] == "SEGMENT_STATE_INVALID"
    assert stale_approve.status_code == 409
    assert stale_approve.json()["error"]["code"] == "REVISION_CONFLICT"
    assert stale_approve.json()["error"]["details"] == {
        "expected_revision": 0,
        "current_revision": 1,
    }


def test_bulk_approve_updates_multiple_segments_and_preserves_revisions(
    page_editor_api: tuple[TestClient, Path],
) -> None:
    client, data_root = page_editor_api
    response = client.post(
        "/api/v1/segments/bulk",
        headers=CLIENT_HEADERS,
        json={
            "action": "approve",
            "selected_ids": [EARLY_SEGMENT_ID, LATE_SEGMENT_FIRST_ID],
            "expected_revisions": {EARLY_SEGMENT_ID: 1, LATE_SEGMENT_FIRST_ID: 1},
        },
    )

    assert response.status_code == 200, response.text
    assert response.json()["data"]["succeeded"] == 2
    assert response.json()["data"]["failed"] == 0
    assert [item["status"] for item in response.json()["data"]["results"]] == [
        "SUCCEEDED",
        "SUCCEEDED",
    ]

    engine, factory = _database_factory(data_root)
    try:
        with factory() as session:
            rows = session.scalars(
                select(DocumentSegment).where(
                    DocumentSegment.id.in_((EARLY_SEGMENT_ID, LATE_SEGMENT_FIRST_ID))
                )
            ).all()
            assert {row.review_status for row in rows} == {ReviewStatus.APPROVED.value}
            assert {row.current_revision for row in rows} == {2}
    finally:
        engine.dispose()


def test_bulk_action_returns_partial_failures_for_mixed_state_and_locked_segments(
    page_editor_api: tuple[TestClient, Path],
) -> None:
    client, data_root = page_editor_api
    approved = client.post(
        f"/api/v1/segments/{EARLY_SEGMENT_ID}/approve",
        headers=CLIENT_HEADERS,
        json={"expected_revision": 1},
    )
    assert approved.status_code == 200

    engine, factory = _database_factory(data_root)
    try:
        with transaction_scope(factory) as session:
            SegmentService(session).lock(EARLY_SEGMENT_ID, LockSegment(expected_revision=2))
    finally:
        engine.dispose()

    response = client.post(
        "/api/v1/segments/bulk",
        headers=CLIENT_HEADERS,
        json={
            "action": "retranslate",
            "selected_ids": [EARLY_SEGMENT_ID, LATE_SEGMENT_FIRST_ID],
            "expected_revisions": {EARLY_SEGMENT_ID: 3, LATE_SEGMENT_FIRST_ID: 1},
        },
    )

    assert response.status_code == 202, response.text
    data = response.json()["data"]
    assert data["failed"] == 1
    assert data["queued"] == 1
    failures = [item for item in data["results"] if item["status"] == "FAILED"]
    assert failures[0]["error"]["code"] == "SEGMENT_LOCKED"
    assert data["job_id"].startswith("job_")


def test_bulk_approve_reports_invalid_id_and_revision_conflict_without_rolling_back_success(
    page_editor_api: tuple[TestClient, Path],
) -> None:
    client, data_root = page_editor_api
    response = client.post(
        "/api/v1/segments/bulk",
        headers=CLIENT_HEADERS,
        json={
            "action": "approve",
            "selected_ids": [EARLY_SEGMENT_ID, "seg_00000000-0000-4000-8000-000000000099"],
            "expected_revisions": {EARLY_SEGMENT_ID: 0},
        },
    )

    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["succeeded"] == 0
    assert data["failed"] == 2
    by_id = {item["segment_id"]: item for item in data["results"]}
    assert by_id[EARLY_SEGMENT_ID]["error"]["code"] == "REVISION_CONFLICT"
    assert by_id["seg_00000000-0000-4000-8000-000000000099"]["error"]["code"] == (
        "SEGMENT_NOT_FOUND"
    )

    engine, factory = _database_factory(data_root)
    try:
        with factory() as session:
            row = session.get(DocumentSegment, EARLY_SEGMENT_ID)
            assert row is not None
            assert row.current_revision == 1
    finally:
        engine.dispose()


def test_bulk_retranslation_is_idempotent_and_keeps_selected_ids_in_job_payload(
    page_editor_api: tuple[TestClient, Path],
) -> None:
    client, data_root = page_editor_api
    headers = {**CLIENT_HEADERS, "Idempotency-Key": "bulk-retranslate-retry"}
    body = {
        "action": "retranslate",
        "selected_ids": [EARLY_SEGMENT_ID, LATE_SEGMENT_FIRST_ID],
        "expected_revisions": {EARLY_SEGMENT_ID: 1, LATE_SEGMENT_FIRST_ID: 1},
    }

    first = client.post("/api/v1/segments/bulk", headers=headers, json=body)
    second = client.post("/api/v1/segments/bulk", headers=headers, json=body)

    assert first.status_code == 202, first.text
    assert second.status_code == 202, second.text
    first_job_id = first.json()["data"]["job_id"]
    assert second.json()["data"]["job_id"] == first_job_id

    engine, factory = _database_factory(data_root)
    try:
        with factory() as session:
            jobs = session.scalars(
                select(ApplicationJob).where(ApplicationJob.id == first_job_id)
            ).all()
            assert len(jobs) == 1
            assert '"scope":"SELECTED_SEGMENTS"' in jobs[0].payload_json
            assert EARLY_SEGMENT_ID in jobs[0].payload_json
            assert LATE_SEGMENT_FIRST_ID in jobs[0].payload_json
    finally:
        engine.dispose()


def test_bulk_retranslation_fails_closed_when_queue_is_not_configured(
    page_editor_api: tuple[TestClient, Path],
) -> None:
    client, data_root = page_editor_api
    application = cast(FastAPI, client.app)
    application.state.translation_queue = None

    response = client.post(
        "/api/v1/segments/bulk",
        headers={**CLIENT_HEADERS, "Idempotency-Key": "bulk-no-queue"},
        json={
            "action": "retranslate",
            "selected_ids": [EARLY_SEGMENT_ID],
            "expected_revisions": {EARLY_SEGMENT_ID: 1},
        },
    )

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "QUEUE_NOT_CONFIGURED"
    engine, factory = _database_factory(data_root)
    try:
        with factory() as session:
            assert session.scalars(select(ApplicationJob)).all() == []
    finally:
        engine.dispose()
