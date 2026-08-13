from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Any, Self

from ._validation import (
    TranslationSchemaError,
    object_schema,
    reject_duplicate,
    require_fields,
    require_list,
    require_mapping,
    require_optional_string,
    require_string,
)


class TranslationStyle(StrEnum):
    ACADEMIC = "ACADEMIC"
    PROFESSIONAL = "PROFESSIONAL"
    NATURAL = "NATURAL"
    LITERAL = "LITERAL"
    LITERARY = "LITERARY"
    CUSTOM = "CUSTOM"


@dataclass(frozen=True, slots=True)
class TranslationRequestSegment:
    segment_id: str
    source_text: str

    def __post_init__(self) -> None:
        require_string(self.segment_id, "segment.segment_id")
        require_string(self.source_text, "segment.source_text")

    @classmethod
    def from_dict(cls, value: object, *, path: str = "segment") -> Self:
        payload = require_mapping(value, path)
        require_fields(
            payload,
            required=frozenset({"segment_id", "source_text"}),
            path=path,
        )
        return cls(
            segment_id=require_string(payload["segment_id"], f"{path}.segment_id"),
            source_text=require_string(payload["source_text"], f"{path}.source_text"),
        )

    def to_dict(self) -> dict[str, str]:
        return {"segment_id": self.segment_id, "source_text": self.source_text}


@dataclass(frozen=True, slots=True)
class TranslationContext:
    source_language: str
    target_language: str
    document_type: str | None = None
    heading: str | None = None
    previous_text: str | None = None
    next_text: str | None = None

    def __post_init__(self) -> None:
        require_string(self.source_language, "context.source_language")
        require_string(self.target_language, "context.target_language")
        for field_name in ("document_type", "heading", "previous_text", "next_text"):
            require_optional_string(getattr(self, field_name), f"context.{field_name}")

    @classmethod
    def from_dict(cls, value: object) -> Self:
        path = "request.context"
        payload = require_mapping(value, path)
        require_fields(
            payload,
            required=frozenset({"source_language", "target_language"}),
            optional=frozenset({"document_type", "heading", "previous_text", "next_text"}),
            path=path,
        )
        return cls(
            source_language=require_string(payload["source_language"], f"{path}.source_language"),
            target_language=require_string(payload["target_language"], f"{path}.target_language"),
            document_type=require_optional_string(
                payload.get("document_type"), f"{path}.document_type"
            ),
            heading=require_optional_string(payload.get("heading"), f"{path}.heading"),
            previous_text=require_optional_string(
                payload.get("previous_text"), f"{path}.previous_text"
            ),
            next_text=require_optional_string(payload.get("next_text"), f"{path}.next_text"),
        )

    def to_dict(self) -> dict[str, str | None]:
        return {
            "source_language": self.source_language,
            "target_language": self.target_language,
            "document_type": self.document_type,
            "heading": self.heading,
            "previous_text": self.previous_text,
            "next_text": self.next_text,
        }


@dataclass(frozen=True, slots=True)
class TranslationGlossaryEntry:
    source_term: str
    target_term: str | None
    rule_type: str

    def __post_init__(self) -> None:
        require_string(self.source_term, "glossary.source_term")
        require_optional_string(self.target_term, "glossary.target_term")
        require_string(self.rule_type, "glossary.rule_type")

    @classmethod
    def from_dict(cls, value: object, *, path: str = "glossary entry") -> Self:
        payload = require_mapping(value, path)
        require_fields(
            payload,
            required=frozenset({"source_term", "target_term", "rule_type"}),
            path=path,
        )
        return cls(
            source_term=require_string(payload["source_term"], f"{path}.source_term"),
            target_term=require_optional_string(payload["target_term"], f"{path}.target_term"),
            rule_type=require_string(payload["rule_type"], f"{path}.rule_type"),
        )

    def to_dict(self) -> dict[str, str | None]:
        return {
            "source_term": self.source_term,
            "target_term": self.target_term,
            "rule_type": self.rule_type,
        }


@dataclass(frozen=True, slots=True)
class TranslationPlaceholder:
    segment_id: str
    placeholder: str
    item_type: str

    def __post_init__(self) -> None:
        require_string(self.segment_id, "placeholder.segment_id")
        require_string(self.placeholder, "placeholder.placeholder")
        require_string(self.item_type, "placeholder.item_type")

    @classmethod
    def from_dict(cls, value: object, *, path: str = "placeholder") -> Self:
        payload = require_mapping(value, path)
        require_fields(
            payload,
            required=frozenset({"segment_id", "placeholder", "item_type"}),
            path=path,
        )
        return cls(
            segment_id=require_string(payload["segment_id"], f"{path}.segment_id"),
            placeholder=require_string(payload["placeholder"], f"{path}.placeholder"),
            item_type=require_string(payload["item_type"], f"{path}.item_type"),
        )

    def to_dict(self) -> dict[str, str]:
        return {
            "segment_id": self.segment_id,
            "placeholder": self.placeholder,
            "item_type": self.item_type,
        }


