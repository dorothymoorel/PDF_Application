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
