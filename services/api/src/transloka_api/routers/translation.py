from __future__ import annotations

import json
import os
import time
from collections.abc import Iterator
from dataclasses import replace
from datetime import UTC, datetime
from math import ceil
from typing import Annotated, Any, Literal, Never, Protocol, Self, cast

from fastapi import APIRouter, Depends, Header, Query, Request, status
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy import case, func, select
from sqlalchemy.orm import Session, sessionmaker
from transloka_api.exception_handlers import TransLokaError
from transloka_api.middleware import get_request_id
from transloka_api.schemas import ErrorResponse
from transloka_api.schemas.projects import ResponseMeta
from transloka_core.database import transaction_scope
from transloka_core.database.models.document_ir import DocumentBlock, DocumentSegment, SegmentStatus
from transloka_core.database.models.glossary import GlossaryConflict
from transloka_core.database.models.jobs import (
    ApplicationJob,
    JobAttempt,
    JobAttemptStatus,
    JobStatus,
    JobType,
)
from transloka_core.database.models.models import LocalModelRecord
from transloka_core.database.models.pages import DocumentPage
from transloka_core.database.models.projects import Project, TranslationStyle
from transloka_core.jobs.cancellation import (
    CancellationJobNotFoundError,
    JobCancellationService,
    JobCannotBeCancelledError,
)
from transloka_core.jobs.dispatch import (
    QUEUE_DISPATCH_FAILED,
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
from transloka_core.storage.local import LocalFileStorage
from transloka_glossary.snapshots import GlossarySnapshotError, create_glossary_snapshot
from transloka_translation.providers import ProviderHealthStatus
from transloka_translation.providers.ctranslate2 import MODEL_ID as CT2_MODEL_ID
from transloka_translation.providers.ctranslate2 import CTranslate2TranslationProvider
from transloka_translation.providers.groq import GROQ_MODELS, GroqTranslationProvider
from transloka_translation.providers.ollama import OllamaTranslationProvider
from transloka_worker.ctranslate2 import (
    CTranslate2ConfigurationError,
    ctranslate2_settings_from_environment,
)
from transloka_worker.health import PersistedWorkerHeartbeat, WorkerHeartbeatStore, WorkerStatus
from transloka_worker.translation import TranslationCommand, TranslationWorkerError

_ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    403: {
        "description": "The request was rejected by the local security policy.",
        "model": ErrorResponse,
    },
    404: {"description": "The project or translation job was not found.", "model": ErrorResponse},
    409: {
        "description": "Translation readiness or job state prevents the operation.",
        "model": ErrorResponse,
    },
    422: {"description": "The request contains invalid values.", "model": ErrorResponse},
    500: {"description": "An unexpected server error was normalized.", "model": ErrorResponse},
}
_ALREADY_RUNNING_RESPONSE = {
    "description": "An active full-document translation already exists.",
    "model": ErrorResponse,
}
_SERVICE_UNAVAILABLE_RESPONSE = {
    "description": "The local worker or translation queue is unavailable.",
    "model": ErrorResponse,
}
WORKER_HEARTBEAT_MAX_AGE_SECONDS = 15.0

router = APIRouter(prefix="/api/v1/projects", tags=["Translation"])


class TranslationBlockingIssue(BaseModel):
    code: str
    message: str


class TranslationReadinessWarning(BaseModel):
    code: str
    count: int = Field(ge=0)


class TranslationReadinessData(BaseModel):
    ready: bool
    blocking_issues: list[TranslationBlockingIssue]
    warnings: list[TranslationReadinessWarning]
    segment_count: int = Field(ge=0)
    estimated_batches: int = Field(ge=0)


class TranslationReadinessResponse(BaseModel):
    data: TranslationReadinessData
    meta: ResponseMeta


TranslationScope = Literal[
    "FULL_DOCUMENT",
    "UNTRANSLATED_ONLY",
    "UNREVIEWED_ONLY",
    "SECTION",
    "PAGE",
    "SELECTED_SEGMENTS",
]
ContextMode = Literal["NONE", "STANDARD", "EXTENDED"]
TranslationProviderType = Literal["OLLAMA", "GROQ", "CTRANSLATE2"]
GroqModelName = Literal["qwen/qwen3.8-27b", "openai/gpt-oss-120b"]


class StartTranslationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scope: TranslationScope = "FULL_DOCUMENT"
    section_ids: list[str] | None = None
    page_ids: list[str] | None = None
    segment_ids: list[str] | None = None
    provider_type: TranslationProviderType | None = None
    model_id: str | None = Field(default=None, min_length=1, max_length=200)
    cloud_model_name: GroqModelName | None = None
    cloud_consent: bool | None = None
    translation_style: TranslationStyle | None = None
    batch_size: int = Field(default=5, ge=1, le=100)
    context_mode: ContextMode = "STANDARD"
    retranslate_existing: bool = False
    skip_locked_segments: bool = True
    run_semantic_validation: bool = False

    @model_validator(mode="after")
    def validate_provider_selection(self) -> Self:
        provider_type = self.provider_type or "OLLAMA"
        if provider_type == "CTRANSLATE2":
            if self.model_id != CT2_MODEL_ID:
                raise ValueError(f"model_id must be {CT2_MODEL_ID} for CTranslate2.")
            if self.cloud_model_name is not None or self.cloud_consent is True:
                raise ValueError("Cloud fields are invalid for the CTranslate2 provider.")
            return self
        if provider_type == "OLLAMA":
            if self.model_id is None:
                raise ValueError("model_id is required for the Ollama provider.")
            if self.cloud_model_name is not None or self.cloud_consent is True:
                raise ValueError("Cloud fields are invalid for the Ollama provider.")
            return self
        if self.model_id is not None:
            raise ValueError("model_id is reserved for local translation models.")
        if self.cloud_model_name is None or self.cloud_consent is not True:
            raise ValueError("A Groq model and explicit cloud consent are required.")
        return self


class TranslationJobData(BaseModel):
    job_id: str
    status: JobStatus


class TranslationJobResponse(BaseModel):
    data: TranslationJobData
    meta: ResponseMeta


class TranslationStatusData(BaseModel):
    status: str
    total_segments: int = Field(ge=0)
    completed_segments: int = Field(ge=0)
    failed_segments: int = Field(ge=0)
    review_required_segments: int = Field(ge=0)
    progress: float = Field(ge=0.0, le=1.0)
    active_job_id: str | None
    current_batch: int = Field(ge=0)
    total_batches: int = Field(ge=0)
    unattempted_segments: int | None = Field(default=None, ge=0)
    provider_error_code: str | None = None
    retry_after_seconds: float | None = Field(default=None, ge=0.0)


class TranslationStatusResponse(BaseModel):
    data: TranslationStatusData
    meta: ResponseMeta


class CancelTranslationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    reason: str = Field(min_length=1, max_length=500)


class RetryTranslationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    use_smaller_batch: bool = True
    use_selected_model: bool = True


class _Readiness:
    def __init__(
        self,
        *,
        project: Project,
        segment_count: int,
        estimated_batches: int,
        blockers: list[TranslationBlockingIssue],
    ) -> None:
        self.project = project
        self.segment_count = segment_count
        self.estimated_batches = estimated_batches
        self.blockers = blockers


class _WorkerHeartbeatReader(Protocol):
    def read(self) -> PersistedWorkerHeartbeat | None: ...


@router.get(
    "/{project_id}/translation-readiness",
    operation_id="get_translation_readiness",
    response_model=TranslationReadinessResponse,
    responses=_ERROR_RESPONSES,
)
async def get_translation_readiness(
    project_id: str,
    request: Request,
    session: Annotated[Session, Depends(_get_session)],
    provider_type: Annotated[TranslationProviderType, Query()] = "OLLAMA",
    model_id: Annotated[str | None, Query(min_length=1, max_length=200)] = None,
    cloud_model_name: Annotated[GroqModelName | None, Query()] = None,
    cloud_consent: Annotated[bool, Query()] = False,
) -> TranslationReadinessResponse:
    readiness = await _collect_readiness(
        request,
        session,
        project_id,
        model_id,
        provider_type=provider_type,
        cloud_model_name=cloud_model_name,
        cloud_consent=cloud_consent,
    )
    return TranslationReadinessResponse(
        data=TranslationReadinessData(
            ready=not readiness.blockers,
            blocking_issues=readiness.blockers,
            warnings=[],
            segment_count=readiness.segment_count,
            estimated_batches=readiness.estimated_batches,
        ),
        meta=ResponseMeta(request_id=_request_id()),
    )


