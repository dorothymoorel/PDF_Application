from collections.abc import Mapping
from datetime import UTC, datetime
from shutil import disk_usage
from typing import Annotated, Any, Literal, Never, cast
from uuid import NAMESPACE_URL, uuid5

from fastapi import APIRouter, Depends, File, Form, Header, Request, UploadFile, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker
from transloka_api.config import (
    DEFAULT_MAX_PDF_OBJECTS,
    DEFAULT_MAX_PDF_PAGES,
    Settings,
)
from transloka_api.exception_handlers import TransLokaError
from transloka_api.middleware import get_request_id
from transloka_api.routers.projects import ProjectSession, _raise_project_error
from transloka_api.schemas import ErrorResponse
from transloka_api.schemas.projects import ResponseMeta
from transloka_api.services.imports import (
    EmptyUploadError,
    ImportService,
    InvalidUploadMetadataError,
    OriginalImportConflictError,
    StagedUpload,
    UploadInterruptedError,
    UploadStorageError,
    UploadTooLargeError,
    ValidatedUploadMismatchError,
)
from transloka_api.services.projects import ProjectService
from transloka_core.database.models.documents import Document, DocumentClass, DocumentStatus
from transloka_core.database.models.files import StoredFile
from transloka_core.database.models.jobs import JobStatus, JobType
from transloka_core.database.models.projects import Project, ProjectStatus
from transloka_core.jobs.dispatch import (
    InvalidJobDispatchError,
    JobDispatchService,
    JobIdempotencyConflictError,
    JobQueueUnavailableError,
)
from transloka_core.repositories.files import StoredFilesRepository
from transloka_core.repositories.projects import ProjectRepositoryError, ProjectsRepository
from transloka_core.storage.local import LocalFileStorage
from transloka_documents.analysis import PdfAnalysisError, PdfAnalysisResult, analyze_pdf
from transloka_documents.validation import PdfValidationError, PdfValidationLimits, validate_pdf
from transloka_worker.analysis import AnalysisCommand, AnalysisWorkerError

_ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    400: {"description": "The upload stream was interrupted.", "model": ErrorResponse},
    403: {
        "description": "The request was rejected by the local security policy.",
        "model": ErrorResponse,
    },
    404: {"description": "The project was not found.", "model": ErrorResponse},
    409: {"description": "The idempotent import conflicts.", "model": ErrorResponse},
    413: {"description": "The uploaded file is too large.", "model": ErrorResponse},
    415: {"description": "The request is not multipart.", "model": ErrorResponse},
    422: {"description": "The upload metadata or content is invalid.", "model": ErrorResponse},
    500: {"description": "An unexpected server error was normalized.", "model": ErrorResponse},
    503: {"description": "The analysis job could not be queued.", "model": ErrorResponse},
}

_DOCUMENT_ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    403: {
        "description": "The request was rejected by the local security policy.",
        "model": ErrorResponse,
    },
    404: {"description": "The document was not found.", "model": ErrorResponse},
    422: {"description": "The request contains invalid values.", "model": ErrorResponse},
    500: {"description": "An unexpected server error was normalized.", "model": ErrorResponse},
}

router = APIRouter(prefix="/api/v1/projects", tags=["Documents"])
document_router = APIRouter(prefix="/api/v1/documents", tags=["Documents"])


class ImportedDocumentData(BaseModel):
    id: str
    project_id: str
    original_file_id: str
    status: DocumentStatus
    original_filename: str
    size_bytes: int
    checksum_sha256: str
    page_count: int
    title: str | None


class AnalysisJobData(BaseModel):
    id: str
    job_type: Literal["ANALYZE_DOCUMENT"] = "ANALYZE_DOCUMENT"
    status: JobStatus


class DocumentImportData(BaseModel):
    document: ImportedDocumentData
    job: AnalysisJobData


class DocumentImportResponse(BaseModel):
    data: DocumentImportData
    meta: ResponseMeta


