from __future__ import annotations

import json
import math
import os
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Self
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker
from transloka_core.database import transaction_scope
from transloka_core.database.models.documents import Document
from transloka_core.database.models.files import FileRole, FileStatus, StoredFile
from transloka_core.database.models.jobs import (
    ApplicationJob,
    JobAttempt,
    JobAttemptStatus,
    JobStatus,
    JobType,
)
from transloka_core.database.models.pages import DocumentPage, PageType
from transloka_core.database.models.projects import Project
from transloka_core.jobs.cancellation import JobCancellationService
from transloka_core.jobs.progress import JobProgressService
from transloka_core.storage.local import LocalFileStorage, LocalFileStorageError
from transloka_documents.ocr import OCRSettings
from transloka_documents.ocr.orchestration import (
    OCRJobRequest,
    OCRPageOrchestrator,
    OCRRunResult,
    OCRRunStatus,
)

OCR_COMMAND_SCHEMA = "transloka.ocr.command.v1"
_OCR_COMMAND_FIELDS = frozenset(
    {
        "schema",
        "project_id",
        "document_id",
        "mode",
        "page_ids",
        "language",
        "detect_tables",
        "detect_formulas",
        "dpi",
        "timeout_seconds",
        "low_confidence_threshold",
        "max_attempts",
    }
)
_OCR_MODES = frozenset({"AUTO", "FORCE"})
_OCR_DPI_VALUES = frozenset({72, 96, 120, 144, 150, 200, 300})


class OCRWorkerError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class OCRCommand:
    project_id: str
    document_id: str
    mode: str
    page_ids: tuple[str, ...]
    language: str
    detect_tables: bool
    detect_formulas: bool
    dpi: int = 150
    timeout_seconds: float = 30.0
    low_confidence_threshold: float = 0.75
    max_attempts: int = 3

    def __post_init__(self) -> None:
        _validate_identifier(self.project_id, "prj_")
        _validate_identifier(self.document_id, "doc_")
        _validate_page_ids(self.page_ids)
        if self.mode not in _OCR_MODES:
            raise OCRWorkerError("The OCR command mode is invalid.")
        if self.mode == "AUTO" and self.page_ids:
            raise OCRWorkerError("Automatic OCR cannot contain explicit page identifiers.")
        if self.mode == "FORCE" and not self.page_ids:
            raise OCRWorkerError("Forced OCR requires page identifiers.")
        if (
            not isinstance(self.language, str)
            or not self.language
            or self.language != self.language.strip()
            or not self.language.isprintable()
            or len(self.language) > 20
        ):
            raise OCRWorkerError("The OCR command language is invalid.")
        if type(self.detect_tables) is not bool or type(self.detect_formulas) is not bool:
            raise OCRWorkerError("The OCR command flags are invalid.")
        if type(self.dpi) is not int or self.dpi not in _OCR_DPI_VALUES:
            raise OCRWorkerError("The OCR command DPI is invalid.")
        if (
            isinstance(self.timeout_seconds, bool)
            or not isinstance(self.timeout_seconds, int | float)
            or not math.isfinite(self.timeout_seconds)
            or not 0 < self.timeout_seconds <= 300
        ):
            raise OCRWorkerError("The OCR command timeout is invalid.")
        if (
            isinstance(self.low_confidence_threshold, bool)
            or not isinstance(self.low_confidence_threshold, int | float)
            or not math.isfinite(self.low_confidence_threshold)
            or not 0 <= self.low_confidence_threshold <= 1
        ):
            raise OCRWorkerError("The OCR command confidence threshold is invalid.")
        if type(self.max_attempts) is not int or not 1 <= self.max_attempts <= 5:
            raise OCRWorkerError("The OCR command maximum attempts are invalid.")

    def to_payload(self) -> dict[str, object]:
        return {
            "schema": OCR_COMMAND_SCHEMA,
            "project_id": self.project_id,
            "document_id": self.document_id,
            "mode": self.mode,
            "page_ids": list(self.page_ids),
            "language": self.language,
            "detect_tables": self.detect_tables,
            "detect_formulas": self.detect_formulas,
            "dpi": self.dpi,
            "timeout_seconds": self.timeout_seconds,
            "low_confidence_threshold": self.low_confidence_threshold,
            "max_attempts": self.max_attempts,
        }

    @classmethod
    def from_payload_json(cls, value: str) -> Self:
        payload = _decode_ocr_command(value)
        if frozenset(payload) != _OCR_COMMAND_FIELDS:
            raise OCRWorkerError("The OCR command fields are invalid.")
        if payload["schema"] != OCR_COMMAND_SCHEMA:
            raise OCRWorkerError("The OCR command schema is unsupported.")
        try:
            return cls(
                project_id=_string_value(payload, "project_id"),
                document_id=_string_value(payload, "document_id"),
                mode=_string_value(payload, "mode"),
                page_ids=_page_id_tuple(payload["page_ids"]),
                language=_string_value(payload, "language"),
                detect_tables=_boolean_value(payload, "detect_tables"),
                detect_formulas=_boolean_value(payload, "detect_formulas"),
                dpi=_integer_value(payload, "dpi"),
                timeout_seconds=_number_value(payload, "timeout_seconds"),
                low_confidence_threshold=_number_value(payload, "low_confidence_threshold"),
                max_attempts=_integer_value(payload, "max_attempts"),
            )
        except (KeyError, TypeError):
            raise OCRWorkerError("The OCR command values are invalid.") from None


