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
from pypdf import PdfReader
from reportlab.pdfgen.canvas import Canvas  # type: ignore[import-untyped]
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
from transloka_core.database.models.document_ir import (
    BlockType,
    DocumentBlock,
    DocumentSegment,
    ReviewStatus,
    SegmentStatus,
    SemanticRole,
)
from transloka_core.database.models.documents import Document, DocumentClass, DocumentStatus
from transloka_core.database.models.exports import Export, ExportStatus
from transloka_core.database.models.files import FileRole, FileStatus, StoredFile
from transloka_core.database.models.jobs import (
    ApplicationJob,
    JobAttempt,
    JobAttemptStatus,
    JobStatus,
)
from transloka_core.database.models.pages import DocumentPage, PageType
from transloka_core.database.models.projects import Project, ProjectStatus
from transloka_core.database.models.reconstruction import (
    ReconstructionBlock,
    ReconstructionJob,
    ReconstructionPage,
    ReconstructionStatus,
    TargetPageMapping,
)
from transloka_core.storage.local import LocalFileStorage
from transloka_documents.extraction import extract_digital_text
from transloka_worker.analysis import _style_json
from transloka_worker.queue import create_huey, resolve_queue_configuration
from transloka_worker.reconstruction import (
    DatabaseReconstructionRequestLoader,
    ProductionReconstructionJobRunner,
)
from transloka_worker.tasks.reconstruction import (
    RECONSTRUCTION_TASK_NAME,
    register_reconstruction_task,
)

REPOSITORY_ROOT = Path(__file__).parents[3]
ALEMBIC_CONFIGURATION = REPOSITORY_ROOT / "alembic.ini"
CLIENT_HEADERS = {
    CLIENT_HEADER: CLIENT_HEADER_VALUE,
    CLIENT_VERSION_HEADER: CLIENT_VERSION_VALUE,
}
CREATED_AT = "2026-08-28T00:00:00.000Z"
SOURCE_TEXT = "Production source sentence."
TRANSLATED_TEXT = "Kalimat produksi diterjemahkan."


def _id(prefix: str, value: int) -> str:
    return f"{prefix}{UUID(int=value)}"


ORIGINAL_FILE_ID = _id("fil_", 201)
DOCUMENT_ID = _id("doc_", 202)
PAGE_ID = _id("pag_", 203)
BLOCK_ID = _id("blk_", 204)
SEGMENT_ID = _id("seg_", 205)