@router.post(
    "/{project_id}/translation/start",
    operation_id="start_translation",
    response_model=TranslationJobResponse,
    responses={
        **_ERROR_RESPONSES,
        429: _ALREADY_RUNNING_RESPONSE,
        503: _SERVICE_UNAVAILABLE_RESPONSE,
    },
    status_code=status.HTTP_202_ACCEPTED,
)
async def start_translation(
    project_id: str,
    payload: StartTranslationRequest,
    request: Request,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=200)],
    session: Annotated[Session, Depends(_get_session)],
) -> TranslationJobResponse:
    readiness = await _collect_readiness(
        request,
        session,
        project_id,
        payload.model_id,
        provider_type=payload.provider_type or "OLLAMA",
        cloud_model_name=payload.cloud_model_name,
        cloud_consent=payload.cloud_consent is True,
    )
    if any(issue.code == "WORKER_UNAVAILABLE" for issue in readiness.blockers):
        _raise_worker_unavailable()
    if readiness.blockers:
        raise TransLokaError(
            code="TRANSLATION_NOT_READY",
            message="Translation cannot start until all readiness blockers are resolved.",
            status_code=409,
            details={"blocking_issues": [issue.model_dump() for issue in readiness.blockers]},
        )

    document_id = readiness.project.active_document_id
    if document_id is None:
        raise TransLokaError(
            code="TRANSLATION_NOT_READY",
            message="The project does not have an active document.",
            status_code=409,
            details={
                "blocking_issues": [
                    {"code": "NO_ACTIVE_DOCUMENT", "message": "Select an active document."}
                ]
            },
        )

    queue = _translation_queue(request)
    session_factory = _session_factory(request)
    try:
        with transaction_scope(session_factory) as snapshot_session:
            snapshot = create_glossary_snapshot(
                session=snapshot_session,
                storage=LocalFileStorage(request.app.state.settings.data_directories),
                project_id=project_id,
                document_id=document_id,
            )
        command = TranslationCommand(
            project_id=project_id,
            document_id=document_id,
            scope=payload.scope,
            section_ids=tuple(payload.section_ids or ()),
            page_ids=tuple(payload.page_ids or ()),
            segment_ids=tuple(payload.segment_ids or ()),
            model_id=payload.model_id,
            translation_style=(
                payload.translation_style.value
                if payload.translation_style is not None
                else readiness.project.translation_style
            ),
            batch_size=payload.batch_size,
            context_mode=payload.context_mode,
            retranslate_existing=payload.retranslate_existing,
            skip_locked_segments=payload.skip_locked_segments,
            run_semantic_validation=payload.run_semantic_validation,
            glossary_snapshot_id=snapshot.id,
            provider_type=payload.provider_type or "OLLAMA",
            ctranslate2_settings=(
                ctranslate2_settings_from_environment()
                if payload.provider_type == "CTRANSLATE2"
                else None
            ),
            cloud_model_name=payload.cloud_model_name,
            cloud_consent=payload.cloud_consent is True,
            cloud_consent_version=(
                "cloud_text_sharing_v1" if payload.cloud_consent is True else None
            ),
        )
        if payload.scope == "FULL_DOCUMENT" and _idempotent_job(session, idempotency_key) is None:
            active_job = _active_full_document_job(session, project_id, document_id)
            if active_job is not None:
                raise TransLokaError(
                    code="TRANSLATION_ALREADY_RUNNING",
                    message="A full-document translation is already running for the active document.",
                    status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                    details={"job_id": active_job.id},
                )
        result = JobDispatchService(session_factory, queue).dispatch(
            job_type=JobType.TRANSLATE_DOCUMENT,
            idempotency_key=idempotency_key,
            project_id=project_id,
            document_id=document_id,
            page_ids=tuple(payload.page_ids or ()),
            command_payload=command.to_payload(),
        )
    except JobIdempotencyConflictError as exc:
        raise TransLokaError(
            code="IDEMPOTENCY_CONFLICT",
            message="The idempotency key belongs to a different translation request.",
            status_code=409,
        ) from exc
    except JobQueueUnavailableError as exc:
        raise TransLokaError(
            code="QUEUE_UNAVAILABLE",
            message="The translation job could not be queued.",
            status_code=503,
            details={"job_id": exc.job_id},
        ) from exc
    except (InvalidJobDispatchError, GlossarySnapshotError, TranslationWorkerError) as exc:
        raise TransLokaError(
            code="VALIDATION_ERROR",
            message="The translation request contains invalid values.",
            status_code=422,
        ) from exc

    return TranslationJobResponse(
        data=TranslationJobData(job_id=result.job_id, status=result.status),
        meta=ResponseMeta(request_id=_request_id()),
    )


@router.get(
    "/{project_id}/translation/status",
    operation_id="get_translation_status",
    response_model=TranslationStatusResponse,
    responses=_ERROR_RESPONSES,
)
def get_translation_status(
    project_id: str,
    session: Annotated[Session, Depends(_get_session)],
) -> TranslationStatusResponse:
    project = _get_project(session, project_id)
    return _status_response(session, project)


