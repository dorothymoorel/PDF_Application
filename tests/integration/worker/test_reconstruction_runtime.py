import json
from dataclasses import replace
from hashlib import sha256
from io import BytesIO
from pathlib import Path
from typing import cast
from uuid import UUID

import pdfplumber
import pypdfium2 as pdfium  # type: ignore[import-untyped]
import pytest
import reportlab  # type: ignore[import-untyped]
from PIL import Image, ImageChops
from pypdf import PdfReader
from reportlab.lib.utils import ImageReader  # type: ignore[import-untyped]
from reportlab.pdfbase import pdfmetrics  # type: ignore[import-untyped]
from reportlab.pdfbase.ttfonts import TTFont  # type: ignore[import-untyped]
from reportlab.pdfgen.canvas import Canvas  # type: ignore[import-untyped]
from transloka_reconstruction.fonts.reportlab import ReportLabFontCatalog
from transloka_reconstruction.overlay import OverlayLayoutError
from transloka_worker.reconstruction import (
    LoadedReconstructionJob,
    ReconstructionBlockInput,
    ReconstructionCommand,
    ReconstructionPageInput,
    ReconstructionRenderer,
    ReconstructionWorkerError,
)


def _id(prefix: str, value: int) -> str:
    return f"{prefix}{UUID(int=value)}"


PROJECT_ID = _id("prj_", 1)
DOCUMENT_ID = _id("doc_", 2)
PAGE_ID = _id("pag_", 3)


def _settings(mode: str = "OVERLAY") -> dict[str, object]:
    return {
        "mode": mode,
        "profile": "BALANCED",
        "preserve_page_size": True,
        "preserve_images": True,
        "preserve_headers": True,
        "preserve_footers": True,
        "preserve_page_numbers": True,
        "translate_captions": True,
        "minimum_body_font_pt": 8.0,
        "maximum_font_reduction_percent": 10.0,
        "allow_page_addition": True,
        "allow_single_column_fallback": False,
        "allow_column_change": False,
        "table_complexity_fallback": "PRESERVE_AS_IMAGE",
        "image_quality": "STANDARD",
        "output_profile": "STANDARD",
        "block_export_on_critical_errors": True,
        "show_layout_warnings": True,
    }


def _command(**overrides: object) -> ReconstructionCommand:
    values: dict[str, object] = {
        "project_id": PROJECT_ID,
        "document_id": DOCUMENT_ID,
        "mode": "OVERLAY",
        "page_ids": (PAGE_ID,),
        "settings": _settings(),
    }
    values.update(overrides)
    return ReconstructionCommand(**values)  # type: ignore[arg-type]


def test_reconstruction_command_round_trips_exact_versioned_payload() -> None:
    command = _command()

    decoded = ReconstructionCommand.from_payload_json(json.dumps(command.to_payload()))

    assert decoded == command
    assert decoded.to_payload()["schema"] == "transloka.reconstruction.command.v1"


def test_reconstruction_command_rejects_mode_disagreement_and_duplicate_pages() -> None:
    with pytest.raises(ReconstructionWorkerError, match="mode"):
        _command(mode="REFLOW")
    with pytest.raises(ReconstructionWorkerError, match="duplicate"):
        _command(page_ids=(PAGE_ID, PAGE_ID))


def test_reconstruction_command_rejects_duplicate_and_unknown_json_fields() -> None:
    payload = json.dumps(_command().to_payload())
    duplicate = payload[:-1] + ',"mode":"OVERLAY"}'
    unknown = json.loads(payload)
    unknown["path"] = "C:/secret.pdf"

    with pytest.raises(ReconstructionWorkerError, match="duplicated"):
        ReconstructionCommand.from_payload_json(duplicate)
    with pytest.raises(ReconstructionWorkerError, match="fields"):
        ReconstructionCommand.from_payload_json(json.dumps(unknown))


