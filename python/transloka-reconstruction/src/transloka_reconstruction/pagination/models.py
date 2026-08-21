"""Immutable source-to-target page mapping values for reconstruction.

The reconstruction engine can preserve a page, split one source page across
several output pages, or merge source pages into one output page.  These values
keep that relationship deterministic and expose the small export/link-update
surface needed by later assembly tasks.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum
from typing import cast


class PageMappingError(ValueError):
    """Raised when source/target page mapping data is inconsistent."""


class PageMappingType(StrEnum):
    """Supported source-to-target cardinalities from the Document IR."""

    ONE_TO_ONE = "ONE_TO_ONE"
    ONE_TO_MANY = "ONE_TO_MANY"
    MANY_TO_ONE = "MANY_TO_ONE"
    UNMAPPED = "UNMAPPED"


TargetPageMappingType = PageMappingType


def _text(value: object, field_name: str) -> str:
    if type(value) is not str or not value.strip():
        raise PageMappingError(f"{field_name} must be a non-empty string.")
    return value


def _positive_int(value: object, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise PageMappingError(f"{field_name} must be a positive integer.")
    return value


def _non_negative_int(value: object, field_name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise PageMappingError(f"{field_name} must be a non-negative integer.")
    return value


def _coerce_mapping_type(value: PageMappingType | str) -> PageMappingType:
    if isinstance(value, PageMappingType):
        return value
    if type(value) is not str:
        raise PageMappingError("mapping_type must be a known page mapping type.")
    try:
        return PageMappingType(value)
    except ValueError as exc:
        raise PageMappingError("mapping_type must be a known page mapping type.") from exc


def _coerce_ids(values: Iterable[object], field_name: str) -> tuple[str, ...]:
    if type(values) is str:
        values = (values,)
    normalized = tuple(_text(value, field_name) for value in values)
    if len(set(normalized)) != len(normalized):
        raise PageMappingError(f"{field_name} must not contain duplicate page IDs.")
    return normalized


@dataclass(frozen=True, slots=True)
class SourcePageRef:
    """A source page and its physical number in the input PDF."""

    page_id: str
    source_page_number: int

    def __post_init__(self) -> None:
        object.__setattr__(self, "page_id", _text(self.page_id, "page_id"))
        object.__setattr__(
            self,
            "source_page_number",
            _positive_int(self.source_page_number, "source_page_number"),
        )

    @property
    def number(self) -> int:
        """Short alias used by page assembly callers."""

        return self.source_page_number


SourcePage = SourcePageRef


@dataclass(frozen=True, slots=True)
class TargetPageRef:
    """An output page with its final physical number."""

    page_id: str
    target_page_number: int
    added: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "page_id", _text(self.page_id, "page_id"))
        object.__setattr__(
            self,
            "target_page_number",
            _positive_int(self.target_page_number, "target_page_number"),
        )
        if type(self.added) is not bool:
            raise PageMappingError("added must be a boolean.")

    @property
    def number(self) -> int:
        """Short alias used by page assembly callers."""

        return self.target_page_number

    @property
    def is_added(self) -> bool:
        return self.added


TargetPage = TargetPageRef


@dataclass(frozen=True, slots=True)
class PageFragment:
    """One ordered fragment of a source page placed on a target page."""

    source_page_id: str
    target_page_id: str
    fragment_order: int = 1
    segment_id: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "source_page_id", _text(self.source_page_id, "source_page_id"))
        object.__setattr__(self, "target_page_id", _text(self.target_page_id, "target_page_id"))
        object.__setattr__(
            self,
            "fragment_order",
            _positive_int(self.fragment_order, "fragment_order"),
        )
        if self.segment_id is not None:
            object.__setattr__(self, "segment_id", _text(self.segment_id, "segment_id"))


TargetPageFragment = PageFragment


@dataclass(frozen=True, slots=True, init=False)
class PageMapping:
    """A relationship between one or more source and output pages.

    A single mapping record is enough for a split paragraph (one source page
    and several targets) and for a merge (several sources and one target).
    ``mapping_type`` is inferred from the cardinality unless explicitly given.
    """

    source_page_ids: tuple[str, ...]
    target_page_ids: tuple[str, ...]
    mapping_type: PageMappingType | str | None = None
    fragments: tuple[PageFragment, ...] = ()

    def __init__(
        self,
        source_page_ids: Iterable[object] | None = None,
        target_page_ids: Iterable[object] = (),
        mapping_type: PageMappingType | str | None = None,
        fragments: Iterable[PageFragment] = (),
        *,
        source_page_id: str | None = None,
    ) -> None:
        """Create a mapping using plural IDs or the Document IR singular alias."""

        if source_page_ids is not None and source_page_id is not None:
            raise PageMappingError("provide source_page_ids or source_page_id, not both.")
        source_values: Iterable[object]
        if source_page_id is not None:
            source_values = (source_page_id,)
        else:
            source_values = source_page_ids or ()
        object.__setattr__(
            self,
            "source_page_ids",
            (source_values,) if type(source_values) is str else tuple(source_values),
        )
        object.__setattr__(
            self,
            "target_page_ids",
            tuple(target_page_ids) if type(target_page_ids) is not str else (target_page_ids,),
        )
        object.__setattr__(self, "mapping_type", mapping_type)
        object.__setattr__(self, "fragments", tuple(fragments))
        self.__post_init__()

    def __post_init__(self) -> None:
        source_ids = _coerce_ids(self.source_page_ids, "source_page_ids")
        target_ids = _coerce_ids(self.target_page_ids, "target_page_ids")
        object.__setattr__(self, "source_page_ids", source_ids)
        object.__setattr__(self, "target_page_ids", target_ids)

        if not source_ids and target_ids:
            raise PageMappingError(
                "A mapping with no source page must be represented as an added page."
            )
        inferred = _infer_mapping_type(len(source_ids), len(target_ids))
        if self.mapping_type is None:
            normalized_type = inferred
        else:
            normalized_type = _coerce_mapping_type(self.mapping_type)
            if normalized_type is not PageMappingType.UNMAPPED and normalized_type is not inferred:
                raise PageMappingError(
                    "mapping_type does not match source_page_ids/target_page_ids cardinality."
                )
            if normalized_type is PageMappingType.UNMAPPED and target_ids:
                raise PageMappingError("UNMAPPED mappings cannot contain target pages.")
        if normalized_type is PageMappingType.UNMAPPED and source_ids:
            pass
        elif not source_ids or not target_ids:
            raise PageMappingError("A mapped relationship must contain source and target pages.")
        object.__setattr__(self, "mapping_type", normalized_type)

        fragments = tuple(self.fragments)
        if any(type(fragment) is not PageFragment for fragment in fragments):
            raise PageMappingError("fragments must contain PageFragment values.")
        if fragments:
            expected_sources = set(source_ids)
            expected_targets = set(target_ids)
            if any(
                fragment.source_page_id not in expected_sources
                or fragment.target_page_id not in expected_targets
                for fragment in fragments
            ):
                raise PageMappingError("fragments must refer to pages in this mapping.")
            orders = [fragment.fragment_order for fragment in fragments]
            if len(set(orders)) != len(orders):
                raise PageMappingError("fragment_order must be unique within a mapping.")
            if set(orders) != set(range(1, len(orders) + 1)):
                raise PageMappingError("fragment_order must start at 1 and be contiguous.")
        object.__setattr__(self, "fragments", fragments)

    @property
    def source_page_id(self) -> str | None:
        """Return the source ID for one-source mappings."""

        return self.source_page_ids[0] if len(self.source_page_ids) == 1 else None

    @property
    def target_page_id(self) -> str | None:
        """Return the target ID for one-target mappings."""

        return self.target_page_ids[0] if len(self.target_page_ids) == 1 else None

    @property
    def is_unmapped(self) -> bool:
        return self.mapping_type is PageMappingType.UNMAPPED

    @property
    def is_split(self) -> bool:
        return self.mapping_type is PageMappingType.ONE_TO_MANY

    @property
    def is_merged(self) -> bool:
        return self.mapping_type is PageMappingType.MANY_TO_ONE

    def to_dict(self) -> dict[str, object]:
        """Serialize the relationship in the Document IR naming style."""

        return {
            "source_page_id": self.source_page_id,
            "source_page_ids": list(self.source_page_ids),
            "target_page_ids": list(self.target_page_ids),
            "mapping_type": cast(PageMappingType, self.mapping_type).value,
            "fragments": [
                {
                    "source_page_id": fragment.source_page_id,
                    "target_page_id": fragment.target_page_id,
                    "fragment_order": fragment.fragment_order,
                    **({"segment_id": fragment.segment_id} if fragment.segment_id else {}),
                }
                for fragment in self.fragments
            ],
        }


TargetPageMapping = PageMapping


@dataclass(frozen=True, slots=True)
class PageExportRecord:
    """One source/target pair ready for export or internal-link updates."""

    source_page_id: str | None
    target_page_id: str
    source_page_number: int | None
    target_page_number: int
    mapping_type: PageMappingType
    mapping_order: int
    added: bool

    def __post_init__(self) -> None:
        if self.source_page_id is not None:
            object.__setattr__(self, "source_page_id", _text(self.source_page_id, "source_page_id"))
        object.__setattr__(self, "target_page_id", _text(self.target_page_id, "target_page_id"))
        if self.source_page_number is not None:
            object.__setattr__(
                self,
                "source_page_number",
                _positive_int(self.source_page_number, "source_page_number"),
            )
        object.__setattr__(
            self,
            "target_page_number",
            _positive_int(self.target_page_number, "target_page_number"),
        )
        object.__setattr__(self, "mapping_type", _coerce_mapping_type(self.mapping_type))
        object.__setattr__(
            self, "mapping_order", _non_negative_int(self.mapping_order, "mapping_order")
        )
        if type(self.added) is not bool:
            raise PageMappingError("added must be a boolean.")

    def to_dict(self) -> dict[str, object]:
        return {
            "source_page_id": self.source_page_id,
            "target_page_id": self.target_page_id,
            "source_page_number": self.source_page_number,
            "target_page_number": self.target_page_number,
            "mapping_type": self.mapping_type.value,
            "mapping_order": self.mapping_order,
            "added": self.added,
        }


def _infer_mapping_type(source_count: int, target_count: int) -> PageMappingType:
    if source_count == 0 or target_count == 0:
        return PageMappingType.UNMAPPED
    if source_count == 1 and target_count == 1:
        return PageMappingType.ONE_TO_ONE
    if source_count == 1:
        return PageMappingType.ONE_TO_MANY
    if target_count == 1:
        return PageMappingType.MANY_TO_ONE
    raise PageMappingError(
        "Many-to-many page mappings are outside the supported reconstruction contract."
    )


def _source_from_value(value: object, number: int) -> SourcePageRef:
    if isinstance(value, SourcePageRef):
        return value
    if type(value) is str:
        return SourcePageRef(value, number)
    if isinstance(value, Mapping):
        page_id = value.get("page_id", value.get("source_page_id"))
        page_number = value.get("source_page_number", value.get("number", number))
        return SourcePageRef(cast(str, page_id), cast(int, page_number))
    raise PageMappingError("source_pages must contain IDs, SourcePageRef values, or mappings.")


def _target_from_value(value: object, number: int, *, inferred_added: bool) -> TargetPageRef:
    if isinstance(value, TargetPageRef):
        return value
    if type(value) is str:
        return TargetPageRef(value, number, added=inferred_added)
    if isinstance(value, Mapping):
        page_id = value.get("page_id", value.get("target_page_id"))
        page_number = value.get("target_page_number", value.get("number", number))
        added = value.get("added", inferred_added)
        return TargetPageRef(cast(str, page_id), cast(int, page_number), cast(bool, added))
    raise PageMappingError("target_pages must contain IDs, TargetPageRef values, or mappings.")


def _normalize_source_pages(values: Iterable[object]) -> tuple[SourcePageRef, ...]:
    pages = tuple(_source_from_value(value, index) for index, value in enumerate(values, start=1))
    if len({page.page_id for page in pages}) != len(pages):
        raise PageMappingError("source page IDs must be unique.")
    if len({page.source_page_number for page in pages}) != len(pages):
        raise PageMappingError("source page numbers must be unique.")
    return pages


def _normalize_target_pages(
    values: Iterable[object], *, source_count: int
) -> tuple[TargetPageRef, ...]:
    pages = tuple(
        _target_from_value(value, index, inferred_added=index > source_count)
        for index, value in enumerate(values, start=1)
    )
    if len({page.page_id for page in pages}) != len(pages):
        raise PageMappingError("target page IDs must be unique.")
    numbers = {page.target_page_number for page in pages}
    expected = set(range(1, len(pages) + 1))
    if numbers != expected:
        raise PageMappingError("target_page_number values must be contiguous and start at 1.")
    return pages


@dataclass(frozen=True, slots=True)
class PageMappingDocument:
    """Validated page map consumed by export and internal-link update steps."""

    source_pages: tuple[SourcePageRef, ...]
    target_pages: tuple[TargetPageRef, ...]
    mappings: tuple[PageMapping, ...]

    def __post_init__(self) -> None:
        sources = tuple(sorted(self.source_pages, key=lambda page: page.source_page_number))
        targets = tuple(sorted(self.target_pages, key=lambda page: page.target_page_number))
        mappings = tuple(self.mappings)
        if any(type(page) is not SourcePageRef for page in sources):
            raise PageMappingError("source_pages must contain SourcePageRef values.")
        if any(type(page) is not TargetPageRef for page in targets):
            raise PageMappingError("target_pages must contain TargetPageRef values.")
        if any(type(mapping) is not PageMapping for mapping in mappings):
            raise PageMappingError("mappings must contain PageMapping values.")
        if len({page.page_id for page in sources}) != len(sources):
            raise PageMappingError("source page IDs must be unique.")
        if len({page.page_id for page in targets}) != len(targets):
            raise PageMappingError("target page IDs must be unique.")
        target_numbers = {page.target_page_number for page in targets}
        if target_numbers != set(range(1, len(targets) + 1)):
            raise PageMappingError("target_page_number values must be contiguous and start at 1.")
        source_ids = {page.page_id for page in sources}
        target_ids = {page.page_id for page in targets}
        mapped_sources: set[str] = set()
        mapped_targets: set[str] = set()
        for mapping in mappings:
            if not set(mapping.source_page_ids) <= source_ids:
                raise PageMappingError("mapping references an unknown source page.")
            if not set(mapping.target_page_ids) <= target_ids:
                raise PageMappingError("mapping references an unknown target page.")
            if mapped_sources.intersection(mapping.source_page_ids):
                raise PageMappingError("a source page may occur in only one mapping record.")
            if mapped_targets.intersection(mapping.target_page_ids):
                raise PageMappingError("a target page may occur in only one mapping record.")
            mapped_sources.update(mapping.source_page_ids)
            mapped_targets.update(mapping.target_page_ids)
        unmapped_sources = source_ids - mapped_sources
        if unmapped_sources:
            raise PageMappingError(
                "every source page must be mapped or represented by an UNMAPPED record."
            )
        unclaimed_targets = target_ids - mapped_targets
        if any(not target.added for target in targets if target.page_id in unclaimed_targets):
            raise PageMappingError("unmapped target pages must be marked added=True.")
        object.__setattr__(self, "source_pages", sources)
        object.__setattr__(self, "target_pages", targets)
        object.__setattr__(self, "mappings", mappings)

    @property
    def source_page_count(self) -> int:
        return len(self.source_pages)

    @property
    def target_page_count(self) -> int:
        return len(self.target_pages)

    @property
    def page_count(self) -> int:
        return self.target_page_count

    @property
    def page_count_changed(self) -> bool:
        return self.source_page_count != self.target_page_count

    @property
    def added_pages(self) -> tuple[TargetPageRef, ...]:
        return tuple(page for page in self.target_pages if page.added)

    @property
    def unmapped_source_page_ids(self) -> tuple[str, ...]:
        return tuple(
            page.page_id
            for page in self.source_pages
            if any(
                page.page_id in mapping.source_page_ids and mapping.is_unmapped
                for mapping in self.mappings
            )
        )

    def mapping_for_source_page(self, page_id: str) -> PageMapping | None:
        """Return the mapping record for one source page, if present."""

        page_id = _text(page_id, "page_id")
        matches = tuple(mapping for mapping in self.mappings if page_id in mapping.source_page_ids)
        return matches[0] if matches else None

    def target_pages_for_source_page(self, page_id: str) -> tuple[TargetPageRef, ...]:
        mapping = self.mapping_for_source_page(page_id)
        if mapping is None:
            return ()
        target_by_id = {page.page_id: page for page in self.target_pages}
        return tuple(target_by_id[target_id] for target_id in mapping.target_page_ids)

    def target_page_ids_for_source(self, page_id: str) -> tuple[str, ...]:
        """Return all output page IDs for an internal-link update."""

        return tuple(page.page_id for page in self.target_pages_for_source_page(page_id))

    def source_pages_for_target_page(self, page_id: str) -> tuple[SourcePageRef, ...]:
        page_id = _text(page_id, "page_id")
        mapping = next(
            (mapping for mapping in self.mappings if page_id in mapping.target_page_ids), None
        )
        if mapping is None:
            return ()
        source_by_id = {page.page_id: page for page in self.source_pages}
        return tuple(source_by_id[source_id] for source_id in mapping.source_page_ids)

    def target_page_number_for_source(self, page_id: str) -> int | None:
        pages = self.target_pages_for_source_page(page_id)
        return pages[0].target_page_number if pages else None

    def link_update_map(self) -> dict[str, tuple[str, ...]]:
        """Return source page IDs and all target IDs needed for link updates."""

        return {
            page.page_id: tuple(
                target.page_id for target in self.target_pages_for_source_page(page.page_id)
            )
            for page in self.source_pages
        }

    def export_records(self) -> tuple[PageExportRecord, ...]:
        """Flatten mappings into deterministic source/target export records."""

        source_by_id = {page.page_id: page for page in self.source_pages}
        target_by_id = {page.page_id: page for page in self.target_pages}
        records: list[PageExportRecord] = []
        for mapping in self.mappings:
            for source_id in mapping.source_page_ids or (None,):
                source_number = source_by_id[source_id].source_page_number if source_id else None
                for order, target_id in enumerate(mapping.target_page_ids):
                    target = target_by_id[target_id]
                    records.append(
                        PageExportRecord(
                            source_page_id=source_id,
                            target_page_id=target.page_id,
                            source_page_number=source_number,
                            target_page_number=target.target_page_number,
                            mapping_type=cast(PageMappingType, mapping.mapping_type),
                            mapping_order=order,
                            added=target.added,
                        )
                    )
        mapped_target_ids = {record.target_page_id for record in records}
        for target in self.target_pages:
            if target.page_id not in mapped_target_ids:
                records.append(
                    PageExportRecord(
                        source_page_id=None,
                        target_page_id=target.page_id,
                        source_page_number=None,
                        target_page_number=target.target_page_number,
                        mapping_type=PageMappingType.UNMAPPED,
                        mapping_order=0,
                        added=target.added,
                    )
                )
        return tuple(sorted(records, key=lambda record: record.target_page_number))

    def to_dict(self) -> dict[str, object]:
        return {
            "source_pages": [
                {"page_id": page.page_id, "source_page_number": page.source_page_number}
                for page in self.source_pages
            ],
            "target_pages": [
                {
                    "page_id": page.page_id,
                    "target_page_number": page.target_page_number,
                    "added": page.added,
                }
                for page in self.target_pages
            ],
            "mappings": [mapping.to_dict() for mapping in self.mappings],
        }


PageMappingResult = PageMappingDocument


def normalize_mapping_records(value: object) -> tuple[PageMapping, ...]:
    """Normalize mapping records supplied as objects or a source-to-target dict."""

    if value is None:
        return ()
    if isinstance(value, PageMapping):
        return (value,)
    if isinstance(value, Mapping):
        records_list: list[PageMapping] = []
        for raw_sources, raw_targets in value.items():
            source_ids = (raw_sources,) if type(raw_sources) is str else tuple(raw_sources)
            target_ids = (raw_targets,) if type(raw_targets) is str else tuple(raw_targets)
            records_list.append(PageMapping(source_ids, target_ids))
        return tuple(records_list)
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        records = tuple(value)
        if any(type(record) is not PageMapping for record in records):
            raise PageMappingError("mappings must contain PageMapping values.")
        return cast(tuple[PageMapping, ...], records)
    raise PageMappingError("mappings must be PageMapping values, a mapping, or a sequence.")
