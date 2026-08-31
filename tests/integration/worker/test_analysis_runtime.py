from collections.abc import Iterator
from io import BytesIO
from pathlib import Path
from typing import Any, cast

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from pypdf import PdfWriter
from reportlab.pdfgen.canvas import Canvas  # type: ignore[import-untyped]
from sqlalchemy import select
from transloka_api.app import create_app
from transloka_api.middleware import (
    CLIENT_HEADER,
    CLIENT_HEADER_VALUE,
    CLIENT_VERSION_HEADER,
    CLIENT_VERSION_VALUE,
)
from transloka_core.database import create_session_factory, create_sqlite_engine
from transloka_core.database.models.document_ir import (
    DocumentBlock,
    DocumentSegment,
    SegmentStatus,
)
from transloka_core.database.models.documents import Document, DocumentStatus
from transloka_core.database.models.jobs import ApplicationJob, JobAttempt, JobStatus
from transloka_core.database.models.pages import DocumentPage, PageType
from transloka_core.database.models.projects import Project, ProjectStatus
from transloka_core.storage import resolve_local_data_directories
from transloka_core.storage.local import LocalFileStorage
from transloka_worker.analysis import DatabaseAnalysisJobRunner
from transloka_worker.queue import create_huey, resolve_queue_configuration
from transloka_worker.tasks.analysis import register_analysis_task

REPOSITORY_ROOT = Path(__file__).parents[3]
ALEMBIC_CONFIGURATION = REPOSITORY_ROOT / "alembic.ini"
HEADERS = {
    CLIENT_HEADER: CLIENT_HEADER_VALUE,
    CLIENT_VERSION_HEADER: CLIENT_VERSION_VALUE,
}
PROJECT = {
    "name": "Analysis Runtime",
    "description": None,
    "source_language": "en",
    "target_language": "id",
    "document_type": "TECHNICAL_BOOK",
    "translation_style": "PROFESSIONAL",
    "reconstruction_mode": "HYBRID",
}


