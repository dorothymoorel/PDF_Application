from io import BytesIO

import pytest
from pypdf import PdfReader, PdfWriter
from pypdf.generic import (
    ArrayObject,
    DecodedStreamObject,
    DictionaryObject,
    NameObject,
    NumberObject,
)
from transloka_documents.analysis import PdfAnalysisError, analyze_pdf


def test_analyzes_portrait_pdf_metadata_and_text_layer() -> None:
    result = analyze_pdf(
        BytesIO(
            _pdf_bytes(
                width=612,
                height=792,
                title="  Guide  ",
                author="  TransLoka  ",
                text="Hello",
            )
        )
    )

    assert result.title == "Guide"
    assert result.author == "TransLoka"
    assert result.page_count == 1
    assert result.text_layer_estimate == 1.0
    assert result.pages[0].width_points == 612
    assert result.pages[0].height_points == 792
    assert result.pages[0].rotation_degrees == 0
    assert result.pages[0].has_text_layer is True


def test_analyzes_landscape_pdf_without_text() -> None:
    result = analyze_pdf(BytesIO(_pdf_bytes(width=792, height=612)))

    assert result.page_count == 1
    assert result.text_layer_estimate == 0.0
    assert result.pages[0].width_points == 792
    assert result.pages[0].height_points == 612
    assert result.pages[0].has_text_layer is False


def test_reports_rotated_page_geometry() -> None:
    result = analyze_pdf(BytesIO(_pdf_bytes(width=612, height=792, rotation=90)))

    assert result.pages[0].width_points == 792
    assert result.pages[0].height_points == 612
    assert result.pages[0].rotation_degrees == 90


def test_missing_metadata_returns_none() -> None:
    result = analyze_pdf(BytesIO(_pdf_bytes()))

    assert result.title is None
    assert result.author is None


def test_metadata_failure_does_not_abort_valid_pdf(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fail_metadata(_reader: PdfReader) -> None:
        raise RuntimeError("broken metadata")

    monkeypatch.setattr(PdfReader, "metadata", property(fail_metadata))

    result = analyze_pdf(BytesIO(_pdf_bytes(text="Still valid")))

    assert result.title is None
    assert result.author is None
    assert result.page_count == 1
    assert result.text_layer_estimate == 1.0


def test_malformed_page_geometry_is_normalized() -> None:
    with pytest.raises(PdfAnalysisError, match="could not be analyzed safely"):
        analyze_pdf(BytesIO(_pdf_bytes(malformed_page=True)))


def test_analysis_does_not_close_caller_stream() -> None:
    stream = BytesIO(_pdf_bytes())

    analyze_pdf(stream)

    assert stream.closed is False


def _pdf_bytes(
    *,
    width: float = 612,
    height: float = 792,
    rotation: int = 0,
    title: str | None = None,
    author: str | None = None,
    text: str | None = None,
    malformed_page: bool = False,
) -> bytes:
    destination = BytesIO()
    writer = PdfWriter()
    page = writer.add_blank_page(width=width, height=height)
    if malformed_page:
        page[NameObject("/MediaBox")] = ArrayObject(
            [
                NumberObject(0),
                NumberObject(0),
                NameObject("/invalid"),
                NumberObject(height),
            ]
        )
    if rotation:
        page.rotate(rotation)
    if title is not None or author is not None:
        writer.add_metadata(
            {
                key: value
                for key, value in {"/Title": title, "/Author": author}.items()
                if value is not None
            }
        )
    if text is not None:
        font = DictionaryObject(
            {
                NameObject("/Type"): NameObject("/Font"),
                NameObject("/Subtype"): NameObject("/Type1"),
                NameObject("/BaseFont"): NameObject("/Helvetica"),
            }
        )
        page[NameObject("/Resources")] = DictionaryObject(
            {NameObject("/Font"): DictionaryObject({NameObject("/F1"): writer._add_object(font)})}
        )
        content = DecodedStreamObject()
        content.set_data(f"BT /F1 12 Tf 10 36 Td ({text}) Tj ET".encode())
        page[NameObject("/Contents")] = writer._add_object(content)
    writer.write(destination)
    return destination.getvalue()
