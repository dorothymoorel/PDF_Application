import json
import math
import unicodedata
from dataclasses import dataclass
from enum import StrEnum
from typing import Any, cast
from uuid import UUID

from sqlalchemy import func, select, update
from sqlalchemy.engine import CursorResult
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from transloka_core.database.models.glossary import (
    Glossary,
    GlossaryMatchMode,
    GlossaryRevision,
    GlossaryRevisionType,
    GlossaryRuleType,
    GlossaryScope,
    GlossaryTerm,
    TermOccurrence,
)


class GlossaryStatus(StrEnum):
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"


class GlossaryTermStatus(StrEnum):
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"
    ARCHIVED = "ARCHIVED"


class GlossaryRepositoryError(ValueError):
    pass


class InvalidGlossaryIdError(GlossaryRepositoryError):
    pass


class InvalidTermIdError(GlossaryRepositoryError):
    pass


class InvalidGlossaryValueError(GlossaryRepositoryError):
    pass


class TargetRequiredError(InvalidGlossaryValueError):
    pass


class GlossaryNotFoundError(GlossaryRepositoryError):
    pass


class TermNotFoundError(GlossaryRepositoryError):
    pass


class GlossaryAlreadyExistsError(GlossaryRepositoryError):
    pass


class DuplicateTermError(GlossaryRepositoryError):
    pass


class RevisionConflictError(GlossaryRepositoryError):
    def __init__(self, expected_revision: int, current_revision: int) -> None:
        super().__init__("The resource revision does not match.")
        self.expected_revision = expected_revision
        self.current_revision = current_revision


class InvalidGlossaryStateError(GlossaryRepositoryError):
    pass


class InvalidTermStateError(GlossaryRepositoryError):
    pass


class CorruptGlossaryError(GlossaryRepositoryError):
    pass


@dataclass(frozen=True)
class GlossaryRecord:
    id: str
    project_id: str | None
    name: str
    description: str | None
    source_language: str
    target_language: str
    scope: GlossaryScope
    domain: str | None
    status: GlossaryStatus
    version: int
    is_default: bool
    term_count: int
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class TermRecord:
    id: str
    glossary_id: str
    source_term: str
    normalized_source_term: str
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
    status: GlossaryTermStatus
    term_source: str
    confidence: float | None
    notes: str | None
    current_revision: int
    occurrence_count: int
    created_at: str
    updated_at: str


@dataclass(frozen=True)
class RevisionRecord:
    id: str
    term_id: str
    revision_number: int
    revision_type: GlossaryRevisionType
    previous_value: dict[str, object] | None
    new_value: dict[str, object]
    reason: str | None
    created_at: str


class GlossaryRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def create_glossary(
        self,
        *,
        glossary_id: str,
        project_id: str | None,
        name: str,
        description: str | None,
        source_language: str,
        target_language: str,
        scope: GlossaryScope,
        domain: str | None,
        is_default: bool,
        created_at: str,
    ) -> GlossaryRecord:
        validate_glossary_id(glossary_id)
        _validate_glossary_values(
            project_id=project_id,
            name=name,
            description=description,
            source_language=source_language,
            target_language=target_language,
            scope=scope,
            domain=domain,
        )
        if self._session.get(Glossary, glossary_id) is not None:
            raise GlossaryAlreadyExistsError("The glossary already exists.")
        duplicate = self._session.scalar(
            select(Glossary.id).where(
                Glossary.deleted_at.is_(None),
                Glossary.project_id.is_(project_id)
                if project_id is None
                else Glossary.project_id == project_id,
                Glossary.scope == scope.value,
                func.lower(Glossary.name) == name.casefold(),
            )
        )
        if duplicate is not None:
            raise GlossaryAlreadyExistsError("A glossary with the same identity exists.")

        row = Glossary(
            id=glossary_id,
            project_id=project_id,
            name=name,
            description=description,
            source_language=source_language,
            target_language=target_language,
            scope=scope.value,
            domain=domain,
            status=GlossaryStatus.ACTIVE.value,
            version=1,
            is_default=int(is_default),
            created_at=created_at,
            updated_at=created_at,
            deleted_at=None,
        )
        self._session.add(row)
        try:
            self._session.flush()
        except IntegrityError:
            raise InvalidGlossaryValueError("The glossary references invalid data.") from None
        return self._glossary_record(row)

    def get_glossary(self, glossary_id: str) -> GlossaryRecord:
        return self._glossary_record(self._glossary_row(glossary_id))

    def list_glossaries(
        self,
        *,
        project_id: str | None = None,
        scope: GlossaryScope | None = None,
        status: GlossaryStatus | None = None,
        search: str | None = None,
    ) -> list[GlossaryRecord]:
        statement = select(Glossary).where(Glossary.deleted_at.is_(None))
        if project_id is not None:
            statement = statement.where(Glossary.project_id == project_id)
        if scope is not None:
            statement = statement.where(Glossary.scope == scope.value)
        if status is not None:
            statement = statement.where(Glossary.status == status.value)
        if search is not None:
            candidate = f"%{_escape_like(search.casefold())}%"
            statement = statement.where(
                func.lower(Glossary.name).like(candidate, escape="\\")
                | func.lower(func.coalesce(Glossary.description, "")).like(
                    candidate,
                    escape="\\",
                )
            )
        statement = statement.order_by(Glossary.updated_at.desc(), Glossary.id)
        return [self._glossary_record(row) for row in self._session.scalars(statement)]

    def update_glossary(
        self,
        glossary_id: str,
        *,
        expected_version: int,
        name: str,
        description: str | None,
        updated_at: str,
    ) -> GlossaryRecord:
        validate_glossary_id(glossary_id)
        _validate_revision(expected_version)
        _validate_text(name, "Glossary name")
        _validate_optional_text(description, "Glossary description")
        result = cast(
            CursorResult[Any],
            self._session.execute(
                update(Glossary)
                .where(
                    Glossary.id == glossary_id,
                    Glossary.deleted_at.is_(None),
                    Glossary.version == expected_version,
                )
                .values(
                    name=name,
                    description=description,
                    version=Glossary.version + 1,
                    updated_at=updated_at,
                )
            ),
        )
        if result.rowcount == 0:
            self._raise_glossary_update_failure(glossary_id, expected_version)
        self._session.flush()
        self._session.expire_all()
        return self.get_glossary(glossary_id)

    def activate_glossary(self, glossary_id: str, *, updated_at: str) -> GlossaryRecord:
        row = self._glossary_row(glossary_id)
        if row.status == GlossaryStatus.ACTIVE.value:
            raise InvalidGlossaryStateError("The glossary is already active.")
        row.status = GlossaryStatus.ACTIVE.value
        row.version += 1
        row.updated_at = updated_at
        self._session.flush()
        return self._glossary_record(row)

    def deactivate_glossary(self, glossary_id: str, *, updated_at: str) -> GlossaryRecord:
        row = self._glossary_row(glossary_id)
        if row.status == GlossaryStatus.INACTIVE.value:
            raise InvalidGlossaryStateError("The glossary is already inactive.")
        row.status = GlossaryStatus.INACTIVE.value
        row.version += 1
        row.updated_at = updated_at
        self._session.flush()
        return self._glossary_record(row)

    def delete_glossary(self, glossary_id: str, *, deleted_at: str) -> None:
        row = self._glossary_row(glossary_id)
        row.status = GlossaryStatus.INACTIVE.value
        row.version += 1
        row.updated_at = deleted_at
        row.deleted_at = deleted_at
        self._session.flush()

    def create_term(
        self,
        *,
        term_id: str,
        revision_id: str,
        glossary_id: str,
        source_term: str,
        rule_type: GlossaryRuleType,
        target_term: str | None,
        scope: GlossaryScope,
        scope_reference_id: str | None,
        priority: int,
        case_sensitive: bool,
        whole_word: bool,
        match_mode: GlossaryMatchMode,
        capitalization_policy: str,
        inflection_policy: str,
        first_use_policy: str,
        confidence: float | None,
        notes: str | None,
        created_at: str,
    ) -> TermRecord:
        validate_term_id(term_id)
        _validate_prefixed_id(revision_id, "grv_", InvalidTermIdError)
        glossary = self._mutable_glossary_row(glossary_id)
        normalized_source_term = normalize_source_term(source_term)
        _validate_term_values(
            source_term=source_term,
            rule_type=rule_type,
            target_term=target_term,
            scope=scope,
            scope_reference_id=scope_reference_id,
            priority=priority,
            case_sensitive=case_sensitive,
            whole_word=whole_word,
            match_mode=match_mode,
            capitalization_policy=capitalization_policy,
            inflection_policy=inflection_policy,
            first_use_policy=first_use_policy,
            confidence=confidence,
            notes=notes,
        )
        row = GlossaryTerm(
            id=term_id,
            glossary_id=glossary_id,
            source_term=source_term,
            normalized_source_term=normalized_source_term,
            rule_type=rule_type.value,
            target_term=target_term,
            scope=scope.value,
            scope_reference_id=scope_reference_id,
            priority=priority,
            case_sensitive=int(case_sensitive),
            whole_word=int(whole_word),
            match_mode=match_mode.value,
            capitalization_policy=capitalization_policy,
            inflection_policy=inflection_policy,
            first_use_policy=first_use_policy,
            status=GlossaryTermStatus.ACTIVE.value,
            term_source="USER_CREATED",
            confidence=confidence,
            notes=notes,
            created_at=created_at,
            updated_at=created_at,
        )
        self._session.add(row)
        try:
            self._session.flush()
        except IntegrityError as exc:
            if "uq_glossary_terms_identity" in str(exc.orig):
                raise DuplicateTermError("The active glossary term already exists.") from None
            raise InvalidGlossaryValueError("The glossary term references invalid data.") from None

        revision = GlossaryRevision(
            id=revision_id,
            term_id=term_id,
            revision_number=1,
            revision_type=GlossaryRevisionType.CREATE_TERM.value,
            previous_value_json=None,
            new_value_json=_term_json(row),
            reason=None,
            created_at=created_at,
        )
        self._session.add(revision)
        self._bump_glossary(glossary, created_at)
        self._session.flush()
        return self._term_record(row, current_revision=1)

    def get_term(self, term_id: str) -> TermRecord:
        row = self._term_row(term_id)
        return self._term_record(row)

    def list_terms(
        self,
        glossary_id: str,
        *,
        search: str | None = None,
        rule_type: GlossaryRuleType | None = None,
        status: GlossaryTermStatus | None = None,
        source: str | None = None,
    ) -> list[TermRecord]:
        self._glossary_row(glossary_id)
        statement = select(GlossaryTerm).where(GlossaryTerm.glossary_id == glossary_id)
        if status is None:
            statement = statement.where(GlossaryTerm.status != GlossaryTermStatus.ARCHIVED.value)
        else:
            statement = statement.where(GlossaryTerm.status == status.value)
        if search is not None:
            candidate = f"%{_escape_like(normalize_source_term(search))}%"
            statement = statement.where(
                GlossaryTerm.normalized_source_term.like(candidate, escape="\\")
            )
        if rule_type is not None:
            statement = statement.where(GlossaryTerm.rule_type == rule_type.value)
        if source is not None:
            _validate_text(source, "Term source")
            statement = statement.where(GlossaryTerm.term_source == source)
        statement = statement.order_by(
            GlossaryTerm.priority.desc(),
            GlossaryTerm.normalized_source_term,
            GlossaryTerm.id,
        )
        return [self._term_record(row) for row in self._session.scalars(statement)]

    def update_term(
        self,
        term_id: str,
        *,
        expected_revision: int,
        revision_id: str,
        revision_type: GlossaryRevisionType,
        values: dict[str, object],
        reason: str | None,
        updated_at: str,
    ) -> TermRecord:
        row = self._term_row(term_id)
        if row.status == GlossaryTermStatus.ARCHIVED.value:
            raise InvalidTermStateError("An archived term cannot be changed.")
        current_revision = self._current_revision(term_id)
        _validate_revision(expected_revision)
        if current_revision != expected_revision:
            raise RevisionConflictError(expected_revision, current_revision)
        if not values:
            raise InvalidGlossaryValueError("At least one term field must be updated.")

        next_values = _term_values(row)
        next_values.update(values)
        _validate_term_values_from_mapping(next_values)
        next_values["normalized_source_term"] = normalize_source_term(
            _string_value(next_values, "source_term")
        )
        if all(getattr(row, field) == value for field, value in next_values.items()):
            raise InvalidGlossaryValueError("The term update does not change any values.")

        _validate_prefixed_id(revision_id, "grv_", InvalidTermIdError)
        revision_number = current_revision + 1
        revision = GlossaryRevision(
            id=revision_id,
            term_id=term_id,
            revision_number=revision_number,
            revision_type=revision_type.value,
            previous_value_json=_term_json(row),
            new_value_json=_canonical_json(next_values),
            reason=reason,
            created_at=updated_at,
        )
        self._session.add(revision)
        try:
            self._session.flush()
        except IntegrityError:
            latest = self._current_revision_after_rollback_required(term_id, current_revision)
            raise RevisionConflictError(expected_revision, latest) from None

        for field, value in next_values.items():
            setattr(row, field, value)
        row.updated_at = updated_at
        glossary = self._mutable_glossary_row(row.glossary_id)
        self._bump_glossary(glossary, updated_at)
        try:
            self._session.flush()
        except IntegrityError as exc:
            if "uq_glossary_terms_identity" in str(exc.orig):
                raise DuplicateTermError("The active glossary term already exists.") from None
            raise InvalidGlossaryValueError("The glossary term update is invalid.") from None
        return self._term_record(row, current_revision=revision_number)

    def archive_term(
        self,
        term_id: str,
        *,
        revision_id: str,
        archived_at: str,
    ) -> TermRecord:
        row = self._term_row(term_id)
        if row.status == GlossaryTermStatus.ARCHIVED.value:
            raise InvalidTermStateError("The term is already archived.")
        return self.update_term(
            term_id,
            expected_revision=self._current_revision(term_id),
            revision_id=revision_id,
            revision_type=GlossaryRevisionType.DEACTIVATE,
            values={"status": GlossaryTermStatus.ARCHIVED.value},
            reason="Archived by user.",
            updated_at=archived_at,
        )

    def deactivate_term(
        self,
        term_id: str,
        *,
        revision_id: str,
        updated_at: str,
    ) -> TermRecord:
        row = self._term_row(term_id)
        if row.status != GlossaryTermStatus.ACTIVE.value:
            raise InvalidTermStateError("Only an active term can be deactivated.")
        return self.update_term(
            term_id,
            expected_revision=self._current_revision(term_id),
            revision_id=revision_id,
            revision_type=GlossaryRevisionType.DEACTIVATE,
            values={"status": GlossaryTermStatus.INACTIVE.value},
            reason=None,
            updated_at=updated_at,
        )

    def list_revisions(self, term_id: str) -> list[RevisionRecord]:
        self._term_row(term_id)
        revisions = self._session.scalars(
            select(GlossaryRevision)
            .where(GlossaryRevision.term_id == term_id)
            .order_by(GlossaryRevision.revision_number)
        )
        return [_revision_record(row) for row in revisions]

    def _glossary_row(self, glossary_id: str) -> Glossary:
        validate_glossary_id(glossary_id)
        row = self._session.get(Glossary, glossary_id)
        if row is None or row.deleted_at is not None:
            raise GlossaryNotFoundError("The glossary was not found.")
        return row

    def _mutable_glossary_row(self, glossary_id: str) -> Glossary:
        row = self._glossary_row(glossary_id)
        if row.status != GlossaryStatus.ACTIVE.value:
            raise InvalidGlossaryStateError("The glossary is not active.")
        return row

    def _term_row(self, term_id: str) -> GlossaryTerm:
        validate_term_id(term_id)
        row = self._session.get(GlossaryTerm, term_id)
        if row is None:
            raise TermNotFoundError("The glossary term was not found.")
        glossary = self._session.get(Glossary, row.glossary_id)
        if glossary is None or glossary.deleted_at is not None:
            raise TermNotFoundError("The glossary term was not found.")
        return row

    def _glossary_record(self, row: Glossary) -> GlossaryRecord:
        try:
            term_count = self._session.scalar(
                select(func.count(GlossaryTerm.id)).where(
                    GlossaryTerm.glossary_id == row.id,
                    GlossaryTerm.status.not_in((GlossaryTermStatus.ARCHIVED.value, "REJECTED")),
                )
            )
            return GlossaryRecord(
                id=row.id,
                project_id=row.project_id,
                name=row.name,
                description=row.description,
                source_language=row.source_language,
                target_language=row.target_language,
                scope=GlossaryScope(row.scope),
                domain=row.domain,
                status=GlossaryStatus(row.status),
                version=row.version,
                is_default=bool(row.is_default),
                term_count=term_count or 0,
                created_at=row.created_at,
                updated_at=row.updated_at,
            )
        except (TypeError, ValueError):
            raise CorruptGlossaryError("The stored glossary is invalid.") from None

    def _term_record(
        self,
        row: GlossaryTerm,
        *,
        current_revision: int | None = None,
    ) -> TermRecord:
        try:
            occurrence_count = self._session.scalar(
                select(func.count(TermOccurrence.id)).where(TermOccurrence.term_id == row.id)
            )
            return TermRecord(
                id=row.id,
                glossary_id=row.glossary_id,
                source_term=row.source_term,
                normalized_source_term=row.normalized_source_term,
                rule_type=GlossaryRuleType(row.rule_type),
                target_term=row.target_term,
                scope=GlossaryScope(row.scope),
                scope_reference_id=row.scope_reference_id,
                priority=row.priority,
                case_sensitive=bool(row.case_sensitive),
                whole_word=bool(row.whole_word),
                match_mode=GlossaryMatchMode(row.match_mode),
                capitalization_policy=row.capitalization_policy,
                inflection_policy=row.inflection_policy,
                first_use_policy=row.first_use_policy,
                status=GlossaryTermStatus(row.status),
                term_source=row.term_source,
                confidence=row.confidence,
                notes=row.notes,
                current_revision=(
                    current_revision
                    if current_revision is not None
                    else self._current_revision(row.id)
                ),
                occurrence_count=occurrence_count or 0,
                created_at=row.created_at,
                updated_at=row.updated_at,
            )
        except (TypeError, ValueError):
            raise CorruptGlossaryError("The stored glossary term is invalid.") from None

    def _current_revision(self, term_id: str) -> int:
        revision = self._session.scalar(
            select(func.max(GlossaryRevision.revision_number)).where(
                GlossaryRevision.term_id == term_id
            )
        )
        if not isinstance(revision, int) or revision < 1:
            raise CorruptGlossaryError("The glossary term has no valid revision history.")
        return revision

    def _current_revision_after_rollback_required(
        self,
        _term_id: str,
        fallback: int,
    ) -> int:
        # A failed flush makes the current SQLAlchemy transaction unreadable.
        # The caller's transaction boundary will roll it back; the stable fallback
        # still communicates that the submitted revision is stale.
        return fallback + 1

    def _raise_glossary_update_failure(self, glossary_id: str, expected_version: int) -> None:
        row = self._session.get(Glossary, glossary_id)
        if row is None or row.deleted_at is not None:
            raise GlossaryNotFoundError("The glossary was not found.")
        raise RevisionConflictError(expected_version, row.version)

    @staticmethod
    def _bump_glossary(row: Glossary, updated_at: str) -> None:
        row.version += 1
        row.updated_at = updated_at


