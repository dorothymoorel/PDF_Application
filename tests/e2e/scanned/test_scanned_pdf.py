from __future__ import annotations

import asyncio
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
from PIL import Image
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session, sessionmaker
from transloka_api.app import create_app
from transloka_api.middleware import (
    CLIENT_HEADER,
    CLIENT_HEADER_VALUE,
    CLIENT_VERSION_HEADER,
    CLIENT_VERSION_VALUE,
)
from transloka_api.routers.ocr import router as ocr_router
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
from transloka_core.database.models.glossary import (
    GlossaryMatchMode,
    GlossaryRuleType,
    GlossaryScope,
)
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
from transloka_core.database.models.translation import (
    SegmentTranslation,
    TranslationBatch,
)
from transloka_core.repositories.files import StoredFilesRepository
from transloka_core.repositories.projects import ProjectsRepository
from transloka_core.storage import resolve_local_data_directories
from transloka_core.storage.local import LocalFileStorage
from transloka_documents.analysis import analyze_pdf
from transloka_documents.extraction import extract_digital_text
from transloka_documents.ocr import (
    FakeOCRProvider,
    OCRGeometry,
    OCRResult,
    OCRSettings,
    OCRTextBlock,
)
from transloka_documents.ocr.detection import detect_scanned_page
from transloka_documents.ocr.normalization import normalize_ocr_result
from transloka_documents.ocr.orchestration import (
    OCRPageOrchestrator,
    OCRPageRequest,
    OCRRawOutputStore,
)
from transloka_documents.validation import PdfValidationLimits, validate_pdf
from transloka_glossary import GlossaryRepository
from transloka_glossary.snapshots import create_glossary_snapshot
from transloka_translation.orchestration import (
    SqlAlchemyTranslationRunStore,
    TranslationOperation,
    TranslationOrchestrator,
    TranslationSegmentInput,
)
from transloka_translation.prompts import TranslationPrompt
from transloka_translation.schemas import (
    TranslationContext,
    TranslationGlossaryEntry,
    TranslationStyle,
)

REPOSITORY_ROOT = Path(__file__).parents[3]
ALEMBIC_CONFIGURATION = REPOSITORY_ROOT / "alembic.ini"
CREATED_AT = "2026-08-20T00:00:00.000Z"
CREATED_AT_DATETIME = datetime(2026, 8, 20, tzinfo=UTC)
CLIENT_HEADERS = {
    CLIENT_HEADER: CLIENT_HEADER_VALUE,
    CLIENT_VERSION_HEADER: CLIENT_VERSION_VALUE,
}


def _id(prefix: str, value: int) -> str:
    return f"{prefix}{UUID(int=value)}"


PROJECT_ID = _id("prj_", 901)
DOCUMENT_ID = _id("doc_", 902)
PAGE_ID = _id("pag_", 903)
BLOCK_ID = _id("blk_", 904)
SEGMENT_ID = _id("seg_", 905)
GLOSSARY_ID = _id("gls_", 906)
TERM_ID = _id("trm_", 907)
TERM_REVISION_ID = _id("grv_", 908)


@dataclass(frozen=True, slots=True)
class ScannedWorkflowContext:
    root: Path
    pdf: bytes
    engine: Engine
    factory: sessionmaker[Session]
    storage: LocalFileStorage
    original_storage_key: str