@pytest.mark.parametrize(
    ("mode", "typography", "expanded"),
    [
        ("OVERLAY", False, False),
        ("HYBRID", False, False),
        ("OVERLAY", True, False),
        ("HYBRID", True, False),
        ("HYBRID", True, True),
    ],
)
def test_production_reconstruction_runtime_crosses_api_queue_worker_boundary(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    mode: str,
    typography: bool,
    expanded: bool,
) -> None:
    initial_artifacts = _database_artifacts()
    data_root = tmp_path / "production reconstruction runtime"
    monkeypatch.setenv("TRANSLOKA_DATA_DIR", str(data_root))
    command.upgrade(Config(str(ALEMBIC_CONFIGURATION)), "head")

    application = create_app()
    with TestClient(application) as client:
        project_response = client.post(
            "/api/v1/projects",
            headers=CLIENT_HEADERS,
            json={
                "name": "Production Reconstruction Project",
                "description": None,
                "source_language": "en",
                "target_language": "id",
                "document_type": "TECHNICAL_BOOK",
                "translation_style": "PROFESSIONAL",
                "reconstruction_mode": mode,
            },
        )
        assert project_response.status_code == 201, project_response.text
        project_id = cast(str, project_response.json()["data"]["id"])
        factory = cast(sessionmaker[Session], application.state.session_factory)
        storage = LocalFileStorage(application.state.settings.data_directories)
        source_pdf = _seed_reconstruction_inputs(
            factory, storage, project_id, typography=typography, expanded=expanded
        )

        start = client.post(
            f"/api/v1/projects/{project_id}/reconstruction/start",
            headers={**CLIENT_HEADERS, "Idempotency-Key": "production-reconstruction-e2e"},
            json={"mode": mode, "page_ids": [PAGE_ID]},
        )
        assert start.status_code == 202, start.text
        job_id = cast(str, start.json()["data"]["job_id"])
        assert application.state.reconstruction_queue_owner.huey.pending_count() == 1

    configuration = resolve_queue_configuration(data_root)
    huey = create_huey(configuration)
    engine = create_sqlite_engine(configuration.directories)
    factory = create_session_factory(engine)
    storage = LocalFileStorage(configuration.directories)
    runner = ProductionReconstructionJobRunner(
        DatabaseReconstructionRequestLoader(factory, storage),
        factory,
        storage,
        configuration.directories.temporary,
        worker_identifier="reconstruction-runtime-e2e",
    )
    try:
        register_reconstruction_task(huey, runner.run)
        task = huey.dequeue()
        assert task is not None
        assert task.name == RECONSTRUCTION_TASK_NAME
        assert task.data == ((job_id,), {})
        huey.execute(task)
        assert huey.pending_count() == 0
    finally:
        huey.storage.close()
        engine.dispose()

    status_application = create_app()
    with TestClient(status_application) as client:
        response = client.get(
            f"/api/v1/projects/{project_id}/reconstruction/status",
            headers=CLIENT_HEADERS,
        )
        assert response.status_code == 200, response.text
        body = response.json()["data"]
        assert body["status"] == ReconstructionStatus.COMPLETED.value
        assert body["progress"] == 1.0
        assert body["completed_pages"] == 1
        assert body["generated_target_pages"] == 1

        factory = cast(sessionmaker[Session], status_application.state.session_factory)
        storage = LocalFileStorage(status_application.state.settings.data_directories)
        with factory() as session:
            job = session.get(ApplicationJob, job_id)
            attempt = session.scalar(select(JobAttempt).where(JobAttempt.job_id == job_id))
            reconstruction = session.scalar(
                select(ReconstructionJob).where(ReconstructionJob.application_job_id == job_id)
            )
            export = session.scalar(
                select(Export).where(Export.reconstruction_job_id == reconstruction.id)
                if reconstruction is not None
                else select(Export).where(Export.id == "missing")
            )
            page = session.scalar(
                select(ReconstructionPage).where(
                    ReconstructionPage.reconstruction_job_id == reconstruction.id
                )
                if reconstruction is not None
                else select(ReconstructionPage).where(ReconstructionPage.id == "missing")
            )
            mapping = session.scalar(
                select(TargetPageMapping).where(
                    TargetPageMapping.reconstruction_job_id == reconstruction.id
                )
                if reconstruction is not None
                else select(TargetPageMapping).where(TargetPageMapping.id == "missing")
            )
            project = session.get(Project, project_id)
            rendered_block = session.scalar(
                select(ReconstructionBlock).where(
                    ReconstructionBlock.block_id == BLOCK_ID,
                )
            )
            assert rendered_block is not None
            assert rendered_block.strategy == ("REFLOW" if mode == "HYBRID" else "OVERLAY")
            assert rendered_block.font_mapping_json is not None
            font_mapping = json.loads(rendered_block.font_mapping_json)
            assert font_mapping["resolved_family"] == "Helvetica"
            assert font_mapping["embedding_status"] == "SYSTEM_REFERENCE"
            assert font_mapping["warnings"] == (
                ["SOURCE_BOX_EXPANDED", "SOURCE_LINE_LAYOUT_ADJUSTED"] if expanded else []
            )
            assert rendered_block.fit_strategy == ("EXPAND_BOX" if expanded else None)
            if expanded:
                assert font_mapping["layout"] == "SOURCE_BLOCK_FIT"
                assert font_mapping["font_size"] == font_mapping["source_font_size"] == 12
                assert rendered_block.target_geometry_json is not None
                target_geometry = json.loads(rendered_block.target_geometry_json)
                assert target_geometry["width"] > 320
            elif typography:
                assert font_mapping["layout"] == "SOURCE_LINES"
                assert [run["line_index"] for run in font_mapping["runs"]] == [0, 1]
            document = session.get(Document, DOCUMENT_ID)
            assert job is not None and job.status == JobStatus.COMPLETED.value
            assert attempt is not None and attempt.status == JobAttemptStatus.COMPLETED.value
            assert reconstruction is not None
            assert reconstruction.status == ReconstructionStatus.COMPLETED.value
            assert export is not None and export.status == ExportStatus.COMPLETED.value
            assert export.file_id is not None
            assert page is not None and page.status == ReconstructionStatus.COMPLETED.value
            assert page.strategy == "OVERLAY"
            assert mapping is not None and mapping.target_page_number == 1
            assert project is not None and project.status == ProjectStatus.READY_FOR_EXPORT.value
            assert document is not None and document.status == DocumentStatus.RECONSTRUCTED.value
            stored = session.get(StoredFile, export.file_id)
            assert stored is not None
            export_key = stored.storage_key
            export_checksum = stored.checksum_sha256

        with storage.open_read(export_key) as source:
            output_pdf = source.read()
        output_text = "\n".join(
            page.extract_text() or "" for page in PdfReader(BytesIO(output_pdf)).pages
        )
        assert TRANSLATED_TEXT in output_text
        assert SOURCE_TEXT not in output_text
        if typography:
            assert " ".join(output_text.split()).count(TRANSLATED_TEXT) == (7 if expanded else 2)
        assert hashlib.sha256(output_pdf).hexdigest() == export_checksum
        with storage.open_read(f"projects/{project_id}/original/{ORIGINAL_FILE_ID}.pdf") as source:
            assert source.read() == source_pdf

    assert _database_artifacts() == initial_artifacts


