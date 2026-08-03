from io import BytesIO

import pytest
from pypdf import PdfWriter
from pypdf.generic import DictionaryObject, NameObject, RectangleObject, TextStringObject
from transloka_documents.security import (
    ActiveContentWarningCode,
    detect_active_content,
)


def test_detects_embedded_javascript_without_executing_it() -> None:
    writer = _writer()
    writer.add_js("app.alert('must not execute')")

    report = detect_active_content(BytesIO(_pdf_bytes(writer)))

    assert report.warning_codes == (ActiveContentWarningCode.EMBEDDED_JAVASCRIPT,)
    assert "will not be executed" in report.warnings[0].message


def test_detects_attachment_without_extracting_it() -> None:
    writer = _writer()
    writer.add_attachment("payload.txt", b"attachment content")

    report = detect_active_content(BytesIO(_pdf_bytes(writer)))

    assert report.warning_codes == (ActiveContentWarningCode.EMBEDDED_ATTACHMENT,)
    assert "will not be opened or extracted" in report.warnings[0].message


def test_allows_safe_external_link_and_preserves_stream_position() -> None:
    writer = _writer()
    writer.add_uri(0, "https://example.com/guide", RectangleObject((0, 0, 20, 20)))
    stream = BytesIO(_pdf_bytes(writer))
    stream.seek(9)

    report = detect_active_content(stream)

    assert report.has_active_content is False
    assert report.warnings == ()
    assert stream.tell() == 9
    assert stream.closed is False


@pytest.mark.parametrize("scheme", ["javascript", "data", "file", "vbscript", "shell"])
def test_warns_for_unsafe_link_scheme(scheme: str) -> None:
    writer = _writer()
    writer.add_uri(0, f"{scheme}:payload", RectangleObject((0, 0, 20, 20)))

    report = detect_active_content(BytesIO(_pdf_bytes(writer)))

    assert report.warning_codes == (ActiveContentWarningCode.UNSAFE_URL_SCHEME,)
    assert report.warnings[0].details == (scheme,)


def test_detects_launch_action() -> None:
    writer = _writer()
    writer.root_object[NameObject("/OpenAction")] = DictionaryObject(
        {
            NameObject("/S"): NameObject("/Launch"),
            NameObject("/F"): TextStringObject("program.exe"),
        }
    )

    report = detect_active_content(BytesIO(_pdf_bytes(writer)))

    assert report.warning_codes == (ActiveContentWarningCode.LAUNCH_ACTION,)


def _writer() -> PdfWriter:
    writer = PdfWriter()
    writer.add_blank_page(width=72, height=72)
    return writer


def _pdf_bytes(writer: PdfWriter) -> bytes:
    destination = BytesIO()
    writer.write(destination)
    return destination.getvalue()