@pytest.fixture
def scanned_workflow(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> Iterator[ScannedWorkflowContext]:
    root = tmp_path / "scanned pdf e2e"
    monkeypatch.setenv("TRANSLOKA_DATA_DIR", str(root))
    command.upgrade(Config(str(ALEMBIC_CONFIGURATION)), "head")
    directories = resolve_local_data_directories(root)
    engine = create_sqlite_engine(directories)
    factory = create_session_factory(engine)
    storage = LocalFileStorage(directories)
    pdf = _image_only_pdf()

    with transaction_scope(factory) as session:
        ProjectsRepository(session).create(
            project_id=PROJECT_ID,
            name="Scanned workflow",
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
        original_filename="scanned-source.pdf",
        idempotency_key="scanned-workflow-import",
        set_as_active=True,
        stream=BytesIO(pdf),
    )
    validation = validate_pdf(
        BytesIO(pdf),
        filename="scanned-source.pdf",
        mime_type="application/pdf",
        limits=PdfValidationLimits(max_bytes=2_000_000, max_pages=10, max_objects=10_000),
    )
    with transaction_scope(factory) as session:
        original = importer.store_original(staged, validation, StoredFilesRepository(session))
        analysis = analyze_pdf(BytesIO(pdf))
        session.add(
            Document(
                id=DOCUMENT_ID,
                project_id=PROJECT_ID,
                original_file_id=original.id,
                ir_version="0.1",
                title=analysis.title,
                author=analysis.author,
                document_type=DocumentType.TECHNICAL_BOOK.value,
                document_class=DocumentClass.SCANNED_PDF.value,
                source_language="en",
                target_language="id",
                page_count=analysis.page_count,
                word_count_estimate=None,
                has_text_layer=0,
                scanned_page_count=analysis.page_count,
                image_count=1,
                table_count=0,
                status=DocumentStatus.ANALYZED.value,
                metadata_json=None,
                analysis_json=json.dumps({"page_count": analysis.page_count}),
                created_at=CREATED_AT,
                updated_at=CREATED_AT,
            )
        )
        session.flush()
        project_row = session.get(Project, PROJECT_ID)
        assert project_row is not None
        project_row.active_document_id = DOCUMENT_ID
        original_storage_key = original.storage_key

    context = ScannedWorkflowContext(
        root=root,
        pdf=pdf,
        engine=engine,
        factory=factory,
        storage=storage,
        original_storage_key=original_storage_key,
    )
    try:
        yield context
    finally:
        engine.dispose()


def test_scanned_pdf_workflow_reaches_review_without_mutating_original(
    scanned_workflow: ScannedWorkflowContext,
) -> None:
    context = scanned_workflow
    analysis = analyze_pdf(BytesIO(context.pdf))
    extracted = extract_digital_text(BytesIO(context.pdf))
    detection = detect_scanned_page(
        extracted.pages[0],
        image_coverage=1.0,
        image_has_text_signal=True,
        native_confidence=0.0,
    )
    assert detection.page_type.value == "SCANNED"
    assert detection.requires_ocr is True

    with transaction_scope(context.factory) as session:
        session.add(
            DocumentPage(
                id=PAGE_ID,
                document_id=DOCUMENT_ID,
                source_page_number=1,
                logical_page_number="1",
                width_points=analysis.pages[0].width_points,
                height_points=analysis.pages[0].height_points,
                rotation_degrees=float(analysis.pages[0].rotation_degrees),
                page_type=DatabasePageType.SCANNED.value,
                page_classification="SINGLE_COLUMN",
                column_count=1,
                reading_direction="LTR",
                status=DocumentStatus.STRUCTURED.value,
                render_file_id=None,
                thumbnail_file_id=None,
                native_extraction_confidence=None,
                ocr_confidence=0.91,
                structure_confidence=0.90,
                metadata_json=None,
                created_at=CREATED_AT,
                updated_at=CREATED_AT,
            )
        )

    ocr_result = OCRResult(
        page_number=1,
        text="Translatoin engine uses workflow.",
        blocks=(
            OCRTextBlock(
                text="Translatoin engine uses workflow.",
                geometry=OCRGeometry(x=72, y=120, width=300, height=24),
                confidence=0.91,
            ),
        ),
        confidence=0.91,
        settings=OCRSettings(language="en"),
        provider="fake-scanned-provider",
    )
    ocr_provider = FakeOCRProvider(result=ocr_result)
    ocr_run = OCRPageRequest.for_auto_pages(
        job_id="job_scanned-workflow",
        project_id=PROJECT_ID,
        document_id=DOCUMENT_ID,
        source_pdf=context.pdf,
        detections=(detection,),
    )
    ocr_output = OCRRawOutputStore(context.storage, context.factory)
    run = OCRPageOrchestrator(
        ocr_provider,
        context.storage,
        raw_output_store=ocr_output,
    ).run(ocr_run)
    assert run.completed_page_numbers == (1,)
    assert len(ocr_provider.requests) == 1
    raw_path = context.root / Path(run.outputs[0].raw_output.storage_key)
    assert json.loads(raw_path.read_text(encoding="utf-8"))["text"] == ocr_result.text

    normalized = normalize_ocr_result(run.outputs[0].result)
    assert normalized.segments
    normalized_block = normalized.blocks[0]
    normalized_segment = normalized.segments[0]
    with transaction_scope(context.factory) as session:
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
                source_text=normalized_block.source_text,
                normalized_source_text=normalized_block.normalized_source_text,
                source_geometry_json=_geometry_json(normalized_block.geometry),
                target_geometry_json=None,
                style_json=None,
                detail_json=None,
                status=DocumentStatus.READY_FOR_TRANSLATION.value,
                confidence=normalized_block.confidence,
                created_at=CREATED_AT,
                updated_at=CREATED_AT,
            )
        )
        session.add(
            DocumentSegment(
                id=SEGMENT_ID,
                block_id=BLOCK_ID,
                section_id=None,
                segment_order=1,
                global_order=1,
                source_text=normalized_segment.source_text,
                native_text=None,
                ocr_text=ocr_result.text,
                resolved_source_text=normalized_segment.normalized_source_text,
                normalized_source_text=normalized_segment.normalized_source_text,
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
                confidence_overall=normalized_segment.confidence,
                confidence_json=None,
                translation_settings_hash=None,
                created_at=CREATED_AT,
                updated_at=CREATED_AT,
            )
        )

    application = create_app()
    application.include_router(ocr_router)
    application.include_router(segments_router)
    application.include_router(review_router)
    with TestClient(application) as client:
        ocr_page = client.get(f"/api/v1/pages/{PAGE_ID}/ocr", headers=CLIENT_HEADERS)
        assert ocr_page.status_code == 200, ocr_page.text
        assert ocr_page.json()["data"]["raw_text"] == ocr_result.text

        correction = client.patch(
            f"/api/v1/segments/{SEGMENT_ID}/source-resolution",
            headers=CLIENT_HEADERS,
            json={
                "resolved_source_text": "Translation engine uses workflow.",
                "resolution_source": "MANUAL",
                "expected_revision": 0,
                "reason": "Corrected the OCR spelling.",
            },
        )
        assert correction.status_code == 200, correction.text
        assert correction.json()["data"]["raw_ocr_text"] == ocr_result.text
        assert correction.json()["data"]["resolved_source_text"] == (
            "Translation engine uses workflow."
        )

    with transaction_scope(context.factory) as session:
        repository = GlossaryRepository(session)
        repository.create_glossary(
            glossary_id=GLOSSARY_ID,
            project_id=PROJECT_ID,
            name="Scanned terms",
            description=None,
            source_language="en",
            target_language="id",
            scope=GlossaryScope.PROJECT,
            domain=None,
            is_default=True,
            created_at=CREATED_AT,
        )
        repository.create_term(
            term_id=TERM_ID,
            revision_id=TERM_REVISION_ID,
            glossary_id=GLOSSARY_ID,
            source_term="workflow",
            rule_type=GlossaryRuleType.TRANSLATE_AS,
            target_term="alur kerja",
            scope=GlossaryScope.PROJECT,
            scope_reference_id=PROJECT_ID,
            priority=100,
            case_sensitive=False,
            whole_word=True,
            match_mode=GlossaryMatchMode.PHRASE,
            capitalization_policy="PRESERVE_SOURCE_CASE",
            inflection_policy="USE_BASE_TERM",
            first_use_policy="NONE",
            confidence=1.0,
            notes=None,
            created_at=CREATED_AT,
        )
        snapshot = create_glossary_snapshot(
            session=session,
            storage=context.storage,
            project_id=PROJECT_ID,
            document_id=DOCUMENT_ID,
            created_at=CREATED_AT_DATETIME,
        )

    with context.factory() as session:
        segment = session.get(DocumentSegment, SEGMENT_ID)
        assert segment is not None
        glossary_entries = tuple(
            TranslationGlossaryEntry(
                source_term=rule.source_term,
                target_term=rule.target_term,
                rule_type=rule.rule_type.value,
            )
            for rule in snapshot.compiled.rules
        )
        operation = TranslationOperation(
            project_id=PROJECT_ID,
            document_id=DOCUMENT_ID,
            section_id=None,
            glossary_snapshot_id=snapshot.id,
            provider_type="fake",
            model_id="fake-scanned-model",
            idempotency_key="translation-scanned-workflow",
            context=TranslationContext(source_language="en", target_language="id"),
            segments=(
                TranslationSegmentInput(
                    segment_id=SEGMENT_ID,
                    source_text=segment.resolved_source_text,
                    page_order=1,
                    block_order=1,
                    segment_order=1,
                ),
            ),
            glossary=glossary_entries,
            style=TranslationStyle.PROFESSIONAL,
        )

    translation_provider = _GlossaryAwareProvider()
    translation_run = asyncio.run(
        TranslationOrchestrator(
            translation_provider,
            SqlAlchemyTranslationRunStore(context.factory),
        ).run(operation)
    )
    assert translation_run.successful is True
    assert translation_run.completed_segment_ids == (SEGMENT_ID,)
    assert translation_provider.glossary_terms == ("workflow",)

    with transaction_scope(context.factory) as session:
        stored_translation = session.scalar(
            select(SegmentTranslation)
            .where(SegmentTranslation.segment_id == SEGMENT_ID)
            .order_by(SegmentTranslation.created_at.desc())
        )
        assert stored_translation is not None
        assert stored_translation.translated_text_restored == (
            "Mesin terjemahan memakai alur kerja."
        )
        segment = session.get(DocumentSegment, SEGMENT_ID)
        assert segment is not None
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
                "reviewed_translation": "Mesin terjemahan memakai alur kerja.",
                "expected_revision": 1,
                "reason": "Reviewed scanned translation.",
            },
        )
        assert edit.status_code == 200, edit.text
        assert edit.json()["data"]["review_status"] == "EDITED"

        approve = client.post(
            f"/api/v1/segments/{SEGMENT_ID}/approve",
            headers=CLIENT_HEADERS,
            json={"expected_revision": 2},
        )
        assert approve.status_code == 200, approve.text
        assert approve.json()["data"]["review_status"] == "APPROVED"

        empty_queue = client.get(
            f"/api/v1/projects/{PROJECT_ID}/review-queue",
            headers=CLIENT_HEADERS,
        )
        assert empty_queue.status_code == 200, empty_queue.text
        assert empty_queue.json()["data"] == []

    with context.factory() as session:
        segment = session.get(DocumentSegment, SEGMENT_ID)
        assert segment is not None
        assert segment.resolved_source_text == "Translation engine uses workflow."
        assert segment.reviewed_translation == "Mesin terjemahan memakai alur kerja."
        assert segment.review_status == ReviewStatus.APPROVED.value
        assert (
            session.scalar(
                select(TranslationBatch).where(TranslationBatch.id == translation_run.run_id)
            )
            is not None
        )
        revision_texts = list(
            session.scalars(
                select(SegmentRevision.new_text)
                .where(SegmentRevision.segment_id == SEGMENT_ID)
                .order_by(SegmentRevision.revision_number)
            )
        )
        assert revision_texts == [
            "Translation engine uses workflow.",
            "Mesin terjemahan memakai alur kerja.",
            "Mesin terjemahan memakai alur kerja.",
        ]

    with context.storage.open_read(context.original_storage_key) as original:
        assert original.read() == context.pdf


class _GlossaryAwareProvider:
    def __init__(self) -> None:
        self.glossary_terms: tuple[str, ...] = ()

    async def translate(self, request: object, *, cancellation: object = None) -> str:
        del cancellation
        prompt = cast(TranslationPrompt, request)
        envelope = cast(dict[str, Any], prompt.source_data)
        source_data = cast(dict[str, Any], envelope["source_data"])
        glossary = cast(list[dict[str, Any]], source_data["glossary"])
        self.glossary_terms = tuple(str(entry["source_term"]) for entry in glossary)
        segments = cast(list[dict[str, str]], source_data["segments"])
        return json.dumps(
            {
                "segments": [
                    {
                        "segment_id": segments[0]["segment_id"],
                        "translated_text": "Mesin terjemahan memakai alur kerja.",
                    }
                ]
            }
        )


def _geometry_json(geometry: OCRGeometry) -> str:
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


def _image_only_pdf() -> bytes:
    output = BytesIO()
    image = Image.new("RGB", (612, 792), "white")
    try:
        image.save(output, format="PDF")
    finally:
        image.close()
    return output.getvalue()
