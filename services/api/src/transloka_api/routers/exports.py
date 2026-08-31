from collections.abc import Iterator
from typing import Annotated, Any, Never, cast

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker
from starlette.responses import StreamingResponse
from transloka_api.config import Settings
from transloka_api.exception_handlers import TransLokaError
from transloka_api.middleware import get_request_id
from transloka_api.schemas import ErrorResponse
from transloka_api.schemas.projects import ResponseMeta
from transloka_core.database.models.exports import Export, ExportStatus, ExportType
from transloka_core.database.models.files import FileStatus, StoredFile
from transloka_core.database.models.projects import Project
from transloka_core.storage.local import LocalFileStorage, LocalFileStorageError

_ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    404: {"description": "The export or project was not found.", "model": ErrorResponse},
    409: {"description": "The export file is unavailable.", "model": ErrorResponse},
    422: {"description": "The request is invalid.", "model": ErrorResponse},
}

router = APIRouter(prefix="/api/v1", tags=["Exports"])


class ExportData(BaseModel):
    id: str
    project_id: str
    document_id: str
    reconstruction_job_id: str | None
    export_type: ExportType
    output_profile: str
    version_number: int
    status: ExportStatus
    filename: str
    page_count: int | None
    size_bytes: int | None
    checksum_sha256: str | None
    created_at: str
    completed_at: str | None


class ExportListResponse(BaseModel):
    data: list[ExportData]
    meta: ResponseMeta


def get_export_session(request: Request) -> Iterator[Session]:
    factory = getattr(request.app.state, "session_factory", None)
    if not callable(factory):
        raise RuntimeError("The export database is not configured.")
    with cast(sessionmaker[Session], factory)() as session:
        yield session


ExportSession = Annotated[Session, Depends(get_export_session)]


@router.get(
    "/projects/{project_id}/exports",
    operation_id="list_project_exports",
    response_model=ExportListResponse,
    responses=_ERROR_RESPONSES,
)
def list_project_exports(project_id: str, session: ExportSession) -> ExportListResponse:
    if session.get(Project, project_id) is None:
        _raise_not_found("PROJECT_NOT_FOUND", "The requested project was not found.")
    rows = list(
        session.execute(
            select(Export, StoredFile)
            .outerjoin(StoredFile, Export.file_id == StoredFile.id)
            .where(Export.project_id == project_id)
            .order_by(Export.version_number.desc(), Export.created_at.desc())
        )
    )
    return ExportListResponse(
        data=[_export_data(export, stored) for export, stored in rows],
        meta=ResponseMeta(request_id=_request_id()),
    )


@router.get(
    "/exports/{export_id}/download",
    operation_id="download_export",
    responses={
        **_ERROR_RESPONSES,
        200: {"content": {"application/pdf": {}}, "description": "Validated export PDF."},
    },
)
def download_export(
    export_id: str,
    request: Request,
    session: ExportSession,
) -> StreamingResponse:
    row = session.execute(
        select(Export, StoredFile)
        .join(StoredFile, Export.file_id == StoredFile.id)
        .where(Export.id == export_id)
    ).one_or_none()
    if row is None:
        _raise_not_found("EXPORT_NOT_FOUND", "The requested export was not found.")
    export, stored = row
    if export.status not in {
        ExportStatus.COMPLETED.value,
        ExportStatus.COMPLETED_WITH_WARNINGS.value,
    } or stored.status not in {FileStatus.AVAILABLE.value, FileStatus.VALIDATED.value}:
        _raise_unavailable()
    settings = cast(Settings, request.app.state.settings)
    storage = LocalFileStorage(settings.data_directories)
    try:
        if storage.checksum(stored.storage_key) != stored.checksum_sha256:
            _raise_unavailable()
        source = storage.open_read(stored.storage_key)
    except LocalFileStorageError as exc:
        raise TransLokaError(
            code="EXPORT_UNAVAILABLE",
            message="The validated export PDF is unavailable.",
            status_code=409,
        ) from exc
    return StreamingResponse(
        _stream_file(source),
        media_type="application/pdf",
        headers={
            "Cache-Control": "no-store",
            "Content-Disposition": f'attachment; filename="{_safe_filename(stored)}"',
            "X-Content-Type-Options": "nosniff",
        },
    )


def _export_data(export: Export, stored: StoredFile | None) -> ExportData:
    return ExportData(
        id=export.id,
        project_id=export.project_id,
        document_id=export.document_id,
        reconstruction_job_id=export.reconstruction_job_id,
        export_type=ExportType(export.export_type),
        output_profile=export.output_profile,
        version_number=export.version_number,
        status=ExportStatus(export.status),
        filename=_safe_filename(stored) if stored is not None else f"export-{export.id[4:12]}.pdf",
        page_count=export.page_count,
        size_bytes=export.size_bytes,
        checksum_sha256=export.checksum_sha256,
        created_at=export.created_at,
        completed_at=export.completed_at,
    )


def _safe_filename(stored: StoredFile) -> str:
    filename = stored.safe_filename
    if not filename or any(character in filename for character in '\\/:"'):
        return "translated.pdf"
    return filename


def _stream_file(source: Any) -> Iterator[bytes]:
    try:
        while chunk := source.read(1024 * 1024):
            yield chunk
    finally:
        source.close()


def _request_id() -> str:
    request_id = get_request_id()
    if request_id is None:
        raise RuntimeError("The request identifier is unavailable.")
    return request_id


def _raise_not_found(code: str, message: str) -> Never:
    raise TransLokaError(code=code, message=message, status_code=404)


def _raise_unavailable() -> Never:
    raise TransLokaError(
        code="EXPORT_UNAVAILABLE",
        message="The validated export PDF is unavailable.",
        status_code=409,
    )


__all__ = ["router"]