@pytest.fixture
def analysis_runtime(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> Iterator[tuple[Path, str, str, str]]:
    root = tmp_path / "analysis runtime"
    monkeypatch.setenv("TRANSLOKA_DATA_DIR", str(root))
    command.upgrade(Config(str(ALEMBIC_CONFIGURATION)), "head")
    with TestClient(create_app()) as client:
        project_response = client.post("/api/v1/projects", headers=HEADERS, json=PROJECT)
        project_id = cast(str, project_response.json()["data"]["id"])
        response = client.post(
            f"/api/v1/projects/{project_id}/documents/import",
            headers={**HEADERS, "Idempotency-Key": "analysis-runtime"},
            files={"file": ("scanned.pdf", _pdf_bytes(2), "application/pdf")},
            data={"set_as_active": "true"},
        )
        assert response.status_code == 202
        document_id = cast(str, response.json()["data"]["document"]["id"])
        job_id = cast(str, response.json()["data"]["job"]["id"])
    yield root, project_id, document_id, job_id


def test_analysis_task_persists_pages_and_completes_job(
    analysis_runtime: tuple[Path, str, str, str],
) -> None:
    root, project_id, document_id, job_id = analysis_runtime
    directories = resolve_local_data_directories(root)
    engine = create_sqlite_engine(directories)
    factory = create_session_factory(engine)
    huey = create_huey(resolve_queue_configuration(root))
    try:
        runner = DatabaseAnalysisJobRunner(factory, LocalFileStorage(directories))
        register_analysis_task(huey, runner.run)
        task: Any = huey.dequeue()
        assert task is not None
        assert task.args == (job_id,)

        result = huey.execute(task)

        assert result.job_id == job_id
        assert result.document_id == document_id
        assert result.status is JobStatus.COMPLETED
        assert result.page_count == 2
        assert result.scanned_page_count == 2
        with factory() as session:
            document = session.get(Document, document_id)
            project = session.get(Project, project_id)
            job = session.get(ApplicationJob, job_id)
            pages = tuple(
                session.scalars(
                    select(DocumentPage)
                    .where(DocumentPage.document_id == document_id)
                    .order_by(DocumentPage.source_page_number)
                )
            )
            attempt = session.scalar(select(JobAttempt).where(JobAttempt.job_id == job_id))
        assert document is not None
        assert document.status == DocumentStatus.ANALYZED.value
        assert document.scanned_page_count == 2
        assert project is not None
        assert project.status == ProjectStatus.WAITING_FOR_SETTINGS.value
        assert project.active_document_id == document_id
        assert job is not None
        assert job.status == JobStatus.COMPLETED.value
        assert job.progress == 1.0
        assert attempt is not None
        assert attempt.status == "COMPLETED"
        assert [page.source_page_number for page in pages] == [1, 2]
        assert all(page.page_type == PageType.SCANNED.value for page in pages)
        assert all(page.status == DocumentStatus.ANALYZED.value for page in pages)
    finally:
        huey.storage.close()
        engine.dispose()


def test_analysis_task_persists_digital_blocks_and_translation_segments(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "digital analysis runtime"
    monkeypatch.setenv("TRANSLOKA_DATA_DIR", str(root))
    command.upgrade(Config(str(ALEMBIC_CONFIGURATION)), "head")
    with TestClient(create_app()) as client:
        project_response = client.post("/api/v1/projects", headers=HEADERS, json=PROJECT)
        project_id = cast(str, project_response.json()["data"]["id"])
        response = client.post(
            f"/api/v1/projects/{project_id}/documents/import",
            headers={**HEADERS, "Idempotency-Key": "digital-analysis-runtime"},
            files={"file": ("digital.pdf", _text_pdf_bytes(), "application/pdf")},
            data={"set_as_active": "true"},
        )
        document_id = cast(str, response.json()["data"]["document"]["id"])
        job_id = cast(str, response.json()["data"]["job"]["id"])

    directories = resolve_local_data_directories(root)
    engine = create_sqlite_engine(directories)
    factory = create_session_factory(engine)
    huey = create_huey(resolve_queue_configuration(root))
    try:
        runner = DatabaseAnalysisJobRunner(factory, LocalFileStorage(directories))
        register_analysis_task(huey, runner.run)
        task: Any = huey.dequeue()
        assert task is not None
        assert task.args == (job_id,)
        huey.execute(task)

        with factory() as session:
            page = session.scalar(
                select(DocumentPage).where(DocumentPage.document_id == document_id)
            )
            blocks = tuple(
                session.scalars(
                    select(DocumentBlock)
                    .join(DocumentPage, DocumentPage.id == DocumentBlock.page_id)
                    .where(DocumentPage.document_id == document_id)
                    .order_by(DocumentBlock.page_reading_order)
                )
            )
            segments = tuple(
                session.scalars(
                    select(DocumentSegment)
                    .join(DocumentBlock, DocumentBlock.id == DocumentSegment.block_id)
                    .join(DocumentPage, DocumentPage.id == DocumentBlock.page_id)
                    .where(DocumentPage.document_id == document_id)
                    .order_by(DocumentSegment.global_order)
                )
            )

        assert page is not None
        assert page.page_type == PageType.DIGITAL.value
        assert page.status == DocumentStatus.STRUCTURED.value
        assert blocks
        assert segments
        assert all(segment.native_text == segment.source_text for segment in segments)
        assert all(segment.resolved_source_text for segment in segments)
        assert all(
            segment.status == SegmentStatus.READY_FOR_TRANSLATION.value for segment in segments
        )
        assert "TransLoka digital extraction" in " ".join(
            segment.source_text for segment in segments
        )
    finally:
        huey.storage.close()
        engine.dispose()


def _pdf_bytes(page_count: int) -> bytes:
    destination = BytesIO()
    writer = PdfWriter()
    for _ in range(page_count):
        writer.add_blank_page(width=612, height=792)
    writer.write(destination)
    return destination.getvalue()


def _text_pdf_bytes() -> bytes:
    destination = BytesIO()
    canvas = Canvas(destination, pagesize=(612, 792))
    canvas.setFont("Helvetica-Bold", 18)
    canvas.drawString(72, 720, "TransLoka digital extraction")
    canvas.setFont("Helvetica", 12)
    canvas.drawString(72, 680, "The analysis worker must persist translatable segments.")
    canvas.drawString(72, 660, "This sentence verifies the production runtime path.")
    canvas.save()
    return destination.getvalue()
