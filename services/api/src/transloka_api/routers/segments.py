import hashlib
import json
from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Annotated, Any, Literal, Never, cast
from uuid import uuid4

from fastapi import APIRouter, Depends, Header, Request, Response, status
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.orm import Session, sessionmaker
from transloka_api.exception_handlers import TransLokaError
from transloka_api.middleware import get_request_id
from transloka_api.routers.pages import _segment_response
from transloka_api.schemas import ErrorResponse
from transloka_api.schemas.pages import PageEditorSegmentResponse
from transloka_api.schemas.projects import ResponseMeta
from transloka_api.services.segments import (
    EditSegmentTranslation,
    EmptySegmentTranslationError,
    LockSegment,
    SegmentLockedError,
    SegmentLockStateError,
    SegmentNotFoundError,
    SegmentRevisionConflictError,
    SegmentService,
    SegmentServiceError,
    invalidate_reconstruction_cache,
)
from transloka_core.database import transaction_scope
from transloka_core.database.models.document_ir import (
    DocumentBlock,
    DocumentSegment,
    ReviewStatus,
    SegmentStatus,
)
from transloka_core.database.models.documents import Document
from transloka_core.database.models.jobs import ApplicationJob, JobStatus, JobType
from transloka_core.database.models.pages import DocumentPage
from transloka_core.database.models.revisions import SegmentRevision, SegmentRevisionType
from transloka_core.database.models.translation import SegmentTranslation
from transloka_core.jobs.dispatch import (
    JobIdempotencyConflictError,
    JobQueueUnavailableError,
)

_ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    403: {
        "description": "The request was rejected by the local security policy.",
        "model": ErrorResponse,
    },
    404: {"description": "The segment was not found.", "model": ErrorResponse},
    409: {"description": "The segment revision is stale.", "model": ErrorResponse},
    422: {"description": "The request contains invalid values.", "model": ErrorResponse},
    423: {"description": "The segment is locked.", "model": ErrorResponse},
    500: {"description": "An unexpected server error was normalized.", "model": ErrorResponse},
}

router = APIRouter(prefix="/api/v1/segments", tags=["Segments"])


class EditSegmentTranslationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    reviewed_translation: str = Field(min_length=1)
    expected_revision: int = Field(ge=0)
    reason: str | None = Field(default=None, max_length=500)


class ApproveSegmentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    expected_revision: int = Field(ge=0)
    lock_after_approval: bool = False


class UnapproveSegmentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    expected_revision: int = Field(ge=0)
    reason: str | None = Field(default=None, max_length=500)


BulkAction = Literal["approve", "lock", "retranslate"]
BulkResultStatus = Literal["FAILED", "QUEUED", "SUCCEEDED"]


class BulkSegmentActionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    action: BulkAction
    selected_ids: list[str] | None = Field(default=None, min_length=1, max_length=100)
    segment_ids: list[str] | None = Field(default=None, min_length=1, max_length=100)
    expected_revisions: dict[str, int] = Field(default_factory=dict)

    @field_validator("action", mode="before")
    @classmethod
    def normalize_action(cls, value: object) -> str:
        if not isinstance(value, str):
            raise ValueError("The bulk action is invalid.")
        normalized = value.strip().lower()
        if normalized not in {"approve", "lock", "retranslate"}:
            raise ValueError("The bulk action is invalid.")
        return normalized


class BulkSegmentActionError(BaseModel):
    code: str
    message: str
    details: dict[str, Any] = Field(default_factory=dict)


class BulkSegmentActionResult(BaseModel):
    segment_id: str
    status: BulkResultStatus
    current_revision: int | None = None
    error: BulkSegmentActionError | None = None


class BulkSegmentActionData(BaseModel):
    action: BulkAction
    results: list[BulkSegmentActionResult]
    succeeded: int = Field(ge=0)
    failed: int = Field(ge=0)
    queued: int = Field(ge=0)
    job_id: str | None = None


class BulkSegmentActionResponse(BaseModel):
    data: BulkSegmentActionData
    meta: ResponseMeta


class SegmentDataResponse(BaseModel):
    data: PageEditorSegmentResponse
    meta: ResponseMeta


