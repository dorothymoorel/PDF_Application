import math
import re
from dataclasses import dataclass
from enum import StrEnum
from io import BufferedReader, BytesIO
from typing import BinaryIO, cast
from uuid import NAMESPACE_URL, uuid5

import pdfplumber
from pdfplumber.table import Table

from transloka_documents.extraction.models import TextGeometry

_TEXT_TABLE_SETTINGS: dict[str, object] = {
    "vertical_strategy": "text",
    "horizontal_strategy": "text",
    "min_words_vertical": 2,
    "min_words_horizontal": 1,
}
_MAX_SIMPLE_COLUMNS = 8
_MAX_RECONSTRUCTABLE_ROWS = 50
_MAX_LIMITED_MERGES = 4
_COORDINATE_TOLERANCE = 0.01
_NUMBER = re.compile(r"^[\s$+-]*\d[\d\s.,%:/-]*$")

type BoundingBox = tuple[float, float, float, float]
type CandidateCell = tuple[BoundingBox | None, str | None]
type CandidateRow = tuple[CandidateCell, ...]


class TableComplexity(StrEnum):
    SIMPLE = "SIMPLE"
    MODERATE = "MODERATE"
    COMPLEX = "COMPLEX"
    UNRECOGNIZED = "UNRECOGNIZED"


class TableBorderStyle(StrEnum):
    VISIBLE = "VISIBLE"
    NONE = "NONE"


class TableCellRole(StrEnum):
    HEADER = "HEADER"
    DATA = "DATA"


class TableFallback(StrEnum):
    PRESERVE_AS_IMAGE = "PRESERVE_AS_IMAGE"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True, slots=True)
class ExtractedTableCell:
    cell_id: str
    table_id: str
    row_index: int
    column_index: int
    row_span: int
    column_span: int
    source_text: str
    source_geometry: TextGeometry
    cell_role: TableCellRole
    is_header_candidate: bool


@dataclass(frozen=True, slots=True)
class ExtractedTable:
    table_id: str
    page_number: int
    source_geometry: TextGeometry
    row_count: int
    column_count: int
    has_header_row_candidate: bool
    border_style: TableBorderStyle
    complexity: TableComplexity
    cells: tuple[ExtractedTableCell, ...]
    confidence: float
    fallback: TableFallback | None

    @property
    def is_reconstructable(self) -> bool:
        return self.fallback is None


@dataclass(frozen=True, slots=True)
class TableExtractionResult:
    tables: tuple[ExtractedTable, ...]


class TableExtractionError(RuntimeError):
    pass


def extract_simple_tables(stream: BinaryIO) -> TableExtractionResult:
    try:
        original_position = stream.tell()
        stream.seek(0)
        typed_stream = cast(BufferedReader | BytesIO, stream)
        extracted: list[ExtractedTable] = []
        with pdfplumber.open(typed_stream) as document:
            for page_number, page in enumerate(document.pages, start=1):
                page_width = _positive_number(page.width, "page width")
                page_height = _positive_number(page.height, "page height")
                candidates = _table_candidates(page)
                extracted.extend(
                    _extract_table(
                        candidate,
                        border_style=border_style,
                        page_number=page_number,
                        page_width=page_width,
                        page_height=page_height,
                    )
                    for candidate, border_style in candidates
                )
        return TableExtractionResult(tables=tuple(extracted))
    except TableExtractionError:
        raise
    except Exception as exc:
        raise TableExtractionError("PDF tables could not be extracted safely.") from exc
    finally:
        try:
            stream.seek(original_position)
        except (NameError, OSError, ValueError):
            pass


def _table_candidates(page: pdfplumber.page.Page) -> tuple[tuple[Table, TableBorderStyle], ...]:
    bordered = tuple(page.find_tables())
    borderless = tuple(
        table
        for table in page.find_tables(_TEXT_TABLE_SETTINGS)
        if not any(_substantially_overlaps(table.bbox, candidate.bbox) for candidate in bordered)
    )
    return tuple((table, TableBorderStyle.VISIBLE) for table in bordered) + tuple(
        (table, TableBorderStyle.NONE) for table in borderless
    )


