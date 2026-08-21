"""Deterministic image placement for the reconstruction pipeline.

The image layer keeps the source asset immutable and returns geometry instead
of mutating a PDF page.  The returned geometry is in PDF user space with an
origin at the lower-left corner.  Raster rendering is deliberately a separate
operation so a missing asset can be reported without preventing the rest of a
page from being reconstructed.
"""

from __future__ import annotations

import math
import os
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from io import BytesIO
from pathlib import Path
from typing import cast

from PIL import Image, UnidentifiedImageError


class ImagePreservationError(ValueError):
    """Base error for invalid image-preservation input."""


class MissingImageError(ImagePreservationError):
    """Raised when raster output is requested for a missing asset."""


class ImageFit(StrEnum):
    """Aspect-ratio-safe fitting modes."""

    CONTAIN = "CONTAIN"
    COVER = "COVER"


FitMode = ImageFit


class ImagePosition(StrEnum):
    """Anchor used for spare space or a crop window."""

    TOP_LEFT = "TOP_LEFT"
    TOP_CENTER = "TOP_CENTER"
    TOP_RIGHT = "TOP_RIGHT"
    CENTER_LEFT = "CENTER_LEFT"
    CENTER = "CENTER"
    CENTER_RIGHT = "CENTER_RIGHT"
    BOTTOM_LEFT = "BOTTOM_LEFT"
    BOTTOM_CENTER = "BOTTOM_CENTER"
    BOTTOM_RIGHT = "BOTTOM_RIGHT"


PlacementPosition = ImagePosition


class CaptionRelation(StrEnum):
    """Relationship between an image and its caption block."""

    ABOVE = "ABOVE"
    BELOW = "BELOW"
    OVERLAY = "OVERLAY"
    NONE = "NONE"


class ImageWarningCode(StrEnum):
    """Stable warning codes emitted by image preservation."""

    MISSING_ASSET = "MISSING_ASSET"
    INVALID_ASSET = "INVALID_ASSET"
    ASSET_METADATA_MISMATCH = "ASSET_METADATA_MISMATCH"
    IMAGE_OUT_OF_BOUNDS = "IMAGE_OUT_OF_BOUNDS"
    CAPTION_OUT_OF_BOUNDS = "CAPTION_OUT_OF_BOUNDS"


def _finite(value: object, field_name: str, *, positive: bool = False) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ImagePreservationError(f"{field_name} must be a finite number.")
    converted = float(value)
    if not math.isfinite(converted) or (positive and converted <= 0):
        qualifier = "positive " if positive else ""
        raise ImagePreservationError(f"{field_name} must be a finite {qualifier}number.")
    return converted


