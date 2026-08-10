import re
from dataclasses import dataclass
from uuid import NAMESPACE_URL, uuid5

from transloka_documents.extraction.models import TextBlockCandidate
from transloka_documents.extraction.normalization import normalize_source_lines
from transloka_documents.structure.classifier import BlockType

SEGMENTATION_VERSION = "segmenter_0.1"
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
_WHOLE_BLOCK_TYPES = {
    BlockType.DOCUMENT_TITLE.value,
    BlockType.HEADING_1.value,
    BlockType.CAPTION.value,
    BlockType.TABLE.value,
    "TABLE_CELL",
}


@dataclass(frozen=True, slots=True)
class TranslationSegment:
    segment_id: str
    block_id: str
    segment_order: int
    source_text: str
    normalized_source_text: str
    block_type: str
    is_translatable: bool
    segmentation_version: str = SEGMENTATION_VERSION


def segment_block(
    block_id: str,
    block: TextBlockCandidate,
    block_type: BlockType | str,
) -> tuple[TranslationSegment, ...]:
    if not block_id.strip():
        raise ValueError("Block ID must not be empty.")
    canonical_type = block_type.value if isinstance(block_type, BlockType) else block_type
    if not canonical_type:
        raise ValueError("Block type must not be empty.")

    source_units = _source_units(block.source_text, canonical_type)
    return tuple(
        _segment(block_id, canonical_type, source_text, order)
        for order, source_text in enumerate(source_units, start=1)
    )


def _source_units(source_text: str, block_type: str) -> tuple[str, ...]:
    if not source_text.strip():
        return ()
    if block_type == BlockType.CODE_BLOCK.value:
        return (source_text,)
    if block_type == BlockType.LIST.value:
        return tuple(line for line in source_text.splitlines() if line.strip())
    if block_type in _WHOLE_BLOCK_TYPES:
        return (source_text,)
    return _split_sentences(source_text)


def _segment(
    block_id: str,
    block_type: str,
    source_text: str,
    order: int,
) -> TranslationSegment:
    normalized = normalize_source_lines(source_text.splitlines() or (source_text,)).text
    identity = uuid5(NAMESPACE_URL, f"{SEGMENTATION_VERSION}:{block_id}:{order}:{source_text}")
    return TranslationSegment(
        segment_id=f"seg_{identity}",
        block_id=block_id,
        segment_order=order,
        source_text=source_text,
        normalized_source_text=normalized,
        block_type=block_type,
        is_translatable=block_type != BlockType.CODE_BLOCK.value,
    )


def _split_sentences(text: str) -> tuple[str, ...]:
    protected = _protected_spans(text)
    boundaries: list[int] = []
    index = 0
    while index < len(text):
        character = text[index]
        if character in ".!?" and not _inside_span(index, protected):
            if _is_sentence_end(text, index, character):
                end = _include_closing_punctuation(text, index + 1)
                boundaries.append(end)
                index = end
                continue
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
                while end > match.start() and text[end - 1] in ".,!?;:":
                    end -= 1
            spans.append((match.start(), end))
    return tuple(spans)


def _inside_span(index: int, spans: tuple[tuple[int, int], ...]) -> bool:
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
    if next_index is None:
        return True
    return text[next_index].isupper() or text[next_index].isdigit() or text[next_index] in "\"'(["


def _word_before(text: str, index: int) -> str:
    start = index - 1
    while start >= 0 and (text[start].isalpha() or text[start] == "."):
        start -= 1
    return text[start + 1 : index]


def _next_content_index(text: str, start: int) -> int | None:
    index = start
    while index < len(text) and (text[index].isspace() or text[index] in "\"')]}\u201d\u2019"):
        index += 1
    return index if index < len(text) else None


def _include_closing_punctuation(text: str, start: int) -> int:
    index = start
    while index < len(text) and text[index] in "\"')]}\u201d\u2019":
        index += 1
    return index
