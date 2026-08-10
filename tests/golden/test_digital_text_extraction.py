from dataclasses import dataclass
from io import BytesIO

import pytest
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject
from transloka_documents.extraction import (
    DigitalTextExtractionError,
    NormalizationKind,
    extract_digital_text,
    normalize_source_lines,
)
from transloka_documents.structure.reading_order import resolve_reading_order


@dataclass(frozen=True, slots=True)
class TextPlacement:
    text: str
    x: float
    y: float
    size: float = 12
    font: str = "F1"


def test_extracts_single_column_text_with_character_geometry_trace() -> None:
    stream = BytesIO(
        _pdf_bytes(
            TextPlacement("First paragraph line", 72, 720),
            TextPlacement("continues here", 72, 704),
        )
    )
    stream.seek(5)

    result = extract_digital_text(stream)

    assert stream.tell() == 5
    assert result.page_count == 1
    page = result.pages[0]
    assert page.has_text is True
    assert [line.source_text for line in page.lines] == [
        "First paragraph line",
        "continues here",
    ]
    assert len(page.block_candidates) == 1
    block = page.block_candidates[0]
    assert block.source_text == "First paragraph line\ncontinues here"
    assert block.normalized_text == "First paragraph line continues here"
    assert block.geometry.coordinate_system == "PDF_POINT_TOP_LEFT"
    assert block.geometry.x == pytest.approx(72)
    assert block.geometry.y >= 0
    assert block.geometry.x + block.geometry.width <= page.width_points
    assert block.geometry.y + block.geometry.height <= page.height_points
    assert block.line_indexes == (0, 1)
    assert block.word_indexes == tuple(range(len(page.words)))
    assert block.character_indexes
    for word_index in block.word_indexes:
        word = page.words[word_index]
        assert word.character_indexes
        assert "".join(page.characters[index].text for index in word.character_indexes) == (
            word.source_text
        )


def test_keeps_two_column_lines_as_separate_block_candidates() -> None:
    result = extract_digital_text(
        BytesIO(
            _pdf_bytes(
                TextPlacement("Left one", 72, 720),
                TextPlacement("Right one", 330, 720),
                TextPlacement("Left two", 72, 704),
                TextPlacement("Right two", 330, 704),
            )
        )
    )

    page = result.pages[0]
    assert [line.source_text for line in page.lines] == [
        "Left one",
        "Right one",
        "Left two",
        "Right two",
    ]
    assert {block.source_text for block in page.block_candidates} == {
        "Left one\nLeft two",
        "Right one\nRight two",
    }
    reading_order = resolve_reading_order(page)
    assert [
        page.block_candidates[index].source_text for index in reading_order.ordered_block_indexes
    ] == ["Left one\nLeft two", "Right one\nRight two"]
    assert reading_order.column_count == 2
    assert reading_order.warnings == ()


def test_heading_font_change_starts_a_new_block_candidate() -> None:
    result = extract_digital_text(
        BytesIO(
            _pdf_bytes(
                TextPlacement("Important Heading", 72, 720, size=20, font="F2"),
                TextPlacement("Paragraph body", 72, 686),
                TextPlacement("continues here", 72, 670),
            )
        )
    )

    blocks = result.pages[0].block_candidates
    assert [block.source_text for block in blocks] == [
        "Important Heading",
        "Paragraph body\ncontinues here",
    ]
    assert blocks[0].font_name == "Helvetica-Bold"
    assert blocks[0].font_size == pytest.approx(20)


def test_list_lines_remain_source_traceable_without_classification() -> None:
    result = extract_digital_text(
        BytesIO(
            _pdf_bytes(
                TextPlacement("- First item", 72, 720),
                TextPlacement("- Second item", 72, 704),
            )
        )
    )

    block = result.pages[0].block_candidates[0]
    assert block.source_text == "- First item\n- Second item"
    assert block.normalized_text == "- First item\n- Second item"
    assert [boundary.kind for boundary in block.normalization_boundaries] == [
        NormalizationKind.PRESERVED_LINE_BREAK
    ]
    assert not hasattr(block, "block_type")


def test_ligature_normalization_preserves_the_raw_boundary() -> None:
    result = normalize_source_lines(("A \ufb01le with an o\ufb03ce",))

    assert result.source_text == "A \ufb01le with an o\ufb03ce"
    assert result.text == "A file with an office"
    assert [boundary.kind for boundary in result.boundaries] == [
        NormalizationKind.LIGATURE,
        NormalizationKind.LIGATURE,
    ]
    assert [boundary.source_text for boundary in result.boundaries] == ["\ufb01", "\ufb03"]
    assert [boundary.normalized_text for boundary in result.boundaries] == ["fi", "ffi"]


def test_hyphenated_line_normalization_records_source_offsets() -> None:
    result = normalize_source_lines(("authenti-", "cation workflow"))

    assert result.source_text == "authenti-\ncation workflow"
    assert result.text == "authentication workflow"
    assert len(result.boundaries) == 1
    boundary = result.boundaries[0]
    assert boundary.kind is NormalizationKind.HYPHENATED_LINE_BREAK
    assert result.source_text[boundary.source_start : boundary.source_end] == "-\n"
    assert boundary.normalized_start == boundary.normalized_end == len("authenti")


def test_invalid_pdf_is_normalized_and_caller_stream_stays_open() -> None:
    stream = BytesIO(b"not a PDF")

    with pytest.raises(DigitalTextExtractionError, match="could not be extracted safely"):
        extract_digital_text(stream)

    assert stream.closed is False


def _pdf_bytes(*placements: TextPlacement) -> bytes:
    output = BytesIO()
    writer = PdfWriter()
    page = writer.add_blank_page(width=612, height=792)
    fonts = DictionaryObject(
        {
            NameObject("/F1"): writer._add_object(_font("Helvetica")),
            NameObject("/F2"): writer._add_object(_font("Helvetica-Bold")),
        }
    )
    page[NameObject("/Resources")] = DictionaryObject({NameObject("/Font"): fonts})
    content = DecodedStreamObject()
    operations = [
        (
            f"BT /{placement.font} {placement.size} Tf "
            f"1 0 0 1 {placement.x} {placement.y} Tm "
            f"({_escape_pdf_text(placement.text)}) Tj ET"
        )
        for placement in placements
    ]
    content.set_data("\n".join(operations).encode("latin-1"))
    page[NameObject("/Contents")] = writer._add_object(content)
    writer.write(output)
    return output.getvalue()


def _font(base_font: str) -> DictionaryObject:
    return DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject(f"/{base_font}"),
            NameObject("/Encoding"): NameObject("/WinAnsiEncoding"),
        }
    )


def _escape_pdf_text(value: str) -> str:
    return value.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