def validate_glossary_id(value: str) -> None:
    _validate_prefixed_id(value, "gls_", InvalidGlossaryIdError)


def validate_term_id(value: str) -> None:
    _validate_prefixed_id(value, "trm_", InvalidTermIdError)


def normalize_source_term(value: str) -> str:
    _validate_text(value, "Source term")
    return " ".join(unicodedata.normalize("NFKC", value).split()).casefold()


def _validate_prefixed_id(
    value: str,
    prefix: str,
    error_type: type[GlossaryRepositoryError],
) -> None:
    if not isinstance(value, str) or not value.startswith(prefix):
        raise error_type("The resource identifier is invalid.")
    try:
        parsed = UUID(value[len(prefix) :])
    except (ValueError, AttributeError):
        raise error_type("The resource identifier is invalid.") from None
    if value != f"{prefix}{parsed}":
        raise error_type("The resource identifier is invalid.")


def _validate_glossary_values(
    *,
    project_id: str | None,
    name: str,
    description: str | None,
    source_language: str,
    target_language: str,
    scope: GlossaryScope,
    domain: str | None,
) -> None:
    _validate_optional_prefixed_id(project_id, "prj_")
    _validate_text(name, "Glossary name")
    _validate_optional_text(description, "Glossary description")
    _validate_text(source_language, "Source language")
    _validate_text(target_language, "Target language")
    _validate_enum(scope, GlossaryScope)
    _validate_optional_text(domain, "Glossary domain")
    if scope is GlossaryScope.PROJECT and project_id is None:
        raise InvalidGlossaryValueError("A project glossary requires a project identifier.")
    if scope is GlossaryScope.DOMAIN and domain is None:
        raise InvalidGlossaryValueError("A domain glossary requires a domain.")