def test_reconstruction_command_rejects_invalid_settings() -> None:
    settings = _settings()
    settings["minimum_body_font_pt"] = 1

    with pytest.raises(ReconstructionWorkerError, match="settings"):
        _command(settings=settings)


def test_overlay_renderer_replaces_source_text_and_preserves_selectable_translation() -> None:
    source = BytesIO()
    canvas = Canvas(source, pagesize=(300, 200))
    canvas.drawString(20, 160, "Source sentence")
    canvas.save()
    loaded = LoadedReconstructionJob(
        job_id=_id("job_", 4),
        reconstruction_job_id=_id("rcj_", 5),
        project_id=PROJECT_ID,
        document_id=DOCUMENT_ID,
        source_pdf=source.getvalue(),
        pages=(
            ReconstructionPageInput(
                page_id=PAGE_ID,
                source_page_number=1,
                width_points=300,
                height_points=200,
                page_type="DIGITAL",
                column_count=1,
                blocks=(
                    ReconstructionBlockInput(
                        block_id=_id("blk_", 6),
                        block_type="PARAGRAPH",
                        source_text="Source sentence",
                        translated_text="Kalimat terjemahan",
                        source_geometry={
                            "coordinate_system": "PDF_POINT_TOP_LEFT",
                            "x": 20,
                            "y": 28,
                            "width": 180,
                            "height": 24,
                        },
                    ),
                ),
            ),
        ),
        selected_page_ids=(PAGE_ID,),
        command=_command(),
        critical_warnings=(),
    )

    result = ReconstructionRenderer().render(loaded)
    text = "\n".join(
        page.extract_text() or "" for page in PdfReader(BytesIO(result.pdf_bytes)).pages
    )

    assert "Kalimat terjemahan" in text
    assert "Source sentence" not in text
    assert result.pages[0].strategy == "OVERLAY"
    assert result.required_segments == ("Kalimat terjemahan",)


def test_overlay_renderer_preserves_source_font_name_and_size() -> None:
    source = BytesIO()
    canvas = Canvas(source, pagesize=(500, 200))
    canvas.setFont("Helvetica-Bold", 20)
    canvas.drawString(20, 160, "Source heading")
    canvas.setFont("Helvetica", 10)
    canvas.drawString(420, 10, "Page 1 of 2")
    canvas.save()
    translated = "Judul terjemahan yang lebih panjang"
    loaded = LoadedReconstructionJob(
        job_id=_id("job_", 14),
        reconstruction_job_id=_id("rcj_", 15),
        project_id=PROJECT_ID,
        document_id=DOCUMENT_ID,
        source_pdf=source.getvalue(),
        pages=(
            ReconstructionPageInput(
                page_id=PAGE_ID,
                source_page_number=1,
                width_points=500,
                height_points=200,
                page_type="DIGITAL",
                column_count=1,
                blocks=(
                    ReconstructionBlockInput(
                        block_id=_id("blk_", 16),
                        block_type="DOCUMENT_TITLE",
                        source_text="Source heading",
                        translated_text=translated,
                        source_geometry={
                            "coordinate_system": "PDF_POINT_TOP_LEFT",
                            "x": 20,
                            "y": 20,
                            "width": 150,
                            "height": 20,
                        },
                        source_style={"font_name": "Helvetica-Bold", "font_size": 20.0},
                    ),
                    ReconstructionBlockInput(
                        block_id=_id("blk_", 17),
                        block_type="PAGE_NUMBER",
                        source_text="Page 1 of 2",
                        translated_text="Halaman 1 dari 2",
                        source_geometry={
                            "coordinate_system": "PDF_POINT_TOP_LEFT",
                            "x": 420,
                            "y": 180,
                            "width": 50,
                            "height": 10,
                        },
                        source_style={"font_name": "Helvetica", "font_size": 10.0},
                    ),
                ),
            ),
        ),
        selected_page_ids=(PAGE_ID,),
        command=_command(),
        critical_warnings=(),
    )

    result = ReconstructionRenderer().render(loaded)
    observed: list[tuple[str, float, str, float]] = []

    def visit_text(
        text: str,
        _cm: list[float],
        tm: list[float],
        font: dict[str, object] | None,
        size: float,
    ) -> None:
        if text.strip():
            observed.append((text.strip(), size, str((font or {}).get("/BaseFont")), tm[4]))

    PdfReader(BytesIO(result.pdf_bytes)).pages[0].extract_text(visitor_text=visit_text)

    assert (translated, 20.0, "/Helvetica-Bold", 20.0) in observed
    assert any(
        text == "Halaman 1 dari 2" and size == 10.0 and font == "/Helvetica"
        for text, size, font, _x in observed
    )


