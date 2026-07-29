import hashlib
from io import BytesIO

import pytest
from pypdf import PdfWriter
from transloka_documents.validation import (
    PdfValidationError,
    PdfValidationLimits,
    validate_pdf,
)

LIMITS = PdfValidationLimits(
    max_bytes=1024 * 1024,
    max_pages=10,
    max_objects=100,
    disk_expansion_factor=3,
    disk_safety_margin_bytes=128,
)


def test_valid_pdf_returns_bounded_metadata() -> None:
    content = _pdf_bytes(page_count=2)

    result = validate_pdf(
        BytesIO(content),
        filename="dokumen_日本語.PDF",
        mime_type="application/pdf; charset=binary",
        limits=LIMITS,
        available_disk_bytes=len(content) * 3 + 128,
    )

    assert result.checksum_sha256 == hashlib.sha256(content).hexdigest()
    assert result.size_bytes == len(content)
    assert result.page_count == 2
    assert 0 < result.object_count <= LIMITS.max_objects
    assert result.required_disk_bytes_estimate == len(content) * 3 + 128


@pytest.mark.parametrize(
    ("filename", "mime_type", "content", "expected_code"),
    [
        ("document.exe", "application/pdf", b"%PDF-invalid", "UNSUPPORTED_FILE_TYPE"),
        ("../document.pdf", "application/pdf", b"%PDF-invalid", "UNSUPPORTED_FILE_TYPE"),
        ("document.pdf", "text/plain", b"%PDF-invalid", "FILE_TYPE_MISMATCH"),
        ("document.pdf", "application/pdf", b"MZ-not-a-pdf", "INVALID_PDF_MAGIC"),
    ],
)
def test_file_type_signals_are_validated_before_parsing(
    filename: str,
    mime_type: str,
    content: bytes,
    expected_code: str,
) -> None:
    _assert_error(
        content,
        expected_code,
        filename=filename,
        mime_type=mime_type,
    )


def test_corrupted_pdf_is_normalized() -> None:
    content = _pdf_bytes()[:-20]

    _assert_error(content, "PDF_CORRUPTED")


def test_malformed_pdf_is_normalized() -> None:
    content = b"%PDF-1.7\n1 0 obj\n<< /Type /Catalog >>\nendobj\n"

    _assert_error(content, "PDF_CORRUPTED")


def test_password_protected_pdf_is_rejected() -> None:
    content = _pdf_bytes(password="secret")

    _assert_error(content, "PDF_PASSWORD_PROTECTED")


def test_page_limit_is_enforced_before_rendering() -> None:
    content = _pdf_bytes(page_count=2)
    limits = PdfValidationLimits(max_bytes=len(content), max_pages=1, max_objects=100)

    _assert_error(content, "PDF_PAGE_LIMIT_EXCEEDED", limits=limits)


def test_oversized_pdf_stops_after_limit_plus_one_byte() -> None:
    content = _pdf_bytes()
    stream = BytesIO(content)
    limits = PdfValidationLimits(max_bytes=10, max_pages=10, max_objects=100)

    with pytest.raises(PdfValidationError, match="file size limit") as captured:
        validate_pdf(
            stream,
            filename="document.pdf",
            mime_type="application/pdf",
            limits=limits,
        )

    assert captured.value.code == "FILE_TOO_LARGE"
    assert stream.tell() == 11


def test_basic_object_complexity_limit_is_enforced() -> None:
    content = _pdf_bytes()
    limits = PdfValidationLimits(
        max_bytes=len(content),
        max_pages=10,
        max_objects=1,
    )

    _assert_error(content, "PDF_COMPLEXITY_LIMIT_EXCEEDED", limits=limits)


def test_insufficient_disk_space_is_rejected_with_numeric_details() -> None:
    content = _pdf_bytes()
    limits = PdfValidationLimits(
        max_bytes=len(content),
        max_pages=10,
        max_objects=100,
        disk_expansion_factor=2,
        disk_safety_margin_bytes=50,
    )

    with pytest.raises(PdfValidationError) as captured:
        validate_pdf(
            BytesIO(content),
            filename="document.pdf",
            mime_type="application/pdf",
            limits=limits,
            available_disk_bytes=1,
        )

    assert captured.value.code == "INSUFFICIENT_DISK_SPACE"
    assert captured.value.details == {
        "required_bytes_estimate": len(content) * 2 + 50,
        "available_bytes": 1,
    }


def test_unexpected_parser_failure_is_normalized(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_parser(*_args: object, **_kwargs: object) -> None:
        raise RuntimeError("sensitive parser failure")

    monkeypatch.setattr("transloka_documents.validation.pdf.PdfReader", fail_parser)

    with pytest.raises(PdfValidationError) as captured:
        validate_pdf(
            BytesIO(_pdf_bytes()),
            filename="document.pdf",
            mime_type="application/pdf",
            limits=LIMITS,
        )

    assert captured.value.code == "PDF_PARSER_FAILED"
    assert "sensitive parser failure" not in captured.value.message


def _assert_error(
    content: bytes,
    expected_code: str,
    *,
    filename: str = "document.pdf",
    mime_type: str = "application/pdf",
    limits: PdfValidationLimits = LIMITS,
) -> PdfValidationError:
    with pytest.raises(PdfValidationError) as captured:
        validate_pdf(
            BytesIO(content),
            filename=filename,
            mime_type=mime_type,
            limits=limits,
        )
    assert captured.value.code == expected_code
    return captured.value


def _pdf_bytes(*, page_count: int = 1, password: str | None = None) -> bytes:
    destination = BytesIO()
    writer = PdfWriter()
    for _ in range(page_count):
        writer.add_blank_page(width=72, height=72)
    if password is not None:
        writer.encrypt(password, algorithm="AES-256")
    writer.write(destination)
    return destination.getvalue()
