import hashlib
import json
import os
from io import BytesIO
from pathlib import Path
from typing import cast
from uuid import UUID

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from pypdf import PdfWriter
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker
from transloka_api.app import create_app
from transloka_api.middleware import (
    CLIENT_HEADER,
    CLIENT_HEADER_VALUE,
    CLIENT_VERSION_HEADER,
    CLIENT_VERSION_VALUE,
)
from transloka_core.database import (
    create_session_factory,
    create_sqlite_engine,
    transaction_scope,
)
from transloka_core.database.models.document_ir import DocumentBlock, DocumentSegment, SegmentStatus
from transloka_core.database.models.documents import Document, DocumentClass, DocumentStatus
from transloka_core.database.models.files import FileRole, FileStatus, StoredFile
from transloka_core.database.models.jobs import (
    ApplicationJob,
    JobAttempt,
    JobAttemptStatus,
    JobStatus,
)
from transloka_core.database.models.pages import DocumentPage, PageType
from transloka_core.database.models.projects import Project
from transloka_core.storage.local import LocalFileStorage
from transloka_documents.ocr import (
    OCRGeometry,
    OCRHealth,
    OCRHealthStatus,
    OCRPage,
    OCRResult,
    OCRSettings,
    OCRTextBlock,
)
from transloka_documents.ocr.orchestration import OCRPageOrchestrator, OCRRawOutputStore
from transloka_worker.ocr import DatabaseOCRRequestLoader, OCRJobRunner
from transloka_worker.queue import create_huey, resolve_queue_configuration
from transloka_worker.tasks.ocr import OCR_TASK_NAME, register_ocr_task

REPOSITORY_ROOT = Path(__file__).parents[3]
ALEMBIC_CONFIGURATION = REPOSITORY_ROOT / "alembic.ini"
CLIENT_HEADERS = {
    CLIENT_HEADER: CLIENT_HEADER_VALUE,
    CLIENT_VERSION_HEADER: CLIENT_VERSION_VALUE,
}
CREATED_AT = "2026-08-27T00:00:00.000Z"


def _id(prefix: str, value: int) -> str:
    return f"{prefix}{UUID(int=value)}"


ORIGINAL_FILE_ID = _id("fil_", 101)
DOCUMENT_ID = _id("doc_", 102)
PAGE_ID = _id("pag_", 103)


class DeterministicOCRProvider:
    def health_check(self) -> OCRHealth:
        return OCRHealth(status=OCRHealthStatus.AVAILABLE, provider="test-ocr")

    def analyze_page(
        self,
        page: OCRPage,
        *,
        settings: OCRSettings | None = None,
    ) -> OCRResult:
        effective_settings = settings or OCRSettings()
        return OCRResult(
            page_number=page.page_number,
            text="Production OCR runtime.",
            blocks=(
                OCRTextBlock(
                    text="Production OCR runtime.",
                    geometry=OCRGeometry(x=10, y=10, width=100, height=20),
                    confidence=0.96,
                ),
            ),
            confidence=0.96,
            settings=effective_settings,
            provider="test-ocr",
        )