def _validate_term_values(
    *,
    source_term: str,
    rule_type: GlossaryRuleType,
    target_term: str | None,
    scope: GlossaryScope,
    scope_reference_id: str | None,
    priority: int,
    case_sensitive: bool,
    whole_word: bool,
    match_mode: GlossaryMatchMode,
    capitalization_policy: str,
    inflection_policy: str,
    first_use_policy: str,
    confidence: float | None,
    notes: str | None,
) -> None:
    _validate_text(source_term, "Source term")
    _validate_enum(rule_type, GlossaryRuleType)
    _validate_optional_text(target_term, "Target term", allow_empty=False)
    if rule_type is GlossaryRuleType.TRANSLATE_AS and target_term is None:
        raise TargetRequiredError("TRANSLATE_AS requires a target term.")
    _validate_enum(scope, GlossaryScope)
    _validate_optional_text(scope_reference_id, "Scope reference", allow_empty=False)
    if (
        scope
        in {
            GlossaryScope.PROJECT,
            GlossaryScope.DOCUMENT,
            GlossaryScope.SECTION,
            GlossaryScope.PAGE,
            GlossaryScope.SEGMENT,
        }
        and scope_reference_id is None
    ):
        raise InvalidGlossaryValueError("The selected scope requires a reference identifier.")
    if isinstance(priority, bool) or not isinstance(priority, int) or priority < 0:
        raise InvalidGlossaryValueError("Term priority must be a non-negative integer.")
    if not isinstance(case_sensitive, bool) or not isinstance(whole_word, bool):
        raise InvalidGlossaryValueError("Term matching flags must be booleans.")
    _validate_enum(match_mode, GlossaryMatchMode)
    _validate_text(capitalization_policy, "Capitalization policy")
    _validate_text(inflection_policy, "Inflection policy")
    _validate_text(first_use_policy, "First-use policy")
    if confidence is not None and (
        isinstance(confidence, bool)
        or not isinstance(confidence, (int, float))
        or not math.isfinite(confidence)
        or not 0.0 <= confidence <= 1.0
    ):
        raise InvalidGlossaryValueError("Term confidence must be between zero and one.")
    _validate_optional_text(notes, "Term notes")