@router.post(
    "/{project_id}/translation/cancel",
    operation_id="cancel_translation",
    response_model=TranslationStatusResponse,
    responses=_ERROR_RESPONSES,
)
def cancel_translation(
    project_id: str,
    payload: CancelTranslationRequest,
    request: Request,
    session: Annotated[Session, Depends(_get_session)],
) -> TranslationStatusResponse:
    project = _get_project(session, project_id)
    job = _latest_job(session, project_id)
    if job is None:
        _raise_job_not_found()
    try:
        settings = request.app.state.settings
        JobCancellationService(
            _session_factory(request), settings.data_directories.temporary
        ).request(job.id, reason=payload.reason)
    except CancellationJobNotFoundError as exc:
        _raise_job_not_found()
        raise AssertionError from exc
    except JobCannotBeCancelledError as exc:
        raise TransLokaError(
            code="JOB_STATE_INVALID",
            message="The translation job cannot be cancelled in its current state.",
            status_code=409,
        ) from exc
    return _status_response(session, project)


@router.post(
    "/{project_id}/translation/retry-failed",
    operation_id="retry_failed_translation",
    response_model=TranslationStatusResponse,
    responses={**_ERROR_RESPONSES, 503: _SERVICE_UNAVAILABLE_RESPONSE},
    status_code=status.HTTP_202_ACCEPTED,
)
def retry_failed_translation(
    project_id: str,
    payload: RetryTranslationRequest,
    request: Request,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=200)],
    session: Annotated[Session, Depends(_get_session)],
) -> TranslationStatusResponse:
    project = _get_project(session, project_id)
    job = _latest_job(session, project_id)
    if job is None:
        _raise_job_not_found()
    _require_worker_available(request)
    try:
        replacement_payload_json = (
            _reduced_translation_command_payload(job.payload_json)
            if payload.use_smaller_batch
            else None
        )
        retry = JobRetryService(_session_factory(request)).request(
            job.id,
            idempotency_key=idempotency_key,
            retry_failed_items_only=True,
            reason=("SMALLER_BATCH" if payload.use_smaller_batch else "USER_REQUESTED"),
            replacement_payload_json=replacement_payload_json,
        )
        if retry.created:
            try:
                _translation_queue(request).enqueue(job.id)
            except Exception as exc:
                _mark_retry_queue_failure(
                    _session_factory(request),
                    job.id,
                    retry.attempt_id,
                )
                raise TransLokaError(
                    code="QUEUE_UNAVAILABLE",
                    message="The translation job could not be queued.",
                    status_code=503,
                    details={"job_id": job.id},
                ) from exc
    except RetryJobNotFoundError as exc:
        _raise_job_not_found()
        raise AssertionError from exc
    except JobRetryLimitError as exc:
        raise TransLokaError(
            code="JOB_RETRY_LIMIT_REACHED",
            message="The translation job retry limit has been reached.",
            status_code=409,
        ) from exc
    except JobNotRetryableError as exc:
        raise TransLokaError(
            code="JOB_STATE_INVALID",
            message="The translation job does not allow retry.",
            status_code=409,
        ) from exc
    except RetryIdempotencyConflictError as exc:
        raise TransLokaError(
            code="IDEMPOTENCY_CONFLICT",
            message="The idempotency key belongs to a different retry request.",
            status_code=409,
        ) from exc
    except TranslationWorkerError as exc:
        raise TransLokaError(
            code="JOB_PAYLOAD_INVALID",
            message="The translation job cannot be retried because its saved settings are invalid.",
            status_code=409,
        ) from exc
    return _status_response(session, project)


def _mark_retry_queue_failure(
    session_factory: sessionmaker[Session],
    job_id: str,
    attempt_id: str,
) -> None:
    completed_at = _utc_now()
    with transaction_scope(session_factory) as failed_session:
        job = failed_session.get(ApplicationJob, job_id)
        attempt = failed_session.get(JobAttempt, attempt_id)
        if job is None or attempt is None:
            return
        job.status = JobStatus.FAILED.value
        job.current_stage = JobStatus.FAILED.value
        job.error_code = QUEUE_DISPATCH_FAILED
        job.error_message = "The translation job could not be queued."
        job.queued_at = None
        job.started_at = None
        job.completed_at = completed_at
        job.heartbeat_at = completed_at
        attempt.status = JobAttemptStatus.FAILED.value
        attempt.completed_at = completed_at
        attempt.error_code = QUEUE_DISPATCH_FAILED
        attempt.error_message = "The translation job could not be queued."


