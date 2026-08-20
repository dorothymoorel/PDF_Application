from __future__ import annotations

import math
import re
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from uuid import NAMESPACE_URL, uuid5

from transloka_documents.extraction.normalization import normalize_source_lines
from transloka_documents.ocr.base import OCRGeometry, OCRResult, OCRTextBlock

NORMALIZATION_VERSION = "ocr_normalizer_0.1"

_URL = re.compile(r"https?://[^\s<>()]+", re.IGNORECASE)
_INLINE_CODE = re.compile(r"`[^`]+`")
_ABBREVIATIONS = {
    "al",
    "dr",
    "e.g",
    "etc",
    "fig",
    "i.e",
    "mr",
    "mrs",
    "ms",
    "no",
    "prof",
    "sr",
    "vs",
}


@dataclass(frozen=True, slots=True)
class OCRNormalizationSettings:
    """Deterministic thresholds used when turning OCR boxes into source blocks."""

    line_vertical_tolerance_ratio: float = 0.55
    line_horizontal_gap_ratio: float = 3.0
    column_overlap_ratio: float = 0.20
    block_line_gap_ratio: float = 2.25
    low_confidence_threshold: float | None = None

    def __post_init__(self) -> None:
        positive = (
            ("line_vertical_tolerance_ratio", self.line_vertical_tolerance_ratio),
            ("line_horizontal_gap_ratio", self.line_horizontal_gap_ratio),
            ("column_overlap_ratio", self.column_overlap_ratio),
            ("block_line_gap_ratio", self.block_line_gap_ratio),
        )
        for name, value in positive:
            if not math.isfinite(value) or value <= 0:
                raise ValueError(f"{name} must be finite and greater than zero.")
        if self.column_overlap_ratio > 1:
            raise ValueError("column_overlap_ratio must not be greater than one.")
        if self.low_confidence_threshold is not None and (
            not math.isfinite(self.low_confidence_threshold)
            or not 0.0 <= self.low_confidence_threshold <= 1.0
        ):
            raise ValueError("low_confidence_threshold must be between 0 and 1.")


@dataclass(frozen=True, slots=True)
class OCRNormalizedLine:
    """A visual OCR line after whitespace cleanup and deterministic ordering."""

    line_index: int
    source_text: str
    normalized_text: str
    geometry: OCRGeometry
    confidence: float
    source_block_indexes: tuple[int, ...]
    reading_order: int
    column_index: int | None
    is_low_confidence: bool

    @property
    def text(self) -> str:
        return self.normalized_text


@dataclass(frozen=True, slots=True)
class OCRNormalizedSegment:
    """A source segment derived from one normalized OCR block."""

    segment_id: str
    block_id: str
    segment_order: int
    source_text: str
    normalized_source_text: str
    geometry: OCRGeometry
    confidence: float
    is_low_confidence: bool

    @property
    def text(self) -> str:
        return self.normalized_source_text


@dataclass(frozen=True, slots=True)
class OCRNormalizedBlock:
    """A logical source block built from one or more ordered OCR lines."""

    block_id: str
    source_text: str
    normalized_source_text: str
    geometry: OCRGeometry
    confidence: float
    line_indexes: tuple[int, ...]
    reading_order: int
    column_index: int | None
    is_low_confidence: bool

    @property
    def text(self) -> str:
        return self.normalized_source_text


@dataclass(frozen=True, slots=True)
class OCRNormalizationResult:
    """Normalized OCR while retaining the immutable provider result verbatim."""

    page_number: int
    raw_result: OCRResult
    source_text: str
    normalized_text: str
    lines: tuple[OCRNormalizedLine, ...]
    blocks: tuple[OCRNormalizedBlock, ...]
    segments: tuple[OCRNormalizedSegment, ...]
    confidence: float
    column_count: int
    warnings: tuple[str, ...] = ()
    settings: OCRNormalizationSettings = OCRNormalizationSettings()

    @property
    def text(self) -> str:
        return self.normalized_text

    @property
    def raw_ocr(self) -> OCRResult:
        """Compatibility name that makes raw OCR preservation explicit."""

        return self.raw_result

    @property
    def raw_text(self) -> str:
        return self.raw_result.text

    @property
    def is_low_confidence(self) -> bool:
        threshold = _confidence_threshold(self.raw_result, self.settings)
        return self.confidence < threshold


@dataclass(frozen=True, slots=True)
class _OCRLinePart:
    source_block_index: int
    text: str
    geometry: OCRGeometry
    confidence: float
    part_index: int


@dataclass(frozen=True, slots=True)
class _LineGroup:
    parts: tuple[_OCRLinePart, ...]


