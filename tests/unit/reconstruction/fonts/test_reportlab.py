from pathlib import Path
from struct import pack_into

import pytest
import reportlab  # type: ignore[import-untyped]
from reportlab.pdfbase import pdfmetrics  # type: ignore[import-untyped]
from reportlab.pdfbase.ttfonts import TTFontFile  # type: ignore[import-untyped]
from transloka_reconstruction.fonts.reportlab import FontRenderingError, ReportLabFontCatalog
from transloka_reconstruction.fonts.resolver import FontEmbeddingStatus, FontResolutionStage


def _vera(name: str = "Vera.ttf") -> Path:
    return Path(reportlab.__file__).parent / "fonts" / name


@pytest.mark.parametrize(
    ("source", "fallback", "expected"),
    [
        ("ABCDEF+BitstreamVeraSans-Roman", "Helvetica", "BitstreamVeraSans-Roman"),
        ("Bitstream Vera Sans", "Helvetica-Bold", "BitstreamVeraSans-Bold"),
        ("BitstreamVeraSans-Oblique", "Helvetica-Oblique", "BitstreamVeraSans-Oblique"),
        ("BitstreamVeraSans-BoldOblique", "Helvetica-BoldOblique", "BitstreamVeraSans-BoldOblique"),
    ],
)
def test_real_font_family_style_and_measurement(source: str, fallback: str, expected: str) -> None:
    catalog = ReportLabFontCatalog(
        paths=(
            _vera(name)
            for name in (
                "Vera.ttf",
                "VeraBd.ttf",
                "VeraIt.ttf",
                "VeraBI.ttf",
            )
        )
    )
    rendered = catalog.resolve(source, "Terjemahan café", fallback=fallback)

    assert rendered.resolution.stage is FontResolutionStage.SYSTEM
    assert rendered.resolution.embedding_status is FontEmbeddingStatus.SUBSET_EMBEDDED
    face = pdfmetrics.getFont(rendered.name).face
    assert face.name.decode() == expected
    assert pdfmetrics.stringWidth("Terjemahan", rendered.name, 12) == pytest.approx(
        sum(face.charWidths[ord(c)] for c in "Terjemahan") * 12 / 1000
    )
    assert "path" not in str(rendered.metadata())


def test_missing_and_corrupt_font_use_explicit_fallback(tmp_path: Path) -> None:
    broken = tmp_path / "broken.ttf"
    broken.write_bytes(b"not a font")
    catalog = ReportLabFontCatalog(paths=(broken, tmp_path / "absent.ttf"))
    result = catalog.resolve("UnavailableSerif", "Teks Indonesia", fallback="Times-Bold")
    assert result.name == "Times-Bold"
    assert result.metadata()["warnings"] == ["FONT_FALLBACK"]


@pytest.mark.parametrize("flags", [2, 6, 0x100, 0x200, 0x104, 0x8000])
def test_embedding_restrictions_are_enforced(tmp_path: Path, flags: int) -> None:
    data = bytearray(_vera().read_bytes())
    face = TTFontFile(str(_vera()), charInfo=0)
    face.seek_table("OS/2")
    pack_into(">H", data, face._pos + 8, flags)
    restricted = tmp_path / "restricted.ttf"
    restricted.write_bytes(data)
    result = ReportLabFontCatalog(paths=(restricted,)).resolve(
        "Bitstream Vera Sans", "Teks", fallback="Helvetica"
    )
    assert result.name == "Helvetica"


def test_missing_glyph_cannot_silently_become_tofu() -> None:
    with pytest.raises(FontRenderingError, match="MISSING_GLYPH_WARNING"):
        ReportLabFontCatalog(paths=(_vera(),)).resolve(
            "Bitstream Vera Sans", "Teks \U0001f9ec", fallback="Helvetica"
        )


def test_font_name_is_never_opened_as_a_path(tmp_path: Path) -> None:
    source_name = str(tmp_path / "private.ttf")
    result = ReportLabFontCatalog(paths=()).resolve(source_name, "Teks", fallback="Helvetica")
    assert result.name == "Helvetica"


def test_style_does_not_select_regular_before_bold() -> None:
    result = ReportLabFontCatalog(paths=(_vera(), _vera("VeraBd.ttf"))).resolve(
        "BitstreamVeraSans-Bold", "Judul", fallback="Helvetica-Bold"
    )
    assert pdfmetrics.getFont(result.name).face.name == b"BitstreamVeraSans-Bold"


def test_standard_symbol_font_keeps_supported_glyph() -> None:
    result = ReportLabFontCatalog(paths=()).resolve("Symbol", "Ω", fallback="Symbol")
    assert result.name == "Symbol"
    assert result.resolution.missing_glyphs == frozenset()


@pytest.mark.parametrize("source", ["Helvetica", "/Helvetica", "ABCDEF+Helvetica"])
def test_standard_pdf_font_alias_does_not_trigger_system_substitution(
    source: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def unexpected_discovery() -> None:
        pytest.fail("A supported PDF base font must not require a system font scan.")

    monkeypatch.setattr(
        "transloka_reconstruction.fonts.reportlab._system_catalog",
        unexpected_discovery,
    )
    result = ReportLabFontCatalog().resolve(source, "Teks Indonesia", fallback="Helvetica")
    assert result.name == "Helvetica"
    assert result.resolution.stage is FontResolutionStage.SYSTEM
    assert result.metadata()["warnings"] == []
