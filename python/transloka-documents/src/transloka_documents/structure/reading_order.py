import math
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import Literal

from transloka_documents.extraction.models import ExtractedPage, TextBlockCandidate, TextGeometry

_HEADER_LIMIT_RATIO = 0.10
_FOOTER_START_RATIO = 0.90
_SPANNING_WIDTH_RATIO = 0.65
_COLUMN_OVERLAP_RATIO = 0.2
_BLOCK_OVERLAP_WARNING_RATIO = 0.25


class ReadingOrderRegion(StrEnum):
    HEADER = "HEADER"
    BODY = "BODY"
    FOOTER = "FOOTER"


class ReadingOrderUncertainty(StrEnum):
    OVERLAPPING_BLOCKS = "OVERLAPPING_BLOCKS"
    TOO_MANY_COLUMNS = "TOO_MANY_COLUMNS"
    INTERNAL_SPANNING_BLOCK = "INTERNAL_SPANNING_BLOCK"


@dataclass(frozen=True, slots=True)
class ReadingOrderWarning:
    code: Literal["READING_ORDER_UNCERTAIN"]
    reason: ReadingOrderUncertainty
    block_indexes: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class ReadingOrderAssignment:
    block_index: int
    page_reading_order: int
    region: ReadingOrderRegion
    column_index: int | None


@dataclass(frozen=True, slots=True)
class ReadingOrderResult:
    assignments: tuple[ReadingOrderAssignment, ...]
    column_count: int
    warnings: tuple[ReadingOrderWarning, ...]

    @property
    def ordered_block_indexes(self) -> tuple[int, ...]:
        return tuple(assignment.block_index for assignment in self.assignments)

    @property
    def is_certain(self) -> bool:
        return not self.warnings


def resolve_reading_order(page: ExtractedPage) -> ReadingOrderResult:
    _validate_page(page)
    indexed_blocks = tuple(enumerate(page.block_candidates))
    header: list[tuple[int, TextBlockCandidate]] = []
    body: list[tuple[int, TextBlockCandidate]] = []
    footer: list[tuple[int, TextBlockCandidate]] = []

    header_limit = page.height_points * _HEADER_LIMIT_RATIO
    footer_start = page.height_points * _FOOTER_START_RATIO
    for indexed_block in indexed_blocks:
        geometry = indexed_block[1].geometry
        if geometry.y + geometry.height <= header_limit:
            header.append(indexed_block)
        elif geometry.y >= footer_start:
            footer.append(indexed_block)
        else:
            body.append(indexed_block)

    warnings = list(_overlap_warnings(indexed_blocks))
    ordered_body, column_count, body_warnings = _order_body(body, page.width_points)
    warnings.extend(body_warnings)

    ordered: list[tuple[int, ReadingOrderRegion, int | None]] = [
        (index, ReadingOrderRegion.HEADER, None)
        for index, _block in sorted(header, key=_stable_geometry_key)
    ]
    ordered.extend(
        (index, ReadingOrderRegion.BODY, column_index) for index, column_index in ordered_body
    )
    ordered.extend(
        (index, ReadingOrderRegion.FOOTER, None)
        for index, _block in sorted(footer, key=_stable_geometry_key)
    )

    assignments = tuple(
        ReadingOrderAssignment(
            block_index=index,
            page_reading_order=reading_order,
            region=region,
            column_index=column_index,
        )
        for reading_order, (index, region, column_index) in enumerate(ordered, start=1)
    )
    return ReadingOrderResult(
        assignments=assignments,
        column_count=column_count,
        warnings=tuple(warnings),
    )


def _order_body(
    blocks: Sequence[tuple[int, TextBlockCandidate]],
    page_width: float,
) -> tuple[
    tuple[tuple[int, int | None], ...],
    int,
    tuple[ReadingOrderWarning, ...],
]:
    if not blocks:
        return (), 1, ()

    spanning = tuple(
        block for block in blocks if block[1].geometry.width >= page_width * _SPANNING_WIDTH_RATIO
    )
    column_blocks = tuple(block for block in blocks if block not in spanning)
    components = _column_components(column_blocks, page_width)

    if len(components) > 2 and _maximum_concurrent_components(components) > 2:
        affected = tuple(sorted(index for component in components for index, _block in component))
        warning = _warning(ReadingOrderUncertainty.TOO_MANY_COLUMNS, affected)
        return _geometry_order(blocks), 1, (warning,)

    if len(components) != 2 or not _components_overlap_vertically(*components):
        return _geometry_order(blocks), 1, ()

    components = tuple(sorted(components, key=_component_x))
    first_body_top = min(block[1].geometry.y for block in column_blocks)
    last_body_bottom = max(_bottom(block[1].geometry) for block in column_blocks)
    prefix = tuple(block for block in spanning if _bottom(block[1].geometry) <= first_body_top)
    suffix = tuple(block for block in spanning if block[1].geometry.y >= last_body_bottom)
    internal = tuple(block for block in spanning if block not in prefix and block not in suffix)
    if internal:
        warning = _warning(
            ReadingOrderUncertainty.INTERNAL_SPANNING_BLOCK,
            tuple(index for index, _block in internal),
        )
        return _geometry_order(blocks), 1, (warning,)

    ordered: list[tuple[int, int | None]] = [
        (index, None) for index, _block in sorted(prefix, key=_stable_geometry_key)
    ]
    for column_index, component in enumerate(components):
        ordered.extend(
            (index, column_index) for index, _block in sorted(component, key=_stable_geometry_key)
        )
    ordered.extend((index, None) for index, _block in sorted(suffix, key=_stable_geometry_key))
    return tuple(ordered), 2, ()