def _positive_int(value: object, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
        raise ImagePreservationError(f"{field_name} must be a positive integer.")
    return value


def _text(value: object, field_name: str) -> str:
    if type(value) is not str or not value.strip():
        raise ImagePreservationError(f"{field_name} must be a non-empty string.")
    return value


def _enum_value[EnumValue: StrEnum](
    enum_type: type[EnumValue], value: object, field_name: str
) -> EnumValue:
    if isinstance(value, enum_type):
        return value
    if type(value) is not str:
        raise ImagePreservationError(f"{field_name} must be a known value.")
    try:
        return enum_type(value)
    except ValueError as exc:
        raise ImagePreservationError(f"{field_name} must be a known value.") from exc


@dataclass(frozen=True, slots=True)
class ImageRect:
    """A finite positive rectangle in PDF user space or source pixels."""

    x: float
    y: float
    width: float
    height: float

    def __post_init__(self) -> None:
        object.__setattr__(self, "x", _finite(self.x, "x"))
        object.__setattr__(self, "y", _finite(self.y, "y"))
        object.__setattr__(self, "width", _finite(self.width, "width", positive=True))
        object.__setattr__(self, "height", _finite(self.height, "height", positive=True))

    @property
    def right(self) -> float:
        return self.x + self.width

    @property
    def top(self) -> float:
        return self.y + self.height

    @property
    def area(self) -> float:
        return self.width * self.height

    def contains(self, other: ImageRect, *, tolerance: float = 1e-9) -> bool:
        return (
            other.x >= self.x - tolerance
            and other.y >= self.y - tolerance
            and other.right <= self.right + tolerance
            and other.top <= self.top + tolerance
        )


@dataclass(frozen=True, slots=True)
class ImageAsset:
    """Metadata and optional source bytes/path for one extracted image.

    ``source`` is intentionally optional.  Extraction can persist only an
    approved storage reference first; preservation then emits a stable
    ``MISSING_ASSET`` warning until the reference is resolved by the caller.
    """

    asset_id: str
    page_id: str
    width_px: int | None = None
    height_px: int | None = None
    source: object | None = None
    storage_key: str | None = None
    mime_type: str | None = None
    rotation_degrees: float = 0.0
    opacity: float = 1.0
    z_index: int = 0
    caption_block_id: str | None = None
    major: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(self, "asset_id", _text(self.asset_id, "asset_id"))
        object.__setattr__(self, "page_id", _text(self.page_id, "page_id"))
        if self.width_px is not None:
            object.__setattr__(self, "width_px", _positive_int(self.width_px, "width_px"))
        if self.height_px is not None:
            object.__setattr__(self, "height_px", _positive_int(self.height_px, "height_px"))
        rotation = _finite(self.rotation_degrees, "rotation_degrees") % 360.0
        quarter_turn = round(rotation / 90.0) * 90.0
        if not math.isclose(rotation, quarter_turn % 360.0, abs_tol=1e-6):
            raise ImagePreservationError("rotation_degrees must be a multiple of 90.")
        object.__setattr__(self, "rotation_degrees", quarter_turn % 360.0)
        opacity = _finite(self.opacity, "opacity")
        if not 0.0 <= opacity <= 1.0:
            raise ImagePreservationError("opacity must be between 0 and 1.")
        object.__setattr__(self, "opacity", opacity)
        if isinstance(self.z_index, bool) or not isinstance(self.z_index, int):
            raise ImagePreservationError("z_index must be an integer.")
        if self.storage_key is not None:
            object.__setattr__(self, "storage_key", _text(self.storage_key, "storage_key"))
        if self.mime_type is not None:
            object.__setattr__(self, "mime_type", _text(self.mime_type, "mime_type"))
        if self.caption_block_id is not None:
            object.__setattr__(
                self, "caption_block_id", _text(self.caption_block_id, "caption_block_id")
            )
        if type(self.major) is not bool:
            raise ImagePreservationError("major must be a boolean.")
        if self.source is None and (self.width_px is None or self.height_px is None):
            raise ImagePreservationError(
                "width_px and height_px are required when source is not available."
            )


@dataclass(frozen=True, slots=True)
class CaptionSpec:
    """Caption text and layout relation for a preserved image."""

    text: str
    relation: CaptionRelation = CaptionRelation.BELOW
    width: float | None = None
    height: float = 12.0
    gap: float = 4.0
    block_id: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "text", _text(self.text, "text"))
        object.__setattr__(
            self, "relation", _enum_value(CaptionRelation, self.relation, "relation")
        )
        if self.width is not None:
            object.__setattr__(self, "width", _finite(self.width, "width", positive=True))
        object.__setattr__(self, "height", _finite(self.height, "height", positive=True))
        object.__setattr__(self, "gap", _finite(self.gap, "gap"))
        if self.gap < 0:
            raise ImagePreservationError("gap must be non-negative.")
        if self.block_id is not None:
            object.__setattr__(self, "block_id", _text(self.block_id, "block_id"))


@dataclass(frozen=True, slots=True)
class CaptionPlacement:
    """The resolved caption rectangle and its image relationship."""

    block_id: str | None
    text: str
    relation: CaptionRelation
    rect: ImageRect
    overlaps_image: bool


@dataclass(frozen=True, slots=True)
class ImageWarning:
    """An auditable, non-fatal preservation warning."""

    code: ImageWarningCode
    message: str
    asset_id: str
    page_id: str


@dataclass(frozen=True, slots=True)
class ImagePreservationMetric:
    """Metrics for the major-image preservation gate."""

    source_aspect_ratio: float
    visible_aspect_ratio: float
    aspect_ratio_error: float
    crop_fraction: float
    scale: float
    aspect_ratio_preserved: bool
    major_image_preserved: bool

    @property
    def score(self) -> float:
        """Return a stable 0..1 score used by reconstruction validation."""

        if not self.major_image_preserved:
            return 0.0
        return max(0.0, min(1.0, 1.0 - self.crop_fraction * 0.25))