def test_overlay_renderer_preserves_source_line_spacing() -> None:
    source = BytesIO()
    canvas = Canvas(source, pagesize=(300, 200))
    canvas.setFont("Helvetica", 12)
    canvas.drawString(20, 140, "First line")
    canvas.drawString(20, 114.5, "Second line")
    canvas.drawString(20, 89, "Third line")
    canvas.save()
    loaded = LoadedReconstructionJob(
        job_id=_id("job_", 24),
        reconstruction_job_id=_id("rcj_", 25),
        project_id=PROJECT_ID,
        document_id=DOCUMENT_ID,
        source_pdf=source.getvalue(),
        pages=(
            ReconstructionPageInput(
                page_id=PAGE_ID,
                source_page_number=1,
                width_points=300,
                height_points=200,
                page_type="DIGITAL",
                column_count=1,
                blocks=(
                    ReconstructionBlockInput(
                        block_id=_id("blk_", 26),
                        block_type="PARAGRAPH",
                        source_text="First line\nSecond line\nThird line",
                        translated_text=(
                            "Baris pertama cukup pendek\n"
                            "Baris kedua sengaja terlalu panjang untuk satu baris sumber\n"
                            "Baris ketiga"
                        ),
                        source_geometry={
                            "coordinate_system": "PDF_POINT_TOP_LEFT",
                            "x": 20,
                            "y": 50.484,
                            "width": 240,
                            "height": 63,
                        },
                        source_style={"font_name": "Helvetica", "font_size": 12.0},
                    ),
                ),
            ),
        ),
        selected_page_ids=(PAGE_ID,),
        command=_command(),
        critical_warnings=(),
    )

    result = ReconstructionRenderer().render(loaded)
    baselines: list[float] = []

    def visit_text(
        text: str,
        _cm: list[float],
        tm: list[float],
        _font: dict[str, object] | None,
        _size: float,
    ) -> None:
        if text.strip():
            baselines.append(tm[5])

    PdfReader(BytesIO(result.pdf_bytes)).pages[0].extract_text(visitor_text=visit_text)

    assert baselines == pytest.approx([140.0, 114.5, 89.0])


