from io import BytesIO

from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject
from transloka_documents.tables import (
    TableBorderStyle,
    TableCellRole,
    TableComplexity,
    TableFallback,
    extract_simple_tables,
)


def test_extracts_grid_table_rows_columns_geometry_and_header_candidate() -> None:
    stream = BytesIO(
        _table_pdf(
            (
                ("Name", "Qty", "Price"),
                ("Alpha", "2", "10"),
                ("Beta", "3", "12"),
            ),
            borders=True,
        )
    )
    stream.seek(7)

    result = extract_simple_tables(stream)

    assert stream.tell() == 7
    assert len(result.tables) == 1
    table = result.tables[0]
    assert (table.row_count, table.column_count) == (3, 3)
    assert table.border_style is TableBorderStyle.VISIBLE
    assert table.complexity is TableComplexity.SIMPLE
    assert table.has_header_row_candidate is True
    assert table.is_reconstructable is True
    assert len(table.cells) == 9
    assert [cell.source_text for cell in table.cells[:3]] == ["Name", "Qty", "Price"]
    assert all(cell.cell_role is TableCellRole.HEADER for cell in table.cells[:3])
    assert table.source_geometry.x >= 0
    assert table.source_geometry.y >= 0
    assert table.source_geometry.x + table.source_geometry.width <= 500
    assert table.source_geometry.y + table.source_geometry.height <= 500


def test_extracts_borderless_table_from_aligned_text() -> None:
    result = extract_simple_tables(
        BytesIO(
            _table_pdf(
                (
                    ("Item", "Count", "Cost"),
                    ("Paper", "4", "20"),
                    ("Ink", "2", "15"),
                ),
                borders=False,
            )
        )
    )

    assert len(result.tables) == 1
    table = result.tables[0]
    assert table.border_style is TableBorderStyle.NONE
    assert table.complexity is TableComplexity.SIMPLE
    assert (table.row_count, table.column_count) == (3, 3)
    assert [cell.source_text for cell in table.cells] == [
        "Item",
        "Count",
        "Cost",
        "Paper",
        "4",
        "20",
        "Ink",
        "2",
        "15",
    ]


def test_extracts_limited_merged_cell_without_losing_grid_positions() -> None:
    result = extract_simple_tables(
        BytesIO(
            _table_pdf(
                (
                    ("Quarterly Results", "", "Total"),
                    ("North", "5", "10"),
                    ("South", "7", "12"),
                ),
                borders=True,
                merged_header_span=2,
            )
        )
    )

    table = result.tables[0]
    assert table.complexity is TableComplexity.MODERATE
    assert table.is_reconstructable is True
    assert len(table.cells) == 8
    merged = table.cells[0]
    assert (merged.row_index, merged.column_index) == (0, 0)
    assert (merged.row_span, merged.column_span) == (1, 2)
    assert merged.source_text == "Quarterly Results"


def test_complex_table_falls_back_without_forced_cell_reconstruction() -> None:
    headers = tuple(f"C{index}" for index in range(1, 10))
    values = tuple(str(index) for index in range(1, 10))
    result = extract_simple_tables(BytesIO(_table_pdf((headers, values), borders=True)))

    table = result.tables[0]
    assert table.complexity is TableComplexity.COMPLEX
    assert table.fallback is TableFallback.PRESERVE_AS_IMAGE
    assert table.is_reconstructable is False
    assert (table.row_count, table.column_count) == (2, 9)
    assert table.cells == ()


def test_unrecognized_table_uses_unknown_fallback() -> None:
    result = extract_simple_tables(BytesIO(_table_pdf((("Name", "Qty", "Price"),), borders=True)))

    table = result.tables[0]
    assert table.complexity is TableComplexity.UNRECOGNIZED
    assert table.fallback is TableFallback.UNKNOWN
    assert table.is_reconstructable is False
    assert table.cells == ()


def _table_pdf(
    rows: tuple[tuple[str, ...], ...],
    *,
    borders: bool,
    merged_header_span: int = 1,
) -> bytes:
    column_count = len(rows[0])
    assert all(len(row) == column_count for row in rows)
    cell_width = 45
    cell_height = 40
    left = 40
    top = 420
    bottom = top - len(rows) * cell_height
    right = left + column_count * cell_width
    operations: list[str] = []
    if borders:
        for column in range(column_count + 1):
            x = left + column * cell_width
            line_top = top - cell_height if 0 < column < merged_header_span else top
            operations.append(f"{x} {bottom} m {x} {line_top} l S")
        for boundary_row in range(len(rows) + 1):
            y = top - boundary_row * cell_height
            operations.append(f"{left} {y} m {right} {y} l S")
    for row_index, row in enumerate(rows):
        for column_index, text in enumerate(row):
            if not text:
                continue
            x = left + column_index * cell_width + 5
            y = top - row_index * cell_height - 25
            operations.append(f"BT /F1 9 Tf 1 0 0 1 {x} {y} Tm ({text}) Tj ET")

    writer = PdfWriter()
    page = writer.add_blank_page(width=500, height=500)
    font = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
            NameObject("/Encoding"): NameObject("/WinAnsiEncoding"),
        }
    )
    page[NameObject("/Resources")] = DictionaryObject(
        {NameObject("/Font"): DictionaryObject({NameObject("/F1"): writer._add_object(font)})}
    )
    content = DecodedStreamObject()
    content.set_data("\n".join(operations).encode("latin-1"))
    page[NameObject("/Contents")] = writer._add_object(content)
    output = BytesIO()
    writer.write(output)
    return output.getvalue()
