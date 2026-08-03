import hashlib
import math
from contextlib import closing
from dataclasses import dataclass
from io import BufferedReader, BytesIO
from tempfile import SpooledTemporaryFile
from typing import BinaryIO, Literal, cast

import pypdfium2 as pdfium  # type: ignore[import-untyped]
from PIL import Image
from transloka_core.storage.local import (
    LocalFileStorage,
    StoredFileArtifact,
    StoredFileExistsError,
    StoredFileNotFoundError,
)

ALLOWED_RENDER_DPI = frozenset({72, 96, 120, 144, 150, 200, 300})
THUMBNAIL_MAX_SIZE = (320, 320)
_MAX_RENDER_DIMENSION = 10_000
_MAX_RENDER_PIXELS = 40_000_000
_SPOOL_MEMORY_LIMIT = 8 * 1024 * 1024
_CACHE_VERSION = "v1"


class PageRenderingError(RuntimeError):
    pass


class UnsupportedRenderDpiError(ValueError):
    pass


class PageRenderTooLargeError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class RenderedFileRecord:
    file_role: Literal["PAGE_RENDER", "THUMBNAIL"]
    storage_key: str
    safe_filename: str
    mime_type: str
    size_bytes: int
    checksum_sha256: str


@dataclass(frozen=True, slots=True)
class PageRenderResult:
    page_number: int
    dpi: int
    source_checksum_sha256: str
    cache_key: str
    render: RenderedFileRecord
    thumbnail: RenderedFileRecord
    cache_hit: bool


def render_pdf_page(
    stream: BinaryIO,
    *,
    storage: LocalFileStorage,
    project_id: str,
    page_number: int,
    dpi: int,
) -> PageRenderResult:
    _validate_request(page_number, dpi)
    try:
        original_position = stream.tell()
        source_checksum = _checksum_stream(stream)
        cache_key = _cache_key(source_checksum, page_number, dpi)
        render_key = f"projects/{project_id}/pages/{cache_key}.png"
        thumbnail_key = f"projects/{project_id}/thumbnails/{cache_key}.webp"

        cached = _load_cache(storage, render_key, thumbnail_key)
        if cached is not None:
            return PageRenderResult(
                page_number=page_number,
                dpi=dpi,
                source_checksum_sha256=source_checksum,
                cache_key=cache_key,
                render=cached[0],
                thumbnail=cached[1],
                cache_hit=True,
            )

        stream.seek(0)
        render, thumbnail = _render_and_store(
            stream,
            storage=storage,
            page_number=page_number,
            dpi=dpi,
            render_key=render_key,
            thumbnail_key=thumbnail_key,
        )
        return PageRenderResult(
            page_number=page_number,
            dpi=dpi,
            source_checksum_sha256=source_checksum,
            cache_key=cache_key,
            render=render,
            thumbnail=thumbnail,
            cache_hit=False,
        )
    except (UnsupportedRenderDpiError, PageRenderTooLargeError, PageRenderingError):
        raise
    except Exception as exc:
        raise PageRenderingError("The PDF page could not be rendered safely.") from exc
    finally:
        try:
            stream.seek(original_position)
        except (NameError, OSError, ValueError):
            pass


def _validate_request(page_number: int, dpi: int) -> None:
    if isinstance(page_number, bool) or not isinstance(page_number, int) or page_number < 1:
        raise PageRenderingError("The PDF page number is invalid.")
    if isinstance(dpi, bool) or not isinstance(dpi, int) or dpi not in ALLOWED_RENDER_DPI:
        raise UnsupportedRenderDpiError("The requested render DPI is not allowed.")


def _checksum_stream(stream: BinaryIO) -> str:
    stream.seek(0)
    checksum = hashlib.sha256()
    for chunk in iter(lambda: stream.read(1024 * 1024), b""):
        if not isinstance(chunk, bytes):
            raise TypeError("The PDF stream returned invalid data.")
        checksum.update(chunk)
    return checksum.hexdigest()


def _cache_key(source_checksum: str, page_number: int, dpi: int) -> str:
    payload = f"{_CACHE_VERSION}:{source_checksum}:{page_number}:{dpi}:png:webp"
    return hashlib.sha256(payload.encode()).hexdigest()