def _validate_term_values_from_mapping(values: dict[str, object]) -> None:
    try:
        _validate_term_values(
            source_term=_string_value(values, "source_term"),
            rule_type=GlossaryRuleType(_string_value(values, "rule_type")),
            target_term=_optional_string_value(values, "target_term"),
            scope=GlossaryScope(_string_value(values, "scope")),
            scope_reference_id=_optional_string_value(values, "scope_reference_id"),
            priority=_int_value(values, "priority"),
            case_sensitive=_bool_value(values, "case_sensitive"),
            whole_word=_bool_value(values, "whole_word"),
            match_mode=GlossaryMatchMode(_string_value(values, "match_mode")),
            capitalization_policy=_string_value(values, "capitalization_policy"),
            inflection_policy=_string_value(values, "inflection_policy"),
            first_use_policy=_string_value(values, "first_use_policy"),
            confidence=_optional_float_value(values, "confidence"),
            notes=_optional_string_value(values, "notes"),
        )
    except ValueError:
        raise InvalidGlossaryValueError("The glossary term values are invalid.") from None


def _term_values(row: GlossaryTerm) -> dict[str, object]:
    return {
        "source_term": row.source_term,
        "normalized_source_term": row.normalized_source_term,
        "rule_type": row.rule_type,
        "target_term": row.target_term,
        "scope": row.scope,
        "scope_reference_id": row.scope_reference_id,
        "priority": row.priority,
        "case_sensitive": row.case_sensitive,
        "whole_word": row.whole_word,
        "match_mode": row.match_mode,
        "capitalization_policy": row.capitalization_policy,
        "inflection_policy": row.inflection_policy,
        "first_use_policy": row.first_use_policy,
        "status": row.status,
        "term_source": row.term_source,
        "confidence": row.confidence,
        "notes": row.notes,
    }