def normalize_ocr_result(
    result: OCRResult,
    *,
    settings: OCRNormalizationSettings | None = None,
) -> OCRNormalizationResult:
    """Normalize OCR text, geometry, confidence, and reading order.

    The provider result is never mutated or replaced.  It is returned by
    reference as ``raw_result`` so callers can persist raw and resolved source
    independently.
    """

    normalized_settings = settings or OCRNormalizationSettings()
    parts = _line_parts(result.blocks)
    if not parts:
        normalized_text = normalize_source_lines((result.text,)).text.strip() if result.text else ""
        return OCRNormalizationResult(
            page_number=result.page_number,
            raw_result=result,
            source_text=result.text,
            normalized_text=normalized_text,
            lines=(),
            blocks=(),
            segments=(),
            confidence=result.confidence,
            column_count=1,
            settings=normalized_settings,
        )

    groups = _group_visual_lines(parts, normalized_settings)
    lines = _build_lines(groups, normalized_settings)
    ordered_line_indexes, column_by_line, column_count = _reading_order(lines, normalized_settings)
    rendered_lines = tuple(
        _line_with_order(
            line,
            reading_order=order,
            column_index=column_by_line[index],
            settings=normalized_settings,
            result=result,
        )
        for order, index, line in (
            (order, index, lines[index])
            for order, index in enumerate(ordered_line_indexes, start=1)
        )
    )
    blocks = _build_blocks(rendered_lines, normalized_settings, result)
    segments = tuple(
        segment for block in blocks for segment in _build_segments(block, normalized_settings)
    )
    source_text = "\n".join(block.source_text for block in blocks)
    normalized_text = "\n".join(block.normalized_source_text for block in blocks)
    warnings = _warnings(result, rendered_lines, normalized_settings)
    return OCRNormalizationResult(
        page_number=result.page_number,
        raw_result=result,
        source_text=source_text,
        normalized_text=normalized_text,
        lines=rendered_lines,
        blocks=blocks,
        segments=segments,
        confidence=result.confidence,
        column_count=column_count,
        warnings=warnings,
        settings=normalized_settings,
    )


def normalize_ocr(
    result: OCRResult,
    *,
    settings: OCRNormalizationSettings | None = None,
) -> OCRNormalizationResult:
    """Short alias for :func:`normalize_ocr_result`."""

    return normalize_ocr_result(result, settings=settings)


class OCRNormalizer:
    """Reusable normalizer for callers processing multiple OCR pages."""

    def __init__(self, settings: OCRNormalizationSettings | None = None) -> None:
        self.settings = settings or OCRNormalizationSettings()

    def normalize(self, result: OCRResult) -> OCRNormalizationResult:
        return normalize_ocr_result(result, settings=self.settings)


NormalizedOCRLine = OCRNormalizedLine
NormalizedOCRBlock = OCRNormalizedBlock
NormalizedOCRSegment = OCRNormalizedSegment
NormalizedOCRResult = OCRNormalizationResult


def _line_parts(blocks: Sequence[OCRTextBlock]) -> tuple[_OCRLinePart, ...]:
    parts: list[_OCRLinePart] = []
    for source_block_index, block in enumerate(blocks):
        raw_lines = block.text.splitlines() or (block.text,)
        line_count = len(raw_lines)
        part_height = block.geometry.height / line_count
        for part_index, text in enumerate(raw_lines):
            geometry = OCRGeometry(
                x=block.geometry.x,
                y=block.geometry.y + part_index * part_height,
                width=block.geometry.width,
                height=part_height,
                coordinate_system=block.geometry.coordinate_system,
            )
            parts.append(
                _OCRLinePart(
                    source_block_index=source_block_index,
                    text=text,
                    geometry=geometry,
                    confidence=block.confidence,
                    part_index=part_index,
                )
            )
    return tuple(parts)


def _group_visual_lines(
    parts: Sequence[_OCRLinePart],
    settings: OCRNormalizationSettings,
) -> tuple[_LineGroup, ...]:
    groups: list[list[_OCRLinePart]] = []
    for part in sorted(parts, key=_part_geometry_key):
        matching: list[int] = []
        for index, group in enumerate(groups):
            if any(_same_visual_line(part, candidate, settings) for candidate in group):
                matching.append(index)
        if not matching:
            groups.append([part])
            continue
        first = matching[0]
        groups[first].append(part)
        for index in reversed(matching[1:]):
            groups[first].extend(groups.pop(index))
    return tuple(_LineGroup(tuple(group)) for group in groups)


