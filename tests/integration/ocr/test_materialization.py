from __future__ import annotations

import json
from collections.abc import Iterator
from io import BytesIO
from pathlib import Path
from uuid import UUID

import pytest
from alembic import command
from alembic.config import Config
from pypdf import PdfWriter
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session, sessionmaker
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
from transloka_core.database.models.files import FileRole, FileStatus, StoredFile
from transloka_core.database.models.jobs import ApplicationJob, JobStatus, JobType
from transloka_core.database.models.pages import DocumentPage, PageType
from transloka_core.database.models.projects import (
    DocumentType,
    Project,
    ProjectStatus,
    ReconstructionMode,
    TranslationStyle,
)
from transloka_core.storage import resolve_local_data_directories
from transloka_core.storage.local import LocalFileStorage
from transloka_documents.ocr import (
    OCRGeometry,
    OCRHealth,
    OCRHealthStatus,
    OCRPage,
    OCRProviderError,
    OCRProviderErrorCode,
    OCRResult,
    OCRSettings,
    OCRTextBlock,
)
from transloka_documents.ocr.orchestration import (
    OCRPageOrchestrator,
    OCRPageRequest,
    OCRRunResult,
)
from transloka_worker.ocr import OCRJobRunner
from transloka_worker.ocr_materialization import OCRMaterializationError

REPOSITORY_ROOT = Path(__file__).parents[3]
ALEMBIC_CONFIGURATION = REPOSITORY_ROOT / "alembic.ini"
NOW = "2026-09-09T00:00:00.000Z"


def _id(prefix: str, value: int) -> str:
    return f"{prefix}{UUID(int=value)}"


class ScriptedProvider:
    def __init__(
        self,
        results: dict[int, OCRResult],
        *,
        failing_pages: frozenset[int] = frozenset(),
    ) -> None:
        self._results = results
        self._failing_pages = failing_pages

    def health_check(self) -> OCRHealth:
        return OCRHealth(status=OCRHealthStatus.AVAILABLE, provider="materialization-test")

    def analyze_page(self, page: OCRPage, *, settings: OCRSettings | None = None) -> OCRResult:
        if page.page_number in self._failing_pages:
            raise OCRProviderError(
                OCRProviderErrorCode.INVALID_REQUEST, "OCR provider rejected page", retryable=False
            )
        return self._results[page.page_number]


