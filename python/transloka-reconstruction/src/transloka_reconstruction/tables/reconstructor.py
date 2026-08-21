"""Deterministic wrapping, row expansion, numeric validation, and pagination."""

from __future__ import annotations

import math
import textwrap
from dataclasses import dataclass
from html import escape

from .models import (
    SimpleTable,
    TableError,
    TableLayoutCell,
    TableLayoutRow,
    TablePage,
    TableReconstructionResult,
    TableRect,
    TableRow,
    TableValidation,
    TableWarning,
    TableWarningCode,
    TableWarningSeverity,
    numeric_signature,
)


@dataclass(frozen=True, slots=True)
class TableLayoutSettings:
    """Stable layout controls for one table reconstruction run."""

    bounds: TableRect
    column_widths: tuple[float, ...] | None = None
    cell_padding_x: float = 4.0
    cell_padding_y: float = 3.0
    font_size_pt: float = 9.0
    line_height: float = 1.2
    characters_per_point: float = 0.5
    repeat_header: bool = True

    def __post_init__(self) -> None:
        for name in (
            "cell_padding_x",
            "cell_padding_y",
            "font_size_pt",
            "line_height",
            "characters_per_point",
        ):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, (int, float)):
                raise TableError(f"{name} must be a finite number.")
            converted = float(value)
            if not math.isfinite(converted) or converted <= 0:
                raise TableError(f"{name} must be a positive finite number.")
            object.__setattr__(self, name, converted)
        if type(self.repeat_header) is not bool:
            raise TableError("repeat_header must be a boolean.")
        if self.column_widths is not None:
            normalized = tuple(float(width) for width in self.column_widths)
            if not normalized or any(
                not math.isfinite(width) or width <= 0 for width in normalized
            ):
                raise TableError("column_widths must contain positive finite widths.")
            if sum(normalized) > self.bounds.width + 1e-9:
                raise TableError("column_widths must fit inside table bounds.")
            object.__setattr__(self, "column_widths", normalized)