@dataclass(frozen=True, slots=True)
class ImagePlacement:
    """Resolved image geometry, crop, metadata, caption, and warnings."""

    asset_id: str
    page_id: str
    target: ImageRect
    rendered: ImageRect | None
    crop: ImageRect | None
    fit: ImageFit
    position: ImagePosition
    rotation_degrees: float
    opacity: float
    z_index: int
    caption: CaptionPlacement | None
    metric: ImagePreservationMetric | None
    warnings: tuple[ImageWarning, ...] = ()

    @property
    def aspect_ratio_preserved(self) -> bool:
        return self.metric is not None and self.metric.aspect_ratio_preserved


PreservedImage = ImagePlacement


@dataclass(frozen=True, slots=True)
class RenderedImage:
    """Raster output for a resolved placement."""

    data: bytes
    mime_type: str
    width_px: int
    height_px: int
    placement: ImagePlacement


def _position_parts(position: ImagePosition) -> tuple[str, str]:
    value = position.value
    if value == "CENTER":
        return "CENTER", "CENTER"
    vertical, horizontal = value.split("_", 1)
    return vertical, horizontal


def _offset(space: float, size: float, alignment: str) -> float:
    if alignment in {"LEFT", "BOTTOM"}:
        return 0.0
    if alignment in {"RIGHT", "TOP"}:
        return space - size
    return (space - size) / 2.0


def _oriented_dimensions(width: float, height: float, rotation: float) -> tuple[float, float]:
    if rotation in {90.0, 270.0}:
        return height, width
    return width, height


def _resolve_caption(
    asset: ImageAsset,
    image: ImageRect,
    spec: CaptionSpec | None,
    page_bounds: ImageRect | None,
) -> tuple[CaptionPlacement | None, ImageWarning | None]:
    if spec is None or spec.relation is CaptionRelation.NONE:
        return None, None
    width = spec.width if spec.width is not None else image.width
    if spec.relation is CaptionRelation.BELOW:
        rect = ImageRect(image.x, image.y - spec.gap - spec.height, width, spec.height)
    elif spec.relation is CaptionRelation.ABOVE:
        rect = ImageRect(image.x, image.top + spec.gap, width, spec.height)
    else:
        rect = ImageRect(image.x, image.y, width, spec.height)
    warning = None
    if page_bounds is not None and not page_bounds.contains(rect):
        warning = ImageWarning(
            code=ImageWarningCode.CAPTION_OUT_OF_BOUNDS,
            message="Caption relation was retained but its resolved box exceeds the page.",
            asset_id=asset.asset_id,
            page_id=asset.page_id,
        )
    overlap = spec.relation is CaptionRelation.OVERLAY
    return (
        CaptionPlacement(
            block_id=spec.block_id or asset.caption_block_id,
            text=spec.text,
            relation=spec.relation,
            rect=rect,
            overlaps_image=overlap,
        ),
        warning,
    )


def _warning(code: ImageWarningCode, message: str, asset: ImageAsset) -> ImageWarning:
    return ImageWarning(code=code, message=message, asset_id=asset.asset_id, page_id=asset.page_id)


def _load_image(source: object) -> Image.Image:
    if isinstance(source, Image.Image):
        image = source.copy()
        image.load()
        return image
    if isinstance(source, (bytes, bytearray, memoryview)):
        with Image.open(BytesIO(bytes(source))) as image:
            image.load()
            return image.copy()
    if isinstance(source, (str, os.PathLike)):
        with Image.open(Path(source)) as image:
            image.load()
            return image.copy()
    raise UnidentifiedImageError("Unsupported image source.")


