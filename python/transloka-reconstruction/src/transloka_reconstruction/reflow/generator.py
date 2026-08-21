"""Generate searchable PDFs from the sanitized reflow HTML contract.

The renderer is deliberately a small boundary around the optional WeasyPrint
dependency.  HTML is produced by :mod:`reflow.builder`; this module adds only
the page settings needed by the PDF output and gives WeasyPrint a restricted
resource fetcher.  It never uses WeasyPrint's default network/file resolver.
"""

from __future__ import annotations

import math
import re
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from html.parser import HTMLParser
from importlib import import_module
from io import BytesIO
from os import PathLike, fspath
from pathlib import Path
from typing import Protocol, cast

from .builder import ReflowError, ReflowSecurityError, SanitizedReflowBuilder
from .resources import (
    ResourceAccessDenied,
    RestrictedResourceLoader,
)
from .types import ReflowDocument, ReflowResult


class ReflowDependencyError(ReflowError):
    """Raised when the optional PDF renderer is not installed correctly."""


class ReflowGenerationError(ReflowError):
    """Raised when a generated PDF is invalid or cannot be written."""


_A4_WIDTH_PT = 595.275590551
_A4_HEIGHT_PT = 841.88976378
_MM_TO_PT = 72.0 / 25.4
_DEFAULT_MARGIN_TOP_PT = 18.0 * _MM_TO_PT
_DEFAULT_MARGIN_RIGHT_PT = 16.0 * _MM_TO_PT
_DEFAULT_MARGIN_BOTTOM_PT = 18.0 * _MM_TO_PT
_DEFAULT_MARGIN_LEFT_PT = 16.0 * _MM_TO_PT


@dataclass(frozen=True, slots=True)
class ReflowPageSettings:
    """Validated page geometry expressed in PDF points."""

    width_pt: float = _A4_WIDTH_PT
    height_pt: float = _A4_HEIGHT_PT
    margin_top_pt: float = _DEFAULT_MARGIN_TOP_PT
    margin_right_pt: float = _DEFAULT_MARGIN_RIGHT_PT
    margin_bottom_pt: float = _DEFAULT_MARGIN_BOTTOM_PT
    margin_left_pt: float = _DEFAULT_MARGIN_LEFT_PT

    def __post_init__(self) -> None:
        for name in (
            "width_pt",
            "height_pt",
            "margin_top_pt",
            "margin_right_pt",
            "margin_bottom_pt",
            "margin_left_pt",
        ):
            value = getattr(self, name)
            if type(value) not in {int, float} or not math.isfinite(value) or value <= 0:
                raise ValueError(f"{name} must be a finite positive number.")
        if self.margin_top_pt + self.margin_bottom_pt >= self.height_pt:
            raise ValueError("vertical margins must leave usable page height.")
        if self.margin_left_pt + self.margin_right_pt >= self.width_pt:
            raise ValueError("horizontal margins must leave usable page width.")

    @property
    def css(self) -> str:
        """Return the controlled CSS overlay used for pagination."""

        return (
            "@page {\n"
            f"  size: {self.width_pt:.6f}pt {self.height_pt:.6f}pt;\n"
            f"  margin: {self.margin_top_pt:.6f}pt {self.margin_right_pt:.6f}pt "
            f"{self.margin_bottom_pt:.6f}pt {self.margin_left_pt:.6f}pt;\n"
            "}\n"
            "p, li, blockquote, pre {\n"
            "  widows: 2;\n"
            "  orphans: 2;\n"
            "}\n"
            "h1, h2, h3, h4, h5, h6 {\n"
            "  break-after: avoid;\n"
            "  page-break-after: avoid;\n"
            "}\n"
            "figure, table, pre {\n"
            "  break-inside: avoid;\n"
            "  page-break-inside: avoid;\n"
            "}\n"
        )


PageSettings = ReflowPageSettings


class _WeasyPdfDocument(Protocol):
    def write_pdf(self, *, stylesheets: Sequence[object] | None = None) -> bytes: ...


class _WeasyHtmlFactory(Protocol):
    def __call__(self, *, string: str, url_fetcher: Callable[..., object]) -> _WeasyPdfDocument: ...


class _WeasyCssFactory(Protocol):
    def __call__(self, *, string: str) -> object: ...