def _term_json(row: GlossaryTerm) -> str:
    return _canonical_json(_term_values(row))


def _canonical_json(value: dict[str, object]) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _revision_record(row: GlossaryRevision) -> RevisionRecord:
    try:
        previous_value = (
            json.loads(row.previous_value_json) if row.previous_value_json is not None else None
        )
        new_value = json.loads(row.new_value_json)
        if previous_value is not None and not isinstance(previous_value, dict):
            raise ValueError
        if not isinstance(new_value, dict):
            raise ValueError
        return RevisionRecord(
            id=row.id,
            term_id=row.term_id,
            revision_number=row.revision_number,
            revision_type=GlossaryRevisionType(row.revision_type),
            previous_value=previous_value,
            new_value=new_value,
            reason=row.reason,
            created_at=row.created_at,
        )
    except (TypeError, ValueError, json.JSONDecodeError):
        raise CorruptGlossaryError("The stored glossary revision is invalid.") from None


def _validate_revision(value: int) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 1:
        raise InvalidGlossaryValueError("The expected revision is invalid.")


def _validate_text(value: str, label: str) -> None:
    if (
        not isinstance(value, str)
        or not value.strip()
        or value != value.strip()
        or not value.isprintable()
    ):
        raise InvalidGlossaryValueError(f"{label} is invalid.")


