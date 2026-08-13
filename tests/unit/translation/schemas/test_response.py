import pytest
from transloka_translation.schemas import TranslationResponse, TranslationSchemaError


def test_valid_response_uses_known_segment_ids_and_translated_text_only() -> None:
    payload = {
        "segments": [
            {"segment_id": "segment_002", "translated_text": "Terjemahan kedua."},
            {"segment_id": "segment_001", "translated_text": "Terjemahan pertama."},
        ]
    }

    response = TranslationResponse.from_dict(
        payload,
        known_segment_ids=("segment_001", "segment_002"),
    )

    assert response.to_dict() == payload


def test_response_rejects_missing_segments_field() -> None:
    with pytest.raises(TranslationSchemaError, match="missing required field.*segments"):
        TranslationResponse.from_dict({}, known_segment_ids=("segment_001",))


@pytest.mark.parametrize("field", ["flags", "action", "command", "url_to_fetch", "file_path"])
def test_response_rejects_every_unknown_segment_field(field: str) -> None:
    payload = {
        "segments": [
            {
                "segment_id": "segment_001",
                "translated_text": "Hasil.",
                field: "not-allowed",
            }
        ]
    }

    with pytest.raises(TranslationSchemaError, match="unknown field"):
        TranslationResponse.from_dict(payload, known_segment_ids=("segment_001",))


def test_response_rejects_unknown_top_level_field() -> None:
    payload = {
        "segments": [{"segment_id": "segment_001", "translated_text": "Hasil."}],
        "explanation": "Model commentary",
    }

    with pytest.raises(TranslationSchemaError, match="unknown field.*explanation"):
        TranslationResponse.from_dict(payload, known_segment_ids=("segment_001",))


def test_response_rejects_duplicate_segment_ids() -> None:
    payload = {
        "segments": [
            {"segment_id": "segment_001", "translated_text": "Pertama."},
            {"segment_id": "segment_001", "translated_text": "Kedua."},
        ]
    }

    with pytest.raises(TranslationSchemaError, match="duplicate value.*segment_001"):
        TranslationResponse.from_dict(payload, known_segment_ids=("segment_001",))


def test_response_rejects_unknown_segment_id() -> None:
    payload = {"segments": [{"segment_id": "segment_999", "translated_text": "Hasil."}]}

    with pytest.raises(TranslationSchemaError, match="unknown segment ID.*segment_999"):
        TranslationResponse.from_dict(payload, known_segment_ids=("segment_001",))


def test_response_rejects_missing_known_segment_id() -> None:
    payload = {"segments": [{"segment_id": "segment_001", "translated_text": "Hasil."}]}

    with pytest.raises(TranslationSchemaError, match="missing segment ID.*segment_002"):
        TranslationResponse.from_dict(
            payload,
            known_segment_ids=("segment_001", "segment_002"),
        )


@pytest.mark.parametrize(
    "payload",
    [
        {"segments": "not-an-array"},
        {"segments": ["not-an-object"]},
        {"segments": [{"segment_id": 1, "translated_text": "Hasil."}]},
        {"segments": [{"segment_id": "segment_001", "translated_text": False}]},
    ],
)
def test_response_rejects_wrong_types(payload: dict[str, object]) -> None:
    with pytest.raises(TranslationSchemaError):
        TranslationResponse.from_dict(payload, known_segment_ids=("segment_001",))


def test_response_schema_is_closed_and_limits_ids_to_the_request() -> None:
    schema = TranslationResponse.json_schema(known_segment_ids=("segment_001", "segment_002"))
    segment_array = schema["properties"]["segments"]
    segment_schema = segment_array["items"]

    assert schema["additionalProperties"] is False
    assert segment_array["minItems"] == 2
    assert segment_array["maxItems"] == 2
    assert segment_schema["additionalProperties"] is False
    assert segment_schema["required"] == ["segment_id", "translated_text"]
    assert segment_schema["properties"] == {
        "segment_id": {"type": "string", "enum": ["segment_001", "segment_002"]},
        "translated_text": {"type": "string"},
    }


def test_response_allows_empty_text_for_the_later_parser_validation_stage() -> None:
    response = TranslationResponse.from_dict(
        {"segments": [{"segment_id": "segment_001", "translated_text": ""}]},
        known_segment_ids=("segment_001",),
    )

    assert response.segments[0].translated_text == ""
