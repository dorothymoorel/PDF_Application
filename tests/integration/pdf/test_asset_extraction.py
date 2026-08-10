import zlib
from io import BytesIO
from pathlib import Path

import pytest
from PIL import Image
from pypdf import PdfWriter
from pypdf.generic import (
    DecodedStreamObject,
    DictionaryObject,
    EncodedStreamObject,
    NameObject,
    NumberObject,
)
from transloka_core.storage import resolve_local_data_directories
from transloka_core.storage.local import LocalFileStorage
from transloka_documents.assets import extract_and_store_assets

PROJECT_ID = "prj_550e8400-e29b-41d4-a716-446655440000"


@pytest.fixture
def storage(tmp_path: Path) -> tuple[Path, LocalFileStorage]:
    root = tmp_path / "asset data"
    return root, LocalFileStorage(resolve_local_data_directories(root))


@pytest.mark.parametrize(("kind", "mime"), [("PNG", "image/png"), ("JPEG", "image/jpeg")])
def test_extracts_png_and_jpeg_with_geometry_aspect_ratio_and_caption(
    storage: tuple[Path, LocalFileStorage], kind: str, mime: str
) -> None:
    root, file_storage = storage
    result = extract_and_store_assets(
        BytesIO(_pdf_with_image(kind=kind)),
        storage=file_storage,
        project_id=PROJECT_ID,
        caption_block_ids={(1, 1): "blk_caption"},
    )
    asset = result.assets[0]
    assert asset.mime_type == mime
    assert (asset.width_px, asset.height_px, asset.aspect_ratio) == (4, 2, 2.0)
    assert asset.page_number == 1 and asset.caption_block_id == "blk_caption"
    assert asset.source_geometry == asset.source_geometry.__class__(x=20, y=60, width=80, height=40)
    assert (root / Path(asset.storage_key)).is_file()


def test_repeated_image_has_two_references_but_one_stored_file(
    storage: tuple[Path, LocalFileStorage],
) -> None:
    root, file_storage = storage
    result = extract_and_store_assets(
        BytesIO(_pdf_with_image(kind="PNG", repeated=True)),
        storage=file_storage,
        project_id=PROJECT_ID,
    )
    assert len(result.assets) == 2 and result.unique_file_count == 1
    assert result.assets[0].storage_key == result.assets[1].storage_key
    assert len(list((root / "projects" / PROJECT_ID / "assets").iterdir())) == 1


def test_pdf_without_images_returns_empty_and_creates_no_storage(
    storage: tuple[Path, LocalFileStorage],
) -> None:
    root, file_storage = storage
    writer = PdfWriter()
    writer.add_blank_page(width=300, height=400)
    output = BytesIO()
    writer.write(output)
    result = extract_and_store_assets(
        BytesIO(output.getvalue()), storage=file_storage, project_id=PROJECT_ID
    )
    assert result.assets == () and result.unique_file_count == 0
    assert not root.exists()


def test_rotated_page_reports_rotated_geometry_and_rotation(
    storage: tuple[Path, LocalFileStorage],
) -> None:
    _root, file_storage = storage
    result = extract_and_store_assets(
        BytesIO(_pdf_with_image(kind="JPEG", rotation=90)),
        storage=file_storage,
        project_id=PROJECT_ID,
    )
    asset = result.assets[0]
    assert asset.rotation_degrees == 90
    assert asset.source_geometry.x + asset.source_geometry.width <= 400
    assert asset.source_geometry.y + asset.source_geometry.height <= 300


def _pdf_with_image(*, kind: str, repeated: bool = False, rotation: int = 0) -> bytes:
    writer = PdfWriter()
    page = writer.add_blank_page(width=300, height=400)
    if rotation:
        page.rotate(rotation)
    stream = _image_stream(kind)
    reference = writer._add_object(stream)
    page[NameObject("/Resources")] = DictionaryObject(
        {NameObject("/XObject"): DictionaryObject({NameObject("/Im0"): reference})}
    )
    operations = ["q 80 0 0 40 20 300 cm /Im0 Do Q"]
    if repeated:
        operations.append("q 40 0 0 20 150 200 cm /Im0 Do Q")
    content = DecodedStreamObject()
    content.set_data("\n".join(operations).encode())
    page[NameObject("/Contents")] = writer._add_object(content)
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


def _image_stream(kind: str) -> EncodedStreamObject:
    stream = EncodedStreamObject()
    if kind == "JPEG":
        output = BytesIO()
        Image.new("RGB", (4, 2), (0, 128, 255)).save(output, "JPEG")
        stream._data = output.getvalue()
        image_filter = "/DCTDecode"
    else:
        stream._data = zlib.compress(bytes([0, 128, 255] * 8))
        image_filter = "/FlateDecode"
    stream.update(
        {
            NameObject("/Type"): NameObject("/XObject"),
            NameObject("/Subtype"): NameObject("/Image"),
            NameObject("/Width"): NumberObject(4),
            NameObject("/Height"): NumberObject(2),
            NameObject("/ColorSpace"): NameObject("/DeviceRGB"),
            NameObject("/BitsPerComponent"): NumberObject(8),
            NameObject("/Filter"): NameObject(image_filter),
        }
    )
    return stream
