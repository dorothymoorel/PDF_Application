from __future__ import annotations

import math
import re
from collections.abc import Sequence
from dataclasses import dataclass
from enum import StrEnum
from uuid import NAMESPACE_URL, uuid5

from .base import OCRGeometry, OCRResult, OCRTextBlock
from .normalization import OCRNormalizationResult

_NUMBER = re.compile(r"^[\s$+-]*\d[\d\s.,%:/-]*$")
_COORDINATE_TOLERANCE = 0.01


class OCRTableComplexity(StrEnum):
    SIMPLE = "SIMPLE"
    COMPLEX = "COMPLEX"
    UNRECOGNIZED = "UNRECOGNIZED"


class OCRTableFallback(StrEnum):
    PRESERVE_AS_IMAGE = "PRESERVE_AS_IMAGE"
    UNKNOWN = "UNKNOWN"


class OCRTableBorderStyle(StrEnum):
    UNKNOWN = "UNKNOWN"
    NONE = "NONE"


@dataclass(frozen=True, slots=True)
class OCRTableMappingSettings:
    """Safety limits for mapping OCR boxes into an editable grid."""

    row_vertical_overlap_ratio: float = 0.35
    column_x_tolerance_ratio: float = 1.5
    max_columns: int = 8
    max_rows: int = 50

    def __post_init__(self) -> None:
        if (
            not math.isfinite(self.row_vertical_overlap_ratio)
            or not 0.0 < self.row_vertical_overlap_ratio <= 1.0
        ):
            raise ValueError("row_vertical_overlap_ratio must be between 0 and 1.")
        if not math.isfinite(self.column_x_tolerance_ratio) or self.column_x_tolerance_ratio <= 0:
            raise ValueError("column_x_tolerance_ratio must be greater than zero.")
        if self.max_columns < 2 or self.max_rows < 2:
            raise ValueError("OCR table limits must allow at least two rows and columns.")


@dataclass(frozen=True, slots=True)
class OCRTableCell:
    cell_id: str
    table_id: str
    row_index: int
    column_index: int
    text: str
    geometry: OCRGeometry
    confidence: float
    row_span: int = 1
    column_span: int = 1

    @property
    def source_text(self) -> str:
        return self.text

    @property
    def source_geometry(self) -> OCRGeometry:
        return self.geometry


@dataclass(frozen=True, slots=True)
class OCRTable:
    table_id: str
    page_number: int
    geometry: OCRGeometry
    row_count: int
    column_count: int
    cells: tuple[OCRTableCell, ...]
    complexity: OCRTableComplexity
    confidence: float
    fallback: OCRTableFallback | None
    has_header_row_candidate: bool
    border_style: OCRTableBorderStyle = OCRTableBorderStyle.UNKNOWN

    @property
    def source_geometry(self) -> OCRGeometry:
        return self.geometry

    @property
    def is_reconstructable(self) -> bool:
        return self.fallback is None


@dataclass(frozen=True, slots=True)
class OCRTableMappingResult:
    page_number: int
    tables: tuple[OCRTable, ...]
    confidence: float
    warnings: tuple[str, ...] = ()

    @property
    def table(self) -> OCRTable | None:
        return self.tables[0] if self.tables else None


class OCRTableMappingError(ValueError):
    """Raised when OCR table input cannot be safely interpreted."""


OCRTableSource = OCRResult | OCRNormalizationResult | Sequence[OCRTextBlock]


def map_ocr_tables(
    source: OCRTableSource,
    *,
    page_number: int | None = None,
    settings: OCRTableMappingSettings | None = None,
) -> OCRTableMappingResult:
    """Map one OCR table candidate into a safe rectangular grid.

    OCR providers do not expose reliable border information for every page, so
    the mapper uses text-box alignment instead. It emits cells only when every
    row resolves to the same number of columns. Otherwise the candidate is
    retained with an explicit fallback and no reconstructed cells.
    """

    normalized_settings = settings or OCRTableMappingSettings()
    effective_page_number, blocks = _source_parts(source, page_number)
    usable_blocks = tuple(block for block in blocks if block.text.strip())
    if not usable_blocks:
        return OCRTableMappingResult(
            page_number=effective_page_number,
            tables=(),
            confidence=0.0,
            warnings=("NO_TABLE_CANDIDATE",),
        )

    candidate = _map_candidate(usable_blocks, effective_page_number, normalized_settings)
    warning = (
        "COMPLEX_TABLE_FALLBACK"
        if candidate.complexity is OCRTableComplexity.COMPLEX
        else "UNRECOGNIZED_TABLE"
        if candidate.complexity is OCRTableComplexity.UNRECOGNIZED
        else None
    )
    return OCRTableMappingResult(
        page_number=effective_page_number,
        tables=(candidate,),
        confidence=candidate.confidence,
        warnings=() if warning is None else (warning,),
    )


