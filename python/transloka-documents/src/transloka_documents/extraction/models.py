from dataclasses import dataclass
from enum import StrEnum
from typing import Literal


class NormalizationKind(StrEnum):
    LIGATURE = "LIGATURE"
    SOFT_HYPHEN = "SOFT_HYPHEN"
    WHITESPACE = "WHITESPACE"
    VISUAL_LINE_BREAK = "VISUAL_LINE_BREAK"
    PRESERVED_LINE_BREAK = "PRESERVED_LINE_BREAK"
    HYPHENATED_LINE_BREAK = "HYPHENATED_LINE_BREAK"


@dataclass(frozen=True, slots=True)
class TextGeometry:
    x: float
    y: float
    width: float
    height: float
    coordinate_system: Literal["PDF_POINT_TOP_LEFT"] = "PDF_POINT_TOP_LEFT"


@dataclass(frozen=True, slots=True)
class NormalizationBoundary:
    kind: NormalizationKind
    source_start: int
    source_end: int
    normalized_start: int
    normalized_end: int
    source_text: str
    normalized_text: str


@dataclass(frozen=True, slots=True)
class NormalizedText:
    source_text: str
    text: str
    boundaries: tuple[NormalizationBoundary, ...]


@dataclass(frozen=True, slots=True)
class ExtractedCharacter:
    text: str
    geometry: TextGeometry
    font_name: str | None
    font_size: float | None
    upright: bool | None


@dataclass(frozen=True, slots=True)
class ExtractedWord:
    source_text: str
    normalized_text: str
    geometry: TextGeometry
    character_indexes: tuple[int, ...]
    normalization_boundaries: tuple[NormalizationBoundary, ...]
    font_name: str | None
    font_size: float | None
    upright: bool | None


@dataclass(frozen=True, slots=True)
class ExtractedLine:
    source_text: str
    normalized_text: str
    geometry: TextGeometry
    word_indexes: tuple[int, ...]
    character_indexes: tuple[int, ...]
    normalization_boundaries: tuple[NormalizationBoundary, ...]
    font_name: str | None
    font_size: float | None


@dataclass(frozen=True, slots=True)
class TextBlockCandidate:
    source_text: str
    normalized_text: str
    geometry: TextGeometry
    line_indexes: tuple[int, ...]
    word_indexes: tuple[int, ...]
    character_indexes: tuple[int, ...]
    normalization_boundaries: tuple[NormalizationBoundary, ...]
    font_name: str | None
    font_size: float | None


@dataclass(frozen=True, slots=True)
class ExtractedPage:
    page_number: int
    width_points: float
    height_points: float
    characters: tuple[ExtractedCharacter, ...]
    words: tuple[ExtractedWord, ...]
    lines: tuple[ExtractedLine, ...]
    block_candidates: tuple[TextBlockCandidate, ...]

    @property
    def has_text(self) -> bool:
        return bool(self.words)


@dataclass(frozen=True, slots=True)
class DigitalTextExtractionResult:
    pages: tuple[ExtractedPage, ...]

    @property
    def page_count(self) -> int:
        return len(self.pages)
