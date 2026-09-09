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
from transloka_core.database.models.jobs import (
    ApplicationJob,
    JobAttempt,
    JobAttemptStatus,
    JobStatus,
    JobType,
)
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
from transloka_reconstruction.settings import ReconstructionSettings as EngineReconstructionSettings
from transloka_worker.reconstruction import ReconstructionCommand, ReconstructionWorkerError

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
_RECONSTRUCTION_SETTINGS_VERSION = "rel-fid-04"


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
        requested_command = _reconstruction_command(project_id, document.id, payload)
        requested_settings = json.dumps(
            cast(EngineReconstructionSettings, requested_command.settings).to_dict(),
            sort_keys=True,
            separators=(",", ":"),
        )
        stored_page_ids: tuple[str, ...] = ()
        try:
            stored_page_ids = tuple(json.loads(existing.payload_json).get("page_ids", ()))
        except (TypeError, ValueError, AttributeError):
            pass
        if existing_reconstruction is None or (
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
    command = _reconstruction_command(project_id, document.id, payload)
    engine_settings = cast(EngineReconstructionSettings, command.settings)
    settings_json = json.dumps(engine_settings.to_dict(), sort_keys=True, separators=(",", ":"))
    reconstruction_hash = hashlib.sha256(
        json.dumps(
            {
                "command": command.to_payload(),
                "settings_version": _RECONSTRUCTION_SETTINGS_VERSION,
            },
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    completed = _completed_reconstruction(session, project_id, reconstruction_hash)
    if completed is not None:
        return _job_response(completed)
    reconstruction_id = f"rcj_{uuid4()}"
    queue = _ReconstructionDispatchQueue(
        _session_factory(request),
        _reconstruction_queue(request),
        reconstruction_id=reconstruction_id,
        project_id=project_id,
        document_id=document.id,
        mode=payload.mode.value,
        settings_json=settings_json,
        reconstruction_hash=reconstruction_hash,
    )
    try:
        dispatch = JobDispatchService(_session_factory(request), queue).dispatch(
            job_type=JobType.RECONSTRUCT_DOCUMENT,
            idempotency_key=idempotency_key,
            project_id=project_id,
            document_id=document.id,
            page_ids=page_ids,
            command_payload=command.to_payload(),
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
    queue = _reconstruction_queue(request)
    stored_application_job = session.get(ApplicationJob, reconstruction_job.application_job_id)
    if stored_application_job is None:
        raise TransLokaError(
            code="RECONSTRUCTION_JOB_NOT_FOUND",
            message="The reconstruction job was not found.",
            status_code=404,
        )
    retry_command = _retry_command(
        stored_application_job,
        source_page_id=page.source_page_id,
        mode=payload.fallback_mode,
        overrides=payload.override_settings,
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
        retry_job = write_session.get(ApplicationJob, reconstruction_job.application_job_id)
        retry_reconstruction = write_session.get(ReconstructionJob, reconstruction_job.id)
        if retry_page is not None:
            retry_page.status = ReconstructionStatus.PREPARING.value
            retry_page.strategy = (
                ReconstructionStrategy.RECONSTRUCT.value
                if payload.fallback_mode is ReconstructionMode.HYBRID
                else ReconstructionStrategy(payload.fallback_mode.value).value
            )
            retry_page.updated_at = _utc_now()
        if retry_job is not None and retry_reconstruction is not None and result.created:
            _update_retry_command(
                retry_job,
                retry_reconstruction,
                command=retry_command,
            )
            retry_job.status = JobStatus.QUEUED.value
            retry_job.queued_at = _utc_now()
            retry_job.error_code = None
            retry_job.error_message = None
            retry_reconstruction.status = ReconstructionStatus.PREPARING.value
            retry_reconstruction.progress = 0.0
            retry_reconstruction.completed_at = None
            retry_reconstruction.error_code = None
    if result.created:
        try:
            queue.enqueue(result.job_id)
        except Exception as exc:
            _mark_retry_dispatch_failed(
                _session_factory(request), result.job_id, reconstruction_job.id
            )
            raise TransLokaError(
                code="QUEUE_UNAVAILABLE",
                message="The reconstruction retry could not be queued.",
                status_code=503,
                details={"job_id": result.job_id},
            ) from exc
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


class _ReconstructionDispatchQueue:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        queue: Any,
        *,
        reconstruction_id: str,
        project_id: str,
        document_id: str,
        mode: str,
        settings_json: str,
        reconstruction_hash: str,
    ) -> None:
        self._session_factory = session_factory
        self._queue = queue
        self._reconstruction_id = reconstruction_id
        self._project_id = project_id
        self._document_id = document_id
        self._mode = mode
        self._settings_json = settings_json
        self._reconstruction_hash = reconstruction_hash

    @property
    def name(self) -> str:
        return cast(str, self._queue.name)

    def enqueue(self, job_id: str) -> None:
        now = _utc_now()
        with transaction_scope(self._session_factory) as session:
            session.add(
                ReconstructionJob(
                    id=self._reconstruction_id,
                    project_id=self._project_id,
                    document_id=self._document_id,
                    application_job_id=job_id,
                    mode=self._mode,
                    settings_version=_RECONSTRUCTION_SETTINGS_VERSION,
                    settings_json=self._settings_json,
                    status=ReconstructionStatus.PREPARING.value,
                    progress=0.0,
                    reconstruction_hash=self._reconstruction_hash,
                    created_at=now,
                    started_at=None,
                    completed_at=None,
                    error_code=None,
                )
            )
            project = session.get(Project, self._project_id)
            document = session.get(Document, self._document_id)
            if project is None or document is None:
                raise RuntimeError("The reconstruction parents are unavailable.")
            project.status = "RECONSTRUCTING"
            document.status = DocumentStatus.RECONSTRUCTING.value
        try:
            self._queue.enqueue(job_id)
        except Exception:
            failed_at = _utc_now()
            with transaction_scope(self._session_factory) as session:
                reconstruction = session.get(ReconstructionJob, self._reconstruction_id)
                if reconstruction is not None:
                    reconstruction.status = ReconstructionStatus.FAILED.value
                    reconstruction.error_code = "QUEUE_DISPATCH_FAILED"
                    reconstruction.completed_at = failed_at
            raise


def _reconstruction_command(
    project_id: str,
    document_id: str,
    payload: StartReconstructionRequest,
) -> ReconstructionCommand:
    values = payload.settings.model_dump()
    values["mode"] = payload.mode.value
    try:
        settings = EngineReconstructionSettings.from_dict(values)
        return ReconstructionCommand(
            project_id=project_id,
            document_id=document_id,
            mode=payload.mode.value,
            page_ids=tuple(payload.page_ids or ()),
            settings=settings,
        )
    except (ValueError, ReconstructionWorkerError) as exc:
        raise TransLokaError(
            code="VALIDATION_ERROR",
            message="The reconstruction request contains invalid settings.",
            status_code=422,
        ) from exc


def _retry_command(
    job: ApplicationJob,
    *,
    source_page_id: str,
    mode: ReconstructionMode,
    overrides: dict[str, object],
) -> ReconstructionCommand | None:
    try:
        current = ReconstructionCommand.from_payload_json(job.payload_json)
    except ReconstructionWorkerError:
        # Rows created before M11-REM-11 remain API-retry compatible, but the
        # production worker will fail them closed instead of guessing inputs.
        return None
    values = cast(EngineReconstructionSettings, current.settings).to_dict()
    values.update(overrides)
    values["mode"] = mode.value
    try:
        settings = EngineReconstructionSettings.from_dict(values)
        return ReconstructionCommand(
            project_id=current.project_id,
            document_id=current.document_id,
            mode=mode.value,
            page_ids=(source_page_id,),
            settings=settings,
        )
    except (TypeError, ValueError, ReconstructionWorkerError) as exc:
        raise TransLokaError(
            code="VALIDATION_ERROR",
            message="The reconstruction retry contains invalid settings.",
            status_code=422,
        ) from exc


def _update_retry_command(
    job: ApplicationJob,
    reconstruction: ReconstructionJob,
    *,
    command: ReconstructionCommand | None,
) -> None:
    if command is None:
        return
    settings = cast(EngineReconstructionSettings, command.settings)
    job.payload_json = json.dumps(command.to_payload(), sort_keys=True, separators=(",", ":"))
    reconstruction.mode = cast(ReconstructionMode, command.mode).value
    reconstruction.settings_json = json.dumps(
        settings.to_dict(), sort_keys=True, separators=(",", ":")
    )


def _mark_retry_dispatch_failed(
    session_factory: sessionmaker[Session], job_id: str, reconstruction_job_id: str
) -> None:
    now = _utc_now()
    with transaction_scope(session_factory) as session:
        job = session.get(ApplicationJob, job_id)
        reconstruction = session.get(ReconstructionJob, reconstruction_job_id)
        if job is not None:
            job.status = JobStatus.FAILED.value
            job.current_stage = JobStatus.FAILED.value
            job.error_code = "QUEUE_DISPATCH_FAILED"
            job.error_message = "The reconstruction retry could not be queued."
            job.queued_at = None
            job.completed_at = now
        if reconstruction is not None:
            reconstruction.status = ReconstructionStatus.FAILED.value
            reconstruction.error_code = "QUEUE_DISPATCH_FAILED"
            reconstruction.completed_at = now
        attempt = session.scalar(
            select(JobAttempt)
            .where(JobAttempt.job_id == job_id)
            .order_by(JobAttempt.attempt_number.desc())
            .limit(1)
        )
        if attempt is not None and attempt.status == JobAttemptStatus.RUNNING.value:
            attempt.status = JobAttemptStatus.FAILED.value
            attempt.completed_at = now
            attempt.error_code = "QUEUE_DISPATCH_FAILED"
            attempt.error_message = "The reconstruction retry could not be queued."


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


def _completed_reconstruction(
    session: Session, project_id: str, reconstruction_hash: str
) -> ApplicationJob | None:
    completed = (JobStatus.COMPLETED.value, JobStatus.COMPLETED_WITH_WARNINGS.value)
    return session.scalar(
        select(ApplicationJob)
        .join(
            ReconstructionJob,
            ReconstructionJob.application_job_id == ApplicationJob.id,
        )
        .where(
            ReconstructionJob.project_id == project_id,
            ReconstructionJob.reconstruction_hash == reconstruction_hash,
            ReconstructionJob.status.in_(completed),
            ApplicationJob.status.in_(completed),
        )
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