def _extract_table(
    table: Table,
    *,
    border_style: TableBorderStyle,
    page_number: int,
    page_width: float,
    page_height: float,
) -> ExtractedTable:
    geometry = _geometry(table.bbox, page_width, page_height)
    rows = _candidate_rows(table, border_style)
    row_count = len(rows)
    column_count = max((len(row) for row in rows), default=0)
    table_identity = uuid5(
        NAMESPACE_URL,
        f"{page_number}:{geometry.x}:{geometry.y}:{geometry.width}:{geometry.height}:"
        f"{border_style.value}",
    )
    table_id = f"tbl_{table_identity}"
    header_candidate = _has_header_candidate(rows)
    cells, structure_is_safe = _extract_cells(
        rows,
        table_id=table_id,
        border_style=border_style,
        page_width=page_width,
        page_height=page_height,
        header_candidate=header_candidate,
    )
    complexity = _classify_complexity(
        row_count,
        column_count,
        cells,
        structure_is_safe=structure_is_safe,
    )
    fallback = _fallback_for(complexity)
    if fallback is not None:
        cells = ()
    return ExtractedTable(
        table_id=table_id,
        page_number=page_number,
        source_geometry=geometry,
        row_count=row_count,
        column_count=column_count,
        has_header_row_candidate=header_candidate,
        border_style=border_style,
        complexity=complexity,
        cells=cells,
        confidence=_confidence(complexity, border_style),
        fallback=fallback,
    )


def _candidate_rows(table: Table, border_style: TableBorderStyle) -> tuple[CandidateRow, ...]:
    raw_rows = table.rows
    extracted_rows = table.extract()
    if len(raw_rows) != len(extracted_rows):
        raise TableExtractionError("Table geometry and text rows are inconsistent.")
    rows: list[CandidateRow] = []
    for raw_row, text_row in zip(raw_rows, extracted_rows, strict=True):
        if len(raw_row.cells) != len(text_row):
            raise TableExtractionError("Table geometry and text columns are inconsistent.")
        row = tuple(
            (_optional_bbox(raw_cell), _optional_text(text))
            for raw_cell, text in zip(raw_row.cells, text_row, strict=True)
        )
        if border_style is TableBorderStyle.NONE and not any(
            text for _cell, text in row if text is not None
        ):
            continue
        rows.append(row)
    return tuple(rows)


def _extract_cells(
    rows: tuple[CandidateRow, ...],
    *,
    table_id: str,
    border_style: TableBorderStyle,
    page_width: float,
    page_height: float,
    header_candidate: bool,
) -> tuple[tuple[ExtractedTableCell, ...], bool]:
    row_count = len(rows)
    column_count = max((len(row) for row in rows), default=0)
    if row_count == 0 or column_count == 0 or any(len(row) != column_count for row in rows):
        return (), False
    all_boxes = tuple(box for row in rows for box, _text in row if box is not None)
    column_starts = tuple(sorted({box[0] for box in all_boxes}))
    row_starts = tuple(sorted({box[1] for box in all_boxes}))
    cells: list[ExtractedTableCell] = []
    occupied: set[tuple[int, int]] = set()
    for row_index, row in enumerate(rows):
        for column_index, (box, text) in enumerate(row):
            if box is None:
                continue
            if border_style is TableBorderStyle.NONE:
                row_span = column_span = 1
            else:
                column_span = _span(box[0], box[2], column_starts)
                row_span = _span(box[1], box[3], row_starts)
            coverage = {
                (covered_row, covered_column)
                for covered_row in range(row_index, row_index + row_span)
                for covered_column in range(column_index, column_index + column_span)
            }
            if (
                row_span < 1
                or column_span < 1
                or row_index + row_span > row_count
                or column_index + column_span > column_count
                or occupied.intersection(coverage)
            ):
                return (), False
            occupied.update(coverage)
            identity = uuid5(NAMESPACE_URL, f"{table_id}:{row_index}:{column_index}")
            is_header = header_candidate and row_index == 0
            cells.append(
                ExtractedTableCell(
                    cell_id=f"cel_{identity}",
                    table_id=table_id,
                    row_index=row_index,
                    column_index=column_index,
                    row_span=row_span,
                    column_span=column_span,
                    source_text=text or "",
                    source_geometry=_geometry(box, page_width, page_height),
                    cell_role=TableCellRole.HEADER if is_header else TableCellRole.DATA,
                    is_header_candidate=is_header,
                )
            )
    return tuple(cells), len(occupied) == row_count * column_count