@dataclass(frozen=True, slots=True)
class LoadedOCRJob:
    request: OCRJobRequest
    selected_page_ids: tuple[str, ...]


class DatabaseOCRRequestLoader:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        storage: LocalFileStorage,
    ) -> None:
        self._session_factory = session_factory
        self._storage = storage

    def load(self, job_id: str) -> LoadedOCRJob:
        _validate_identifier(job_id, "job_")
        with self._session_factory() as session:
            job = session.get(ApplicationJob, job_id)
            if job is None or job.job_type != JobType.OCR_DOCUMENT.value:
                raise OCRWorkerError("The OCR job is unavailable.")
            if job.status not in {
                JobStatus.QUEUED.value,
                JobStatus.RETRYING.value,
                JobStatus.RUNNING.value,
                JobStatus.CANCELLATION_REQUESTED.value,
                JobStatus.CANCELLED.value,
            }:
                raise OCRWorkerError("The OCR job is not executable.")

            command = OCRCommand.from_payload_json(job.payload_json)
            project = session.get(Project, command.project_id)
            document = session.get(Document, command.document_id)
            if (
                project is None
                or document is None
                or document.project_id != command.project_id
                or project.active_document_id != command.document_id
                or job.project_id != command.project_id
                or job.document_id != command.document_id
            ):
                raise OCRWorkerError("The OCR command state is inconsistent.")

            original = session.get(StoredFile, document.original_file_id)
            if (
                original is None
                or original.project_id != command.project_id
                or original.file_role != FileRole.ORIGINAL.value
                or original.status != FileStatus.VALIDATED.value
                or not original.is_immutable
                or original.mime_type != "application/pdf"
            ):
                raise OCRWorkerError("The OCR source PDF is unavailable.")

            pages = tuple(
                session.scalars(
                    select(DocumentPage)
                    .where(DocumentPage.document_id == command.document_id)
                    .order_by(DocumentPage.source_page_number, DocumentPage.id)
                )
            )
            selected = _selected_pages(pages, command)
            try:
                checksum = self._storage.checksum(original.storage_key)
            except LocalFileStorageError as exc:
                raise OCRWorkerError("The OCR source PDF is unavailable.") from exc
            if checksum != original.checksum_sha256:
                raise OCRWorkerError("The OCR source PDF checksum is invalid.")

            request = OCRJobRequest(
                job_id=job.id,
                project_id=command.project_id,
                document_id=command.document_id,
                source_pdf=lambda: self._storage.open_read(original.storage_key),
                page_numbers=tuple(page.source_page_number for page in selected),
                dpi=command.dpi,
                settings=OCRSettings(
                    language=command.language,
                    detect_tables=command.detect_tables,
                    detect_formulas=command.detect_formulas,
                    timeout_seconds=command.timeout_seconds,
                    low_confidence_threshold=command.low_confidence_threshold,
                ),
                max_attempts=command.max_attempts,
            )
            return LoadedOCRJob(
                request=request,
                selected_page_ids=tuple(page.id for page in selected),
            )

    def __call__(self, job_id: str) -> OCRJobRequest:
        return self.load(job_id).request


