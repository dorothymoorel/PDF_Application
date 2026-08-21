"""Restricted resource loading for sanitized WeasyPrint reflow output.

WeasyPrint accepts a callable ``url_fetcher``.  This module provides one that
can read only approved asset/font roots, never follows symlinks, and never
performs network access.  It intentionally does not import WeasyPrint so the
reconstruction package remains importable when the optional renderer is absent.
"""

from __future__ import annotations

import base64
import binascii
import mimetypes
import os
from collections.abc import Callable, Collection, Mapping
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Final
from urllib.parse import unquote, unquote_to_bytes, urlsplit


class ResourceLoaderError(ValueError):
    """Base error for an unsafe or unavailable reflow resource."""


class ResourceAccessDenied(ResourceLoaderError):
    """Raised when a URL is outside the approved local resource policy."""


class ResourceNotFound(ResourceLoaderError):
    """Raised when an approved resource does not exist as a regular file."""


class ResourceTooLarge(ResourceLoaderError):
    """Raised before a resource can exceed the configured memory budget."""


class ResourceSymlinkError(ResourceAccessDenied):
    """Raised when a resource path or one of its parents is a symlink."""


@dataclass(frozen=True, slots=True)
class ResolvedResource:
    """A validated local resource selected by the loader."""

    url: str
    path: Path
    mime_type: str
    size_bytes: int


_ASSET_PREFIX: Final[str] = "assets"
_FONT_PREFIX: Final[str] = "fonts"
_DEFAULT_MAX_RESOURCE_BYTES: Final[int] = 20 * 1024 * 1024
_DEFAULT_MAX_DATA_URI_BYTES: Final[int] = 1 * 1024 * 1024
_NETWORK_SCHEMES: Final[frozenset[str]] = frozenset({"http", "https", "ftp"})
_FONT_MIME_TYPES: Final[dict[str, str]] = {
    ".otf": "font/otf",
    ".ttf": "font/ttf",
    ".woff": "font/woff",
    ".woff2": "font/woff2",
}


