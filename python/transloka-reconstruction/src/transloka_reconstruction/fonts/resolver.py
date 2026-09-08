"""Safe font discovery and deterministic font resolution.

The resolver only keeps references and metadata for candidate fonts.  It never
copies or extracts bytes from an embedded source font, which keeps proprietary
fonts out of the output unless the caller has explicitly reviewed their use.
"""

from __future__ import annotations

import os
import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Self


class FontCategory(StrEnum):
    """Broad fallback families used by the reconstruction engine."""

    SERIF = "SERIF"
    SANS_SERIF = "SANS_SERIF"
    MONOSPACE = "MONOSPACE"
    DISPLAY = "DISPLAY"
    SYMBOL = "SYMBOL"


class FontResolutionStage(StrEnum):
    """Step at which a font candidate was selected."""

    EMBEDDED = "EMBEDDED"
    SYSTEM = "SYSTEM"
    METRIC_COMPATIBLE = "METRIC_COMPATIBLE"
    CONFIGURED_FALLBACK = "CONFIGURED_FALLBACK"
    UNIVERSAL_FALLBACK = "UNIVERSAL_FALLBACK"


class FontEmbeddingStatus(StrEnum):
    """How a resolved font may be referenced by a renderer."""

    EMBEDDED = "EMBEDDED"
    SUBSET_EMBEDDED = "SUBSET_EMBEDDED"
    SYSTEM_REFERENCE = "SYSTEM_REFERENCE"
    NOT_EMBEDDED = "NOT_EMBEDDED"


class FontResolutionWarning(StrEnum):
    """Stable warning codes emitted by the resolver."""

    PROPRIETARY_FONT_SKIPPED = "PROPRIETARY_FONT_SKIPPED"
    MISSING_GLYPH_WARNING = "MISSING_GLYPH_WARNING"


def _category(value: FontCategory | str) -> FontCategory:
    if isinstance(value, FontCategory):
        return value
    if type(value) is not str:
        raise ValueError("Font category must be a known category name.")
    try:
        return FontCategory(value)
    except ValueError as exc:
        allowed = ", ".join(member.value for member in FontCategory)
        raise ValueError(f"Font category must be one of: {allowed}.") from exc


def _non_empty_text(value: object, field_name: str) -> str:
    if type(value) is not str or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string.")
    return value.strip()


def _bool(value: object, field_name: str) -> bool:
    if type(value) is not bool:
        raise ValueError(f"{field_name} must be a boolean.")
    return value


def _normalise_family(value: str) -> str:
    value = re.sub(r"^[A-Z]{6}\+", "", value.removeprefix("/").strip()).casefold()
    value = re.sub(r"(?:ps)?mt$", "", value)
    value = re.sub(
        r"[-_, ]?(bolditalic|boldoblique|semibolditalic|semibold|bold|italic|oblique|regular|medium|light)$",
        "",
        value,
    )
    return re.sub(r"[-_, ]", "", value.removesuffix("ps"))


def _required_glyphs(text: str) -> frozenset[str]:
    return frozenset(character for character in text if not character.isspace())


@dataclass(frozen=True, slots=True)
class FontDescriptor:
    """Metadata for a usable font reference.

    ``path`` is informational only.  The resolver never reads or copies it.
    For embedded fonts, ``legal_to_use`` must be true before the descriptor is
    eligible for selection.
    """

    family_name: str
    category: FontCategory = FontCategory.SANS_SERIF
    path: Path | None = None
    metric_group: str | None = None
    glyphs: frozenset[str] | None = None
    usable: bool = True
    embedded: bool = False
    legal_to_use: bool = False
    subsettable: bool = False
    proprietary: bool = False
    weight: int = 400
    italic: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "family_name", _non_empty_text(self.family_name, "family_name"))
        object.__setattr__(self, "category", _category(self.category))
        if self.path is not None and not isinstance(self.path, Path):
            object.__setattr__(self, "path", Path(self.path))
        if self.metric_group is not None:
            object.__setattr__(
                self,
                "metric_group",
                _non_empty_text(self.metric_group, "metric_group"),
            )
        if self.glyphs is not None:
            glyphs = frozenset(self.glyphs)
            if any(type(character) is not str for character in glyphs):
                raise ValueError("glyphs must contain strings.")
            object.__setattr__(self, "glyphs", glyphs)
        for field_name in (
            "usable",
            "embedded",
            "legal_to_use",
            "subsettable",
            "proprietary",
            "italic",
        ):
            _bool(getattr(self, field_name), field_name)
        if (
            isinstance(self.weight, bool)
            or type(self.weight) is not int
            or not 100 <= self.weight <= 900
        ):
            raise ValueError("weight must be an integer between 100 and 900.")

    @property
    def effective_metric_group(self) -> str:
        return self.metric_group or self.category.value

    @property
    def family_key(self) -> str:
        return _normalise_family(self.family_name)

    def supports(self, text: str) -> bool:
        """Return whether this descriptor is known to cover all required glyphs."""

        return self.glyphs is None or not (_required_glyphs(text) - self.glyphs)

    def missing_glyphs(self, text: str) -> frozenset[str]:
        if self.glyphs is None:
            return frozenset()
        return _required_glyphs(text) - self.glyphs


