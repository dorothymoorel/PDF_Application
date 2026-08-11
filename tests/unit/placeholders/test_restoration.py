from dataclasses import replace

import pytest
from transloka_core.database.models.glossary import ProtectedItemType
from transloka_glossary.placeholders.generator import PlaceholderEntry, PlaceholderGenerator
from transloka_glossary.placeholders.restoration import (
    InvalidPlaceholderInventoryError,
    PlaceholderIntegrityError,
    PlaceholderIssueCode,
    PlaceholderRestorer,
)
from transloka_glossary.protection import ProtectedContentDetector


def _inventory() -> tuple[PlaceholderEntry, ...]:
    generator = PlaceholderGenerator("framework and https://example.test")
    generator.generate(ProtectedItemType.TERM, "framework")
    generator.generate(ProtectedItemType.URL, "https://example.test")
    return generator.inventory


def _codes(error: PlaceholderIntegrityError) -> set[PlaceholderIssueCode]:
    return {issue.code for issue in error.issues}


def test_successful_restore_preserves_surrounding_punctuation() -> None:
    inventory = _inventory()
    first, second = inventory
    translated = f"Gunakan ({first.placeholder}), lalu buka {second.placeholder}."

    restored = PlaceholderRestorer().restore(translated, inventory)

    assert restored == "Gunakan (framework), lalu buka https://example.test."


def test_restores_inventory_created_by_protection_pipeline() -> None:
    source = "Open https://example.test and preserve PDF."
    protected = ProtectedContentDetector().protect(source)

    restored = PlaceholderRestorer().restore(protected.text, protected.inventory)

    assert restored == source


def test_missing_placeholder_is_a_critical_failure() -> None:
    inventory = _inventory()
    translated = f"Hanya {inventory[0].placeholder} yang tersisa."

    with pytest.raises(PlaceholderIntegrityError) as captured:
        PlaceholderRestorer().restore(translated, inventory)

    assert captured.value.critical is True
    assert PlaceholderIssueCode.MISSING in _codes(captured.value)
    assert "framework" not in translated


def test_duplicate_placeholder_is_rejected_without_partial_restore() -> None:
    inventory = _inventory()
    first, second = inventory
    translated = f"{first.placeholder} {first.placeholder} {second.placeholder}"

    with pytest.raises(PlaceholderIntegrityError) as captured:
        PlaceholderRestorer().restore(translated, inventory)

    assert PlaceholderIssueCode.DUPLICATED in _codes(captured.value)
    assert first.placeholder in translated


def test_unknown_placeholder_is_rejected() -> None:
    inventory = _inventory()
    first, second = inventory
    unknown = "__TLK_TERM_9999_AA__"
    translated = f"{first.placeholder} {unknown} {second.placeholder}"

    with pytest.raises(PlaceholderIntegrityError) as captured:
        PlaceholderRestorer().restore(translated, inventory)

    assert PlaceholderIssueCode.UNKNOWN in _codes(captured.value)


def test_malformed_and_altered_placeholder_are_rejected() -> None:
    inventory = _inventory()
    first, second = inventory
    malformed = f"__TLK_TERM_{first.number:04d}_A__"
    translated = f"{malformed} {second.placeholder}"

    with pytest.raises(PlaceholderIntegrityError) as captured:
        PlaceholderRestorer().restore(translated, inventory)

    assert {
        PlaceholderIssueCode.MISSING,
        PlaceholderIssueCode.MALFORMED,
        PlaceholderIssueCode.ALTERED,
    } <= _codes(captured.value)


def test_valid_shape_with_changed_checksum_is_altered_not_unknown() -> None:
    inventory = _inventory()
    first, second = inventory
    replacement_checksum = "FF" if first.checksum != "FF" else "00"
    altered = first.placeholder[:-4] + replacement_checksum + "__"
    translated = f"{altered} {second.placeholder}"

    with pytest.raises(PlaceholderIntegrityError) as captured:
        PlaceholderRestorer().restore(translated, inventory)

    assert PlaceholderIssueCode.ALTERED in _codes(captured.value)
    assert PlaceholderIssueCode.UNKNOWN not in _codes(captured.value)


def test_reordered_placeholders_fail_only_when_order_matters() -> None:
    inventory = _inventory()
    first, second = inventory
    translated = f"{second.placeholder} lalu {first.placeholder}"
    restorer = PlaceholderRestorer()

    with pytest.raises(PlaceholderIntegrityError) as captured:
        restorer.restore(translated, inventory)
    restored = restorer.restore(translated, inventory, enforce_order=False)

    assert PlaceholderIssueCode.REORDERED in _codes(captured.value)
    assert restored == "https://example.test lalu framework"


def test_case_changed_placeholder_is_malformed_and_missing() -> None:
    inventory = _inventory()
    first, second = inventory
    changed = first.placeholder.replace("__TLK_TERM_", "__TLK_term_", 1)

    with pytest.raises(PlaceholderIntegrityError) as captured:
        PlaceholderRestorer().restore(f"{changed} {second.placeholder}", inventory)

    assert PlaceholderIssueCode.MISSING in _codes(captured.value)
    assert PlaceholderIssueCode.MALFORMED in _codes(captured.value)


def test_invalid_or_duplicate_inventory_is_rejected() -> None:
    inventory = _inventory()
    invalid = replace(inventory[0], placeholder="not-a-placeholder")

    with pytest.raises(InvalidPlaceholderInventoryError):
        PlaceholderRestorer().restore("text", [inventory[0], inventory[0]])
    with pytest.raises(InvalidPlaceholderInventoryError):
        PlaceholderRestorer().restore("text", [invalid])


def test_empty_inventory_accepts_plain_text_but_rejects_placeholder_tokens() -> None:
    restorer = PlaceholderRestorer()

    assert restorer.restore("Plain translated text.", []) == "Plain translated text."
    with pytest.raises(PlaceholderIntegrityError) as captured:
        restorer.restore("Unexpected __TLK_TERM_0001_AA__.", [])

    assert PlaceholderIssueCode.UNKNOWN in _codes(captured.value)