def _load_cache(
    storage: LocalFileStorage,
    render_key: str,
    thumbnail_key: str,
) -> tuple[RenderedFileRecord, RenderedFileRecord] | None:
    try:
        render = _existing_record(storage, "PAGE_RENDER", render_key, "image/png")
        thumbnail = _existing_record(storage, "THUMBNAIL", thumbnail_key, "image/webp")
    except StoredFileNotFoundError:
        return None
    return render, thumbnail


def _render_and_store(
    stream: BinaryIO,
    *,
    storage: LocalFileStorage,
    page_number: int,
    dpi: int,
    render_key: str,
    thumbnail_key: str,
) -> tuple[RenderedFileRecord, RenderedFileRecord]:
    typed_stream = cast(BufferedReader | BytesIO, stream)
    with pdfium.PdfDocument(typed_stream, autoclose=False) as document:
        if page_number > len(document):
            raise ValueError("The PDF page does not exist.")
        with closing(document[page_number - 1]) as page:
            scale = dpi / 72
            _validate_render_size(page.get_width(), page.get_height(), scale)
            with closing(
                page.render(
                    scale=scale,
                    fill_color=(255, 255, 255, 0),
                    limit_image_cache=True,
                    rev_byteorder=True,
                )
            ) as bitmap:
                image = bitmap.to_pil()
                try:
                    render = _store_image(
                        storage,
                        image,
                        file_role="PAGE_RENDER",
                        storage_key=render_key,
                        mime_type="image/png",
                        image_format="PNG",
                    )
                    image.thumbnail(THUMBNAIL_MAX_SIZE, Image.Resampling.LANCZOS)
                    thumbnail = _store_image(
                        storage,
                        image,
                        file_role="THUMBNAIL",
                        storage_key=thumbnail_key,
                        mime_type="image/webp",
                        image_format="WEBP",
                    )
                finally:
                    image.close()
    return render, thumbnail


def _validate_render_size(width_points: float, height_points: float, scale: float) -> None:
    if (
        not math.isfinite(width_points)
        or not math.isfinite(height_points)
        or width_points <= 0
        or height_points <= 0
    ):
        raise PageRenderingError("The PDF page geometry is invalid.")
    width = math.ceil(width_points * scale)
    height = math.ceil(height_points * scale)
    if (
        width > _MAX_RENDER_DIMENSION
        or height > _MAX_RENDER_DIMENSION
        or width * height > _MAX_RENDER_PIXELS
    ):
        raise PageRenderTooLargeError("The requested PDF page render is too large.")


def _store_image(
    storage: LocalFileStorage,
    image: Image.Image,
    *,
    file_role: Literal["PAGE_RENDER", "THUMBNAIL"],
    storage_key: str,
    mime_type: str,
    image_format: Literal["PNG", "WEBP"],
) -> RenderedFileRecord:
    with SpooledTemporaryFile(max_size=_SPOOL_MEMORY_LIMIT, mode="w+b") as output:
        if image_format == "WEBP":
            image.save(output, format=image_format, lossless=True, method=4)
        else:
            image.save(output, format=image_format)
        output.seek(0)
        temporary = storage.write_temporary(cast(BinaryIO, output))
    try:
        artifact = storage.commit(temporary, storage_key)
    except StoredFileExistsError:
        return _existing_record(storage, file_role, storage_key, mime_type)
    return _artifact_record(file_role, storage_key, mime_type, artifact)


def _existing_record(
    storage: LocalFileStorage,
    file_role: Literal["PAGE_RENDER", "THUMBNAIL"],
    storage_key: str,
    mime_type: str,
) -> RenderedFileRecord:
    checksum = hashlib.sha256()
    size_bytes = 0
    with storage.open_read(storage_key) as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            checksum.update(chunk)
            size_bytes += len(chunk)
    return RenderedFileRecord(
        file_role=file_role,
        storage_key=storage_key,
        safe_filename=storage_key.rsplit("/", 1)[-1],
        mime_type=mime_type,
        size_bytes=size_bytes,
        checksum_sha256=checksum.hexdigest(),
    )


def _artifact_record(
    file_role: Literal["PAGE_RENDER", "THUMBNAIL"],
    storage_key: str,
    mime_type: str,
    artifact: StoredFileArtifact,
) -> RenderedFileRecord:
    return RenderedFileRecord(
        file_role=file_role,
        storage_key=storage_key,
        safe_filename=storage_key.rsplit("/", 1)[-1],
        mime_type=mime_type,
        size_bytes=artifact.size_bytes,
        checksum_sha256=artifact.checksum_sha256,
    )
