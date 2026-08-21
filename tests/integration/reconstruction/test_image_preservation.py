from __future__ import annotations

from io import BytesIO

import pytest
from PIL import Image
from transloka_reconstruction.assets import (
    CaptionRelation,
    CaptionSpec,
    ImageAsset,
    ImageFit,
    ImagePosition,
    ImageRect,
    ImageWarningCode,
    MissingImageError,
    preserve_image,
    render_preserved_image,
)


def _encoded_image(image_format: str, *, size: tuple[int, int], mode: str = "RGB") -> bytes:
    image = Image.new(mode, size, (20, 40, 60, 255) if mode == "RGBA" else (20, 40, 60))
    output = BytesIO()
    image.save(output, format=image_format)
    return output.getvalue()


def test_png_contain_preserves_aspect_ratio_and_reports_metric() -> None:
    asset = ImageAsset(
        asset_id="asset-png",
        page_id="page-1",
        source=_encoded_image("PNG", size=(400, 200)),
        rotation_degrees=0,
    )

    placement = preserve_image(asset, ImageRect(10, 20, 100, 100))

    assert placement.rendered == ImageRect(10, 45, 100, 50)
    assert placement.crop == ImageRect(0, 0, 400, 200)
    assert placement.aspect_ratio_preserved
    assert placement.metric is not None
    assert placement.metric.crop_fraction == 0
    assert placement.metric.score == 1


def test_jpeg_cover_crops_without_distortion_and_honors_position() -> None:
    asset = ImageAsset(
        asset_id="asset-jpeg",
        page_id="page-1",
        source=_encoded_image("JPEG", size=(400, 200)),
    )

    placement = preserve_image(
        asset,
        ImageRect(0, 0, 100, 100),
        fit=ImageFit.COVER,
        position=ImagePosition.TOP_RIGHT,
    )

    assert placement.rendered == ImageRect(0, 0, 100, 100)
    assert placement.crop == ImageRect(200, 0, 200, 200)
    assert placement.metric is not None
    assert placement.metric.aspect_ratio_preserved
    assert placement.metric.crop_fraction == pytest.approx(0.5)


def test_transparent_png_and_opacity_survive_raster_render() -> None:
    asset = ImageAsset(
        asset_id="asset-alpha",
        page_id="page-1",
        source=_encoded_image("PNG", size=(20, 20), mode="RGBA"),
        opacity=0.5,
    )
    placement = preserve_image(asset, ImageRect(0, 0, 20, 20))

    rendered = render_preserved_image(asset, placement)
    with Image.open(BytesIO(rendered.data)) as image:
        assert image.mode == "RGBA"
        assert image.getchannel("A").getextrema() == (128, 128)


def test_rotation_swaps_oriented_dimensions_and_is_kept_in_result() -> None:
    asset = ImageAsset(
        asset_id="asset-rotated",
        page_id="page-1",
        source=_encoded_image("PNG", size=(80, 40)),
        rotation_degrees=90,
    )

    placement = preserve_image(asset, ImageRect(0, 0, 80, 80))
    rendered = render_preserved_image(asset, placement)

    assert placement.rotation_degrees == 90
    assert placement.rendered == ImageRect(20, 0, 40, 80)
    assert rendered.width_px == 80
    assert rendered.height_px == 80


def test_caption_relation_and_page_association_are_preserved() -> None:
    asset = ImageAsset(
        asset_id="asset-caption",
        page_id="page-7",
        source=_encoded_image("PNG", size=(20, 20)),
        caption_block_id="caption-7",
        z_index=3,
    )

    placement = preserve_image(
        asset,
        ImageRect(10, 30, 40, 40),
        caption=CaptionSpec("Gambar 7", relation=CaptionRelation.BELOW),
        page_bounds=ImageRect(0, 0, 100, 100),
        page_id="page-7",
    )

    assert placement.page_id == "page-7"
    assert placement.z_index == 3
    assert placement.caption is not None
    assert placement.caption.block_id == "caption-7"
    assert placement.caption.relation is CaptionRelation.BELOW
    assert not placement.caption.overlaps_image


def test_missing_asset_emits_warning_and_render_fails_safely() -> None:
    asset = ImageAsset(
        asset_id="asset-missing",
        page_id="page-1",
        width_px=100,
        height_px=50,
        source="does-not-exist.png",
    )

    placement = preserve_image(asset, ImageRect(0, 0, 100, 50))

    assert placement.rendered is None
    assert any(warning.code is ImageWarningCode.MISSING_ASSET for warning in placement.warnings)
    with pytest.raises(MissingImageError):
        render_preserved_image(asset, placement)
