import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any, Literal, cast
from uuid import uuid4

from fastapi import APIRouter, Header, Request, status
from fastapi import Path as PathParameter
from pydantic import BaseModel, ConfigDict
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker
from transloka_api.exception_handlers import TransLokaError
from transloka_api.schemas import ErrorResponse
from transloka_core.backup.manifest import BackupType
from transloka_core.backup.restore import (
    RestoreBusyError,
    RestoreConfirmationError,
    RestoreError,
    RestoreResult,
    RestoreRollbackError,
    RestoreValidationError,
    RestoreWorkflow,
)
from transloka_core.database import transaction_scope
from transloka_core.database.models.backups import Backup, BackupStatus
from transloka_core.database.models.files import FileRole, FileStatus, StoredFile
from transloka_core.database.models.jobs import ApplicationJob, JobStatus, JobType

_ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    404: {"description": "The backup was not found.", "model": ErrorResponse},
    409: {
        "description": "The restore conflicts with existing state or maintenance.",
        "model": ErrorResponse,
    },
    422: {"description": "The restore request or archive is invalid.", "model": ErrorResponse},
    500: {"description": "The restore could not be completed safely.", "model": ErrorResponse},
    503: {"description": "The application is in maintenance mode.", "model": ErrorResponse},
}
_BACKUP_ID_PATTERN = r"^bkp_[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$"
_RESTORE_QUEUE_NAME = "transloka-api"

router = APIRouter(prefix="/api/v1/backups", tags=["Backups"])


class RestoreRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    confirmation: Literal["RESTORE"]
    create_pre_restore_backup: Literal[True] = True
    restore_files: bool = True


class RestoreData(BaseModel):
    job_id: str
    backup_id: str
    status: Literal["COMPLETED"] = "COMPLETED"
    backup_type: BackupType
    pre_restore_backup_id: str


class RestoreResponse(BaseModel):
    data: RestoreData


@router.post(
    "/{backup_id}/restore",
    operation_id="restore_backup",
    response_model=RestoreResponse,
    responses=_ERROR_RESPONSES,
    status_code=status.HTTP_202_ACCEPTED,
)
def restore_backup(
    payload: RestoreRequest,
    request: Request,
    backup_id: Annotated[str, PathParameter(pattern=_BACKUP_ID_PATTERN)],
    idempotency_key: Annotated[
        str,
        Header(alias="Idempotency-Key", min_length=1, max_length=200),
    ],
) -> RestoreResponse:
    workflow = _restore_workflow(request)
    payload_json = _restore_payload_json(backup_id, payload)
    existing = _existing_restore_response(request, idempotency_key, payload_json)
    if existing is not None:
        return existing
    storage_key = _backup_storage_key(request, backup_id)

    job_id = f"job_{uuid4()}"
    pre_restore_backup_id = f"bkp_{uuid4()}"
    pre_restore_file_id = f"fil_{uuid4()}"
    started_at = _utc_now()
    response_data: RestoreData | None = None

    def persist_completion(result: RestoreResult) -> None:
        nonlocal response_data
        response_data = RestoreData(
            job_id=job_id,
            backup_id=backup_id,
            backup_type=result.backup_type,
            pre_restore_backup_id=pre_restore_backup_id,
        )
        _persist_completion(
            request,
            result=result,
            response_data=response_data,
            payload_json=payload_json,
            idempotency_key=idempotency_key,
            started_at=started_at,
            pre_restore_backup_id=pre_restore_backup_id,
            pre_restore_file_id=pre_restore_file_id,
        )

    try:
        workflow.restore(
            storage_key,
            confirmation=payload.confirmation,
            restore_files=payload.restore_files,
            completion=persist_completion,
        )
    except RestoreConfirmationError as exc:
        raise TransLokaError(
            code="RESTORE_CONFIRMATION_REQUIRED",
            message="The exact RESTORE confirmation is required.",
            status_code=422,
        ) from exc
    except RestoreBusyError as exc:
        raise TransLokaError(
            code="RESTORE_MAINTENANCE_ACTIVE",
            message="Another restore or maintenance operation is active.",
            status_code=409,
        ) from exc
    except RestoreValidationError as exc:
        raise TransLokaError(
            code="RESTORE_ARCHIVE_INVALID",
            message="The restore archive is invalid or not restorable.",
            status_code=422,
        ) from exc
    except RestoreRollbackError as exc:
        raise TransLokaError(
            code="RESTORE_ROLLBACK_FAILED",
            message="The restore failed and the previous state could not be restored.",
            status_code=500,
        ) from exc
    except RestoreError as exc:
        raise TransLokaError(
            code="RESTORE_FAILED",
            message="The restore could not be completed safely.",
            status_code=500,
        ) from exc

    if response_data is None:
        raise RuntimeError("The restore completion result was not persisted.")
    return RestoreResponse(data=response_data)


def _restore_workflow(request: Request) -> RestoreWorkflow:
    try:
        workflow = request.app.state.restore_workflow
    except AttributeError as exc:
        raise RuntimeError("The restore workflow is not configured.") from exc
    if not isinstance(workflow, RestoreWorkflow):
        raise RuntimeError("The restore workflow is not configured.")
    return workflow