class RestrictedResourceLoader:
    """Resolve only approved local assets and fonts for WeasyPrint.

    Relative URLs must use ``assets/<approved-id>`` or ``fonts/<approved-id>``.
    If an explicit mapping is supplied, the ID maps to that exact file; when no
    mapping is supplied, the ID is resolved below the corresponding root.  The
    optional ID sets turn the latter behavior into an explicit allowlist.
    """

    def __init__(
        self,
        *,
        data_root: str | os.PathLike[str] | None = None,
        asset_root: str | os.PathLike[str] | None = None,
        font_root: str | os.PathLike[str] | None = None,
        approved_assets: Mapping[str, str | os.PathLike[str]] | None = None,
        approved_fonts: Mapping[str, str | os.PathLike[str]] | None = None,
        approved_asset_ids: Collection[str] | None = None,
        approved_font_ids: Collection[str] | None = None,
        max_resource_bytes: int = _DEFAULT_MAX_RESOURCE_BYTES,
        max_data_uri_bytes: int = _DEFAULT_MAX_DATA_URI_BYTES,
    ) -> None:
        self._max_resource_bytes = _positive_limit(max_resource_bytes, "max_resource_bytes")
        self._max_data_uri_bytes = _positive_limit(max_data_uri_bytes, "max_data_uri_bytes")

        base_root = _safe_root(data_root, "data_root") if data_root is not None else None
        asset_value = asset_root or (base_root / _ASSET_PREFIX if base_root is not None else None)
        font_value = font_root or (base_root / _FONT_PREFIX if base_root is not None else None)
        if asset_value is None and font_value is not None:
            asset_value = font_value
        if font_value is None and asset_value is not None:
            font_value = asset_value
        if asset_value is None or font_value is None:
            raise ResourceAccessDenied("asset_root or data_root and font_root are required.")
        self._asset_root = _safe_root(asset_value, "asset_root")
        self._font_root = _safe_root(font_value, "font_root")
        self._approved_assets = _prepare_mapping(approved_assets, self._asset_root, "asset")
        self._approved_fonts = _prepare_mapping(approved_fonts, self._font_root, "font")
        self._approved_asset_ids = _prepare_ids(approved_asset_ids, "asset")
        self._approved_font_ids = _prepare_ids(approved_font_ids, "font")

    @property
    def asset_root(self) -> Path:
        return self._asset_root

    @property
    def font_root(self) -> Path:
        return self._font_root

    def resolve(self, url: str) -> ResolvedResource:
        """Validate a URL and return its approved local path metadata."""

        raw_url = _validate_url_text(url)
        if raw_url.casefold().startswith("data:"):
            _reject_data_uri(raw_url, self._max_data_uri_bytes)
        parsed = urlsplit(raw_url)
        scheme = parsed.scheme.casefold()
        if scheme in _NETWORK_SCHEMES:
            raise ResourceAccessDenied("Network resource schemes are not allowed.")
        if scheme and scheme != "file":
            raise ResourceAccessDenied("Only approved local resource URLs are allowed.")
        if parsed.query or parsed.fragment:
            raise ResourceAccessDenied("Resource queries and fragments are not allowed.")
        if parsed.netloc:
            raise ResourceAccessDenied("Network hosts and UNC resources are not allowed.")

        if scheme == "file":
            path = _file_url_path(parsed.path)
            return self._resolve_absolute_path(raw_url, path)
        return self._resolve_relative_path(raw_url, parsed.path)

    def fetch(
        self,
        url: str,
        *,
        timeout: float = 10.0,
        ssl_context: object | None = None,
    ) -> dict[str, object]:
        """Return the mapping expected by WeasyPrint's ``url_fetcher`` API."""

        del timeout, ssl_context
        resource = self.resolve(url)
        try:
            data = resource.path.read_bytes()
        except OSError as exc:
            raise ResourceNotFound("The approved resource could not be read.") from exc
        if len(data) > self._max_resource_bytes:
            raise ResourceTooLarge("The resource exceeds the configured size limit.")
        return {
            "file_obj": BytesIO(data),
            "mime_type": resource.mime_type,
            "encoding": None,
        }

    def url_fetcher(
        self,
        url: str,
        timeout: float = 10.0,
        ssl_context: object | None = None,
    ) -> dict[str, object]:
        """Adapter method suitable for ``HTML(..., url_fetcher=...)``."""

        return self.fetch(url, timeout=timeout, ssl_context=ssl_context)

    __call__ = url_fetcher

    def _resolve_relative_path(self, url: str, raw_path: str) -> ResolvedResource:
        decoded = unquote(raw_path)
        if _looks_like_absolute_or_unc(decoded):
            raise ResourceAccessDenied("Absolute, drive-qualified, and UNC paths are not allowed.")
        if "\\" in decoded or "\x00" in decoded:
            raise ResourceAccessDenied("Resource paths must use safe relative URL components.")
        parts = PurePosixPath(decoded).parts
        if not parts or any(part in {"", ".", ".."} for part in parts):
            raise ResourceAccessDenied("Resource path traversal is not allowed.")
        prefix = parts[0].casefold()
        if prefix == _ASSET_PREFIX:
            root = self._asset_root
            identifier = "/".join(parts[1:])
            mapping = self._approved_assets
            approved_ids = self._approved_asset_ids
        elif prefix == _FONT_PREFIX:
            root = self._font_root
            identifier = "/".join(parts[1:])
            mapping = self._approved_fonts
            approved_ids = self._approved_font_ids
        else:
            raise ResourceAccessDenied("Only assets/ and fonts/ resources are allowed.")
        if not identifier:
            raise ResourceAccessDenied("A resource identifier is required.")
        if approved_ids and identifier not in approved_ids:
            raise ResourceAccessDenied("The resource identifier is not approved.")
        if mapping and identifier not in mapping:
            raise ResourceAccessDenied("The resource identifier is not approved.")
        candidate = mapping.get(identifier, root.joinpath(*parts[1:]))
        return self._validated_file(url, candidate, root)

    def _resolve_absolute_path(self, url: str, raw_path: str) -> ResolvedResource:
        if "\x00" in raw_path:
            raise ResourceAccessDenied("Null bytes are not allowed in resource paths.")
        candidate = Path(raw_path)
        if not candidate.is_absolute():
            raise ResourceAccessDenied("File URLs must contain an absolute path.")
        canonical = candidate.resolve(strict=False)
        roots = (
            (self._asset_root, self._approved_assets, self._approved_asset_ids),
            (self._font_root, self._approved_fonts, self._approved_font_ids),
        )
        for root, mapping, approved_ids in roots:
            if canonical.is_relative_to(root):
                identifier = canonical.relative_to(root).as_posix()
                if approved_ids and identifier not in approved_ids:
                    raise ResourceAccessDenied("The file URL is not an approved resource.")
                if mapping:
                    approved_path = next(
                        (
                            path
                            for path in mapping.values()
                            if path.resolve(strict=False) == canonical
                        ),
                        None,
                    )
                    if approved_path is None:
                        raise ResourceAccessDenied("The file URL is not an approved resource.")
                    candidate = approved_path
                return self._validated_file(url, candidate, root)
        raise ResourceAccessDenied("The file URL is outside approved resource roots.")

    def _validated_file(self, url: str, candidate: Path, root: Path) -> ResolvedResource:
        _reject_symlink_chain(root, candidate)
        canonical = candidate.resolve(strict=False)
        if not canonical.is_relative_to(root):
            raise ResourceAccessDenied("The resource escapes its approved root.")
        if not candidate.is_file() or candidate.is_symlink():
            raise ResourceNotFound("The approved resource is not a regular file.")
        try:
            size = candidate.stat().st_size
        except OSError as exc:
            raise ResourceNotFound("The approved resource could not be inspected.") from exc
        if size > self._max_resource_bytes:
            raise ResourceTooLarge("The resource exceeds the configured size limit.")
        return ResolvedResource(
            url=url, path=candidate, mime_type=_mime_type(candidate), size_bytes=size
        )


RestrictedWeasyPrintResourceLoader = RestrictedResourceLoader
WeasyPrintResourceLoader = RestrictedResourceLoader


