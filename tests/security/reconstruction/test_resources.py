import base64
from io import BytesIO
from pathlib import Path

import pytest
from transloka_reconstruction.reflow import (
    ResourceAccessDenied,
    ResourceSymlinkError,
    ResourceTooLarge,
    RestrictedResourceLoader,
)


@pytest.fixture
def resource_roots(tmp_path: Path) -> tuple[Path, Path, Path]:
    assets = tmp_path / "assets"
    fonts = tmp_path / "fonts"
    assets.mkdir()
    fonts.mkdir()
    (assets / "approved.png").write_bytes(b"png-bytes")
    (fonts / "approved.ttf").write_bytes(b"font-bytes")
    return tmp_path, assets, fonts


def test_approved_local_asset_and_font_are_readable(
    resource_roots: tuple[Path, Path, Path],
) -> None:
    _root, assets, fonts = resource_roots
    loader = RestrictedResourceLoader(
        asset_root=assets,
        font_root=fonts,
        approved_assets={"cover": assets / "approved.png"},
        approved_fonts={"body": fonts / "approved.ttf"},
    )

    asset = loader.fetch("assets/cover")
    font = loader.fetch("fonts/body")

    assert asset["mime_type"] == "image/png"
    assert font["mime_type"] == "font/ttf"
    assert isinstance(asset["file_obj"], BytesIO)
    assert isinstance(font["file_obj"], BytesIO)
    assert asset["file_obj"].read() == b"png-bytes"
    assert font["file_obj"].read() == b"font-bytes"


def test_path_traversal_and_outside_file_url_are_rejected(
    resource_roots: tuple[Path, Path, Path],
) -> None:
    root, assets, fonts = resource_roots
    outside = root / "outside.txt"
    outside.write_text("outside", encoding="utf-8")
    loader = RestrictedResourceLoader(asset_root=assets, font_root=fonts)

    with pytest.raises(ResourceAccessDenied):
        loader.fetch("assets/../outside.txt")
    with pytest.raises(ResourceAccessDenied):
        loader.fetch(outside.as_uri())


@pytest.mark.parametrize(
    "url",
    (
        "http://example.test/image.png",
        "https://example.test/image.png",
        "ftp://example.test/font.ttf",
        "http://localhost:8000/asset.png",
        "http://127.0.0.1/asset.png",
        "//server/share/asset.png",
        r"\\server\share\asset.png",
    ),
)
def test_remote_localhost_and_unc_resources_are_rejected(
    resource_roots: tuple[Path, Path, Path],
    url: str,
) -> None:
    _root, assets, fonts = resource_roots
    loader = RestrictedResourceLoader(asset_root=assets, font_root=fonts)

    with pytest.raises(ResourceAccessDenied):
        loader.fetch(url)


def test_oversized_data_uri_is_rejected_before_loading(
    resource_roots: tuple[Path, Path, Path],
) -> None:
    _root, assets, fonts = resource_roots
    loader = RestrictedResourceLoader(
        asset_root=assets,
        font_root=fonts,
        max_data_uri_bytes=4,
    )
    encoded = base64.b64encode(b"12345").decode("ascii")

    with pytest.raises(ResourceTooLarge):
        loader.fetch(f"data:image/png;base64,{encoded}")


def test_symlink_resource_is_rejected(
    resource_roots: tuple[Path, Path, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root, assets, fonts = resource_roots
    outside = root / "outside.png"
    outside.write_bytes(b"outside")
    link = assets / "link.png"
    try:
        link.symlink_to(outside)
    except (OSError, NotImplementedError):
        # Windows CI may not grant symlink creation.  Keep this a real
        # regression test by simulating the filesystem predicate instead of
        # silently skipping a critical control.
        link.write_bytes(outside.read_bytes())
        monkeypatch.setattr(Path, "is_symlink", lambda path: path == link)
    loader = RestrictedResourceLoader(asset_root=assets, font_root=fonts)

    with pytest.raises(ResourceSymlinkError):
        loader.fetch("assets/link.png")
