"""Connect the metadata resolver to real, locally installed TrueType faces.

Only the trusted local catalog supplies paths; document font names are lookup
keys, never filenames. Source PDF font programs are not extracted. Unsupported
outlines and fonts whose OS/2 flags prohibit embedding or subsetting are skipped.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass, replace
from functools import lru_cache
from hashlib import sha256
from io import BytesIO
from pathlib import Path
from struct import error as StructError
from threading import RLock
from typing import Any

from reportlab.pdfbase import pdfmetrics  # type: ignore[import-untyped]
from reportlab.pdfbase.ttfonts import TTFError, TTFont, TTFontFile  # type: ignore[import-untyped]

from .resolver import (
    FontCategory,
    FontDescriptor,
    FontEmbeddingStatus,
    FontResolution,
    FontResolutionStage,
    FontResolver,
    _normalise_family,
    discover_system_fonts,
)

_REGISTRATION_LOCK = RLock()
_MAX_FONT_BYTES = 32 * 1024 * 1024


class FontRenderingError(ValueError):
    """A font cannot safely render all of the translated characters."""


@dataclass(frozen=True)
class RenderFont:
    name: str
    resolution: FontResolution

    def metadata(self) -> dict[str, object]:
        result = self.resolution.to_dict()
        result["weight"] = self.resolution.font.weight
        result["italic"] = self.resolution.font.italic
        if self.resolution.stage is not FontResolutionStage.SYSTEM:
            result["warnings"] = [*self.resolution.warnings, "FONT_FALLBACK"]
        return result


def _metric_group(name: str) -> str:
    key = _normalise_family(name)
    for group in (
        ("arial", "helvetica", "liberationsans"),
        ("timesnewroman", "timesroman", "times", "liberationserif"),
        ("couriernew", "courier", "liberationmono"),
        ("calibri", "carlito"),
        ("cambria", "caladea"),
    ):
        if key in group:
            return group[0]
    return key


def _font_bytes(path: Path) -> bytes:
    if path.is_symlink() or path.stat().st_size > _MAX_FONT_BYTES:
        raise ValueError("Local font is not eligible for rendering.")
    with path.open("rb") as stream:
        data = stream.read(_MAX_FONT_BYTES + 1)
    if len(data) > _MAX_FONT_BYTES:
        raise ValueError("Local font is too large.")
    return data


def _embedding_allowed(face: Any) -> bool:
    if "OS/2" not in face.table:
        return False
    face.seek_table("OS/2")
    face.skip(8)
    flags = int(face.read_ushort())
    # Allow installable, preview/print, or editable embedding; reject restricted,
    # no-subsetting, bitmap-only and unknown flags regardless of ReportLab config.
    return flags & ~0x000C == 0


def _name(value: Any) -> str:
    return str(value.ustr) if hasattr(value, "ustr") else str(value)


def _standard_glyphs(text: str, encoding: str) -> frozenset[str]:
    supported: set[str] = set()
    for character in set(text):
        try:
            character.encode(encoding.removesuffix("Encoding").lower())
            supported.add(character)
        except UnicodeEncodeError:
            continue
    return frozenset(supported)


def _catalog(paths: Iterable[Path]) -> tuple[FontDescriptor, ...]:
    fonts: list[FontDescriptor] = []
    for path in paths:
        try:
            face = TTFontFile(BytesIO(_font_bytes(path)), charInfo=0)
            if not _embedding_allowed(face):
                continue
            face.seek_table("OS/2")
            face.skip(4)
            weight = int(face.read_ushort())
            for family in dict.fromkeys((_name(face.familyName), _name(face.name))):
                fonts.append(
                    FontDescriptor(
                        family_name=family,
                        path=path,
                        metric_group=_metric_group(family),
                        weight=min(900, max(100, weight)),
                        italic=bool(face.italicAngle),
                        legal_to_use=True,
                        subsettable=True,
                    )
                )
        except (OSError, ValueError, KeyError, IndexError, StructError, TTFError):
            continue
    return tuple(fonts)


@lru_cache(maxsize=1)
def _system_catalog() -> tuple[FontDescriptor, ...]:
    # Metadata is stable for a worker lifetime; restart after installing fonts.
    return _catalog(font.path for font in discover_system_fonts() if font.path is not None)


class ReportLabFontCatalog:
    """Resolve, check glyph coverage, and register only fonts used by a render."""

    def __init__(self, *, paths: Iterable[Path] | None = None) -> None:
        self._fonts = _catalog(paths) if paths is not None else None
        self._loaded: dict[Path, tuple[str, frozenset[str]] | None] = {}

    def resolve(self, source: str, text: str, *, fallback: str) -> RenderFont:
        fallback_face = pdfmetrics.getFont(fallback)
        category = (
            FontCategory.MONOSPACE
            if fallback.startswith("Courier")
            else FontCategory.SERIF
            if fallback.startswith("Times")
            else FontCategory.SANS_SERIF
        )
        standard = FontDescriptor(
            family_name=fallback,
            category=category,
            metric_group=_metric_group(fallback),
            glyphs=_standard_glyphs(text, fallback_face.encName),
            weight=700 if fallback_face.face.bold else 400,
            italic=bool(fallback_face.face.italic),
        )
        source_name = re.sub(r"^[A-Z]{6}\+", "", source.strip().removeprefix("/"))
        if (
            source_name in pdfmetrics.standardFonts
            and source_name == fallback
            and standard.supports(text)
        ):
            return RenderFont(fallback, FontResolver((standard,)).resolve(source, text=text))
        fonts = self._fonts if self._fonts is not None else _system_catalog()
        candidates = list(fonts)
        while True:
            resolution = FontResolver(
                candidates,
                configured_fallbacks={category: (standard,)},
                universal_fallback=standard,
            ).resolve(
                source,
                text=text,
                category=category,
                metric_group=_metric_group(source),
                weight=standard.weight,
                italic=standard.italic,
            )
            path = resolution.font.path
            if path is None:
                if resolution.missing_glyphs:
                    raise FontRenderingError(
                        "MISSING_GLYPH_WARNING: no usable font covers the text."
                    )
                return RenderFont(fallback, resolution)
            loaded = self._load(path)
            if loaded is not None and all(c.isspace() or c in loaded[1] for c in text):
                return RenderFont(
                    loaded[0],
                    replace(
                        resolution,
                        embedding_status=FontEmbeddingStatus.SUBSET_EMBEDDED,
                    ),
                )
            candidates = [font for font in candidates if font.path != path]

    def _load(self, path: Path) -> tuple[str, frozenset[str]] | None:
        if path not in self._loaded:
            try:
                data = _font_bytes(path)
                name = "TransLoka_" + sha256(data).hexdigest()
                with _REGISTRATION_LOCK:
                    font = TTFont(name, BytesIO(data))
                    if not _embedding_allowed(font.face):
                        raise ValueError("Font does not permit embedding.")
                    glyphs = frozenset(
                        chr(code)
                        for code in font.face.charToGlyph
                        if font.face.charToGlyph[code] != 0
                    )
                    pdfmetrics.registerFont(font)
                self._loaded[path] = (name, glyphs)
            except (OSError, ValueError, KeyError, IndexError, StructError, TTFError):
                self._loaded[path] = None
        return self._loaded[path]
