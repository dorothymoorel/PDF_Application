from __future__ import annotations

import base64
import sys
from importlib import import_module
from io import BytesIO
from pathlib import Path

import pytest
from pypdf import PdfReader
from transloka_reconstruction.reflow.generator import (
    ReflowDependencyError,
    ReflowPageSettings,
    ReflowPDFGenerator,
)
from transloka_reconstruction.reflow.resources import (
    ResourceAccessDenied,
    RestrictedResourceLoader,
)
from transloka_reconstruction.reflow.types import (
    ReflowBlock,
    ReflowBlockKind,
    ReflowDocument,
    ReflowTable,
)

_ONE_BY_ONE_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII="
)


def _text(pdf: bytes) -> str:
    return "\n".join(page.extract_text() or "" for page in PdfReader(BytesIO(pdf)).pages)


def _require_weasyprint() -> None:
    try:
        import_module("weasyprint")
    except (ImportError, OSError) as exc:
        pytest.skip(f"WeasyPrint runtime is unavailable: {exc}")


def test_long_paragraph_produces_searchable_pdf() -> None:
    _require_weasyprint()
    paragraph = " ".join(["Long paragraph content remains selectable."] * 900)
    document = ReflowDocument(
        blocks=(ReflowBlock(block_id="long", text=paragraph),),
    )

    pdf = ReflowPDFGenerator().generate(document)
    reader = PdfReader(BytesIO(pdf), strict=False)

    assert pdf.startswith(b"%PDF-")
    assert len(reader.pages) >= 2
    assert "Long paragraph content remains selectable." in _text(pdf)


def test_heading_and_page_settings_are_preserved() -> None:
    _require_weasyprint()
    settings = ReflowPageSettings(
        width_pt=300,
        height_pt=400,
        margin_top_pt=20,
        margin_right_pt=20,
        margin_bottom_pt=20,
        margin_left_pt=20,
    )
    document = ReflowDocument(
        blocks=(
            ReflowBlock(
                block_id="heading",
                kind=ReflowBlockKind.HEADING,
                level=2,
                text="A searchable heading",
            ),
            ReflowBlock(block_id="paragraph", text="Heading body text."),
        )
    )

    pdf = ReflowPDFGenerator(page_settings=settings).generate(document)
    page = PdfReader(BytesIO(pdf), strict=False).pages[0]

    assert float(page.mediabox.width) == pytest.approx(300)
    assert float(page.mediabox.height) == pytest.approx(400)
    assert "A searchable heading" in _text(pdf)


def test_approved_image_is_embedded(tmp_path: Path) -> None:
    _require_weasyprint()
    asset_root = tmp_path / "assets"
    font_root = tmp_path / "fonts"
    asset_root.mkdir()
    font_root.mkdir()
    image_path = asset_root / "cover.png"
    image_path.write_bytes(_ONE_BY_ONE_PNG)
    loader = RestrictedResourceLoader(
        asset_root=asset_root,
        font_root=font_root,
        approved_assets={"cover.png": image_path},
    )
    document = ReflowDocument(
        blocks=(
            ReflowBlock(
                block_id="image",
                kind=ReflowBlockKind.IMAGE,
                asset_id="cover.png",
                alt_text="Approved cover image",
            ),
        )
    )

    pdf = ReflowPDFGenerator(resource_loader=loader).generate(document)
    resources = PdfReader(BytesIO(pdf), strict=False).pages[0].get("/Resources")

    assert resources is not None
    assert resources.get("/XObject")


def test_table_cells_are_searchable() -> None:
    _require_weasyprint()
    document = ReflowDocument(
        blocks=(
            ReflowBlock(
                block_id="table",
                kind=ReflowBlockKind.TABLE,
                table=ReflowTable(
                    rows=(("Term", "Translation"), ("hello", "halo")),
                    header_row=True,
                ),
            ),
        )
    )

    pdf = ReflowPDFGenerator().generate(document)

    assert "Term" in _text(pdf)
    assert "halo" in _text(pdf)


def test_page_break_adds_a_page() -> None:
    _require_weasyprint()
    document = ReflowDocument(
        blocks=(
            ReflowBlock(block_id="first", text="First page."),
            ReflowBlock(block_id="break", kind=ReflowBlockKind.PAGE_BREAK),
            ReflowBlock(
                block_id="second",
                kind=ReflowBlockKind.HEADING,
                text="Second page heading",
            ),
        )
    )

    pdf = ReflowPDFGenerator().generate(document)
    reader = PdfReader(BytesIO(pdf), strict=False)

    assert len(reader.pages) == 2
    assert "Second page heading" in _text(pdf)


def test_unsafe_resource_is_rejected_before_rendering() -> None:
    html = '<!doctype html><html><body><img src="https://example.invalid/image.png"></body></html>'

    with pytest.raises(ResourceAccessDenied):
        ReflowPDFGenerator().generate(html)


def test_missing_weasyprint_is_reported_as_dependency_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(sys.modules, "weasyprint", None)

    with pytest.raises(ReflowDependencyError):
        ReflowPDFGenerator().generate("<html><body>plain text</body></html>")
