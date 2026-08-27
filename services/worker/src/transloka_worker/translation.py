from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Self
from uuid import UUID

from transloka_translation.orchestration import (
    TranslationOperation,
    TranslationOrchestrator,
    TranslationRunResult,
)

TRANSLATION_COMMAND_SCHEMA = "transloka.translation.command.v1"
_TRANSLATION_SCOPES = frozenset(
    {
        "FULL_DOCUMENT",
        "UNTRANSLATED_ONLY",
        "UNREVIEWED_ONLY",
        "SECTION",
        "PAGE",
        "SELECTED_SEGMENTS",
    }
)
_TRANSLATION_STYLES = frozenset({"ACADEMIC", "PROFESSIONAL", "NATURAL", "LITERAL"})
_CONTEXT_MODES = frozenset({"NONE", "STANDARD", "EXTENDED"})
_COMMAND_FIELDS = frozenset(
    {
        "schema",
        "project_id",
        "document_id",
        "scope",
        "section_ids",
        "page_ids",
        "segment_ids",
        "model_id",
        "translation_style",
        "batch_size",
        "context_mode",
        "retranslate_existing",
        "skip_locked_segments",
        "run_semantic_validation",
        "glossary_snapshot_id",
    }
)


class TranslationWorkerError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class TranslationCommand:
    project_id: str
    document_id: str
    scope: str
    section_ids: tuple[str, ...]
    page_ids: tuple[str, ...]
    segment_ids: tuple[str, ...]
    model_id: str
    translation_style: str
    batch_size: int
    context_mode: str
    retranslate_existing: bool
    skip_locked_segments: bool
    run_semantic_validation: bool
    glossary_snapshot_id: str

    def __post_init__(self) -> None:
        _validate_identifier(self.project_id, "prj_")
        _validate_identifier(self.document_id, "doc_")
        _validate_identifiers(self.section_ids, "sec_")
        _validate_identifiers(self.page_ids, "pag_")
        _validate_identifiers(self.segment_ids, "seg_")
        _validate_identifier(self.model_id, "mdl_")
        _validate_identifier(self.glossary_snapshot_id, "gsn_")
        if self.scope not in _TRANSLATION_SCOPES:
            raise TranslationWorkerError("The translation command scope is invalid.")
        if self.translation_style not in _TRANSLATION_STYLES:
            raise TranslationWorkerError("The translation command style is invalid.")
        if type(self.batch_size) is not int or not 1 <= self.batch_size <= 100:
            raise TranslationWorkerError("The translation command batch size is invalid.")
        if self.context_mode not in _CONTEXT_MODES:
            raise TranslationWorkerError("The translation command context mode is invalid.")
        for value in (
            self.retranslate_existing,
            self.skip_locked_segments,
            self.run_semantic_validation,
        ):
            if type(value) is not bool:
                raise TranslationWorkerError("The translation command flags are invalid.")
        _validate_scope_selectors(self)

    def to_payload(self) -> dict[str, object]:
        return {
            "schema": TRANSLATION_COMMAND_SCHEMA,
            "project_id": self.project_id,
            "document_id": self.document_id,
            "scope": self.scope,
            "section_ids": list(self.section_ids),
            "page_ids": list(self.page_ids),
            "segment_ids": list(self.segment_ids),
            "model_id": self.model_id,
            "translation_style": self.translation_style,
            "batch_size": self.batch_size,
            "context_mode": self.context_mode,
            "retranslate_existing": self.retranslate_existing,
            "skip_locked_segments": self.skip_locked_segments,
            "run_semantic_validation": self.run_semantic_validation,
            "glossary_snapshot_id": self.glossary_snapshot_id,
        }

    @classmethod
    def from_payload_json(cls, value: str) -> Self:
        payload = _decode_translation_command(value)
        if frozenset(payload) != _COMMAND_FIELDS:
            raise TranslationWorkerError("The translation command fields are invalid.")
        if payload["schema"] != TRANSLATION_COMMAND_SCHEMA:
            raise TranslationWorkerError("The translation command schema is unsupported.")
        try:
            return cls(
                project_id=_string_value(payload, "project_id"),
                document_id=_string_value(payload, "document_id"),
                scope=_string_value(payload, "scope"),
                section_ids=_identifier_tuple(payload["section_ids"]),
                page_ids=_identifier_tuple(payload["page_ids"]),
                segment_ids=_identifier_tuple(payload["segment_ids"]),
                model_id=_string_value(payload, "model_id"),
                translation_style=_string_value(payload, "translation_style"),
                batch_size=_integer_value(payload, "batch_size"),
                context_mode=_string_value(payload, "context_mode"),
                retranslate_existing=_boolean_value(payload, "retranslate_existing"),
                skip_locked_segments=_boolean_value(payload, "skip_locked_segments"),
                run_semantic_validation=_boolean_value(payload, "run_semantic_validation"),
                glossary_snapshot_id=_string_value(payload, "glossary_snapshot_id"),
            )
        except (TypeError, KeyError):
            raise TranslationWorkerError("The translation command values are invalid.") from None


