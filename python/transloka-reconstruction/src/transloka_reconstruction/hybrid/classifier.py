"""Deterministic page and block strategy selection for Hybrid Mode.

The classifier consumes either small descriptor values or the repository's
Document IR objects.  It does not render or mutate a document.  Every result
contains its evidence and a canonical hash so callers can persist and compare
decisions without depending on object identity or hash randomization.
"""

from __future__ import annotations

import hashlib
import json
import math
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import cast

from transloka_reconstruction.settings import (
    ReconstructionMode,
    ReconstructionSettings,
    TableComplexityFallback,
)


class PageClassification(StrEnum):
    """Stable page-shape labels used by the reconstruction pipeline."""

    FIXED_LAYOUT = "FIXED_LAYOUT"
    REFLOW_FRIENDLY = "REFLOW_FRIENDLY"
    MIXED_LAYOUT = "MIXED_LAYOUT"
    IMAGE_ONLY = "IMAGE_ONLY"
    TABLE_HEAVY = "TABLE_HEAVY"
    CODE_HEAVY = "CODE_HEAVY"
    FORMULA_HEAVY = "FORMULA_HEAVY"
    COVER = "COVER"
    UNKNOWN = "UNKNOWN"


PageKind = PageClassification


class PageStrategy(StrEnum):
    """Strategy selected for a complete page."""

    PRESERVE = "PRESERVE"
    OVERLAY = "OVERLAY"
    REFLOW = "REFLOW"
    HYBRID = "HYBRID"
    MANUAL_REVIEW = "MANUAL_REVIEW"


class BlockStrategy(StrEnum):
    """Strategy selected for one page block."""

    PRESERVE = "PRESERVE"
    OVERLAY = "OVERLAY"
    REFLOW = "REFLOW"
    RECONSTRUCT = "RECONSTRUCT"
    RENDER_AS_IMAGE = "RENDER_AS_IMAGE"
    MANUAL_REVIEW = "MANUAL_REVIEW"


ReconstructionStrategy = BlockStrategy


class TableComplexity(StrEnum):
    """Table complexity values used by the safe fallback chain."""

    SIMPLE = "SIMPLE"
    COMPLEX = "COMPLEX"
    UNKNOWN = "UNKNOWN"


_FIXED_BLOCK_TYPES = frozenset(
    {
        "DOCUMENT_TITLE",
        "SUBTITLE",
        "HEADER",
        "FOOTER",
        "PAGE_NUMBER",
        "CAPTION",
        "EQUATION_LABEL",
        "DECORATIVE_TEXT",
    }
)
_BODY_BLOCK_TYPES = frozenset(
    {
        "PARAGRAPH",
        "BLOCKQUOTE",
        "LIST",
        "LIST_ITEM",
        "FOOTNOTE",
        "ENDNOTE",
        "BIBLIOGRAPHY_ENTRY",
        "INDEX_ENTRY",
        "TABLE_OF_CONTENTS_ENTRY",
        "SIDEBAR",
        "CALLOUT",
    }
)
_UNSUPPORTED_BLOCK_TYPES = frozenset(
    {
        "FORM_FIELD",
        "SIGNATURE_FIELD",
        "UNKNOWN",
    }
)
_TEXT_TYPES = (
    _FIXED_BLOCK_TYPES
    | _BODY_BLOCK_TYPES
    | {
        "HEADING_1",
        "HEADING_2",
        "HEADING_3",
        "HEADING_4",
        "HEADING_5",
        "HEADING_6",
        "CODE_BLOCK",
        "FORMULA",
    }
)