def _classify_complexity(
    row_count: int,
    column_count: int,
    cells: tuple[ExtractedTableCell, ...],
    *,
    structure_is_safe: bool,
) -> TableComplexity:
    if row_count < 2 or column_count < 2 or not structure_is_safe:
        return TableComplexity.UNRECOGNIZED
    merged = tuple(cell for cell in cells if cell.row_span > 1 or cell.column_span > 1)
    if (
        row_count > _MAX_RECONSTRUCTABLE_ROWS
        or column_count > _MAX_SIMPLE_COLUMNS
        or len(merged) > _MAX_LIMITED_MERGES
        or any(cell.row_span > 2 or cell.column_span > 2 for cell in merged)
    ):
        return TableComplexity.COMPLEX
    return TableComplexity.MODERATE if merged else TableComplexity.SIMPLE


def _fallback_for(complexity: TableComplexity) -> TableFallback | None:
    if complexity is TableComplexity.COMPLEX:
        return TableFallback.PRESERVE_AS_IMAGE
    if complexity is TableComplexity.UNRECOGNIZED:
        return TableFallback.UNKNOWN
    return None


def _confidence(complexity: TableComplexity, border_style: TableBorderStyle) -> float:
    if complexity is TableComplexity.UNRECOGNIZED:
        return 0.0
    if complexity is TableComplexity.COMPLEX:
        return 0.5
    if complexity is TableComplexity.MODERATE:
        return 0.8
    return 0.95 if border_style is TableBorderStyle.VISIBLE else 0.8


def _has_header_candidate(rows: tuple[CandidateRow, ...]) -> bool:
    if len(rows) < 2:
        return False
    first = tuple(text.strip() for _box, text in rows[0] if text is not None)
    later = tuple(text.strip() for row in rows[1:] for _box, text in row if text is not None)
    return bool(
        len(first) >= 2
        and all(first)
        and not any(_NUMBER.fullmatch(value) for value in first)
        and any(_NUMBER.fullmatch(value) for value in later)
    )


def _span(start: float, end: float, starts: tuple[float, ...]) -> int:
    return sum(
        start - _COORDINATE_TOLERANCE <= candidate < end - _COORDINATE_TOLERANCE
        for candidate in starts
    )


def _substantially_overlaps(first: object, second: object) -> bool:
    first_box = _required_bbox(first)
    second_box = _required_bbox(second)
    intersection_width = max(
        0.0, min(first_box[2], second_box[2]) - max(first_box[0], second_box[0])
    )
    intersection_height = max(
        0.0, min(first_box[3], second_box[3]) - max(first_box[1], second_box[1])
    )
    intersection = intersection_width * intersection_height
    smaller_area = min(_area(first_box), _area(second_box))
    return smaller_area > 0 and intersection / smaller_area >= 0.8


def _area(box: BoundingBox) -> float:
    return (box[2] - box[0]) * (box[3] - box[1])


def _geometry(box: object, page_width: float, page_height: float) -> TextGeometry:
    x0, top, x1, bottom = _required_bbox(box)
    if (
        x1 <= x0
        or bottom <= top
        or x0 < -_COORDINATE_TOLERANCE
        or top < -_COORDINATE_TOLERANCE
        or x1 > page_width + _COORDINATE_TOLERANCE
        or bottom > page_height + _COORDINATE_TOLERANCE
    ):
        raise TableExtractionError("Table geometry must remain within the PDF page.")
    safe_x0 = max(0.0, x0)
    safe_top = max(0.0, top)
    return TextGeometry(
        x=safe_x0,
        y=safe_top,
        width=min(page_width, x1) - safe_x0,
        height=min(page_height, bottom) - safe_top,
    )


def _optional_bbox(value: object) -> BoundingBox | None:
    return None if value is None else _required_bbox(value)


def _required_bbox(value: object) -> BoundingBox:
    if not isinstance(value, tuple | list) or len(value) != 4:
        raise TableExtractionError("Table geometry is invalid.")
    coordinates = tuple(_finite_number(item, "table coordinate") for item in value)
    return coordinates[0], coordinates[1], coordinates[2], coordinates[3]


def _optional_text(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise TableExtractionError("Table cell text is invalid.")
    return value.strip()


def _positive_number(value: object, name: str) -> float:
    number = _finite_number(value, name)
    if number <= 0:
        raise TableExtractionError(f"The PDF {name} must be positive.")
    return number


def _finite_number(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise TableExtractionError(f"The PDF {name} is invalid.")
    number = float(value)
    if not math.isfinite(number):
        raise TableExtractionError(f"The PDF {name} is invalid.")
    return number