def _decode_translation_command(value: str) -> dict[str, object]:
    if type(value) is not str or not value:
        raise TranslationWorkerError("The translation command JSON is invalid.")

    def decode_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, item in pairs:
            if key in result:
                raise TranslationWorkerError("The translation command fields are duplicated.")
            result[key] = item
        return result

    try:
        payload = json.loads(value, object_pairs_hook=decode_pairs)
    except (json.JSONDecodeError, TranslationWorkerError):
        raise TranslationWorkerError("The translation command JSON is invalid.") from None
    if not isinstance(payload, dict):
        raise TranslationWorkerError("The translation command must be a JSON object.")
    return payload


def _identifier_tuple(value: object) -> tuple[str, ...]:
    if type(value) is not list or any(type(item) is not str for item in value):
        raise TranslationWorkerError("The translation command selector values are invalid.")
    return tuple(value)


def _string_value(payload: dict[str, object], key: str) -> str:
    value = payload[key]
    if type(value) is not str:
        raise TranslationWorkerError("The translation command values are invalid.")
    return value


def _integer_value(payload: dict[str, object], key: str) -> int:
    value = payload[key]
    if type(value) is not int:
        raise TranslationWorkerError("The translation command values are invalid.")
    return value


def _boolean_value(payload: dict[str, object], key: str) -> bool:
    value = payload[key]
    if type(value) is not bool:
        raise TranslationWorkerError("The translation command values are invalid.")
    return value


def _validate_identifier(value: object, prefix: str) -> None:
    if type(value) is not str or not value.startswith(prefix):
        raise TranslationWorkerError("A translation command identifier is invalid.")
    try:
        identifier = UUID(value[len(prefix) :])
    except (ValueError, AttributeError):
        raise TranslationWorkerError("A translation command identifier is invalid.") from None
    if value != f"{prefix}{identifier}":
        raise TranslationWorkerError("A translation command identifier is invalid.")


def _validate_identifiers(values: object, prefix: str) -> None:
    if type(values) is not tuple or len(values) != len(set(values)):
        raise TranslationWorkerError("The translation command selectors are invalid.")
    for value in values:
        _validate_identifier(value, prefix)


def _validate_scope_selectors(command: TranslationCommand) -> None:
    populated = {
        "SECTION": bool(command.section_ids),
        "PAGE": bool(command.page_ids),
        "SELECTED_SEGMENTS": bool(command.segment_ids),
    }
    if command.scope in populated:
        if not populated[command.scope] or sum(populated.values()) != 1:
            raise TranslationWorkerError("The translation command selector is invalid.")
        return
    if any(populated.values()):
        raise TranslationWorkerError("The translation command selector is invalid.")


class TranslationJobRunner:
    """Small worker boundary that keeps queue concerns separate from the pipeline."""

    def __init__(
        self,
        orchestrator: TranslationOrchestrator,
        operation_loader: Callable[[str], TranslationOperation],
    ) -> None:
        self._orchestrator = orchestrator
        self._operation_loader = operation_loader

    def run(self, job_id: str) -> TranslationRunResult:
        if type(job_id) is not str or not job_id.strip():
            raise ValueError("job_id must be a non-empty string.")
        operation = self._operation_loader(job_id)
        if not isinstance(operation, TranslationOperation):
            raise TypeError("operation_loader must return TranslationOperation.")
        return asyncio.run(self._orchestrator.run(operation))


def run_translation_job(
    job_id: str,
    *,
    orchestrator: TranslationOrchestrator,
    operation_loader: Callable[[str], TranslationOperation],
) -> TranslationRunResult:
    return TranslationJobRunner(orchestrator, operation_loader).run(job_id)


def create_translation_task(
    *,
    orchestrator: TranslationOrchestrator,
    operation_loader: Callable[[str], TranslationOperation],
) -> Callable[[str], TranslationRunResult]:
    runner = TranslationJobRunner(orchestrator, operation_loader)
    return runner.run
