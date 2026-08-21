from __future__ import annotations

import hashlib
from io import BytesIO
from typing import cast

import pypdfium2 as pdfium  # type: ignore[import-untyped]
from PIL import Image
from pypdf import PdfReader, PdfWriter
from pypdf.generic import ArrayObject, DictionaryObject, NameObject
from reportlab.lib.utils import ImageReader  # type: ignore[import-untyped]
from reportlab.pdfgen.canvas import Canvas  # type: ignore[import-untyped]
from transloka_reconstruction.overlay import (
    CoverRegion,
    OverlayPageGenerator,
    OverlayText,
    TextAlignment,
    generate_overlay_page,
    merge_overlay_page,
)
from transloka_reconstruction.overlay.cover import (
    CoverStrategy,
    CoverWarningCode,
    raster_background_fallback,
    solid_background_cover,
)


def _source_page(
    *lines: tuple[str, float, float], width: float = 300, height: float = 200
) -> bytes:
    output = BytesIO()
    canvas = Canvas(output, pagesize=(width, height))
    canvas.setFont("Helvetica", 12)
    for text, x, y in lines:
        canvas.drawString(x, y, text)
    canvas.save()
    return output.getvalue()


def _text(pdf: bytes) -> str:
    return PdfReader(BytesIO(pdf), strict=False).pages[0].extract_text() or ""


def _render(pdf: bytes) -> Image.Image:
    return cast(Image.Image, pdfium.PdfDocument(pdf)[0].render(scale=1).to_pil().convert("RGB"))


def _pixel(image: Image.Image, x: int, y: int) -> tuple[int, int, int]:
    value = image.getpixel((x, y))
    if not isinstance(value, tuple) or len(value) < 3:
        raise AssertionError("rendered pixel is not RGB")
    return (int(value[0]), int(value[1]), int(value[2]))


def test_plain_page_copy_preserves_dimensions_and_adds_selectable_text() -> None:
    source = _source_page(("Source page", 20, 150), width=320, height=240)

    output = generate_overlay_page(
        source,
        texts=(OverlayText("Translated page", 20, 120),),
    )
    page = PdfReader(BytesIO(output), strict=False).pages[0]

    assert (float(page.mediabox.width), float(page.mediabox.height)) == (320.0, 240.0)
    assert "Source page" in _text(output)
    assert "Translated page" in _text(output)


def test_header_cover_removes_searchable_source_residue() -> None:
    source = _source_page(("Original header", 20, 170))

    output = OverlayPageGenerator().generate(
        source,
        covers=(CoverRegion(15, 160, 125, 20, source_text="Original header"),),
        texts=(OverlayText("Terjemahan header", 20, 170),),
    )
    extracted = _text(output)

    assert "Original header" not in extracted
    assert "Terjemahan header" in extracted


def test_caption_cover_and_translation_are_merged_in_page_order() -> None:
    source = _source_page(("Caption source", 40, 80))
    covers = (
        CoverRegion(35, 70, 110, 20, fill_color=(0.9, 0.9, 0.9), source_text="Caption source"),
    )
    overlay = OverlayPageGenerator().build_overlay(
        300,
        200,
        covers=covers,
        texts=(OverlayText("Caption terjemahan", 40, 80),),
    )

    output = merge_overlay_page(source, overlay, covers=covers)
    extracted = _text(output)

    assert "Caption source" not in extracted
    assert "Caption terjemahan" in extracted


def test_text_box_wraps_and_honors_alignment() -> None:
    source = _source_page(("Background", 20, 20))
    output = generate_overlay_page(
        source,
        texts=(
            OverlayText(
                "Satu dua tiga empat",
                20,
                130,
                width=105,
                height=40,
                alignment=TextAlignment.CENTER,
                text_id="box-1",
            ),
        ),
    )

    extracted = _text(output)
    assert "Satu dua tiga empat" in extracted.replace("\n", " ")