def _seed_reconstruction_inputs(
    factory: sessionmaker[Session],
    storage: LocalFileStorage,
    project_id: str,
    *,
    typography: bool = False,
    expanded: bool = False,
) -> bytes:
    source_pdf = _pdf_bytes(typography=typography)
    style_json = None
    source_text = SOURCE_TEXT
    translated_text = TRANSLATED_TEXT
    if typography:
        extracted = extract_digital_text(BytesIO(source_pdf))
        page = extracted.pages[0]
        assert len(page.block_candidates) == 1
        source_text = page.block_candidates[0].source_text
        assert source_text == f"{SOURCE_TEXT}\n{SOURCE_TEXT}"
        style_json = _style_json(page, page.block_candidates[0])
        translated_text = f"{TRANSLATED_TEXT}\n{TRANSLATED_TEXT}"
        if expanded:
            translated_text = " ".join([TRANSLATED_TEXT] * 7)
    normalized_source = " ".join(source_text.split())
    storage_key = f"projects/{project_id}/original/{ORIGINAL_FILE_ID}.pdf"
    temporary = storage.write_temporary(BytesIO(source_pdf))
    artifact = storage.commit(temporary, storage_key, immutable=True)
    with transaction_scope(factory) as session:
        session.add(
            StoredFile(
                id=ORIGINAL_FILE_ID,
                project_id=project_id,
                document_id=None,
                file_role=FileRole.ORIGINAL.value,
                storage_key=storage_key,
                original_filename="source.pdf",
                safe_filename="source.pdf",
                mime_type="application/pdf",
                size_bytes=artifact.size_bytes,
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
                title="Production reconstruction document",
                author=None,
                document_type="TECHNICAL_BOOK",
                document_class=DocumentClass.DIGITAL_PDF.value,
                source_language="en",
                target_language="id",
                page_count=1,
                word_count_estimate=3,
                has_text_layer=1,
                scanned_page_count=0,
                image_count=0,
                table_count=0,
                status=DocumentStatus.TRANSLATED.value,
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
                width_points=612,
                height_points=792,
                rotation_degrees=0.0,
                page_type=PageType.DIGITAL.value,
                page_classification="SINGLE_COLUMN",
                column_count=1,
                reading_direction="LTR",
                status=DocumentStatus.TRANSLATED.value,
                render_file_id=None,
                thumbnail_file_id=None,
                native_extraction_confidence=0.99,
                ocr_confidence=None,
                structure_confidence=0.99,
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
                source_text=source_text,
                normalized_source_text=normalized_source,
                source_geometry_json=json.dumps(
                    {
                        "coordinate_system": "PDF_POINT_TOP_LEFT",
                        "x": 72,
                        "y": 52,
                        "width": 320,
                        "height": 60 if typography else 30,
                    }
                ),
                target_geometry_json=None,
                style_json=style_json,
                detail_json=None,
                status=DocumentStatus.TRANSLATED.value,
                confidence=0.99,
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
                source_text=normalized_source,
                native_text=normalized_source,
                ocr_text=None,
                resolved_source_text=normalized_source,
                normalized_source_text=normalized_source,
                protected_source_text=normalized_source,
                machine_translation=translated_text,
                reviewed_translation=translated_text,
                final_text=translated_text,
                source_language="en",
                target_language="id",
                status=SegmentStatus.APPROVED.value,
                review_status=ReviewStatus.APPROVED.value,
                is_locked=0,
                current_revision=1,
                confidence_overall=0.99,
                confidence_json=None,
                translation_settings_hash="runtime-e2e",
                created_at=CREATED_AT,
                updated_at=CREATED_AT,
            )
        )
        project = session.get(Project, project_id)
        assert project is not None
        project.active_document_id = DOCUMENT_ID
    return source_pdf


def _pdf_bytes(*, typography: bool = False) -> bytes:
    output = BytesIO()
    canvas = Canvas(output, pagesize=(612, 792))
    canvas.drawString(72, 720, SOURCE_TEXT)
    if typography:
        canvas.drawString(72, 700, SOURCE_TEXT)
    canvas.save()
    return output.getvalue()


def _database_artifacts() -> set[Path]:
    artifacts: set[Path] = set()
    ignored = {".git", ".next", ".venv", ".worktrees", "node_modules", "test-results"}
    for current, directories, filenames in os.walk(REPOSITORY_ROOT):
        directories[:] = [name for name in directories if name not in ignored]
        artifacts.update(
            (Path(current) / filename).resolve()
            for filename in filenames
            if Path(filename).suffix.casefold() in {".db", ".sqlite", ".sqlite3"}
        )
    return artifacts
