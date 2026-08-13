from __future__ import annotations

from collections.abc import Mapping
from typing import Any


class TranslationSchemaError(ValueError):
    """Raised when a translation contract payload is invalid."""


def require_mapping(value: object, path: str) -> Mapping[str, object]:
    if not isinstance(value, Mapping):
        raise TranslationSchemaError(f"{path} must be an object.")
    if any(type(key) is not str for key in value):
        raise TranslationSchemaError(f"{path} field names must be strings.")
    return value


def require_fields(
    value: Mapping[str, object],
    *,
    required: frozenset[str],
    optional: frozenset[str] = frozenset(),
    path: str,
) -> None:
    fields = set(value)
    missing = required - fields
    if missing:
        raise TranslationSchemaError(f"{path} is missing required field(s): {_names(missing)}.")

    unknown = fields - required - optional
    if unknown:
        raise TranslationSchemaError(f"{path} has unknown field(s): {_names(unknown)}.")


def require_list(value: object, path: str) -> list[object]:
    if type(value) is not list:
        raise TranslationSchemaError(f"{path} must be an array.")
    return value


def require_string(value: object, path: str, *, allow_empty: bool = False) -> str:
    if type(value) is not str:
        raise TranslationSchemaError(f"{path} must be a string.")
    if not allow_empty and not value.strip():
        raise TranslationSchemaError(f"{path} must not be empty.")
    return value


def require_optional_string(value: object, path: str) -> str | None:
    if value is None:
        return None
    return require_string(value, path)


def reject_duplicate(values: tuple[str, ...], path: str) -> None:
    seen: set[str] = set()
    duplicate: set[str] = set()
    for value in values:
        if value in seen:
            duplicate.add(value)
        seen.add(value)
    if duplicate:
        raise TranslationSchemaError(f"{path} contains duplicate value(s): {_names(duplicate)}.")


def object_schema(
    properties: dict[str, Any],
    required: list[str],
) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": properties,
        "required": required,
        "additionalProperties": False,
    }


def _names(values: set[str] | frozenset[str]) -> str:
    return ", ".join(sorted(values))
