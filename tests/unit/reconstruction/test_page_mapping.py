from __future__ import annotations

import pytest
from transloka_reconstruction.pagination import (
    PageFragment,
    PageMapping,
    PageMappingError,
    PageMappingType,
    SourcePageRef,
    TargetPageRef,
    build_page_mapping,
)


def test_no_change_builds_one_to_one_mapping_with_target_numbers() -> None:
    result = build_page_mapping(
        ["source-1", "source-2"],
        ["target-1", "target-2"],
    )

    assert result.source_page_count == 2
    assert result.target_page_count == 2
    assert not result.page_count_changed
    assert result.added_pages == ()
    assert [mapping.mapping_type for mapping in result.mappings] == [
        PageMappingType.ONE_TO_ONE,
        PageMappingType.ONE_TO_ONE,
    ]
    assert [page.target_page_number for page in result.target_pages] == [1, 2]
    assert result.target_page_number_for_source("source-2") == 2
    assert result.link_update_map() == {
        "source-1": ("target-1",),
        "source-2": ("target-2",),
    }

    records = result.export_records()
    assert [(record.source_page_id, record.target_page_number) for record in records] == [
        ("source-1", 1),
        ("source-2", 2),
    ]


def test_document_ir_singular_source_page_alias_is_supported() -> None:
    mapping = PageMapping(source_page_id="source-1", target_page_ids=("target-1",))

    assert mapping.source_page_id == "source-1"
    assert mapping.source_page_ids == ("source-1",)
    assert mapping.mapping_type is PageMappingType.ONE_TO_ONE


def test_added_page_and_split_paragraph_preserve_fragment_order() -> None:
    mapping = PageMapping(
        ("source-1",),
        ("target-1", "target-2"),
        fragments=(
            PageFragment("source-1", "target-1", fragment_order=1, segment_id="segment-a"),
            PageFragment("source-1", "target-2", fragment_order=2, segment_id="segment-a"),
        ),
    )
    result = build_page_mapping(
        [SourcePageRef("source-1", 1)],
        [
            TargetPageRef("target-1", 1),
            TargetPageRef("target-2", 2, added=True),
        ],
        [mapping],
    )

    assert result.page_count_changed
    assert [page.page_id for page in result.added_pages] == ["target-2"]
    assert result.mappings[0].mapping_type is PageMappingType.ONE_TO_MANY
    assert [fragment.fragment_order for fragment in result.mappings[0].fragments] == [1, 2]
    assert result.link_update_map()["source-1"] == ("target-1", "target-2")
    assert [record.target_page_number for record in result.export_records()] == [1, 2]


def test_multiple_source_pages_can_merge_into_one_target() -> None:
    result = build_page_mapping(
        [SourcePageRef("source-1", 1), SourcePageRef("source-2", 2)],
        [TargetPageRef("target-1", 1)],
        [PageMapping(("source-1", "source-2"), ("target-1",))],
    )

    assert result.mappings[0].mapping_type is PageMappingType.MANY_TO_ONE
    assert result.target_pages_for_source_page("source-2")[0].page_id == "target-1"
    assert [page.page_id for page in result.source_pages_for_target_page("target-1")] == [
        "source-1",
        "source-2",
    ]
    assert result.link_update_map() == {
        "source-1": ("target-1",),
        "source-2": ("target-1",),
    }
    assert [
        (record.source_page_id, record.target_page_id) for record in result.export_records()
    ] == [
        ("source-1", "target-1"),
        ("source-2", "target-1"),
    ]


def test_unmapped_source_is_exportable_without_inventing_target_page() -> None:
    result = build_page_mapping(
        [SourcePageRef("source-1", 1)],
        [],
        [PageMapping(("source-1",), (), PageMappingType.UNMAPPED)],
    )

    assert result.unmapped_source_page_ids == ("source-1",)
    assert result.target_pages_for_source_page("source-1") == ()
    assert result.export_records() == ()


def test_unclaimed_target_must_be_explicitly_marked_as_added() -> None:
    with pytest.raises(PageMappingError, match="marked added"):
        build_page_mapping(
            [SourcePageRef("source-1", 1)],
            [TargetPageRef("target-1", 1), TargetPageRef("target-2", 2)],
            [PageMapping(("source-1",), ("target-1",))],
        )


def test_target_numbers_must_be_contiguous() -> None:
    with pytest.raises(PageMappingError, match="contiguous"):
        build_page_mapping(
            [SourcePageRef("source-1", 1)],
            [TargetPageRef("target-1", 2)],
        )