def make_restricted_url_fetcher(
    loader: RestrictedResourceLoader,
) -> Callable[[str, float, object | None], dict[str, object]]:
    """Return a callable for WeasyPrint without importing the optional package."""

    if not isinstance(loader, RestrictedResourceLoader):
        raise TypeError("loader must be a RestrictedResourceLoader.")
    return loader.url_fetcher


def _safe_root(value: str | os.PathLike[str], field_name: str) -> Path:
    try:
        raw = os.fspath(value)
    except TypeError as exc:
        raise ResourceAccessDenied(f"{field_name} must be an absolute path.") from exc
    if not isinstance(raw, str) or not raw or "\x00" in raw or not raw.isprintable():
        raise ResourceAccessDenied(f"{field_name} must be an absolute path.")
    path = Path(raw)
    if not path.is_absolute() or path == Path(path.anchor) or path.anchor.startswith("\\\\"):
        raise ResourceAccessDenied(f"{field_name} must be a safe local directory.")
    _reject_root_symlinks(path, field_name)
    return path.resolve(strict=False)


def _positive_limit(value: int, field_name: str) -> int:
    if type(value) is not int or value <= 0:
        raise ResourceAccessDenied(f"{field_name} must be a positive integer.")
    return value


def _prepare_mapping(
    value: Mapping[str, str | os.PathLike[str]] | None,
    root: Path,
    kind: str,
) -> dict[str, Path]:
    if value is None:
        return {}
    prepared: dict[str, Path] = {}
    for identifier, raw_path in value.items():
        _validate_identifier(identifier, kind)
        try:
            candidate = Path(os.fspath(raw_path))
        except TypeError as exc:
            raise ResourceAccessDenied(f"Approved {kind} paths must be valid paths.") from exc
        if not candidate.is_absolute():
            candidate = root / candidate
        canonical = candidate.resolve(strict=False)
        if not canonical.is_relative_to(root):
            raise ResourceAccessDenied(f"Approved {kind} paths must remain inside their root.")
        prepared[identifier] = candidate
    return prepared


def _prepare_ids(value: Collection[str] | None, kind: str) -> frozenset[str]:
    if value is None:
        return frozenset()
    result = frozenset(value)
    for identifier in result:
        _validate_identifier(identifier, kind)
    return result


def _validate_identifier(value: str, kind: str) -> None:
    if (
        type(value) is not str
        or not value
        or value in {".", ".."}
        or "/" in value
        or "\\" in value
        or "\x00" in value
        or not value.isprintable()
    ):
        raise ResourceAccessDenied(f"Approved {kind} identifiers must be safe local names.")


def _validate_url_text(value: object) -> str:
    if type(value) is not str or not value or "\x00" in value or not value.isprintable():
        raise ResourceAccessDenied("The resource URL is invalid.")
    return value


def _looks_like_absolute_or_unc(value: str) -> bool:
    windows = PureWindowsPath(value)
    return value.startswith(("/", "\\")) or windows.is_absolute() or bool(windows.drive)


def _file_url_path(value: str) -> str:
    decoded = unquote(value)
    if decoded.startswith("/") and len(decoded) > 2 and decoded[2] == ":":
        decoded = decoded[1:]
    if _looks_like_absolute_or_unc(decoded) is False:
        raise ResourceAccessDenied("File URLs must contain an absolute local path.")
    return decoded


def _reject_data_uri(value: str, max_bytes: int) -> None:
    header, separator, payload = value.partition(",")
    if not separator or not header.casefold().startswith("data:"):
        raise ResourceAccessDenied("The data URI is invalid.")
    try:
        if ";base64" in header.casefold():
            decoded = base64.b64decode(payload, validate=True)
        else:
            decoded = unquote_to_bytes(payload)
    except (binascii.Error, ValueError) as exc:
        raise ResourceAccessDenied("The data URI is invalid.") from exc
    if len(decoded) > max_bytes:
        raise ResourceTooLarge("The data URI exceeds the configured size limit.")
    raise ResourceAccessDenied("Data URI resources are not approved local resources.")


def _reject_symlink_chain(root: Path, candidate: Path) -> None:
    try:
        relative = candidate.relative_to(root)
    except ValueError as exc:
        raise ResourceAccessDenied("The resource is outside its approved root.") from exc
    current = root
    if current.is_symlink():
        raise ResourceSymlinkError("Approved resource roots must not be symlinks.")
    for part in relative.parts:
        current /= part
        if current.is_symlink():
            raise ResourceSymlinkError("Symlink resources are not allowed.")


def _reject_root_symlinks(path: Path, field_name: str) -> None:
    current = Path(path.anchor)
    for part in path.parts[1:]:
        current /= part
        if current.is_symlink():
            raise ResourceSymlinkError(f"{field_name} cannot contain symbolic links.")


def _mime_type(path: Path) -> str:
    if path.suffix.casefold() in _FONT_MIME_TYPES:
        return _FONT_MIME_TYPES[path.suffix.casefold()]
    guessed, _encoding = mimetypes.guess_type(path.name)
    return guessed or "application/octet-stream"