def map_ocr_table(
    source: OCRTableSource,
    *,
    page_number: int | None = None,
    settings: OCRTableMappingSettings | None = None,
) -> OCRTableMappingResult:
    """Singular alias for :func:`map_ocr_tables`."""

    return map_ocr_tables(source, page_number=page_number, settings=settings)


def _source_parts(
    source: OCRTableSource,
    page_number: int | None,
) -> tuple[int, Sequence[OCRTextBlock]]:
    if isinstance(source, OCRResult):
        return source.page_number if page_number is None else page_number, source.blocks
    if isinstance(source, OCRNormalizationResult):
        result = source.raw_result
        return result.page_number if page_number is None else page_number, result.blocks
    if page_number is None or page_number < 1:
        raise OCRTableMappingError("page_number is required for a sequence of OCR blocks.")
    return page_number, source


def _map_candidate(
    blocks: Sequence[OCRTextBlock],
    page_number: int,
    settings: OCRTableMappingSettings,
) -> OCRTable:
    rows = _group_rows(blocks, settings)
    geometry = _union_geometry(tuple(block.geometry for block in blocks))
    table_identity = uuid5(
        NAMESPACE_URL,
        f"ocr-table:{page_number}:{_geometry_key(geometry)}:{len(blocks)}",
    )
    table_id = f"tbl_{table_identity}"
    row_count = len(rows)
    column_positions = _column_positions(rows, settings)
    column_count = len(column_positions)
    average_confidence = _average_confidence(blocks)

    if row_count < 2 or column_count < 2:
        return _fallback_table(
            table_id,
            page_number,
            geometry,
            row_count,
            column_count,
            OCRTableComplexity.UNRECOGNIZED,
            average_confidence=0.0,
        )
    if row_count > settings.max_rows or column_count > settings.max_columns:
        return _fallback_table(
            table_id,
            page_number,
            geometry,
            row_count,
            column_count,
            OCRTableComplexity.COMPLEX,
            average_confidence=min(0.5, average_confidence),
        )

    assignments = _assign_cells(rows, column_positions, settings)
    if assignments is None:
        return _fallback_table(
            table_id,
            page_number,
            geometry,
            row_count,
            column_count,
            OCRTableComplexity.COMPLEX,
            average_confidence=min(0.5, average_confidence),
        )

    cells = tuple(
        OCRTableCell(
            cell_id=f"cel_{uuid5(NAMESPACE_URL, f'{table_id}:{row_index}:{column_index}')}",
            table_id=table_id,
            row_index=row_index,
            column_index=column_index,
            text=block.text.strip(),
            geometry=block.geometry,
            confidence=block.confidence,
        )
        for row_index, row in enumerate(assignments)
        for column_index, block in enumerate(row)
    )
    return OCRTable(
        table_id=table_id,
        page_number=page_number,
        geometry=geometry,
        row_count=row_count,
        column_count=column_count,
        cells=cells,
        complexity=OCRTableComplexity.SIMPLE,
        confidence=average_confidence,
        fallback=None,
        has_header_row_candidate=_has_header_candidate(assignments),
        border_style=OCRTableBorderStyle.NONE,
    )


def _fallback_table(
    table_id: str,
    page_number: int,
    geometry: OCRGeometry,
    row_count: int,
    column_count: int,
    complexity: OCRTableComplexity,
    *,
    average_confidence: float,
) -> OCRTable:
    fallback = (
        OCRTableFallback.PRESERVE_AS_IMAGE
        if complexity is OCRTableComplexity.COMPLEX
        else OCRTableFallback.UNKNOWN
    )
    return OCRTable(
        table_id=table_id,
        page_number=page_number,
        geometry=geometry,
        row_count=row_count,
        column_count=column_count,
        cells=(),
        complexity=complexity,
        confidence=average_confidence,
        fallback=fallback,
        has_header_row_candidate=False,
        border_style=OCRTableBorderStyle.UNKNOWN,
    )


def _group_rows(
    blocks: Sequence[OCRTextBlock],
    settings: OCRTableMappingSettings,
) -> tuple[tuple[OCRTextBlock, ...], ...]:
    groups: list[list[OCRTextBlock]] = []
    for block in sorted(blocks, key=lambda item: (item.geometry.y, item.geometry.x)):
        matching = [
            index
            for index, group in enumerate(groups)
            if any(_same_row(block.geometry, candidate.geometry, settings) for candidate in group)
        ]
        if not matching:
            groups.append([block])
            continue
        first = matching[0]
        groups[first].append(block)
        for index in reversed(matching[1:]):
            groups[first].extend(groups.pop(index))
    return tuple(
        tuple(sorted(group, key=lambda item: item.geometry.x))
        for group in sorted(groups, key=lambda group: min(item.geometry.y for item in group))
    )


