from __future__ import annotations

import json
from collections.abc import Iterable
from enum import StrEnum
from typing import Never

from transloka_translation.schemas import TranslationResponse, TranslationSchemaError


class ResponseParseErrorCode(StrEnum):
    INVALID_JSON = "INVALID_JSON"
    MARKDOWN_WRAPPER = "MARKDOWN_WRAPPER"
    SCHEMA_MISMATCH = "SCHEMA_MISMATCH"
    MISSING_SEGMENT = "MISSING_SEGMENT"
    DUPLICATE_SEGMENT = "DUPLICATE_SEGMENT"
    UNKNOWN_SEGMENT_ID = "UNKNOWN_SEGMENT_ID"
    EMPTY_TRANSLATION = "EMPTY_TRANSLATION"


class ResponseParseError(ValueError):
    """Raised when an untrusted model response cannot become a valid translation."""

    def __init__(self, code: ResponseParseErrorCode, message: str) -> None:
        super().__init__(message)
        self.code = code


class _InvalidJsonValueError(ValueError):
    pass


class StructuredResponseParser:
    @staticmethod
    def parse(
        raw_response: str,
        *,
        known_segment_ids: Iterable[str],
    ) -> TranslationResponse:
        if type(raw_response) is not str:
            raise ResponseParseError(
                ResponseParseErrorCode.INVALID_JSON,
                "Translation response must be a JSON string.",
            )

        stripped_response = raw_response.strip()
        if stripped_response.startswith("```") or stripped_response.endswith("```"):
            raise ResponseParseError(
                ResponseParseErrorCode.MARKDOWN_WRAPPER,
                "Translation response must not use a Markdown code fence.",
            )

        try:
            payload: object = json.loads(
                raw_response,
                object_pairs_hook=_unique_object,
                parse_constant=_reject_nonstandard_constant,
            )
        except (json.JSONDecodeError, _InvalidJsonValueError) as error:
            raise ResponseParseError(
                ResponseParseErrorCode.INVALID_JSON,
                "Translation response is not strict JSON.",
            ) from error

        try:
            response = TranslationResponse.from_dict(
                payload,
                known_segment_ids=known_segment_ids,
            )
        except TranslationSchemaError as error:
            code = _schema_error_code(str(error))
            raise ResponseParseError(code, _schema_error_message(code)) from error

        if any(not segment.translated_text.strip() for segment in response.segments):
            raise ResponseParseError(
                ResponseParseErrorCode.EMPTY_TRANSLATION,
                "Translation response contains empty translated text.",
            )

        return response


def parse_translation_response(
    raw_response: str,
    *,
    known_segment_ids: Iterable[str],
) -> TranslationResponse:
    return StructuredResponseParser.parse(
        raw_response,
        known_segment_ids=known_segment_ids,
    )


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise _InvalidJsonValueError("JSON object field names must be unique.")
        result[key] = value
    return result


def _reject_nonstandard_constant(value: str) -> Never:
    raise _InvalidJsonValueError(f"Non-standard JSON constant is not allowed: {value}.")


def _schema_error_code(message: str) -> ResponseParseErrorCode:
    if message.startswith("response segment IDs contains duplicate value(s):"):
        return ResponseParseErrorCode.DUPLICATE_SEGMENT
    if message.startswith("response contains unknown segment ID(s):"):
        return ResponseParseErrorCode.UNKNOWN_SEGMENT_ID
    if message.startswith("response is missing segment ID(s):"):
        return ResponseParseErrorCode.MISSING_SEGMENT
    return ResponseParseErrorCode.SCHEMA_MISMATCH


def _schema_error_message(code: ResponseParseErrorCode) -> str:
    messages = {
        ResponseParseErrorCode.DUPLICATE_SEGMENT: (
            "Translation response contains a duplicate segment ID."
        ),
        ResponseParseErrorCode.UNKNOWN_SEGMENT_ID: (
            "Translation response contains an unknown segment ID."
        ),
        ResponseParseErrorCode.MISSING_SEGMENT: (
            "Translation response is missing an expected segment."
        ),
        ResponseParseErrorCode.SCHEMA_MISMATCH: (
            "Translation response does not match the required schema."
        ),
    }
    return messages[code]