class ImagePreserver:
    """Resolve and optionally rasterize one extracted image without distortion."""

    def preserve(
        self,
        asset: ImageAsset,
        target: ImageRect,
        *,
        fit: ImageFit = ImageFit.CONTAIN,
        position: ImagePosition = ImagePosition.CENTER,
        caption: CaptionSpec | None = None,
        page_bounds: ImageRect | None = None,
        page_id: str | None = None,
    ) -> ImagePlacement:
        if page_id is not None and page_id != asset.page_id:
            raise ImagePreservationError("Image asset does not belong to the requested page.")
        fit = _enum_value(ImageFit, fit, "fit")
        position = _enum_value(ImagePosition, position, "position")
        warnings: list[ImageWarning] = []
        if page_bounds is not None and not page_bounds.contains(target):
            warnings.append(
                _warning(
                    ImageWarningCode.IMAGE_OUT_OF_BOUNDS,
                    "Image target was retained but exceeds the page bounds.",
                    asset,
                )
            )

        dimensions = self._dimensions(asset, warnings)
        if dimensions is None:
            caption_placement, caption_warning = _resolve_caption(
                asset, target, caption, page_bounds
            )
            if caption_warning is not None:
                warnings.append(caption_warning)
            return ImagePlacement(
                asset_id=asset.asset_id,
                page_id=asset.page_id,
                target=target,
                rendered=None,
                crop=None,
                fit=fit,
                position=position,
                rotation_degrees=asset.rotation_degrees,
                opacity=asset.opacity,
                z_index=asset.z_index,
                caption=caption_placement,
                metric=None,
                warnings=tuple(warnings),
            )

        source_width, source_height = dimensions
        oriented_width, oriented_height = _oriented_dimensions(
            float(source_width), float(source_height), asset.rotation_degrees
        )
        source = ImageRect(0.0, 0.0, oriented_width, oriented_height)
        if fit is ImageFit.CONTAIN:
            scale = min(target.width / oriented_width, target.height / oriented_height)
            render_width = oriented_width * scale
            render_height = oriented_height * scale
            vertical, horizontal = _position_parts(position)
            rendered = ImageRect(
                target.x + _offset(target.width, render_width, horizontal),
                target.y + _offset(target.height, render_height, vertical),
                render_width,
                render_height,
            )
            crop = source
        else:
            scale = max(target.width / oriented_width, target.height / oriented_height)
            crop_width = target.width / scale
            crop_height = target.height / scale
            vertical, horizontal = _position_parts(position)
            crop = ImageRect(
                _offset(oriented_width, crop_width, horizontal),
                _offset(oriented_height, crop_height, vertical),
                crop_width,
                crop_height,
            )
            rendered = target

        caption_placement, caption_warning = _resolve_caption(asset, rendered, caption, page_bounds)
        if caption_warning is not None:
            warnings.append(caption_warning)
        visible_ratio = crop.width / crop.height
        source_ratio = oriented_width / oriented_height
        metric = ImagePreservationMetric(
            source_aspect_ratio=source_ratio,
            visible_aspect_ratio=visible_ratio,
            aspect_ratio_error=0.0,
            crop_fraction=max(0.0, min(1.0, 1.0 - crop.area / source.area)),
            scale=scale,
            aspect_ratio_preserved=True,
            major_image_preserved=asset.major,
        )
        return ImagePlacement(
            asset_id=asset.asset_id,
            page_id=asset.page_id,
            target=target,
            rendered=rendered,
            crop=crop,
            fit=fit,
            position=position,
            rotation_degrees=asset.rotation_degrees,
            opacity=asset.opacity,
            z_index=asset.z_index,
            caption=caption_placement,
            metric=metric,
            warnings=tuple(warnings),
        )

    def render(
        self,
        asset: ImageAsset,
        placement: ImagePlacement,
        *,
        output_format: str = "PNG",
    ) -> RenderedImage:
        """Render the placement into a deterministic RGBA raster.

        The source is rotated before crop calculations, so rotation never
        changes the aspect-ratio guarantee or the caption relationship.
        """

        if placement.asset_id != asset.asset_id or placement.page_id != asset.page_id:
            raise ImagePreservationError("Placement and asset identity do not match.")
        if asset.source is None or placement.rendered is None or placement.crop is None:
            raise MissingImageError(f"Asset {asset.asset_id} has no renderable source.")
        try:
            image = _load_image(asset.source).convert("RGBA")
        except (FileNotFoundError, IsADirectoryError) as exc:
            raise MissingImageError(f"Asset {asset.asset_id} is missing.") from exc
        except (OSError, UnidentifiedImageError) as exc:
            raise ImagePreservationError(
                f"Asset {asset.asset_id} is not a readable image."
            ) from exc

        if asset.rotation_degrees:
            image = image.rotate(
                -asset.rotation_degrees, expand=True, resample=Image.Resampling.BICUBIC
            )
        oriented_width, oriented_height = image.size
        crop = placement.crop
        left = max(0, min(oriented_width - 1, math.floor(crop.x)))
        top = max(0, min(oriented_height - 1, math.floor(oriented_height - crop.top)))
        right = max(left + 1, min(oriented_width, math.ceil(crop.right)))
        bottom = max(top + 1, min(oriented_height, math.ceil(oriented_height - crop.y)))
        image = image.crop((left, top, right, bottom))

        if placement.fit is ImageFit.CONTAIN:
            output_width = max(1, round(placement.target.width))
            output_height = max(1, round(placement.target.height))
            resized = image.resize(
                (max(1, round(placement.rendered.width)), max(1, round(placement.rendered.height))),
                resample=Image.Resampling.LANCZOS,
            )
            canvas = Image.new("RGBA", (output_width, output_height), (0, 0, 0, 0))
            paste_x = max(0, round(placement.rendered.x - placement.target.x))
            paste_y = max(0, round(placement.target.top - placement.rendered.top))
            canvas.alpha_composite(resized, (paste_x, paste_y))
            image = canvas
        else:
            image = image.resize(
                (max(1, round(placement.target.width)), max(1, round(placement.target.height))),
                resample=Image.Resampling.LANCZOS,
            )
        if asset.opacity < 1.0:
            alpha = image.getchannel("A")
            alpha = alpha.point(
                cast(Callable[[int], int], lambda value: round(value * asset.opacity))
            )
            image.putalpha(alpha)
        buffer = BytesIO()
        normalized_format = output_format.upper()
        if normalized_format != "PNG":
            raise ImagePreservationError("Rendered image output_format must be PNG.")
        image.save(buffer, format="PNG", optimize=False, compress_level=9)
        return RenderedImage(
            data=buffer.getvalue(),
            mime_type="image/png",
            width_px=image.width,
            height_px=image.height,
            placement=placement,
        )

    @staticmethod
    def _dimensions(asset: ImageAsset, warnings: list[ImageWarning]) -> tuple[int, int] | None:
        if asset.source is None:
            warnings.append(
                _warning(
                    ImageWarningCode.MISSING_ASSET,
                    "Image source is not available; preservation metadata was retained.",
                    asset,
                )
            )
            if asset.width_px is None or asset.height_px is None:
                return None
            return asset.width_px, asset.height_px
        try:
            with _opened_source(asset.source) as image:
                width, height = image.size
        except (FileNotFoundError, IsADirectoryError):
            warnings.append(
                _warning(
                    ImageWarningCode.MISSING_ASSET,
                    "Image source could not be found; preservation metadata was retained.",
                    asset,
                )
            )
            return None
        except (OSError, UnidentifiedImageError):
            warnings.append(
                _warning(
                    ImageWarningCode.INVALID_ASSET,
                    "Image source could not be decoded; preservation metadata was retained.",
                    asset,
                )
            )
            return None
        if width <= 0 or height <= 0:
            warnings.append(
                _warning(
                    ImageWarningCode.INVALID_ASSET,
                    "Image source has invalid dimensions.",
                    asset,
                )
            )
            return None
        if (
            asset.width_px is not None
            and asset.height_px is not None
            and (asset.width_px != width or asset.height_px != height)
        ):
            warnings.append(
                _warning(
                    ImageWarningCode.ASSET_METADATA_MISMATCH,
                    "Declared image dimensions differ from decoded source dimensions.",
                    asset,
                )
            )
        return width, height


class _OpenedSource:
    def __init__(self, image: Image.Image) -> None:
        self._image = image

    def __enter__(self) -> Image.Image:
        return self._image

    def __exit__(self, *_: object) -> None:
        self._image.close()


def _opened_source(source: object) -> _OpenedSource:
    return _OpenedSource(_load_image(source))


def preserve_image(
    asset: ImageAsset,
    target: ImageRect,
    *,
    fit: ImageFit = ImageFit.CONTAIN,
    position: ImagePosition = ImagePosition.CENTER,
    caption: CaptionSpec | None = None,
    page_bounds: ImageRect | None = None,
    page_id: str | None = None,
) -> ImagePlacement:
    """Convenience wrapper for :meth:`ImagePreserver.preserve`."""

    return ImagePreserver().preserve(
        asset,
        target,
        fit=fit,
        position=position,
        caption=caption,
        page_bounds=page_bounds,
        page_id=page_id,
    )


def render_preserved_image(
    asset: ImageAsset,
    placement: ImagePlacement,
    *,
    output_format: str = "PNG",
) -> RenderedImage:
    """Convenience wrapper for :meth:`ImagePreserver.render`."""

    return ImagePreserver().render(asset, placement, output_format=output_format)