def get_segment_session(request: Request) -> Iterator[Session]:
    try:
        factory = request.app.state.session_factory
    except AttributeError as exc:
        raise RuntimeError("The segment database is not configured.") from exc
    if not callable(factory):
        raise RuntimeError("The segment database is not configured.")
    with transaction_scope(cast(sessionmaker[Session], factory)) as session:
        yield session


SegmentSession = Annotated[Session, Depends(get_segment_session)]


@router.patch(
    "/{segment_id}/translation",
    operation_id="edit_segment_translation",
    response_model=SegmentDataResponse,
    responses=_ERROR_RESPONSES,
)
def edit_segment_translation(
    segment_id: str,
    payload: EditSegmentTranslationRequest,
    session: SegmentSession,
) -> SegmentDataResponse:
    try:
        row = SegmentService(session).edit_translation(
            segment_id,
            EditSegmentTranslation(
                reviewed_translation=payload.reviewed_translation,
                expected_revision=payload.expected_revision,
                reason=payload.reason,
            ),
        )
    except SegmentServiceError as exc:
        _raise_segment_error(exc)
    return SegmentDataResponse(
        data=_segment_response(row),
        meta=ResponseMeta(request_id=_request_id()),
    )


@router.post(
    "/{segment_id}/approve",
    operation_id="approve_segment",
    response_model=SegmentDataResponse,
    responses=_ERROR_RESPONSES,
)
def approve_segment(
    segment_id: str,
    payload: ApproveSegmentRequest,
    session: SegmentSession,
) -> SegmentDataResponse:
    try:
        row = _change_review_state(
            session,
            segment_id,
            expected_revision=payload.expected_revision,
            revision_type=SegmentRevisionType.APPROVE,
            lock_after_approval=payload.lock_after_approval,
        )
    except SegmentServiceError as exc:
        _raise_segment_error(exc)
    return SegmentDataResponse(
        data=_segment_response(row),
        meta=ResponseMeta(request_id=_request_id()),
    )


@router.post(
    "/{segment_id}/unapprove",
    operation_id="unapprove_segment",
    response_model=SegmentDataResponse,
    responses=_ERROR_RESPONSES,
)
def unapprove_segment(
    segment_id: str,
    payload: UnapproveSegmentRequest,
    session: SegmentSession,
) -> SegmentDataResponse:
    try:
        row = _change_review_state(
            session,
            segment_id,
            expected_revision=payload.expected_revision,
            revision_type=SegmentRevisionType.UNAPPROVE,
            reason=payload.reason,
        )
    except SegmentServiceError as exc:
        _raise_segment_error(exc)
    return SegmentDataResponse(
        data=_segment_response(row),
        meta=ResponseMeta(request_id=_request_id()),
    )


@router.post(
    "/bulk",
    operation_id="bulk_segment_action",
    response_model=BulkSegmentActionResponse,
    responses=_ERROR_RESPONSES,
)
def bulk_segment_action(
    payload: BulkSegmentActionRequest,
    request: Request,
    response: Response,
    session: SegmentSession,
    idempotency_key: Annotated[str | None, Header(alias="Idempotency-Key")] = None,
) -> BulkSegmentActionResponse:
    selected_ids = _selected_segment_ids(payload)
    expected_revisions = payload.expected_revisions

    if payload.action == "retranslate":
        results, job_id = _bulk_retranslate(
            request,
            selected_ids,
            expected_revisions,
            idempotency_key,
            session,
        )
        if job_id is not None:
            response.status_code = status.HTTP_202_ACCEPTED
    else:
        results = [
            _bulk_mutate_segment(
                session,
                segment_id,
                expected_revisions.get(segment_id),
                payload.action,
            )
            for segment_id in selected_ids
        ]
        job_id = None

    return BulkSegmentActionResponse(
        data=BulkSegmentActionData(
            action=payload.action,
            results=results,
            succeeded=sum(result.status == "SUCCEEDED" for result in results),
            failed=sum(result.status == "FAILED" for result in results),
            queued=sum(result.status == "QUEUED" for result in results),
            job_id=job_id,
        ),
        meta=ResponseMeta(request_id=_request_id()),
    )