@dataclass(frozen=True, slots=True)
class FontRequest:
    """Source font information needed to resolve one text run."""

    source_family: str
    category: FontCategory = FontCategory.SANS_SERIF
    text: str = ""
    embedded_fonts: tuple[FontDescriptor, ...] = ()
    metric_group: str | None = None
    weight: int = 400
    italic: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(
            self, "source_family", _non_empty_text(self.source_family, "source_family")
        )
        object.__setattr__(self, "category", _category(self.category))
        if type(self.text) is not str:
            raise ValueError("text must be a string.")
        if self.metric_group is not None:
            object.__setattr__(
                self,
                "metric_group",
                _non_empty_text(self.metric_group, "metric_group"),
            )
        if (
            isinstance(self.weight, bool)
            or type(self.weight) is not int
            or not 100 <= self.weight <= 900
        ):
            raise ValueError("weight must be an integer between 100 and 900.")
        _bool(self.italic, "italic")
        embedded_fonts = tuple(self.embedded_fonts)
        if any(type(font) is not FontDescriptor for font in embedded_fonts):
            raise TypeError("embedded_fonts must contain FontDescriptor values.")
        object.__setattr__(self, "embedded_fonts", embedded_fonts)

    @property
    def effective_metric_group(self) -> str:
        return self.metric_group or self.category.value


@dataclass(frozen=True, slots=True)
class FontResolution:
    """Selected font and auditable resolution metadata."""

    request: FontRequest
    font: FontDescriptor
    stage: FontResolutionStage
    embedding_status: FontEmbeddingStatus
    missing_glyphs: frozenset[str] = frozenset()
    warnings: tuple[FontResolutionWarning, ...] = ()

    @property
    def family_name(self) -> str:
        return self.font.family_name

    @property
    def can_embed(self) -> bool:
        return self.embedding_status in {
            FontEmbeddingStatus.EMBEDDED,
            FontEmbeddingStatus.SUBSET_EMBEDDED,
        }

    def to_dict(self) -> dict[str, object]:
        return {
            "source_family": self.request.source_family,
            "resolved_family": self.font.family_name,
            "stage": self.stage.value,
            "embedding_status": self.embedding_status.value,
            "missing_glyphs": sorted(self.missing_glyphs),
            "warnings": [warning.value for warning in self.warnings],
        }


