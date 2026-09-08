from pathlib import Path

import pytest
from transloka_reconstruction.fonts import (
    FontCategory,
    FontDescriptor,
    FontEmbeddingStatus,
    FontRequest,
    FontResolutionStage,
    FontResolutionWarning,
    FontResolver,
)

LATIN = frozenset("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ ,.!?")


def _font(
    family: str,
    *,
    category: FontCategory = FontCategory.SANS_SERIF,
    metric_group: str | None = None,
    glyphs: frozenset[str] | None = LATIN,
    path: Path | None = None,
    usable: bool = True,
    embedded: bool = False,
    legal_to_use: bool = False,
    subsettable: bool = False,
    proprietary: bool = False,
    weight: int = 400,
    italic: bool = False,
) -> FontDescriptor:
    return FontDescriptor(
        family_name=family,
        category=category,
        metric_group=metric_group,
        glyphs=glyphs,
        path=path,
        usable=usable,
        embedded=embedded,
        legal_to_use=legal_to_use,
        subsettable=subsettable,
        proprietary=proprietary,
        weight=weight,
        italic=italic,
    )


def test_available_system_font_is_selected_before_fallback() -> None:
    resolver = FontResolver(system_fonts=(_font("Acme Sans"), _font("Noto Sans")))

    result = resolver.resolve("Acme Sans", text="Hello")

    assert result.family_name == "Acme Sans"
    assert result.stage is FontResolutionStage.SYSTEM
    assert result.embedding_status is FontEmbeddingStatus.SYSTEM_REFERENCE
    assert result.warnings == ()


def test_unavailable_font_uses_universal_fallback() -> None:
    universal = _font("Universal Sans", glyphs=None)
    resolver = FontResolver(
        system_fonts=(),
        configured_fallbacks={FontCategory.SANS_SERIF: ()},
        universal_fallback=universal,
    )

    result = resolver.resolve("Missing Family", text="Hello")

    assert result.family_name == "Universal Sans"
    assert result.stage is FontResolutionStage.UNIVERSAL_FALLBACK
    assert result.missing_glyphs == frozenset()


@pytest.mark.parametrize(
    ("category", "expected"),
    [
        (FontCategory.SERIF, "Noto Serif"),
        (FontCategory.SANS_SERIF, "Noto Sans"),
        (FontCategory.MONOSPACE, "Noto Sans Mono"),
    ],
)
def test_configured_category_fallbacks(category: FontCategory, expected: str) -> None:
    result = FontResolver().resolve("Missing Family", category=category, text="Hello")

    assert result.family_name == expected
    assert result.stage is FontResolutionStage.CONFIGURED_FALLBACK


def test_metric_compatible_font_precedes_configured_fallback() -> None:
    metric_font = _font("Metric Sans", metric_group="body-sans")
    fallback = _font("Configured Sans")
    resolver = FontResolver(
        system_fonts=(metric_font,),
        configured_fallbacks={FontCategory.SANS_SERIF: fallback},
    )

    result = resolver.resolve(
        FontRequest(
            source_family="Missing Family",
            category=FontCategory.SANS_SERIF,
            metric_group="body-sans",
            text="Hello",
        )
    )

    assert result.family_name == "Metric Sans"
    assert result.stage is FontResolutionStage.METRIC_COMPATIBLE


def test_legal_embedded_font_is_selected_without_copying_source_bytes(tmp_path: Path) -> None:
    source_path = tmp_path / "source-proprietary.ttf"
    source_path.write_bytes(b"font bytes are never read by the resolver")
    embedded = _font(
        "Embedded Reviewed",
        embedded=True,
        legal_to_use=True,
        subsettable=True,
        path=source_path,
    )

    result = FontResolver().resolve("Embedded Reviewed", embedded_fonts=(embedded,), text="Hello")

    assert result.stage is FontResolutionStage.EMBEDDED
    assert result.embedding_status is FontEmbeddingStatus.SUBSET_EMBEDDED
    assert result.can_embed is True
    assert source_path.read_bytes() == b"font bytes are never read by the resolver"


def test_unreviewed_proprietary_embedded_font_is_skipped() -> None:
    embedded = _font("Vendor Font", embedded=True, proprietary=True, legal_to_use=False)

    result = FontResolver().resolve("Vendor Font", embedded_fonts=(embedded,), text="Hello")

    assert result.stage is FontResolutionStage.CONFIGURED_FALLBACK
    assert FontResolutionWarning.PROPRIETARY_FONT_SKIPPED in result.warnings


def test_missing_glyph_is_reported_when_no_candidate_covers_text() -> None:
    universal = _font("Universal", glyphs=frozenset("abc"))
    resolver = FontResolver(
        system_fonts=(),
        configured_fallbacks={FontCategory.SANS_SERIF: ()},
        universal_fallback=universal,
    )

    result = resolver.resolve("Missing Family", text="abcΩ")

    assert result.missing_glyphs == frozenset({"Ω"})
    assert FontResolutionWarning.MISSING_GLYPH_WARNING in result.warnings


def test_invalid_descriptor_and_request_are_rejected() -> None:
    with pytest.raises(ValueError, match="family_name"):
        FontDescriptor(family_name=" ")
    with pytest.raises(ValueError, match="source_family"):
        FontRequest(source_family=" ")


@pytest.mark.parametrize("source", ["ABCDEF+Calibri-BoldItalic", "/Calibri", "Calibri-Bold"])
def test_pdf_subset_names_match_system_family(source: str) -> None:
    result = FontResolver((_font("Calibri"),)).resolve(source, text="Hello")
    assert result.stage is FontResolutionStage.SYSTEM


def test_postscript_name_matches_spaced_family() -> None:
    result = FontResolver((_font("Times New Roman"),)).resolve("TimesNewRomanPS-BoldMT")
    assert result.stage is FontResolutionStage.SYSTEM
