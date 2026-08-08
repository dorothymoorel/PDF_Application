import json

import pytest
from pydantic import ValidationError
from transloka_document_ir import CURRENT_IR_VERSION, Document


def test_document_json_round_trip_is_lossless(minimal_document: Document) -> None:
    serialized = minimal_document.model_dump_json()
    restored = Document.model_validate_json(serialized)

    assert restored == minimal_document
    assert restored.pages[0].blocks[0].segments[0].source_text == (
        "The workflow begins after authentication."
    )


def test_serialized_contract_uses_schema_version_and_snake_case(
    minimal_document: Document,
) -> None:
    payload = json.loads(minimal_document.model_dump_json())

    assert payload["ir_version"] == CURRENT_IR_VERSION
    assert payload["source_file_id"].startswith("fil_")
    assert "sourceFileId" not in payload


def test_unknown_incompatible_schema_version_is_rejected(
    minimal_document: Document,
) -> None:
    payload = json.loads(minimal_document.model_dump_json())
    payload["ir_version"] = "1.0"

    with pytest.raises(ValidationError, match="ir_version"):
        Document.model_validate_json(json.dumps(payload))


def test_unknown_optional_field_is_preserved_for_compatible_version(
    minimal_document: Document,
) -> None:
    payload = json.loads(minimal_document.model_dump_json())
    payload["publisher"] = "TransLoka Press"

    restored = Document.model_validate_json(json.dumps(payload))

    assert restored.model_dump()["publisher"] == "TransLoka Press"
