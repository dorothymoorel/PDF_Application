from typing import Any, Literal

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, Field
from transloka_api.exception_handlers import TransLokaError
from transloka_api.schemas import ErrorResponse
from transloka_core.backup.manifest import BackupType
from transloka_core.backup.restore import (
    RestoreBusyError,
    RestoreConfirmationError,
    RestoreError,
    RestoreRollbackError,
    RestoreValidationError,
    RestoreWorkflow,
)

_ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    409: {
        "description": "Another restore or maintenance operation is active.",
        "model": ErrorResponse,
    },
    422: {"description": "The restore request or archive is invalid.", "model": ErrorResponse},
    500: {"description": "The restore could not be completed safely.", "model": ErrorResponse},
}

router = APIRouter(prefix="/api/v1/backups", tags=["Backups"])


class RestoreRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    storage_key: str = Field(min_length=1, max_length=1024)
    confirmation: Literal["RESTORE"]


class RestoreData(BaseModel):
    archive_storage_key: str
    backup_type: BackupType
    restored_content: list[str]
    pre_restore_storage_key: str


class RestoreResponse(BaseModel):
    data: RestoreData


@router.post(
    "/restore",
    operation_id="restore_backup",
    response_model=RestoreResponse,
    responses=_ERROR_RESPONSES,
)
def restore_backup(payload: RestoreRequest, request: Request) -> RestoreResponse:
    try:
        workflow = request.app.state.restore_workflow
    except AttributeError as exc:
        raise RuntimeError("The restore workflow is not configured.") from exc
    if not isinstance(workflow, RestoreWorkflow):
        raise RuntimeError("The restore workflow is not configured.")

    try:
        result = workflow.restore(payload.storage_key, confirmation=payload.confirmation)
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

    return RestoreResponse(
        data=RestoreData(
            archive_storage_key=payload.storage_key,
            backup_type=result.backup_type,
            restored_content=list(result.restored_content),
            pre_restore_storage_key=result.pre_restore_backup.storage_key,
        )
    )


__all__ = ["RestoreData", "RestoreRequest", "RestoreResponse", "router"]
