import math
import re
from dataclasses import dataclass
from enum import StrEnum
from typing import Literal

from transloka_documents.extraction.models import TextBlockCandidate
from transloka_documents.structure.reading_order import ReadingOrderRegion

_LIST_ITEM = re.compile(r"^\s*(?:[-*\u2022]|(?:\d+|[A-Za-z])[.)])\s+\S")
_CAPTION = re.compile(r"^\s*(?:figure|fig\.|table|image)\s+\d+\b", re.IGNORECASE)
_ARABIC_PAGE_NUMBER = re.compile(r"^(?:page\s+)?\d+(?:\s*(?:of|/)\s*\d+)?$", re.IGNORECASE)
_ROMAN_PAGE_NUMBER = re.compile(r"^[ivxlcdm]{2,}$", re.IGNORECASE)
_CODE_PREFIX = re.compile(
    r"^\s*(?:def|class|from|import|async\s+def|function|const|let|var|SELECT|WITH)\b"
)
_MONOSPACE_MARKERS = ("courier", "mono", "consolas", "menlo", "code")


class BlockType(StrEnum):
    DOCUMENT_TITLE = "DOCUMENT_TITLE"
    HEADING_1 = "HEADING_1"
    PARAGRAPH = "PARAGRAPH"
    LIST = "LIST"
    CAPTION = "CAPTION"
    IMAGE = "IMAGE"
    TABLE = "TABLE"
    CODE_BLOCK = "CODE_BLOCK"
    HEADER = "HEADER"
    FOOTER = "FOOTER"
    PAGE_NUMBER = "PAGE_NUMBER"
    UNKNOWN = "UNKNOWN"


class NativeBlockKind(StrEnum):
    IMAGE = "IMAGE"
    TABLE = "TABLE"


class ClassificationUncertainty(StrEnum):
    EMPTY_CONTENT = "EMPTY_CONTENT"
    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"


@dataclass(frozen=True, slots=True)
class BlockClassificationContext:
    page_width: float
    page_height: float
    region: ReadingOrderRegion = ReadingOrderRegion.BODY
    body_font_size: float | None = None
    native_kind: NativeBlockKind | None = None
    is_first_content_block: bool = False


@dataclass(frozen=True, slots=True)
class BlockClassificationWarning:
    code: Literal["BLOCK_CLASSIFICATION_UNCERTAIN"]
    reason: ClassificationUncertainty


@dataclass(frozen=True, slots=True)
class BlockClassificationResult:
    block_type: BlockType
    confidence: float
    evidence: tuple[str, ...]
    warnings: tuple[BlockClassificationWarning, ...]

    @property
    def is_certain(self) -> bool:
        return not self.warnings


def classify_block(
    block: TextBlockCandidate,
    context: BlockClassificationContext,
) -> BlockClassificationResult:
    _validate_input(block, context)
    if context.native_kind is NativeBlockKind.IMAGE:
        return _classified(BlockType.IMAGE, 1.0, "native image signal")
    if context.native_kind is NativeBlockKind.TABLE:
        return _classified(BlockType.TABLE, 1.0, "native table signal")

    text = block.source_text.strip()
    if not text:
        return _unknown(ClassificationUncertainty.EMPTY_CONTENT, 0.0)

    lines = tuple(line.strip() for line in text.splitlines() if line.strip())
    if _is_page_number(text, context.region):
        return _classified(BlockType.PAGE_NUMBER, 0.98, "edge-region number pattern")
    if lines and all(_LIST_ITEM.match(line) for line in lines):
        return _classified(BlockType.LIST, 0.95, "list marker pattern")
    if _CAPTION.match(text):
        return _classified(BlockType.CAPTION, 0.95, "numbered caption pattern")
    if _looks_like_code(text, block.font_name):
        return _classified(BlockType.CODE_BLOCK, 0.90, "code typography or syntax")

    typography = _typographic_type(block, context, len(text.split()), len(lines))
    if typography is not None:
        return typography

    if context.region is ReadingOrderRegion.HEADER:
        return _classified(BlockType.HEADER, 0.85, "header layout region")
    if context.region is ReadingOrderRegion.FOOTER:
        return _classified(BlockType.FOOTER, 0.85, "footer layout region")
    if len(text.split()) >= 4 or len(text) >= 24 or len(lines) >= 2:
        return _classified(BlockType.PARAGRAPH, 0.80, "body prose shape")
    return _unknown(ClassificationUncertainty.INSUFFICIENT_EVIDENCE, 0.35)


