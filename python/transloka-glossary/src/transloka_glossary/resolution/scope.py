from collections.abc import Iterable
from dataclasses import dataclass

from transloka_core.database.models.glossary import GlossaryRuleType, GlossaryScope

from transloka_glossary.matching import GlossaryMatch

_SCOPE_PRIORITY = {
    GlossaryScope.SYSTEM: 0,
    GlossaryScope.DOMAIN: 1,
    GlossaryScope.USER: 2,
    GlossaryScope.PROJECT: 3,
    GlossaryScope.DOCUMENT: 4,
    GlossaryScope.SECTION: 5,
    GlossaryScope.PAGE: 6,
    GlossaryScope.SEGMENT: 7,
}
_REFERENCED_SCOPES = frozenset(
    {
        GlossaryScope.PROJECT,
        GlossaryScope.DOCUMENT,
        GlossaryScope.SECTION,
        GlossaryScope.PAGE,
        GlossaryScope.SEGMENT,
    }
)
_EQUAL_PRIORITY_CONFLICT = "EQUAL_PRIORITY_CONFLICT"


class InvalidScopeResolutionError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class ScopeContext:
    project_id: str | None = None
    document_id: str | None = None
    section_id: str | None = None
    page_id: str | None = None
    segment_id: str | None = None
    domain: str | None = None
    personal_scope_reference_id: str | None = None

    def __post_init__(self) -> None:
        for value in (
            self.project_id,
            self.document_id,
            self.section_id,
            self.page_id,
            self.segment_id,
            self.domain,
            self.personal_scope_reference_id,
        ):
            _validate_optional_reference(value)


@dataclass(frozen=True, slots=True)
class ScopedGlossaryMatch:
    match: GlossaryMatch
    scope: GlossaryScope
    scope_reference_id: str | None
    priority: int
    rule_type: GlossaryRuleType
    target_term: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.match, GlossaryMatch):
            raise InvalidScopeResolutionError("A scoped rule requires a glossary match.")
        if not isinstance(self.scope, GlossaryScope):
            raise InvalidScopeResolutionError("The glossary scope is invalid.")
        if (
            isinstance(self.priority, bool)
            or not isinstance(self.priority, int)
            or self.priority < 0
        ):
            raise InvalidScopeResolutionError("Glossary priority must be a non-negative integer.")
        if not isinstance(self.rule_type, GlossaryRuleType):
            raise InvalidScopeResolutionError("The glossary rule type is invalid.")
        _validate_optional_reference(self.scope_reference_id)
        if self.scope in _REFERENCED_SCOPES and self.scope_reference_id is None:
            raise InvalidScopeResolutionError("The selected scope requires a reference identifier.")
        if self.scope is GlossaryScope.SYSTEM and self.scope_reference_id is not None:
            raise InvalidScopeResolutionError("System scope cannot have a reference identifier.")
        if self.target_term is not None and (
            not isinstance(self.target_term, str)
            or not self.target_term.strip()
            or self.target_term != self.target_term.strip()
            or not self.target_term.isprintable()
        ):
            raise InvalidScopeResolutionError("The target term is invalid.")
        if self.rule_type is GlossaryRuleType.TRANSLATE_AS and self.target_term is None:
            raise InvalidScopeResolutionError("TRANSLATE_AS requires a target term.")


@dataclass(frozen=True, slots=True)
class ResolutionWarning:
    code: str
    message: str
    term_ids: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ResolutionResult:
    winner: ScopedGlossaryMatch | None
    warnings: tuple[ResolutionWarning, ...]
    considered: tuple[ScopedGlossaryMatch, ...]


class ScopeResolver:
    def resolve(
        self,
        candidates: Iterable[ScopedGlossaryMatch],
        context: ScopeContext,
    ) -> ResolutionResult:
        if not isinstance(context, ScopeContext):
            raise InvalidScopeResolutionError("Scope resolution requires a valid context.")

        materialized = tuple(candidates)
        if not all(isinstance(candidate, ScopedGlossaryMatch) for candidate in materialized):
            raise InvalidScopeResolutionError(
                "Every scope resolution candidate must be a ScopedGlossaryMatch."
            )
        _validate_candidate_set(materialized)

        considered = tuple(
            sorted(
                (candidate for candidate in materialized if _applies(candidate, context)),
                key=_candidate_order,
            )
        )
        if not considered:
            return ResolutionResult(winner=None, warnings=(), considered=())

        winning_scope_priority = max(scope_priority(candidate.scope) for candidate in considered)
        scoped = tuple(
            candidate
            for candidate in considered
            if scope_priority(candidate.scope) == winning_scope_priority
        )
        winning_rule_priority = max(candidate.priority for candidate in scoped)
        finalists = tuple(
            candidate for candidate in scoped if candidate.priority == winning_rule_priority
        )

        if len({_behavior(candidate) for candidate in finalists}) > 1:
            warning = ResolutionWarning(
                code=_EQUAL_PRIORITY_CONFLICT,
                message=(
                    "Multiple glossary rules have equal effective priority and "
                    "incompatible behavior."
                ),
                term_ids=tuple(sorted(candidate.match.term_id for candidate in finalists)),
            )
            return ResolutionResult(winner=None, warnings=(warning,), considered=considered)

        return ResolutionResult(winner=finalists[0], warnings=(), considered=considered)


def scope_priority(scope: GlossaryScope) -> int:
    if not isinstance(scope, GlossaryScope):
        raise InvalidScopeResolutionError("The glossary scope is invalid.")
    return _SCOPE_PRIORITY[scope]


def _validate_candidate_set(candidates: tuple[ScopedGlossaryMatch, ...]) -> None:
    term_ids = [candidate.match.term_id for candidate in candidates]
    if len(term_ids) != len(set(term_ids)):
        raise InvalidScopeResolutionError("Glossary term identifiers must be unique.")
    occurrences = {
        (
            candidate.match.start_offset,
            candidate.match.end_offset,
            candidate.match.matched_text,
        )
        for candidate in candidates
    }
    if len(occurrences) > 1:
        raise InvalidScopeResolutionError(
            "Scope resolution candidates must describe one source occurrence."
        )


def _applies(candidate: ScopedGlossaryMatch, context: ScopeContext) -> bool:
    reference = candidate.scope_reference_id
    if candidate.scope is GlossaryScope.SYSTEM:
        return True
    if candidate.scope is GlossaryScope.DOMAIN:
        return reference is None or reference == context.domain
    if candidate.scope is GlossaryScope.USER:
        return reference is None or reference == context.personal_scope_reference_id

    context_reference = {
        GlossaryScope.PROJECT: context.project_id,
        GlossaryScope.DOCUMENT: context.document_id,
        GlossaryScope.SECTION: context.section_id,
        GlossaryScope.PAGE: context.page_id,
        GlossaryScope.SEGMENT: context.segment_id,
    }[candidate.scope]
    return reference == context_reference


def _behavior(candidate: ScopedGlossaryMatch) -> tuple[GlossaryRuleType, str | None]:
    return candidate.rule_type, candidate.target_term


def _candidate_order(candidate: ScopedGlossaryMatch) -> tuple[object, ...]:
    return (
        -scope_priority(candidate.scope),
        -candidate.priority,
        candidate.match.term_id,
        candidate.rule_type.value,
        candidate.target_term or "",
    )


def _validate_optional_reference(value: str | None) -> None:
    if value is not None and (
        not isinstance(value, str)
        or not value.strip()
        or value != value.strip()
        or not value.isprintable()
    ):
        raise InvalidScopeResolutionError("Scope references must be valid strings.")