@dataclass(frozen=True, slots=True)
class TranslationRequest:
    segments: tuple[TranslationRequestSegment, ...]
    context: TranslationContext
    glossary: tuple[TranslationGlossaryEntry, ...]
    placeholders: tuple[TranslationPlaceholder, ...]
    style: TranslationStyle

    def __post_init__(self) -> None:
        if type(self.segments) is not tuple or not self.segments:
            raise TranslationSchemaError("request.segments must be a non-empty tuple.")
        if any(type(item) is not TranslationRequestSegment for item in self.segments):
            raise TranslationSchemaError("request.segments contains an invalid item.")
        if type(self.context) is not TranslationContext:
            raise TranslationSchemaError("request.context must be a TranslationContext.")
        if type(self.glossary) is not tuple or any(
            type(item) is not TranslationGlossaryEntry for item in self.glossary
        ):
            raise TranslationSchemaError("request.glossary must contain glossary entries.")
        if type(self.placeholders) is not tuple or any(
            type(item) is not TranslationPlaceholder for item in self.placeholders
        ):
            raise TranslationSchemaError("request.placeholders must contain placeholders.")
        if type(self.style) is not TranslationStyle:
            raise TranslationSchemaError("request.style must be a TranslationStyle.")

        segment_ids = tuple(segment.segment_id for segment in self.segments)
        reject_duplicate(segment_ids, "request segment IDs")
        reject_duplicate(
            tuple(placeholder.placeholder for placeholder in self.placeholders),
            "request placeholders",
        )
        unknown_placeholder_ids = {
            placeholder.segment_id
            for placeholder in self.placeholders
            if placeholder.segment_id not in segment_ids
        }
        if unknown_placeholder_ids:
            unknown = ", ".join(sorted(unknown_placeholder_ids))
            raise TranslationSchemaError(
                f"request.placeholders references unknown segment ID(s): {unknown}."
            )

    @property
    def segment_ids(self) -> tuple[str, ...]:
        return tuple(segment.segment_id for segment in self.segments)

    @classmethod
    def from_dict(cls, value: object) -> Self:
        path = "request"
        payload = require_mapping(value, path)
        require_fields(
            payload,
            required=frozenset({"segments", "context", "glossary", "placeholders", "style"}),
            path=path,
        )
        segments = require_list(payload["segments"], "request.segments")
        glossary = require_list(payload["glossary"], "request.glossary")
        placeholders = require_list(payload["placeholders"], "request.placeholders")
        style_value = require_string(payload["style"], "request.style")
        try:
            style = TranslationStyle(style_value)
        except ValueError as error:
            raise TranslationSchemaError(
                f"request.style has an unsupported value: {style_value}."
            ) from error

        return cls(
            segments=tuple(
                TranslationRequestSegment.from_dict(item, path=f"request.segments[{index}]")
                for index, item in enumerate(segments)
            ),
            context=TranslationContext.from_dict(payload["context"]),
            glossary=tuple(
                TranslationGlossaryEntry.from_dict(item, path=f"request.glossary[{index}]")
                for index, item in enumerate(glossary)
            ),
            placeholders=tuple(
                TranslationPlaceholder.from_dict(item, path=f"request.placeholders[{index}]")
                for index, item in enumerate(placeholders)
            ),
            style=style,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "segments": [segment.to_dict() for segment in self.segments],
            "context": self.context.to_dict(),
            "glossary": [entry.to_dict() for entry in self.glossary],
            "placeholders": [placeholder.to_dict() for placeholder in self.placeholders],
            "style": self.style.value,
        }

    @staticmethod
    def json_schema() -> dict[str, Any]:
        optional_context = {
            "document_type": {"type": ["string", "null"], "minLength": 1},
            "heading": {"type": ["string", "null"], "minLength": 1},
            "previous_text": {"type": ["string", "null"], "minLength": 1},
            "next_text": {"type": ["string", "null"], "minLength": 1},
        }
        return object_schema(
            {
                "segments": {
                    "type": "array",
                    "minItems": 1,
                    "items": object_schema(
                        {
                            "segment_id": {"type": "string", "minLength": 1},
                            "source_text": {"type": "string", "minLength": 1},
                        },
                        ["segment_id", "source_text"],
                    ),
                },
                "context": object_schema(
                    {
                        "source_language": {"type": "string", "minLength": 1},
                        "target_language": {"type": "string", "minLength": 1},
                        **optional_context,
                    },
                    ["source_language", "target_language"],
                ),
                "glossary": {
                    "type": "array",
                    "items": object_schema(
                        {
                            "source_term": {"type": "string", "minLength": 1},
                            "target_term": {"type": ["string", "null"], "minLength": 1},
                            "rule_type": {"type": "string", "minLength": 1},
                        },
                        ["source_term", "target_term", "rule_type"],
                    ),
                },
                "placeholders": {
                    "type": "array",
                    "items": object_schema(
                        {
                            "segment_id": {"type": "string", "minLength": 1},
                            "placeholder": {"type": "string", "minLength": 1},
                            "item_type": {"type": "string", "minLength": 1},
                        },
                        ["segment_id", "placeholder", "item_type"],
                    ),
                },
                "style": {"type": "string", "enum": [style.value for style in TranslationStyle]},
            },
            ["segments", "context", "glossary", "placeholders", "style"],
        )