def _session_factory(request: Request) -> sessionmaker[Session]:
    try:
        factory = request.app.state.session_factory
    except AttributeError as exc:
        raise RuntimeError("The application database is not configured.") from exc
    if not callable(factory):
        raise RuntimeError("The application database is not configured.")
    return cast(sessionmaker[Session], factory)


def _backup_storage_key(request: Request, backup_id: str) -> str:
    with _session_factory(request)() as session:
        row = session.execute(
            select(Backup, StoredFile)
            .join(StoredFile, Backup.file_id == StoredFile.id)
            .where(Backup.id == backup_id)
        ).one_or_none()
    if row is None:
        raise TransLokaError(
            code="BACKUP_NOT_FOUND",
            message="The requested backup was not found.",
            status_code=404,
        )
    backup, stored_file = row
    if backup.status != BackupStatus.COMPLETED.value or stored_file.status not in {
        FileStatus.AVAILABLE.value,
        FileStatus.VALIDATED.value,
    }:
        raise TransLokaError(
            code="BACKUP_STATE_INVALID",
            message="The backup is not ready to be restored.",
            status_code=409,
        )
    return cast(str, stored_file.storage_key)


def _existing_restore_response(
    request: Request,
    idempotency_key: str,
    payload_json: str,
) -> RestoreResponse | None:
    with _session_factory(request)() as session:
        row = session.scalar(
            select(ApplicationJob).where(ApplicationJob.idempotency_key == idempotency_key)
        )
    if row is None:
        return None
    if row.job_type != JobType.RESTORE_DATABASE.value or row.payload_json != payload_json:
        _raise_idempotency_conflict()
    if row.status != JobStatus.COMPLETED.value or row.result_json is None:
        raise TransLokaError(
            code="RESTORE_ALREADY_IN_PROGRESS",
            message="The restore request is already in progress.",
            status_code=409,
        )
    try:
        return RestoreResponse(data=RestoreData.model_validate_json(row.result_json))
    except ValueError as exc:
        raise RuntimeError("The stored restore result is invalid.") from exc


def _persist_completion(
    request: Request,
    *,
    result: RestoreResult,
    response_data: RestoreData,
    payload_json: str,
    idempotency_key: str,
    started_at: str,
    pre_restore_backup_id: str,
    pre_restore_file_id: str,
) -> None:
    completed_at = _utc_now()
    artifact = result.pre_restore_backup
    with transaction_scope(_session_factory(request)) as session:
        session.add(
            StoredFile(
                id=pre_restore_file_id,
                project_id=None,
                document_id=None,
                file_role=FileRole.BACKUP.value,
                storage_key=artifact.storage_key,
                original_filename=None,
                safe_filename=Path(artifact.storage_key).name,
                mime_type="application/zip",
                size_bytes=artifact.size_bytes,
                checksum_sha256=artifact.checksum_sha256,
                is_immutable=1,
                status=FileStatus.VALIDATED.value,
                metadata_json='{"purpose":"PRE_RESTORE"}',
                created_at=artifact.created_at,
                deleted_at=None,
            )
        )
        session.flush()
        session.add(
            Backup(
                id=pre_restore_backup_id,
                backup_type=artifact.backup_type.value,
                file_id=pre_restore_file_id,
                application_version=artifact.manifest.application_version,
                database_schema_version=artifact.manifest.database_schema_version,
                status=BackupStatus.COMPLETED.value,
                size_bytes=artifact.size_bytes,
                checksum_sha256=artifact.checksum_sha256,
                included_content_json=json.dumps(
                    list(artifact.included_content),
                    ensure_ascii=False,
                    separators=(",", ":"),
                ),
                created_at=artifact.created_at,
                completed_at=completed_at,
                error_code=None,
            )
        )
        session.add(
            ApplicationJob(
                id=response_data.job_id,
                project_id=None,
                document_id=None,
                parent_job_id=None,
                job_type=JobType.RESTORE_DATABASE.value,
                queue_name=_RESTORE_QUEUE_NAME,
                status=JobStatus.COMPLETED.value,
                progress=1.0,
                current_stage=JobStatus.COMPLETED.value,
                idempotency_key=idempotency_key,
                payload_json=payload_json,
                result_json=response_data.model_dump_json(),
                retry_count=0,
                max_retries=0,
                error_code=None,
                error_message=None,
                created_at=started_at,
                queued_at=started_at,
                started_at=started_at,
                completed_at=completed_at,
                cancelled_at=None,
                heartbeat_at=None,
            )
        )


def _restore_payload_json(backup_id: str, payload: RestoreRequest) -> str:
    return json.dumps(
        {
            "backup_id": backup_id,
            "create_pre_restore_backup": payload.create_pre_restore_backup,
            "restore_files": payload.restore_files,
        },
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    )


def _raise_idempotency_conflict() -> None:
    raise TransLokaError(
        code="IDEMPOTENCY_CONFLICT",
        message="The idempotency key belongs to a different restore request.",
        status_code=409,
    )


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


__all__ = ["RestoreData", "RestoreRequest", "RestoreResponse", "router"]
