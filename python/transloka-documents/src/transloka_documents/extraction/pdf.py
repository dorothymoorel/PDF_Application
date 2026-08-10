import math
from collections.abc import Iterable, Sequence
from io import BufferedReader, BytesIO
from typing import BinaryIO, cast

import pdfplumber

from transloka_documents.extraction.models import (
    DigitalTextExtractionResult,
    ExtractedCharacter,
    ExtractedLine,
    ExtractedPage,
    ExtractedWord,
    TextBlockCandidate,
    TextGeometry,
)
from transloka_documents.extraction.normalization import normalize_source_lines

_LINE_TOLERANCE = 3.0
_MIN_FRAGMENT_GAP = 24.0
_BLOCK_GAP_RATIO = 1.5


class DigitalTextExtractionError(RuntimeError):
    pass


def extract_digital_text(stream: BinaryIO) -> DigitalTextExtractionResult:
    try:
        original_position = stream.tell()
        stream.seek(0)
        typed_stream = cast(BufferedReader | BytesIO, stream)
        with pdfplumber.open(typed_stream) as document:
            pages = tuple(
                _extract_page(page, page_number=page_number)
                for page_number, page in enumerate(document.pages, start=1)
            )
        return DigitalTextExtractionResult(pages=pages)
    except DigitalTextExtractionError:
        raise
    except Exception as exc:
        raise DigitalTextExtractionError("The PDF text could not be extracted safely.") from exc
    finally:
        try:
            stream.seek(original_position)
        except (NameError, OSError, ValueError):
            pass


def _extract_page(page: pdfplumber.page.Page, *, page_number: int) -> ExtractedPage:
    width = _finite_positive(page.width, "page width")
    height = _finite_positive(page.height, "page height")
    raw_characters = cast(list[dict[str, object]], page.chars)
    characters = tuple(_extract_character(raw, width, height) for raw in raw_characters)
    character_indexes = {id(raw): index for index, raw in enumerate(raw_characters)}

    raw_words = cast(
        list[dict[str, object]],
        page.extract_words(
            return_chars=True,
            expand_ligatures=False,
            extra_attrs=["fontname", "size"],
        ),
    )
    words = tuple(_extract_word(raw, character_indexes, width, height) for raw in raw_words)
    line_word_indexes = _group_words_into_lines(words)
    lines = tuple(_extract_line(indexes, words) for indexes in line_word_indexes)
    block_line_indexes = _group_lines_into_blocks(lines)
    blocks = tuple(_extract_block(indexes, lines) for indexes in block_line_indexes)

    return ExtractedPage(
        page_number=page_number,
        width_points=width,
        height_points=height,
        characters=characters,
        words=words,
        lines=lines,
        block_candidates=blocks,
    )


def _extract_character(
    raw: dict[str, object],
    page_width: float,
    page_height: float,
) -> ExtractedCharacter:
    return ExtractedCharacter(
        text=_text_field(raw, "text"),
        geometry=_geometry(raw, page_width, page_height),
        font_name=_optional_text_field(raw, "fontname"),
        font_size=_optional_float_field(raw, "size"),
        upright=_optional_bool_field(raw, "upright"),
    )


def _extract_word(
    raw: dict[str, object],
    character_indexes: dict[int, int],
    page_width: float,
    page_height: float,
) -> ExtractedWord:
    source_text = _text_field(raw, "text")
    normalization = normalize_source_lines((source_text,))
    raw_word_characters = raw.get("chars")
    if not isinstance(raw_word_characters, list):
        raise DigitalTextExtractionError("A PDF word is missing character geometry.")
    indexes = tuple(
        _character_index(character, character_indexes) for character in raw_word_characters
    )

    return ExtractedWord(
        source_text=source_text,
        normalized_text=normalization.text,
        geometry=_geometry(raw, page_width, page_height),
        character_indexes=indexes,
        normalization_boundaries=normalization.boundaries,
        font_name=_optional_text_field(raw, "fontname"),
        font_size=_optional_float_field(raw, "size"),
        upright=_optional_bool_field(raw, "upright"),
    )