class DocumentDetailData(BaseModel):
    id: str
    project_id: str
    original_file_id: str
    status: DocumentStatus
    original_filename: str
    size_bytes: int
    checksum_sha256: str
    page_count: int
    title: str | None


class DocumentDetailResponse(BaseModel):
    data: DocumentDetailData
    meta: ResponseMeta


def _require_multipart(request: Request) -> None:
    media_type = request.headers.get("content-type", "").partition(";")[0].strip().casefold()
    if media_type != "multipart/form-data":
        raise TransLokaError(
            code="UNSUPPORTED_MEDIA_TYPE",
            message="Document import requires multipart form data.",
            status_code=415,
        )


@router.post(
    "/{project_id}/documents/import",
    dependencies=[Depends(_require_multipart)],
    operation_id="import_document",
    response_model=DocumentImportResponse,
    responses=_ERROR_RESPONSES,
    status_code=status.HTTP_202_ACCEPTED,
)
def import_document(
    project_id: str,
    request: Request,
    session: ProjectSession,
    file: Annotated[UploadFile, File()],
    idempotency_key: Annotated[
        str,
        Header(alias="Idempotency-Key", min_length=1, max_length=200),
    ],
    set_as_active: Annotated[bool, Form()] = True,
) -> DocumentImportResponse:
    try:
        ProjectService(ProjectsRepository(session)).get(project_id)
    except ProjectRepositoryError as exc:
        _raise_project_error(exc)

    settings = cast(Settings, request.app.state.settings)
    service = ImportService(
        LocalFileStorage(settings.data_directories),
        settings.max_upload_bytes,
    )
    staged: StagedUpload | None = None
    try:
        staged = service.stage_upload(
            project_id=project_id,
            original_filename=file.filename or "",
            idempotency_key=idempotency_key,
            set_as_active=set_as_active,
            stream=file.file,
        )
        with staged.temporary.path.open("rb") as source:
            validation = validate_pdf(
                source,
                filename=staged.original_filename,
                mime_type=file.content_type or "",
                limits=PdfValidationLimits(
                    max_bytes=settings.max_upload_bytes,
                    max_pages=DEFAULT_MAX_PDF_PAGES,
                    max_objects=DEFAULT_MAX_PDF_OBJECTS,
                ),
                available_disk_bytes=disk_usage(settings.data_directories.root).free,
            )
        with staged.temporary.path.open("rb") as source:
            initial_analysis = analyze_pdf(source)
        original = service.store_original(
            staged,
            validation,
            StoredFilesRepository(session),
        )
        document = _create_or_reuse_document(
            session,
            staged,
            original.id,
            initial_analysis,
        )
        session.commit()
        command = AnalysisCommand(project_id=project_id, document_id=document.id)
        dispatch = JobDispatchService(
            _session_factory(request),
            _analysis_queue(request),
        ).dispatch(
            job_type=JobType.ANALYZE_DOCUMENT,
            idempotency_key=_analysis_idempotency_key(project_id, idempotency_key),
            project_id=project_id,
            document_id=document.id,
            command_payload=command.to_payload(),
        )
    except EmptyUploadError as exc:
        _raise_upload_error("EMPTY_UPLOAD", "The uploaded file is empty.", 422, exc)
    except UploadTooLargeError as exc:
        _raise_upload_error(
            "FILE_TOO_LARGE",
            "The uploaded file exceeds the configured size limit.",
            413,
            exc,
        )
    except UploadInterruptedError as exc:
        _raise_upload_error(
            "UPLOAD_INTERRUPTED",
            "The upload stream was interrupted.",
            400,
            exc,
        )
    except InvalidUploadMetadataError as exc:
        _raise_upload_error(
            "VALIDATION_ERROR",
            "The upload metadata is invalid.",
            422,
            exc,
        )
    except PdfValidationError as exc:
        _discard_after_failure(service, staged)
        _raise_upload_error(
            exc.code,
            exc.message,
            413 if exc.code == "FILE_TOO_LARGE" else 422,
            exc,
            details=exc.details,
        )
    except PdfAnalysisError as exc:
        _discard_after_failure(service, staged)
        _raise_upload_error(
            "DOCUMENT_ANALYSIS_FAILED",
            "The PDF could not be analyzed safely.",
            422,
            exc,
        )
    except OriginalImportConflictError as exc:
        _discard_after_failure(service, staged)
        _raise_upload_error(
            "IMPORT_CONFLICT",
            "The idempotency key belongs to a different original import.",
            409,
            exc,
        )
    except JobIdempotencyConflictError as exc:
        _raise_upload_error(
            "IDEMPOTENCY_CONFLICT",
            "The idempotency key belongs to a different analysis request.",
            409,
            exc,
        )
    except JobQueueUnavailableError as exc:
        raise TransLokaError(
            code="QUEUE_UNAVAILABLE",
            message="The document analysis job could not be queued.",
            status_code=503,
            details={"job_id": exc.job_id},
        ) from exc
    except (InvalidJobDispatchError, AnalysisWorkerError) as exc:
        _raise_upload_error(
            "VALIDATION_ERROR",
            "The document analysis request is invalid.",
            422,
            exc,
        )
    except ValidatedUploadMismatchError as exc:
        _discard_after_failure(service, staged)
        _raise_upload_error(
            "VALIDATED_UPLOAD_MISMATCH",
            "The validated upload changed before immutable storage.",
            422,
            exc,
        )
    except OSError as exc:
        _discard_after_failure(service, staged)
        _raise_upload_error(
            "INTERNAL_ERROR",
            "An internal server error occurred.",
            500,
            exc,
        )
    except UploadStorageError as exc:
        _discard_after_failure(service, staged)
        _raise_upload_error(
            "INTERNAL_ERROR",
            "An internal server error occurred.",
            500,
            exc,
        )
    finally:
        file.file.close()

    if staged is None:
        raise RuntimeError("The validated upload is unavailable.")
    session.expire_all()
    current_document = session.get(Document, document.id)
    if current_document is None:
        raise RuntimeError("The imported document is unavailable.")
    return DocumentImportResponse(
        data=DocumentImportData(
            document=ImportedDocumentData(
                id=current_document.id,
                project_id=current_document.project_id,
                original_file_id=current_document.original_file_id,
                status=DocumentStatus(current_document.status),
                original_filename=staged.original_filename,
                size_bytes=original.size_bytes,
                checksum_sha256=original.checksum_sha256,
                page_count=current_document.page_count,
                title=current_document.title,
            ),
            job=AnalysisJobData(
                id=dispatch.job_id,
                status=dispatch.status,
            ),
        ),
        meta=ResponseMeta(request_id=_request_id()),
    )


