import hashlib
import json
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Annotated, Any, cast
from uuid import uuid4

from fastapi import APIRouter, Depends, Header, Request, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker
from transloka_api.exception_handlers import TransLokaError
from transloka_api.middleware import get_request_id
from transloka_api.schemas import ErrorResponse
from transloka_api.schemas.projects import ResponseMeta
from transloka_core.database import transaction_scope
from transloka_core.database.models.document_ir import DocumentBlock, DocumentSegment, SegmentStatus
from transloka_core.database.models.documents import Document, DocumentStatus
from transloka_core.database.models.jobs import ApplicationJob, JobStatus, JobType
from transloka_core.database.models.pages import DocumentPage
from transloka_core.database.models.projects import Project, ReconstructionMode
from transloka_core.database.models.reconstruction import (
    ReconstructionBlock,
    ReconstructionBlockStatus,
    ReconstructionJob,
    ReconstructionPage,
    ReconstructionStatus,
    ReconstructionStrategy,
    TargetPageMapping,
)
from transloka_core.database.models.warnings import Warning, WarningSeverity, WarningStatus
from transloka_core.jobs.cancellation import (
    CancellationJobNotFoundError,
    JobCancellationService,
    JobCannotBeCancelledError,
)
from transloka_core.jobs.dispatch import (
    InvalidJobDispatchError,
    JobDispatchService,
    JobIdempotencyConflictError,
    JobQueueUnavailableError,
)
from transloka_core.jobs.retry import (
    JobNotRetryableError,
    JobRetryLimitError,
    JobRetryService,
    RetryIdempotencyConflictError,
    RetryJobNotFoundError,
)

_ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    404: {"description": "The reconstruction resource was not found.", "model": ErrorResponse},
    409: {
        "description": "The reconstruction state does not allow this operation.",
        "model": ErrorResponse,
    },
    422: {"description": "The request contains invalid values.", "model": ErrorResponse},
    500: {"description": "An unexpected server error was normalized.", "model": ErrorResponse},
    503: {"description": "The reconstruction queue is unavailable.", "model": ErrorResponse},
}

router = APIRouter(prefix="/api/v1", tags=["Reconstruction"])

_ACTIVE_JOB_STATUSES = {
    JobStatus.CREATED.value,
    JobStatus.QUEUED.value,
    JobStatus.RUNNING.value,
    JobStatus.RETRYING.value,
    JobStatus.CANCELLATION_REQUESTED.value,
}
_TRANSLATED_DOCUMENT_STATUSES = {
    DocumentStatus.TRANSLATED.value,
    DocumentStatus.PARTIALLY_TRANSLATED.value,
    DocumentStatus.REVIEWING.value,
    DocumentStatus.REVIEWED.value,
    DocumentStatus.RECONSTRUCTING.value,
    DocumentStatus.RECONSTRUCTED.value,
    DocumentStatus.QUALITY_CHECKED.value,
    DocumentStatus.READY_FOR_EXPORT.value,
    DocumentStatus.EXPORTED.value,
}
_PLACEHOLDER_WARNING_TYPES = {"PLACEHOLDER_MISSING", "PLACEHOLDER_RESTORATION_FAILED"}


class ReconstructionBlockingIssue(BaseModel):
    code: str
    message: str


class ReconstructionWarning(BaseModel):
    code: str
    count: int = Field(ge=0)


class ReconstructionReadinessData(BaseModel):
    ready: bool
    blocking_issues: list[ReconstructionBlockingIssue]
    warnings: list[ReconstructionWarning]
    available_modes: list[ReconstructionMode]


class ReconstructionReadinessResponse(BaseModel):
    data: ReconstructionReadinessData
    meta: ResponseMeta


class ReconstructionSettings(BaseModel):
    model_config = ConfigDict(extra="allow")

    preserve_page_size: bool = True
    preserve_images: bool = True
    preserve_headers: bool = True
    preserve_footers: bool = True
    preserve_page_numbers: bool = True
    translate_captions: bool = True
    minimum_body_font_pt: float = Field(default=8, gt=0, le=72)
    maximum_font_reduction_percent: float = Field(default=10, ge=0, le=100)
    allow_page_addition: bool = True
    allow_column_change: bool = False
    table_complexity_fallback: str = "PRESERVE_AS_IMAGE"
    image_quality: str = "STANDARD"
    block_export_on_critical_errors: bool = True


class ReconstructionPreviewRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    page_id: str
    mode: ReconstructionMode
    settings: ReconstructionSettings = Field(default_factory=ReconstructionSettings)


class ReconstructionPreviewData(BaseModel):
    preview_id: str
    page_id: str
    mode: ReconstructionMode
    status: str
    temporary: bool
    warnings: list[ReconstructionBlockingIssue]


class ReconstructionPreviewResponse(BaseModel):
    data: ReconstructionPreviewData
    meta: ResponseMeta


class StartReconstructionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: ReconstructionMode
    page_ids: list[str] | None = None
    settings: ReconstructionSettings = Field(default_factory=ReconstructionSettings)


class ReconstructionJobData(BaseModel):
    job_id: str
    status: JobStatus


class ReconstructionJobResponse(BaseModel):
    data: ReconstructionJobData
    meta: ResponseMeta


class ReconstructionStatusData(BaseModel):
    status: str
    progress: float = Field(ge=0, le=1)
    completed_pages: int = Field(ge=0)
    total_source_pages: int = Field(ge=0)
    generated_target_pages: int = Field(ge=0)
    warning_count: int = Field(ge=0)
    critical_warning_count: int = Field(ge=0)
    active_job_id: str | None


class ReconstructionStatusResponse(BaseModel):
    data: ReconstructionStatusData
    meta: ResponseMeta


class RetryReconstructionPageRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    fallback_mode: ReconstructionMode
    override_settings: dict[str, object] = Field(default_factory=dict)


class ReconstructionPageData(BaseModel):
    id: str
    source_page_id: str
    target_page_start: int
    target_page_end: int
    strategy: ReconstructionStrategy
    status: ReconstructionStatus
    block_status: dict[str, ReconstructionBlockStatus]
    target_page_mapping: list[dict[str, object]]
    warnings: list[ReconstructionBlockingIssue]
    preview_endpoint: str | None


class ReconstructionPageResponse(BaseModel):
    data: ReconstructionPageData
    meta: ResponseMeta


def _get_session(request: Request) -> Iterator[Session]:
    with _session_factory(request)() as session:
        yield session


def _session_factory(request: Request) -> sessionmaker[Session]:
    factory = getattr(request.app.state, "session_factory", None)
    if not callable(factory):
        raise RuntimeError("The reconstruction database is not configured.")
    return cast(sessionmaker[Session], factory)


SessionDependency = Annotated[Session, Depends(_get_session)]


@router.get(
    "/projects/{project_id}/reconstruction-readiness",
    operation_id="get_reconstruction_readiness",
    response_model=ReconstructionReadinessResponse,
    responses=_ERROR_RESPONSES,
)
def get_reconstruction_readiness(
    project_id: str,
    request: Request,
    session: SessionDependency,
) -> ReconstructionReadinessResponse:
    project, document = _project_document(session, project_id)
    blockers, warnings = _readiness(session, project, document)
    return ReconstructionReadinessResponse(
        data=ReconstructionReadinessData(
            ready=not blockers,
            blocking_issues=blockers,
            warnings=warnings,
            available_modes=list(ReconstructionMode),
        ),
        meta=_meta(),
    )


@router.post(
    "/projects/{project_id}/reconstruction/preview",
    operation_id="preview_reconstruction",
    response_model=ReconstructionPreviewResponse,
    responses=_ERROR_RESPONSES,
)
def preview_reconstruction(
    project_id: str,
    payload: ReconstructionPreviewRequest,
    session: SessionDependency,
) -> ReconstructionPreviewResponse:
    project, document = _project_document(session, project_id)
    page = session.scalar(
        select(DocumentPage).where(
            DocumentPage.id == payload.page_id,
            DocumentPage.document_id == document.id,
        )
    )
    if page is None:
        raise TransLokaError(
            code="PAGE_NOT_FOUND",
            message="The requested reconstruction page was not found.",
            status_code=404,
        )
    warnings = _page_warnings(session, project.id, page.id)
    return ReconstructionPreviewResponse(
        data=ReconstructionPreviewData(
            preview_id=f"prv_{uuid4()}",
            page_id=page.id,
            mode=payload.mode,
            status="READY",
            temporary=True,
            warnings=warnings,
        ),
        meta=_meta(),
    )