def _validate_optional_text(
    value: str | None,
    label: str,
    *,
    allow_empty: bool = True,
) -> None:
    if value is None:
        return
    if not isinstance(value, str) or not value.isprintable() or value != value.strip():
        raise InvalidGlossaryValueError(f"{label} is invalid.")
    if not allow_empty and not value:
        raise InvalidGlossaryValueError(f"{label} is invalid.")


def _validate_optional_prefixed_id(value: str | None, prefix: str) -> None:
    if value is None:
        return
    try:
        _validate_prefixed_id(value, prefix, InvalidGlossaryValueError)
    except InvalidGlossaryValueError:
        raise


def _validate_enum(value: object, enum_type: type[StrEnum]) -> None:
    if not isinstance(value, enum_type):
        raise InvalidGlossaryValueError("The glossary enum value is invalid.")


def _string_value(values: dict[str, object], key: str) -> str:
    value = values[key]
    if not isinstance(value, str):
        raise ValueError
    return value


def _optional_string_value(values: dict[str, object], key: str) -> str | None:
    value = values[key]
    if value is not None and not isinstance(value, str):
        raise ValueError
    return value


def _int_value(values: dict[str, object], key: str) -> int:
    value = values[key]
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError
    return value


def _bool_value(values: dict[str, object], key: str) -> bool:
    value = values[key]
    if isinstance(value, bool):
        return value
    if isinstance(value, int) and value in (0, 1):
        return bool(value)
    raise ValueError


def _optional_float_value(values: dict[str, object], key: str) -> float | None:
    value = values[key]
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError
    return float(value)


def _escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