def _same_visual_line(
    first: _OCRLinePart,
    second: _OCRLinePart,
    settings: OCRNormalizationSettings,
) -> bool:
    first_geometry = first.geometry
    second_geometry = second.geometry
    top = max(first_geometry.y, second_geometry.y)
    bottom = min(_bottom(first_geometry), _bottom(second_geometry))
    overlap = max(0.0, bottom - top)
    minimum_height = min(first_geometry.height, second_geometry.height)
    centers_close = abs(_center_y(first_geometry) - _center_y(second_geometry)) <= (
        max(first_geometry.height, second_geometry.height) * settings.line_vertical_tolerance_ratio
    )
    vertically_aligned = overlap / minimum_height >= 0.30 or centers_close
    if not vertically_aligned:
        return False
    gap = _horizontal_gap(first_geometry, second_geometry)
    maximum_gap = max(
        max(first_geometry.height, second_geometry.height) * settings.line_horizontal_gap_ratio,
        min(first_geometry.width, second_geometry.width) * 0.25,
    )
    return gap <= maximum_gap


def _build_lines(
    groups: Sequence[_LineGroup],
    settings: OCRNormalizationSettings,
) -> tuple[OCRNormalizedLine, ...]:
    lines: list[OCRNormalizedLine] = []
    for line_index, group in enumerate(groups):
        parts = tuple(sorted(group.parts, key=_part_geometry_key))
        source_text = " ".join(_clean_inline(part.text) for part in parts).strip()
        geometry = _union_geometry(tuple(part.geometry for part in parts))
        confidence = _weighted_confidence(
            ((_clean_inline(part.text), part.confidence) for part in parts),
            fallback=0.0,
        )
        lines.append(
            OCRNormalizedLine(
                line_index=line_index,
                source_text=source_text,
                normalized_text=normalize_source_lines((source_text,)).text.strip(),
                geometry=geometry,
                confidence=confidence,
                source_block_indexes=tuple(sorted({part.source_block_index for part in parts})),
                reading_order=0,
                column_index=None,
                is_low_confidence=confidence < _line_threshold(settings),
            )
        )
    return tuple(lines)


def _reading_order(
    lines: Sequence[OCRNormalizedLine],
    settings: OCRNormalizationSettings,
) -> tuple[tuple[int, ...], dict[int, int | None], int]:
    if not lines:
        return (), {}, 1
    components = _column_components(lines, settings)
    if len(components) == 2 and _components_overlap_vertically(
        tuple(lines[index] for index in components[0]),
        tuple(lines[index] for index in components[1]),
    ):
        components = tuple(sorted(components, key=lambda component: _component_x(lines, component)))
        ordered_indexes: list[int] = []
        column_by_line: dict[int, int | None] = {}
        for column_index, component in enumerate(components):
            for index in sorted(component, key=lambda item: _line_geometry_key(lines[item])):
                ordered_indexes.append(index)
                column_by_line[index] = column_index
        return tuple(ordered_indexes), column_by_line, 2
    ordered = tuple(sorted(range(len(lines)), key=lambda index: _line_geometry_key(lines[index])))
    return ordered, {index: None for index in ordered}, 1


def _column_components(
    lines: Sequence[OCRNormalizedLine],
    settings: OCRNormalizationSettings,
) -> tuple[tuple[int, ...], ...]:
    remaining = set(range(len(lines)))
    components: list[tuple[int, ...]] = []
    while remaining:
        first = min(remaining)
        remaining.remove(first)
        pending = [first]
        component: list[int] = []
        while pending:
            current = pending.pop()
            component.append(current)
            connected = {
                candidate
                for candidate in remaining
                if _same_column(lines[current].geometry, lines[candidate].geometry, settings)
            }
            remaining.difference_update(connected)
            pending.extend(connected)
        components.append(tuple(component))
    return tuple(components)


def _same_column(
    first: OCRGeometry,
    second: OCRGeometry,
    settings: OCRNormalizationSettings,
) -> bool:
    overlap = _horizontal_overlap(first, second)
    overlap_ratio = overlap / min(first.width, second.width) if overlap > 0 else 0.0
    aligned = abs(first.x - second.x) <= max(12.0, min(first.width, second.width) * 0.15)
    return overlap_ratio >= settings.column_overlap_ratio or aligned


def _components_overlap_vertically(
    first: Sequence[OCRNormalizedLine],
    second: Sequence[OCRNormalizedLine],
) -> bool:
    first_top, first_bottom = _vertical_range(first)
    second_top, second_bottom = _vertical_range(second)
    overlap = min(first_bottom, second_bottom) - max(first_top, second_top)
    smaller_span = min(first_bottom - first_top, second_bottom - second_top)
    return smaller_span > 0 and overlap / smaller_span >= 0.20


