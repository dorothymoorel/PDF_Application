from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from enum import StrEnum
from io import BytesIO
from typing import BinaryIO, Protocol
from uuid import uuid4

from PIL import Image
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker
from transloka_core.database import transaction_scope
from transloka_core.database.models.files import FileRole, FileStatus, StoredFile
from transloka_core.repositories.files import (
    StoredFileRecord,
    StoredFilesRepository,
    StoredFileStorageKeyExistsError,
)
from transloka_core.storage.local import (
    LocalFileStorage,
    StoredFileExistsError,
    StoredFileNotFoundError,
)

from transloka_documents.ocr.base import (
    OCRPage,
    OCRProvider,
    OCRProviderError,
    OCRProviderErrorCode,
    OCRResult,
    OCRSettings,
)
from transloka_documents.ocr.detection import ScannedPageDetection
from transloka_documents.rendering.page import PageRenderResult, render_pdf_page


class OCRRunStatus(StrEnum):
    COMPLETED = "COMPLETED"
    PARTIALLY_COMPLETED = "PARTIALLY_COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class OCROrchestrationError(RuntimeError):
    pass


class OCRRequestError(ValueError):
    pass


class OCRPersistenceError(OCROrchestrationError):
    pass


class OCRPageProcessingError(OCROrchestrationError):
    def __init__(self, error: Exception, attempts: int) -> None:
        self.error_code = _error_code(error)
        self.attempts = attempts
        super().__init__(_safe_error_message(error))


@dataclass(frozen=True, slots=True)
class OCRPageRequest:
    """Immutable input for one OCR job's selected pages."""

    job_id: str
    project_id: str
    source_pdf: bytes | bytearray | BinaryIO | Callable[[], BinaryIO]
    page_numbers: Sequence[int] = ()
    document_id: str | None = None
    dpi: int = 150
    settings: OCRSettings = OCRSettings()
    max_attempts: int = 3

    def __post_init__(self) -> None:
        _validate_non_empty_text(self.job_id, "Job identifier")
        _validate_non_empty_text(self.project_id, "Project identifier")
        if self.document_id is not None:
            _validate_non_empty_text(self.document_id, "Document identifier")
        if isinstance(self.page_numbers, (str, bytes, bytearray)):
            raise OCRRequestError("Page numbers must be a sequence of integers.")
        try:
            pages = tuple(self.page_numbers)
        except TypeError as exc:
            raise OCRRequestError("Page numbers must be a sequence of integers.") from exc
        if any(isinstance(page, bool) or not isinstance(page, int) or page < 1 for page in pages):
            raise OCRRequestError("Page numbers must be positive integers.")
        if len(set(pages)) != len(pages):
            raise OCRRequestError("Page numbers must not contain duplicates.")
        object.__setattr__(self, "page_numbers", pages)
        if (
            isinstance(self.dpi, bool)
            or not isinstance(self.dpi, int)
            or self.dpi
            not in {
                72,
                96,
                120,
                144,
                150,
                200,
                300,
            }
        ):
            raise OCRRequestError("The OCR render DPI is not allowed.")
        if isinstance(self.max_attempts, bool) or not isinstance(self.max_attempts, int):
            raise OCRRequestError("Maximum OCR attempts must be a positive integer.")
        if self.max_attempts < 1:
            raise OCRRequestError("Maximum OCR attempts must be a positive integer.")
        _validate_source(self.source_pdf)

    @classmethod
    def for_auto_pages(
        cls,
        *,
        job_id: str,
        project_id: str,
        source_pdf: bytes | bytearray | BinaryIO | Callable[[], BinaryIO],
        detections: Iterable[ScannedPageDetection],
        document_id: str | None = None,
        dpi: int = 150,
        settings: OCRSettings | None = None,
        max_attempts: int = 3,
    ) -> OCRPageRequest:
        return cls(
            job_id=job_id,
            project_id=project_id,
            source_pdf=source_pdf,
            page_numbers=pages_requiring_ocr(detections),
            document_id=document_id,
            dpi=dpi,
            settings=settings or OCRSettings(),
            max_attempts=max_attempts,
        )


@dataclass(frozen=True, slots=True)
class RawOCROutput:
    file_id: str | None
    storage_key: str
    checksum_sha256: str
    size_bytes: int
    record: StoredFileRecord | None = None


@dataclass(frozen=True, slots=True)
class OCRPageOutput:
    page_number: int
    result: OCRResult
    render: PageRenderResult
    raw_output: RawOCROutput
    attempts: int