@document_router.get(
    "/{document_id}",
    operation_id="get_document",
    response_model=DocumentDetailResponse,
    responses=_DOCUMENT_ERROR_RESPONSES,
)
def get_document(document_id: str, session: ProjectSession) -> DocumentDetailResponse:
    document = session.get(Document, document_id)
    if document is None:
        raise TransLokaError(
            code="DOCUMENT_NOT_FOUND",
            message="The requested document was not found.",
            status_code=404,
        )
    stored = session.get(StoredFile, document.original_file_id)
    if stored is None:
        raise TransLokaError(
            code="DOCUMENT_NOT_FOUND",
            message="The requested document was not found.",
            status_code=404,
        )
    original_filename = stored.original_filename or stored.safe_filename
    # Ensure we never expose filesystem paths
    if (
        "/" in original_filename
        or "\\" in original_filename
        or original_filename != original_filename.strip()
    ):
        original_filename = stored.safe_filename
    return DocumentDetailResponse(
        data=DocumentDetailData(
            id=document.id,
            project_id=document.project_id,
            original_file_id=document.original_file_id,
            status=DocumentStatus(document.status),
            original_filename=original_filename,
            size_bytes=stored.size_bytes,
            checksum_sha256=stored.checksum_sha256,
            page_count=document.page_count,
            title=document.title,
        ),
        meta=ResponseMeta(request_id=_request_id()),
    )