@pytest.mark.parametrize("mode", ["OVERLAY", "HYBRID"])
@pytest.mark.parametrize("translate", [False, True])
def test_production_font_fidelity_with_real_metrics_and_images(
    tmp_path: Path,
    mode: str,
    translate: bool,
) -> None:
    font_root = Path(reportlab.__file__).parent / "fonts"
    faces = (font_root / "VeraBd.ttf", font_root / "Vera.ttf", font_root / "VeraIt.ttf")
    content = (
        ("Original document", "Dokumen terjemahan", 20, 250),
        ("First sentence\nSecond sentence", "Kalimat pertama\nKalimat kedua", 12, 200),
        ("Caption for image", "Keterangan gambar", 10, 110),
    )
    source = BytesIO()
    canvas = Canvas(source, pagesize=(400, 300))
    for index, (path, (text, _target, size, baseline)) in enumerate(
        zip(faces, content, strict=True)
    ):
        name = f"FidelitySource{index}"
        pdfmetrics.registerFont(TTFont(name, str(path)))
        canvas.setFont(name, size)
        for line in text.splitlines():
            canvas.drawString(30, baseline, line)
            baseline -= 22
    canvas.setStrokeColorRGB(0, 0.4, 0.8)
    canvas.rect(20, 15, 360, 80, stroke=1, fill=0)
    image = Image.new("RGB", (48, 32), "#249f70")
    canvas.drawImage(ImageReader(image), 30, 25, width=96, height=64)
    canvas.save()
    source_bytes = source.getvalue()
    original_hash = sha256(source_bytes).hexdigest()
    blocks: list[ReconstructionBlockInput] = []
    with pdfplumber.open(BytesIO(source_bytes)) as pdf:
        source_chars = pdf.pages[0].chars
        for index, (original, target, size, _baseline) in enumerate(content):
            chars = [char for char in source_chars if char["size"] == size]
            left = min(char["x0"] for char in chars)
            top = min(char["top"] for char in chars)
            bottom = max(char["bottom"] for char in chars)
            blocks.append(
                ReconstructionBlockInput(
                    block_id=_id("blk_", 100 + index),
                    block_type=("DOCUMENT_TITLE", "PARAGRAPH", "CAPTION")[index],
                    source_text=original,
                    translated_text=target if translate else original,
                    source_style={"font_name": chars[0]["fontname"], "font_size": size},
                    source_geometry={
                        "x": left,
                        "y": top,
                        "width": 340,
                        "height": bottom - top,
                        "coordinate_system": "PDF_POINT_TOP_LEFT",
                    },
                )
            )
    blocks.append(
        ReconstructionBlockInput(
            block_id=_id("blk_", 103),
            block_type="IMAGE",
            source_text="",
            translated_text=None,
            source_geometry={"x": 30, "y": 211, "width": 96, "height": 64},
        )
    )
    page = ReconstructionPageInput(
        page_id=PAGE_ID,
        source_page_number=1,
        width_points=400,
        height_points=300,
        page_type="DIGITAL",
        column_count=1,
        blocks=tuple(blocks),
    )
    loaded = LoadedReconstructionJob(
        job_id=_id("job_", 101),
        reconstruction_job_id=_id("rcj_", 102),
        project_id=PROJECT_ID,
        document_id=DOCUMENT_ID,
        source_pdf=source_bytes,
        pages=(page,),
        selected_page_ids=(PAGE_ID,),
        command=_command(mode=mode, settings=_settings(mode)),
        critical_warnings=(),
    )
    result = ReconstructionRenderer(font_catalog=ReportLabFontCatalog(paths=faces)).render(loaded)
    assert result.pages[0].strategy == "OVERLAY"
    assert sha256(loaded.source_pdf).hexdigest() == original_hash
    assert len(PdfReader(BytesIO(result.pdf_bytes)).pages) == 1
    for _block_id, mapping in result.pages[0].font_mappings:
        assert mapping["embedding_status"] == "SUBSET_EMBEDDED"
        assert mapping["stage"] == "SYSTEM"
        assert mapping["warnings"] == []
    with pdfplumber.open(BytesIO(result.pdf_bytes)) as pdf:
        output_page = pdf.pages[0]
        assert (output_page.width, output_page.height) == (400, 300)
        for _original, target, size, _baseline in content:
            original_chars = [char for char in source_chars if char["size"] == size]
            output_chars = [char for char in output_page.chars if char["size"] == size]
            assert output_chars
            assert {char["fontname"] for char in output_chars} == {
                char["fontname"] for char in original_chars
            }
            assert min(char["top"] for char in output_chars) == pytest.approx(
                min(char["top"] for char in original_chars),
                abs=0.01,
            )
            assert sorted({round(char["top"], 2) for char in output_chars}) == sorted(
                {round(char["top"], 2) for char in original_chars}
            )
            if translate:
                for line in target.splitlines():
                    assert line in (output_page.extract_text() or "")
    source_reader = PdfReader(BytesIO(source_bytes))
    output_reader = PdfReader(BytesIO(result.pdf_bytes))
    assert [item.data for item in source_reader.pages[0].images] == [
        item.data for item in output_reader.pages[0].images
    ]

    def raster(data: bytes) -> Image.Image:
        with pdfium.PdfDocument(data) as document:
            pdf_page = document[0]
            bitmap = pdf_page.render(scale=2)
            try:
                return cast(Image.Image, bitmap.to_pil().convert("RGB").copy())
            finally:
                bitmap.close()
                pdf_page.close()

    before, after = raster(source_bytes), raster(result.pdf_bytes)
    # Same-text reconstruction must be pixel-identical, including the text.
    # Translation may change text pixels only; artwork below it stays identical.
    region = (0, 410, 800, 600) if translate else (0, 0, 800, 600)
    assert ImageChops.difference(before.crop(region), after.crop(region)).getbbox() is None
    (tmp_path / "source.pdf").write_bytes(source_bytes)
    (tmp_path / "output.pdf").write_bytes(result.pdf_bytes)
    before.save(tmp_path / "source.png")
    after.save(tmp_path / "output.png")


