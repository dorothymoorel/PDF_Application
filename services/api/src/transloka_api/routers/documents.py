from collections.abc import Mapping
from shutil import disk_usage
from typing import Annotated, Any, Literal, Never, cast

from fastapi import APIRouter, Depends, File, Form, Header, Request, UploadFile, status
from pydantic import BaseModel
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
from transloka_core.repositories.files import StoredFilesRepository
from transloka_core.repositories.projects import ProjectRepositoryError, ProjectsRepository
from transloka_core.storage.local import LocalFileStorage
from transloka_documents.validation import PdfValidationError, PdfValidationLimits, validate_pdf

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
}

router = APIRouter(prefix="/api/v1/projects", tags=["Documents"])


class ValidatedUploadData(BaseModel):
    original_file_id: str
    project_id: str
    status: Literal["VALIDATED"] = "VALIDATED"
    original_filename: str
    size_bytes: int
    checksum_sha256: str
    page_count: int
    set_as_active: bool


class ValidatedUploadResponse(BaseModel):
    data: ValidatedUploadData
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
    response_model=ValidatedUploadResponse,
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
) -> ValidatedUploadResponse:
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
        original = service.store_original(
            staged,
            validation,
            StoredFilesRepository(session),
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
    except OriginalImportConflictError as exc:
        _discard_after_failure(service, staged)
        _raise_upload_error(
            "IMPORT_CONFLICT",
            "The idempotency key belongs to a different original import.",
            409,
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
    return ValidatedUploadResponse(
        data=ValidatedUploadData(
            original_file_id=original.id,
            project_id=staged.project_id,
            original_filename=staged.original_filename,
            size_bytes=original.size_bytes,
            checksum_sha256=original.checksum_sha256,
            page_count=validation.page_count,
            set_as_active=staged.set_as_active,
        ),
        meta=ResponseMeta(request_id=_request_id()),
    )


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
