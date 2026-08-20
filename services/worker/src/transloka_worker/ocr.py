from __future__ import annotations

import json
import os
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker
from transloka_core.database import transaction_scope
from transloka_core.database.models.jobs import (
    ApplicationJob,
    JobAttempt,
    JobAttemptStatus,
    JobStatus,
)
from transloka_core.jobs.cancellation import JobCancellationService
from transloka_core.jobs.progress import JobProgressService
from transloka_documents.ocr.orchestration import (
    OCRJobRequest,
    OCRPageOrchestrator,
    OCRRunResult,
    OCRRunStatus,
)


class OCRWorkerError(RuntimeError):
    pass


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


# Compatibility alias for callers that name worker adapters explicitly.
OCRWorker = OCRJobRunner