class OCRJobRunner:
    """Worker boundary for OCR page execution and persisted job lifecycle."""

    def __init__(
        self,
        orchestrator: OCRPageOrchestrator,
        request_loader: Callable[[str], OCRJobRequest],
        session_factory: sessionmaker[Session],
        temporary_root: Path,
        *,
        worker_identifier: str | None = None,
    ) -> None:
        if not callable(request_loader):
            raise ValueError("The OCR request loader must be callable.")
        if not temporary_root.is_absolute():
            raise ValueError("The worker temporary root must be absolute.")
        self._orchestrator = orchestrator
        self._request_loader = request_loader
        self._session_factory = session_factory
        self._temporary_root = temporary_root.resolve(strict=False)
        self._worker_identifier = _worker_identifier(worker_identifier)

    def run(self, job_id: str) -> OCRRunResult:
        request = self._request_loader(job_id)
        if not isinstance(request, OCRJobRequest) or request.job_id != job_id:
            raise OCRWorkerError("The OCR request loader returned an invalid job request.")

        cancellation = JobCancellationService(self._session_factory, self._temporary_root)
        progress = JobProgressService(self._session_factory)
        current_status = _job_status(self._session_factory, job_id)
        if current_status is JobStatus.CANCELLED:
            result = _cancelled_result(request)
            _finish_job(self._session_factory, request, result, self._worker_identifier)
            return result
        if current_status is JobStatus.CANCELLATION_REQUESTED:
            cancellation.checkpoint(job_id)
            result = _cancelled_result(request)
            _finish_job(self._session_factory, request, result, self._worker_identifier)
            return result

        try:
            _start_attempt(self._session_factory, job_id, self._worker_identifier)
            if request.page_numbers:
                progress.update(job_id, progress=0.0, current_stage="OCR_SELECT")
            else:
                progress.update(job_id, progress=1.0, current_stage="OCR_SELECT_EMPTY")

            def report_progress(value: float, stage: str) -> None:
                progress.update(job_id, progress=value, current_stage=stage)

            result = self._orchestrator.run(
                request,
                cancel_check=lambda: _is_cancellation_requested(
                    self._session_factory,
                    job_id,
                ),
                progress_callback=report_progress,
            )
            if result.status is OCRRunStatus.CANCELLED:
                cancellation.checkpoint(job_id)
            _finish_job(self._session_factory, request, result, self._worker_identifier)
            return result
        except Exception as exc:
            _fail_job(self._session_factory, job_id, exc, self._worker_identifier)
            raise


def run_ocr_job(
    job_id: str,
    *,
    orchestrator: OCRPageOrchestrator,
    request_loader: Callable[[str], OCRJobRequest],
    session_factory: sessionmaker[Session],
    temporary_root: Path,
    worker_identifier: str | None = None,
) -> OCRRunResult:
    return OCRJobRunner(
        orchestrator,
        request_loader,
        session_factory,
        temporary_root,
        worker_identifier=worker_identifier,
    ).run(job_id)


def create_ocr_task(
    *,
    orchestrator: OCRPageOrchestrator,
    request_loader: Callable[[str], OCRJobRequest],
    session_factory: sessionmaker[Session],
    temporary_root: Path,
    worker_identifier: str | None = None,
) -> Callable[[str], OCRRunResult]:
    runner = OCRJobRunner(
        orchestrator,
        request_loader,
        session_factory,
        temporary_root,
        worker_identifier=worker_identifier,
    )
    return runner.run


def _start_attempt(
    session_factory: sessionmaker[Session],
    job_id: str,
    worker_identifier: str,
) -> None:
    now = _utc_now()
    with transaction_scope(session_factory) as session:
        row = session.get(ApplicationJob, job_id)
        if row is None:
            raise OCRWorkerError("The OCR job was not found.")
        if row.status not in {
            JobStatus.QUEUED.value,
            JobStatus.RETRYING.value,
            JobStatus.RUNNING.value,
        }:
            raise OCRWorkerError("The OCR job is not in an executable state.")
        attempts = list(
            session.scalars(
                select(JobAttempt)
                .where(JobAttempt.job_id == job_id)
                .order_by(JobAttempt.attempt_number)
            )
        )
        if attempts and attempts[-1].status == JobAttemptStatus.RUNNING.value:
            attempts[-1].worker_identifier = worker_identifier
            return
        session.add(
            JobAttempt(
                id=_attempt_id(job_id, len(attempts) + 1),
                job_id=job_id,
                attempt_number=len(attempts) + 1,
                status=JobAttemptStatus.RUNNING.value,
                worker_identifier=worker_identifier,
                started_at=now,
                completed_at=None,
                duration_ms=None,
                error_code=None,
                error_message=None,
                details_json=None,
            )
        )
        session.flush()


