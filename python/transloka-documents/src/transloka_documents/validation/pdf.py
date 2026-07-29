import hashlib
from dataclasses import dataclass
from typing import BinaryIO

from pypdf import PdfReader
from pypdf.errors import FileNotDecryptedError, LimitReachedError, PyPdfError

_CHUNK_SIZE = 1024 * 1024
_PDF_MAGIC = b"%PDF-"
_PDF_MIME_TYPE = "application/pdf"


@dataclass(frozen=True, slots=True)
class PdfValidationLimits:
    max_bytes: int
    max_pages: int
    max_objects: int
    disk_expansion_factor: int = 3
    disk_safety_margin_bytes: int = 0

    def __post_init__(self) -> None:
        if (
            self.max_bytes < 1
            or self.max_pages < 1
            or self.max_objects < 1
            or self.disk_expansion_factor < 1
            or self.disk_safety_margin_bytes < 0
        ):
            raise ValueError("PDF validation limits must be positive.")


@dataclass(frozen=True, slots=True)
class PdfValidationResult:
    checksum_sha256: str
    size_bytes: int
    page_count: int
    object_count: int
    required_disk_bytes_estimate: int


class PdfValidationError(ValueError):
    def __init__(
        self,
        code: str,
        message: str,
        *,
        details: dict[str, int] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.details = details or {}


def validate_pdf(
    stream: BinaryIO,
    *,
    filename: str,
    mime_type: str,
    limits: PdfValidationLimits,
    available_disk_bytes: int | None = None,
) -> PdfValidationResult:
    _validate_filename(filename)
    _validate_mime_type(mime_type)
    if available_disk_bytes is not None and available_disk_bytes < 0:
        raise ValueError("Available disk bytes cannot be negative.")

    _seek_start(stream)
    if _read(stream, len(_PDF_MAGIC)) != _PDF_MAGIC:
        _fail("INVALID_PDF_MAGIC", "The uploaded file does not have a valid PDF signature.")

    checksum, size_bytes = _checksum_and_size(stream, limits.max_bytes)
    reader = _open_reader(stream, limits.max_objects)
    if reader.is_encrypted:
        _fail("PDF_PASSWORD_PROTECTED", "Password-protected PDF files are not supported.")

    object_count = _object_count(reader)
    if object_count > limits.max_objects:
        _fail(
            "PDF_COMPLEXITY_LIMIT_EXCEEDED",
            "The PDF exceeds the configured object complexity limit.",
            details={"object_count": object_count, "max_objects": limits.max_objects},
        )

    page_count = _page_count(reader)
    if page_count > limits.max_pages:
        _fail(
            "PDF_PAGE_LIMIT_EXCEEDED",
            "The PDF exceeds the configured page limit.",
            details={"page_count": page_count, "max_pages": limits.max_pages},
        )

    required_disk_bytes = (
        size_bytes * limits.disk_expansion_factor + limits.disk_safety_margin_bytes
    )
    if available_disk_bytes is not None and available_disk_bytes < required_disk_bytes:
        _fail(
            "INSUFFICIENT_DISK_SPACE",
            "There is not enough free disk space for this PDF.",
            details={
                "required_bytes_estimate": required_disk_bytes,
                "available_bytes": available_disk_bytes,
            },
        )

    return PdfValidationResult(
        checksum_sha256=checksum,
        size_bytes=size_bytes,
        page_count=page_count,
        object_count=object_count,
        required_disk_bytes_estimate=required_disk_bytes,
    )


def _validate_filename(filename: str) -> None:
    if (
        not isinstance(filename, str)
        or not filename
        or not filename.isprintable()
        or filename != filename.strip()
        or "/" in filename
        or "\\" in filename
        or filename.casefold() == ".pdf"
        or not filename.casefold().endswith(".pdf")
    ):
        _fail("UNSUPPORTED_FILE_TYPE", "Only PDF files are supported.")


def _validate_mime_type(mime_type: str) -> None:
    if not isinstance(mime_type, str) or not mime_type.isprintable():
        _fail("FILE_TYPE_MISMATCH", "The file type signals do not identify a PDF.")
    media_type = mime_type.partition(";")[0].strip().casefold()
    if media_type != _PDF_MIME_TYPE:
        _fail("FILE_TYPE_MISMATCH", "The file type signals do not identify a PDF.")


def _checksum_and_size(stream: BinaryIO, max_bytes: int) -> tuple[str, int]:
    _seek_start(stream)
    checksum = hashlib.sha256()
    size_bytes = 0
    while True:
        chunk = _read(stream, min(_CHUNK_SIZE, max_bytes - size_bytes + 1))
        if not chunk:
            return checksum.hexdigest(), size_bytes
        size_bytes += len(chunk)
        if size_bytes > max_bytes:
            _fail(
                "FILE_TOO_LARGE",
                "The PDF exceeds the configured file size limit.",
                details={"max_bytes": max_bytes},
            )
        checksum.update(chunk)


def _open_reader(stream: BinaryIO, max_objects: int) -> PdfReader:
    _seek_start(stream)
    try:
        return PdfReader(
            stream,
            strict=True,
            root_object_recovery_limit=max_objects,
        )
    except LimitReachedError as exc:
        raise PdfValidationError(
            "PDF_COMPLEXITY_LIMIT_EXCEEDED",
            "The PDF exceeds the configured object complexity limit.",
        ) from exc
    except PyPdfError as exc:
        raise PdfValidationError(
            "PDF_CORRUPTED",
            "The PDF structure is corrupted or malformed.",
        ) from exc
    except Exception as exc:
        raise PdfValidationError(
            "PDF_PARSER_FAILED",
            "The PDF parser could not safely inspect the file.",
        ) from exc


def _page_count(reader: PdfReader) -> int:
    try:
        return len(reader.pages)
    except FileNotDecryptedError as exc:
        raise PdfValidationError(
            "PDF_PASSWORD_PROTECTED",
            "Password-protected PDF files are not supported.",
        ) from exc
    except PyPdfError as exc:
        raise PdfValidationError(
            "PDF_CORRUPTED",
            "The PDF structure is corrupted or malformed.",
        ) from exc
    except Exception as exc:
        raise PdfValidationError(
            "PDF_PARSER_FAILED",
            "The PDF parser could not safely inspect the file.",
        ) from exc


def _object_count(reader: PdfReader) -> int:
    object_ids = {
        object_id
        for generation in reader.xref.values()
        for object_id in generation
        if object_id != 0
    }
    object_ids.update(reader.xref_objStm)
    return len(object_ids)


def _seek_start(stream: BinaryIO) -> None:
    try:
        stream.seek(0)
    except (OSError, ValueError) as exc:
        raise PdfValidationError(
            "PDF_PARSER_FAILED",
            "The PDF stream could not be inspected safely.",
        ) from exc


def _read(stream: BinaryIO, size: int) -> bytes:
    try:
        chunk = stream.read(size)
    except (OSError, ValueError) as exc:
        raise PdfValidationError(
            "PDF_PARSER_FAILED",
            "The PDF stream could not be inspected safely.",
        ) from exc
    if not isinstance(chunk, bytes):
        _fail("PDF_PARSER_FAILED", "The PDF stream returned invalid data.")
    return chunk


def _fail(
    code: str,
    message: str,
    *,
    details: dict[str, int] | None = None,
) -> None:
    raise PdfValidationError(code, message, details=details)