def _build_blocks(
    lines: Sequence[OCRNormalizedLine],
    settings: OCRNormalizationSettings,
    result: OCRResult,
) -> tuple[OCRNormalizedBlock, ...]:
    groups: list[list[OCRNormalizedLine]] = []
    for line in lines:
        if groups and _same_logical_block(groups[-1][-1], line, settings):
            groups[-1].append(line)
        else:
            groups.append([line])
    blocks: list[OCRNormalizedBlock] = []
    for block_index, group in enumerate(groups, start=1):
        source_lines = tuple(line.source_text for line in group)
        source_text = "\n".join(source_lines).strip()
        normalized_source_text = normalize_source_lines(source_lines).text.strip()
        confidence = _weighted_confidence(
            ((line.normalized_text, line.confidence) for line in group),
            fallback=result.confidence,
        )
        identity = uuid5(
            NAMESPACE_URL,
            f"{NORMALIZATION_VERSION}:{result.page_number}:{block_index}:{source_text}",
        )
        blocks.append(
            OCRNormalizedBlock(
                block_id=f"blk_{identity}",
                source_text=source_text,
                normalized_source_text=normalized_source_text,
                geometry=_union_geometry(tuple(line.geometry for line in group)),
                confidence=confidence,
                line_indexes=tuple(line.line_index for line in group),
                reading_order=block_index,
                column_index=_common_column(group),
                is_low_confidence=confidence < _confidence_threshold(result, settings),
            )
        )
    return tuple(blocks)


def _same_logical_block(
    previous: OCRNormalizedLine,
    current: OCRNormalizedLine,
    settings: OCRNormalizationSettings,
) -> bool:
    if previous.column_index != current.column_index:
        return False
    vertical_gap = current.geometry.y - _bottom(previous.geometry)
    if vertical_gap < 0:
        return False
    allowed_gap = (
        max(previous.geometry.height, current.geometry.height) * settings.block_line_gap_ratio
    )
    return vertical_gap <= allowed_gap


def _build_segments(
    block: OCRNormalizedBlock,
    settings: OCRNormalizationSettings,
) -> tuple[OCRNormalizedSegment, ...]:
    source_units = _split_sentences(block.source_text)
    if not source_units:
        return ()
    segments: list[OCRNormalizedSegment] = []
    for segment_order, source_text in enumerate(source_units, start=1):
        normalized_text = normalize_source_lines(
            source_text.splitlines() or (source_text,)
        ).text.strip()
        identity = uuid5(
            NAMESPACE_URL,
            f"{NORMALIZATION_VERSION}:{block.block_id}:{segment_order}:{normalized_text}",
        )
        segments.append(
            OCRNormalizedSegment(
                segment_id=f"seg_{identity}",
                block_id=block.block_id,
                segment_order=segment_order,
                source_text=source_text,
                normalized_source_text=normalized_text,
                geometry=block.geometry,
                confidence=block.confidence,
                is_low_confidence=block.is_low_confidence,
            )
        )
    return tuple(segments)


def _line_with_order(
    line: OCRNormalizedLine,
    *,
    reading_order: int,
    column_index: int | None,
    settings: OCRNormalizationSettings,
    result: OCRResult,
) -> OCRNormalizedLine:
    confidence = line.confidence
    return OCRNormalizedLine(
        line_index=line.line_index,
        source_text=line.source_text,
        normalized_text=line.normalized_text,
        geometry=line.geometry,
        confidence=confidence,
        source_block_indexes=line.source_block_indexes,
        reading_order=reading_order,
        column_index=column_index,
        is_low_confidence=confidence < _confidence_threshold(result, settings),
    )


def _warnings(
    result: OCRResult,
    lines: Sequence[OCRNormalizedLine],
    settings: OCRNormalizationSettings,
) -> tuple[str, ...]:
    warnings: list[str] = []
    if result.confidence < _confidence_threshold(result, settings):
        warnings.append("LOW_CONFIDENCE")
    if any(line.is_low_confidence for line in lines):
        warnings.append("LOW_CONFIDENCE_LINE")
    return tuple(dict.fromkeys(warnings))


def _split_sentences(text: str) -> tuple[str, ...]:
    protected = _protected_spans(text)
    boundaries: list[int] = []
    index = 0
    while index < len(text):
        character = text[index]
        if character in ".!?" and not _inside_span(index, protected):
            if _is_sentence_end(text, index, character):
                boundaries.append(_include_closing_punctuation(text, index + 1))
        index += 1
    units: list[str] = []
    start = 0
    for end in boundaries:
        unit = text[start:end].strip()
        if unit:
            units.append(unit)
        start = end
    remainder = text[start:].strip()
    if remainder:
        units.append(remainder)
    return tuple(units)


