import json
from collections.abc import Iterator
from typing import Annotated, Any, Literal, Never, cast

from fastapi import APIRouter, Depends, Header, Request, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker
from transloka_api.exception_handlers import TransLokaError
from transloka_api.middleware import get_request_id
from transloka_api.routers.pages import _segment_response
from transloka_api.schemas import ErrorResponse
from transloka_api.schemas.pages import PageEditorSegmentResponse
from transloka_api.schemas.projects import ResponseMeta
from transloka_api.services.source_resolution import (
    EmptyResolvedSourceError,
    InvalidResolutionSourceError,
    ResolveSource,
    SourceResolutionService,
    SourceRevisionConflictError,
    SourceSegmentLockedError,
    SourceSegmentNotFoundError,
)
from transloka_core.database import transaction_scope
from transloka_core.database.models.document_ir import DocumentBlock, DocumentSegment
from transloka_core.database.models.documents import Document
from transloka_core.database.models.jobs import ApplicationJob, JobStatus, JobType
from transloka_core.database.models.pages import DocumentPage, PageType
from transloka_core.database.models.projects import Project
from transloka_core.jobs.dispatch import (
    InvalidJobDispatchError,
    JobDispatchService,
    JobIdempotencyConflictError,
    JobQueueUnavailableError,
)
from transloka_worker.ocr import OCRCommand, OCRWorkerError

_ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    403: {
        "description": "The request was rejected by the local security policy.",
        "model": ErrorResponse,
    },
    404: {"description": "The OCR page or segment was not found.", "model": ErrorResponse},
    409: {"description": "The segment revision is stale.", "model": ErrorResponse},
    422: {"description": "The request contains invalid values.", "model": ErrorResponse},
    423: {"description": "The segment is locked.", "model": ErrorResponse},
    500: {"description": "An unexpected server error was normalized.", "model": ErrorResponse},
}
_QUEUE_NOT_CONFIGURED_RESPONSE = {
    "description": "The OCR queue is not configured.",
    "model": ErrorResponse,
}

router = APIRouter(tags=["OCR"])


class OCRPageSegmentResponse(PageEditorSegmentResponse):
    raw_ocr_text: str | None
    normalized_source_text: str


class OCRPageData(BaseModel):
    page_id: str
    raw_text: str
    resolved_source_text: str
    ocr_confidence: float | None = Field(default=None, ge=0.0, le=1.0)
    segments: list[OCRPageSegmentResponse]


class OCRPageResponse(BaseModel):
    data: OCRPageData
    meta: ResponseMeta


class StartOCRRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    page_ids: list[str] | None = None
    mode: Literal["AUTO", "FORCE"] = "AUTO"
    language: str = Field(default="en", min_length=1, max_length=20)
    detect_tables: bool = True
    detect_formulas: bool = True


class OCRJobData(BaseModel):
    job_id: str
    status: JobStatus


class OCRJobResponse(BaseModel):
    data: OCRJobData
    meta: ResponseMeta


class OCRStatusData(BaseModel):
    status: str
    selected_pages: int = Field(ge=0)
    completed_pages: int = Field(ge=0)
    failed_pages: int = Field(ge=0)
    progress: float = Field(ge=0.0, le=1.0)
    current_stage: str | None
    active_job_id: str | None


class OCRStatusResponse(BaseModel):
    data: OCRStatusData
    meta: ResponseMeta


class SourceResolutionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    resolved_source_text: str = Field(min_length=1)
    resolution_source: Literal["AUTO", "AUTOMATIC", "MANUAL", "NATIVE", "OCR"] = "MANUAL"
    expected_revision: int = Field(ge=0)
    reason: str | None = Field(default=None, max_length=2000)


class SourceResolutionSegmentResponse(OCRPageSegmentResponse):
    resolution_source: str


class SourceResolutionResponse(BaseModel):
    data: SourceResolutionSegmentResponse
    meta: ResponseMeta


def get_ocr_session(request: Request) -> Iterator[Session]:
    try:
        factory = request.app.state.session_factory
    except AttributeError as exc:
        raise RuntimeError("The OCR database is not configured.") from exc
    if not callable(factory):
        raise RuntimeError("The OCR database is not configured.")
    with transaction_scope(cast(sessionmaker[Session], factory)) as session:
        yield session


OCRSession = Annotated[Session, Depends(get_ocr_session)]


