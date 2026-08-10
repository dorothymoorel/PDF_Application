from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum
from uuid import uuid4

from transloka_core.database.models.glossary import (
    GlossaryMatchMode,
    GlossaryRevisionType,
    GlossaryRuleType,
    GlossaryScope,
)

from transloka_glossary.repository import (
    GlossaryRecord,
    GlossaryRepository,
    GlossaryStatus,
    GlossaryTermStatus,
    InvalidGlossaryValueError,
    RevisionRecord,
    TermRecord,
)

_GLOSSARY_UPDATE_FIELDS = frozenset({"name", "description"})
_TERM_UPDATE_FIELDS = frozenset(
    {
        "source_term",
        "rule_type",
        "target_term",
        "scope",
        "scope_reference_id",
        "priority",
        "case_sensitive",
        "whole_word",
        "match_mode",
        "capitalization_policy",
        "inflection_policy",
        "first_use_policy",
        "confidence",
        "notes",
    }
)


@dataclass(frozen=True)
class CreateGlossary:
    project_id: str | None
    name: str
    description: str | None
    source_language: str
    target_language: str
    scope: GlossaryScope
    domain: str | None
    is_default: bool


@dataclass(frozen=True)
class UpdateGlossary:
    expected_version: int
    values: dict[str, object]


@dataclass(frozen=True)
class CreateTerm:
    source_term: str
    rule_type: GlossaryRuleType
    target_term: str | None
    scope: GlossaryScope
    scope_reference_id: str | None
    priority: int
    case_sensitive: bool
    whole_word: bool
    match_mode: GlossaryMatchMode
    capitalization_policy: str
    inflection_policy: str
    first_use_policy: str
    confidence: float | None = 1.0
    notes: str | None = None


@dataclass(frozen=True)
class UpdateTerm:
    expected_revision: int
    values: dict[str, object]
    reason: str | None = None


class GlossaryService:
    def __init__(self, repository: GlossaryRepository) -> None:
        self._repository = repository

    def create_glossary(self, command: CreateGlossary) -> GlossaryRecord:
        return self._repository.create_glossary(
            glossary_id=_generate_id("gls_"),
            project_id=command.project_id,
            name=command.name,
            description=command.description,
            source_language=command.source_language,
            target_language=command.target_language,
            scope=command.scope,
            domain=command.domain,
            is_default=command.is_default,
            created_at=_utc_now(),
        )

    def get_glossary(self, glossary_id: str) -> GlossaryRecord:
        return self._repository.get_glossary(glossary_id)

    def list_glossaries(
        self,
        *,
        project_id: str | None = None,
        scope: GlossaryScope | None = None,
        status: GlossaryStatus | None = None,
        search: str | None = None,
    ) -> list[GlossaryRecord]:
        return self._repository.list_glossaries(
            project_id=project_id,
            scope=scope,
            status=status,
            search=search,
        )

    def update_glossary(self, glossary_id: str, command: UpdateGlossary) -> GlossaryRecord:
        _validate_update_fields(command.values, _GLOSSARY_UPDATE_FIELDS, "glossary")
        current = self._repository.get_glossary(glossary_id)
        return self._repository.update_glossary(
            glossary_id,
            expected_version=command.expected_version,
            name=_mapping_value(command.values, "name", current.name, str),
            description=_optional_string_mapping_value(
                command.values,
                "description",
                current.description,
            ),
            updated_at=_utc_now(),
        )

    def activate_glossary(self, glossary_id: str) -> GlossaryRecord:
        return self._repository.activate_glossary(glossary_id, updated_at=_utc_now())

    def deactivate_glossary(self, glossary_id: str) -> GlossaryRecord:
        return self._repository.deactivate_glossary(glossary_id, updated_at=_utc_now())

    def delete_glossary(self, glossary_id: str) -> None:
        self._repository.delete_glossary(glossary_id, deleted_at=_utc_now())

    def create_term(self, glossary_id: str, command: CreateTerm) -> TermRecord:
        return self._repository.create_term(
            term_id=_generate_id("trm_"),
            revision_id=_generate_id("grv_"),
            glossary_id=glossary_id,
            source_term=command.source_term,
            rule_type=command.rule_type,
            target_term=command.target_term,
            scope=command.scope,
            scope_reference_id=command.scope_reference_id,
            priority=command.priority,
            case_sensitive=command.case_sensitive,
            whole_word=command.whole_word,
            match_mode=command.match_mode,
            capitalization_policy=command.capitalization_policy,
            inflection_policy=command.inflection_policy,
            first_use_policy=command.first_use_policy,
            confidence=command.confidence,
            notes=command.notes,
            created_at=_utc_now(),
        )

    def get_term(self, term_id: str) -> TermRecord:
        return self._repository.get_term(term_id)

    def list_terms(
        self,
        glossary_id: str,
        *,
        search: str | None = None,
        rule_type: GlossaryRuleType | None = None,
        status: GlossaryTermStatus | None = None,
        source: str | None = None,
    ) -> list[TermRecord]:
        return self._repository.list_terms(
            glossary_id,
            search=search,
            rule_type=rule_type,
            status=status,
            source=source,
        )

    def update_term(self, term_id: str, command: UpdateTerm) -> TermRecord:
        _validate_update_fields(command.values, _TERM_UPDATE_FIELDS, "term")
        values = _database_term_values(command.values)
        return self._repository.update_term(
            term_id,
            expected_revision=command.expected_revision,
            revision_id=_generate_id("grv_"),
            revision_type=_revision_type(values),
            values=values,
            reason=command.reason,
            updated_at=_utc_now(),
        )

    def deactivate_term(self, term_id: str) -> TermRecord:
        return self._repository.deactivate_term(
            term_id,
            revision_id=_generate_id("grv_"),
            updated_at=_utc_now(),
        )

    def archive_term(self, term_id: str) -> TermRecord:
        return self._repository.archive_term(
            term_id,
            revision_id=_generate_id("grv_"),
            archived_at=_utc_now(),
        )

    def list_revisions(self, term_id: str) -> list[RevisionRecord]:
        return self._repository.list_revisions(term_id)