@pytest.fixture
def materialization_environment(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> Iterator[tuple[Path, sessionmaker[Session], LocalFileStorage]]:
    root = tmp_path / "ocr materialization"
    monkeypatch.setenv("TRANSLOKA_DATA_DIR", str(root))
    command.upgrade(Config(str(ALEMBIC_CONFIGURATION)), "head")
    engine: Engine = create_sqlite_engine(resolve_local_data_directories(root))
    try:
        yield (
            root,
            create_session_factory(engine),
            LocalFileStorage(resolve_local_data_directories(root)),
        )
    finally:
        engine.dispose()


def test_runner_materializes_normalized_ocr_and_pixel_geometry(
    materialization_environment: tuple[Path, sessionmaker[Session], LocalFileStorage],
) -> None:
    root, factory, storage = materialization_environment
    project_id, document_id, page_ids = _seed_document(factory, value=1, page_count=1)
    job_id = _seed_job(factory, value=10, project_id=project_id, document_id=document_id)
    raw_text = " Raw   OCR\nline "

    _run(
        root,
        factory,
        storage,
        _request(job_id, project_id, document_id, (1,), dpi=144),
        {
            1: _result(
                1,
                raw_text,
                confidence=0.4,
                geometry=OCRGeometry(
                    x=20,
                    y=40,
                    width=200,
                    height=80,
                    coordinate_system="PIXEL_TOP_LEFT",
                ),
            )
        },
    )

    with factory() as session:
        page = session.get(DocumentPage, page_ids[1])
        block = session.scalar(select(DocumentBlock))
        segment = session.scalar(select(DocumentSegment))
        assert page is not None
        assert block is not None
        assert segment is not None
        assert page.status == DocumentStatus.STRUCTURED.value
        assert page.ocr_confidence == pytest.approx(0.4)
        assert page.structure_confidence == pytest.approx(0.4)
        assert block.source_text == "Raw OCR\nline"
        assert block.normalized_source_text == "Raw OCR line"
        assert json.loads(block.source_geometry_json) == {
            "coordinate_system": "PDF_POINT_TOP_LEFT",
            "height": 40.0,
            "width": 100.0,
            "x": 10.0,
            "y": 20.0,
        }
        assert segment.ocr_text == "Raw OCR\nline"
        assert segment.resolved_source_text == "Raw OCR line"
        assert segment.review_status == ReviewStatus.REVIEW_REQUIRED.value

    raw_output = next((root / "projects" / project_id / "ocr" / "raw").rglob("*.json"))
    assert json.loads(raw_output.read_text(encoding="utf-8"))["text"] == raw_text


def test_repeated_new_job_never_duplicates_or_overwrites_existing_edits(
    materialization_environment: tuple[Path, sessionmaker[Session], LocalFileStorage],
) -> None:
    root, factory, storage = materialization_environment
    project_id, document_id, _page_ids = _seed_document(factory, value=20, page_count=1)
    first_job = _seed_job(factory, value=21, project_id=project_id, document_id=document_id)
    request = _request(first_job, project_id, document_id, (1,))
    _run(root, factory, storage, request, {1: _result(1, "First OCR")})

    with transaction_scope(factory) as session:
        segment = session.scalar(select(DocumentSegment))
        assert segment is not None
        segment.source_text = "Reviewer preserved source"
        segment.resolved_source_text = "Reviewer preserved source"
        segment.review_status = ReviewStatus.EDITED.value
        segment.reviewed_translation = "Terjemahan yang ditinjau"
        segment.final_text = "Terjemahan final"
        segment.is_locked = 1

    second_job = _seed_job(factory, value=22, project_id=project_id, document_id=document_id)
    _run(
        root,
        factory,
        storage,
        _request(second_job, project_id, document_id, (1,)),
        {1: _result(1, "Replacement OCR")},
    )

    with factory() as session:
        assert len(list(session.scalars(select(DocumentBlock)))) == 1
        segments = list(session.scalars(select(DocumentSegment)))
        assert len(segments) == 1
        assert segments[0].source_text == "Reviewer preserved source"
        assert segments[0].ocr_text == "First OCR"
        assert segments[0].review_status == ReviewStatus.EDITED.value
        assert segments[0].reviewed_translation == "Terjemahan yang ditinjau"
        assert segments[0].final_text == "Terjemahan final"
        assert segments[0].is_locked == 1
        job = session.get(ApplicationJob, second_job)
        assert job is not None
        assert job.status == JobStatus.COMPLETED.value


def test_identical_ocr_ids_are_page_scoped_across_documents(
    materialization_environment: tuple[Path, sessionmaker[Session], LocalFileStorage],
) -> None:
    root, factory, storage = materialization_environment
    first_project, first_document, _ = _seed_document(factory, value=30, page_count=1)
    second_project, second_document, _ = _seed_document(factory, value=40, page_count=1)
    first_job = _seed_job(factory, value=31, project_id=first_project, document_id=first_document)
    second_job = _seed_job(
        factory, value=41, project_id=second_project, document_id=second_document
    )
    identical = {1: _result(1, "Same OCR identifiers")}

    _run(
        root, factory, storage, _request(first_job, first_project, first_document, (1,)), identical
    )
    _run(
        root,
        factory,
        storage,
        _request(second_job, second_project, second_document, (1,)),
        identical,
    )

    with factory() as session:
        blocks = list(session.scalars(select(DocumentBlock).order_by(DocumentBlock.id)))
        segments = list(session.scalars(select(DocumentSegment).order_by(DocumentSegment.id)))
        assert len(blocks) == 2
        assert len(segments) == 2
        assert len({block.id for block in blocks}) == 2
        assert len({segment.id for segment in segments}) == 2


def test_runner_preserves_native_pages_and_reorders_document_globally(
    materialization_environment: tuple[Path, sessionmaker[Session], LocalFileStorage],
) -> None:
    root, factory, storage = materialization_environment
    project_id, document_id, page_ids = _seed_document(factory, value=50, page_count=3)
    _seed_native_content(factory, page_ids[1], value=501, text="Native first")
    _seed_native_content(factory, page_ids[3], value=503, text="Native last")
    job_id = _seed_job(factory, value=51, project_id=project_id, document_id=document_id)

    _run(
        root,
        factory,
        storage,
        _request(job_id, project_id, document_id, (1, 2, 3)),
        {
            1: _result(1, "OCR must not replace first"),
            2: _result(2, "OCR middle"),
            3: _result(3, "OCR must not replace last"),
        },
    )

    with factory() as session:
        blocks = list(
            session.scalars(
                select(DocumentBlock).join(DocumentPage).order_by(DocumentPage.source_page_number)
            )
        )
        segments = list(
            session.scalars(
                select(DocumentSegment)
                .join(DocumentBlock)
                .join(DocumentPage)
                .order_by(DocumentPage.source_page_number)
            )
        )
        assert [block.source_text for block in blocks] == [
            "Native first",
            "OCR middle",
            "Native last",
        ]
        assert [block.global_reading_order for block in blocks] == [1, 2, 3]
        assert [segment.global_order for segment in segments] == [1, 2, 3]


def test_blank_success_is_structured_when_another_page_fails(
    materialization_environment: tuple[Path, sessionmaker[Session], LocalFileStorage],
) -> None:
    root, factory, storage = materialization_environment
    project_id, document_id, page_ids = _seed_document(factory, value=60, page_count=3)
    job_id = _seed_job(factory, value=61, project_id=project_id, document_id=document_id)

    result = _run(
        root,
        factory,
        storage,
        _request(job_id, project_id, document_id, (1, 2, 3)),
        {1: _result(1, "Materialized text"), 2: _result(2, "", blocks=())},
        failing_pages=frozenset({3}),
    )

    assert result.status.value == "PARTIALLY_COMPLETED"
    with factory() as session:
        valid_page = session.get(DocumentPage, page_ids[1])
        blank_page = session.get(DocumentPage, page_ids[2])
        job = session.get(ApplicationJob, job_id)
        assert valid_page is not None
        assert blank_page is not None
        assert job is not None
        assert valid_page.status == DocumentStatus.STRUCTURED.value
        assert blank_page.status == DocumentStatus.STRUCTURED.value
        assert blank_page.ocr_confidence == pytest.approx(0.96)
        assert session.scalar(select(DocumentBlock).where(DocumentBlock.page_id == page_ids[1]))
        assert (
            session.scalar(select(DocumentBlock).where(DocumentBlock.page_id == page_ids[2]))
            is None
        )
        assert job.status == JobStatus.PARTIALLY_COMPLETED.value


@pytest.mark.parametrize(
    "invalid_kind",
    ("out_of_bounds", "missing_geometry", "unsupported_coordinate_system"),
)
def test_invalid_materialization_rolls_back_prior_page_and_fails_job(
    materialization_environment: tuple[Path, sessionmaker[Session], LocalFileStorage],
    invalid_kind: str,
) -> None:
    root, factory, storage = materialization_environment
    project_id, document_id, page_ids = _seed_document(factory, value=70, page_count=2)
    job_id = _seed_job(factory, value=71, project_id=project_id, document_id=document_id)
    invalid_result = {
        "out_of_bounds": _result(
            2,
            "Outside page",
            geometry=OCRGeometry(
                x=610,
                y=0,
                width=10,
                height=10,
                coordinate_system="PDF_POINT_TOP_LEFT",
            ),
        ),
        "missing_geometry": _result(2, "Text without geometry", blocks=()),
        "unsupported_coordinate_system": _result(
            2,
            "Unsupported coordinates",
            geometry=OCRGeometry(
                x=10,
                y=10,
                width=10,
                height=10,
                coordinate_system="IMAGE_NORMALIZED",
            ),
        ),
    }[invalid_kind]

    with pytest.raises(OCRMaterializationError):
        _run(
            root,
            factory,
            storage,
            _request(job_id, project_id, document_id, (1, 2)),
            {
                1: _result(1, "Valid output must roll back"),
                2: invalid_result,
            },
        )

    with factory() as session:
        first_page = session.get(DocumentPage, page_ids[1])
        invalid_page = session.get(DocumentPage, page_ids[2])
        job = session.get(ApplicationJob, job_id)
        assert first_page is not None
        assert invalid_page is not None
        assert job is not None
        assert session.scalar(select(DocumentBlock)) is None
        assert session.scalar(select(DocumentSegment)) is None
        assert first_page.status == DocumentStatus.ANALYZED.value
        assert first_page.ocr_confidence is None
        assert invalid_page.status == DocumentStatus.ANALYZED.value
        assert job.status == JobStatus.FAILED.value
        assert job.status != JobStatus.COMPLETED.value
        assert job.error_message == "OCR job failed."

    assert len(list((root / "projects" / project_id / "ocr" / "raw").rglob("*.json"))) == 2


def test_documentless_runner_remains_artifact_only(
    materialization_environment: tuple[Path, sessionmaker[Session], LocalFileStorage],
) -> None:
    root, factory, storage = materialization_environment
    project_id, _document_id, _page_ids = _seed_document(factory, value=80, page_count=1)
    job_id = _seed_job(factory, value=81, project_id=project_id, document_id=None)
    request = OCRPageRequest(
        job_id=job_id,
        project_id=project_id,
        source_pdf=_pdf_bytes(1),
        page_numbers=(1,),
    )

    _run(root, factory, storage, request, {1: _result(1, "Standalone OCR")})

    with factory() as session:
        job = session.get(ApplicationJob, job_id)
        assert job is not None
        assert job.status == JobStatus.COMPLETED.value
        assert session.scalar(select(DocumentBlock)) is None
    assert list((root / "projects" / project_id / "ocr" / "raw").rglob("*.json"))


def _run(
    root: Path,
    factory: sessionmaker[Session],
    storage: LocalFileStorage,
    request: OCRPageRequest,
    results: dict[int, OCRResult],
    *,
    failing_pages: frozenset[int] = frozenset(),
) -> OCRRunResult:
    return OCRJobRunner(
        OCRPageOrchestrator(ScriptedProvider(results, failing_pages=failing_pages), storage),
        lambda _job_id: request,
        factory,
        root / "temporary",
        worker_identifier="materialization-test",
    ).run(request.job_id)


def _request(
    job_id: str,
    project_id: str,
    document_id: str,
    page_numbers: tuple[int, ...],
    *,
    dpi: int = 150,
) -> OCRPageRequest:
    return OCRPageRequest(
        job_id=job_id,
        project_id=project_id,
        document_id=document_id,
        source_pdf=_pdf_bytes(max(page_numbers)),
        page_numbers=page_numbers,
        dpi=dpi,
    )


def _result(
    page_number: int,
    text: str,
    *,
    confidence: float = 0.96,
    geometry: OCRGeometry | None = None,
    blocks: tuple[OCRTextBlock, ...] | None = None,
) -> OCRResult:
    if blocks is None:
        blocks = (
            OCRTextBlock(
                text=text,
                geometry=geometry or OCRGeometry(x=10, y=10, width=100, height=20),
                confidence=confidence,
            ),
        )
    return OCRResult(
        page_number=page_number,
        text=text,
        blocks=blocks,
        confidence=confidence,
        settings=OCRSettings(),
        provider="materialization-test",
    )


def _seed_document(
    factory: sessionmaker[Session], *, value: int, page_count: int
) -> tuple[str, str, dict[int, str]]:
    project_id = _id("prj_", value)
    document_id = _id("doc_", value)
    page_ids = {number: _id("pag_", value * 100 + number) for number in range(1, page_count + 1)}
    with transaction_scope(factory) as session:
        original_file_id = _id("fil_", value)
        session.add(
            Project(
                id=project_id,
                name=f"OCR materialization {value}",
                description=None,
                status=ProjectStatus.CREATED.value,
                source_language="en",
                target_language="id",
                document_type=DocumentType.TECHNICAL_BOOK.value,
                translation_style=TranslationStyle.PROFESSIONAL.value,
                reconstruction_mode=ReconstructionMode.HYBRID.value,
                progress=0.0,
                active_document_id=None,
                settings_json="{}",
                created_at=NOW,
                updated_at=NOW,
                archived_at=None,
                deleted_at=None,
            )
        )
        session.flush()
        session.add(
            StoredFile(
                id=original_file_id,
                project_id=project_id,
                document_id=None,
                file_role=FileRole.ORIGINAL.value,
                storage_key=f"projects/{project_id}/original/source.pdf",
                original_filename="source.pdf",
                safe_filename="source.pdf",
                mime_type="application/pdf",
                size_bytes=1,
                checksum_sha256="0" * 64,
                is_immutable=1,
                status=FileStatus.VALIDATED.value,
                metadata_json=None,
                created_at=NOW,
                deleted_at=None,
            )
        )
        session.flush()
        session.add(
            Document(
                id=document_id,
                project_id=project_id,
                original_file_id=original_file_id,
                ir_version="0.1",
                title=f"OCR document {value}",
                author=None,
                document_type=DocumentType.TECHNICAL_BOOK.value,
                document_class=DocumentClass.SCANNED_PDF.value,
                source_language="en",
                target_language="id",
                page_count=page_count,
                word_count_estimate=None,
                has_text_layer=0,
                scanned_page_count=page_count,
                image_count=page_count,
                table_count=0,
                status=DocumentStatus.ANALYZED.value,
                metadata_json=None,
                analysis_json=None,
                created_at=NOW,
                updated_at=NOW,
            )
        )
        for number, page_id in page_ids.items():
            session.add(
                DocumentPage(
                    id=page_id,
                    document_id=document_id,
                    source_page_number=number,
                    logical_page_number=str(number),
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
                    created_at=NOW,
                    updated_at=NOW,
                )
            )
        project = session.get(Project, project_id)
        assert project is not None
        project.active_document_id = document_id
    return project_id, document_id, page_ids


def _seed_job(
    factory: sessionmaker[Session], *, value: int, project_id: str, document_id: str | None
) -> str:
    job_id = _id("job_", value)
    with transaction_scope(factory) as session:
        session.add(
            ApplicationJob(
                id=job_id,
                project_id=project_id,
                document_id=document_id,
                parent_job_id=None,
                job_type=JobType.OCR_DOCUMENT.value,
                queue_name="ocr-test",
                status=JobStatus.QUEUED.value,
                progress=0.0,
                current_stage="QUEUED",
                idempotency_key=f"ocr-materialization-{value}",
                payload_json="{}",
                result_json=None,
                retry_count=0,
                max_retries=3,
                error_code=None,
                error_message=None,
                created_at=NOW,
                queued_at=NOW,
                started_at=None,
                completed_at=None,
                cancelled_at=None,
                heartbeat_at=None,
            )
        )
    return job_id


def _seed_native_content(
    factory: sessionmaker[Session], page_id: str, *, value: int, text: str
) -> None:
    block_id = _id("blk_", value)
    with transaction_scope(factory) as session:
        session.add(
            DocumentBlock(
                id=block_id,
                page_id=page_id,
                section_id=None,
                parent_block_id=None,
                block_type=BlockType.PARAGRAPH.value,
                semantic_role=SemanticRole.BODY_TEXT.value,
                page_reading_order=1,
                global_reading_order=99,
                source_text=text,
                normalized_source_text=text,
                source_geometry_json="{}",
                target_geometry_json=None,
                style_json=None,
                detail_json="{}",
                status=DocumentStatus.STRUCTURED.value,
                confidence=0.99,
                created_at=NOW,
                updated_at=NOW,
            )
        )
        session.add(
            DocumentSegment(
                id=_id("seg_", value),
                block_id=block_id,
                section_id=None,
                segment_order=1,
                global_order=99,
                source_text=text,
                native_text=text,
                ocr_text=None,
                resolved_source_text=text,
                normalized_source_text=text,
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
                created_at=NOW,
                updated_at=NOW,
            )
        )


def _pdf_bytes(page_count: int) -> bytes:
    output = BytesIO()
    writer = PdfWriter()
    for _ in range(page_count):
        writer.add_blank_page(width=612, height=792)
    writer.write(output)
    return output.getvalue()
