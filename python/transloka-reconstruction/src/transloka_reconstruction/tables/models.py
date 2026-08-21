"""Immutable table values and layout results for simple reconstruction."""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from decimal import Decimal
from enum import StrEnum
from typing import Final, cast


class TableError(ValueError):
    """Base error for invalid simple-table input or layout."""


class TableStructureError(TableError):
    """Raised when a table cannot be safely represented as a simple grid."""


class CellAlignment(StrEnum):
    """Supported cell alignments."""

    LEFT = "LEFT"
    CENTER = "CENTER"
    RIGHT = "RIGHT"


class TableWarningCode(StrEnum):
    """Stable warning codes emitted by the reconstruction validator."""

    TABLE_CELL_MISSING = "TABLE_CELL_MISSING"
    TABLE_STRUCTURE_CORRUPTED = "TABLE_STRUCTURE_CORRUPTED"
    TABLE_NUMERIC_CHANGED = "TABLE_NUMERIC_CHANGED"
    TABLE_OVERFLOW = "TABLE_OVERFLOW"
    TABLE_CONTINUATION = "TABLE_CONTINUATION"


class TableWarningSeverity(StrEnum):
    INFO = "INFO"
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


def _text(value: object, field_name: str) -> str:
    if type(value) is not str or not value.strip():
        raise TableError(f"{field_name} must be a non-empty string.")
    return value


def _finite(value: object, field_name: str, *, positive: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise TableError(f"{field_name} must be a finite number.")
    converted = float(value)
    if not math.isfinite(converted) or (positive and converted <= 0):
        qualifier = "positive " if positive else ""
        raise TableError(f"{field_name} must be a finite {qualifier}number.")
    return converted


def _coerce_alignment(value: CellAlignment | str | None) -> CellAlignment | None:
    if value is None or isinstance(value, CellAlignment):
        return value
    if type(value) is not str:
        raise TableError("alignment must be a known cell alignment or None.")
    try:
        return CellAlignment(value)
    except ValueError as exc:
        raise TableError("alignment must be a known cell alignment or None.") from exc


def _display_text(value: object) -> str:
    if value is None:
        return "0"
    if isinstance(value, str):
        return value.replace("\r\n", "\n").replace("\r", "\n")
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, float):
        if not math.isfinite(value):
            raise TableError("numeric cell values must be finite.")
        return repr(value)
    if isinstance(value, int) and not isinstance(value, bool):
        return str(value)
    if isinstance(value, bool):
        return "True" if value else "False"
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    if isinstance(value, list | tuple | dict | set):
        raise TableStructureError("nested cell values are outside simple-table scope.")
    return str(value)


_NUMERIC_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"(?<![\w])[-+]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?(?:[eE][-+]?\d+)?%?"
)


def numeric_signature(value: object) -> tuple[str, ...]:
    """Return canonical numeric tokens without changing displayed source text."""

    text = _display_text(value)
    tokens: list[str] = []
    for match in _NUMERIC_PATTERN.finditer(text):
        token = match.group(0).replace(",", "")
        suffix = "%" if token.endswith("%") else ""
        if suffix:
            token = token[:-1]
        try:
            numeric = Decimal(token)
        except Exception:
            continue
        tokens.append(f"{numeric.normalize()}%" if suffix else str(numeric.normalize()))
    return tuple(tokens)


@dataclass(frozen=True, slots=True)
class TableRect:
    """A finite positive table rectangle in PDF user space."""

    x: float
    y: float
    width: float
    height: float

    def __post_init__(self) -> None:
        object.__setattr__(self, "x", _finite(self.x, "x"))
        object.__setattr__(self, "y", _finite(self.y, "y"))
        object.__setattr__(self, "width", _finite(self.width, "width", positive=True))
        object.__setattr__(self, "height", _finite(self.height, "height", positive=True))

    @property
    def right(self) -> float:
        return self.x + self.width

    @property
    def top(self) -> float:
        return self.y + self.height


@dataclass(frozen=True, slots=True)
class TableCell:
    """One scalar cell value; ``None`` is retained until table normalization."""

    value: object
    alignment: CellAlignment | str | None = None
    cell_id: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "alignment", _coerce_alignment(self.alignment))
        if self.cell_id is not None:
            object.__setattr__(self, "cell_id", _text(self.cell_id, "cell_id"))
        _display_text(self.value)

    @property
    def text(self) -> str:
        return _display_text(self.value)

    @property
    def is_numeric(self) -> bool:
        return bool(numeric_signature(self.value))

    def effective_alignment(self) -> CellAlignment:
        alignment = cast(CellAlignment | None, self.alignment)
        if alignment is not None:
            return alignment
        return CellAlignment.RIGHT if self.is_numeric else CellAlignment.LEFT


@dataclass(frozen=True, slots=True)
class TableRow:
    """A row of scalar cells, optionally marked as a header row."""

    cells: tuple[TableCell, ...] = ()
    row_id: str | None = None
    is_header: bool = False

    def __post_init__(self) -> None:
        raw_cells = cast(tuple[object, ...], self.cells)
        normalized = tuple(
            cell if isinstance(cell, TableCell) else TableCell(cell) for cell in raw_cells
        )
        object.__setattr__(self, "cells", normalized)
        if self.row_id is not None:
            object.__setattr__(self, "row_id", _text(self.row_id, "row_id"))
        if type(self.is_header) is not bool:
            raise TableError("is_header must be a boolean.")

    @property
    def values(self) -> tuple[object, ...]:
        return tuple(cell.value for cell in self.cells)


