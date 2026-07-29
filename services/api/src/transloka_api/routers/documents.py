from typing import Annotated, Any, Literal, Never, cast

from fastapi import APIRouter, Depends, File, Form, Header, Request, UploadFile, status
from pydantic import BaseModel
from transloka_api.config import Settings
from transloka_api.exception_handlers import TransLokaError
from transloka_api.middleware import get_request_id
from transloka_api.routers.projects import ProjectSession, _raise_project_error
from transloka_api.schemas import ErrorResponse
from transloka_api.schemas.projects import ResponseMeta
from transloka_api.services.imports import (
    EmptyUploadError,
    ImportService,
    InvalidUploadMetadataError,
    UploadInterruptedError,
    UploadStorageError,
    UploadTooLargeError,
)
from transloka_api.services.projects import ProjectService
from transloka_core.repositories.projects import ProjectRepositoryError, ProjectsRepository
from transloka_core.storage.local import LocalFileStorage

_ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    400: {"description": "The upload stream was interrupted.", "model": ErrorResponse},
    403: {
        "description": "The request was rejected by the local security policy.",
        "model": ErrorResponse,
    },
    404: {"description": "The project was not found.", "model": ErrorResponse},
    413: {"description": "The uploaded file is too large.", "model": ErrorResponse},
    415: {"description": "The request is not multipart.", "model": ErrorResponse},
    422: {"description": "The upload metadata or content is invalid.", "model": ErrorResponse},
    500: {"description": "An unexpected server error was normalized.", "model": ErrorResponse},
}

router = APIRouter(prefix="/api/v1/projects", tags=["Documents"])


class StagedUploadData(BaseModel):
    upload_id: str
    project_id: str
    status: Literal["STAGED"] = "STAGED"
    original_filename: str
    size_bytes: int
    set_as_active: bool


class StagedUploadResponse(BaseModel):
    data: StagedUploadData
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
    response_model=StagedUploadResponse,
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
) -> StagedUploadResponse:
    try:
        ProjectService(ProjectsRepository(session)).get(project_id)
    except ProjectRepositoryError as exc:
        _raise_project_error(exc)

    settings = cast(Settings, request.app.state.settings)
    service = ImportService(
        LocalFileStorage(settings.data_directories),
        settings.max_upload_bytes,
    )
    try:
        staged = service.stage_upload(
            project_id=project_id,
            original_filename=file.filename or "",
            idempotency_key=idempotency_key,
            set_as_active=set_as_active,
            stream=file.file,
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
    except UploadStorageError as exc:
        _raise_upload_error(
            "INTERNAL_ERROR",
            "An internal server error occurred.",
            500,
            exc,
        )
    finally:
        file.file.close()

    return StagedUploadResponse(
        data=StagedUploadData(
            upload_id=staged.upload_id,
            project_id=staged.project_id,
            original_filename=staged.original_filename,
            size_bytes=staged.temporary.size_bytes,
            set_as_active=staged.set_as_active,
        ),
        meta=ResponseMeta(request_id=_request_id()),
    )


def _request_id() -> str:
    request_id = get_request_id()
    if request_id is None:
        raise RuntimeError("The request identifier is unavailable.")
    return request_id


def _raise_upload_error(code: str, message: str, status_code: int, exc: Exception) -> Never:
    raise TransLokaError(code=code, message=message, status_code=status_code) from exc