@router.post(
    "/api/v1/documents/{document_id}/ocr/start",
    operation_id="start_document_ocr",
    response_model=OCRJobResponse,
    responses={**_ERROR_RESPONSES, 503: _QUEUE_NOT_CONFIGURED_RESPONSE},
    status_code=status.HTTP_202_ACCEPTED,
)
def start_document_ocr(
    document_id: str,
    payload: StartOCRRequest,
    request: Request,
    session: OCRSession,
    idempotency_key: Annotated[
        str,
        Header(alias="Idempotency-Key", min_length=1, max_length=200),
    ],
) -> OCRJobResponse:
    document, project = _get_document_project(session, document_id)
    page_ids = tuple(payload.page_ids or ())
    if payload.mode == "AUTO" and payload.page_ids is not None:
        _raise_validation_error("Automatic OCR must not include explicit page identifiers.")
    if payload.mode == "FORCE" and not page_ids:
        _raise_validation_error("Forced OCR requires at least one page identifier.")
    if page_ids:
        available = frozenset(
            session.scalars(select(DocumentPage.id).where(DocumentPage.document_id == document_id))
        )
        if not set(page_ids).issubset(available) or len(set(page_ids)) != len(page_ids):
            _raise_validation_error("An OCR page identifier is invalid for this document.")

    try:
        command = OCRCommand(
            project_id=project.id,
            document_id=document.id,
            mode=payload.mode,
            page_ids=page_ids,
            language=payload.language,
            detect_tables=payload.detect_tables,
            detect_formulas=payload.detect_formulas,
        )
        result = JobDispatchService(_session_factory(request), _ocr_queue(request)).dispatch(
            job_type=JobType.OCR_DOCUMENT,
            idempotency_key=idempotency_key,
            project_id=project.id,
            document_id=document.id,
            page_ids=page_ids,
            command_payload=command.to_payload(),
        )
    except JobIdempotencyConflictError as exc:
        raise TransLokaError(
            code="IDEMPOTENCY_CONFLICT",
            message="The idempotency key belongs to a different OCR request.",
            status_code=409,
        ) from exc
    except JobQueueUnavailableError as exc:
        raise TransLokaError(
            code="QUEUE_UNAVAILABLE",
            message="The OCR job could not be queued.",
            status_code=503,
            details={"job_id": exc.job_id},
        ) from exc
    except (InvalidJobDispatchError, OCRWorkerError) as exc:
        raise TransLokaError(
            code="VALIDATION_ERROR",
            message="The OCR request contains invalid values.",
            status_code=422,
        ) from exc

    return OCRJobResponse(
        data=OCRJobData(job_id=result.job_id, status=result.status),
        meta=ResponseMeta(request_id=_request_id()),
    )


@router.get(
    "/api/v1/documents/{document_id}/ocr/status",
    operation_id="get_document_ocr_status",
    response_model=OCRStatusResponse,
    responses=_ERROR_RESPONSES,
)
def get_document_ocr_status(document_id: str, session: OCRSession) -> OCRStatusResponse:
    _get_document_project(session, document_id)
    job = session.scalar(
        select(ApplicationJob)
        .where(
            ApplicationJob.document_id == document_id,
            ApplicationJob.job_type == JobType.OCR_DOCUMENT.value,
        )
        .order_by(ApplicationJob.created_at.desc(), ApplicationJob.id.desc())
        .limit(1)
    )
    if job is None:
        data = OCRStatusData(
            status="NOT_STARTED",
            selected_pages=0,
            completed_pages=0,
            failed_pages=0,
            progress=0.0,
            current_stage=None,
            active_job_id=None,
        )
    else:
        selected, completed, failed = _ocr_result_counts(session, job)
        data = OCRStatusData(
            status=job.status,
            selected_pages=selected,
            completed_pages=completed,
            failed_pages=failed,
            progress=job.progress,
            current_stage=job.current_stage,
            active_job_id=job.id,
        )
    return OCRStatusResponse(data=data, meta=ResponseMeta(request_id=_request_id()))


@router.get(
    "/api/v1/pages/{page_id}/ocr",
    operation_id="get_page_ocr",
    response_model=OCRPageResponse,
    responses=_ERROR_RESPONSES,
)
def get_page_ocr(page_id: str, session: OCRSession) -> OCRPageResponse:
    page = session.get(DocumentPage, page_id)
    if page is None:
        _raise_page_not_found()

    rows = list(
        session.scalars(
            select(DocumentSegment)
            .join(DocumentBlock, DocumentSegment.block_id == DocumentBlock.id)
            .where(DocumentBlock.page_id == page_id)
            .order_by(
                DocumentBlock.page_reading_order,
                DocumentBlock.id,
                DocumentSegment.segment_order,
                DocumentSegment.id,
            )
        )
    )
    return OCRPageResponse(
        data=OCRPageData(
            page_id=page_id,
            raw_text="\n".join(
                row.ocr_text for row in rows if row.ocr_text and row.ocr_text.strip()
            ),
            resolved_source_text="\n".join(row.resolved_source_text for row in rows),
            ocr_confidence=page.ocr_confidence,
            segments=[_ocr_segment_response(row) for row in rows],
        ),
        meta=ResponseMeta(request_id=_request_id()),
    )