def _finish_job(
    session_factory: sessionmaker[Session],
    request: OCRJobRequest,
    result: OCRRunResult,
    worker_identifier: str,
) -> None:
    now = _utc_now()
    status = _job_status_for_result(result.status)
    result_json = json.dumps(
        {
            "schema": "transloka.ocr.job.v1",
            "selected_pages": list(result.selected_page_numbers),
            "completed_pages": list(result.completed_page_numbers),
            "failed_pages": list(result.failed_page_numbers),
            "cancelled_pages": list(result.cancelled_page_numbers),
            "outputs": [
                {
                    "page_number": output.page_number,
                    "file_id": output.raw_output.file_id,
                    "storage_key": output.raw_output.storage_key,
                    "checksum_sha256": output.raw_output.checksum_sha256,
                    "confidence": output.result.confidence,
                    "attempts": output.attempts,
                }
                for output in result.outputs
            ],
            "failures": [
                {
                    "page_number": failure.page_number,
                    "error_code": failure.error_code,
                    "error_message": failure.error_message,
                    "attempts": failure.attempts,
                }
                for failure in result.failures
            ],
        },
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    progress = (
        len(result.completed_page_numbers) / len(result.selected_page_numbers)
        if result.selected_page_numbers
        else 1.0
    )
    if status is JobStatus.COMPLETED:
        progress = 1.0
    error_code, error_message = _result_error(result)
    with transaction_scope(session_factory) as session:
        row = session.get(ApplicationJob, request.job_id)
        if row is None:
            raise OCRWorkerError("The OCR job disappeared before completion.")
        if row.status == JobStatus.CANCELLED.value and status is not JobStatus.CANCELLED:
            return
        row.status = status.value
        row.progress = progress
        row.current_stage = status.value
        row.result_json = result_json
        row.error_code = error_code
        row.error_message = error_message
        row.completed_at = now
        row.heartbeat_at = now
        _finish_attempt(session, row.id, status, now, worker_identifier, error_code, error_message)
        session.flush()


def _fail_job(
    session_factory: sessionmaker[Session],
    job_id: str,
    error: Exception,
    worker_identifier: str,
) -> None:
    now = _utc_now()
    error_code = type(error).__name__.upper()
    error_message = str(error).strip() or "OCR job failed."
    if not error_message.isprintable():
        error_message = "OCR job failed."
    try:
        with transaction_scope(session_factory) as session:
            row = session.get(ApplicationJob, job_id)
            if row is None or row.status not in {
                JobStatus.QUEUED.value,
                JobStatus.RETRYING.value,
                JobStatus.RUNNING.value,
                JobStatus.CANCELLATION_REQUESTED.value,
            }:
                return
            row.status = JobStatus.FAILED.value
            row.current_stage = JobStatus.FAILED.value
            row.error_code = error_code
            row.error_message = error_message
            row.completed_at = now
            row.heartbeat_at = now
            _finish_attempt(
                session,
                job_id,
                JobStatus.FAILED,
                now,
                worker_identifier,
                error_code,
                error_message,
            )
            session.flush()
    except Exception:
        # Preserve the original worker exception; recovery will mark the job stale.
        return


def _finish_attempt(
    session: Session,
    job_id: str,
    status: JobStatus,
    completed_at: str,
    worker_identifier: str,
    error_code: str | None,
    error_message: str | None,
) -> None:
    attempts = list(
        session.scalars(
            select(JobAttempt)
            .where(JobAttempt.job_id == job_id)
            .order_by(JobAttempt.attempt_number)
        )
    )
    if not attempts:
        return
    attempt = attempts[-1]
    if attempt.status != JobAttemptStatus.RUNNING.value:
        return
    attempt.status = _attempt_status_for_job(status).value
    attempt.completed_at = completed_at
    attempt.worker_identifier = worker_identifier
    attempt.error_code = error_code
    attempt.error_message = error_message


def _is_cancellation_requested(
    session_factory: sessionmaker[Session],
    job_id: str,
) -> bool:
    status = _job_status(session_factory, job_id)
    return status in {JobStatus.CANCELLATION_REQUESTED, JobStatus.CANCELLED}


def _job_status(session_factory: sessionmaker[Session], job_id: str) -> JobStatus:
    with session_factory() as session:
        row = session.get(ApplicationJob, job_id)
        if row is None:
            raise OCRWorkerError("The OCR job was not found.")
        try:
            return JobStatus(row.status)
        except ValueError as exc:
            raise OCRWorkerError("The stored OCR job status is invalid.") from exc


def _cancelled_result(request: OCRJobRequest) -> OCRRunResult:
    return OCRRunResult(
        job_id=request.job_id,
        status=OCRRunStatus.CANCELLED,
        selected_page_numbers=tuple(request.page_numbers),
        completed_page_numbers=(),
        failed_page_numbers=(),
        cancelled_page_numbers=tuple(request.page_numbers),
    )


def _job_status_for_result(status: OCRRunStatus) -> JobStatus:
    return {
        OCRRunStatus.COMPLETED: JobStatus.COMPLETED,
        OCRRunStatus.PARTIALLY_COMPLETED: JobStatus.PARTIALLY_COMPLETED,
        OCRRunStatus.FAILED: JobStatus.FAILED,
        OCRRunStatus.CANCELLED: JobStatus.CANCELLED,
    }[status]


def _attempt_status_for_job(status: JobStatus) -> JobAttemptStatus:
    return {
        JobStatus.COMPLETED: JobAttemptStatus.COMPLETED,
        JobStatus.PARTIALLY_COMPLETED: JobAttemptStatus.PARTIALLY_COMPLETED,
        JobStatus.FAILED: JobAttemptStatus.FAILED,
        JobStatus.CANCELLED: JobAttemptStatus.CANCELLED,
    }.get(status, JobAttemptStatus.FAILED)


def _result_error(result: OCRRunResult) -> tuple[str | None, str | None]:
    if not result.failures:
        return None, None
    return (
        "OCR_PAGE_FAILED",
        f"{len(result.failures)} OCR page(s) failed; successful pages were preserved.",
    )


def _attempt_id(job_id: str, attempt_number: int) -> str:
    import uuid

    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"transloka:ocr-attempt:{job_id}:{attempt_number}"))