class TableReconstructor:
    """Reconstruct a rectangular table without silently changing its cells."""

    def __init__(self, settings: TableLayoutSettings) -> None:
        self.settings = settings

    def reconstruct(
        self,
        table: SimpleTable,
        *,
        source_table: SimpleTable | None = None,
    ) -> TableReconstructionResult:
        widths = self._column_widths(table)
        warnings: list[TableWarning] = []
        if table.missing_cells_filled:
            warnings.append(
                TableWarning(
                    code=TableWarningCode.TABLE_CELL_MISSING,
                    message=(
                        f"{table.missing_cells_filled} missing cell(s) were normalized to numeric zero."
                    ),
                    severity=TableWarningSeverity.WARNING,
                )
            )

        numeric_ok = True
        if source_table is not None:
            numeric_ok = _numeric_integrity(source_table, table)
            if not numeric_ok:
                warnings.append(
                    TableWarning(
                        code=TableWarningCode.TABLE_NUMERIC_CHANGED,
                        message="A numeric token differs between source and reconstructed table.",
                        severity=TableWarningSeverity.CRITICAL,
                    )
                )

        row_specs: list[tuple[TableRow, float, tuple[tuple[str, ...], ...]]] = []
        overflow_cells = 0
        for row_index, row in enumerate(table.normalized_rows):
            wrapped_cells: list[tuple[str, ...]] = []
            row_height = self.settings.cell_padding_y * 2
            for column_index, cell in enumerate(row.cells):
                available = widths[column_index] - self.settings.cell_padding_x * 2
                max_chars = max(
                    1,
                    math.floor(
                        available
                        / (self.settings.font_size_pt * self.settings.characters_per_point)
                    ),
                )
                lines = _wrap_cell(cell.text, max_chars, numeric=cell.is_numeric)
                if cell.is_numeric and len(cell.text) > max_chars:
                    overflow_cells += 1
                    warnings.append(
                        TableWarning(
                            code=TableWarningCode.TABLE_OVERFLOW,
                            message="A numeric cell is wider than its column and was not split.",
                            severity=TableWarningSeverity.WARNING,
                            row_index=row_index,
                            column_index=column_index,
                        )
                    )
                wrapped_cells.append(lines)
                row_height = max(
                    row_height,
                    len(lines) * self.settings.font_size_pt * self.settings.line_height
                    + self.settings.cell_padding_y * 2,
                )
            row_specs.append((row, row_height, tuple(wrapped_cells)))

        pages = self._paginate(table, widths, row_specs, warnings)
        validation = TableValidation(
            row_count=table.row_count,
            column_count=table.column_count or 0,
            header_present=bool(table.header_rows),
            missing_cells_filled=table.missing_cells_filled,
            numeric_integrity=numeric_ok,
            overflow_cells=overflow_cells,
            continuation=len(pages) > 1,
            warnings=tuple(warnings),
        )
        return TableReconstructionResult(
            table=table,
            pages=tuple(pages),
            warnings=tuple(warnings),
            validation=validation,
        )

    def _column_widths(self, table: SimpleTable) -> tuple[float, ...]:
        count = table.column_count or 0
        if count == 0:
            return ()
        explicit = self.settings.column_widths
        if explicit is not None:
            if len(explicit) != count:
                raise TableError("column_widths length must equal table column_count.")
            return explicit
        width = self.settings.bounds.width / count
        return tuple(width for _ in range(count))

    def _paginate(
        self,
        table: SimpleTable,
        widths: tuple[float, ...],
        row_specs: list[tuple[TableRow, float, tuple[tuple[str, ...], ...]]],
        warnings: list[TableWarning],
    ) -> list[TablePage]:
        if not row_specs:
            return [
                TablePage(
                    page_number=1,
                    table_id=table.table_id,
                    bounds=TableRect(
                        self.settings.bounds.x,
                        self.settings.bounds.top,
                        self.settings.bounds.width,
                        0.01,
                    ),
                    rows=(),
                )
            ]
        header_specs = [spec for spec in row_specs if spec[0].is_header]
        pages: list[TablePage] = []
        row_index = 0
        page_number = 1
        while row_index < len(row_specs):
            continuation = page_number > 1
            cursor = self.settings.bounds.top
            remaining = self.settings.bounds.height
            page_rows: list[TableLayoutRow] = []
            if continuation and self.settings.repeat_header:
                for header, height, lines in header_specs:
                    if height > remaining and page_rows:
                        break
                    header_row_index = next(
                        index for index, spec in enumerate(row_specs) if spec[0] is header
                    )
                    page_rows.append(
                        self._layout_row(
                            header,
                            lines,
                            widths,
                            cursor - height,
                            height,
                            row_index=header_row_index,
                            repeated=True,
                        )
                    )
                    cursor -= height
                    remaining -= height
            start_index = row_index
            while row_index < len(row_specs):
                row, height, lines = row_specs[row_index]
                if height > remaining and page_rows:
                    break
                page_rows.append(
                    self._layout_row(
                        row,
                        lines,
                        widths,
                        cursor - height,
                        height,
                        row_index=row_index,
                        repeated=False,
                    )
                )
                cursor -= height
                remaining -= height
                row_index += 1
            if row_index == start_index:
                # A single row taller than a page is kept intact and reported;
                # silently splitting it would corrupt cell reading order.
                row, height, lines = row_specs[row_index]
                page_rows.append(
                    self._layout_row(
                        row,
                        lines,
                        widths,
                        cursor - height,
                        height,
                        row_index=row_index,
                        repeated=False,
                    )
                )
                cursor -= height
                row_index += 1
                warnings.append(
                    TableWarning(
                        code=TableWarningCode.TABLE_OVERFLOW,
                        message="A row exceeds the available page height and was kept intact.",
                        severity=TableWarningSeverity.WARNING,
                        row_index=row_index - 1,
                    )
                )
            used_height = max(0.01, self.settings.bounds.top - cursor)
            pages.append(
                TablePage(
                    page_number=page_number,
                    table_id=table.table_id,
                    bounds=TableRect(
                        self.settings.bounds.x,
                        self.settings.bounds.top - used_height,
                        self.settings.bounds.width,
                        used_height,
                    ),
                    rows=tuple(page_rows),
                    is_continuation=continuation,
                    continuation_label=f"{table.table_id} — continued" if continuation else None,
                )
            )
            if row_index < len(row_specs):
                warnings.append(
                    TableWarning(
                        code=TableWarningCode.TABLE_CONTINUATION,
                        message="Table continues on a later page with its header repeated.",
                        severity=TableWarningSeverity.INFO,
                    )
                )
            page_number += 1
        return pages

    @staticmethod
    def _layout_row(
        row: TableRow,
        lines: tuple[tuple[str, ...], ...],
        widths: tuple[float, ...],
        y: float,
        height: float,
        *,
        row_index: int,
        repeated: bool,
    ) -> TableLayoutRow:
        x = 0.0
        cells: list[TableLayoutCell] = []
        for column_index, (cell, cell_lines, width) in enumerate(
            zip(row.cells, lines, widths, strict=True)
        ):
            rect = TableRect(x, y, width, height)
            cells.append(
                TableLayoutCell(
                    row_index=row_index,
                    column_index=column_index,
                    value=cell.value,
                    text=cell.text,
                    lines=cell_lines,
                    rect=rect,
                    alignment=cell.effective_alignment(),
                    is_header=row.is_header,
                    is_repeated_header=repeated,
                )
            )
            x += width
        return TableLayoutRow(
            row_index=row_index,
            cells=tuple(cells),
            rect=TableRect(0.0, y, sum(widths), height),
            is_header=row.is_header,
            is_repeated_header=repeated,
        )