def _column_components(
    blocks: Sequence[tuple[int, TextBlockCandidate]],
    page_width: float,
) -> tuple[tuple[tuple[int, TextBlockCandidate], ...], ...]:
    remaining = set(range(len(blocks)))
    components: list[tuple[tuple[int, TextBlockCandidate], ...]] = []
    while remaining:
        first = min(remaining)
        remaining.remove(first)
        pending = [first]
        component_indexes: list[int] = []
        while pending:
            current = pending.pop()
            component_indexes.append(current)
            connected = {
                candidate
                for candidate in remaining
                if _same_column(
                    blocks[current][1].geometry,
                    blocks[candidate][1].geometry,
                    page_width,
                )
            }
            remaining.difference_update(connected)
            pending.extend(connected)
        components.append(tuple(blocks[index] for index in component_indexes))
    return tuple(components)


def _same_column(first: TextGeometry, second: TextGeometry, page_width: float) -> bool:
    overlap = _horizontal_overlap(first, second)
    overlap_ratio = overlap / min(first.width, second.width) if overlap > 0 else 0.0
    aligned = abs(first.x - second.x) <= page_width * 0.03
    return overlap_ratio >= _COLUMN_OVERLAP_RATIO or aligned


def _components_overlap_vertically(
    first: Sequence[tuple[int, TextBlockCandidate]],
    second: Sequence[tuple[int, TextBlockCandidate]],
) -> bool:
    first_top, first_bottom = _component_vertical_range(first)
    second_top, second_bottom = _component_vertical_range(second)
    overlap = min(first_bottom, second_bottom) - max(first_top, second_top)
    smaller_span = min(first_bottom - first_top, second_bottom - second_top)
    return overlap > 0 and smaller_span > 0 and overlap / smaller_span >= _COLUMN_OVERLAP_RATIO


def _maximum_concurrent_components(
    components: Sequence[Sequence[tuple[int, TextBlockCandidate]]],
) -> int:
    events: list[tuple[float, int]] = []
    for component in components:
        top, bottom = _component_vertical_range(component)
        events.extend(((top, 1), (bottom, -1)))
    active = 0
    maximum = 0
    for _position, change in sorted(events):
        active += change
        maximum = max(maximum, active)
    return maximum


def _component_vertical_range(
    component: Sequence[tuple[int, TextBlockCandidate]],
) -> tuple[float, float]:
    return (
        min(block.geometry.y for _index, block in component),
        max(_bottom(block.geometry) for _index, block in component),
    )


def _component_x(component: Sequence[tuple[int, TextBlockCandidate]]) -> float:
    return min(block.geometry.x for _index, block in component)


def _overlap_warnings(
    blocks: Sequence[tuple[int, TextBlockCandidate]],
) -> tuple[ReadingOrderWarning, ...]:
    overlapping: set[int] = set()
    for position, (first_index, first) in enumerate(blocks):
        for second_index, second in blocks[position + 1 :]:
            overlap = _intersection_area(first.geometry, second.geometry)
            smaller_area = min(_area(first.geometry), _area(second.geometry))
            if smaller_area > 0 and overlap / smaller_area >= _BLOCK_OVERLAP_WARNING_RATIO:
                overlapping.update((first_index, second_index))
    if not overlapping:
        return ()
    return (_warning(ReadingOrderUncertainty.OVERLAPPING_BLOCKS, tuple(sorted(overlapping))),)


def _geometry_order(
    blocks: Iterable[tuple[int, TextBlockCandidate]],
) -> tuple[tuple[int, int], ...]:
    return tuple((index, 0) for index, _block in sorted(blocks, key=_stable_geometry_key))


def _stable_geometry_key(
    indexed_block: tuple[int, TextBlockCandidate],
) -> tuple[float, float, float, float, str, int]:
    index, block = indexed_block
    geometry = block.geometry
    return (
        geometry.y,
        geometry.x,
        geometry.height,
        geometry.width,
        block.source_text,
        index,
    )


def _validate_page(page: ExtractedPage) -> None:
    if not _is_positive_finite(page.width_points) or not _is_positive_finite(page.height_points):
        raise ValueError("Page dimensions must be finite and positive.")
    for block in page.block_candidates:
        geometry = block.geometry
        values = (geometry.x, geometry.y, geometry.width, geometry.height)
        if not all(math.isfinite(value) for value in values):
            raise ValueError("Block geometry must be finite.")
        if geometry.width <= 0 or geometry.height <= 0 or geometry.x < 0 or geometry.y < 0:
            raise ValueError("Block dimensions must be positive and positions non-negative.")
        if (
            geometry.x + geometry.width > page.width_points
            or _bottom(geometry) > page.height_points
        ):
            raise ValueError("Block geometry must remain within the page.")


def _is_positive_finite(value: float) -> bool:
    return not isinstance(value, bool) and math.isfinite(value) and value > 0


def _intersection_area(first: TextGeometry, second: TextGeometry) -> float:
    width = max(0.0, _horizontal_overlap(first, second))
    height = max(
        0.0,
        min(_bottom(first), _bottom(second)) - max(first.y, second.y),
    )
    return width * height


def _horizontal_overlap(first: TextGeometry, second: TextGeometry) -> float:
    return min(first.x + first.width, second.x + second.width) - max(first.x, second.x)


def _area(geometry: TextGeometry) -> float:
    return geometry.width * geometry.height


def _bottom(geometry: TextGeometry) -> float:
    return geometry.y + geometry.height


def _warning(
    reason: ReadingOrderUncertainty,
    block_indexes: tuple[int, ...],
) -> ReadingOrderWarning:
    return ReadingOrderWarning(
        code="READING_ORDER_UNCERTAIN",
        reason=reason,
        block_indexes=block_indexes,
    )
