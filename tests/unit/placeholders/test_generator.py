import re
from typing import Any, cast

import pytest
from transloka_core.database.models.glossary import ProtectedItemType
from transloka_glossary.placeholders.generator import (
    InvalidPlaceholderError,
    PlaceholderGenerator,
)

PLACEHOLDER_PATTERN = re.compile(r"__TLK_[A-Z_]+_[0-9]{4,}_[0-9A-F]{2}__")


def test_placeholders_are_unique_and_use_the_required_format() -> None:
    generator = PlaceholderGenerator("A source document")

    entries = [
        generator.generate(item_type, f"value-{index}")
        for index, item_type in enumerate(ProtectedItemType, start=1)
    ]

    assert len({entry.placeholder for entry in entries}) == len(ProtectedItemType)
    assert all(PLACEHOLDER_PATTERN.fullmatch(entry.placeholder) for entry in entries)
    assert [entry.number for entry in entries] == list(range(1, len(entries) + 1))


def test_natural_source_collision_uses_a_different_placeholder() -> None:
    initial = PlaceholderGenerator("").generate(ProtectedItemType.TERM, "framework")
    source = f"The document naturally contains {initial.placeholder}."

    replacement = PlaceholderGenerator(source).generate(
        ProtectedItemType.TERM,
        "framework",
    )

    assert replacement.placeholder != initial.placeholder
    assert replacement.placeholder not in source
    assert replacement.number == initial.number


def test_all_checksum_collisions_advance_to_the_next_number() -> None:
    collisions = " ".join(f"__TLK_TERM_0001_{checksum:02X}__" for checksum in range(256))

    entry = PlaceholderGenerator(collisions).generate(
        ProtectedItemType.TERM,
        "framework",
    )

    assert entry.number == 2
    assert entry.placeholder not in collisions


def test_repeated_source_values_receive_unique_restorable_entries() -> None:
    generator = PlaceholderGenerator("framework appears twice: framework")

    first = generator.generate(ProtectedItemType.TERM, "framework")
    second = generator.generate(ProtectedItemType.TERM, "framework")

    assert first.placeholder != second.placeholder
    assert generator.inventory == (first, second)
    assert generator.restoration_map == {
        first.placeholder: "framework",
        second.placeholder: "framework",
    }


def test_same_request_inputs_produce_a_stable_inventory() -> None:
    def build_inventory() -> tuple[str, ...]:
        generator = PlaceholderGenerator("Use https://example.test and API.")
        generator.generate(ProtectedItemType.URL, "https://example.test")
        generator.generate(ProtectedItemType.ACRONYM, "API")
        return tuple(entry.placeholder for entry in generator.inventory)

    assert build_inventory() == build_inventory()


@pytest.mark.parametrize("invalid_type", ["TERM", "FORMULA", None, 1])
def test_invalid_types_are_rejected(invalid_type: object) -> None:
    with pytest.raises(InvalidPlaceholderError):
        PlaceholderGenerator("source").generate(
            cast(Any, invalid_type),
            "value",
        )


@pytest.mark.parametrize("source_value", ["", None, 1])
def test_invalid_source_values_are_rejected(source_value: object) -> None:
    with pytest.raises(InvalidPlaceholderError):
        PlaceholderGenerator("source").generate(
            ProtectedItemType.TERM,
            cast(Any, source_value),
        )


def test_unicode_source_and_values_are_preserved_exactly() -> None:
    value = "Straße_日本語_é"
    generator = PlaceholderGenerator(f"Dokumen panjang: {value}")

    entry = generator.generate(ProtectedItemType.TERM, value)

    assert entry.source_value == value
    assert generator.restoration_map[entry.placeholder] == value
    assert entry.placeholder.isascii()


def test_long_document_and_more_than_four_digit_inventory_remain_supported() -> None:
    source = "Dokumen panjang 日本語. " * 50_000
    generator = PlaceholderGenerator(source)

    entries = [
        generator.generate(ProtectedItemType.TERM, f"term-{number}") for number in range(1, 10_002)
    ]

    assert len({entry.placeholder for entry in entries}) == 10_001
    assert entries[-2].number == 10_000
    assert "_10000_" in entries[-2].placeholder
    assert entries[-1].number == 10_001