def _worker_identifier(value: str | None) -> str:
    candidate = (
        value or os.environ.get("COMPUTERNAME") or os.environ.get("HOSTNAME") or "transloka-worker"
    )
    normalized = candidate.strip()
    if not normalized or not normalized.isprintable() or len(normalized) > 200:
        return "transloka-worker"
    return normalized


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _selected_pages(
    pages: tuple[DocumentPage, ...],
    command: OCRCommand,
) -> tuple[DocumentPage, ...]:
    by_id = {page.id: page for page in pages}
    if command.mode == "FORCE":
        if not set(command.page_ids).issubset(by_id):
            raise OCRWorkerError("An OCR command page is unavailable.")
        return tuple(by_id[page_id] for page_id in command.page_ids)
    return tuple(
        page for page in pages if page.page_type in {PageType.SCANNED.value, PageType.HYBRID.value}
    )


def _decode_ocr_command(value: str) -> dict[str, object]:
    if not isinstance(value, str):
        raise OCRWorkerError("The OCR command JSON is invalid.")

    def pairs_hook(pairs: list[tuple[str, object]]) -> dict[str, object]:
        payload: dict[str, object] = {}
        for key, item in pairs:
            if key in payload:
                raise OCRWorkerError("The OCR command fields are duplicated.")
            payload[key] = item
        return payload

    try:
        payload = json.loads(value, object_pairs_hook=pairs_hook)
    except OCRWorkerError:
        raise
    except (TypeError, ValueError):
        raise OCRWorkerError("The OCR command JSON is invalid.") from None
    if not isinstance(payload, dict):
        raise OCRWorkerError("The OCR command must be a JSON object.")
    return payload


def _validate_identifier(value: str, prefix: str) -> None:
    if not isinstance(value, str) or not value.startswith(prefix):
        raise OCRWorkerError("An OCR command identifier is invalid.")
    try:
        parsed = UUID(value[len(prefix) :])
    except (AttributeError, ValueError):
        raise OCRWorkerError("An OCR command identifier is invalid.") from None
    if value != f"{prefix}{parsed}":
        raise OCRWorkerError("An OCR command identifier is invalid.")


def _validate_page_ids(values: tuple[str, ...]) -> None:
    if not isinstance(values, tuple) or len(set(values)) != len(values):
        raise OCRWorkerError("The OCR command page identifiers are invalid.")
    for value in values:
        _validate_identifier(value, "pag_")


def _page_id_tuple(value: object) -> tuple[str, ...]:
    if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
        raise OCRWorkerError("The OCR command page identifiers are invalid.")
    return tuple(value)


def _string_value(payload: dict[str, object], key: str) -> str:
    value = payload[key]
    if not isinstance(value, str):
        raise TypeError
    return value


def _boolean_value(payload: dict[str, object], key: str) -> bool:
    value = payload[key]
    if type(value) is not bool:
        raise TypeError
    return value


def _integer_value(payload: dict[str, object], key: str) -> int:
    value = payload[key]
    if type(value) is not int:
        raise TypeError
    return value


def _number_value(payload: dict[str, object], key: str) -> float:
    value = payload[key]
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise TypeError
    return float(value)


# Compatibility alias for callers that name worker adapters explicitly.
OCRWorker = OCRJobRunner