def test_production_ocr_runtime_crosses_api_queue_worker_boundary(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    initial_artifacts = _database_artifacts()
    data_root = tmp_path / "production ocr runtime"
    monkeypatch.setenv("TRANSLOKA_DATA_DIR", str(data_root))
    command.upgrade(Config(str(ALEMBIC_CONFIGURATION)), "head")

    application = create_app()
    with TestClient(application) as client:
        project_response = client.post(
            "/api/v1/projects",
            headers=CLIENT_HEADERS,
            json={
                "name": "Production OCR Project",
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
        _seed_ocr_inputs(
            factory, LocalFileStorage(application.state.settings.data_directories), project_id
        )

        before = client.get(
            f"/api/v1/documents/{DOCUMENT_ID}/ocr/status",
            headers=CLIENT_HEADERS,
        )
        assert before.status_code == 200
        assert before.json()["data"]["status"] == "NOT_STARTED"

        invalid = client.post(
            f"/api/v1/documents/{DOCUMENT_ID}/ocr/start",
            headers={**CLIENT_HEADERS, "Idempotency-Key": "invalid-force-ocr"},
            json={"mode": "FORCE", "page_ids": []},
        )
        assert invalid.status_code == 422
        assert invalid.json()["error"]["code"] == "VALIDATION_ERROR"

        active_queue = application.state.ocr_queue
        application.state.ocr_queue = None
        unavailable = client.post(
            f"/api/v1/documents/{DOCUMENT_ID}/ocr/start",
            headers={**CLIENT_HEADERS, "Idempotency-Key": "missing-ocr-queue"},
            json={"mode": "AUTO", "page_ids": None},
        )
        assert unavailable.status_code == 503
        assert unavailable.json()["error"]["code"] == "QUEUE_NOT_CONFIGURED"
        application.state.ocr_queue = active_queue

        start = client.post(
            f"/api/v1/documents/{DOCUMENT_ID}/ocr/start",
            headers={**CLIENT_HEADERS, "Idempotency-Key": "production-ocr-runtime-e2e"},
            json={
                "page_ids": None,
                "mode": "AUTO",
                "language": "en",
                "detect_tables": True,
                "detect_formulas": True,
            },
        )
        assert start.status_code == 202, start.text
        job_id = cast(str, start.json()["data"]["job_id"])
        assert application.state.ocr_queue_owner.huey.pending_count() == 1

    configuration = resolve_queue_configuration(data_root)
    huey = create_huey(configuration)
    engine = create_sqlite_engine(configuration.directories)
    factory = create_session_factory(engine)
    storage = LocalFileStorage(configuration.directories)
    runner = OCRJobRunner(
        OCRPageOrchestrator(
            DeterministicOCRProvider(),
            storage,
            raw_output_store=OCRRawOutputStore(storage, factory),
        ),
        DatabaseOCRRequestLoader(factory, storage),
        factory,
        configuration.directories.temporary,
        worker_identifier="ocr-runtime-e2e",
    )
    try:
        register_ocr_task(huey, runner.run)
        task = huey.dequeue()
        assert task is not None
        assert task.name == OCR_TASK_NAME
        assert task.data == ((job_id,), {})
        huey.execute(task)
        assert huey.pending_count() == 0
    finally:
        huey.storage.close()
        engine.dispose()

    status_application = create_app()
    with TestClient(status_application) as client:
        response = client.get(
            f"/api/v1/documents/{DOCUMENT_ID}/ocr/status",
            headers=CLIENT_HEADERS,
        )
        assert response.status_code == 200
        body = response.json()["data"]
        assert body["status"] == "COMPLETED"
        assert body["selected_pages"] == 1
        assert body["completed_pages"] == 1
        assert body["failed_pages"] == 0
        assert body["progress"] == 1.0

        factory = cast(sessionmaker[Session], status_application.state.session_factory)
        with factory() as session:
            job = session.get(ApplicationJob, job_id)
            attempt = session.scalar(select(JobAttempt).where(JobAttempt.job_id == job_id))
            assert job is not None and job.status == JobStatus.COMPLETED.value
            assert attempt is not None and attempt.status == JobAttemptStatus.COMPLETED.value
            page = session.get(DocumentPage, PAGE_ID)
            assert page is not None and page.status == DocumentStatus.STRUCTURED.value
            assert page.ocr_confidence == 0.96
            block = session.scalars(
                select(DocumentBlock).where(DocumentBlock.page_id == PAGE_ID)
            ).one()
            segment = session.scalars(
                select(DocumentSegment).where(DocumentSegment.block_id == block.id)
            ).one()
            assert segment.status == SegmentStatus.READY_FOR_TRANSLATION.value
            assert segment.ocr_text == "Production OCR runtime."
            assert segment.native_text is None
            assert segment.resolved_source_text == "Production OCR runtime."
            assert segment.global_order == block.global_reading_order == 1
            assert json.loads(block.source_geometry_json) == {
                "x": 4.8,
                "y": 4.8,
                "width": 48.0,
                "height": 9.6,
                "coordinate_system": "PDF_POINT_TOP_LEFT",
            }

        page_response = client.get(f"/api/v1/pages/{PAGE_ID}/ocr", headers=CLIENT_HEADERS)
        assert page_response.status_code == 200
        assert page_response.json()["data"]["raw_text"] == "Production OCR runtime."
        assert len(page_response.json()["data"]["segments"]) == 1

    raw_outputs = list((data_root / "projects" / project_id / "ocr" / "raw").rglob("*.json"))
    assert len(raw_outputs) == 1
    assert "Production OCR runtime." in raw_outputs[0].read_text(encoding="utf-8")
    assert _database_artifacts() == initial_artifacts


def _seed_ocr_inputs(
    factory: sessionmaker[Session],
    storage: LocalFileStorage,
    project_id: str,
) -> None:
    source = _pdf_bytes()
    storage_key = f"projects/{project_id}/original/{ORIGINAL_FILE_ID}.pdf"
    temporary = storage.write_temporary(BytesIO(source))
    artifact = storage.commit(temporary, storage_key, immutable=True)
    assert artifact.checksum_sha256 == hashlib.sha256(source).hexdigest()

    with transaction_scope(factory) as session:
        session.add(
            StoredFile(
                id=ORIGINAL_FILE_ID,
                project_id=project_id,
                document_id=None,
                file_role=FileRole.ORIGINAL.value,
                storage_key=storage_key,
                original_filename="scan.pdf",
                safe_filename="scan.pdf",
                mime_type="application/pdf",
                size_bytes=len(source),
                checksum_sha256=artifact.checksum_sha256,
                is_immutable=1,
                status=FileStatus.VALIDATED.value,
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
                original_file_id=ORIGINAL_FILE_ID,
                ir_version="0.1",
                title="Scanned runtime document",
                author=None,
                document_type="TECHNICAL_BOOK",
                document_class=DocumentClass.SCANNED_PDF.value,
                source_language="en",
                target_language="id",
                page_count=1,
                word_count_estimate=None,
                has_text_layer=0,
                scanned_page_count=1,
                image_count=1,
                table_count=0,
                status=DocumentStatus.ANALYZED.value,
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
                width_points=612.0,
                height_points=792.0,
                rotation_degrees=0.0,
                page_type=PageType.SCANNED.value,
                page_classification="SINGLE_COLUMN",
                column_count=1,
                reading_direction="LTR",
                status=DocumentStatus.ANALYZED.value,
                render_file_id=None,
                thumbnail_file_id=None,
                native_extraction_confidence=None,
                ocr_confidence=None,
                structure_confidence=None,
                metadata_json=None,
                created_at=CREATED_AT,
                updated_at=CREATED_AT,
            )
        )
        project = session.get(Project, project_id)
        assert project is not None
        project.active_document_id = DOCUMENT_ID


def _pdf_bytes() -> bytes:
    output = BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(width=612, height=792)
    writer.write(output)
    return output.getvalue()


def _database_artifacts() -> frozenset[Path]:
    artifacts: set[Path] = set()
    ignored = {".git", ".next", ".venv", "node_modules", "test-results"}
    for current, directories, filenames in os.walk(REPOSITORY_ROOT):
        directories[:] = [name for name in directories if name not in ignored]
        artifacts.update(
            Path(current) / filename
            for filename in filenames
            if Path(filename).suffix.casefold() in {".db", ".sqlite", ".sqlite3"}
        )
    return frozenset(artifacts)