@dataclass(frozen=True, slots=True)
class BlockDescriptor:
    """Minimal normalized signals for one block classification."""

    block_id: str
    block_type: str = "UNKNOWN"
    text: str = ""
    expansion_ratio: float | None = None
    fixed: bool = False
    supported: bool = True
    table_complexity: TableComplexity | str = TableComplexity.SIMPLE

    def __post_init__(self) -> None:
        if type(self.block_id) is not str or not self.block_id.strip():
            raise ValueError("block_id must be a non-empty string.")
        if type(self.block_type) is not str or not self.block_type.strip():
            raise ValueError("block_type must be a non-empty string.")
        object.__setattr__(self, "block_type", _enum_text(self.block_type))
        if type(self.text) is not str:
            raise ValueError("text must be a string.")
        if self.expansion_ratio is not None:
            if (
                isinstance(self.expansion_ratio, bool)
                or not isinstance(self.expansion_ratio, (int, float))
                or not math.isfinite(float(self.expansion_ratio))
                or self.expansion_ratio < 0
            ):
                raise ValueError("expansion_ratio must be a finite non-negative number.")
            object.__setattr__(self, "expansion_ratio", float(self.expansion_ratio))
        if type(self.fixed) is not bool or type(self.supported) is not bool:
            raise ValueError("fixed and supported must be booleans.")
        object.__setattr__(
            self,
            "table_complexity",
            _enum_value(TableComplexity, self.table_complexity, "table_complexity"),
        )

    @property
    def word_count(self) -> int:
        return len(self.text.split())


@dataclass(frozen=True, slots=True)
class PageDescriptor:
    """Minimal normalized signals for one page classification."""

    page_id: str
    page_type: str = "UNKNOWN"
    blocks: tuple[BlockDescriptor, ...] = ()
    assets_count: int = 0
    column_count: int = 1
    fixed_layout: bool = False

    def __post_init__(self) -> None:
        if type(self.page_id) is not str or not self.page_id.strip():
            raise ValueError("page_id must be a non-empty string.")
        if type(self.page_type) is not str or not self.page_type.strip():
            raise ValueError("page_type must be a non-empty string.")
        object.__setattr__(self, "page_type", _enum_text(self.page_type))
        values = tuple(self.blocks)
        if any(type(block) is not BlockDescriptor for block in values):
            raise TypeError("blocks must contain BlockDescriptor values.")
        if len({block.block_id for block in values}) != len(values):
            raise ValueError("page block IDs must be unique.")
        object.__setattr__(self, "blocks", values)
        if type(self.assets_count) is not int or self.assets_count < 0:
            raise ValueError("assets_count must be a non-negative integer.")
        if type(self.column_count) is not int or self.column_count < 1:
            raise ValueError("column_count must be a positive integer.")
        if type(self.fixed_layout) is not bool:
            raise ValueError("fixed_layout must be a boolean.")


@dataclass(frozen=True, slots=True)
class BlockDecision:
    """Auditable, immutable decision for one block."""

    block_id: str
    strategy: BlockStrategy
    evidence: tuple[str, ...]
    confidence: float

    def __post_init__(self) -> None:
        if type(self.block_id) is not str or not self.block_id.strip():
            raise ValueError("block_id must be a non-empty string.")
        if not isinstance(self.strategy, BlockStrategy):
            object.__setattr__(self, "strategy", BlockStrategy(self.strategy))
        _validate_confidence(self.confidence)
        evidence = tuple(self.evidence)
        if any(type(item) is not str or not item.strip() for item in evidence):
            raise ValueError("evidence must contain non-empty strings.")
        object.__setattr__(self, "evidence", evidence)

    @property
    def rationale(self) -> tuple[str, ...]:
        return self.evidence

    def to_dict(self) -> dict[str, object]:
        return {
            "block_id": self.block_id,
            "strategy": self.strategy.value,
            "evidence": list(self.evidence),
            "confidence": self.confidence,
        }


