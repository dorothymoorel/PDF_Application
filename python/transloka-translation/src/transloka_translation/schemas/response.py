from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any, Self

from ._validation import (
    TranslationSchemaError,
    object_schema,
    reject_duplicate,
    require_fields,
    require_list,
    require_mapping,
    require_string,
)


@dataclass(frozen=True, slots=True)
class TranslatedSegment:
    segment_id: str
    translated_text: str

    def __post_init__(self) -> None:
        require_string(self.segment_id, "translated segment.segment_id")
        require_string(
            self.translated_text,
            "translated segment.translated_text",
            allow_empty=True,
        )

    @classmethod
    def from_dict(cls, value: object, *, path: str = "translated segment") -> Self:
        payload = require_mapping(value, path)
        require_fields(
            payload,
            required=frozenset({"segment_id", "translated_text"}),
            path=path,
        )
        return cls(
            segment_id=require_string(payload["segment_id"], f"{path}.segment_id"),
            translated_text=require_string(
                payload["translated_text"],
                f"{path}.translated_text",
                allow_empty=True,
            ),
        )

    def to_dict(self) -> dict[str, str]:
        return {"segment_id": self.segment_id, "translated_text": self.translated_text}


@dataclass(frozen=True, slots=True)
class TranslationResponse:
    segments: tuple[TranslatedSegment, ...]

    def __post_init__(self) -> None:
        if type(self.segments) is not tuple:
            raise TranslationSchemaError("response.segments must be a tuple.")
        if any(type(item) is not TranslatedSegment for item in self.segments):
            raise TranslationSchemaError("response.segments contains an invalid item.")
        reject_duplicate(
            tuple(segment.segment_id for segment in self.segments),
            "response segment IDs",
        )

    @classmethod
    def from_dict(cls, value: object, *, known_segment_ids: Iterable[str]) -> Self:
        known_ids = _known_segment_ids(known_segment_ids)
        path = "response"
        payload = require_mapping(value, path)
        require_fields(payload, required=frozenset({"segments"}), path=path)
        segments = require_list(payload["segments"], "response.segments")
        response = cls(
            segments=tuple(
                TranslatedSegment.from_dict(item, path=f"response.segments[{index}]")
                for index, item in enumerate(segments)
            )
        )
        response.validate_segment_ids(known_ids)
        return response

    def validate_segment_ids(self, known_segment_ids: Iterable[str]) -> None:
        known_ids = _known_segment_ids(known_segment_ids)
        response_ids = {segment.segment_id for segment in self.segments}
        known_set = set(known_ids)
        unknown = response_ids - known_set
        if unknown:
            raise TranslationSchemaError(
                "response contains unknown segment ID(s): " + ", ".join(sorted(unknown)) + "."
            )
        missing = known_set - response_ids
        if missing:
            raise TranslationSchemaError(
                "response is missing segment ID(s): " + ", ".join(sorted(missing)) + "."
            )

    def to_dict(self) -> dict[str, object]:
        return {"segments": [segment.to_dict() for segment in self.segments]}

    @staticmethod
    def json_schema(*, known_segment_ids: Iterable[str]) -> dict[str, Any]:
        known_ids = _known_segment_ids(known_segment_ids)
        count = len(known_ids)
        return object_schema(
            {
                "segments": {
                    "type": "array",
                    "minItems": count,
                    "maxItems": count,
                    "items": object_schema(
                        {
                            "segment_id": {"type": "string", "enum": list(known_ids)},
                            "translated_text": {"type": "string"},
                        },
                        ["segment_id", "translated_text"],
                    ),
                }
            },
            ["segments"],
        )


def _known_segment_ids(values: Iterable[str]) -> tuple[str, ...]:
    if isinstance(values, (str, bytes)):
        raise TranslationSchemaError("known_segment_ids must be an iterable of strings.")
    try:
        result = tuple(values)
    except TypeError as error:
        raise TranslationSchemaError("known_segment_ids must be an iterable of strings.") from error
    if not result:
        raise TranslationSchemaError("known_segment_ids must not be empty.")
    for index, value in enumerate(result):
        require_string(value, f"known_segment_ids[{index}]")
    reject_duplicate(result, "known_segment_ids")
    return result
