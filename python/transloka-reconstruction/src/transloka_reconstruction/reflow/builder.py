"""Build a small, deterministic, and sanitized HTML representation of a document."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from html import escape
from re import fullmatch
from typing import Final

from .types import (
    ReflowBlock,
    ReflowBlockKind,
    ReflowDocument,
    ReflowPage,
    ReflowResult,
    ReflowTable,
    validate_local_asset_id,
)


class ReflowError(ValueError):
    """Base error for invalid reflow input."""


class ReflowSecurityError(ReflowError):
    """Raised when input attempts to escape the internal HTML contract."""


INTERNAL_CSS: Final[str] = """/* TransLoka internal reflow stylesheet. */
:root {
  --reflow-text: #1f2937;
  --reflow-muted: #4b5563;
  --reflow-border: #d1d5db;
  --reflow-code: #f3f4f6;
}

@page {
  margin: 18mm 16mm;
}

* {
  box-sizing: border-box;
}

body {
  color: var(--reflow-text);
  font-family: sans-serif;
  font-size: 11pt;
  line-height: 1.45;
  margin: 0;
}

.reflow-page {
  break-after: page;
}

.reflow-page:last-child {
  break-after: auto;
}

h1,
h2,
h3,
h4,
h5,
h6 {
  break-after: avoid;
  line-height: 1.2;
  margin: 0.8em 0 0.35em;
}

p,
blockquote,
figure,
table,
pre,
ul,
ol {
  break-inside: avoid;
  margin: 0 0 0.8em;
}

.reflow-subtitle,
figcaption {
  color: var(--reflow-muted);
}

blockquote {
  border-left: 3px solid var(--reflow-border);
  margin-left: 0;
  padding-left: 1em;
}

pre {
  background: var(--reflow-code);
  padding: 0.7em;
  white-space: pre-wrap;
}

code {
  font-family: monospace;
}

img {
  height: auto;
  max-width: 100%;
}

table {
  border-collapse: collapse;
  width: 100%;
}

th,
td {
  border: 1px solid var(--reflow-border);
  padding: 0.35em 0.5em;
  text-align: left;
  vertical-align: top;
}

