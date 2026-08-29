from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Self
from uuid import NAMESPACE_URL, UUID, uuid5

from sqlalchemy import delete, select
from sqlalchemy.orm import Session, sessionmaker
from transloka_core.database import transaction_scope
from transloka_core.database.models.documents import (
    Document,
    DocumentClass,
    DocumentStatus,
)
from transloka_core.database.models.files import FileRole, FileStatus, StoredFile
from transloka_core.database.models.jobs import (
    ApplicationJob,
    JobAttempt,
    JobAttemptStatus,
    JobStatus,
    JobType,
)
from transloka_core.database.models.pages import DocumentPage, PageType
from transloka_core.database.models.projects import Project, ProjectStatus
from transloka_core.storage.local import LocalFileStorage, LocalFileStorageError
from transloka_documents.analysis import PdfAnalysisResult, analyze_pdf

ANALYSIS_COMMAND_SCHEMA = "transloka.analysis.command.v1"
_ANALYSIS_COMMAND_FIELDS = frozenset({"schema", "project_id", "document_id"})


class AnalysisWorkerError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class AnalysisCommand:
    project_id: str
    document_id: str

    def __post_init__(self) -> None:
        _validate_identifier(self.project_id, "prj_")
        _validate_identifier(self.document_id, "doc_")

    def to_payload(self) -> dict[str, object]:
        return {
            "schema": ANALYSIS_COMMAND_SCHEMA,
            "project_id": self.project_id,
            "document_id": self.document_id,
        }

    @classmethod
    def from_payload_json(cls, value: str) -> Self:
        try:
            payload = json.loads(value)
        except (json.JSONDecodeError, TypeError, ValueError):
            raise AnalysisWorkerError("The analysis command payload is invalid.") from None
        if not isinstance(payload, dict) or frozenset(payload) != _ANALYSIS_COMMAND_FIELDS:
            raise AnalysisWorkerError("The analysis command fields are invalid.")
        if payload["schema"] != ANALYSIS_COMMAND_SCHEMA:
            raise AnalysisWorkerError("The analysis command schema is unsupported.")
        project_id = payload["project_id"]
        document_id = payload["document_id"]
        if type(project_id) is not str or type(document_id) is not str:
            raise AnalysisWorkerError("The analysis command values are invalid.")
        return cls(project_id=project_id, document_id=document_id)


@dataclass(frozen=True, slots=True)
class LoadedAnalysisJob:
    job_id: str
    command: AnalysisCommand
    storage_key: str
    checksum_sha256: str


@dataclass(frozen=True, slots=True)
class AnalysisRunResult:
    job_id: str
    document_id: str
    status: JobStatus
    page_count: int
    scanned_page_count: int


class DatabaseAnalysisJobRunner:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        storage: LocalFileStorage,
        *,
        worker_identifier: str | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._storage = storage
        self._worker_identifier = _worker_identifier(worker_identifier)

    def run(self, job_id: str) -> AnalysisRunResult:
        loaded = self._load(job_id)
        try:
            _start_attempt(self._session_factory, job_id, self._worker_identifier)
            with self._storage.open_read(loaded.storage_key) as source:
                analysis = analyze_pdf(source)
            result = _complete_analysis(
                self._session_factory,
                loaded,
                analysis,
                self._worker_identifier,
            )
        except Exception:
            _fail_analysis(
                self._session_factory,
                job_id,
                loaded.command.document_id,
                self._worker_identifier,
            )
            raise
        return result

    def _load(self, job_id: str) -> LoadedAnalysisJob:
        _validate_identifier(job_id, "job_")
        with self._session_factory() as session:
            job = session.get(ApplicationJob, job_id)
            if job is None or job.job_type != JobType.ANALYZE_DOCUMENT.value:
                raise AnalysisWorkerError("The analysis job is unavailable.")
            if job.status not in {
                JobStatus.QUEUED.value,
                JobStatus.RETRYING.value,
                JobStatus.RUNNING.value,
            }:
                raise AnalysisWorkerError("The analysis job is not executable.")
            command = AnalysisCommand.from_payload_json(job.payload_json)
            project = session.get(Project, command.project_id)
            document = session.get(Document, command.document_id)
            if (
                project is None
                or document is None
                or document.project_id != command.project_id
                or job.project_id != command.project_id
                or job.document_id != command.document_id
            ):
                raise AnalysisWorkerError("The analysis command state is inconsistent.")
            original = session.get(StoredFile, document.original_file_id)
            if (
                original is None
                or original.project_id != command.project_id
                or original.file_role != FileRole.ORIGINAL.value
                or original.status != FileStatus.VALIDATED.value
                or not original.is_immutable
                or original.mime_type != "application/pdf"
            ):
                raise AnalysisWorkerError("The analysis source PDF is unavailable.")
            try:
                checksum = self._storage.checksum(original.storage_key)
            except LocalFileStorageError as exc:
                raise AnalysisWorkerError("The analysis source PDF is unavailable.") from exc
            if checksum != original.checksum_sha256:
                raise AnalysisWorkerError("The analysis source PDF checksum is invalid.")
            return LoadedAnalysisJob(
                job_id=job.id,
                command=command,
                storage_key=original.storage_key,
                checksum_sha256=original.checksum_sha256,
            )


