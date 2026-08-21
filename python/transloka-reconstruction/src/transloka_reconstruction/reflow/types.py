"""Immutable values used by the sanitized reflow HTML builder."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from re import fullmatch
from typing import Final


class ReflowBlockKind(StrEnum):
    """Document structures that the internal reflow renderer can emit."""

    TITLE = "title"
    SUBTITLE = "subtitle"
    HEADING = "heading"
    PARAGRAPH = "paragraph"
    BLOCKQUOTE = "blockquote"
    LIST = "list"
    LIST_ITEM = "list_item"
    CODE = "code"
    TABLE = "table"
    IMAGE = "image"
    FIGURE = "figure"
    CAPTION = "caption"
    PAGE_BREAK = "page_break"


# The short, opaque ID is deliberately stricter than a filesystem path.  The
# next reflow task maps this ID to an approved local resource.
LOCAL_ASSET_ID_PATTERN: Final[str] = r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$"


def validate_local_asset_id(value: object) -> str:
    """Validate an asset identifier without accepting URLs or paths."""

    if type(value) is not str or fullmatch(LOCAL_ASSET_ID_PATTERN, value) is None:
        raise ValueError("asset_id must be a short local identifier, not a URL or path.")
    return value


@dataclass(frozen=True, slots=True)
class ReflowTable:
    """A small table represented as rows of cell text."""

    rows: tuple[tuple[str, ...], ...]
    header_row: bool = False

    def __post_init__(self) -> None:
        normalized = tuple(tuple(_text(cell) for cell in row) for row in self.rows)
        if any(len(row) == 0 for row in normalized):
            raise ValueError("table rows must contain at least one cell.")
        object.__setattr__(self, "rows", normalized)


@dataclass(frozen=True, slots=True)
class ReflowBlock:
    """A normalized block accepted by :class:`SanitizedReflowBuilder`."""

    block_id: str
    kind: ReflowBlockKind | str = ReflowBlockKind.PARAGRAPH
    text: str = ""
    level: int = 1
    asset_id: str | None = None
    alt_text: str | None = None
    ordered: bool = False
    table: ReflowTable | None = None
    children: tuple[ReflowBlock, ...] = ()

    def __post_init__(self) -> None:
        if type(self.block_id) is not str or not self.block_id.strip():
            raise ValueError("block_id must be a non-empty string.")
        object.__setattr__(self, "text", _text(self.text))
        if type(self.level) is not int or self.level < 1 or self.level > 6:
            raise ValueError("level must be an integer between 1 and 6.")
        if self.asset_id is not None:
            validate_local_asset_id(self.asset_id)
        if self.alt_text is not None:
            object.__setattr__(self, "alt_text", _text(self.alt_text))
        if not isinstance(self.ordered, bool):
            raise ValueError("ordered must be a boolean.")
        if not isinstance(self.kind, ReflowBlockKind):
            object.__setattr__(self, "kind", _coerce_kind(self.kind))
        if any(type(child) is not ReflowBlock for child in self.children):
            raise TypeError("children must contain ReflowBlock values.")


@dataclass(frozen=True, slots=True)
class ReflowPage:
    """A page-shaped grouping retained while converting Document IR."""

    page_id: str
    blocks: tuple[ReflowBlock, ...] = ()

    def __post_init__(self) -> None:
        if type(self.page_id) is not str or not self.page_id.strip():
            raise ValueError("page_id must be a non-empty string.")
        if any(type(block) is not ReflowBlock for block in self.blocks):
            raise TypeError("blocks must contain ReflowBlock values.")


@dataclass(frozen=True, slots=True)
class ReflowDocument:
    """Minimal document shape used by the renderer and its tests."""

    blocks: tuple[ReflowBlock, ...] = ()
    pages: tuple[ReflowPage, ...] = ()
    document_id: str | None = None
    title: str | None = None
    language: str = "und"

    def __post_init__(self) -> None:
        if any(type(block) is not ReflowBlock for block in self.blocks):
            raise TypeError("blocks must contain ReflowBlock values.")
        if any(type(page) is not ReflowPage for page in self.pages):
            raise TypeError("pages must contain ReflowPage values.")
        if self.document_id is not None and type(self.document_id) is not str:
            raise ValueError("document_id must be a string or None.")
        if self.title is not None:
            object.__setattr__(self, "title", _text(self.title))
        if type(self.language) is not str or not self.language.strip():
            raise ValueError("language must be a non-empty string.")

    def effective_pages(self) -> tuple[ReflowPage, ...]:
        """Return explicit pages, or one synthetic page for flat documents."""

        if self.pages:
            return self.pages
        return (ReflowPage(page_id="page-1", blocks=self.blocks),)


@dataclass(frozen=True, slots=True)
class ReflowResult:
    """Deterministic sanitized HTML, CSS, and referenced local asset IDs."""

    html: str
    css: str
    asset_ids: tuple[str, ...] = ()

    def __str__(self) -> str:
        return self.html


def _text(value: object) -> str:
    if type(value) is not str:
        raise ValueError("reflow text must be a string.")
    return value.replace("\r\n", "\n").replace("\r", "\n")


def _coerce_kind(value: object) -> ReflowBlockKind:
    raw = getattr(value, "value", value)
    normalized = str(raw).casefold()
    if normalized.startswith("heading_") and normalized[-1:].isdigit():
        return ReflowBlockKind.HEADING
    aliases = {
        "document_title": ReflowBlockKind.TITLE,
        "code_block": ReflowBlockKind.CODE,
        "figure": ReflowBlockKind.FIGURE,
    }
    if normalized in aliases:
        return aliases[normalized]
    try:
        return ReflowBlockKind(normalized)
    except ValueError:
        # Unknown IR block types are rendered as plain paragraphs instead of
        # becoming arbitrary HTML.
        return ReflowBlockKind.PARAGRAPH