class FontResolver:
    """Resolve fonts with the documented safe fallback order."""

    def __init__(
        self,
        system_fonts: Iterable[FontDescriptor] = (),
        *,
        available_fonts: Iterable[FontDescriptor] | None = None,
        configured_fallbacks: Mapping[FontCategory | str, FontDescriptor | Iterable[FontDescriptor]]
        | None = None,
        universal_fallback: FontDescriptor | None = None,
    ) -> None:
        if available_fonts is not None:
            if tuple(system_fonts):
                raise ValueError("Pass either system_fonts or available_fonts, not both.")
            system_fonts = available_fonts
        self._system_fonts = _font_tuple(system_fonts, "system_fonts")
        self._configured_fallbacks = self._normalise_fallbacks(configured_fallbacks)
        self._universal_fallback = universal_fallback or FontDescriptor(
            family_name="Noto Sans",
            category=FontCategory.SANS_SERIF,
            metric_group=FontCategory.SANS_SERIF.value,
            usable=True,
        )
        if type(self._universal_fallback) is not FontDescriptor:
            raise TypeError("universal_fallback must be a FontDescriptor.")

    @classmethod
    def from_system(cls) -> Self:
        """Create a resolver using read-only metadata from local font folders."""

        return cls(discover_system_fonts())

    def resolve(
        self,
        request: FontRequest | str,
        *,
        category: FontCategory | str = FontCategory.SANS_SERIF,
        text: str = "",
        embedded_fonts: Iterable[FontDescriptor] = (),
        metric_group: str | None = None,
        weight: int = 400,
        italic: bool = False,
    ) -> FontResolution:
        """Resolve a request without reading or copying any font file."""

        if isinstance(request, str):
            request = FontRequest(
                source_family=request,
                category=_category(category),
                text=text,
                embedded_fonts=tuple(embedded_fonts),
                metric_group=metric_group,
                weight=weight,
                italic=italic,
            )
        elif type(request) is not FontRequest:
            raise TypeError("request must be a FontRequest or source family string.")

        warnings: list[FontResolutionWarning] = []
        partial: tuple[FontDescriptor, FontResolutionStage] | None = None
        stages: tuple[tuple[FontResolutionStage, tuple[FontDescriptor, ...]], ...] = (
            (FontResolutionStage.EMBEDDED, request.embedded_fonts),
            (
                FontResolutionStage.SYSTEM,
                tuple(
                    font
                    for font in self._system_fonts
                    if font.family_key == _normalise_family(request.source_family)
                ),
            ),
            (
                FontResolutionStage.METRIC_COMPATIBLE,
                tuple(
                    font
                    for font in self._system_fonts
                    if font.effective_metric_group == request.effective_metric_group
                ),
            ),
            (
                FontResolutionStage.CONFIGURED_FALLBACK,
                self._configured_fallbacks.get(request.category, ()),
            ),
            (FontResolutionStage.UNIVERSAL_FALLBACK, (self._universal_fallback,)),
        )

        for stage, candidates in stages:
            usable: list[FontDescriptor] = []
            for font in candidates:
                if type(font) is not FontDescriptor or not font.usable:
                    continue
                if stage is FontResolutionStage.EMBEDDED and not font.legal_to_use:
                    warnings.append(FontResolutionWarning.PROPRIETARY_FONT_SKIPPED)
                    continue
                usable.append(font)
            if not usable:
                continue

            matching = [font for font in usable if font.supports(request.text)]
            selected = min(matching or usable, key=lambda font: _style_distance(font, request))
            if not matching and partial is None:
                partial = (selected, stage)
            if matching:
                return self._result(request, selected, stage, warnings)

        if partial is not None:
            return self._result(request, partial[0], partial[1], warnings)

        # The built-in universal descriptor is intentionally metadata-only and
        # is a final safety net for an empty or unusable configured catalog.
        return self._result(
            request,
            self._universal_fallback,
            FontResolutionStage.UNIVERSAL_FALLBACK,
            warnings,
        )

    def _result(
        self,
        request: FontRequest,
        font: FontDescriptor,
        stage: FontResolutionStage,
        warnings: list[FontResolutionWarning],
    ) -> FontResolution:
        missing = font.missing_glyphs(request.text)
        result_warnings = list(dict.fromkeys(warnings))
        if missing:
            result_warnings.append(FontResolutionWarning.MISSING_GLYPH_WARNING)
        return FontResolution(
            request=request,
            font=font,
            stage=stage,
            embedding_status=_embedding_status(font, stage),
            missing_glyphs=missing,
            warnings=tuple(dict.fromkeys(result_warnings)),
        )

    @staticmethod
    def _normalise_fallbacks(
        configured: Mapping[FontCategory | str, FontDescriptor | Iterable[FontDescriptor]] | None,
    ) -> dict[FontCategory, tuple[FontDescriptor, ...]]:
        result = _default_fallbacks()
        if configured is None:
            return result
        for key, value in configured.items():
            category = _category(key)
            if isinstance(value, FontDescriptor):
                result[category] = (value,)
            else:
                result[category] = _font_tuple(value, f"configured_fallbacks[{category.value}]")
        return result


def _font_tuple(values: Iterable[FontDescriptor], field_name: str) -> tuple[FontDescriptor, ...]:
    result = tuple(values)
    if any(type(font) is not FontDescriptor for font in result):
        raise TypeError(f"{field_name} must contain FontDescriptor values.")
    return result


