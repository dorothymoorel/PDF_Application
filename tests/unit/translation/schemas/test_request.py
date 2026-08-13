import pytest
from transloka_translation.schemas import (
    TranslationRequest,
    TranslationSchemaError,
    TranslationStyle,
)


def valid_request_payload() -> dict[str, object]:
    return {
        "segments": [
            {
                "segment_id": "segment_001",
                "source_text": "The __TLK_TERM_0001_AA__ validates credentials.",
            }
        ],
        "context": {
            "source_language": "en",
            "target_language": "id",
            "document_type": "TECHNICAL_BOOK",
            "heading": "Authentication Workflow",
            "previous_text": "The user submits a login request.",
            "next_text": "A token is generated.",
        },
        "glossary": [
            {
                "source_term": "workflow",
                "target_term": None,
                "rule_type": "KEEP_ORIGINAL",
            }
        ],
        "placeholders": [
            {
                "segment_id": "segment_001",
                "placeholder": "__TLK_TERM_0001_AA__",
                "item_type": "TERM",
            }
        ],
        "style": "PROFESSIONAL",
    }


def test_valid_request_round_trips_without_losing_contract_fields() -> None:
    payload = valid_request_payload()

    request = TranslationRequest.from_dict(payload)

    assert request.segment_ids == ("segment_001",)
    assert request.style is TranslationStyle.PROFESSIONAL
    assert request.to_dict() == payload


def test_request_rejects_missing_required_field() -> None:
    payload = valid_request_payload()
    del payload["context"]

    with pytest.raises(TranslationSchemaError, match="missing required field.*context"):
        TranslationRequest.from_dict(payload)


@pytest.mark.parametrize(
    ("location", "field"),
    [
        ("request", "command"),
        ("segment", "action"),
        ("context", "url_to_fetch"),
        ("glossary", "file_to_delete"),
        ("placeholder", "path"),
    ],
)
def test_request_rejects_unknown_fields(location: str, field: str) -> None:
    payload = valid_request_payload()
    if location == "request":
        payload[field] = "unsafe"
    elif location == "segment":
        segments = payload["segments"]
        assert isinstance(segments, list)
        segments[0][field] = "unsafe"
    elif location == "context":
        context = payload["context"]
        assert isinstance(context, dict)
        context[field] = "unsafe"
    elif location == "glossary":
        glossary = payload["glossary"]
        assert isinstance(glossary, list)
        glossary[0][field] = "unsafe"
    else:
        placeholders = payload["placeholders"]
        assert isinstance(placeholders, list)
        placeholders[0][field] = "unsafe"

    with pytest.raises(TranslationSchemaError, match="unknown field"):
        TranslationRequest.from_dict(payload)


def test_request_rejects_duplicate_segment_ids() -> None:
    payload = valid_request_payload()
    segments = payload["segments"]
    assert isinstance(segments, list)
    segments.append({"segment_id": "segment_001", "source_text": "Another sentence."})

    with pytest.raises(TranslationSchemaError, match="duplicate value.*segment_001"):
        TranslationRequest.from_dict(payload)


def test_request_rejects_duplicate_placeholders() -> None:
    payload = valid_request_payload()
    placeholders = payload["placeholders"]
    assert isinstance(placeholders, list)
    placeholders.append(dict(placeholders[0]))

    with pytest.raises(TranslationSchemaError, match="duplicate value.*__TLK_TERM_0001_AA__"):
        TranslationRequest.from_dict(payload)


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("segments", "not-an-array", "request.segments must be an array"),
        ("context", [], "request.context must be an object"),
        ("glossary", {}, "request.glossary must be an array"),
        ("placeholders", None, "request.placeholders must be an array"),
        ("style", 1, "request.style must be a string"),
    ],
)
def test_request_rejects_wrong_top_level_types(
    field: str,
    value: object,
    message: str,
) -> None:
    payload = valid_request_payload()
    payload[field] = value

    with pytest.raises(TranslationSchemaError, match=message):
        TranslationRequest.from_dict(payload)


def test_request_rejects_placeholder_for_unknown_segment() -> None:
    payload = valid_request_payload()
    placeholders = payload["placeholders"]
    assert isinstance(placeholders, list)
    placeholders[0]["segment_id"] = "segment_unknown"

    with pytest.raises(TranslationSchemaError, match="unknown segment ID.*segment_unknown"):
        TranslationRequest.from_dict(payload)


def test_request_json_schema_forbids_additional_fields_recursively() -> None:
    schema = TranslationRequest.json_schema()

    assert schema["additionalProperties"] is False
    assert schema["properties"]["segments"]["items"]["additionalProperties"] is False
    assert schema["properties"]["context"]["additionalProperties"] is False
    assert schema["properties"]["glossary"]["items"]["additionalProperties"] is False
    assert schema["properties"]["placeholders"]["items"]["additionalProperties"] is False
