from __future__ import annotations

from decimal import Decimal

from transloka_reconstruction.tables import (
    SimpleTable,
    TableRect,
    TableWarningCode,
    reconstruct_simple_table,
    render_table_html,
)


def test_simple_table_preserves_rows_columns_and_header() -> None:
    table = SimpleTable(
        table_id="table-simple",
        rows=(("Term", "Count"), ("alpha", 2), ("beta", 3)),
    )

    result = reconstruct_simple_table(table, bounds=TableRect(0, 0, 240, 200))

    assert result.row_count == 3
    assert result.column_count == 2
    assert result.validation.header_present
    assert len(result.pages) == 1
    assert result.pages[0].rows[0].is_header
    assert result.pages[0].rows[1].cells[1].text == "2"


def test_missing_cells_are_normalized_to_zero_without_shifting_columns() -> None:
    table = SimpleTable(
        table_id="table-missing",
        rows=(("Name", "Count", "Score"), ("alpha", 2)),
    )

    result = reconstruct_simple_table(table, bounds=TableRect(0, 0, 240, 200))

    assert table.values == (("Name", "Count", "Score"), ("alpha", 2, 0))
    assert result.validation.missing_cells_filled == 1
    assert any(warning.code is TableWarningCode.TABLE_CELL_MISSING for warning in result.warnings)
    assert len(result.pages[0].rows[1].cells) == 3


def test_multiline_cell_wraps_and_expands_row_height() -> None:
    table = SimpleTable(
        table_id="table-multiline",
        rows=(
            ("Description", "Value"),
            ("This is a deliberately long cell that must wrap.", "ok"),
        ),
    )

    result = reconstruct_simple_table(
        table,
        bounds=TableRect(0, 0, 120, 200),
        column_widths=(60, 60),
    )
    header, body = result.pages[0].rows

    assert len(body.cells[0].lines) > 1
    assert body.height > header.height
    assert body.cells[0].rect.height == body.height


def test_small_page_repeats_header_and_marks_continuation() -> None:
    table = SimpleTable(
        table_id="table-pages",
        rows=(
            ("Item", "Value"),
            *(tuple((f"item-{index}", index)) for index in range(1, 9)),
        ),
    )

    result = reconstruct_simple_table(table, bounds=TableRect(0, 0, 160, 55))

    assert len(result.pages) >= 2
    assert result.validation.continuation
    continuation = result.pages[1]
    assert continuation.is_continuation
    assert continuation.header_rows
    assert continuation.header_rows[0].is_repeated_header
    assert continuation.header_rows[0].row_index == 0
    assert continuation.continuation_label == "table-pages — continued"


def test_rows_are_not_split_when_a_table_continues() -> None:
    table = SimpleTable(
        table_id="table-split",
        rows=(("A", "B"),) + tuple((f"row-{index}", "content") for index in range(12)),
    )

    result = reconstruct_simple_table(table, bounds=TableRect(0, 0, 160, 48))
    row_indices = [
        row.row_index for page in result.pages for row in page.rows if not row.is_repeated_header
    ]

    assert row_indices == list(range(table.row_count))


def test_numeric_integrity_is_validated_without_reformatting_values() -> None:
    source = SimpleTable(
        table_id="table-numbers",
        rows=(("Label", "Amount"), ("subtotal", "1,234.50"), ("rate", Decimal("0.25"))),
    )
    translated = SimpleTable(
        table_id="table-numbers",
        rows=(("Label ID", "Amount"), ("subtotal ID", "1,234.50"), ("rate ID", Decimal("0.25"))),
    )

    result = reconstruct_simple_table(
        translated,
        bounds=TableRect(0, 0, 240, 200),
        source_table=source,
    )

    assert result.validation.numeric_integrity
    assert result.normalized_rows[1].cells[1].value == "1,234.50"
    assert result.normalized_rows[2].cells[1].value == Decimal("0.25")


def test_changed_number_is_critical_and_html_is_escaped() -> None:
    source = SimpleTable(table_id="table-safe", rows=(("Label", "Amount"), ("A", 10)))
    translated = SimpleTable(table_id="table-safe", rows=(("Label", "Amount"), ("&lt;", 11)))

    result = reconstruct_simple_table(
        translated,
        bounds=TableRect(0, 0, 200, 200),
        source_table=source,
    )
    html = render_table_html(result)

    assert not result.validation.numeric_integrity
    assert any(
        warning.code is TableWarningCode.TABLE_NUMERIC_CHANGED
        and warning.severity.value == "CRITICAL"
        for warning in result.warnings
    )
    assert "&amp;lt;" in html
    assert 'data-table-id="table-safe"' in html
