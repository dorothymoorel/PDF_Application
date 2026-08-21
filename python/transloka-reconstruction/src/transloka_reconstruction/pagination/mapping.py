"""Build deterministic source-to-target page mappings."""

from __future__ import annotations

from collections.abc import Iterable

from .models import (
    PageMapping,
    PageMappingDocument,
    PageMappingType,
    SourcePageRef,
    TargetPageRef,
    _normalize_source_pages,
    _normalize_target_pages,
    normalize_mapping_records,
)


class PageMappingBuilder:
    """Construct and validate mappings used by export and link updates."""

    def build(
        self,
        source_pages: Iterable[object],
        target_pages: Iterable[object],
        mappings: object = None,
    ) -> PageMappingDocument:
        sources = _normalize_source_pages(source_pages)
        targets = _normalize_target_pages(target_pages, source_count=len(sources))
        records = normalize_mapping_records(mappings)
        if not records:
            records = _infer_records(sources, targets)
        return PageMappingDocument(sources, targets, records)

    __call__ = build
    map = build


PageMapper = PageMappingBuilder
TargetPageMapper = PageMappingBuilder


def _infer_records(
    sources: tuple[SourcePageRef, ...], targets: tuple[TargetPageRef, ...]
) -> tuple[PageMapping, ...]:
    """Infer only unambiguous sequential relationships for simple callers."""

    if not sources:
        return ()
    if not targets:
        return (PageMapping(tuple(page.page_id for page in sources), (), PageMappingType.UNMAPPED),)
    source_ids = tuple(page.page_id for page in sources)
    target_ids = tuple(page.page_id for page in targets)
    if len(sources) == len(targets):
        return tuple(
            PageMapping((source_id,), (target_id,))
            for source_id, target_id in zip(source_ids, target_ids, strict=True)
        )
    if len(sources) == 1:
        return (PageMapping(source_ids, target_ids),)
    if len(targets) == 1:
        return (PageMapping(source_ids, target_ids),)

    # When counts differ and neither side has cardinality one, pair the shared
    # prefix and leave extra output pages explicitly marked ``added``.  This is
    # deterministic and keeps callers from silently losing a source page.
    records = tuple(
        PageMapping((source_id,), (target_id,))
        for source_id, target_id in zip(source_ids, target_ids, strict=False)
    )
    if len(sources) > len(targets):
        # The final target absorbs any remaining source pages.
        records = records[:-1] + (
            PageMapping(
                (sources[len(targets) - 1].page_id, *source_ids[len(targets) :]),
                (targets[-1].page_id,),
            ),
        )
    return records


def build_page_mapping(
    source_pages: Iterable[object],
    target_pages: Iterable[object],
    mappings: object = None,
) -> PageMappingDocument:
    """Build and validate a source-to-target page map."""

    return PageMappingBuilder().build(source_pages, target_pages, mappings)


create_page_mapping = build_page_mapping
map_pages = build_page_mapping
map_source_to_target_pages = build_page_mapping
build_target_page_mapping = build_page_mapping


__all__ = [
    "PageMapper",
    "PageMappingBuilder",
    "TargetPageMapper",
    "build_page_mapping",
    "build_target_page_mapping",
    "create_page_mapping",
    "map_pages",
    "map_source_to_target_pages",
]