def _create_or_reuse_document(
    session: Session,
    staged: StagedUpload,
    original_file_id: str,
    analysis: PdfAnalysisResult,
) -> Document:
    document_id = _document_id(staged.project_id, original_file_id)
    existing = session.scalar(
        select(Document).where(
            Document.project_id == staged.project_id,
            Document.original_file_id == original_file_id,
        )
    )
    if existing is not None:
        if existing.id != document_id or existing.page_count != analysis.page_count:
            raise OriginalImportConflictError("The existing document import is inconsistent.")
        _activate_document(session, staged, existing)
        return existing

    scanned_page_count = sum(not page.has_text_layer for page in analysis.pages)
    now = _utc_now()
    project = session.get(Project, staged.project_id)
    if project is None:
        raise OriginalImportConflictError("The import project is unavailable.")
    document = Document(
        id=document_id,
        project_id=project.id,
        original_file_id=original_file_id,
        ir_version="0.1",
        title=analysis.title,
        author=analysis.author,
        document_type=project.document_type,
        document_class=_document_class(analysis).value,
        source_language=project.source_language,
        target_language=project.target_language,
        page_count=analysis.page_count,
        word_count_estimate=None,
        has_text_layer=int(scanned_page_count < analysis.page_count),
        scanned_page_count=scanned_page_count,
        image_count=0,
        table_count=0,
        status=DocumentStatus.CREATED.value,
        metadata_json=None,
        analysis_json=None,
        created_at=now,
        updated_at=now,
    )
    session.add(document)
    _activate_document(session, staged, document)
    session.flush()
    return document


def _activate_document(session: Session, staged: StagedUpload, document: Document) -> None:
    if not staged.set_as_active:
        return
    project = session.get(Project, staged.project_id)
    if project is None:
        raise OriginalImportConflictError("The import project is unavailable.")
    project.active_document_id = document.id
    project.status = ProjectStatus.ANALYZING.value
    project.updated_at = _utc_now()


def _document_class(analysis: PdfAnalysisResult) -> DocumentClass:
    scanned = sum(not page.has_text_layer for page in analysis.pages)
    if scanned == 0:
        return DocumentClass.DIGITAL_PDF
    if scanned == analysis.page_count:
        return DocumentClass.SCANNED_PDF
    return DocumentClass.HYBRID_PDF


def _document_id(project_id: str, original_file_id: str) -> str:
    return f"doc_{uuid5(NAMESPACE_URL, f'transloka:document:{project_id}:{original_file_id}')}"


def _analysis_idempotency_key(project_id: str, import_key: str) -> str:
    token = uuid5(NAMESPACE_URL, f"transloka:analysis:{project_id}:{import_key}")
    return f"analysis-{token}"


def _session_factory(request: Request) -> sessionmaker[Session]:
    factory = getattr(request.app.state, "session_factory", None)
    if not callable(factory):
        raise RuntimeError("The document database is not configured.")
    return cast(sessionmaker[Session], factory)


def _analysis_queue(request: Request) -> Any:
    queue = getattr(request.app.state, "analysis_queue", None)
    if queue is None:
        raise RuntimeError("The document analysis queue is not configured.")
    return queue


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _request_id() -> str:
    request_id = get_request_id()
    if request_id is None:
        raise RuntimeError("The request identifier is unavailable.")
    return request_id


def _discard_after_failure(service: ImportService, staged: StagedUpload | None) -> None:
    if staged is not None:
        service.discard(staged)


def _raise_upload_error(
    code: str,
    message: str,
    status_code: int,
    exc: Exception,
    *,
    details: Mapping[str, object] | None = None,
) -> Never:
    raise TransLokaError(
        code=code,
        message=message,
        status_code=status_code,
        details=dict(details) if details is not None else None,
    ) from exc
