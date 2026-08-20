import json
from collections.abc import Iterator
from io import BytesIO
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from pypdf import PdfWriter
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session, sessionmaker
from transloka_core.database import create_session_factory, create_sqlite_engine
from transloka_core.database.models.jobs import (
    ApplicationJob,
    JobAttempt,
    JobAttemptStatus,
    JobStatus,
    JobType,
)
from transloka_core.jobs.cancellation import JobCancellationService
from transloka_core.jobs.dispatch import JobDispatchResult, JobDispatchService
from transloka_core.storage import resolve_local_data_directories
from transloka_core.storage.local import LocalFileStorage
from transloka_documents.ocr import (
    OCRHealth,
    OCRHealthStatus,
    OCRPage,
    OCRProviderError,
    OCRProviderErrorCode,
    OCRResult,
    OCRSettings,
)
from transloka_documents.ocr.orchestration import OCRPageOrchestrator, OCRPageRequest
from transloka_worker.ocr import OCRJobRunner

REPOSITORY_ROOT = Path(__file__).parents[3]
ALEMBIC_CONFIGURATION = REPOSITORY_ROOT / "alembic.ini"
PROJECT_ID = "prj_550e8400-e29b-41d4-a716-446655440000"


class RecordingQueue:
    name = "ocr-test"

    def enqueue(self, _job_id: str) -> None:
        pass


class ScriptedProvider:
    def __init__(self, *, failure: OCRProviderError | None = None) -> None:
        self.failure = failure
        self.calls: list[OCRPage] = []

    def health_check(self) -> OCRHealth:
        return OCRHealth(status=OCRHealthStatus.AVAILABLE, provider="test")

    def analyze_page(
        self,
        page: OCRPage,
        *,
        settings: OCRSettings | None = None,
    ) -> OCRResult:
        self.calls.append(page)
        if self.failure is not None and page.page_number == 2:
            raise self.failure
        effective_settings = settings or OCRSettings()
        return OCRResult(
            page_number=page.page_number,
            text=f"OCR page {page.page_number}",
            settings=effective_settings,
            provider="test",
        )


@pytest.fixture
def job_environment(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> Iterator[tuple[Path, Engine, sessionmaker[Session], LocalFileStorage]]:
    root = tmp_path / "ocr worker"
    monkeypatch.setenv("TRANSLOKA_DATA_DIR", str(root))
    command.upgrade(Config(str(ALEMBIC_CONFIGURATION)), "head")
    directories = resolve_local_data_directories(root)
    engine = create_sqlite_engine(directories)
    try:
        yield root, engine, create_session_factory(engine), LocalFileStorage(directories)
    finally:
        engine.dispose()


def test_worker_persists_progress_attempt_and_result(
    job_environment: tuple[Path, Engine, sessionmaker[Session], LocalFileStorage],
) -> None:
    root, _engine, factory, storage = job_environment
    job_id = _dispatch(factory).job_id
    provider = ScriptedProvider()
    request = OCRPageRequest(
        job_id=job_id,
        project_id=PROJECT_ID,
        source_pdf=_pdf_bytes(page_count=2),
        page_numbers=(1, 2),
    )
    runner = OCRJobRunner(
        OCRPageOrchestrator(provider, storage),
        lambda requested_job_id: request if requested_job_id == job_id else request,
        factory,
        root / "temp",
        worker_identifier="test-worker",
    )

    result = runner.run(job_id)

    assert result.status.value == "COMPLETED"
    with factory() as session:
        job = session.get(ApplicationJob, job_id)
        assert job is not None
        assert job.status == JobStatus.COMPLETED.value
        assert job.progress == 1.0
        assert json.loads(job.result_json or "{}")["completed_pages"] == [1, 2]
        attempt = session.scalar(select(JobAttempt).where(JobAttempt.job_id == job_id))
        assert attempt is not None
        assert attempt.status == JobAttemptStatus.COMPLETED.value

    assert len(list((root / "projects" / PROJECT_ID / "ocr" / "raw").rglob("*.json"))) == 2


def test_worker_marks_partial_failure_without_losing_valid_page_output(
    job_environment: tuple[Path, Engine, sessionmaker[Session], LocalFileStorage],
) -> None:
    root, _engine, factory, storage = job_environment
    job_id = _dispatch(factory).job_id
    provider = ScriptedProvider(
        failure=OCRProviderError(
            OCRProviderErrorCode.INVALID_REQUEST,
            "bad page",
            retryable=False,
        )
    )
    request = OCRPageRequest(
        job_id=job_id,
        project_id=PROJECT_ID,
        source_pdf=_pdf_bytes(page_count=2),
        page_numbers=(1, 2),
    )
    runner = OCRJobRunner(
        OCRPageOrchestrator(provider, storage), lambda _id: request, factory, root / "temp"
    )

    result = runner.run(job_id)

    assert result.status.value == "PARTIALLY_COMPLETED"
    with factory() as session:
        job = session.get(ApplicationJob, job_id)
        assert job is not None
        assert job.status == JobStatus.PARTIALLY_COMPLETED.value
        assert job.error_code == "OCR_PAGE_FAILED"
    assert len(list((root / "projects" / PROJECT_ID / "ocr" / "raw").rglob("*.json"))) == 1


def test_cancelled_queued_job_does_not_start_ocr(
    job_environment: tuple[Path, Engine, sessionmaker[Session], LocalFileStorage],
) -> None:
    root, _engine, factory, storage = job_environment
    job_id = _dispatch(factory).job_id
    JobCancellationService(factory, root / "temp").request(job_id, reason="user requested")
    request = OCRPageRequest(
        job_id=job_id,
        project_id=PROJECT_ID,
        source_pdf=_pdf_bytes(),
        page_numbers=(1,),
    )
    provider = ScriptedProvider()
    result = OCRJobRunner(
        OCRPageOrchestrator(provider, storage), lambda _id: request, factory, root / "temp"
    ).run(job_id)

    assert result.status.value == "CANCELLED"
    assert provider.calls == []


def _dispatch(factory: sessionmaker[Session]) -> JobDispatchResult:
    return JobDispatchService(factory, RecordingQueue()).dispatch(
        job_type=JobType.OCR_DOCUMENT,
        idempotency_key="ocr-worker-test",
    )


def _pdf_bytes(*, page_count: int = 1) -> bytes:
    output = BytesIO()
    writer = PdfWriter()
    for _ in range(page_count):
        writer.add_blank_page(width=612, height=792)
    writer.write(output)
    return output.getvalue()
