from __future__ import annotations

import asyncio
import hashlib
import json
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime
from io import BytesIO
from pathlib import Path
from typing import Any, cast
from uuid import UUID

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from reportlab.lib.pagesizes import letter  # type: ignore[import-untyped]
from reportlab.pdfgen import canvas  # type: ignore[import-untyped]
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session, sessionmaker
from transloka_api.app import create_app
from transloka_api.middleware import (
    CLIENT_HEADER,
    CLIENT_HEADER_VALUE,
    CLIENT_VERSION_HEADER,
    CLIENT_VERSION_VALUE,
)
from transloka_api.routers.review import router as review_router
from transloka_api.routers.segments import router as segments_router
from transloka_api.services.imports import ImportService
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
from transloka_core.database.models.exports import Export, ExportProfile, ExportStatus, ExportType
from transloka_core.database.models.files import FileRole, FileStatus
from transloka_core.database.models.pages import DocumentPage
from transloka_core.database.models.pages import PageType as DatabasePageType
from transloka_core.database.models.projects import (
    DocumentType,
    Project,
    ReconstructionMode,
)
from transloka_core.database.models.projects import (
    TranslationStyle as ProjectTranslationStyle,
)
from transloka_core.database.models.revisions import SegmentRevision
from transloka_core.database.models.translation import SegmentTranslation
from transloka_core.repositories.files import StoredFilesRepository
from transloka_core.repositories.projects import ProjectsRepository
from transloka_core.storage import resolve_local_data_directories
from transloka_core.storage.local import LocalFileStorage
from transloka_documents.analysis import analyze_pdf
from transloka_documents.extraction import extract_digital_text
from transloka_documents.extraction.models import TextGeometry
from transloka_documents.validation import PdfValidationLimits, validate_pdf
from transloka_glossary.protection import ProtectedContentDetector
from transloka_glossary.snapshots import create_glossary_snapshot
from transloka_quality.pdf import validate_final_pdf
from transloka_translation.orchestration import (
    SqlAlchemyTranslationRunStore,
    TranslationOperation,
    TranslationOrchestrator,
    TranslationSegmentInput,
)
from transloka_translation.prompts import TranslationPrompt
from transloka_translation.providers.fake import FakeTranslationProvider
from transloka_translation.schemas import TranslationContext, TranslationStyle

REPOSITORY_ROOT = Path(__file__).parents[3]
ALEMBIC_CONFIGURATION = REPOSITORY_ROOT / "alembic.ini"
CREATED_AT = "2026-08-23T00:00:00.000Z"
CREATED_AT_DATETIME = datetime(2026, 8, 23, tzinfo=UTC)
CLIENT_HEADERS = {
    CLIENT_HEADER: CLIENT_HEADER_VALUE,
    CLIENT_VERSION_HEADER: CLIENT_VERSION_VALUE,
}


def _id(prefix: str, value: int) -> str:
    return f"{prefix}{UUID(int=value)}"


PROJECT_ID = _id("prj_", 1201)
DOCUMENT_ID = _id("doc_", 1202)
PAGE_ID = _id("pag_", 1203)
BLOCK_ID = _id("blk_", 1204)
SEGMENT_ID = _id("seg_", 1205)
EXPORT_ID = _id("exp_", 1206)
EXPORT_FILE_ID = _id("fil_", 1207)


@dataclass(frozen=True, slots=True)
class DigitalWorkflowContext:
    pdf: bytes
    engine: Engine
    factory: sessionmaker[Session]
    storage: LocalFileStorage
    original_storage_key: str
    glossary_snapshot_id: str