def _reduced_translation_command_payload(payload_json: str) -> str:
    command = TranslationCommand.from_payload_json(payload_json)
    reduced_batch_size = max(1, (command.batch_size + 1) // 2)
    return json.dumps(
        replace(command, batch_size=reduced_batch_size).to_payload(),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def _get_session(request: Request) -> Iterator[Session]:
    with _session_factory(request)() as session:
        yield session


def _session_factory(request: Request) -> sessionmaker[Session]:
    factory = getattr(request.app.state, "session_factory", None)
    if not callable(factory):
        raise RuntimeError("The translation database is not configured.")
    return cast(sessionmaker[Session], factory)


def _translation_queue(request: Request) -> Any:
    queue = getattr(request.app.state, "translation_queue", None)
    if queue is None:
        queue = getattr(request.app.state, "job_queue", None)
    if queue is None:
        raise TransLokaError(
            code="QUEUE_NOT_CONFIGURED",
            message="The translation queue is not configured.",
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
        )
    return queue


def _get_project(session: Session, project_id: str) -> Project:
    project = session.get(Project, project_id)
    if project is None:
        raise TransLokaError(
            code="PROJECT_NOT_FOUND",
            message="The requested project was not found.",
            status_code=404,
        )
    return project


async def _collect_readiness(
    request: Request,
    session: Session,
    project_id: str,
    requested_model_id: str | None = None,
    *,
    provider_type: TranslationProviderType = "OLLAMA",
    cloud_model_name: GroqModelName | None = None,
    cloud_consent: bool = False,
) -> _Readiness:
    project = _get_project(session, project_id)
    segment_count = _segment_count(session, project.active_document_id)
    unresolved_count = _unresolved_source_count(session, project.active_document_id)
    conflict_count = (
        session.scalar(
            select(func.count())
            .select_from(GlossaryConflict)
            .where(
                GlossaryConflict.project_id == project_id,
                GlossaryConflict.status == "UNRESOLVED",
            )
        )
        or 0
    )
    blockers: list[TranslationBlockingIssue] = []
    if provider_type == "OLLAMA":
        selected_model = cast(
            LocalModelRecord | None,
            session.scalar(
                select(LocalModelRecord)
                .where(LocalModelRecord.is_selected_translation == 1)
                .order_by(LocalModelRecord.id)
                .limit(1)
            ),
        )
        if selected_model is None or not selected_model.is_installed:
            blockers.append(
                TranslationBlockingIssue(
                    code="OLLAMA_MODEL_NOT_SELECTED",
                    message="Select an installed local translation model.",
                )
            )
        elif requested_model_id is not None and selected_model.id != requested_model_id:
            requested = cast(
                LocalModelRecord | None, session.get(LocalModelRecord, requested_model_id)
            )
            message = (
                "The requested translation model is not installed and selected."
                if requested is None or not requested.is_installed
                else "Select the requested translation model before starting."
            )
            blockers.append(
                TranslationBlockingIssue(
                    code="OLLAMA_MODEL_NOT_SELECTED",
                    message=message,
                )
            )
        provider = getattr(request.app.state, "ollama_provider", None)
        if provider is None:
            provider = OllamaTranslationProvider()
        unavailable_code = "OLLAMA_UNAVAILABLE"
        unavailable_message = "The local Ollama service is unavailable."
    elif provider_type == "CTRANSLATE2":
        try:
            ctranslate2_settings_from_environment()
        except CTranslate2ConfigurationError:
            blockers.append(
                TranslationBlockingIssue(
                    code="CTRANSLATE2_FALLBACK_INVALID",
                    message="Configure a valid local Ollama fallback model and loopback endpoint.",
                )
            )
        if not os.environ.get("TRANSLOKA_CT2_MODEL_DIR", "").strip():
            blockers.append(
                TranslationBlockingIssue(
                    code="CTRANSLATE2_DISABLED",
                    message="Configure the private CTranslate2 model directory to enable it.",
                )
            )
        if requested_model_id != CT2_MODEL_ID:
            blockers.append(
                TranslationBlockingIssue(
                    code="CTRANSLATE2_MODEL_NOT_ALLOWED",
                    message=f"Select the {CT2_MODEL_ID} local translation model.",
                )
            )
        if (project.source_language, project.target_language) != ("en", "id"):
            blockers.append(
                TranslationBlockingIssue(
                    code="CTRANSLATE2_LANGUAGE_UNSUPPORTED",
                    message="CTranslate2 supports only English to Indonesian translation.",
                )
            )
        if cloud_model_name is not None or cloud_consent:
            blockers.append(
                TranslationBlockingIssue(
                    code="CTRANSLATE2_PROVIDER_FIELDS_INVALID",
                    message="Cloud fields are invalid for the CTranslate2 provider.",
                )
            )
        provider = getattr(request.app.state, "ctranslate2_provider", None)
        if provider is None:
            provider = CTranslate2TranslationProvider()
        unavailable_code = "CTRANSLATE2_UNAVAILABLE"
        unavailable_message = "The private CTranslate2 model or runtime is unavailable."
    else:
        if not _cloud_translation_enabled():
            blockers.append(
                TranslationBlockingIssue(
                    code="CLOUD_TRANSLATION_DISABLED",
                    message="Cloud translation is disabled in this TransLoka process.",
                )
            )
        if not cloud_consent:
            blockers.append(
                TranslationBlockingIssue(
                    code="CLOUD_CONSENT_REQUIRED",
                    message="Explicit consent is required before sharing translation text.",
                )
            )
        if cloud_model_name not in GROQ_MODELS:
            blockers.append(
                TranslationBlockingIssue(
                    code="GROQ_MODEL_NOT_ALLOWED",
                    message="Select an allowlisted Groq translation model.",
                )
            )
        provider = getattr(request.app.state, "groq_provider", None)
        if provider is None:
            provider = GroqTranslationProvider(
                enabled=_cloud_translation_enabled(),
                cloud_consent=cloud_consent,
                model_name=cloud_model_name,
            )
        unavailable_code = "GROQ_UNAVAILABLE"
        unavailable_message = "Groq is unavailable or its credential is invalid."

    if not blockers or provider_type == "OLLAMA":
        try:
            health = await provider.health_check()
        except Exception:
            health = None
        if health is None or health.status is not ProviderHealthStatus.AVAILABLE:
            blockers.append(
                TranslationBlockingIssue(
                    code=unavailable_code,
                    message=unavailable_message,
                )
            )
    if not _worker_available(request):
        blockers.append(
            TranslationBlockingIssue(
                code="WORKER_UNAVAILABLE",
                message="Start the TransLoka worker and wait for it to become ready.",
            )
        )
    if unresolved_count:
        blockers.append(
            TranslationBlockingIssue(
                code="UNRESOLVED_SOURCE",
                message="Resolve all source segments before translation.",
            )
        )
    if conflict_count:
        blockers.append(
            TranslationBlockingIssue(
                code="GLOSSARY_CONFLICT",
                message="Resolve all blocking glossary conflicts before translation.",
            )
        )
    if segment_count == 0:
        blockers.append(
            TranslationBlockingIssue(
                code="NO_SEGMENTS",
                message="The active document has no translatable segments.",
            )
        )
    return _Readiness(
        project=project,
        segment_count=segment_count,
        estimated_batches=ceil(segment_count / 5) if segment_count else 0,
        blockers=blockers,
    )


def _cloud_translation_enabled() -> bool:
    return os.environ.get("TRANSLOKA_CLOUD_TRANSLATION_ENABLED", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _worker_available(request: Request) -> bool:
    heartbeat_reader = cast(
        _WorkerHeartbeatReader | None,
        getattr(request.app.state, "worker_heartbeat_store", None),
    )
    if heartbeat_reader is None:
        queue_owner = getattr(request.app.state, "translation_queue_owner", None)
        huey = getattr(queue_owner, "huey", None)
        if huey is None:
            return False
        heartbeat_reader = WorkerHeartbeatStore(huey)
    try:
        heartbeat = heartbeat_reader.read()
    except Exception:
        return False
    if heartbeat is None or heartbeat.status is not WorkerStatus.RUNNING:
        return False
    age_seconds = time.time() - heartbeat.recorded_at
    return 0.0 <= age_seconds <= WORKER_HEARTBEAT_MAX_AGE_SECONDS


def _require_worker_available(request: Request) -> None:
    if not _worker_available(request):
        _raise_worker_unavailable()


def _raise_worker_unavailable() -> Never:
    raise TransLokaError(
        code="WORKER_UNAVAILABLE",
        message="The TransLoka worker is unavailable. Start it and wait for readiness.",
        status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
    )


def _segment_count(session: Session, document_id: str | None) -> int:
    if document_id is None:
        return 0
    return int(
        session.scalar(
            select(func.count())
            .select_from(DocumentSegment)
            .join(DocumentBlock, DocumentBlock.id == DocumentSegment.block_id)
            .join(DocumentPage, DocumentPage.id == DocumentBlock.page_id)
            .where(
                DocumentPage.document_id == document_id,
                DocumentSegment.status.not_in(
                    (SegmentStatus.IGNORED.value, SegmentStatus.NOT_TRANSLATABLE.value)
                ),
            )
        )
        or 0
    )


def _unresolved_source_count(session: Session, document_id: str | None) -> int:
    if document_id is None:
        return 0
    return int(
        session.scalar(
            select(func.count())
            .select_from(DocumentSegment)
            .join(DocumentBlock, DocumentBlock.id == DocumentSegment.block_id)
            .join(DocumentPage, DocumentPage.id == DocumentBlock.page_id)
            .where(
                DocumentPage.document_id == document_id,
                DocumentSegment.status.not_in(
                    (
                        SegmentStatus.IGNORED.value,
                        SegmentStatus.NOT_TRANSLATABLE.value,
                    )
                ),
                (
                    (func.trim(DocumentSegment.resolved_source_text) == "")
                    | DocumentSegment.status.in_(
                        (
                            SegmentStatus.CREATED.value,
                            SegmentStatus.EXTRACTED.value,
                            SegmentStatus.OCR_REQUIRED.value,
                        )
                    )
                ),
            )
        )
        or 0
    )


def _latest_job(session: Session, project_id: str) -> ApplicationJob | None:
    return session.scalar(
        select(ApplicationJob)
        .where(
            ApplicationJob.project_id == project_id,
            ApplicationJob.job_type == JobType.TRANSLATE_DOCUMENT.value,
        )
        .order_by(
            case(
                (
                    ApplicationJob.status.in_(
                        (
                            JobStatus.RUNNING.value,
                            JobStatus.RETRYING.value,
                            JobStatus.CANCELLATION_REQUESTED.value,
                        )
                    ),
                    0,
                ),
                (ApplicationJob.status == JobStatus.QUEUED.value, 1),
                (
                    ApplicationJob.status.in_(
                        (
                            JobStatus.STALE.value,
                            JobStatus.FAILED.value,
                            JobStatus.PARTIALLY_COMPLETED.value,
                            JobStatus.COMPLETED_WITH_WARNINGS.value,
                        )
                    ),
                    2,
                ),
                (ApplicationJob.status == JobStatus.CANCELLED.value, 3),
                else_=4,
            ),
            ApplicationJob.created_at.desc(),
            ApplicationJob.id.desc(),
        )
        .limit(1)
    )


def _idempotent_job(session: Session, idempotency_key: str) -> ApplicationJob | None:
    return session.scalar(
        select(ApplicationJob).where(ApplicationJob.idempotency_key == idempotency_key).limit(1)
    )


def _active_full_document_job(
    session: Session,
    project_id: str,
    document_id: str,
) -> ApplicationJob | None:
    return session.scalar(
        select(ApplicationJob)
        .where(
            ApplicationJob.project_id == project_id,
            ApplicationJob.document_id == document_id,
            ApplicationJob.job_type == JobType.TRANSLATE_DOCUMENT.value,
            ApplicationJob.status.in_(
                (
                    JobStatus.QUEUED.value,
                    JobStatus.RUNNING.value,
                    JobStatus.RETRYING.value,
                    JobStatus.CANCELLATION_REQUESTED.value,
                )
            ),
            func.json_extract(ApplicationJob.payload_json, "$.scope") == "FULL_DOCUMENT",
        )
        .order_by(ApplicationJob.created_at.desc(), ApplicationJob.id.desc())
        .limit(1)
    )


def _status_response(session: Session, project: Project) -> TranslationStatusResponse:
    session.expire_all()
    has_translation = (
        (func.trim(func.coalesce(DocumentSegment.machine_translation, ""), " \t\r\n") != "")
        | (func.trim(func.coalesce(DocumentSegment.reviewed_translation, ""), " \t\r\n") != "")
        | (func.trim(func.coalesce(DocumentSegment.final_text, ""), " \t\r\n") != "")
    )
    # One aggregate snapshot keeps numerator and denominator consistent during writes.
    total_segments, completed_segments, failed_segments, review_required_segments = session.execute(
        select(
            func.count(),
            func.count().filter(
                DocumentSegment.status.in_(
                    ("MACHINE_TRANSLATED", "NEEDS_REVIEW", "USER_EDITED", "APPROVED", "LOCKED")
                ),
                has_translation,
            ),
            func.count().filter(DocumentSegment.status == SegmentStatus.TRANSLATION_FAILED.value),
            func.count().filter(DocumentSegment.status == SegmentStatus.NEEDS_REVIEW.value),
        )
        .select_from(DocumentSegment)
        .join(DocumentBlock, DocumentBlock.id == DocumentSegment.block_id)
        .join(DocumentPage, DocumentPage.id == DocumentBlock.page_id)
        .where(
            DocumentPage.document_id == project.active_document_id,
            DocumentSegment.status.not_in(("IGNORED", "NOT_TRANSLATABLE")),
        )
    ).one()
    # Display the active job, otherwise the newest terminal job for this document.
    # Retry-target selection deliberately has different historical priorities.
    job = session.scalar(
        select(ApplicationJob)
        .where(
            ApplicationJob.project_id == project.id,
            ApplicationJob.document_id == project.active_document_id,
            ApplicationJob.job_type == JobType.TRANSLATE_DOCUMENT.value,
        )
        .order_by(
            case(
                (ApplicationJob.status.in_(("RUNNING", "RETRYING", "CANCELLATION_REQUESTED")), 0),
                (ApplicationJob.status.in_(("CREATED", "QUEUED")), 1),
                else_=2,
            ),
            ApplicationJob.created_at.desc(),
            ApplicationJob.id.desc(),
        )
        .limit(1)
    )
    if job is None:
        job_status = "NOT_STARTED"
        active_job_id = None
    else:
        job_status = _translation_status(job.status)
        active_job_id = job.id
    progress = completed_segments / total_segments if total_segments else 0.0
    current_batch, total_batches = _persisted_batch_progress(job)
    unattempted_segments, provider_error_code, retry_after_seconds = _persisted_provider_failure(
        job
    )
    return TranslationStatusResponse(
        data=TranslationStatusData(
            status=job_status,
            total_segments=total_segments,
            completed_segments=completed_segments,
            failed_segments=failed_segments,
            review_required_segments=review_required_segments,
            progress=progress,
            active_job_id=active_job_id,
            current_batch=current_batch,
            total_batches=total_batches,
            unattempted_segments=unattempted_segments,
            provider_error_code=provider_error_code,
            retry_after_seconds=retry_after_seconds,
        ),
        meta=ResponseMeta(request_id=_request_id()),
    )


def _persisted_batch_progress(job: ApplicationJob | None) -> tuple[int, int]:
    if job is None or not job.result_json or job.status in {"CREATED", "QUEUED", "RETRYING"}:
        return 0, 0
    try:
        data = json.loads(job.result_json)
    except (TypeError, ValueError):
        return 0, 0
    if not isinstance(data, dict):
        return 0, 0
    current, total = data.get("current_batch"), data.get("total_batches")
    if type(current) is int and type(total) is int and 0 <= current <= total:
        return current, total
    return 0, 0


def _persisted_provider_failure(
    job: ApplicationJob | None,
) -> tuple[int, str | None, float | None]:
    if job is None or not job.result_json:
        return 0, None, None
    try:
        data = json.loads(job.result_json)
    except (TypeError, ValueError):
        return 0, None, None
    if not isinstance(data, dict):
        return 0, None, None
    identifiers = data.get("unattempted_segment_ids")
    count = len(identifiers) if isinstance(identifiers, list) else 0
    code = data.get("provider_error_code")
    if not isinstance(code, str):
        code = None
    retry_after = data.get("retry_after_seconds")
    if isinstance(retry_after, bool) or not isinstance(retry_after, (int, float)):
        retry_after = None
    return count, code, float(retry_after) if retry_after is not None else None


def _translation_status(value: str) -> str:
    return {
        JobStatus.CREATED.value: "QUEUED",
        JobStatus.QUEUED.value: "QUEUED",
        JobStatus.RUNNING.value: "TRANSLATING",
        JobStatus.RETRYING.value: "TRANSLATING",
        JobStatus.COMPLETED.value: "COMPLETED",
        JobStatus.COMPLETED_WITH_WARNINGS.value: "COMPLETED_WITH_WARNINGS",
        JobStatus.PARTIALLY_COMPLETED.value: "PARTIALLY_COMPLETED",
        JobStatus.FAILED.value: "FAILED",
        JobStatus.CANCELLATION_REQUESTED.value: "CANCELLING",
        JobStatus.CANCELLED.value: "CANCELLED",
        JobStatus.STALE.value: "FAILED",
    }.get(value, "UNKNOWN")


def _request_id() -> str:
    request_id = get_request_id()
    if request_id is None:
        raise RuntimeError("The request identifier is unavailable.")
    return request_id


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _raise_job_not_found() -> Never:
    raise TransLokaError(
        code="TRANSLATION_JOB_NOT_FOUND",
        message="The project has no translation job.",
        status_code=404,
    )
