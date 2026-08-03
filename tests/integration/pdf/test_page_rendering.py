import hashlib
from io import BytesIO
from pathlib import Path

import pytest
from PIL import Image
from pypdf import PdfWriter
from transloka_core.storage import resolve_local_data_directories
from transloka_core.storage.local import LocalFileStorage
from transloka_documents.rendering import (
    PageRenderingError,
    UnsupportedRenderDpiError,
    render_pdf_page,
)

PROJECT_ID = "prj_135390ce-c186-4ed1-9723-d7daa3065017"


@pytest.fixture
def storage(tmp_path: Path) -> tuple[Path, LocalFileStorage]:
    root = tmp_path / "transloka-data"
    return root, LocalFileStorage(resolve_local_data_directories(root))


@pytest.mark.parametrize(
    ("width", "height", "expected_size"),
    [(612, 792, (612, 792)), (792, 612, (792, 612))],
)
def test_renders_portrait_and_landscape_pages(
    storage: tuple[Path, LocalFileStorage],
    width: float,
    height: float,
    expected_size: tuple[int, int],
) -> None:
    root, file_storage = storage

    result = render_pdf_page(
        BytesIO(_pdf_bytes(width=width, height=height)),
        storage=file_storage,
        project_id=PROJECT_ID,
        page_number=1,
        dpi=72,
    )

    with Image.open(root / Path(result.render.storage_key)) as render:
        assert render.format == "PNG"
        assert render.size == expected_size
    with Image.open(root / Path(result.thumbnail.storage_key)) as thumbnail:
        assert thumbnail.format == "WEBP"
        assert thumbnail.width <= 320
        assert thumbnail.height <= 320


def test_render_respects_page_rotation(storage: tuple[Path, LocalFileStorage]) -> None:
    root, file_storage = storage

    result = render_pdf_page(
        BytesIO(_pdf_bytes(width=612, height=792, rotation=90)),
        storage=file_storage,
        project_id=PROJECT_ID,
        page_number=1,
        dpi=72,
    )

    with Image.open(root / Path(result.render.storage_key)) as render:
        assert render.size == (792, 612)


def test_rejects_excessive_dpi_before_creating_data(
    storage: tuple[Path, LocalFileStorage],
) -> None:
    root, file_storage = storage

    with pytest.raises(UnsupportedRenderDpiError, match="not allowed"):
        render_pdf_page(
            BytesIO(_pdf_bytes()),
            storage=file_storage,
            project_id=PROJECT_ID,
            page_number=1,
            dpi=600,
        )

    assert not root.exists()


def test_render_checksum_is_stable_and_repeat_is_a_cache_hit(
    storage: tuple[Path, LocalFileStorage],
) -> None:
    root, file_storage = storage
    content = _pdf_bytes()
    source = BytesIO(content)
    source.seek(7)

    first = render_pdf_page(
        source,
        storage=file_storage,
        project_id=PROJECT_ID,
        page_number=1,
        dpi=96,
    )
    second = render_pdf_page(
        BytesIO(content),
        storage=file_storage,
        project_id=PROJECT_ID,
        page_number=1,
        dpi=96,
    )

    assert source.tell() == 7
    assert first.cache_hit is False
    assert second.cache_hit is True
    assert second == first.__class__(
        page_number=first.page_number,
        dpi=first.dpi,
        source_checksum_sha256=first.source_checksum_sha256,
        cache_key=first.cache_key,
        render=first.render,
        thumbnail=first.thumbnail,
        cache_hit=True,
    )
    assert first.source_checksum_sha256 == hashlib.sha256(content).hexdigest()
    assert (
        first.render.checksum_sha256
        == hashlib.sha256((root / Path(first.render.storage_key)).read_bytes()).hexdigest()
    )
    assert len(list((root / "projects" / PROJECT_ID).rglob("*.*"))) == 2


def test_unsafe_project_id_cannot_escape_data_root(
    storage: tuple[Path, LocalFileStorage],
    tmp_path: Path,
) -> None:
    _root, file_storage = storage
    escaped = tmp_path / "outside"

    with pytest.raises(PageRenderingError, match="could not be rendered safely"):
        render_pdf_page(
            BytesIO(_pdf_bytes()),
            storage=file_storage,
            project_id="../../outside",
            page_number=1,
            dpi=72,
        )

    assert not escaped.exists()


def _pdf_bytes(
    *,
    width: float = 612,
    height: float = 792,
    rotation: int = 0,
) -> bytes:
    output = BytesIO()
    writer = PdfWriter()
    page = writer.add_blank_page(width=width, height=height)
    if rotation:
        page.rotate(rotation)
    writer.write(output)
    return output.getvalue()
