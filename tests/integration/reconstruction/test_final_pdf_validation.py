from __future__ import annotations

import hashlib
from io import BytesIO
from types import SimpleNamespace

from PIL import Image
from pypdf import PdfWriter
from pypdf.generic import ArrayObject, DictionaryObject, NameObject
from reportlab.lib.utils import ImageReader  # type: ignore[import-untyped]
from reportlab.pdfgen.canvas import Canvas  # type: ignore[import-untyped]
from transloka_quality.pdf import (
    FinalPdfValidationIssueCode,
    validate_final_pdf,
)


def _text_pdf(*lines: str) -> bytes:
    output = BytesIO()
    canvas = Canvas(output, pagesize=(300, 200))
    canvas.setFont("Helvetica", 12)
    for index, line in enumerate(lines):
        canvas.drawString(20, 170 - index * 20, line)
    canvas.save()
    return output.getvalue()


def _blank_pdf() -> bytes:
    output = BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(width=300, height=200)
    writer.write(output)
    return output.getvalue()


def test_valid_output_has_checksum_text_and_completed_gate() -> None:
    output = _text_pdf("Terjemahan final", "Segmen wajib")
    checksum = hashlib.sha256(output).hexdigest()

    report = validate_final_pdf(
        output,
        expected_page_count=1,
        expected_checksum_sha256=checksum,
        required_segments=("Segmen wajib",),
    )

    assert report.is_valid is True
    assert report.can_complete is True
    assert report.completion_status == "COMPLETED"
    assert report.page_count == 1
    assert report.checksum_sha256 == checksum
    assert "Terjemahan final" in report.extracted_text
    report.raise_for_completion()


def test_corrupted_output_cannot_complete() -> None:
    report = validate_final_pdf(b"not a PDF")

    assert report.is_valid is False
    assert report.completion_status == "FAILED"
    assert FinalPdfValidationIssueCode.CANNOT_OPEN in {issue.code for issue in report.issues}


def test_missing_required_segment_blocks_completion() -> None:
    report = validate_final_pdf(
        _text_pdf("Terjemahan tersedia"),
        required_segments=("Segmen hilang",),
    )

    assert report.is_valid is False
    assert any(issue.code is FinalPdfValidationIssueCode.MISSING_SEGMENT for issue in report.issues)


def test_active_content_blocks_completion() -> None:
    writer = PdfWriter()
    page = writer.add_blank_page(width=300, height=200)
    page[NameObject("/Annots")] = ArrayObject(
        [
            DictionaryObject(
                {
                    NameObject("/Subtype"): NameObject("/Link"),
                    NameObject("/A"): DictionaryObject(
                        {NameObject("/S"): NameObject("/JavaScript")}
                    ),
                }
            )
        ]
    )
    output = BytesIO()
    writer.write(output)

    report = validate_final_pdf(output.getvalue())

    assert report.is_valid is False
    assert any(issue.code is FinalPdfValidationIssueCode.ACTIVE_CONTENT for issue in report.issues)


def test_blank_output_is_rejected() -> None:
    report = validate_final_pdf(_blank_pdf())

    assert report.is_valid is False
    assert any(issue.code is FinalPdfValidationIssueCode.BLANK_OUTPUT for issue in report.issues)


def test_major_images_and_source_residue_are_checked() -> None:
    image = Image.new("RGB", (20, 20), (30, 80, 160))
    output = BytesIO()
    canvas = Canvas(output, pagesize=(300, 200))
    canvas.drawImage(ImageReader(image), 20, 20, width=40, height=40)
    canvas.drawString(20, 170, "Terjemahan")
    canvas.drawString(20, 150, "Source residue")
    canvas.save()

    report = validate_final_pdf(
        output.getvalue(),
        expected_major_images=1,
        source_residue=("Source residue",),
    )

    assert report.image_count == 1
    assert report.is_valid is False
    assert any(issue.code is FinalPdfValidationIssueCode.SOURCE_RESIDUE for issue in report.issues)


def test_open_critical_warning_blocks_completion() -> None:
    warning = SimpleNamespace(code="CRITICAL_CLIPPING", severity="CRITICAL", status="OPEN")

    report = validate_final_pdf(_text_pdf("Terjemahan"), critical_warnings=(warning,))

    assert report.is_valid is False
    assert any(
        issue.code is FinalPdfValidationIssueCode.CRITICAL_WARNING for issue in report.issues
    )