class _ResourceReferenceParser(HTMLParser):
    """Collect only attributes which can make WeasyPrint load a resource."""

    _RESOURCE_ATTRIBUTES: dict[str, tuple[str, ...]] = {
        "img": ("src",),
        "source": ("src",),
        "audio": ("src",),
        "video": ("src",),
        "link": ("href",),
    }
    _UNSAFE_TAGS = frozenset({"embed", "frame", "iframe", "object", "script"})

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.references: list[str] = []
        self._style_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        normalized_tag = tag.casefold()
        if normalized_tag in self._UNSAFE_TAGS:
            raise ReflowSecurityError(f"the {normalized_tag} tag is not allowed in reflow HTML.")
        self._collect_attributes(normalized_tag, attrs)
        if normalized_tag == "style":
            self._style_depth += 1

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        normalized_tag = tag.casefold()
        if normalized_tag in self._UNSAFE_TAGS:
            raise ReflowSecurityError(f"the {normalized_tag} tag is not allowed in reflow HTML.")
        self._collect_attributes(normalized_tag, attrs)

    def handle_endtag(self, tag: str) -> None:
        if tag.casefold() == "style" and self._style_depth:
            self._style_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._style_depth:
            self.references.extend(_css_urls(data))

    def _collect_attributes(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        wanted = self._RESOURCE_ATTRIBUTES.get(tag, ())
        for name, value in attrs:
            if name.casefold() in wanted and value:
                self.references.append(value)
            if name.casefold() == "style" and value:
                self.references.extend(_css_urls(value))


_CSS_URL_PATTERN = re.compile(
    r"url\(\s*(?:['\"](?P<quoted>[^'\"]+)['\"]|(?P<bare>[^)\s]+))\s*\)",
    flags=re.IGNORECASE,
)


def _css_urls(value: str) -> tuple[str, ...]:
    return tuple(
        match.group("quoted") or match.group("bare") for match in _CSS_URL_PATTERN.finditer(value)
    )


def _deny_resource(url: str, *args: object, **kwargs: object) -> dict[str, object]:
    del args, kwargs
    raise ResourceAccessDenied(f"resource access requires an approved local loader: {url}")


class ReflowPDFGenerator:
    """Render sanitized HTML into a validated searchable PDF."""

    def __init__(
        self,
        *,
        page_settings: ReflowPageSettings | None = None,
        resource_loader: RestrictedResourceLoader | None = None,
    ) -> None:
        self.page_settings = page_settings or ReflowPageSettings()
        if resource_loader is not None and not isinstance(
            resource_loader, RestrictedResourceLoader
        ):
            raise TypeError("resource_loader must be a RestrictedResourceLoader or None.")
        self.resource_loader = resource_loader

    def generate(
        self,
        source: ReflowDocument | ReflowResult | str | object,
        *,
        output_path: str | PathLike[str] | None = None,
    ) -> bytes:
        """Generate PDF bytes, optionally writing the same bytes to ``output_path``."""

        result = self._result(source)
        _validate_resource_references(result.html, self.resource_loader)
        html_factory, css_factory = _load_weasyprint()
        fetcher: Callable[..., object]
        if self.resource_loader is None:
            fetcher = _deny_resource
        else:
            fetcher = cast(Callable[..., object], self.resource_loader.url_fetcher)
        try:
            document = html_factory(string=result.html, url_fetcher=fetcher)
            stylesheet = css_factory(string=self.page_settings.css)
            rendered = document.write_pdf(stylesheets=[stylesheet])
        except ResourceAccessDenied:
            raise
        except Exception as exc:
            raise ReflowGenerationError("WeasyPrint could not generate the reflow PDF.") from exc
        pdf_bytes = bytes(rendered)
        _validate_pdf(pdf_bytes)
        if output_path is not None:
            self._write_output(pdf_bytes, output_path)
        return pdf_bytes

    render = generate

    def _result(self, source: ReflowDocument | ReflowResult | str | object) -> ReflowResult:
        if isinstance(source, ReflowResult):
            return source
        if isinstance(source, str):
            return ReflowResult(html=source, css="")
        return SanitizedReflowBuilder().build(source)

    @staticmethod
    def _write_output(pdf_bytes: bytes, output_path: str | PathLike[str]) -> None:
        try:
            path = Path(fspath(output_path))
            path.write_bytes(pdf_bytes)
        except (OSError, TypeError, ValueError) as exc:
            raise ReflowGenerationError("The generated PDF could not be written.") from exc


ReflowGenerator = ReflowPDFGenerator


def generate_reflow_pdf(
    source: ReflowDocument | ReflowResult | str | object,
    *,
    page_settings: ReflowPageSettings | None = None,
    resource_loader: RestrictedResourceLoader | None = None,
    output_path: str | PathLike[str] | None = None,
) -> bytes:
    """Convenience wrapper around :class:`ReflowPDFGenerator`."""

    return ReflowPDFGenerator(
        page_settings=page_settings,
        resource_loader=resource_loader,
    ).generate(source, output_path=output_path)


def _load_weasyprint() -> tuple[_WeasyHtmlFactory, _WeasyCssFactory]:
    try:
        module = import_module("weasyprint")
    except (ImportError, OSError) as exc:
        raise ReflowDependencyError(
            "WeasyPrint is required for reflow PDF generation; install the optional "
            "renderer in the runtime environment."
        ) from exc
    html_factory = getattr(module, "HTML", None)
    css_factory = getattr(module, "CSS", None)
    if not callable(html_factory) or not callable(css_factory):
        raise ReflowDependencyError("The installed WeasyPrint package has no HTML/CSS API.")
    return cast(_WeasyHtmlFactory, html_factory), cast(_WeasyCssFactory, css_factory)


def _validate_resource_references(
    html: str,
    loader: RestrictedResourceLoader | None,
) -> None:
    parser = _ResourceReferenceParser()
    try:
        parser.feed(html)
        parser.close()
    except ReflowSecurityError:
        raise
    except Exception as exc:
        raise ReflowSecurityError("reflow HTML could not be parsed safely.") from exc
    references = tuple(parser.references)
    if not references:
        return
    if loader is None:
        raise ResourceAccessDenied("resource references require an approved local loader.")
    for url in references:
        loader.resolve(url)


def _validate_pdf(pdf_bytes: bytes) -> None:
    if not pdf_bytes.startswith(b"%PDF-") or b"%%EOF" not in pdf_bytes[-1024:]:
        raise ReflowGenerationError("WeasyPrint returned an invalid PDF stream.")
    try:
        from pypdf import PdfReader

        reader = PdfReader(BytesIO(pdf_bytes), strict=False)
        if len(reader.pages) < 1:
            raise ReflowGenerationError("The generated PDF has no pages.")
    except ReflowGenerationError:
        raise
    except Exception as exc:
        raise ReflowGenerationError("The generated PDF could not be validated.") from exc


__all__ = [
    "PageSettings",
    "ReflowDependencyError",
    "ReflowGenerationError",
    "ReflowGenerator",
    "ReflowPDFGenerator",
    "ReflowPageSettings",
    "generate_reflow_pdf",
]
