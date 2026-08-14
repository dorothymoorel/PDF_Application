import json

import pytest
from transloka_translation.parsing import (
    ResponseParseError,
    ResponseParseErrorCode,
    StructuredResponseParser,
    parse_translation_response,
)


def test_parser_returns_valid_response_for_strict_json() -> None:
    raw_response = json.dumps(
        {
            "segments": [
                {"segment_id": "segment_002", "translated_text": "Kedua."},
                {"segment_id": "segment_001", "translated_text": "Pertama."},
            ]
        }
    )

    response = parse_translation_response(
        raw_response,
        known_segment_ids=("segment_001", "segment_002"),
    )

    assert [segment.segment_id for segment in response.segments] == [
        "segment_002",
        "segment_001",
    ]


def test_parser_allows_json_surrounded_by_whitespace() -> None:
    raw_response = (
        '\n  {"segments": [{"segment_id": "segment_001", "translated_text": "Hasil."}]}  \t'
    )

    response = StructuredResponseParser.parse(
        raw_response,
        known_segment_ids=("segment_001",),
    )

    assert response.segments[0].translated_text == "Hasil."


@pytest.mark.parametrize(
    "raw_response",
    [
        "not JSON",
        "",
        '{"segments": [',
        '{"segments": []} trailing text',
    ],
)
def test_parser_rejects_invalid_or_truncated_json(raw_response: str) -> None:
    _assert_rejected(raw_response, ResponseParseErrorCode.INVALID_JSON)


def test_parser_rejects_explanation_before_json() -> None:
    raw_response = (
        'Here is the translation: {"segments": '
        '[{"segment_id": "segment_001", "translated_text": "Hasil."}]}'
    )

    _assert_rejected(raw_response, ResponseParseErrorCode.INVALID_JSON)


@pytest.mark.parametrize(
    "raw_response",
    [
        '```json\n{"segments": []}\n```',
        '```\n{"segments": []}\n```',
        '```json\n{"segments": []}\n```\nModel explanation',
    ],
)
def test_parser_rejects_markdown_code_fence(raw_response: str) -> None:
    _assert_rejected(raw_response, ResponseParseErrorCode.MARKDOWN_WRAPPER)


@pytest.mark.parametrize(
    "payload",
    [
        {},
        {"segments": [{"segment_id": "segment_001"}]},
        {
            "segments": [
                {
                    "segment_id": "segment_001",
                    "translated_text": "Hasil.",
                    "command": "delete files",
                }
            ]
        },
        {
            "segments": [{"segment_id": "segment_001", "translated_text": "Hasil."}],
            "explanation": "Model commentary",
        },
        {"segments": "not-an-array"},
        {"segments": [{"segment_id": 1, "translated_text": "Hasil."}]},
        {"segments": [{"segment_id": "segment_001", "translated_text": False}]},
    ],
)
def test_parser_rejects_missing_unknown_and_wrong_typed_fields(
    payload: dict[str, object],
) -> None:
    _assert_rejected(json.dumps(payload), ResponseParseErrorCode.SCHEMA_MISMATCH)


def test_parser_rejects_duplicate_segment() -> None:
    raw_response = json.dumps(
        {
            "segments": [
                {"segment_id": "segment_001", "translated_text": "Pertama."},
                {"segment_id": "segment_001", "translated_text": "Kedua."},
            ]
        }
    )

    _assert_rejected(raw_response, ResponseParseErrorCode.DUPLICATE_SEGMENT)


def test_parser_rejects_unknown_segment_id() -> None:
    raw_response = json.dumps(
        {"segments": [{"segment_id": "segment_999", "translated_text": "Hasil."}]}
    )

    _assert_rejected(raw_response, ResponseParseErrorCode.UNKNOWN_SEGMENT_ID)


def test_parser_rejects_missing_segment() -> None:
    raw_response = json.dumps(
        {"segments": [{"segment_id": "segment_001", "translated_text": "Hasil."}]}
    )

    _assert_rejected(
        raw_response,
        ResponseParseErrorCode.MISSING_SEGMENT,
        known_segment_ids=("segment_001", "segment_002"),
    )


@pytest.mark.parametrize("translated_text", ["", " ", "\n\t"])
def test_parser_rejects_empty_translation(translated_text: str) -> None:
    raw_response = json.dumps(
        {
            "segments": [
                {
                    "segment_id": "segment_001",
                    "translated_text": translated_text,
                }
            ]
        }
    )

    _assert_rejected(raw_response, ResponseParseErrorCode.EMPTY_TRANSLATION)


@pytest.mark.parametrize("constant", ["NaN", "Infinity", "-Infinity"])
def test_parser_rejects_nonstandard_json_constants(constant: str) -> None:
    raw_response = (
        '{"segments": [{"segment_id": "segment_001", "translated_text": ' + constant + "}]}"
    )

    _assert_rejected(raw_response, ResponseParseErrorCode.INVALID_JSON)


def test_parser_rejects_duplicate_json_fields_instead_of_discarding_one() -> None:
    raw_response = (
        '{"segments": [{"segment_id": "segment_001", '
        '"translated_text": "Safe", "translated_text": "Replacement"}]}'
    )

    _assert_rejected(raw_response, ResponseParseErrorCode.INVALID_JSON)


def test_parser_rejects_non_string_provider_output() -> None:
    with pytest.raises(ResponseParseError) as raised:
        StructuredResponseParser.parse(
            {"segments": []},  # type: ignore[arg-type]
            known_segment_ids=("segment_001",),
        )

    assert raised.value.code is ResponseParseErrorCode.INVALID_JSON


def test_parser_does_not_include_untrusted_output_in_normalized_error() -> None:
    secret_model_output = "sensitive model output"

    with pytest.raises(ResponseParseError) as raised:
        parse_translation_response(
            secret_model_output,
            known_segment_ids=("segment_001",),
        )

    assert secret_model_output not in str(raised.value)


def _assert_rejected(
    raw_response: str,
    expected_code: ResponseParseErrorCode,
    *,
    known_segment_ids: tuple[str, ...] = ("segment_001",),
) -> None:
    with pytest.raises(ResponseParseError) as raised:
        parse_translation_response(
            raw_response,
            known_segment_ids=known_segment_ids,
        )

    assert raised.value.code is expected_code