@dataclass(frozen=True, slots=True)
class OCRPageFailure:
    page_number: int
    error_code: str
    error_message: str
    attempts: int


@dataclass(frozen=True, slots=True)
class OCRRunResult:
    job_id: str
    status: OCRRunStatus
    selected_page_numbers: tuple[int, ...]
    completed_page_numbers: tuple[int, ...]
    failed_page_numbers: tuple[int, ...]
    cancelled_page_numbers: tuple[int, ...]
    outputs: tuple[OCRPageOutput, ...] = ()
    failures: tuple[OCRPageFailure, ...] = ()


class PageRenderer(Protocol):
    def __call__(
        self,
        stream: BinaryIO,
        *,
        storage: LocalFileStorage,
        project_id: str,
        page_number: int,
        dpi: int,
    ) -> PageRenderResult: ...


class RawOutputStore(Protocol):
    def persist(
        self,
        *,
        job_id: str,
        project_id: str,
        document_id: str | None,
        page_number: int,
        result: OCRResult,
        attempts: int,
    ) -> RawOCROutput: ...


class OCRRawOutputStore:
    """Writes immutable raw OCR JSON and optionally records it in SQLite."""

    def __init__(
        self,
        storage: LocalFileStorage,
        session_factory: sessionmaker[Session] | None = None,
    ) -> None:
        self._storage = storage
        self._session_factory = session_factory

    def persist(
        self,
        *,
        job_id: str,
        project_id: str,
        document_id: str | None,
        page_number: int,
        result: OCRResult,
        attempts: int,
    ) -> RawOCROutput:
        payload = _raw_payload(
            job_id=job_id,
            project_id=project_id,
            document_id=document_id,
            page_number=page_number,
            result=result,
            attempts=attempts,
        )
        encoded = json.dumps(
            payload,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
        storage_key = f"projects/{project_id}/ocr/raw/{job_id}/page-{page_number}.json"
        artifact = self._commit_bytes(encoded, storage_key)
        record = self._record_file(
            storage_key=storage_key,
            artifact=artifact,
            job_id=job_id,
            project_id=project_id,
            document_id=document_id,
            page_number=page_number,
            result=result,
            attempts=attempts,
        )
        return RawOCROutput(
            file_id=record.id if record is not None else None,
            storage_key=storage_key,
            checksum_sha256=artifact[0],
            size_bytes=artifact[1],
            record=record,
        )

    def _commit_bytes(self, payload: bytes, storage_key: str) -> tuple[str, int]:
        checksum = hashlib.sha256(payload).hexdigest()
        temporary = self._storage.write_temporary(BytesIO(payload))
        try:
            self._storage.commit(temporary, storage_key, immutable=True)
            return checksum, len(payload)
        except StoredFileExistsError:
            try:
                existing_checksum = self._storage.checksum(storage_key)
                with self._storage.open_read(storage_key) as existing:
                    existing_size = len(existing.read())
            except (StoredFileNotFoundError, OSError) as exc:
                raise OCRPersistenceError(
                    "The existing raw OCR output could not be verified."
                ) from exc
            if existing_checksum != checksum or existing_size != len(payload):
                raise OCRPersistenceError(
                    "A raw OCR output already exists with different content."
                ) from None
            return existing_checksum, existing_size
        except Exception as exc:
            raise OCRPersistenceError("The raw OCR output could not be persisted safely.") from exc

    def _record_file(
        self,
        *,
        storage_key: str,
        artifact: tuple[str, int],
        job_id: str,
        project_id: str,
        document_id: str | None,
        page_number: int,
        result: OCRResult,
        attempts: int,
    ) -> StoredFileRecord | None:
        if self._session_factory is None:
            return None
        checksum, size_bytes = artifact
        created_at = _utc_now()
        metadata = {
            "job_id": job_id,
            "page_number": page_number,
            "attempts": attempts,
            "provider": result.provider,
            "confidence": result.confidence,
        }
        with transaction_scope(self._session_factory) as session:
            repository = StoredFilesRepository(session)
            try:
                return repository.create(
                    file_id=f"fil_{uuid4()}",
                    project_id=project_id,
                    document_id=document_id,
                    file_role=FileRole.OCR_OUTPUT,
                    storage_key=storage_key,
                    original_filename=None,
                    safe_filename=storage_key.rsplit("/", 1)[-1],
                    mime_type="application/json",
                    size_bytes=size_bytes,
                    checksum_sha256=checksum,
                    is_immutable=True,
                    status=FileStatus.VALIDATED,
                    metadata=metadata,
                    created_at=created_at,
                )
            except StoredFileStorageKeyExistsError:
                existing_id = session.scalar(
                    select(StoredFile.id).where(StoredFile.storage_key == storage_key)
                )
                if existing_id is None:
                    raise OCRPersistenceError(
                        "The raw OCR file record disappeared during retry."
                    ) from None
                existing = repository.get(existing_id)
                if existing.checksum_sha256 != checksum or existing.size_bytes != size_bytes:
                    raise OCRPersistenceError(
                        "The stored raw OCR record has different content."
                    ) from None
                return existing


class OCRPageOrchestrator:
    """Renders and OCRs selected pages while preserving valid page results."""

    def __init__(
        self,
        provider: OCRProvider,
        storage: LocalFileStorage,
        *,
        raw_output_store: RawOutputStore | None = None,
        renderer: PageRenderer = render_pdf_page,
    ) -> None:
        self._provider = provider
        self._storage = storage
        self._raw_output_store = raw_output_store or OCRRawOutputStore(storage)
        self._renderer = renderer

    def run(
        self,
        request: OCRPageRequest,
        *,
        cancel_check: Callable[[], bool] | None = None,
        progress_callback: Callable[[float, str], None] | None = None,
    ) -> OCRRunResult:
        source_bytes = _read_source_bytes(request.source_pdf)
        outputs: list[OCRPageOutput] = []
        failures: list[OCRPageFailure] = []
        cancelled_pages: list[int] = []
        total = len(request.page_numbers)

        for index, page_number in enumerate(request.page_numbers):
            if cancel_check is not None and cancel_check():
                cancelled_pages.extend(request.page_numbers[index:])
                break
            if progress_callback is not None:
                progress_callback(index / total if total else 0.0, f"OCR_PAGE_{page_number}")
            try:
                output = self._run_page(request, source_bytes, page_number)
            except Exception as exc:
                failures.append(
                    OCRPageFailure(
                        page_number=page_number,
                        error_code=_error_code(exc),
                        error_message=_safe_error_message(exc),
                        attempts=_attempt_count(exc),
                    )
                )
            else:
                outputs.append(output)
            if progress_callback is not None:
                progress_callback(
                    (index + 1) / total if total else 1.0, f"OCR_PAGE_{page_number}_DONE"
                )
            if cancel_check is not None and cancel_check():
                cancelled_pages.extend(request.page_numbers[index + 1 :])
                break

        completed = tuple(output.page_number for output in outputs)
        failed = tuple(failure.page_number for failure in failures)
        cancelled = tuple(cancelled_pages)
        if cancelled:
            status = OCRRunStatus.CANCELLED
        elif failures and outputs:
            status = OCRRunStatus.PARTIALLY_COMPLETED
        elif failures:
            status = OCRRunStatus.FAILED
        else:
            status = OCRRunStatus.COMPLETED
        return OCRRunResult(
            job_id=request.job_id,
            status=status,
            selected_page_numbers=tuple(request.page_numbers),
            completed_page_numbers=completed,
            failed_page_numbers=failed,
            cancelled_page_numbers=cancelled,
            outputs=tuple(outputs),
            failures=tuple(failures),
        )

    def _run_page(
        self,
        request: OCRPageRequest,
        source_bytes: bytes,
        page_number: int,
    ) -> OCRPageOutput:
        render = self._renderer(
            BytesIO(source_bytes),
            storage=self._storage,
            project_id=request.project_id,
            page_number=page_number,
            dpi=request.dpi,
        )
        with self._storage.open_read(render.render.storage_key) as stored_render:
            image_bytes = stored_render.read()
        width_px, height_px = _image_size(image_bytes)

        attempts = 0
        while True:
            attempts += 1
            try:
                result = self._provider.analyze_page(
                    OCRPage(
                        page_number=page_number,
                        width_px=width_px,
                        height_px=height_px,
                        image=image_bytes,
                    ),
                    settings=request.settings,
                )
                if result.page_number != page_number:
                    raise OCRProviderError(
                        code=OCRProviderErrorCode.INVALID_RESPONSE,
                        message="The OCR provider returned the wrong page number.",
                        retryable=False,
                    )
                raw_output = self._raw_output_store.persist(
                    job_id=request.job_id,
                    project_id=request.project_id,
                    document_id=request.document_id,
                    page_number=page_number,
                    result=result,
                    attempts=attempts,
                )
                return OCRPageOutput(
                    page_number=page_number,
                    result=result,
                    render=render,
                    raw_output=raw_output,
                    attempts=attempts,
                )
            except OCRProviderError as exc:
                if not exc.retryable or attempts >= request.max_attempts:
                    raise OCRPageProcessingError(exc, attempts) from exc


def pages_requiring_ocr(detections: Iterable[ScannedPageDetection]) -> tuple[int, ...]:
    pages: list[int] = []
    for detection in detections:
        if not isinstance(detection, ScannedPageDetection):
            raise OCRRequestError("Automatic OCR selection contains an invalid detection.")
        if detection.requires_ocr:
            pages.append(detection.page_number)
    if len(set(pages)) != len(pages):
        raise OCRRequestError("Automatic OCR selection contains duplicate pages.")
    return tuple(pages)


def _raw_payload(
    *,
    job_id: str,
    project_id: str,
    document_id: str | None,
    page_number: int,
    result: OCRResult,
    attempts: int,
) -> dict[str, object]:
    return {
        "schema": "transloka.ocr.raw.v1",
        "job_id": job_id,
        "project_id": project_id,
        "document_id": document_id,
        "page_number": page_number,
        "attempts": attempts,
        "provider": result.provider,
        "text": result.text,
        "confidence": result.confidence,
        "settings": {
            "language": result.settings.language,
            "detect_tables": result.settings.detect_tables,
            "detect_formulas": result.settings.detect_formulas,
            "timeout_seconds": result.settings.timeout_seconds,
            "low_confidence_threshold": result.settings.low_confidence_threshold,
        },
        "blocks": [
            {
                "text": block.text,
                "confidence": block.confidence,
                "geometry": {
                    "x": block.geometry.x,
                    "y": block.geometry.y,
                    "width": block.geometry.width,
                    "height": block.geometry.height,
                    "coordinate_system": block.geometry.coordinate_system,
                },
            }
            for block in result.blocks
        ],
    }


def _read_source_bytes(
    source: bytes | bytearray | BinaryIO | Callable[[], BinaryIO],
) -> bytes:
    stream: BinaryIO | None = None
    owns_stream = False
    try:
        if callable(source):
            stream = source()
            owns_stream = True
        elif isinstance(source, (bytes, bytearray)):
            return bytes(source)
        else:
            stream = source
        if stream is None or not hasattr(stream, "read") or not hasattr(stream, "seek"):
            raise OCRRequestError("The OCR source must be readable binary data.")
        stream.seek(0)
        payload = stream.read()
        if not isinstance(payload, bytes) or not payload:
            raise OCRRequestError("The OCR source must contain non-empty binary data.")
        return payload
    except OCRRequestError:
        raise
    except Exception as exc:
        raise OCRRequestError("The OCR source could not be read safely.") from exc
    finally:
        if owns_stream and stream is not None:
            try:
                stream.close()
            except OSError:
                pass


def _image_size(image_bytes: bytes) -> tuple[int, int]:
    try:
        with Image.open(BytesIO(image_bytes)) as image:
            width, height = image.size
    except Exception as exc:
        raise OCROrchestrationError("The rendered OCR input is not a valid image.") from exc
    if width <= 0 or height <= 0:
        raise OCROrchestrationError("The rendered OCR input has invalid dimensions.")
    return width, height


def _validate_source(source: object) -> None:
    if isinstance(source, (bytes, bytearray)):
        if not source:
            raise OCRRequestError("The OCR source must not be empty.")
        return
    if callable(source) or (hasattr(source, "read") and hasattr(source, "seek")):
        return
    raise OCRRequestError("The OCR source must be bytes or a readable stream factory.")


def _validate_non_empty_text(value: object, label: str) -> None:
    if not isinstance(value, str) or not value.strip() or not value.isprintable():
        raise OCRRequestError(f"{label} is invalid.")


def _error_code(error: Exception) -> str:
    if isinstance(error, OCRPageProcessingError):
        return error.error_code
    if isinstance(error, OCRProviderError):
        return str(error.code)
    return type(error).__name__.upper()


def _safe_error_message(error: Exception) -> str:
    message = str(error).strip()
    return message if message and message.isprintable() else "OCR page processing failed."


def _attempt_count(error: Exception) -> int:
    return int(getattr(error, "attempts", 1))


def _utc_now() -> str:
    from datetime import UTC, datetime

    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


# Compatibility aliases keep the public entry points easy to discover.
OCROrchestrator = OCRPageOrchestrator
OCRJobRequest = OCRPageRequest
OCRJobResult = OCRRunResult