def _validate_update_fields(
    values: dict[str, object],
    allowed: frozenset[str],
    resource: str,
) -> None:
    if not values:
        raise InvalidGlossaryValueError(f"At least one {resource} field must be updated.")
    if not values.keys() <= allowed:
        raise InvalidGlossaryValueError(f"The {resource} update contains unsupported fields.")


def _mapping_value(
    values: dict[str, object],
    key: str,
    fallback: str,
    expected_type: type[str],
) -> str:
    value = values.get(key, fallback)
    if not isinstance(value, expected_type):
        raise InvalidGlossaryValueError(f"The {key} value is invalid.")
    return value


def _optional_string_mapping_value(
    values: dict[str, object],
    key: str,
    fallback: str | None,
) -> str | None:
    value = values.get(key, fallback)
    if value is not None and not isinstance(value, str):
        raise InvalidGlossaryValueError(f"The {key} value is invalid.")
    return value


def _database_term_values(values: dict[str, object]) -> dict[str, object]:
    result = dict(values)
    for key in ("rule_type", "scope", "match_mode"):
        value = result.get(key)
        if isinstance(value, StrEnum):
            result[key] = value.value
    for key in ("case_sensitive", "whole_word"):
        value = result.get(key)
        if isinstance(value, bool):
            result[key] = int(value)
    return result


def _revision_type(values: dict[str, object]) -> GlossaryRevisionType:
    fields = values.keys()
    if len(fields) != 1:
        return GlossaryRevisionType.EDIT_TERM
    field = next(iter(fields))
    if field in {"rule_type", "target_term"}:
        return GlossaryRevisionType.CHANGE_TARGET
    if field in {"scope", "scope_reference_id"}:
        return GlossaryRevisionType.CHANGE_SCOPE
    if field == "priority":
        return GlossaryRevisionType.CHANGE_PRIORITY
    if field in {
        "case_sensitive",
        "whole_word",
        "match_mode",
        "capitalization_policy",
        "inflection_policy",
        "first_use_policy",
    }:
        return GlossaryRevisionType.CHANGE_MATCHING_MODE
    return GlossaryRevisionType.EDIT_TERM


def _generate_id(prefix: str) -> str:
    return f"{prefix}{uuid4()}"


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")
