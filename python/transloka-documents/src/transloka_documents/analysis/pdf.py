import math
from contextlib import closing
from dataclasses import dataclass
from io import BufferedReader, BytesIO
from typing import BinaryIO, cast

import pdfplumber
import pypdfium2 as pdfium  # type: ignore[import-untyped]
from pypdf import PdfReader


@dataclass(frozen=True, slots=True)
class PdfPageAnalysis:
    page_number: int
    width_points: float
    height_points: float
    rotation_degrees: int
    has_text_layer: bool


@dataclass(frozen=True, slots=True)
class PdfAnalysisResult:
    title: str | None
    author: str | None
    pages: tuple[PdfPageAnalysis, ...]

    @property
    def page_count(self) -> int:
        return len(self.pages)

    @property
    def text_layer_estimate(self) -> float:
        if not self.pages:
            return 0.0
        return sum(page.has_text_layer for page in self.pages) / len(self.pages)


class PdfAnalysisError(RuntimeError):
    pass


def analyze_pdf(stream: BinaryIO) -> PdfAnalysisResult:
    title, author = _read_metadata(stream)
    try:
        text_presence = _read_text_presence(stream)
        pages = _read_pages(stream, text_presence)
    except Exception as exc:
        raise PdfAnalysisError("The PDF pages could not be analyzed safely.") from exc
    return PdfAnalysisResult(title=title, author=author, pages=pages)


def _read_metadata(stream: BinaryIO) -> tuple[str | None, str | None]:
    try:
        stream.seek(0)
        metadata = PdfReader(stream, strict=False).metadata
        if metadata is None:
            return None, None
        return _clean_text(metadata.title), _clean_text(metadata.author)
    except Exception:
        return None, None


def _read_text_presence(stream: BinaryIO) -> tuple[bool, ...]:
    stream.seek(0)
    typed_stream = cast(BufferedReader | BytesIO, stream)
    with pdfplumber.open(typed_stream) as document:
        return tuple(bool((page.extract_text() or "").strip()) for page in document.pages)


def _read_pages(
    stream: BinaryIO,
    text_presence: tuple[bool, ...],
) -> tuple[PdfPageAnalysis, ...]:
    stream.seek(0)
    pages: list[PdfPageAnalysis] = []
    with pdfium.PdfDocument(stream, autoclose=False) as document:
        if len(document) != len(text_presence):
            raise ValueError("PDF parsers returned inconsistent page counts.")
        for page_index in range(len(document)):
            with closing(document[page_index]) as page:
                width, height = page.get_size()
                rotation = int(page.get_rotation())
                if (
                    not math.isfinite(width)
                    or not math.isfinite(height)
                    or width <= 0
                    or height <= 0
                    or rotation not in {0, 90, 180, 270}
                ):
                    raise ValueError("The PDF contains invalid page geometry.")
                pages.append(
                    PdfPageAnalysis(
                        page_number=page_index + 1,
                        width_points=float(width),
                        height_points=float(height),
                        rotation_degrees=rotation,
                        has_text_layer=text_presence[page_index],
                    )
                )
    return tuple(pages)


def _clean_text(value: str | None) -> str | None:
    if not isinstance(value, str):
        return None
    return value.strip() or None
