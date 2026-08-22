"""Deterministic, fail-closed validation for reconstructed PDF output."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Iterable, Iterator, Mapping, Sequence
from dataclasses import dataclass, field
from enum import StrEnum
from io import BytesIO
from os import PathLike
from pathlib import Path
from typing import Any, BinaryIO, cast
from urllib.parse import urlsplit

from pypdf import PdfReader
from pypdf.generic import ArrayObject, DictionaryObject, IndirectObject

_ALLOWED_URI_SCHEMES = frozenset({"http", "https", "mailto"})
_MAX_VISITED_CONTAINERS = 100_000
_SHA256_PATTERN = re.compile(r"^[0-9a-f]{64}$")


class FinalPdfValidationIssueCode(StrEnum):
    """Stable issue codes emitted by final PDF validation."""

    CANNOT_OPEN = "PDF_CANNOT_OPEN"
    ENCRYPTED = "PDF_PASSWORD_PROTECTED"
    INVALID_PAGE_COUNT = "PDF_INVALID_PAGE_COUNT"
    PAGE_COUNT_MISMATCH = "PDF_PAGE_COUNT_MISMATCH"
    CHECKSUM_MISMATCH = "PDF_CHECKSUM_MISMATCH"
    TEXT_EXTRACTION_FAILED = "PDF_TEXT_EXTRACTION_FAILED"
    NO_SELECTABLE_TEXT = "PDF_NO_SELECTABLE_TEXT"
    BLANK_OUTPUT = "PDF_BLANK_OUTPUT"
    MISSING_SEGMENT = "PDF_MISSING_SEGMENT"
    SOURCE_RESIDUE = "PDF_SOURCE_RESIDUE"
    ACTIVE_CONTENT = "PDF_ACTIVE_CONTENT_DETECTED"
    ACTIVE_CONTENT_INSPECTION_FAILED = "PDF_ACTIVE_CONTENT_INSPECTION_FAILED"
    MAJOR_IMAGES_MISSING = "PDF_MAJOR_IMAGES_MISSING"
    CRITICAL_WARNING = "PDF_CRITICAL_WARNING"


@dataclass(frozen=True, slots=True)
class FinalPdfValidationIssue:
    """One blocking or informational finding from final output validation."""

    code: FinalPdfValidationIssueCode
    message: str
    page_number: int | None = None
    details: Mapping[str, str | int] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class FinalPdfValidationReport:
    """Validation evidence used to decide whether an export may complete."""

    is_valid: bool
    checksum_sha256: str
    size_bytes: int
    page_count: int
    extracted_text: str
    image_count: int
    issues: tuple[FinalPdfValidationIssue, ...] = ()

    @property
    def can_complete(self) -> bool:
        """Return whether the caller may mark the export ``COMPLETED``."""

        return self.is_valid and not self.issues

    @property
    def completion_status(self) -> str:
        """Return the only export status allowed by this report."""

        return "COMPLETED" if self.can_complete else "FAILED"

    @property
    def critical_issues(self) -> tuple[FinalPdfValidationIssue, ...]:
        return self.issues

    def raise_for_completion(self) -> None:
        """Fail closed when invalid output is about to be marked complete."""

        if not self.can_complete:
            raise FinalPdfValidationError(self)

    def raise_for_critical(self) -> None:
        """Compatibility alias for quality-gate callers."""

        self.raise_for_completion()


class FinalPdfValidationError(ValueError):
    """Raised when final output fails a completion gate."""

    def __init__(self, report: FinalPdfValidationReport) -> None:
        self.report = report
        codes = ", ".join(issue.code.value for issue in report.issues)
        super().__init__(f"Final PDF validation failed: {codes or 'unknown issue'}.")


def validate_final_pdf(
    source: bytes | bytearray | BinaryIO | str | PathLike[str],
    *,
    expected_page_count: int | None = None,
    expected_checksum_sha256: str | None = None,
    required_segments: Sequence[str] = (),
    source_residue: Sequence[str] = (),
    expected_major_images: int | None = None,
    minimum_major_images: int | None = None,
    critical_warnings: Iterable[object] | object | None = None,
    require_selectable_text: bool = True,
) -> FinalPdfValidationReport:
    """Validate a reconstructed PDF without executing any document content.

    The function reads the output into memory once, computes its checksum, and
    then inspects it with ``pypdf``. Every finding is returned in the report;
    callers must use :meth:`FinalPdfValidationReport.raise_for_completion` (or
    check ``can_complete``) before persisting ``COMPLETED``.
    """

    if expected_page_count is not None and expected_page_count < 1:
        raise ValueError("expected_page_count must be positive when supplied.")
    if expected_checksum_sha256 is not None and not _SHA256_PATTERN.fullmatch(
        expected_checksum_sha256
    ):
        raise ValueError("expected_checksum_sha256 must be a lowercase SHA-256 digest.")
    if expected_major_images is not None and expected_major_images < 0:
        raise ValueError("expected_major_images cannot be negative.")
    if minimum_major_images is not None and minimum_major_images < 0:
        raise ValueError("minimum_major_images cannot be negative.")
    if expected_major_images is not None and minimum_major_images is not None:
        raise ValueError("Supply only one major-image requirement.")
    image_requirement = (
        expected_major_images if expected_major_images is not None else minimum_major_images
    )

    data = _read_source(source)
    checksum = hashlib.sha256(data).hexdigest()
    issues: list[FinalPdfValidationIssue] = []
    if expected_checksum_sha256 is not None and checksum != expected_checksum_sha256:
        issues.append(
            FinalPdfValidationIssue(
                FinalPdfValidationIssueCode.CHECKSUM_MISMATCH,
                "The output checksum does not match the expected checksum.",
                details={"expected": expected_checksum_sha256, "actual": checksum},
            )
        )

    try:
        reader = PdfReader(BytesIO(data), strict=False)
    except Exception as exc:
        issues.append(
            FinalPdfValidationIssue(
                FinalPdfValidationIssueCode.CANNOT_OPEN,
                "The final PDF could not be opened safely.",
                details={"error": type(exc).__name__},
            )
        )
        return _report(data, checksum, "", 0, 0, issues)

    if reader.is_encrypted:
        issues.append(
            FinalPdfValidationIssue(
                FinalPdfValidationIssueCode.ENCRYPTED,
                "Password-protected output cannot be validated for export.",
            )
        )

    pages: list[Any] = []
    try:
        pages = list(reader.pages)
    except Exception as exc:
        issues.append(
            FinalPdfValidationIssue(
                FinalPdfValidationIssueCode.CANNOT_OPEN,
                "The final PDF page tree could not be opened safely.",
                details={"error": type(exc).__name__},
            )
        )

    page_count = len(pages)
    if page_count < 1:
        issues.append(
            FinalPdfValidationIssue(
                FinalPdfValidationIssueCode.INVALID_PAGE_COUNT,
                "The final PDF must contain at least one page.",
            )
        )
    if expected_page_count is not None and page_count != expected_page_count:
        issues.append(
            FinalPdfValidationIssue(
                FinalPdfValidationIssueCode.PAGE_COUNT_MISMATCH,
                "The output page count does not match the expected count.",
                details={"expected": expected_page_count, "actual": page_count},
            )
        )

    page_text: list[str] = []
    for page_number, page in enumerate(pages, start=1):
        try:
            page_text.append(page.extract_text() or "")
        except Exception as exc:
            page_text.append("")
            issues.append(
                FinalPdfValidationIssue(
                    FinalPdfValidationIssueCode.TEXT_EXTRACTION_FAILED,
                    "Text could not be extracted from a final PDF page.",
                    page_number=page_number,
                    details={"error": type(exc).__name__},
                )
            )

    extracted_text = "\n".join(page_text)
    normalized_text = _normalize_text(extracted_text)
    if require_selectable_text and not normalized_text:
        issues.append(
            FinalPdfValidationIssue(
                FinalPdfValidationIssueCode.BLANK_OUTPUT,
                "The final PDF contains no selectable text.",
            )
        )
    elif require_selectable_text and not any(text.strip() for text in page_text):
        issues.append(
            FinalPdfValidationIssue(
                FinalPdfValidationIssueCode.NO_SELECTABLE_TEXT,
                "The final PDF does not contain a selectable text layer.",
            )
        )

    for segment in _required_values(required_segments, "required_segments"):
        if _normalize_text(segment) not in normalized_text:
            issues.append(
                FinalPdfValidationIssue(
                    FinalPdfValidationIssueCode.MISSING_SEGMENT,
                    "A required translated segment is missing from the final PDF.",
                    details={"segment": segment},
                )
            )

    for residue in _required_values(source_residue, "source_residue"):
        if _normalize_text(residue) in normalized_text:
            issues.append(
                FinalPdfValidationIssue(
                    FinalPdfValidationIssueCode.SOURCE_RESIDUE,
                    "Source text residue remains searchable in the final PDF.",
                    details={"residue": residue},
                )
            )

    image_count = _count_images(pages)
    if image_requirement is not None and image_count < image_requirement:
        issues.append(
            FinalPdfValidationIssue(
                FinalPdfValidationIssueCode.MAJOR_IMAGES_MISSING,
                "The final PDF contains fewer major images than required.",
                details={"expected": image_requirement, "actual": image_count},
            )
        )

    try:
        active_content = _active_content_findings(reader)
    except Exception as exc:
        issues.append(
            FinalPdfValidationIssue(
                FinalPdfValidationIssueCode.ACTIVE_CONTENT_INSPECTION_FAILED,
                "Active content could not be inspected safely.",
                details={"error": type(exc).__name__},
            )
        )
    else:
        if active_content:
            issues.append(
                FinalPdfValidationIssue(
                    FinalPdfValidationIssueCode.ACTIVE_CONTENT,
                    "The final PDF contains unsafe active content.",
                    details={"findings": ",".join(sorted(active_content))},
                )
            )

    for warning in _blocking_warnings(critical_warnings):
        issues.append(
            FinalPdfValidationIssue(
                FinalPdfValidationIssueCode.CRITICAL_WARNING,
                "A critical reconstruction warning blocks final export.",
                details={"warning": warning},
            )
        )

    return _report(data, checksum, extracted_text, page_count, image_count, issues)


def _read_source(source: bytes | bytearray | BinaryIO | str | PathLike[str]) -> bytes:
    if isinstance(source, bytes):
        return source
    if isinstance(source, bytearray):
        return bytes(source)
    if isinstance(source, (str, PathLike)):
        return Path(source).read_bytes()

    original_position: int | None = None
    try:
        original_position = source.tell()
        source.seek(0)
        data = source.read()
    finally:
        if original_position is not None:
            try:
                source.seek(original_position)
            except (OSError, ValueError):
                pass
    if not isinstance(data, bytes):
        raise TypeError("PDF source stream must return bytes.")
    return data


def _report(
    data: bytes,
    checksum: str,
    extracted_text: str,
    page_count: int,
    image_count: int,
    issues: list[FinalPdfValidationIssue],
) -> FinalPdfValidationReport:
    return FinalPdfValidationReport(
        is_valid=not issues,
        checksum_sha256=checksum,
        size_bytes=len(data),
        page_count=page_count,
        extracted_text=extracted_text,
        image_count=image_count,
        issues=tuple(issues),
    )


def _required_values(values: Sequence[str], name: str) -> tuple[str, ...]:
    normalized = tuple(values)
    if any(not isinstance(value, str) or not value.strip() for value in normalized):
        raise ValueError(f"{name} values must be non-empty strings.")
    return normalized


def _normalize_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip().casefold()


def _count_images(pages: Sequence[Any]) -> int:
    count = 0
    for page in pages:
        resources = _resolve(page.get("/Resources"))
        if not isinstance(resources, DictionaryObject):
            continue
        xobjects = _resolve(resources.get("/XObject"))
        if not isinstance(xobjects, DictionaryObject):
            continue
        for reference in xobjects.values():
            image = _resolve(reference)
            if isinstance(image, DictionaryObject) and str(image.get("/Subtype", "")) == "/Image":
                count += 1
    return count


def _active_content_findings(reader: PdfReader) -> set[str]:
    findings: set[str] = set()
    for dictionary in _walk_dictionaries(reader.root_object):
        action = str(dictionary.get("/S", ""))
        if action == "/JavaScript" or "/JavaScript" in dictionary or "/JS" in dictionary:
            findings.add("JavaScript")
        if action == "/Launch":
            findings.add("Launch")
        if any(key in dictionary for key in ("/EmbeddedFiles", "/EF", "/AF")):
            findings.add("EmbeddedFile")
        if str(dictionary.get("/Subtype", "")) == "/FileAttachment":
            findings.add("FileAttachment")
        if any(key in dictionary for key in ("/RichMedia", "/Movie", "/Sound", "/3D")):
            findings.add("EmbeddedMedia")
        if action == "/URI" and "/URI" in dictionary:
            scheme = _uri_scheme(dictionary["/URI"])
            if scheme not in _ALLOWED_URI_SCHEMES:
                findings.add(f"UnsafeURI:{scheme or 'missing'}")
    return findings


def _walk_dictionaries(root: object) -> Iterator[DictionaryObject]:
    stack: list[object] = [root]
    seen_indirect: set[tuple[int, int]] = set()
    seen_containers: set[int] = set()
    while stack:
        current = _resolve(stack.pop(), seen_indirect)
        if not isinstance(current, (DictionaryObject, ArrayObject)):
            continue
        identity = id(current)
        if identity in seen_containers:
            continue
        seen_containers.add(identity)
        if len(seen_containers) > _MAX_VISITED_CONTAINERS:
            raise ValueError("The PDF object graph is too large to inspect safely.")
        if isinstance(current, DictionaryObject):
            yield current
            stack.extend(current.values())
        else:
            stack.extend(current)


def _resolve(value: object, seen: set[tuple[int, int]] | None = None) -> object:
    if not isinstance(value, IndirectObject):
        return value
    if seen is not None:
        reference = (value.idnum, value.generation)
        if reference in seen:
            return None
        seen.add(reference)
    return value.get_object()


def _uri_scheme(value: object) -> str:
    if isinstance(value, bytes):
        text = value.decode("utf-8", errors="replace")
    else:
        text = str(value)
    return urlsplit(text.strip()).scheme.casefold()


def _blocking_warnings(value: Iterable[object] | object | None) -> tuple[str, ...]:
    if value is None:
        return ()
    if hasattr(value, "critical_warnings"):
        value = cast(Any, value).critical_warnings
    if isinstance(value, (str, bytes)):
        values: Iterable[object] = (value,)
    else:
        try:
            values = iter(value)  # type: ignore[arg-type]
        except TypeError:
            values = (value,)

    blocking: list[str] = []
    for warning in values:
        if not _warning_blocks_export(warning):
            continue
        if isinstance(warning, bytes):
            label = warning.decode("utf-8", errors="replace")
        elif isinstance(warning, str):
            label = warning
        else:
            code = getattr(warning, "code", None) or getattr(warning, "warning_type", None)
            label = getattr(code, "value", None) or str(code or type(warning).__name__)
        if label.strip():
            blocking.append(label.strip())
    return tuple(blocking)


def _warning_blocks_export(warning: object) -> bool:
    if isinstance(warning, (str, bytes)):
        return bool(warning.strip())
    severity = getattr(warning, "severity", None)
    if severity is None:
        return True
    severity_value = str(getattr(severity, "value", severity)).casefold()
    if severity_value != "critical":
        return False
    status = getattr(warning, "status", None)
    if status is None:
        return True
    status_value = str(getattr(status, "value", status)).casefold()
    return status_value in {"open", "unresolved", "active"}