@pytest.fixture
def hybrid_paragraph() -> LoadedReconstructionJob:
    source = BytesIO()
    canvas = Canvas(source, pagesize=(400, 420))
    canvas.setFont("Helvetica-Bold", 20)
    canvas.drawString(30, 380, "Original heading")
    canvas.setFont("Helvetica", 12)
    lines = [f"Original paragraph line {index}." for index in range(8)]
    for index, line in enumerate(lines):
        canvas.drawString(30, 340 - index * 14, line)
    canvas.drawImage(ImageReader(Image.new("RGB", (48, 32), "#249f70")), 30, 40, 96, 64)
    canvas.setStrokeColorRGB(0, 0.4, 0.8)
    canvas.rect(20, 20, 360, 100, stroke=1, fill=0)
    canvas.save()
    blocks = (
        ReconstructionBlockInput(
            block_id=_id("blk_", 201),
            block_type="DOCUMENT_TITLE",
            source_text="Original heading",
            translated_text="Judul terjemahan",
            source_geometry={"x": 30, "y": 24.14, "width": 340, "height": 20},
            source_style={"font_name": "Helvetica-Bold", "font_size": 20},
        ),
        ReconstructionBlockInput(
            block_id=_id("blk_", 202),
            block_type="PARAGRAPH",
            source_text="\n".join(lines),
            translated_text="Isi terjemahan tetap berada di kotak paragraf sumber. " * 8,
            source_geometry={"x": 30, "y": 70.484, "width": 340, "height": 110},
            source_style={"font_name": "Helvetica", "font_size": 12},
        ),
        ReconstructionBlockInput(
            block_id=_id("blk_", 203),
            block_type="IMAGE",
            source_text="",
            translated_text=None,
            source_geometry={"x": 30, "y": 316, "width": 96, "height": 64},
        ),
    )
    return LoadedReconstructionJob(
        job_id=_id("job_", 201),
        reconstruction_job_id=_id("rcj_", 202),
        project_id=PROJECT_ID,
        document_id=DOCUMENT_ID,
        source_pdf=source.getvalue(),
        pages=(
            ReconstructionPageInput(
                page_id=PAGE_ID,
                source_page_number=1,
                width_points=400,
                height_points=420,
                page_type="DIGITAL",
                column_count=1,
                blocks=blocks,
            ),
        ),
        selected_page_ids=(PAGE_ID,),
        command=_command(mode="HYBRID", settings=_settings("HYBRID")),
        critical_warnings=(),
    )