def _selected_segment_ids(payload: BulkSegmentActionRequest) -> list[str]:
    if payload.selected_ids is not None and payload.segment_ids is not None:
        raise TransLokaError(
            code="VALIDATION_ERROR",
            message="Provide selected_ids or segment_ids, not both.",
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )
    selected_ids = payload.selected_ids or payload.segment_ids
    if not selected_ids:
        raise TransLokaError(
            code="VALIDATION_ERROR",
            message="At least one segment must be selected.",
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )
    if len(set(selected_ids)) != len(selected_ids):
        raise TransLokaError(
            code="VALIDATION_ERROR",
            message="A segment may only be selected once.",
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )
    return selected_ids


def _bulk_mutate_segment(
    session: Session,
    segment_id: str,
    expected_revision: int | None,
    action: Literal["approve", "lock"],
) -> BulkSegmentActionResult:
    with session.begin_nested():
        row = session.get(DocumentSegment, segment_id)
        if row is None:
            return _bulk_failure(segment_id, "SEGMENT_NOT_FOUND", "The segment was not found.")
        if expected_revision is not None and row.current_revision != expected_revision:
            return _bulk_failure(
                segment_id,
                "REVISION_CONFLICT",
                "The segment was changed after it was loaded.",
                current_revision=row.current_revision,
                details={
                    "expected_revision": expected_revision,
                    "current_revision": row.current_revision,
                },
            )

        try:
            if action == "approve":
                updated = _change_review_state(
                    session,
                    segment_id,
                    expected_revision=(
                        row.current_revision if expected_revision is None else expected_revision
                    ),
                    revision_type=SegmentRevisionType.APPROVE,
                )
            else:
                updated = SegmentService(session).lock(
                    segment_id,
                    LockSegment(
                        expected_revision=(
                            row.current_revision if expected_revision is None else expected_revision
                        )
                    ),
                )
        except SegmentServiceError as exc:
            return _bulk_failure_from_exception(segment_id, exc)

        return BulkSegmentActionResult(
            segment_id=segment_id,
            status="SUCCEEDED",
            current_revision=updated.current_revision,
        )


def _bulk_failure(
    segment_id: str,
    code: str,
    message: str,
    *,
    current_revision: int | None = None,
    details: dict[str, Any] | None = None,
) -> BulkSegmentActionResult:
    return BulkSegmentActionResult(
        segment_id=segment_id,
        status="FAILED",
        current_revision=current_revision,
        error=BulkSegmentActionError(code=code, message=message, details=details or {}),
    )


def _bulk_failure_from_exception(
    segment_id: str,
    exc: SegmentServiceError,
) -> BulkSegmentActionResult:
    if isinstance(exc, SegmentNotFoundError):
        return _bulk_failure(segment_id, "SEGMENT_NOT_FOUND", "The segment was not found.")
    if isinstance(exc, SegmentLockedError):
        return _bulk_failure(
            segment_id,
            "SEGMENT_LOCKED",
            "The segment is locked and cannot be changed.",
        )
    if isinstance(exc, SegmentRevisionConflictError):
        return _bulk_failure(
            segment_id,
            "REVISION_CONFLICT",
            "The segment was changed after it was loaded.",
            current_revision=exc.current_revision,
            details={
                "expected_revision": exc.expected_revision,
                "current_revision": exc.current_revision,
            },
        )
    if isinstance(exc, SegmentReviewStateError | SegmentLockStateError):
        return _bulk_failure(segment_id, "SEGMENT_STATE_INVALID", str(exc))
    if isinstance(exc, EmptySegmentTranslationError):
        return _bulk_failure(segment_id, "VALIDATION_ERROR", str(exc))
    return _bulk_failure(segment_id, "VALIDATION_ERROR", "The segment action is invalid.")