.reflow-page-break {
  break-before: page;
  height: 0;
}
"""

_LANGUAGE_PATTERN: Final[str] = r"^[A-Za-z]{2,8}(?:-[A-Za-z0-9]{1,8})*$"


class SanitizedReflowBuilder:
    """Convert Document IR or normalized reflow values to safe HTML/CSS.

    The builder owns every emitted tag and attribute.  Text is always escaped,
    CSS is fixed internal CSS, and images can only reference an opaque local
    asset ID.  Resource resolution is intentionally deferred to M10-T09.
    """

    def build(
        self,
        document: ReflowDocument | Sequence[ReflowBlock] | Mapping[str, object] | object,
    ) -> ReflowResult:
        normalized = _normalize_document(document)
        return _render_document(normalized)

    def build_html(
        self,
        document: ReflowDocument | Sequence[ReflowBlock] | Mapping[str, object] | object,
    ) -> str:
        """Return only the complete sanitized HTML document."""

        return self.build(document).html


# Readable aliases for callers that describe the output rather than the
# implementation class.
ReflowHTMLBuilder = SanitizedReflowBuilder
SanitizedHTMLBuilder = SanitizedReflowBuilder


def build_reflow_html(
    document: ReflowDocument | Sequence[ReflowBlock] | Mapping[str, object] | object,
) -> str:
    """Convenience function returning sanitized HTML."""

    return SanitizedReflowBuilder().build_html(document)


def build_sanitized_reflow(
    document: ReflowDocument | Sequence[ReflowBlock] | Mapping[str, object] | object,
) -> ReflowResult:
    """Convenience function returning HTML, CSS, and referenced assets."""

    return SanitizedReflowBuilder().build(document)


def _normalize_document(
    document: ReflowDocument | Sequence[ReflowBlock] | Mapping[str, object] | object,
) -> ReflowDocument:
    if isinstance(document, ReflowDocument):
        return document
    if isinstance(document, Mapping):
        return _document_from_mapping(document)
    if isinstance(document, Sequence) and not isinstance(document, (str, bytes, bytearray)):
        blocks = tuple(document)
        if any(type(block) is not ReflowBlock for block in blocks):
            raise TypeError("a block sequence must contain ReflowBlock values.")
        return ReflowDocument(blocks=blocks)
    return _document_from_ir(document)


def _document_from_mapping(payload: Mapping[str, object]) -> ReflowDocument:
    blocks_value = payload.get("blocks", ())
    pages_value = payload.get("pages", ())
    blocks = _coerce_blocks(blocks_value)
    pages = tuple(_page_from_mapping(page) for page in _objects(pages_value))
    title = payload.get("title")
    language = payload.get("language", "und")
    document_id = payload.get("document_id")
    if title is not None and type(title) is not str:
        raise TypeError("document title must be a string or None.")
    if type(language) is not str:
        raise TypeError("document language must be a string.")
    if document_id is not None and type(document_id) is not str:
        raise TypeError("document_id must be a string or None.")
    return ReflowDocument(
        blocks=blocks,
        pages=pages,
        document_id=document_id,
        title=title,
        language=language,
    )


def _page_from_mapping(value: object) -> ReflowPage:
    if not isinstance(value, Mapping):
        raise TypeError("page values must be mappings.")
    page_id = value.get("page_id", "page-1")
    if type(page_id) is not str:
        raise TypeError("page_id must be a string.")
    return ReflowPage(page_id=page_id, blocks=_coerce_blocks(value.get("blocks", ())))


def _coerce_blocks(value: object) -> tuple[ReflowBlock, ...]:
    if isinstance(value, (str, bytes, bytearray)) or not isinstance(value, Sequence):
        raise TypeError("blocks must be a sequence.")
    result: list[ReflowBlock] = []
    for item in value:
        if isinstance(item, ReflowBlock):
            result.append(item)
        elif isinstance(item, Mapping):
            result.append(_block_from_mapping(item))
        else:
            raise TypeError("blocks must contain ReflowBlock values or mappings.")
    return tuple(result)


def _block_from_mapping(value: Mapping[str, object]) -> ReflowBlock:
    block_id = value.get("block_id", "block-1")
    kind = value.get("kind", value.get("block_type", ReflowBlockKind.PARAGRAPH))
    text = value.get("text", value.get("source_text", ""))
    level = value.get("level", 1)
    asset_id = value.get("asset_id")
    alt_text = value.get("alt_text")
    ordered = value.get("ordered", False)
    children = _coerce_blocks(value.get("children", ()))
    table_value = value.get("table")
    table = _table_from_mapping(table_value) if table_value is not None else None
    if type(block_id) is not str or type(text) is not str or type(level) is not int:
        raise TypeError("block_id, text, and level have invalid types.")
    if asset_id is not None and type(asset_id) is not str:
        raise TypeError("asset_id must be a string or None.")
    if alt_text is not None and type(alt_text) is not str:
        raise TypeError("alt_text must be a string or None.")
    if type(ordered) is not bool:
        raise TypeError("ordered must be a boolean.")
    return ReflowBlock(
        block_id=block_id,
        kind=kind if isinstance(kind, (str, ReflowBlockKind)) else ReflowBlockKind.PARAGRAPH,
        text=text,
        level=level,
        asset_id=asset_id,
        alt_text=alt_text,
        ordered=ordered,
        table=table,
        children=children,
    )


def _table_from_mapping(value: object) -> ReflowTable:
    if not isinstance(value, Mapping):
        raise TypeError("table must be a mapping.")
    rows_value = value.get("rows", ())
    if isinstance(rows_value, (str, bytes, bytearray)) or not isinstance(rows_value, Sequence):
        raise TypeError("table rows must be a sequence.")
    rows: list[tuple[str, ...]] = []
    for row in rows_value:
        if isinstance(row, (str, bytes, bytearray)) or not isinstance(row, Sequence):
            raise TypeError("table rows must contain sequences of strings.")
        if any(type(cell) is not str for cell in row):
            raise TypeError("table cells must be strings.")
        rows.append(tuple(row))
    header_row = value.get("header_row", False)
    if type(header_row) is not bool:
        raise TypeError("header_row must be a boolean.")
    return ReflowTable(rows=tuple(rows), header_row=header_row)


def _document_from_ir(document: object) -> ReflowDocument:
    pages_value = getattr(document, "pages", None)
    if pages_value is None or isinstance(pages_value, (str, bytes, bytearray)):
        raise TypeError(
            "document must be a ReflowDocument, block sequence, mapping, or Document IR."
        )
    pages = tuple(_page_from_ir(page) for page in pages_value)
    title = getattr(document, "title", None)
    language = getattr(document, "target_language", None) or getattr(
        document, "source_language", "und"
    )
    document_id = getattr(document, "document_id", None)
    if title is not None and type(title) is not str:
        title = None
    if type(language) is not str:
        language = "und"
    if document_id is not None and type(document_id) is not str:
        document_id = None
    return ReflowDocument(
        pages=pages,
        document_id=document_id,
        title=title,
        language=language,
    )


def _page_from_ir(page: object) -> ReflowPage:
    page_id = getattr(page, "page_id", None)
    raw_blocks = getattr(page, "blocks", ())
    if type(page_id) is not str:
        raise TypeError("Document IR pages must expose a string page_id.")
    tables: dict[str, object] = {}
    for table_item in getattr(page, "tables", ()):
        table_id = _read(table_item, "table_id")
        block_id = _read(table_item, "block_id")
        if table_id is not None:
            tables[str(table_id)] = table_item
        if block_id is not None:
            tables[f"block:{block_id}"] = table_item
    segments = {
        str(_read(segment, "segment_id")): segment
        for block in raw_blocks
        for segment in getattr(block, "segments", ())
        if _read(segment, "segment_id") is not None
    }
    assets = tuple(getattr(page, "assets", ()))
    used_assets: set[str] = set()
    blocks = []
    for block in sorted(raw_blocks, key=lambda item: getattr(item, "reading_order", 0)):
        converted = _block_from_ir(block, tables, segments, assets, used_assets)
        blocks.append(converted)
    for asset in assets:
        asset_id = _asset_id(asset)
        if asset_id not in used_assets and _is_image_asset(asset):
            blocks.append(
                ReflowBlock(
                    block_id=f"asset-{asset_id}",
                    kind=ReflowBlockKind.IMAGE,
                    asset_id=asset_id,
                    alt_text=getattr(asset, "alt_text", None),
                )
            )
            used_assets.add(asset_id)
    return ReflowPage(page_id=page_id, blocks=tuple(blocks))


def _block_from_ir(
    block: object,
    tables: Mapping[str, object],
    segments: Mapping[str, object],
    assets: Sequence[object],
    used_assets: set[str],
) -> ReflowBlock:
    block_id = getattr(block, "block_id", None)
    if type(block_id) is not str:
        raise TypeError("Document IR blocks must expose a string block_id.")
    raw_kind = _enum_text(getattr(block, "block_type", "paragraph"))
    kind, level = _kind_and_level(raw_kind)
    text = _resolve_text(block, segments)
    table = None
    if kind is ReflowBlockKind.TABLE:
        table_id = _read(block, "table_id")
        table = _table_from_ir(
            tables.get(str(table_id)) if table_id is not None else tables.get(f"block:{block_id}"),
            segments,
        )
    asset_id: str | None = None
    alt_text: str | None = None
    if kind in {ReflowBlockKind.IMAGE, ReflowBlockKind.FIGURE}:
        candidate = getattr(block, "asset_id", None)
        if candidate is None:
            candidates = getattr(block, "asset_ids", ())
            candidate = next(iter(candidates), None)
        asset = next((item for item in assets if _asset_id(item) == candidate), None)
        if asset is None:
            asset = next((item for item in assets if _asset_id(item) not in used_assets), None)
        if asset is not None:
            asset_id = _asset_id(asset)
            used_assets.add(asset_id)
            alt_text = getattr(asset, "alt_text", None)
    return ReflowBlock(
        block_id=block_id,
        kind=kind,
        text=text,
        level=level,
        asset_id=asset_id,
        alt_text=alt_text,
        table=table,
    )


def _kind_and_level(value: str) -> tuple[ReflowBlockKind, int]:
    normalized = value.casefold()
    if normalized == "document_title":
        return ReflowBlockKind.TITLE, 1
    if normalized == "subtitle":
        return ReflowBlockKind.SUBTITLE, 2
    if normalized.startswith("heading_"):
        suffix = normalized.rsplit("_", 1)[-1]
        if suffix.isdigit() and 1 <= int(suffix) <= 6:
            return ReflowBlockKind.HEADING, int(suffix)
    mapping = {
        "blockquote": ReflowBlockKind.BLOCKQUOTE,
        "list": ReflowBlockKind.LIST,
        "list_item": ReflowBlockKind.LIST_ITEM,
        "code_block": ReflowBlockKind.CODE,
        "table": ReflowBlockKind.TABLE,
        "image": ReflowBlockKind.IMAGE,
        "figure": ReflowBlockKind.FIGURE,
        "caption": ReflowBlockKind.CAPTION,
        "page_break": ReflowBlockKind.PAGE_BREAK,
    }
    return mapping.get(normalized, ReflowBlockKind.PARAGRAPH), 1


def _resolve_text(block: object, segments: Mapping[str, object]) -> str:
    values: list[str] = []
    for segment in sorted(
        getattr(block, "segments", ()),
        key=lambda item: getattr(item, "segment_order", 0),
    ):
        final_text = getattr(segment, "final_text", None)
        if type(final_text) is str:
            values.append(final_text)
        elif (
            _read(segment, "segment_id") is not None
            and str(_read(segment, "segment_id")) in segments
        ):
            fallback = _read(segments[str(_read(segment, "segment_id"))], "source_text")
            if type(fallback) is str:
                values.append(fallback)
    if values:
        return "\n".join(values)
    source_text = getattr(block, "source_text", "")
    return source_text if type(source_text) is str else ""


def _table_from_ir(table: object | None, segments: Mapping[str, object]) -> ReflowTable | None:
    if table is None:
        return None
    row_count = getattr(table, "row_count", 0)
    column_count = getattr(table, "column_count", 0)
    if (
        type(row_count) is not int
        or type(column_count) is not int
        or not row_count
        or not column_count
    ):
        return None
    cells = {(cell.row_index, cell.column_index): cell for cell in getattr(table, "cells", ())}
    rows: list[tuple[str, ...]] = []
    for row_index in range(row_count):
        row: list[str] = []
        for column_index in range(column_count):
            cell = cells.get((row_index, column_index))
            row.append(_cell_text(cell, segments))
        rows.append(tuple(row))
    return ReflowTable(rows=tuple(rows), header_row=bool(getattr(table, "has_header_row", False)))


def _cell_text(cell: object | None, segments: Mapping[str, object]) -> str:
    if cell is None:
        return ""
    values = []
    for segment_id in getattr(cell, "segment_ids", ()):
        segment = segments.get(str(segment_id))
        final_text = getattr(segment, "final_text", None) if segment is not None else None
        if type(final_text) is str:
            values.append(final_text)
    if values:
        return "\n".join(values)
    source_text = getattr(cell, "source_text", "")
    return source_text if type(source_text) is str else ""


def _render_document(document: ReflowDocument) -> ReflowResult:
    language = _safe_language(document.language)
    title = escape(document.title or "TransLoka document", quote=True)
    asset_ids: list[str] = []
    body: list[str] = []
    for page in document.effective_pages():
        page_id = escape(page.page_id, quote=True)
        body.append(f'<section class="reflow-page" data-page-id="{page_id}">')
        for block in page.blocks:
            body.append(_render_block(block, asset_ids))
        body.append("</section>")
    document_attribute = ""
    if document.document_id:
        document_attribute = f' data-document-id="{escape(document.document_id, quote=True)}"'
    html = (
        "<!doctype html>\n"
        f'<html lang="{language}">\n'
        "<head>\n"
        '<meta charset="utf-8">\n'
        f"<title>{title}</title>\n"
        f"<style>\n{INTERNAL_CSS}</style>\n"
        "</head>\n"
        f"<body{document_attribute}>\n" + "\n".join(body) + "\n</body>\n</html>\n"
    )
    return ReflowResult(html=html, css=INTERNAL_CSS, asset_ids=tuple(asset_ids))


def _render_block(block: ReflowBlock, asset_ids: list[str]) -> str:
    block_id = escape(block.block_id, quote=True)
    marker = f' data-block-id="{block_id}"'
    text = escape(block.text, quote=True)
    if block.kind is ReflowBlockKind.TITLE:
        return f"<h1{marker}>{text}</h1>"
    if block.kind is ReflowBlockKind.SUBTITLE:
        return f'<p class="reflow-subtitle"{marker}>{text}</p>'
    if block.kind is ReflowBlockKind.HEADING:
        return f"<h{block.level}{marker}>{text}</h{block.level}>"
    if block.kind is ReflowBlockKind.BLOCKQUOTE:
        return f"<blockquote{marker}>{text}</blockquote>"
    if block.kind is ReflowBlockKind.CODE:
        return f"<pre{marker}><code>{text}</code></pre>"
    if block.kind is ReflowBlockKind.LIST:
        tag = "ol" if block.ordered else "ul"
        children = block.children or (
            ReflowBlock(block_id=f"{block.block_id}-item", text=block.text),
        )
        items = "".join(_render_list_item(child) for child in children)
        return f"<{tag}{marker}>{items}</{tag}>"
    if block.kind is ReflowBlockKind.LIST_ITEM:
        return f"<li{marker}>{text}</li>"
    if block.kind is ReflowBlockKind.TABLE and block.table is not None:
        return _render_table(block, marker)
    if block.kind in {ReflowBlockKind.IMAGE, ReflowBlockKind.FIGURE}:
        return _render_image(block, marker, asset_ids)
    if block.kind is ReflowBlockKind.CAPTION:
        return f"<figcaption{marker}>{text}</figcaption>"
    if block.kind is ReflowBlockKind.PAGE_BREAK:
        return f'<div class="reflow-page-break"{marker}></div>'
    return f"<p{marker}>{text}</p>"


def _render_list_item(block: ReflowBlock) -> str:
    marker = f' data-block-id="{escape(block.block_id, quote=True)}"'
    text = escape(block.text, quote=True)
    return f"<li{marker}>{text}</li>"


def _render_table(block: ReflowBlock, marker: str) -> str:
    assert block.table is not None
    rows = block.table.rows
    if not rows:
        return f"<table{marker}><tbody></tbody></table>"
    head = ""
    body_rows = rows
    if block.table.header_row:
        head_cells = "".join(f"<th>{escape(cell, quote=True)}</th>" for cell in rows[0])
        head = f"<thead><tr>{head_cells}</tr></thead>"
        body_rows = rows[1:]
    body = "".join(
        "<tr>" + "".join(f"<td>{escape(cell, quote=True)}</td>" for cell in row) + "</tr>"
        for row in body_rows
    )
    return f"<table{marker}>{head}<tbody>{body}</tbody></table>"


def _render_image(block: ReflowBlock, marker: str, asset_ids: list[str]) -> str:
    caption = escape(block.text, quote=True)
    if block.asset_id is None:
        return (
            f"<figure{marker}>{f'<figcaption>{caption}</figcaption>' if caption else ''}</figure>"
        )
    try:
        asset_id = validate_local_asset_id(block.asset_id)
    except ValueError as exc:
        raise ReflowSecurityError(str(exc)) from exc
    if asset_id not in asset_ids:
        asset_ids.append(asset_id)
    src = escape(f"assets/{asset_id}", quote=True)
    alt = escape(block.alt_text or block.text or "", quote=True)
    image = f'<img src="{src}" alt="{alt}" data-asset-id="{escape(asset_id, quote=True)}">'
    caption_html = f"<figcaption>{caption}</figcaption>" if caption else ""
    return f"<figure{marker}>{image}{caption_html}</figure>"


def _safe_language(value: str) -> str:
    if fullmatch(_LANGUAGE_PATTERN, value) is None:
        raise ReflowSecurityError("language must be a valid language tag.")
    return escape(value, quote=True)


def _asset_id(asset: object) -> str:
    value = getattr(asset, "asset_id", None)
    try:
        return validate_local_asset_id(value)
    except ValueError as exc:
        raise ReflowSecurityError(str(exc)) from exc


def _is_image_asset(asset: object) -> bool:
    asset_type = _enum_text(getattr(asset, "asset_type", ""))
    mime_type = getattr(asset, "mime_type", "")
    return asset_type.casefold() in {"image", "figure"} or (
        type(mime_type) is str and mime_type.casefold().startswith("image/")
    )


def _enum_text(value: object) -> str:
    raw = getattr(value, "value", value)
    return raw if type(raw) is str else str(raw)


def _read(value: object, name: str, default: object = None) -> object:
    """Read an optional field from both Pydantic models and test doubles."""

    return getattr(value, name, default)


def _objects(value: object) -> tuple[object, ...]:
    if isinstance(value, (str, bytes, bytearray)) or not isinstance(value, Sequence):
        raise TypeError("value must be a sequence.")
    return tuple(value)