class SimpleTableReconstructor(TableReconstructor):
    """Descriptive alias for callers that prefer the task name."""


def _wrap_cell(text: str, width: int, *, numeric: bool) -> tuple[str, ...]:
    if numeric:
        return tuple(text.split("\n")) or ("",)
    lines: list[str] = []
    for source_line in text.split("\n"):
        wrapped = textwrap.wrap(
            source_line,
            width=width,
            break_long_words=True,
            break_on_hyphens=False,
            replace_whitespace=False,
            drop_whitespace=True,
        )
        lines.extend(wrapped or [""])
    return tuple(lines) or ("",)


def _numeric_integrity(source: SimpleTable, target: SimpleTable) -> bool:
    if source.row_count != target.row_count or source.column_count != target.column_count:
        return False
    return all(
        numeric_signature(source_row.cells[column].value)
        == numeric_signature(target_row.cells[column].value)
        for source_row, target_row in zip(
            source.normalized_rows, target.normalized_rows, strict=True
        )
        for column in range(source.column_count or 0)
    )


def reconstruct_simple_table(
    table: SimpleTable,
    *,
    bounds: TableRect,
    column_widths: tuple[float, ...] | None = None,
    source_table: SimpleTable | None = None,
    repeat_header: bool = True,
) -> TableReconstructionResult:
    """Convenience wrapper for one deterministic table reconstruction."""

    return TableReconstructor(
        TableLayoutSettings(
            bounds=bounds,
            column_widths=column_widths,
            repeat_header=repeat_header,
        )
    ).reconstruct(table, source_table=source_table)


def render_table_html(result: TableReconstructionResult) -> str:
    """Render safe, searchable HTML for all reconstructed table pages."""

    tables: list[str] = []
    for page in result.pages:
        header = [row for row in page.rows if row.is_header]
        body = [row for row in page.rows if not row.is_header]
        head_html = "".join(_render_row(row, "th") for row in header)
        body_html = "".join(_render_row(row, "td") for row in body)
        continuation = ' data-continuation="true"' if page.is_continuation else ""
        label = (
            f"<caption>{escape(page.continuation_label)}</caption>"
            if page.continuation_label
            else ""
        )
        tables.append(
            f'<table data-table-id="{escape(result.table_id)}" '
            f'data-page="{page.page_number}"{continuation}>'
            f"{label}<thead>{head_html}</thead><tbody>{body_html}</tbody></table>"
        )
    return "\n".join(tables)


def _render_row(row: TableLayoutRow, tag: str) -> str:
    cells: list[str] = []
    for cell in row.cells:
        text = "<br>".join(escape(line) for line in cell.lines)
        cells.append(f'<{tag} style="text-align:{cell.alignment.value.casefold()}">{text}</{tag}>')
    return "<tr>" + "".join(cells) + "</tr>"