def test_generator_does_not_modify_original_pdf_bytes() -> None:
    source = _source_page(("Immutable source", 20, 100))
    original_hash = hashlib.sha256(source).hexdigest()

    generate_overlay_page(
        source,
        covers=(CoverRegion(15, 90, 110, 20, source_text="Immutable source"),),
        texts=(OverlayText("Translated", 20, 100),),
    )

    assert hashlib.sha256(source).hexdigest() == original_hash


def test_active_page_annotations_are_not_propagated() -> None:
    writer = PdfWriter()
    page = writer.add_blank_page(width=300, height=200)
    page[NameObject("/Annots")] = ArrayObject(
        [
            DictionaryObject(
                {
                    NameObject("/Subtype"): NameObject("/Link"),
                    NameObject("/A"): DictionaryObject(
                        {NameObject("/S"): NameObject("/JavaScript")}
                    ),
                }
            )
        ]
    )
    page[NameObject("/AA")] = DictionaryObject()
    source_buffer = BytesIO()
    writer.write(source_buffer)

    output = generate_overlay_page(source_buffer.getvalue())
    output_page = PdfReader(BytesIO(output), strict=False).pages[0]

    assert "/Annots" not in output_page
    assert "/AA" not in output_page


def test_white_solid_cover_removes_source_and_paints_white_region() -> None:
    source = _source_page(("White source", 20, 170))

    result = solid_background_cover(
        source,
        (CoverRegion(15, 160, 100, 20, source_text="White source"),),
    )
    image = _render(result.pdf_bytes)

    assert result.strategy is CoverStrategy.SOLID_BACKGROUND
    assert result.source_text_covered is True
    assert "White source" not in _text(result.pdf_bytes)
    assert _pixel(image, 50, 25) == (255, 255, 255)


def test_colored_solid_cover_preserves_requested_background_color() -> None:
    source = _source_page(("Colored source", 20, 170))

    result = solid_background_cover(
        source,
        (CoverRegion(15, 160, 110, 20, fill_color=(0.1, 0.6, 0.2), source_text="Colored source"),),
    )
    pixel = _pixel(_render(result.pdf_bytes), 50, 25)

    assert result.warnings == ()
    assert pixel[1] > pixel[0]
    assert pixel[1] > pixel[2]


def test_raster_background_fallback_covers_text_on_image_background() -> None:
    source_buffer = BytesIO()
    canvas = Canvas(source_buffer, pagesize=(300, 200))
    background = Image.new("RGB", (300, 200), (25, 100, 180))
    canvas.drawImage(ImageReader(background), 0, 0, width=300, height=200)
    canvas.setFillColorRGB(1, 1, 1)
    canvas.drawString(20, 170, "Image source")
    canvas.save()

    result = raster_background_fallback(
        source_buffer.getvalue(),
        (CoverRegion(15, 160, 105, 20, source_text="Image source"),),
        dpi=144,
    )
    image = _render(result.pdf_bytes)

    assert result.strategy is CoverStrategy.RASTER_BACKGROUND
    assert result.rasterized is True
    assert result.source_text_covered is True
    assert _text(result.pdf_bytes) == ""
    pixel = _pixel(image, 50, 25)
    assert pixel[2] > pixel[0]


def test_uncovered_source_is_returned_with_an_explicit_warning() -> None:
    source = _source_page(("Uncovered source", 20, 170))

    result = solid_background_cover(source, ())

    assert result.strategy is CoverStrategy.PRESERVE_WITH_WARNING
    assert result.source_text_covered is False
    assert any(
        warning.code is CoverWarningCode.UNCOVERED_SOURCE_TEXT for warning in result.warnings
    )
    assert "Uncovered source" in _text(result.pdf_bytes)


def test_declared_source_text_that_remains_emits_uncovered_warning() -> None:
    source = _source_page(("Visible source", 20, 170))

    result = solid_background_cover(
        source,
        (CoverRegion(15, 20, 100, 20, source_text="Visible source"),),
    )

    assert any(
        warning.code is CoverWarningCode.UNCOVERED_SOURCE_TEXT for warning in result.warnings
    )