def _same_row(
    first: OCRGeometry,
    second: OCRGeometry,
    settings: OCRTableMappingSettings,
) -> bool:
    top = max(first.y, second.y)
    bottom = min(_bottom(first), _bottom(second))
    overlap = max(0.0, bottom - top)
    minimum_height = min(first.height, second.height)
    if minimum_height <= 0:
        return False
    overlap_ratio = overlap / minimum_height
    center_distance = abs(_center_y(first) - _center_y(second))
    return overlap_ratio >= settings.row_vertical_overlap_ratio or center_distance <= (
        max(first.height, second.height) * 0.5
    )


def _column_positions(
    rows: Sequence[Sequence[OCRTextBlock]],
    settings: OCRTableMappingSettings,
) -> tuple[float, ...]:
    blocks = [block for row in rows for block in row]
    if not blocks:
        return ()
    typical_height = _median(tuple(block.geometry.height for block in blocks))
    tolerance = max(_COORDINATE_TOLERANCE, typical_height * settings.column_x_tolerance_ratio)
    positions: list[float] = []
    counts: list[int] = []
    for block in sorted(blocks, key=lambda item: item.geometry.x):
        nearest = min(
            range(len(positions)),
            key=lambda index: abs(block.geometry.x - positions[index]),
            default=-1,
        )
        if nearest >= 0 and abs(block.geometry.x - positions[nearest]) <= tolerance:
            counts[nearest] += 1
            positions[nearest] += (block.geometry.x - positions[nearest]) / counts[nearest]
        else:
            positions.append(block.geometry.x)
            counts.append(1)
    return tuple(sorted(positions))


def _assign_cells(
    rows: Sequence[Sequence[OCRTextBlock]],
    positions: Sequence[float],
    settings: OCRTableMappingSettings,
) -> tuple[tuple[OCRTextBlock, ...], ...] | None:
    blocks = [block for row in rows for block in row]
    typical_height = _median(tuple(block.geometry.height for block in blocks))
    tolerance = max(_COORDINATE_TOLERANCE, typical_height * settings.column_x_tolerance_ratio)
    assigned_rows: list[tuple[OCRTextBlock, ...]] = []
    for row in rows:
        assigned: dict[int, OCRTextBlock] = {}
        for block in row:
            column_index = min(
                range(len(positions)),
                key=lambda index: abs(block.geometry.x - positions[index]),
            )
            if abs(block.geometry.x - positions[column_index]) > tolerance:
                return None
            if column_index in assigned:
                return None
            assigned[column_index] = block
        if len(assigned) != len(positions) or set(assigned) != set(range(len(positions))):
            return None
        assigned_rows.append(tuple(assigned[index] for index in range(len(positions))))
    return tuple(assigned_rows)


def _has_header_candidate(rows: Sequence[Sequence[OCRTextBlock]]) -> bool:
    if len(rows) < 2:
        return False
    first = tuple(block.text.strip() for block in rows[0])
    later = tuple(block.text.strip() for row in rows[1:] for block in row)
    return bool(
        all(first)
        and not any(_NUMBER.fullmatch(value) for value in first)
        and any(_NUMBER.fullmatch(value) for value in later)
    )


def _union_geometry(geometries: Sequence[OCRGeometry]) -> OCRGeometry:
    if not geometries:
        raise OCRTableMappingError("At least one OCR geometry is required.")
    coordinate_systems = {geometry.coordinate_system for geometry in geometries}
    if len(coordinate_systems) != 1:
        raise OCRTableMappingError("OCR table geometries must use one coordinate system.")
    x = min(geometry.x for geometry in geometries)
    y = min(geometry.y for geometry in geometries)
    right = max(geometry.x + geometry.width for geometry in geometries)
    bottom = max(geometry.y + geometry.height for geometry in geometries)
    return OCRGeometry(
        x=x,
        y=y,
        width=right - x,
        height=bottom - y,
        coordinate_system=next(iter(coordinate_systems)),
    )


def _average_confidence(blocks: Sequence[OCRTextBlock]) -> float:
    total_weight = sum(max(1, len(block.text.strip())) for block in blocks)
    if total_weight <= 0:
        return 0.0
    return (
        sum(max(1, len(block.text.strip())) * block.confidence for block in blocks) / total_weight
    )


def _geometry_key(geometry: OCRGeometry) -> str:
    return ":".join(
        f"{value:.3f}" for value in (geometry.x, geometry.y, geometry.width, geometry.height)
    )


def _median(values: Sequence[float]) -> float:
    ordered = sorted(values)
    middle = len(ordered) // 2
    if len(ordered) % 2:
        return ordered[middle]
    return (ordered[middle - 1] + ordered[middle]) / 2


def _bottom(geometry: OCRGeometry) -> float:
    return geometry.y + geometry.height


def _center_y(geometry: OCRGeometry) -> float:
    return geometry.y + geometry.height / 2


__all__ = [
    "OCRTable",
    "OCRTableBorderStyle",
    "OCRTableCell",
    "OCRTableComplexity",
    "OCRTableFallback",
    "OCRTableMappingError",
    "OCRTableMappingResult",
    "OCRTableMappingSettings",
    "map_ocr_table",
    "map_ocr_tables",
]