@router.patch(
    "/api/v1/segments/{segment_id}/source-resolution",
    operation_id="resolve_segment_source",
    response_model=SourceResolutionResponse,
    responses=_ERROR_RESPONSES,
)
def resolve_segment_source(
    segment_id: str,
    payload: SourceResolutionRequest,
    session: OCRSession,
) -> SourceResolutionResponse:
    try:
        row = SourceResolutionService(session).resolve(
            segment_id,
            ResolveSource(
                resolved_source_text=payload.resolved_source_text,
                expected_revision=payload.expected_revision,
                resolution_source=payload.resolution_source,
                reason=payload.reason,
            ),
        )
    except SourceSegmentNotFoundError as exc:
        _raise_segment_not_found(str(exc))
    except SourceSegmentLockedError as exc:
        _raise_segment_locked(str(exc))
    except SourceRevisionConflictError as exc:
        _raise_revision_conflict(exc.expected_revision, exc.current_revision)
    except (EmptyResolvedSourceError, InvalidResolutionSourceError) as exc:
        _raise_validation_error(str(exc))

    return SourceResolutionResponse(
        data=SourceResolutionSegmentResponse(
            **_ocr_segment_response(row).model_dump(),
            resolution_source=payload.resolution_source,
        ),
        meta=ResponseMeta(request_id=_request_id()),
    )


def _ocr_segment_response(row: DocumentSegment) -> OCRPageSegmentResponse:
    return OCRPageSegmentResponse(
        **_segment_response(row).model_dump(),
        raw_ocr_text=row.ocr_text,
        normalized_source_text=row.normalized_source_text,
    )


def _get_document_project(session: Session, document_id: str) -> tuple[Document, Project]:
    document = session.get(Document, document_id)
    if document is None:
        raise TransLokaError(
            code="DOCUMENT_NOT_FOUND",
            message="The requested OCR document was not found.",
            status_code=404,
        )
    project = session.get(Project, document.project_id)
    if project is None or project.active_document_id != document.id:
        raise TransLokaError(
            code="OCR_NOT_READY",
            message="The OCR document is not the active project document.",
            status_code=409,
        )
    return document, project


def _session_factory(request: Request) -> sessionmaker[Session]:
    factory = getattr(request.app.state, "session_factory", None)
    if not callable(factory):
        raise RuntimeError("The OCR database is not configured.")
    return cast(sessionmaker[Session], factory)


def _ocr_queue(request: Request) -> Any:
    queue = getattr(request.app.state, "ocr_queue", None)
    if queue is None:
        raise TransLokaError(
            code="QUEUE_NOT_CONFIGURED",
            message="The OCR queue is not configured.",
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        )
    return queue


def _ocr_result_counts(session: Session, job: ApplicationJob) -> tuple[int, int, int]:
    if job.result_json is not None:
        try:
            result = json.loads(job.result_json)
            selected = result["selected_pages"]
            completed = result["completed_pages"]
            failed = result["failed_pages"]
        except (KeyError, TypeError, ValueError):
            raise RuntimeError("The stored OCR result is invalid.") from None
        if not all(isinstance(value, list) for value in (selected, completed, failed)):
            raise RuntimeError("The stored OCR result is invalid.")
        return len(selected), len(completed), len(failed)

    command = OCRCommand.from_payload_json(job.payload_json)
    if command.mode == "FORCE":
        return len(command.page_ids), 0, 0
    selected = (
        session.scalar(
            select(func.count())
            .select_from(DocumentPage)
            .where(
                DocumentPage.document_id == job.document_id,
                DocumentPage.page_type.in_([PageType.SCANNED.value, PageType.HYBRID.value]),
            )
        )
        or 0
    )
    return selected, 0, 0


def _request_id() -> str:
    request_id = get_request_id()
    if request_id is None:
        raise RuntimeError("The request ID middleware is not configured.")
    return request_id


def _raise_page_not_found() -> Never:
    raise TransLokaError(
        code="PAGE_NOT_FOUND",
        message="The requested OCR page was not found.",
        status_code=status.HTTP_404_NOT_FOUND,
    )


def _raise_segment_not_found(message: str = "The segment was not found.") -> Never:
    raise TransLokaError(
        code="SEGMENT_NOT_FOUND",
        message=message,
        status_code=status.HTTP_404_NOT_FOUND,
    )


def _raise_segment_locked(message: str = "The segment is locked.") -> Never:
    raise TransLokaError(
        code="SEGMENT_LOCKED",
        message=message,
        status_code=status.HTTP_423_LOCKED,
    )


def _raise_revision_conflict(expected_revision: int, current_revision: int) -> Never:
    raise TransLokaError(
        code="REVISION_CONFLICT",
        message="The segment was changed after it was loaded.",
        status_code=status.HTTP_409_CONFLICT,
        details={
            "expected_revision": expected_revision,
            "current_revision": current_revision,
        },
    )


def _raise_validation_error(message: str = "The request contains invalid values.") -> Never:
    raise TransLokaError(
        code="VALIDATION_ERROR",
        message=message,
        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
    )
