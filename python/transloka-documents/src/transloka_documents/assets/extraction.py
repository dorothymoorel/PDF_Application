import hashlib
import math
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from io import BufferedReader, BytesIO
from pathlib import PurePosixPath
from typing import BinaryIO, cast
from uuid import NAMESPACE_URL, uuid5

import pdfplumber
from PIL import Image
from pypdf import PdfReader
from transloka_core.storage.local import LocalFileStorage, StoredFileExistsError

from transloka_documents.extraction.models import TextGeometry


class AssetType(StrEnum):
    RASTER_IMAGE = "RASTER_IMAGE"


@dataclass(frozen=True, slots=True)
class ExtractedAsset:
    asset_id: str
    page_number: int
    occurrence_number: int
    asset_type: AssetType
    source_geometry: TextGeometry
    storage_key: str
    mime_type: str
    checksum_sha256: str
    width_px: int
    height_px: int
    aspect_ratio: float
    rotation_degrees: int
    caption_block_id: str | None


@dataclass(frozen=True, slots=True)
class AssetExtractionResult:
    assets: tuple[ExtractedAsset, ...]
    unique_file_count: int


@dataclass(frozen=True, slots=True)
class _ImagePayload:
    data: bytes
    extension: str
    mime_type: str
    checksum_sha256: str
    width_px: int
    height_px: int


class AssetExtractionError(RuntimeError):
    pass


def extract_and_store_assets(
    stream: BinaryIO,
    *,
    storage: LocalFileStorage,
    project_id: str,
    caption_block_ids: Mapping[tuple[int, int], str] | None = None,
) -> AssetExtractionResult:
    try:
        original_position = stream.tell()
        payloads = _read_payloads(stream)
        stream.seek(0)
        typed_stream = cast(BufferedReader | BytesIO, stream)
        assets: list[ExtractedAsset] = []
        stored_checksums: set[str] = set()
        with pdfplumber.open(typed_stream) as document:
            if len(document.pages) != len(payloads):
                raise AssetExtractionError("PDF parsers returned inconsistent page counts.")
            for page_number, page in enumerate(document.pages, start=1):
                rotation = int(page.rotation or 0)
                if rotation not in {0, 90, 180, 270}:
                    raise AssetExtractionError("The PDF page rotation is invalid.")
                page_payloads = payloads[page_number - 1]
                raw_images = cast(list[dict[str, object]], page.images)
                for occurrence_number, raw in enumerate(raw_images, start=1):
                    name = _normalized_name(raw.get("name"))
                    payload = page_payloads.get(name)
                    if payload is None:
                        raise AssetExtractionError(
                            "An image binary could not be matched to its geometry."
                        )
                    storage_key = f"projects/{project_id}/assets/{payload.checksum_sha256}.{payload.extension}"
                    if payload.checksum_sha256 not in stored_checksums:
                        _store_payload(storage, storage_key, payload)
                        stored_checksums.add(payload.checksum_sha256)
                    geometry = _geometry(raw, float(page.width), float(page.height))
                    identity = uuid5(
                        NAMESPACE_URL,
                        f"{payload.checksum_sha256}:{page_number}:{occurrence_number}:"
                        f"{geometry.x}:{geometry.y}:{geometry.width}:{geometry.height}",
                    )
                    assets.append(
                        ExtractedAsset(
                            asset_id=f"ast_{identity}",
                            page_number=page_number,
                            occurrence_number=occurrence_number,
                            asset_type=AssetType.RASTER_IMAGE,
                            source_geometry=geometry,
                            storage_key=storage_key,
                            mime_type=payload.mime_type,
                            checksum_sha256=payload.checksum_sha256,
                            width_px=payload.width_px,
                            height_px=payload.height_px,
                            aspect_ratio=payload.width_px / payload.height_px,
                            rotation_degrees=rotation,
                            caption_block_id=(caption_block_ids or {}).get(
                                (page_number, occurrence_number)
                            ),
                        )
                    )
        return AssetExtractionResult(assets=tuple(assets), unique_file_count=len(stored_checksums))
    except AssetExtractionError:
        raise
    except Exception as exc:
        raise AssetExtractionError("PDF assets could not be extracted safely.") from exc
    finally:
        try:
            stream.seek(original_position)
        except (NameError, OSError, ValueError):
            pass


def _read_payloads(stream: BinaryIO) -> tuple[dict[str, _ImagePayload], ...]:
    stream.seek(0)
    reader = PdfReader(stream, strict=False)
    pages: list[dict[str, _ImagePayload]] = []
    for page in reader.pages:
        payloads: dict[str, _ImagePayload] = {}
        for image_file in page.images:
            name = _normalized_name(image_file.name)
            payload = _payload(image_file.data)
            existing = payloads.get(name)
            if existing is not None and existing.checksum_sha256 != payload.checksum_sha256:
                raise AssetExtractionError("Image names are ambiguous within a PDF page.")
            payloads[name] = payload
        pages.append(payloads)
    return tuple(pages)


def _payload(data: bytes) -> _ImagePayload:
    with Image.open(BytesIO(data)) as image:
        image.load()
        width, height = image.size
        image_format = (image.format or "").upper()
    formats = {"JPEG": ("jpg", "image/jpeg"), "PNG": ("png", "image/png")}
    if image_format not in formats or width <= 0 or height <= 0:
        raise AssetExtractionError("The extracted image format is unsupported.")
    extension, mime_type = formats[image_format]
    return _ImagePayload(
        data=data,
        extension=extension,
        mime_type=mime_type,
        checksum_sha256=hashlib.sha256(data).hexdigest(),
        width_px=width,
        height_px=height,
    )


def _store_payload(storage: LocalFileStorage, storage_key: str, payload: _ImagePayload) -> None:
    temporary = storage.write_temporary(BytesIO(payload.data))
    try:
        storage.commit(temporary, storage_key, immutable=True)
    except StoredFileExistsError:
        if storage.checksum(storage_key) != payload.checksum_sha256:
            raise AssetExtractionError(
                "A checksum-addressed asset contains different data."
            ) from None


def _normalized_name(value: object) -> str:
    if not isinstance(value, str) or not value:
        raise AssetExtractionError("An image reference name is invalid.")
    return PurePosixPath(value.lstrip("/")).stem


def _geometry(raw: dict[str, object], page_width: float, page_height: float) -> TextGeometry:
    x0 = _number(raw.get("x0"))
    top = _number(raw.get("top"))
    x1 = _number(raw.get("x1"))
    bottom = _number(raw.get("bottom"))
    if x1 <= x0 or bottom <= top or x0 < 0 or top < 0 or x1 > page_width or bottom > page_height:
        raise AssetExtractionError("Image geometry must remain within the PDF page.")
    return TextGeometry(x=x0, y=top, width=x1 - x0, height=bottom - top)


def _number(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise AssetExtractionError("Image geometry is invalid.")
    number = float(value)
    if not math.isfinite(number):
        raise AssetExtractionError("Image geometry is invalid.")
    return number