def _character_index(raw: object, indexes: dict[int, int]) -> int:
    if not isinstance(raw, dict) or id(raw) not in indexes:
        raise DigitalTextExtractionError("A PDF word references unknown character geometry.")
    return indexes[id(raw)]


def _group_words_into_lines(words: Sequence[ExtractedWord]) -> tuple[tuple[int, ...], ...]:
    ordered_indexes = sorted(
        range(len(words)),
        key=lambda index: (words[index].geometry.y, words[index].geometry.x),
    )
    visual_rows: list[list[int]] = []
    for word_index in ordered_indexes:
        word = words[word_index]
        if visual_rows and _same_visual_row(words[visual_rows[-1][0]], word):
            visual_rows[-1].append(word_index)
        else:
            visual_rows.append([word_index])

    lines: list[tuple[int, ...]] = []
    for row in visual_rows:
        row.sort(key=lambda index: words[index].geometry.x)
        fragment: list[int] = []
        for word_index in row:
            if fragment and _is_fragment_gap(words[fragment[-1]], words[word_index]):
                lines.append(tuple(fragment))
                fragment = []
            fragment.append(word_index)
        if fragment:
            lines.append(tuple(fragment))
    return tuple(lines)


def _same_visual_row(first: ExtractedWord, second: ExtractedWord) -> bool:
    return abs(first.geometry.y - second.geometry.y) <= _LINE_TOLERANCE


def _is_fragment_gap(previous: ExtractedWord, current: ExtractedWord) -> bool:
    previous_end = previous.geometry.x + previous.geometry.width
    gap = current.geometry.x - previous_end
    font_size = max(previous.font_size or 0.0, current.font_size or 0.0)
    return gap > max(_MIN_FRAGMENT_GAP, font_size * 2.5)


def _extract_line(indexes: tuple[int, ...], words: Sequence[ExtractedWord]) -> ExtractedLine:
    selected = tuple(words[index] for index in indexes)
    source_text = " ".join(word.source_text for word in selected)
    normalization = normalize_source_lines((source_text,))
    return ExtractedLine(
        source_text=source_text,
        normalized_text=normalization.text,
        geometry=_union_geometry(word.geometry for word in selected),
        word_indexes=indexes,
        character_indexes=_ordered_unique(
            character_index for word in selected for character_index in word.character_indexes
        ),
        normalization_boundaries=normalization.boundaries,
        font_name=_common_font(word.font_name for word in selected),
        font_size=_max_font_size(word.font_size for word in selected),
    )


def _group_lines_into_blocks(lines: Sequence[ExtractedLine]) -> tuple[tuple[int, ...], ...]:
    blocks: list[list[int]] = []
    for line_index, line in enumerate(lines):
        candidates = [
            (block_index, _block_distance(lines[block[-1]], line))
            for block_index, block in enumerate(blocks)
            if _can_join_block(lines[block[-1]], line)
        ]
        if candidates:
            block_index = min(candidates, key=lambda candidate: candidate[1])[0]
            blocks[block_index].append(line_index)
        else:
            blocks.append([line_index])
    return tuple(tuple(block) for block in blocks)


def _can_join_block(previous: ExtractedLine, current: ExtractedLine) -> bool:
    vertical_gap = current.geometry.y - (previous.geometry.y + previous.geometry.height)
    max_gap = max(previous.geometry.height, current.geometry.height) * _BLOCK_GAP_RATIO
    if vertical_gap < -_LINE_TOLERANCE or vertical_gap > max_gap:
        return False
    if not _font_sizes_match(previous.font_size, current.font_size):
        return False
    return (
        _horizontal_overlap(previous.geometry, current.geometry) > 0
        or abs(previous.geometry.x - current.geometry.x) <= _MIN_FRAGMENT_GAP
    )


def _block_distance(previous: ExtractedLine, current: ExtractedLine) -> tuple[float, float]:
    vertical_gap = max(
        0.0,
        current.geometry.y - (previous.geometry.y + previous.geometry.height),
    )
    return vertical_gap, abs(previous.geometry.x - current.geometry.x)


