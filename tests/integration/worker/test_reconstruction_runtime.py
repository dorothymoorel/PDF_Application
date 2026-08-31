import json
from io import BytesIO
from uuid import UUID

import pytest
from pypdf import PdfReader
from reportlab.pdfgen.canvas import Canvas  # type: ignore[import-untyped]
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