def _bulk_retranslate(
    request: Request,
    selected_ids: list[str],
    expected_revisions: dict[str, int],
    idempotency_key: str | None,
    session: Session,
) -> tuple[list[BulkSegmentActionResult], str | None]:
    rows = list(
        session.scalars(select(DocumentSegment).where(DocumentSegment.id.in_(tuple(selected_ids))))
    )
    by_id = {row.id: row for row in rows}
    results: list[BulkSegmentActionResult] = []
    eligible: list[DocumentSegment] = []
    for segment_id in selected_ids:
        row = by_id.get(segment_id)
        if row is None:
            results.append(
                _bulk_failure(segment_id, "SEGMENT_NOT_FOUND", "The segment was not found.")
            )
            continue
        expected = expected_revisions.get(segment_id)
        if expected is not None and row.current_revision != expected:
            results.append(
                _bulk_failure(
                    segment_id,
                    "REVISION_CONFLICT",
                    "The segment was changed after it was loaded.",
                    current_revision=row.current_revision,
                    details={
                        "expected_revision": expected,
                        "current_revision": row.current_revision,
                    },
                )
            )
            continue
        if row.is_locked:
            results.append(
                _bulk_failure(
                    segment_id,
                    "SEGMENT_LOCKED",
                    "The segment is locked and cannot be retranslated.",
                    current_revision=row.current_revision,
                )
            )
            continue
        eligible.append(row)

    if not eligible:
        return results, None

    context = _retranslation_context(session, eligible)
    if context is None:
        for row in eligible:
            results.append(
                _bulk_failure(
                    row.id,
                    "SEGMENT_CONTEXT_INVALID",
                    "The selected segments do not share one active document.",
                    current_revision=row.current_revision,
                )
            )
        return results, None

    job_key = idempotency_key or _default_bulk_idempotency_key(selected_ids, expected_revisions)
    _validate_bulk_idempotency_key(job_key)
    try:
        job_id = _dispatch_selected_retranslation(
            request,
            context,
            tuple(row.id for row in eligible),
            job_key,
        )
    except JobIdempotencyConflictError as exc:
        raise TransLokaError(
            code="IDEMPOTENCY_CONFLICT",
            message="The idempotency key belongs to a different bulk action.",
            status_code=status.HTTP_409_CONFLICT,
        ) from exc
    except JobQueueUnavailableError as exc:
        for row in eligible:
            results.append(
                _bulk_failure(
                    row.id,
                    "QUEUE_UNAVAILABLE",
                    "The retranslation job could not be queued.",
                    current_revision=row.current_revision,
                    details={"job_id": exc.job_id},
                )
            )
        return results, exc.job_id

    results.extend(
        BulkSegmentActionResult(
            segment_id=row.id,
            status="QUEUED",
            current_revision=row.current_revision,
        )
        for row in eligible
    )
    return results, job_id


def _retranslation_context(
    session: Session,
    rows: list[DocumentSegment],
) -> tuple[str, str, tuple[str, ...]] | None:
    context_rows = list(
        session.execute(
            select(DocumentSegment.id, Document.project_id, Document.id, DocumentPage.id)
            .join(DocumentBlock, DocumentBlock.id == DocumentSegment.block_id)
            .join(DocumentPage, DocumentPage.id == DocumentBlock.page_id)
            .join(Document, Document.id == DocumentPage.document_id)
            .where(DocumentSegment.id.in_(tuple(row.id for row in rows)))
        )
    )
    contexts = {(project_id, document_id) for _, project_id, document_id, _ in context_rows}
    if len(contexts) != 1 or not context_rows:
        return None
    project_id, document_id = next(iter(contexts))
    page_ids = tuple(sorted({page_id for _, _, _, page_id in context_rows}))
    return project_id, document_id, page_ids