@dataclass(frozen=True, slots=True)
class SimpleTable:
    """A normalized rectangular table suitable for deterministic reconstruction."""

    rows: tuple[TableRow | tuple[object, ...], ...] = ()
    table_id: str = "table-1"
    column_count: int | None = None
    header_row: bool | int | None = True
    missing_cells_filled: int = field(init=False, default=0)

    def __post_init__(self) -> None:
        object.__setattr__(self, "table_id", _text(self.table_id, "table_id"))
        if self.column_count is not None and (
            isinstance(self.column_count, bool)
            or not isinstance(self.column_count, int)
            or self.column_count < 0
        ):
            raise TableError("column_count must be a non-negative integer or None.")
        if self.header_row is not None and type(self.header_row) not in {bool, int}:
            raise TableError("header_row must be a boolean, row index, or None.")
        raw_rows: list[TableRow] = []
        for raw_row in cast(tuple[object, ...], self.rows):
            if isinstance(raw_row, TableRow):
                raw_rows.append(raw_row)
            elif isinstance(raw_row, tuple):
                raw_rows.append(TableRow(cast(tuple[TableCell, ...], raw_row)))
            else:
                raise TableStructureError("rows must contain TableRow or tuple values.")
        raw_rows_tuple = tuple(raw_rows)
        inferred_count = max((len(row.cells) for row in raw_rows_tuple), default=0)
        count = self.column_count if self.column_count is not None else inferred_count
        if inferred_count > count:
            raise TableStructureError("A row contains more cells than column_count.")
        if count == 0 and raw_rows_tuple:
            raise TableStructureError("A non-empty table must contain at least one column.")
        header_index: int | None
        if self.header_row is True:
            header_index = 0 if raw_rows_tuple else None
        elif self.header_row is False or self.header_row is None:
            header_index = None
        else:
            header_index = self.header_row
            if header_index < 0 or header_index >= len(raw_rows_tuple):
                raise TableStructureError("header_row index must refer to an existing row.")
        missing = 0
        normalized_rows: list[TableRow] = []
        for row_index, row in enumerate(raw_rows_tuple):
            missing += max(0, count - len(row.cells))
            cells: list[TableCell] = []
            for cell in row.cells:
                if cell.value is None:
                    missing += 1
                    cells.append(TableCell(0, alignment=cell.alignment, cell_id=cell.cell_id))
                else:
                    cells.append(cell)
            cells.extend(TableCell(0) for _ in range(count - len(cells)))
            normalized_rows.append(
                TableRow(
                    tuple(cells),
                    row_id=row.row_id,
                    is_header=row.is_header or row_index == header_index,
                )
            )
        object.__setattr__(self, "rows", tuple(normalized_rows))
        object.__setattr__(self, "column_count", count)
        object.__setattr__(self, "missing_cells_filled", missing)

    @property
    def row_count(self) -> int:
        return len(self.rows)

    @property
    def header_rows(self) -> tuple[TableRow, ...]:
        rows = cast(tuple[TableRow, ...], self.rows)
        return tuple(row for row in rows if row.is_header)

    @property
    def normalized_rows(self) -> tuple[TableRow, ...]:
        return cast(tuple[TableRow, ...], self.rows)

    @property
    def values(self) -> tuple[tuple[object, ...], ...]:
        return tuple(row.values for row in self.normalized_rows)


@dataclass(frozen=True, slots=True)
class TableWarning:
    """One auditable table reconstruction warning."""

    code: TableWarningCode
    message: str
    severity: TableWarningSeverity
    row_index: int | None = None
    column_index: int | None = None


@dataclass(frozen=True, slots=True)
class TableLayoutCell:
    """One positioned cell after wrapping and row expansion."""

    row_index: int
    column_index: int
    value: object
    text: str
    lines: tuple[str, ...]
    rect: TableRect
    alignment: CellAlignment
    is_header: bool
    is_repeated_header: bool = False


@dataclass(frozen=True, slots=True)
class TableLayoutRow:
    """One positioned row; rows are never split across pages."""

    row_index: int
    cells: tuple[TableLayoutCell, ...]
    rect: TableRect
    is_header: bool
    is_repeated_header: bool = False

    @property
    def height(self) -> float:
        return self.rect.height


@dataclass(frozen=True, slots=True)
class TablePage:
    """One page fragment with repeated headers when it is a continuation."""

    page_number: int
    table_id: str
    bounds: TableRect
    rows: tuple[TableLayoutRow, ...]
    is_continuation: bool = False
    continuation_label: str | None = None

    @property
    def header_rows(self) -> tuple[TableLayoutRow, ...]:
        return tuple(row for row in self.rows if row.is_header)

    @property
    def height(self) -> float:
        return sum(row.height for row in self.rows)


@dataclass(frozen=True, slots=True)
class TableValidation:
    """Integrity facts used by the reconstruction/export gate."""

    row_count: int
    column_count: int
    header_present: bool
    missing_cells_filled: int
    numeric_integrity: bool
    overflow_cells: int
    continuation: bool
    warnings: tuple[TableWarning, ...]

    @property
    def valid(self) -> bool:
        return self.numeric_integrity and not any(
            warning.severity is TableWarningSeverity.CRITICAL for warning in self.warnings
        )


@dataclass(frozen=True, slots=True)
class TableReconstructionResult:
    """Complete normalized table, page fragments, and validation evidence."""

    table: SimpleTable
    pages: tuple[TablePage, ...]
    warnings: tuple[TableWarning, ...]
    validation: TableValidation

    @property
    def table_id(self) -> str:
        return self.table.table_id

    @property
    def row_count(self) -> int:
        return self.table.row_count

    @property
    def column_count(self) -> int:
        return self.table.column_count or 0

    @property
    def normalized_rows(self) -> tuple[TableRow, ...]:
        return self.table.normalized_rows