def _protected_spans(text: str) -> tuple[tuple[int, int], ...]:
    spans: list[tuple[int, int]] = []
    for pattern in (_URL, _INLINE_CODE):
        for match in pattern.finditer(text):
            end = match.end()
            if pattern is _URL:
                while end > match.start() and text[end - 1] in ".!?;:":
                    end -= 1
            spans.append((match.start(), end))
    return tuple(spans)


def _inside_span(index: int, spans: Sequence[tuple[int, int]]) -> bool:
    return any(start <= index < end for start, end in spans)


def _is_sentence_end(text: str, index: int, punctuation: str) -> bool:
    if punctuation == ".":
        if (
            index > 0
            and index + 1 < len(text)
            and text[index - 1].isdigit()
            and text[index + 1].isdigit()
        ):
            return False
        token = _word_before(text, index).lower()
        if token in _ABBREVIATIONS or (len(token) == 1 and token.isalpha()):
            return False
        if index + 1 < len(text) and text[index + 1] == ".":
            return False
    next_index = _next_content_index(text, index + 1)
    return next_index is None or text[next_index].isupper() or text[next_index].isdigit()


def _word_before(text: str, index: int) -> str:
    start = index - 1
    while start >= 0 and (text[start].isalpha() or text[start] == "."):
        start -= 1
    return text[start + 1 : index]


def _next_content_index(text: str, start: int) -> int | None:
    index = start
    while index < len(text) and (text[index].isspace() or text[index] in "\"')]}”’"):
        index += 1
    return index if index < len(text) else None


def _include_closing_punctuation(text: str, start: int) -> int:
    index = start
    while index < len(text) and text[index] in "\"')]}”’":
        index += 1
    return index


def _clean_inline(text: str) -> str:
    return normalize_source_lines((text,)).text.strip()


def _union_geometry(geometries: Sequence[OCRGeometry]) -> OCRGeometry:
    if not geometries:
        raise ValueError("At least one OCR geometry is required.")
    coordinate_systems = {geometry.coordinate_system for geometry in geometries}
    if len(coordinate_systems) != 1:
        raise ValueError("OCR geometries must use one coordinate system.")
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


def _weighted_confidence(
    values: Iterable[tuple[str, float]],
    *,
    fallback: float,
) -> float:
    items = tuple((text, confidence) for text, confidence in values if text.strip())
    if not items:
        return fallback
    total_weight = sum(max(1, len(text.strip())) for text, _confidence in items)
    if total_weight <= 0:
        return fallback
    return sum(max(1, len(text.strip())) * confidence for text, confidence in items) / total_weight


def _confidence_threshold(result: OCRResult, settings: OCRNormalizationSettings) -> float:
    return (
        settings.low_confidence_threshold
        if settings.low_confidence_threshold is not None
        else result.settings.low_confidence_threshold
    )


def _line_threshold(settings: OCRNormalizationSettings) -> float:
    return (
        settings.low_confidence_threshold if settings.low_confidence_threshold is not None else 0.75
    )


def _common_column(lines: Sequence[OCRNormalizedLine]) -> int | None:
    columns = {line.column_index for line in lines}
    return next(iter(columns)) if len(columns) == 1 else None


def _part_geometry_key(part: _OCRLinePart) -> tuple[float, float, int, int]:
    return part.geometry.y, part.geometry.x, part.source_block_index, part.part_index


def _line_geometry_key(line: OCRNormalizedLine) -> tuple[float, float, int]:
    return line.geometry.y, line.geometry.x, line.line_index


def _vertical_range(lines: Sequence[OCRNormalizedLine]) -> tuple[float, float]:
    return min(line.geometry.y for line in lines), max(_bottom(line.geometry) for line in lines)


def _component_x(lines: Sequence[OCRNormalizedLine], component: Sequence[int]) -> float:
    return min(lines[index].geometry.x for index in component)


def _bottom(geometry: OCRGeometry) -> float:
    return geometry.y + geometry.height


def _center_y(geometry: OCRGeometry) -> float:
    return geometry.y + geometry.height / 2


def _horizontal_gap(first: OCRGeometry, second: OCRGeometry) -> float:
    if first.x <= second.x:
        return max(0.0, second.x - (first.x + first.width))
    return max(0.0, first.x - (second.x + second.width))


def _horizontal_overlap(first: OCRGeometry, second: OCRGeometry) -> float:
    return max(0.0, min(first.x + first.width, second.x + second.width) - max(first.x, second.x))