@pytest.fixture
def digital_workflow(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> Iterator[DigitalWorkflowContext]:
    root = tmp_path / "digital pdf e2e"
    monkeypatch.setenv("TRANSLOKA_DATA_DIR", str(root))
    command.upgrade(Config(str(ALEMBIC_CONFIGURATION)), "head")
    directories = resolve_local_data_directories(root)
    engine = create_sqlite_engine(directories)
    factory = create_session_factory(engine)
    storage = LocalFileStorage(directories)
    pdf = _digital_pdf()

    with transaction_scope(factory) as session:
        ProjectsRepository(session).create(
            project_id=PROJECT_ID,
            name="Digital workflow",
            description=None,
            source_language="en",
            target_language="id",
            document_type=DocumentType.TECHNICAL_BOOK,
            translation_style=ProjectTranslationStyle.PROFESSIONAL,
            reconstruction_mode=ReconstructionMode.HYBRID,
            created_at=CREATED_AT,
        )

    importer = ImportService(storage, max_upload_bytes=2_000_000)
    staged = importer.stage_upload(
        project_id=PROJECT_ID,
        original_filename="digital-source.pdf",
        idempotency_key="digital-workflow-import",
        set_as_active=True,
        stream=BytesIO(pdf),
    )
    validation = validate_pdf(
        BytesIO(pdf),
        filename="digital-source.pdf",
        mime_type="application/pdf",
        limits=PdfValidationLimits(max_bytes=2_000_000, max_pages=10, max_objects=10_000),
    )
    analysis = analyze_pdf(BytesIO(pdf))
    extracted = extract_digital_text(BytesIO(pdf))
    extracted_page = extracted.pages[0]
    extracted_block = extracted_page.block_candidates[0]

    with transaction_scope(factory) as session:
        original = importer.store_original(staged, validation, StoredFilesRepository(session))
        session.add(
            Document(
                id=DOCUMENT_ID,
                project_id=PROJECT_ID,
                original_file_id=original.id,
                ir_version="0.1",
                title=analysis.title,
                author=analysis.author,
                document_type=DocumentType.TECHNICAL_BOOK.value,
                document_class=DocumentClass.DIGITAL_PDF.value,
                source_language="en",
                target_language="id",
                page_count=analysis.page_count,
                word_count_estimate=None,
                has_text_layer=1,
                scanned_page_count=0,
                image_count=0,
                table_count=0,
                status=DocumentStatus.STRUCTURED.value,
                metadata_json=None,
                analysis_json=json.dumps({"page_count": analysis.page_count}),
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
                width_points=extracted_page.width_points,
                height_points=extracted_page.height_points,
                rotation_degrees=0.0,
                page_type=DatabasePageType.DIGITAL.value,
                page_classification="SINGLE_COLUMN",
                column_count=1,
                reading_direction="LTR",
                status=DocumentStatus.STRUCTURED.value,
                render_file_id=None,
                thumbnail_file_id=None,
                native_extraction_confidence=1.0,
                ocr_confidence=None,
                structure_confidence=0.95,
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
                page_reading_order=1,
                global_reading_order=1,
                source_text=extracted_block.source_text,
                normalized_source_text=extracted_block.normalized_text,
                source_geometry_json=_geometry_json(extracted_block.geometry),
                target_geometry_json=None,
                style_json=None,
                detail_json=None,
                status=DocumentStatus.READY_FOR_TRANSLATION.value,
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
                segment_order=1,
                global_order=1,
                source_text=extracted_block.source_text,
                native_text=None,
                ocr_text=None,
                resolved_source_text=extracted_block.normalized_text,
                normalized_source_text=extracted_block.normalized_text,
                protected_source_text=None,
                machine_translation=None,
                reviewed_translation=None,
                final_text=None,
                source_language="en",
                target_language="id",
                status=SegmentStatus.READY_FOR_TRANSLATION.value,
                review_status=ReviewStatus.NOT_REVIEWED.value,
                is_locked=0,
                current_revision=0,
                confidence_overall=0.99,
                confidence_json=None,
                translation_settings_hash=None,
                created_at=CREATED_AT,
                updated_at=CREATED_AT,
            )
        )
        session.flush()
        project = session.get(Project, PROJECT_ID)
        assert project is not None
        project.active_document_id = DOCUMENT_ID
        snapshot = create_glossary_snapshot(
            session=session,
            storage=storage,
            project_id=PROJECT_ID,
            document_id=DOCUMENT_ID,
            created_at=CREATED_AT_DATETIME,
        )
        original_storage_key = original.storage_key

    try:
        yield DigitalWorkflowContext(
            pdf=pdf,
            engine=engine,
            factory=factory,
            storage=storage,
            original_storage_key=original_storage_key,
            glossary_snapshot_id=snapshot.id,
        )
    finally:
        engine.dispose()


def test_digital_pdf_workflow_reaches_downloadable_export_without_mutating_original(
    digital_workflow: DigitalWorkflowContext,
) -> None:
    context = digital_workflow
    extracted = extract_digital_text(BytesIO(context.pdf))
    source_text = extracted.pages[0].block_candidates[0].normalized_text
    assert source_text == "Use API_KEY in the workflow."

    detector = ProtectedContentDetector()
    protected = detector.protect(source_text)
    assert any(item.source_value == "API_KEY" for item in protected.inventory)
    translated_protected = protected.text.replace("Use", "Gunakan").replace(
        "in the workflow", "dalam alur kerja"
    )
    provider: FakeTranslationProvider[TranslationPrompt, str] = FakeTranslationProvider(
        response=json.dumps(
            {
                "segments": [
                    {
                        "segment_id": SEGMENT_ID,
                        "translated_text": translated_protected,
                    }
                ]
            }
        )
    )
    operation = TranslationOperation(
        project_id=PROJECT_ID,
        document_id=DOCUMENT_ID,
        section_id=None,
        glossary_snapshot_id=context.glossary_snapshot_id,
        provider_type="fake",
        model_id="fake-digital-model",
        idempotency_key="translation-digital-workflow",
        context=TranslationContext(source_language="en", target_language="id"),
        segments=(
            TranslationSegmentInput(
                segment_id=SEGMENT_ID,
                source_text=source_text,
                page_order=1,
                block_order=1,
                segment_order=1,
            ),
        ),
        style=TranslationStyle.PROFESSIONAL,
    )
    translation_run = asyncio.run(
        TranslationOrchestrator(
            provider,
            SqlAlchemyTranslationRunStore(context.factory),
        ).run(operation)
    )
    assert translation_run.successful is True
    assert translation_run.completed_segment_ids == (SEGMENT_ID,)
    assert len(provider.requests) == 1
    prompt = provider.requests[0]
    prompt_source = cast(dict[str, Any], prompt.source_data)["source_data"]
    prompt_segment = cast(list[dict[str, str]], cast(dict[str, Any], prompt_source)["segments"])[0]
    assert "API_KEY" not in prompt_segment["source_text"]
    assert "__TLK_CODE_" in prompt_segment["source_text"]

    with transaction_scope(context.factory) as session:
        stored_translation = session.scalar(
            select(SegmentTranslation)
            .where(SegmentTranslation.segment_id == SEGMENT_ID)
            .order_by(SegmentTranslation.created_at.desc())
        )
        assert stored_translation is not None
        approved_text = stored_translation.translated_text_restored
        assert approved_text == "Gunakan API_KEY dalam alur kerja."
        segment = session.get(DocumentSegment, SEGMENT_ID)
        assert segment is not None
        assert segment.machine_translation == approved_text
        assert segment.status == SegmentStatus.MACHINE_TRANSLATED.value
        assert segment.review_status == ReviewStatus.NOT_REVIEWED.value
        segment.protected_source_text = protected.text
        segment.machine_translation = approved_text
        segment.status = SegmentStatus.NEEDS_REVIEW.value
        segment.review_status = ReviewStatus.REVIEW_REQUIRED.value

    application = create_app()
    application.include_router(segments_router)
    application.include_router(review_router)
    with TestClient(application) as client:
        queue = client.get(f"/api/v1/projects/{PROJECT_ID}/review-queue", headers=CLIENT_HEADERS)
        assert queue.status_code == 200, queue.text
        assert [item["segment"]["id"] for item in queue.json()["data"]] == [SEGMENT_ID]

        edit = client.patch(
            f"/api/v1/segments/{SEGMENT_ID}/translation",
            headers=CLIENT_HEADERS,
            json={
                "reviewed_translation": approved_text,
                "expected_revision": 0,
                "reason": "Reviewed digital translation.",
            },
        )
        assert edit.status_code == 200, edit.text
        assert edit.json()["data"]["review_status"] == "EDITED"

        approve = client.post(
            f"/api/v1/segments/{SEGMENT_ID}/approve",
            headers=CLIENT_HEADERS,
            json={"expected_revision": 1},
        )
        assert approve.status_code == 200, approve.text
        assert approve.json()["data"]["review_status"] == "APPROVED"

    with transaction_scope(context.factory) as session:
        segment = session.get(DocumentSegment, SEGMENT_ID)
        assert segment is not None
        assert segment.resolved_source_text == source_text
        assert segment.final_text == approved_text
        assert segment.review_status == ReviewStatus.APPROVED.value
        assert segment.current_revision == 2
        revision = session.scalar(
            select(SegmentRevision).where(
                SegmentRevision.segment_id == SEGMENT_ID,
                SegmentRevision.revision_number == 2,
            )
        )
        assert revision is not None

    export_pdf = _export_pdf(approved_text)
    validation_report = validate_final_pdf(
        BytesIO(export_pdf),
        expected_page_count=1,
        required_segments=(approved_text,),
        source_residue=("Use", "workflow"),
        require_selectable_text=True,
    )
    validation_report.raise_for_completion()
    assert validation_report.is_valid is True

    export_storage_key = f"projects/{PROJECT_ID}/exports/{EXPORT_ID}.pdf"
    temporary = context.storage.write_temporary(BytesIO(export_pdf))
    committed = context.storage.commit(temporary, export_storage_key, immutable=True)
    with transaction_scope(context.factory) as session:
        StoredFilesRepository(session).create(
            file_id=EXPORT_FILE_ID,
            project_id=PROJECT_ID,
            document_id=DOCUMENT_ID,
            file_role=FileRole.EXPORT,
            storage_key=committed.storage_key,
            original_filename="digital-export.pdf",
            safe_filename="digital-export.pdf",
            mime_type="application/pdf",
            size_bytes=committed.size_bytes,
            checksum_sha256=committed.checksum_sha256,
            is_immutable=True,
            status=FileStatus.VALIDATED,
            metadata={"validation_report": validation_report.completion_status},
            created_at=CREATED_AT,
        )
        session.add(
            Export(
                id=EXPORT_ID,
                project_id=PROJECT_ID,
                document_id=DOCUMENT_ID,
                reconstruction_job_id=None,
                file_id=EXPORT_FILE_ID,
                export_type=ExportType.TRANSLATED_PDF.value,
                output_profile=ExportProfile.STANDARD.value,
                version_number=1,
                status=ExportStatus.COMPLETED.value,
                page_count=validation_report.page_count,
                size_bytes=validation_report.size_bytes,
                checksum_sha256=validation_report.checksum_sha256,
                validation_report_id="val_digital_workflow",
                settings_json="{}",
                created_at=CREATED_AT,
                completed_at=CREATED_AT,
                error_code=None,
            )
        )

    with context.storage.open_read(export_storage_key) as exported:
        downloaded = exported.read()
    assert downloaded == export_pdf
    assert hashlib.sha256(downloaded).hexdigest() == validation_report.checksum_sha256

    with context.storage.open_read(context.original_storage_key) as original:
        assert original.read() == context.pdf


def _geometry_json(geometry: TextGeometry) -> str:
    return json.dumps(
        {
            "coordinate_system": geometry.coordinate_system,
            "x": geometry.x,
            "y": geometry.y,
            "width": geometry.width,
            "height": geometry.height,
        },
        separators=(",", ":"),
        sort_keys=True,
    )


def _digital_pdf() -> bytes:
    output = BytesIO()
    pdf = canvas.Canvas(output, pagesize=letter)
    pdf.drawString(72, 720, "Use API_KEY in the workflow.")
    pdf.save()
    return output.getvalue()


def _export_pdf(text: str) -> bytes:
    output = BytesIO()
    pdf = canvas.Canvas(output, pagesize=letter)
    pdf.drawString(72, 720, text)
    pdf.save()
    return output.getvalue()