def _default_bulk_idempotency_key(
    selected_ids: list[str], expected_revisions: dict[str, int]
) -> str:
    canonical = json.dumps(
        {"expected_revisions": expected_revisions, "selected_ids": selected_ids},
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    return f"bulk-retranslate-{hashlib.sha256(canonical).hexdigest()[:32]}"


def _validate_bulk_idempotency_key(value: str) -> None:
    if not value or len(value) > 200 or value != value.strip() or not value.isprintable():
        raise TransLokaError(
            code="VALIDATION_ERROR",
            message="The idempotency key is invalid.",
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        )


def _dispatch_selected_retranslation(
    request: Request,
    context: tuple[str, str, tuple[str, ...]],
    segment_ids: tuple[str, ...],
    idempotency_key: str,
) -> str:
    project_id, document_id, page_ids = context
    factory = cast(sessionmaker[Session], request.app.state.session_factory)
    queue = getattr(request.app.state, "translation_queue", None)
    if queue is None:
        queue = getattr(request.app.state, "job_queue", None)
    if queue is None:
        queue = _FallbackTranslationQueue()
    queue_name = getattr(queue, "name", "translation")
    payload_json = json.dumps(
        {
            "document_id": document_id,
            "page_ids": list(page_ids),
            "project_id": project_id,
            "retranslate_existing": True,
            "scope": "SELECTED_SEGMENTS",
            "segment_ids": list(segment_ids),
        },
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )
    with factory() as lookup_session:
        existing = lookup_session.scalar(
            select(ApplicationJob).where(ApplicationJob.idempotency_key == idempotency_key)
        )
        if existing is not None:
            if (
                existing.job_type != JobType.TRANSLATE_DOCUMENT.value
                or existing.project_id != project_id
                or existing.document_id != document_id
                or existing.queue_name != queue_name
                or existing.payload_json != payload_json
            ):
                raise JobIdempotencyConflictError(
                    "The idempotency key belongs to a different job request."
                )
            return existing.id

    job_id = f"job_{uuid4()}"
    with transaction_scope(factory) as create_session:
        create_session.add(
            ApplicationJob(
                id=job_id,
                project_id=project_id,
                document_id=document_id,
                parent_job_id=None,
                job_type=JobType.TRANSLATE_DOCUMENT.value,
                queue_name=queue_name,
                status=JobStatus.CREATED.value,
                progress=0.0,
                current_stage=None,
                idempotency_key=idempotency_key,
                payload_json=payload_json,
                result_json=None,
                retry_count=0,
                max_retries=3,
                error_code=None,
                error_message=None,
                created_at=_utc_now(),
                queued_at=None,
                started_at=None,
                completed_at=None,
                cancelled_at=None,
                heartbeat_at=None,
            )
        )

    try:
        queue.enqueue(job_id)
    except Exception as exc:
        with transaction_scope(factory) as failed_session:
            failed = failed_session.get(ApplicationJob, job_id)
            if failed is not None:
                failed.status = JobStatus.FAILED.value
                failed.error_code = "QUEUE_DISPATCH_FAILED"
                failed.error_message = "The job could not be queued."
                failed.completed_at = _utc_now()
        raise JobQueueUnavailableError(job_id) from exc

    with transaction_scope(factory) as queued_session:
        queued = queued_session.get(ApplicationJob, job_id)
        if queued is None:
            raise RuntimeError("The retranslation job disappeared before queueing.")
        queued.status = JobStatus.QUEUED.value
        queued.queued_at = _utc_now()
    return job_id


class _FallbackTranslationQueue:
    name = "translation"

    def enqueue(self, _job_id: str) -> None:
        return None


def _change_review_state(
    session: Session,
    segment_id: str,
    *,
    expected_revision: int,
    revision_type: SegmentRevisionType,
    lock_after_approval: bool = False,
    reason: str | None = None,
) -> DocumentSegment:
    row = session.get(DocumentSegment, segment_id)
    if row is None:
        raise SegmentNotFoundError("The segment was not found.")
    if row.is_locked:
        raise SegmentLockedError("The segment is locked.")
    if row.current_revision != expected_revision:
        raise SegmentRevisionConflictError(expected_revision, row.current_revision)

    if revision_type is SegmentRevisionType.APPROVE:
        if row.review_status == ReviewStatus.APPROVED.value:
            raise SegmentReviewStateError("The segment is already approved.")
        new_text = next(
            (
                value.strip()
                for value in (row.reviewed_translation, row.final_text, row.machine_translation)
                if value and value.strip()
            ),
            None,
        )
        if new_text is None:
            raise SegmentReviewStateError("A translated value is required before approval.")
        new_status = (
            SegmentStatus.LOCKED.value if lock_after_approval else SegmentStatus.APPROVED.value
        )
        new_review_status = ReviewStatus.APPROVED.value
        new_is_locked = 1 if lock_after_approval else 0
        reviewed_translation = new_text
    else:
        if row.review_status != ReviewStatus.APPROVED.value:
            raise SegmentReviewStateError("Only an approved segment can be unapproved.")
        new_text = row.final_text or row.reviewed_translation or row.machine_translation
        if not new_text or not new_text.strip():
            raise SegmentReviewStateError("The approved segment has no translatable value.")
        new_status = SegmentStatus.USER_EDITED.value
        new_review_status = ReviewStatus.EDITED.value
        new_is_locked = 0
        reviewed_translation = row.reviewed_translation or new_text

    next_revision = expected_revision + 1
    now = _utc_now()
    result = cast(
        CursorResult[Any],
        session.execute(
            update(DocumentSegment)
            .where(
                DocumentSegment.id == segment_id,
                DocumentSegment.current_revision == expected_revision,
                DocumentSegment.is_locked == 0,
            )
            .values(
                reviewed_translation=reviewed_translation,
                final_text=new_text.strip(),
                status=new_status,
                review_status=new_review_status,
                is_locked=new_is_locked,
                current_revision=next_revision,
                updated_at=now,
            )
        ),
    )
    if result.rowcount != 1:
        current = session.get(DocumentSegment, segment_id)
        if current is None:
            raise SegmentNotFoundError("The segment was not found.")
        if current.is_locked:
            raise SegmentLockedError("The segment is locked.")
        raise SegmentRevisionConflictError(expected_revision, current.current_revision)

    session.add(
        SegmentRevision(
            id=f"rev_{uuid4()}",
            segment_id=segment_id,
            revision_number=next_revision,
            revision_type=revision_type.value,
            previous_text=row.final_text,
            new_text=new_text.strip(),
            source_translation_id=_latest_translation_id(session, segment_id),
            reason=reason.strip() if reason else None,
            metadata_json=None,
            created_at=now,
        )
    )
    session.flush()
    invalidate_reconstruction_cache(segment_id)
    updated = session.get(DocumentSegment, segment_id)
    if updated is None:
        raise SegmentNotFoundError("The segment was not found after review update.")
    return updated


def _latest_translation_id(session: Session, segment_id: str) -> str | None:
    return session.scalar(
        select(SegmentTranslation.id)
        .where(SegmentTranslation.segment_id == segment_id)
        .order_by(SegmentTranslation.created_at.desc(), SegmentTranslation.id.desc())
        .limit(1)
    )


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


class SegmentReviewStateError(SegmentServiceError):
    pass


def _request_id() -> str:
    request_id = get_request_id()
    if request_id is None:
        raise RuntimeError("The request identifier is unavailable.")
    return request_id


def _raise_segment_error(exc: SegmentServiceError) -> Never:
    if isinstance(exc, SegmentNotFoundError):
        raise TransLokaError(
            code="SEGMENT_NOT_FOUND",
            message="The requested segment was not found.",
            status_code=status.HTTP_404_NOT_FOUND,
        ) from exc
    if isinstance(exc, SegmentLockedError):
        raise TransLokaError(
            code="SEGMENT_LOCKED",
            message="The segment is locked and cannot be edited.",
            status_code=status.HTTP_423_LOCKED,
        ) from exc
    if isinstance(exc, SegmentRevisionConflictError):
        raise TransLokaError(
            code="REVISION_CONFLICT",
            message="The segment was changed after it was loaded.",
            status_code=status.HTTP_409_CONFLICT,
            details={
                "expected_revision": exc.expected_revision,
                "current_revision": exc.current_revision,
            },
        ) from exc
    if isinstance(exc, EmptySegmentTranslationError):
        raise TransLokaError(
            code="VALIDATION_ERROR",
            message="The reviewed translation cannot be empty.",
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        ) from exc
    if isinstance(exc, SegmentReviewStateError):
        raise TransLokaError(
            code="SEGMENT_STATE_INVALID",
            message="The segment review state does not allow this operation.",
            status_code=status.HTTP_409_CONFLICT,
        ) from exc
    raise TransLokaError(
        code="VALIDATION_ERROR",
        message="The segment edit is invalid.",
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
    ) from exc