@pytest.mark.parametrize("image_in_ir", [True, False])
def test_hybrid_reflows_only_paragraph_inside_source_box(
    hybrid_paragraph: LoadedReconstructionJob,
    tmp_path: Path,
    image_in_ir: bool,
) -> None:
    loaded = hybrid_paragraph
    if not image_in_ir:
        # Also preserve artwork when IR classifies the page as reflow-friendly.
        loaded = replace(
            loaded, pages=(replace(loaded.pages[0], blocks=loaded.pages[0].blocks[:2]),)
        )
    original_hash = sha256(loaded.source_pdf).hexdigest()
    result = ReconstructionRenderer().render(loaded)
    assert result.pages[0].strategy == "OVERLAY"
    strategies = dict(result.pages[0].block_strategies)
    assert strategies[_id("blk_", 201)] == "OVERLAY"
    assert strategies[_id("blk_", 202)] == "REFLOW"
    if image_in_ir:
        assert strategies[_id("blk_", 203)] == "PRESERVE"
    assert len(result.pages[0].font_mappings) == 2
    assert sha256(loaded.source_pdf).hexdigest() == original_hash
    source_page = PdfReader(BytesIO(loaded.source_pdf)).pages[0]
    output = PdfReader(BytesIO(result.pdf_bytes))
    assert len(output.pages) == 1
    assert [item.data for item in source_page.images] == [
        item.data for item in output.pages[0].images
    ]
    with pdfplumber.open(BytesIO(result.pdf_bytes)) as pdf:
        page = pdf.pages[0]
        assert (page.width, page.height) == (400, 420)
        extracted = " ".join((page.extract_text() or "").split())
        assert " ".join((loaded.pages[0].blocks[1].translated_text or "").split()) in extracted
        assert "Original" not in extracted
        title = [char for char in page.chars if char["size"] == 20]
        body = [char for char in page.chars if char["size"] == 12]
        assert title and body
        assert {char["fontname"] for char in title} == {"Helvetica-Bold"}
        assert min(char["top"] for char in title) == pytest.approx(24.14)
        assert {char["fontname"] for char in body} == {"Helvetica"}
        assert min(char["x0"] for char in body) >= 30
        assert max(char["x1"] for char in body) <= 370
        assert min(char["top"] for char in body) == pytest.approx(70.484)
        assert max(char["bottom"] for char in body) <= 180.484 + 0.01
    rasters = []
    for name, data in (("source", loaded.source_pdf), ("output", result.pdf_bytes)):
        with pdfium.PdfDocument(data) as document:
            page_handle = document[0]
            bitmap = page_handle.render(scale=2)
            try:
                raster = bitmap.to_pil().convert("RGB").copy()
                raster.save(tmp_path / f"{name}.png")
                rasters.append(raster)
            finally:
                bitmap.close()
                page_handle.close()
    region = (0, 390, 800, 840)
    assert ImageChops.difference(rasters[0].crop(region), rasters[1].crop(region)).getbbox() is None


def test_hybrid_rejects_region_overflow_instead_of_reflowing_entire_page(
    hybrid_paragraph: LoadedReconstructionJob,
) -> None:
    page = hybrid_paragraph.pages[0]
    paragraph = replace(page.blocks[1], translated_text="Teks terlalu panjang. " * 300)
    loaded = replace(
        hybrid_paragraph, pages=(replace(page, blocks=(page.blocks[0], paragraph, page.blocks[2])),)
    )
    with pytest.raises(OverlayLayoutError, match="exceeds its declared height"):
        ReconstructionRenderer().render(loaded)


def test_explicit_reflow_still_uses_document_renderer(
    hybrid_paragraph: LoadedReconstructionJob,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def reflow(page: ReconstructionPageInput) -> tuple[bytes, str, tuple[tuple[str, str], ...]]:
        assert page == hybrid_paragraph.pages[0]
        return hybrid_paragraph.source_pdf, "REFLOW", ()

    monkeypatch.setattr(ReconstructionRenderer, "_reflow", staticmethod(reflow))
    loaded = replace(
        hybrid_paragraph, command=_command(mode="REFLOW", settings=_settings("REFLOW"))
    )
    assert ReconstructionRenderer().render(loaded).pages[0].strategy == "REFLOW"