def _typographic_type(
    block: TextBlockCandidate,
    context: BlockClassificationContext,
    word_count: int,
    line_count: int,
) -> BlockClassificationResult | None:
    if block.font_size is None or context.body_font_size is None:
        return None
    ratio = block.font_size / context.body_font_size
    is_short = word_count <= 16 and line_count <= 2
    if ratio >= 1.55 and is_short and context.is_first_content_block:
        return _classified(BlockType.DOCUMENT_TITLE, 0.96, "large first-block typography")
    if ratio >= 1.18 and is_short:
        return _classified(BlockType.HEADING_1, 0.90, "larger-than-body typography")
    if is_short and _is_bold_font(block.font_name):
        return _classified(BlockType.HEADING_1, 0.75, "bold short-block typography")
    return None


def _looks_like_code(text: str, font_name: str | None) -> bool:
    if font_name is not None and any(marker in font_name.lower() for marker in _MONOSPACE_MARKERS):
        return True
    return bool(_CODE_PREFIX.match(text)) or ("{" in text and "}" in text and ";" in text)


def _is_page_number(text: str, region: ReadingOrderRegion) -> bool:
    if region is ReadingOrderRegion.BODY:
        return False
    compact = " ".join(text.split())
    return bool(_ARABIC_PAGE_NUMBER.fullmatch(compact) or _ROMAN_PAGE_NUMBER.fullmatch(compact))


def _is_bold_font(font_name: str | None) -> bool:
    if font_name is None:
        return False
    lowered = font_name.lower()
    return "bold" in lowered or "semibold" in lowered or "demi" in lowered


def _classified(
    block_type: BlockType,
    confidence: float,
    evidence: str,
) -> BlockClassificationResult:
    return BlockClassificationResult(
        block_type=block_type,
        confidence=confidence,
        evidence=(evidence,),
        warnings=(),
    )


def _unknown(
    reason: ClassificationUncertainty,
    confidence: float,
) -> BlockClassificationResult:
    return BlockClassificationResult(
        block_type=BlockType.UNKNOWN,
        confidence=confidence,
        evidence=(),
        warnings=(
            BlockClassificationWarning(
                code="BLOCK_CLASSIFICATION_UNCERTAIN",
                reason=reason,
            ),
        ),
    )


def _validate_input(
    block: TextBlockCandidate,
    context: BlockClassificationContext,
) -> None:
    if not _positive_finite(context.page_width) or not _positive_finite(context.page_height):
        raise ValueError("Page dimensions must be finite and positive.")
    if context.body_font_size is not None and not _positive_finite(context.body_font_size):
        raise ValueError("Body font size must be finite and positive when provided.")
    geometry = block.geometry
    values = (geometry.x, geometry.y, geometry.width, geometry.height)
    if not all(math.isfinite(value) for value in values):
        raise ValueError("Block geometry must be finite.")
    if geometry.x < 0 or geometry.y < 0 or geometry.width <= 0 or geometry.height <= 0:
        raise ValueError("Block geometry must have non-negative position and positive size.")
    if (
        geometry.x + geometry.width > context.page_width
        or geometry.y + geometry.height > context.page_height
    ):
        raise ValueError("Block geometry must remain within the page.")


def _positive_finite(value: float) -> bool:
    return not isinstance(value, bool) and math.isfinite(value) and value > 0