@dataclass(frozen=True, slots=True)
class PageDecision:
    """Auditable, immutable decision for one page and its blocks."""

    page_id: str
    classification: PageClassification
    strategy: PageStrategy
    block_decisions: tuple[BlockDecision, ...]
    evidence: tuple[str, ...]
    confidence: float

    def __post_init__(self) -> None:
        if type(self.page_id) is not str or not self.page_id.strip():
            raise ValueError("page_id must be a non-empty string.")
        if not isinstance(self.classification, PageClassification):
            object.__setattr__(
                self,
                "classification",
                PageClassification(self.classification),
            )
        if not isinstance(self.strategy, PageStrategy):
            object.__setattr__(self, "strategy", PageStrategy(self.strategy))
        blocks = tuple(self.block_decisions)
        if any(type(block) is not BlockDecision for block in blocks):
            raise TypeError("block_decisions must contain BlockDecision values.")
        if len({block.block_id for block in blocks}) != len(blocks):
            raise ValueError("page decision block IDs must be unique.")
        object.__setattr__(self, "block_decisions", blocks)
        _validate_confidence(self.confidence)
        evidence = tuple(self.evidence)
        if any(type(item) is not str or not item.strip() for item in evidence):
            raise ValueError("evidence must contain non-empty strings.")
        object.__setattr__(self, "evidence", evidence)

    @property
    def decision_hash(self) -> str:
        payload = json.dumps(
            self.to_dict(), ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def to_dict(self) -> dict[str, object]:
        return {
            "page_id": self.page_id,
            "classification": self.classification.value,
            "strategy": self.strategy.value,
            "block_decisions": [block.to_dict() for block in self.block_decisions],
            "evidence": list(self.evidence),
            "confidence": self.confidence,
        }


@dataclass(frozen=True, slots=True)
class HybridDecision:
    """Stored decision set for a document, stable across repeated runs."""

    pages: tuple[PageDecision, ...]
    document_id: str | None = None

    def __post_init__(self) -> None:
        pages = tuple(self.pages)
        if any(type(page) is not PageDecision for page in pages):
            raise TypeError("pages must contain PageDecision values.")
        if len({page.page_id for page in pages}) != len(pages):
            raise ValueError("document page IDs must be unique.")
        if self.document_id is not None and (
            type(self.document_id) is not str or not self.document_id.strip()
        ):
            raise ValueError("document_id must be a non-empty string or None.")
        object.__setattr__(self, "pages", pages)

    def __iter__(self) -> Iterator[PageDecision]:
        return iter(self.pages)

    def __len__(self) -> int:
        return len(self.pages)

    @property
    def decision_hash(self) -> str:
        payload = json.dumps(
            self.to_dict(), ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def to_dict(self) -> dict[str, object]:
        return {
            "document_id": self.document_id,
            "pages": [page.to_dict() for page in self.pages],
        }


class HybridStrategyClassifier:
    """Classify pages and blocks using an explicit deterministic rule set."""

    def __init__(
        self,
        *,
        long_paragraph_words: int = 60,
        long_paragraph_characters: int = 360,
        expansion_reflow_ratio: float = 1.20,
        complex_table_strategy: BlockStrategy | str = BlockStrategy.RENDER_AS_IMAGE,
    ) -> None:
        if type(long_paragraph_words) is not int or long_paragraph_words < 1:
            raise ValueError("long_paragraph_words must be a positive integer.")
        if type(long_paragraph_characters) is not int or long_paragraph_characters < 1:
            raise ValueError("long_paragraph_characters must be a positive integer.")
        if (
            isinstance(expansion_reflow_ratio, bool)
            or not isinstance(expansion_reflow_ratio, (int, float))
            or not math.isfinite(float(expansion_reflow_ratio))
            or expansion_reflow_ratio < 1.0
        ):
            raise ValueError("expansion_reflow_ratio must be finite and at least 1.")
        strategy = _enum_value(BlockStrategy, complex_table_strategy, "complex_table_strategy")
        if strategy not in {BlockStrategy.RENDER_AS_IMAGE, BlockStrategy.MANUAL_REVIEW}:
            raise ValueError("complex_table_strategy must render an image or require review.")
        self.long_paragraph_words = long_paragraph_words
        self.long_paragraph_characters = long_paragraph_characters
        self.expansion_reflow_ratio = float(expansion_reflow_ratio)
        self.complex_table_strategy = strategy

    def classify_page(
        self,
        page: object,
        *,
        settings: ReconstructionSettings | None = None,
    ) -> PageDecision:
        descriptor = _normalize_page(page)
        classification, page_evidence, confidence = self._classify_page_shape(descriptor)
        page_strategy = self._page_strategy(classification, settings)
        block_decisions = tuple(
            self.classify_block(block, page_strategy=page_strategy, settings=settings)
            for block in descriptor.blocks
        )
        return PageDecision(
            page_id=descriptor.page_id,
            classification=classification,
            strategy=page_strategy,
            block_decisions=block_decisions,
            evidence=page_evidence,
            confidence=confidence,
        )

    def classify_block(
        self,
        block: BlockDescriptor | object,
        *,
        page_strategy: PageStrategy = PageStrategy.HYBRID,
        settings: ReconstructionSettings | None = None,
    ) -> BlockDecision:
        descriptor = block if isinstance(block, BlockDescriptor) else _normalize_block(block)
        block_type = descriptor.block_type
        if not descriptor.supported or block_type in _UNSUPPORTED_BLOCK_TYPES:
            return _decision(
                descriptor.block_id, BlockStrategy.MANUAL_REVIEW, "unsupported block type", 0.99
            )
        if block_type in {"IMAGE", "FIGURE"}:
            return _decision(
                descriptor.block_id, BlockStrategy.PRESERVE, "image content is preserved", 1.0
            )
        if block_type == "TABLE":
            if descriptor.table_complexity is TableComplexity.COMPLEX:
                complex_strategy = self.complex_table_strategy
                if (
                    settings is not None
                    and settings.table_complexity_fallback is TableComplexityFallback.MANUAL_REVIEW
                ):
                    complex_strategy = BlockStrategy.MANUAL_REVIEW
                return _decision(
                    descriptor.block_id,
                    complex_strategy,
                    "complex table uses the configured image/review fallback",
                    0.98,
                )
            if descriptor.table_complexity is TableComplexity.UNKNOWN:
                return _decision(
                    descriptor.block_id,
                    BlockStrategy.MANUAL_REVIEW,
                    "table complexity is unknown",
                    0.65,
                )
            return _decision(
                descriptor.block_id,
                BlockStrategy.RECONSTRUCT,
                "simple table can be reconstructed deterministically",
                0.96,
            )
        if block_type in {"FORMULA", "EQUATION_LABEL"}:
            return _decision(
                descriptor.block_id, BlockStrategy.PRESERVE, "formula content is protected", 0.98
            )
        if block_type in {"CODE_BLOCK", "INLINE_CODE_CONTAINER"}:
            return _decision(
                descriptor.block_id,
                BlockStrategy.RECONSTRUCT,
                "code structure is reconstructed",
                0.94,
            )
        if descriptor.fixed or block_type in _FIXED_BLOCK_TYPES:
            return _decision(
                descriptor.block_id,
                BlockStrategy.OVERLAY,
                "fixed-position content uses overlay",
                0.98,
            )
        if block_type.startswith("HEADING_"):
            strategy = (
                BlockStrategy.REFLOW
                if page_strategy is PageStrategy.REFLOW
                else BlockStrategy.OVERLAY
            )
            return _decision(
                descriptor.block_id, strategy, "heading keeps semantic hierarchy", 0.88
            )
        if block_type in _BODY_BLOCK_TYPES:
            if self._needs_reflow(descriptor) or page_strategy is PageStrategy.REFLOW:
                return _decision(
                    descriptor.block_id,
                    BlockStrategy.REFLOW,
                    "body content benefits from expansion",
                    0.92,
                )
            return _decision(
                descriptor.block_id,
                BlockStrategy.OVERLAY,
                "short body content fits its source region",
                0.76,
            )
        return _decision(
            descriptor.block_id, BlockStrategy.MANUAL_REVIEW, "block type has no safe default", 0.40
        )

    def classify_document(
        self,
        document: object,
        *,
        settings: ReconstructionSettings | None = None,
    ) -> HybridDecision:
        raw_pages = _read(document, "pages", ())
        if isinstance(raw_pages, (str, bytes, bytearray)) or not isinstance(raw_pages, Sequence):
            raise TypeError("document.pages must be a sequence.")
        document_id = _read(document, "document_id", None)
        if document_id is not None and type(document_id) is not str:
            raise TypeError("document_id must be a string or None.")
        pages = tuple(self.classify_page(page, settings=settings) for page in raw_pages)
        return HybridDecision(pages=pages, document_id=document_id)

    def _classify_page_shape(
        self, page: PageDescriptor
    ) -> tuple[PageClassification, tuple[str, ...], float]:
        page_type = page.page_type
        if page_type == "COVER":
            return PageClassification.COVER, ("page type is COVER",), 1.0
        if page_type in {"FORM", "FIXED_LAYOUT"} or page.fixed_layout:
            reason = "page type is FORM" if page_type == "FORM" else "explicit fixed-layout signal"
            return PageClassification.FIXED_LAYOUT, (reason,), 0.98
        non_image_blocks = tuple(
            block for block in page.blocks if block.block_type not in {"IMAGE", "FIGURE"}
        )
        image_block_count = sum(block.block_type in {"IMAGE", "FIGURE"} for block in page.blocks)
        if (
            page_type == "IMAGE_ONLY"
            or (page.assets_count + image_block_count > 0 and not non_image_blocks)
            or (
                page.assets_count > 0
                and not any(block.block_type in _TEXT_TYPES for block in non_image_blocks)
                and not any(
                    block.block_type in _UNSUPPORTED_BLOCK_TYPES for block in non_image_blocks
                )
            )
        ):
            return (
                PageClassification.IMAGE_ONLY,
                ("page has image content without text blocks",),
                0.97,
            )
        blocks = page.blocks
        if not blocks:
            return PageClassification.UNKNOWN, ("page has no classified blocks",), 0.35
        table_count = sum(block.block_type == "TABLE" for block in blocks)
        code_count = sum(block.block_type == "CODE_BLOCK" for block in blocks)
        formula_count = sum(block.block_type == "FORMULA" for block in blocks)
        fixed_count = sum(block.fixed or block.block_type in _FIXED_BLOCK_TYPES for block in blocks)
        image_count = page.assets_count + image_block_count
        body_blocks = tuple(block for block in blocks if block.block_type in _BODY_BLOCK_TYPES)
        long_body = any(self._needs_reflow(block) for block in body_blocks)
        if table_count and table_count * 2 >= len(blocks):
            return PageClassification.TABLE_HEAVY, ("table blocks dominate the page",), 0.94
        if code_count and code_count * 2 >= len(blocks):
            return PageClassification.CODE_HEAVY, ("code blocks dominate the page",), 0.92
        if formula_count and formula_count * 2 >= len(blocks):
            return PageClassification.FORMULA_HEAVY, ("formula blocks dominate the page",), 0.90
        if image_count and (long_body or fixed_count):
            return (
                PageClassification.MIXED_LAYOUT,
                ("text and preserved image/fixed content coexist",),
                0.88,
            )
        if long_body or (body_blocks and page.column_count <= 2):
            return (
                PageClassification.REFLOW_FRIENDLY,
                ("body prose is suitable for expansion",),
                0.86,
            )
        if fixed_count:
            return (
                PageClassification.FIXED_LAYOUT,
                ("fixed-position blocks dominate the page",),
                0.84,
            )
        if any(block.block_type in _UNSUPPORTED_BLOCK_TYPES for block in blocks):
            return (
                PageClassification.UNKNOWN,
                ("unsupported blocks prevent a safe page default",),
                0.45,
            )
        return PageClassification.UNKNOWN, ("page shape lacks sufficient evidence",), 0.35

    @staticmethod
    def _page_strategy(
        classification: PageClassification,
        settings: ReconstructionSettings | None,
    ) -> PageStrategy:
        if classification in {PageClassification.COVER, PageClassification.FIXED_LAYOUT}:
            return PageStrategy.OVERLAY
        if classification is PageClassification.IMAGE_ONLY:
            return PageStrategy.PRESERVE
        if classification is PageClassification.REFLOW_FRIENDLY:
            return PageStrategy.REFLOW
        if classification in {
            PageClassification.MIXED_LAYOUT,
            PageClassification.TABLE_HEAVY,
            PageClassification.CODE_HEAVY,
            PageClassification.FORMULA_HEAVY,
        }:
            return PageStrategy.HYBRID
        if settings is not None and settings.mode is ReconstructionMode.OVERLAY:
            return PageStrategy.OVERLAY
        return PageStrategy.MANUAL_REVIEW

    def _needs_reflow(self, block: BlockDescriptor) -> bool:
        return (
            (
                block.expansion_ratio is not None
                and block.expansion_ratio >= self.expansion_reflow_ratio
            )
            or block.word_count >= self.long_paragraph_words
            or len(block.text) >= self.long_paragraph_characters
        )


HybridClassifier = HybridStrategyClassifier


def classify_page(
    page: object,
    *,
    settings: ReconstructionSettings | None = None,
    classifier: HybridStrategyClassifier | None = None,
) -> PageDecision:
    """Classify one page with the default deterministic classifier."""

    return (classifier or HybridStrategyClassifier()).classify_page(page, settings=settings)


def classify_block(
    block: object,
    *,
    page_strategy: PageStrategy = PageStrategy.HYBRID,
    settings: ReconstructionSettings | None = None,
    classifier: HybridStrategyClassifier | None = None,
) -> BlockDecision:
    """Classify one block with the default deterministic classifier."""

    return (classifier or HybridStrategyClassifier()).classify_block(
        block,
        page_strategy=page_strategy,
        settings=settings,
    )


def classify_document(
    document: object,
    *,
    settings: ReconstructionSettings | None = None,
    classifier: HybridStrategyClassifier | None = None,
) -> HybridDecision:
    """Classify all pages in a document with stable persisted decisions."""

    return (classifier or HybridStrategyClassifier()).classify_document(document, settings=settings)


def _decision(
    block_id: str,
    strategy: BlockStrategy,
    evidence: str,
    confidence: float,
) -> BlockDecision:
    return BlockDecision(
        block_id=block_id,
        strategy=strategy,
        evidence=(evidence,),
        confidence=confidence,
    )


def _normalize_page(value: object) -> PageDescriptor:
    if isinstance(value, PageDescriptor):
        return value
    raw_blocks = _read(value, "blocks", ())
    if isinstance(raw_blocks, (str, bytes, bytearray)) or not isinstance(raw_blocks, Sequence):
        raise TypeError("page.blocks must be a sequence.")
    raw_tables = _read(value, "tables", ())
    table_by_block: dict[str, object] = {}
    if isinstance(raw_tables, Sequence) and not isinstance(raw_tables, (str, bytes, bytearray)):
        for table in raw_tables:
            table_id = _read(table, "block_id", None)
            if isinstance(table_id, str):
                table_by_block[table_id] = table
    normalized_blocks: list[BlockDescriptor] = []
    for block in raw_blocks:
        block_id = _read(block, "block_id", "")
        table = table_by_block.get(block_id) if isinstance(block_id, str) else None
        normalized_blocks.append(_normalize_block(block, table=table))
    blocks = tuple(normalized_blocks)
    raw_assets = _read(value, "assets", ())
    assets_count = _read(value, "assets_count", None)
    if assets_count is None:
        assets_count = len(raw_assets) if isinstance(raw_assets, Sequence) else 0
    if type(assets_count) is not int:
        raise ValueError("assets_count must be a non-negative integer.")
    column_count = _read(value, "column_count", 1)
    if type(column_count) is not int:
        raise ValueError("column_count must be a positive integer.")
    fixed_layout = _read(value, "fixed_layout", _read(value, "is_fixed", False))
    if type(fixed_layout) is not bool:
        raise ValueError("fixed_layout must be a boolean.")
    return PageDescriptor(
        page_id=_required_text(_read(value, "page_id", None), "page_id"),
        page_type=_enum_text(_read(value, "page_type", "UNKNOWN")),
        blocks=blocks,
        assets_count=assets_count,
        column_count=column_count,
        fixed_layout=fixed_layout,
    )


def _normalize_block(value: object, *, table: object | None = None) -> BlockDescriptor:
    if isinstance(value, BlockDescriptor):
        return value
    block_type = _enum_text(_read(value, "block_type", _read(value, "kind", "UNKNOWN")))
    block_id = _required_text(_read(value, "block_id", None), "block_id")
    text = _block_text(value)
    raw_expansion = _read(value, "expansion_ratio", None)
    if raw_expansion is None:
        expansion: float | None = _geometry_expansion(value)
    elif not _positive_number(raw_expansion) and raw_expansion != 0:
        raise ValueError("expansion_ratio must be a finite non-negative number.")
    else:
        assert isinstance(raw_expansion, (int, float))
        expansion = float(raw_expansion)
    table_value = _read(value, "table_complexity", _read(value, "complexity", None))
    if table_value is None and block_type == "TABLE":
        table_value = _infer_table_complexity(table or _read(value, "table", value))
    if table_value is None:
        table_value = TableComplexity.SIMPLE
    unsupported = _read(value, "unsupported", None)
    supported = _read(value, "supported", None)
    if supported is None:
        supported = not bool(unsupported)
    fixed = _read(value, "fixed", _read(value, "is_fixed", False))
    if type(fixed) is not bool or type(supported) is not bool:
        raise ValueError("fixed and supported must be booleans.")
    return BlockDescriptor(
        block_id=block_id,
        block_type=block_type,
        text=text,
        expansion_ratio=expansion,
        fixed=fixed,
        supported=supported,
        table_complexity=cast(TableComplexity | str, table_value),
    )


def _block_text(value: object) -> str:
    final_text = _read(value, "final_text", None)
    if isinstance(final_text, str):
        return final_text
    segments = _read(value, "segments", ())
    if isinstance(segments, Sequence) and not isinstance(segments, (str, bytes, bytearray)):
        values = [
            _read(segment, "final_text", None) for segment in sorted(segments, key=_segment_order)
        ]
        final_values = [value for value in values if isinstance(value, str)]
        if final_values:
            return "\n".join(final_values)
    text = _read(value, "text", _read(value, "source_text", ""))
    return text if isinstance(text, str) else ""


def _geometry_expansion(value: object) -> float | None:
    source = _read(value, "source_geometry", None)
    target = _read(value, "target_geometry", None)
    source_height = _read(source, "height", None)
    target_height = _read(target, "height", None)
    if not _positive_number(source_height) or not _positive_number(target_height):
        return None
    assert isinstance(source_height, (int, float))
    assert isinstance(target_height, (int, float))
    return float(target_height) / float(source_height)


def _infer_table_complexity(value: object) -> TableComplexity:
    explicit = _read(value, "table_complexity", _read(value, "complexity", None))
    if explicit is not None:
        return _enum_value(TableComplexity, explicit, "table_complexity")
    rows = _read(value, "row_count", None)
    columns = _read(value, "column_count", None)
    raw_rows = _read(value, "rows", None)
    if (
        rows is None
        and isinstance(raw_rows, Sequence)
        and not isinstance(raw_rows, (str, bytes, bytearray))
    ):
        rows = len(raw_rows)
    if columns is None and isinstance(raw_rows, Sequence) and raw_rows:
        first_row = raw_rows[0]
        if isinstance(first_row, Sequence) and not isinstance(first_row, (str, bytes, bytearray)):
            columns = len(first_row)
    if rows is None or columns is None:
        return TableComplexity.SIMPLE
    if type(rows) is not int or type(columns) is not int or rows < 0 or columns < 0:
        return TableComplexity.UNKNOWN
    cells = _read(value, "cells", ())
    merged = False
    if isinstance(cells, Sequence) and not isinstance(cells, (str, bytes, bytearray)):
        merged = any(
            _read(cell, "row_span", 1) != 1 or _read(cell, "column_span", 1) != 1 for cell in cells
        )
    if merged or rows > 30 or columns > 12 or rows * columns > 240:
        return TableComplexity.COMPLEX
    return TableComplexity.SIMPLE


def _read(value: object, name: str, default: object = None) -> object:
    if isinstance(value, Mapping):
        return value.get(name, default)
    return getattr(value, name, default)


def _required_text(value: object, field_name: str) -> str:
    if type(value) is not str or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string.")
    return value


def _enum_text(value: object) -> str:
    raw = getattr(value, "value", value)
    if type(raw) is not str or not raw.strip():
        raise ValueError("enum values must be non-empty strings.")
    return raw.strip().replace("-", "_").replace(" ", "_").upper()


def _enum_value[EnumValue: StrEnum](
    enum_type: type[EnumValue], value: object, field_name: str
) -> EnumValue:
    if isinstance(value, enum_type):
        return value
    try:
        return enum_type(_enum_text(value))
    except (TypeError, ValueError) as exc:
        allowed = ", ".join(member.value for member in enum_type)
        raise ValueError(f"{field_name} must be one of: {allowed}.") from exc


def _positive_number(value: object) -> bool:
    return (
        not isinstance(value, bool)
        and isinstance(value, (int, float))
        and math.isfinite(float(value))
        and float(value) > 0
    )


def _segment_order(value: object) -> int:
    order = _read(value, "segment_order", 0)
    return order if type(order) is int else 0


def _validate_confidence(value: object) -> None:
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not math.isfinite(float(value))
        or not 0.0 <= float(value) <= 1.0
    ):
        raise ValueError("confidence must be a finite number between 0 and 1.")