def _start_attempt(
    session_factory: sessionmaker[Session],
    job_id: str,
    worker_identifier: str,
) -> None:
    now = _utc_now()
    with transaction_scope(session_factory) as session:
        job = session.get(ApplicationJob, job_id)
        if job is None or job.status not in {
            JobStatus.QUEUED.value,
            JobStatus.RETRYING.value,
            JobStatus.RUNNING.value,
        }:
            raise AnalysisWorkerError("The analysis job is not executable.")
        attempts = list(
            session.scalars(
                select(JobAttempt)
                .where(JobAttempt.job_id == job_id)
                .order_by(JobAttempt.attempt_number)
            )
        )
        if not attempts or attempts[-1].status != JobAttemptStatus.RUNNING.value:
            attempt_number = len(attempts) + 1
            session.add(
                JobAttempt(
                    id=str(
                        uuid5(
                            NAMESPACE_URL,
                            f"transloka:analysis-attempt:{job_id}:{attempt_number}",
                        )
                    ),
                    job_id=job_id,
                    attempt_number=attempt_number,
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
        job.status = JobStatus.RUNNING.value
        job.current_stage = "ANALYZE_DOCUMENT"
        job.started_at = job.started_at or now
        job.heartbeat_at = now
        session.flush()


def _complete_analysis(
    session_factory: sessionmaker[Session],
    loaded: LoadedAnalysisJob,
    analysis: PdfAnalysisResult,
    worker_identifier: str,
) -> AnalysisRunResult:
    now = _utc_now()
    scanned_page_count = sum(not page.has_text_layer for page in analysis.pages)
    document_class = _document_class(analysis)
    with transaction_scope(session_factory) as session:
        job = session.get(ApplicationJob, loaded.job_id)
        document = session.get(Document, loaded.command.document_id)
        project = session.get(Project, loaded.command.project_id)
        if job is None or document is None or project is None:
            raise AnalysisWorkerError("The analysis state disappeared before completion.")
        session.execute(delete(DocumentPage).where(DocumentPage.document_id == document.id))
        for page in analysis.pages:
            session.add(
                DocumentPage(
                    id=_page_id(document.id, page.page_number),
                    document_id=document.id,
                    source_page_number=page.page_number,
                    logical_page_number=None,
                    width_points=page.width_points,
                    height_points=page.height_points,
                    rotation_degrees=float(page.rotation_degrees),
                    page_type=(
                        PageType.DIGITAL.value if page.has_text_layer else PageType.SCANNED.value
                    ),
                    page_classification=None,
                    column_count=0,
                    reading_direction="LTR",
                    status=DocumentStatus.ANALYZED.value,
                    render_file_id=None,
                    thumbnail_file_id=None,
                    native_extraction_confidence=None,
                    ocr_confidence=None,
                    structure_confidence=None,
                    metadata_json=json.dumps(
                        {"has_text_layer": page.has_text_layer},
                        separators=(",", ":"),
                        sort_keys=True,
                    ),
                    created_at=now,
                    updated_at=now,
                )
            )
        document.title = analysis.title
        document.author = analysis.author
        document.document_class = document_class.value
        document.page_count = analysis.page_count
        document.has_text_layer = int(scanned_page_count < analysis.page_count)
        document.scanned_page_count = scanned_page_count
        document.status = DocumentStatus.ANALYZED.value
        document.analysis_json = json.dumps(
            {
                "checksum_sha256": loaded.checksum_sha256,
                "text_layer_estimate": analysis.text_layer_estimate,
            },
            separators=(",", ":"),
            sort_keys=True,
        )
        document.updated_at = now
        if project.active_document_id == document.id:
            project.status = ProjectStatus.WAITING_FOR_SETTINGS.value
            project.updated_at = now
        result_json = json.dumps(
            {
                "document_class": document_class.value,
                "document_id": document.id,
                "page_count": analysis.page_count,
                "scanned_page_count": scanned_page_count,
                "schema": "transloka.analysis.job.v1",
            },
            separators=(",", ":"),
            sort_keys=True,
        )
        job.status = JobStatus.COMPLETED.value
        job.progress = 1.0
        job.current_stage = JobStatus.COMPLETED.value
        job.result_json = result_json
        job.error_code = None
        job.error_message = None
        job.completed_at = now
        job.heartbeat_at = now
        _finish_attempt(session, job.id, JobAttemptStatus.COMPLETED, now, worker_identifier)
        session.flush()
    return AnalysisRunResult(
        job_id=loaded.job_id,
        document_id=loaded.command.document_id,
        status=JobStatus.COMPLETED,
        page_count=analysis.page_count,
        scanned_page_count=scanned_page_count,
    )


def _fail_analysis(
    session_factory: sessionmaker[Session],
    job_id: str,
    document_id: str,
    worker_identifier: str,
) -> None:
    now = _utc_now()
    try:
        with transaction_scope(session_factory) as session:
            job = session.get(ApplicationJob, job_id)
            document = session.get(Document, document_id)
            if job is None or job.status not in {
                JobStatus.QUEUED.value,
                JobStatus.RETRYING.value,
                JobStatus.RUNNING.value,
            }:
                return
            job.status = JobStatus.FAILED.value
            job.current_stage = JobStatus.FAILED.value
            job.error_code = "DOCUMENT_ANALYSIS_FAILED"
            job.error_message = "The document could not be analyzed safely."
            job.completed_at = now
            job.heartbeat_at = now
            _finish_attempt(session, job.id, JobAttemptStatus.FAILED, now, worker_identifier)
            if document is not None:
                document.status = DocumentStatus.FAILED.value
                document.updated_at = now
                project = session.get(Project, document.project_id)
                if project is not None and project.active_document_id == document.id:
                    project.status = ProjectStatus.FAILED.value
                    project.updated_at = now
    except Exception:
        return


def _finish_attempt(
    session: Session,
    job_id: str,
    status: JobAttemptStatus,
    completed_at: str,
    worker_identifier: str,
) -> None:
    attempt = session.scalar(
        select(JobAttempt)
        .where(JobAttempt.job_id == job_id)
        .order_by(JobAttempt.attempt_number.desc())
        .limit(1)
    )
    if attempt is None:
        return
    attempt.status = status.value
    attempt.worker_identifier = worker_identifier
    attempt.completed_at = completed_at


def _document_class(analysis: PdfAnalysisResult) -> DocumentClass:
    scanned = sum(not page.has_text_layer for page in analysis.pages)
    if scanned == 0:
        return DocumentClass.DIGITAL_PDF
    if scanned == analysis.page_count:
        return DocumentClass.SCANNED_PDF
    return DocumentClass.HYBRID_PDF


def _page_id(document_id: str, page_number: int) -> str:
    return f"pag_{uuid5(NAMESPACE_URL, f'transloka:page:{document_id}:{page_number}')}"


def _validate_identifier(value: str, prefix: str) -> None:
    if type(value) is not str or not value.startswith(prefix):
        raise AnalysisWorkerError("An analysis command identifier is invalid.")
    try:
        parsed = UUID(value[len(prefix) :])
    except (ValueError, AttributeError):
        raise AnalysisWorkerError("An analysis command identifier is invalid.") from None
    if str(parsed) != value[len(prefix) :]:
        raise AnalysisWorkerError("An analysis command identifier is invalid.")


def _worker_identifier(value: str | None) -> str:
    if value is None:
        return "transloka-analysis-worker"
    if not value or value != value.strip() or not value.isprintable() or len(value) > 200:
        raise ValueError("The worker identifier is invalid.")
    return value


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


__all__ = [
    "ANALYSIS_COMMAND_SCHEMA",
    "AnalysisCommand",
    "AnalysisRunResult",
    "AnalysisWorkerError",
    "DatabaseAnalysisJobRunner",
]