def _font_sizes_match(first: float | None, second: float | None) -> bool:
    if first is None or second is None:
        return first is second
    return abs(first - second) <= max(1.0, max(first, second) * 0.15)


def _horizontal_overlap(first: TextGeometry, second: TextGeometry) -> float:
    return min(first.x + first.width, second.x + second.width) - max(first.x, second.x)


def _extract_block(
    indexes: tuple[int, ...],
    lines: Sequence[ExtractedLine],
) -> TextBlockCandidate:
    selected = tuple(lines[index] for index in indexes)
    normalization = normalize_source_lines(tuple(line.source_text for line in selected))
    return TextBlockCandidate(
        source_text=normalization.source_text,
        normalized_text=normalization.text,
        geometry=_union_geometry(line.geometry for line in selected),
        line_indexes=indexes,
        word_indexes=_ordered_unique(
            word_index for line in selected for word_index in line.word_indexes
        ),
        character_indexes=_ordered_unique(
            character_index for line in selected for character_index in line.character_indexes
        ),
        normalization_boundaries=normalization.boundaries,
        font_name=_common_font(line.font_name for line in selected),
        font_size=_max_font_size(line.font_size for line in selected),
    )


def _union_geometry(geometries: Iterable[TextGeometry]) -> TextGeometry:
    items = tuple(geometries)
    if not items:
        raise DigitalTextExtractionError("Text geometry cannot be empty.")
    x0 = min(item.x for item in items)
    top = min(item.y for item in items)
    x1 = max(item.x + item.width for item in items)
    bottom = max(item.y + item.height for item in items)
    return TextGeometry(x=x0, y=top, width=x1 - x0, height=bottom - top)


def _geometry(
    raw: dict[str, object],
    page_width: float,
    page_height: float,
) -> TextGeometry:
    x0 = _finite_number(raw.get("x0"), "x0")
    top = _finite_number(raw.get("top"), "top")
    x1 = _finite_number(raw.get("x1"), "x1")
    bottom = _finite_number(raw.get("bottom"), "bottom")
    tolerance = 0.01
    if (
        x1 < x0
        or bottom < top
        or x0 < -tolerance
        or top < -tolerance
        or x1 > page_width + tolerance
        or bottom > page_height + tolerance
    ):
        raise DigitalTextExtractionError("Extracted text geometry is outside the PDF page.")
    return TextGeometry(
        x=max(0.0, x0),
        y=max(0.0, top),
        width=min(page_width, x1) - max(0.0, x0),
        height=min(page_height, bottom) - max(0.0, top),
    )


def _finite_positive(value: object, name: str) -> float:
    number = _finite_number(value, name)
    if number <= 0:
        raise DigitalTextExtractionError(f"The PDF {name} must be positive.")
    return number


def _finite_number(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise DigitalTextExtractionError(f"The PDF {name} is invalid.")
    number = float(value)
    if not math.isfinite(number):
        raise DigitalTextExtractionError(f"The PDF {name} is invalid.")
    return number


def _text_field(raw: dict[str, object], name: str) -> str:
    value = raw.get(name)
    if not isinstance(value, str):
        raise DigitalTextExtractionError(f"Extracted text field {name} is invalid.")
    return value


def _optional_text_field(raw: dict[str, object], name: str) -> str | None:
    value = raw.get(name)
    return value if isinstance(value, str) else None


def _optional_float_field(raw: dict[str, object], name: str) -> float | None:
    value = raw.get(name)
    if value is None:
        return None
    return _finite_number(value, name)


def _optional_bool_field(raw: dict[str, object], name: str) -> bool | None:
    value = raw.get(name)
    return value if isinstance(value, bool) else None


def _ordered_unique(values: Iterable[int]) -> tuple[int, ...]:
    return tuple(dict.fromkeys(values))


def _common_font(font_names: Iterable[str | None]) -> str | None:
    values = set(font_names)
    return values.pop() if len(values) == 1 else None


def _max_font_size(font_sizes: Iterable[float | None]) -> float | None:
    values = tuple(size for size in font_sizes if size is not None)
    return max(values, default=None)