@router.post(
    "/projects/{project_id}/reconstruction/start",
    operation_id="start_reconstruction",
    response_model=ReconstructionJobResponse,
    responses=_ERROR_RESPONSES,
    status_code=status.HTTP_202_ACCEPTED,
)
def start_reconstruction(
    project_id: str,
    payload: StartReconstructionRequest,
    request: Request,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=200)],
    session: SessionDependency,
) -> ReconstructionJobResponse:
    project, document = _project_document(session, project_id)
    existing = _job_for_idempotency(session, idempotency_key)
    if existing is not None:
        if (
            existing.job_type != JobType.RECONSTRUCT_DOCUMENT.value
            or existing.project_id != project_id
        ):
            raise TransLokaError(
                code="IDEMPOTENCY_CONFLICT",
                message="The idempotency key belongs to a different reconstruction request.",
                status_code=409,
            )
        existing_reconstruction = session.scalar(
            select(ReconstructionJob).where(ReconstructionJob.application_job_id == existing.id)
        )
        requested_settings = json.dumps(
            payload.settings.model_dump(), sort_keys=True, separators=(",", ":")
        )
        stored_page_ids: tuple[str, ...] = ()
        try:
            stored_page_ids = tuple(json.loads(existing.payload_json).get("page_ids", ()))
        except (TypeError, ValueError, AttributeError):
            pass
        if existing_reconstruction is not None and (
            existing_reconstruction.mode != payload.mode.value
            or existing_reconstruction.settings_json != requested_settings
            or stored_page_ids != tuple(payload.page_ids or ())
        ):
            raise TransLokaError(
                code="IDEMPOTENCY_CONFLICT",
                message="The idempotency key belongs to a different reconstruction request.",
                status_code=409,
            )
        return _job_response(existing)

    active = _active_reconstruction(session, project_id)
    if active is not None:
        raise TransLokaError(
            code="RECONSTRUCTION_ALREADY_RUNNING",
            message="A reconstruction job is already running for this project.",
            status_code=409,
            details={"job_id": active.id},
        )

    blockers, _warnings = _readiness(session, project, document)
    critical = [issue for issue in blockers if issue.code == "CRITICAL_WARNING"]
    if critical:
        raise TransLokaError(
            code="RECONSTRUCTION_BLOCKED",
            message="Critical warnings must be resolved before reconstruction can start.",
            status_code=409,
            details={"blocking_issues": [issue.model_dump() for issue in critical]},
        )
    if blockers:
        raise TransLokaError(
            code="RECONSTRUCTION_NOT_READY",
            message="Reconstruction cannot start until all readiness blockers are resolved.",
            status_code=409,
            details={"blocking_issues": [issue.model_dump() for issue in blockers]},
        )

    page_ids = tuple(payload.page_ids or ())
    if page_ids:
        _validate_pages(session, document.id, page_ids)
    try:
        dispatch = JobDispatchService(
            _session_factory(request), _reconstruction_queue(request)
        ).dispatch(
            job_type=JobType.RECONSTRUCT_DOCUMENT,
            idempotency_key=idempotency_key,
            project_id=project_id,
            document_id=document.id,
            page_ids=page_ids,
        )
    except JobIdempotencyConflictError as exc:
        raise TransLokaError(
            code="IDEMPOTENCY_CONFLICT",
            message="The idempotency key belongs to a different reconstruction request.",
            status_code=409,
        ) from exc
    except JobQueueUnavailableError as exc:
        raise TransLokaError(
            code="QUEUE_UNAVAILABLE",
            message="The reconstruction job could not be queued.",
            status_code=503,
            details={"job_id": exc.job_id},
        ) from exc
    except InvalidJobDispatchError as exc:
        raise TransLokaError(
            code="VALIDATION_ERROR",
            message="The reconstruction request contains invalid values.",
            status_code=422,
        ) from exc

    settings_json = json.dumps(payload.settings.model_dump(), sort_keys=True, separators=(",", ":"))
    reconstruction_hash = hashlib.sha256(
        json.dumps(
            {
                "mode": payload.mode.value,
                "page_ids": page_ids,
                "settings": payload.settings.model_dump(),
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    with transaction_scope(_session_factory(request)) as write_session:
        write_session.add(
            ReconstructionJob(
                id=f"rcj_{uuid4()}",
                project_id=project_id,
                document_id=document.id,
                application_job_id=dispatch.job_id,
                mode=payload.mode.value,
                settings_version="m10-t20",
                settings_json=settings_json,
                status=ReconstructionStatus.PREPARING.value,
                progress=0.0,
                reconstruction_hash=reconstruction_hash,
                created_at=_utc_now(),
                started_at=None,
                completed_at=None,
                error_code=None,
            )
        )
        project_row = write_session.get(Project, project_id)
        document_row = write_session.get(Document, document.id)
        if project_row is not None:
            project_row.status = "RECONSTRUCTING"
        if document_row is not None:
            document_row.status = DocumentStatus.RECONSTRUCTING.value
    return ReconstructionJobResponse(
        data=ReconstructionJobData(job_id=dispatch.job_id, status=dispatch.status),
        meta=_meta(),
    )


@router.get(
    "/projects/{project_id}/reconstruction/status",
    operation_id="get_reconstruction_status",
    response_model=ReconstructionStatusResponse,
    responses=_ERROR_RESPONSES,
)
def get_reconstruction_status(
    project_id: str,
    session: SessionDependency,
) -> ReconstructionStatusResponse:
    project, document = _project_document(session, project_id)
    job = _latest_reconstruction(session, project_id)
    source_pages = int(
        session.scalar(
            select(func.count())
            .select_from(DocumentPage)
            .where(DocumentPage.document_id == document.id)
        )
        or 0
    )
    if job is None:
        data = _status_data(session, None, source_pages)
    else:
        data = _status_data(session, job, source_pages)
    return ReconstructionStatusResponse(data=data, meta=_meta())


@router.get(
    "/reconstruction/pages/{reconstruction_page_id}",
    operation_id="get_reconstruction_page",
    response_model=ReconstructionPageResponse,
    responses=_ERROR_RESPONSES,
)
def get_reconstruction_page(
    reconstruction_page_id: str,
    session: SessionDependency,
) -> ReconstructionPageResponse:
    page = session.get(ReconstructionPage, reconstruction_page_id)
    if page is None:
        raise TransLokaError(
            code="RECONSTRUCTION_PAGE_NOT_FOUND",
            message="The requested reconstruction page was not found.",
            status_code=404,
        )
    blocks = {
        row.block_id: ReconstructionBlockStatus(row.status)
        for row in session.scalars(
            select(ReconstructionBlock).where(ReconstructionBlock.reconstruction_page_id == page.id)
        )
    }
    mappings = [
        {
            "target_page_number": row.target_page_number,
            "mapping_type": row.mapping_type,
            "mapping_order": row.mapping_order,
        }
        for row in session.scalars(
            select(TargetPageMapping)
            .where(
                TargetPageMapping.reconstruction_job_id == page.reconstruction_job_id,
                TargetPageMapping.source_page_id == page.source_page_id,
            )
            .order_by(TargetPageMapping.mapping_order)
        )
    ]
    warning_rows = list(
        session.scalars(
            select(Warning).where(
                Warning.page_id == page.source_page_id,
                Warning.project_id
                == session.scalar(
                    select(ReconstructionJob.project_id).where(
                        ReconstructionJob.id == page.reconstruction_job_id
                    )
                ),
            )
        )
    )
    warnings = [
        ReconstructionBlockingIssue(code=row.warning_type, message=row.message)
        for row in warning_rows
    ]
    return ReconstructionPageResponse(
        data=ReconstructionPageData(
            id=page.id,
            source_page_id=page.source_page_id,
            target_page_start=page.target_page_start,
            target_page_end=page.target_page_end,
            strategy=ReconstructionStrategy(page.strategy),
            status=ReconstructionStatus(page.status),
            block_status=blocks,
            target_page_mapping=mappings,
            warnings=warnings,
            preview_endpoint=f"/api/v1/reconstruction/pages/{page.id}/preview",
        ),
        meta=_meta(),
    )


@router.post(
    "/reconstruction/pages/{reconstruction_page_id}/retry",
    operation_id="retry_reconstruction_page",
    response_model=ReconstructionJobResponse,
    responses=_ERROR_RESPONSES,
    status_code=status.HTTP_202_ACCEPTED,
)
def retry_reconstruction_page(
    reconstruction_page_id: str,
    payload: RetryReconstructionPageRequest,
    request: Request,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=200)],
    session: SessionDependency,
) -> ReconstructionJobResponse:
    page = session.get(ReconstructionPage, reconstruction_page_id)
    if page is None:
        raise TransLokaError(
            code="RECONSTRUCTION_PAGE_NOT_FOUND",
            message="The requested reconstruction page was not found.",
            status_code=404,
        )
    reconstruction_job = session.get(ReconstructionJob, page.reconstruction_job_id)
    if reconstruction_job is None or reconstruction_job.application_job_id is None:
        raise TransLokaError(
            code="RECONSTRUCTION_JOB_NOT_FOUND",
            message="The reconstruction job was not found.",
            status_code=404,
        )
    try:
        result = JobRetryService(_session_factory(request)).request(
            reconstruction_job.application_job_id,
            idempotency_key=idempotency_key,
            retry_failed_items_only=True,
            reason=f"PAGE:{page.source_page_id}:{payload.fallback_mode.value}",
        )
    except RetryJobNotFoundError as exc:
        raise TransLokaError(
            code="RECONSTRUCTION_JOB_NOT_FOUND",
            message="The reconstruction job was not found.",
            status_code=404,
        ) from exc
    except RetryIdempotencyConflictError as exc:
        raise TransLokaError(
            code="IDEMPOTENCY_CONFLICT",
            message="The idempotency key belongs to a different retry request.",
            status_code=409,
        ) from exc
    except JobRetryLimitError as exc:
        raise TransLokaError(
            code="JOB_RETRY_LIMIT_REACHED",
            message="The reconstruction job retry limit has been reached.",
            status_code=409,
        ) from exc
    except JobNotRetryableError as exc:
        raise TransLokaError(
            code="JOB_STATE_INVALID",
            message="The reconstruction job does not allow retry.",
            status_code=409,
        ) from exc
    with transaction_scope(_session_factory(request)) as write_session:
        retry_page = write_session.get(ReconstructionPage, page.id)
        if retry_page is not None:
            retry_page.status = ReconstructionStatus.PREPARING.value
            retry_page.strategy = ReconstructionStrategy(payload.fallback_mode.value).value
            retry_page.updated_at = _utc_now()
    return ReconstructionJobResponse(
        data=ReconstructionJobData(job_id=result.job_id, status=result.status),
        meta=_meta(),
    )


@router.post(
    "/projects/{project_id}/reconstruction/cancel",
    operation_id="cancel_reconstruction",
    response_model=ReconstructionStatusResponse,
    responses=_ERROR_RESPONSES,
)
def cancel_reconstruction(
    project_id: str,
    request: Request,
    session: SessionDependency,
) -> ReconstructionStatusResponse:
    _project_document(session, project_id)
    job = _latest_reconstruction(session, project_id)
    if job is None or job.application_job_id is None:
        raise TransLokaError(
            code="RECONSTRUCTION_JOB_NOT_FOUND",
            message="The project has no reconstruction job.",
            status_code=404,
        )
    try:
        settings = request.app.state.settings
        JobCancellationService(
            _session_factory(request), settings.data_directories.temporary
        ).request(job.application_job_id, reason="User requested reconstruction cancellation.")
    except CancellationJobNotFoundError as exc:
        raise TransLokaError(
            code="RECONSTRUCTION_JOB_NOT_FOUND",
            message="The reconstruction job was not found.",
            status_code=404,
        ) from exc
    except JobCannotBeCancelledError as exc:
        raise TransLokaError(
            code="JOB_STATE_INVALID",
            message="The reconstruction job cannot be cancelled in its current state.",
            status_code=409,
        ) from exc
    with transaction_scope(_session_factory(request)) as write_session:
        row = write_session.get(ReconstructionJob, job.id)
        if row is not None:
            row.status = ReconstructionStatus.CANCELLED.value
            row.completed_at = _utc_now()
    with _session_factory(request)() as refreshed:
        project, document = _project_document(refreshed, project_id)
        source_pages = int(
            refreshed.scalar(
                select(func.count())
                .select_from(DocumentPage)
                .where(DocumentPage.document_id == document.id)
            )
            or 0
        )
        return ReconstructionStatusResponse(
            data=_status_data(
                refreshed, _latest_reconstruction(refreshed, project.id), source_pages
            ),
            meta=_meta(),
        )


def _reconstruction_queue(request: Request) -> Any:
    queue = getattr(request.app.state, "reconstruction_queue", None)
    if queue is None:
        queue = getattr(request.app.state, "job_queue", None)
    if queue is None:
        raise TransLokaError(
            code="QUEUE_NOT_CONFIGURED",
            message="The reconstruction queue is not configured.",
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        )
    return queue


def _project_document(session: Session, project_id: str) -> tuple[Project, Document]:
    project = session.get(Project, project_id)
    if project is None:
        raise TransLokaError(
            code="PROJECT_NOT_FOUND",
            message="The requested project was not found.",
            status_code=404,
        )
    if project.active_document_id is None:
        raise TransLokaError(
            code="RECONSTRUCTION_NOT_READY",
            message="The project does not have an active document.",
            status_code=409,
            details={
                "blocking_issues": [
                    {"code": "NO_ACTIVE_DOCUMENT", "message": "Select an active document."}
                ]
            },
        )
    document = session.get(Document, project.active_document_id)
    if document is None or document.project_id != project.id:
        raise TransLokaError(
            code="RECONSTRUCTION_NOT_READY",
            message="The active document is unavailable.",
            status_code=409,
            details={
                "blocking_issues": [
                    {"code": "NO_ACTIVE_DOCUMENT", "message": "Select an active document."}
                ]
            },
        )
    return project, document


def _readiness(
    session: Session, project: Project, document: Document
) -> tuple[list[ReconstructionBlockingIssue], list[ReconstructionWarning]]:
    blockers: list[ReconstructionBlockingIssue] = []
    warnings: list[ReconstructionWarning] = []
    if document.status not in _TRANSLATED_DOCUMENT_STATUSES:
        translated_count = int(
            session.scalar(
                select(func.count())
                .select_from(DocumentSegment)
                .join(DocumentBlock, DocumentBlock.id == DocumentSegment.block_id)
                .join(DocumentPage, DocumentPage.id == DocumentBlock.page_id)
                .where(
                    DocumentPage.document_id == document.id,
                    DocumentSegment.status.in_(
                        (
                            SegmentStatus.MACHINE_TRANSLATED.value,
                            SegmentStatus.NEEDS_REVIEW.value,
                            SegmentStatus.USER_EDITED.value,
                            SegmentStatus.APPROVED.value,
                            SegmentStatus.LOCKED.value,
                        )
                    ),
                )
            )
            or 0
        )
        if translated_count == 0:
            blockers.append(
                ReconstructionBlockingIssue(
                    code="TRANSLATION_NOT_READY",
                    message="Complete translation before reconstruction.",
                )
            )
    placeholder_count = int(
        session.scalar(
            select(func.count())
            .select_from(Warning)
            .where(
                Warning.project_id == project.id,
                Warning.status == WarningStatus.OPEN.value,
                Warning.warning_type.in_(tuple(_PLACEHOLDER_WARNING_TYPES)),
            )
        )
        or 0
    )
    if placeholder_count:
        blockers.append(
            ReconstructionBlockingIssue(
                code="PLACEHOLDERS_INCOMPLETE",
                message="Resolve all placeholder warnings before reconstruction.",
            )
        )
    critical_count = int(
        session.scalar(
            select(func.count())
            .select_from(Warning)
            .where(
                Warning.project_id == project.id,
                Warning.status == WarningStatus.OPEN.value,
                Warning.severity == WarningSeverity.CRITICAL.value,
            )
        )
        or 0
    )
    if critical_count:
        blockers.append(
            ReconstructionBlockingIssue(
                code="CRITICAL_WARNING", message="Resolve critical warnings before reconstruction."
            )
        )
    low_confidence_count = int(
        session.scalar(
            select(func.count())
            .select_from(Warning)
            .where(
                Warning.project_id == project.id,
                Warning.status == WarningStatus.OPEN.value,
                Warning.severity.in_(
                    (
                        WarningSeverity.LOW.value,
                        WarningSeverity.MEDIUM.value,
                        WarningSeverity.HIGH.value,
                    )
                ),
            )
        )
        or 0
    )
    if low_confidence_count:
        warnings.append(ReconstructionWarning(code="OPEN_WARNINGS", count=low_confidence_count))
    return blockers, warnings


def _validate_pages(session: Session, document_id: str, page_ids: tuple[str, ...]) -> None:
    count = int(
        session.scalar(
            select(func.count())
            .select_from(DocumentPage)
            .where(DocumentPage.document_id == document_id, DocumentPage.id.in_(page_ids))
        )
        or 0
    )
    if count != len(set(page_ids)):
        raise TransLokaError(
            code="PAGE_NOT_FOUND",
            message="One or more requested pages were not found.",
            status_code=404,
        )


def _job_for_idempotency(session: Session, key: str) -> ApplicationJob | None:
    return session.scalar(select(ApplicationJob).where(ApplicationJob.idempotency_key == key))


def _active_reconstruction(session: Session, project_id: str) -> ApplicationJob | None:
    return session.scalar(
        select(ApplicationJob)
        .where(
            ApplicationJob.project_id == project_id,
            ApplicationJob.job_type == JobType.RECONSTRUCT_DOCUMENT.value,
            ApplicationJob.status.in_(tuple(_ACTIVE_JOB_STATUSES)),
        )
        .order_by(ApplicationJob.created_at.desc(), ApplicationJob.id.desc())
        .limit(1)
    )


def _latest_reconstruction(session: Session, project_id: str) -> ReconstructionJob | None:
    return session.scalar(
        select(ReconstructionJob)
        .where(ReconstructionJob.project_id == project_id)
        .order_by(ReconstructionJob.created_at.desc(), ReconstructionJob.id.desc())
        .limit(1)
    )


def _status_data(
    session: Session, job: ReconstructionJob | None, source_pages: int
) -> ReconstructionStatusData:
    if job is None:
        return ReconstructionStatusData(
            status="NOT_STARTED",
            progress=0.0,
            completed_pages=0,
            total_source_pages=source_pages,
            generated_target_pages=0,
            warning_count=0,
            critical_warning_count=0,
            active_job_id=None,
        )
    completed_pages = int(
        session.scalar(
            select(func.count())
            .select_from(ReconstructionPage)
            .where(
                ReconstructionPage.reconstruction_job_id == job.id,
                ReconstructionPage.status.in_(
                    (
                        ReconstructionStatus.COMPLETED.value,
                        ReconstructionStatus.COMPLETED_WITH_WARNINGS.value,
                    )
                ),
            )
        )
        or 0
    )
    generated_pages = int(
        session.scalar(
            select(
                func.coalesce(
                    func.sum(
                        ReconstructionPage.target_page_end
                        - ReconstructionPage.target_page_start
                        + 1
                    ),
                    0,
                )
            ).where(ReconstructionPage.reconstruction_job_id == job.id)
        )
        or 0
    )
    warning_count = int(
        session.scalar(
            select(func.coalesce(func.sum(ReconstructionPage.warning_count), 0)).where(
                ReconstructionPage.reconstruction_job_id == job.id
            )
        )
        or 0
    )
    critical_count = int(
        session.scalar(
            select(func.count())
            .select_from(Warning)
            .where(
                Warning.project_id == job.project_id,
                Warning.status == WarningStatus.OPEN.value,
                Warning.severity == WarningSeverity.CRITICAL.value,
            )
        )
        or 0
    )
    app_job = (
        session.get(ApplicationJob, job.application_job_id) if job.application_job_id else None
    )
    status_value = (
        app_job.status
        if app_job is not None and app_job.status in _ACTIVE_JOB_STATUSES
        else job.status
    )
    return ReconstructionStatusData(
        status=status_value,
        progress=job.progress,
        completed_pages=completed_pages,
        total_source_pages=source_pages,
        generated_target_pages=generated_pages,
        warning_count=warning_count,
        critical_warning_count=critical_count,
        active_job_id=job.application_job_id,
    )


def _page_warnings(
    session: Session, project_id: str, page_id: str
) -> list[ReconstructionBlockingIssue]:
    return [
        ReconstructionBlockingIssue(code=row.warning_type, message=row.message)
        for row in session.scalars(
            select(Warning).where(
                Warning.project_id == project_id,
                Warning.page_id == page_id,
                Warning.status == WarningStatus.OPEN.value,
            )
        )
    ]


def _job_response(job: ApplicationJob) -> ReconstructionJobResponse:
    return ReconstructionJobResponse(
        data=ReconstructionJobData(job_id=job.id, status=JobStatus(job.status)), meta=_meta()
    )


def _meta() -> ResponseMeta:
    request_id = get_request_id()
    if request_id is None:
        raise RuntimeError("The request identifier is unavailable.")
    return ResponseMeta(request_id=request_id)


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")