def _style_distance(font: FontDescriptor, request: FontRequest) -> tuple[int, int]:
    return (abs(font.weight - request.weight), int(font.italic is not request.italic))


def _embedding_status(font: FontDescriptor, stage: FontResolutionStage) -> FontEmbeddingStatus:
    if stage is FontResolutionStage.EMBEDDED:
        return (
            FontEmbeddingStatus.SUBSET_EMBEDDED
            if font.subsettable
            else FontEmbeddingStatus.EMBEDDED
        )
    if stage is FontResolutionStage.SYSTEM:
        return FontEmbeddingStatus.SYSTEM_REFERENCE
    return FontEmbeddingStatus.NOT_EMBEDDED


def _default_fallbacks() -> dict[FontCategory, tuple[FontDescriptor, ...]]:
    values = {
        FontCategory.SERIF: "Noto Serif",
        FontCategory.SANS_SERIF: "Noto Sans",
        FontCategory.MONOSPACE: "Noto Sans Mono",
        FontCategory.DISPLAY: "Noto Sans",
        FontCategory.SYMBOL: "Noto Sans Symbols",
    }
    return {
        category: (
            FontDescriptor(
                family_name=family,
                category=category,
                metric_group=category.value,
            ),
        )
        for category, family in values.items()
    }


def _infer_category(family_name: str) -> FontCategory:
    name = family_name.casefold()
    if any(marker in name for marker in ("mono", "code", "courier", "consol")):
        return FontCategory.MONOSPACE
    if any(marker in name for marker in ("symbol", "emoji", "dingbat")):
        return FontCategory.SYMBOL
    if any(marker in name for marker in ("serif", "times", "georgia", "garamond")):
        return FontCategory.SERIF
    if any(marker in name for marker in ("display", "poster", "headline")):
        return FontCategory.DISPLAY
    return FontCategory.SANS_SERIF


def _family_from_filename(path: Path) -> str:
    family = re.sub(
        r"[-_ ]?(bolditalic|semibolditalic|bold|italic|oblique|regular|medium|light|semibold)$",
        "",
        path.stem,
        flags=re.IGNORECASE,
    )
    return family.replace("_", " ").replace("-", " ").strip() or path.stem


def discover_system_fonts(paths: Iterable[Path] | None = None) -> tuple[FontDescriptor, ...]:
    """Discover local font files without opening or copying them.

    Names are inferred from filenames because this package intentionally has no
    font parsing dependency.  Callers that need exact names can inject a
    catalog of :class:`FontDescriptor` values instead.
    """

    roots = tuple(paths) if paths is not None else _default_font_paths()
    suffixes = {".ttf", ".otf", ".ttc"}
    discovered: list[FontDescriptor] = []
    seen: set[tuple[str, str]] = set()
    for root in roots:
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("*")):
            if not path.is_file() or path.suffix.casefold() not in suffixes:
                continue
            family = _family_from_filename(path)
            key = (str(path).casefold(), _normalise_family(family))
            if key in seen:
                continue
            seen.add(key)
            discovered.append(
                FontDescriptor(
                    family_name=family,
                    category=_infer_category(family),
                    path=path,
                    metric_group=_infer_category(family).value,
                    usable=True,
                )
            )
    return tuple(discovered)


def _default_font_paths() -> tuple[Path, ...]:
    roots: list[Path] = []
    windows_root = os.environ.get("WINDIR")
    if windows_root:
        roots.append(Path(windows_root) / "Fonts")
    roots.extend(
        (
            Path("/usr/share/fonts"),
            Path("/usr/local/share/fonts"),
            Path("/Library/Fonts"),
            Path("/System/Library/Fonts"),
        )
    )
    return tuple(dict.fromkeys(roots))


def resolve_font(
    source_family: str,
    *,
    resolver: FontResolver | None = None,
    category: FontCategory | str = FontCategory.SANS_SERIF,
    text: str = "",
    embedded_fonts: Iterable[FontDescriptor] = (),
    metric_group: str | None = None,
    weight: int = 400,
    italic: bool = False,
) -> FontResolution:
    """Convenience wrapper around :class:`FontResolver`."""

    active_resolver = resolver or FontResolver()
    return active_resolver.resolve(
        source_family,
        category=category,
        text=text,
        embedded_fonts=embedded_fonts,
        metric_group=metric_group,
        weight=weight,
        italic=italic,
    )
