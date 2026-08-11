from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum
from itertools import combinations

from transloka_core.database.models.glossary import GlossaryRuleType, GlossaryScope

from transloka_glossary.resolution import scope_priority

_REFERENCED_SCOPES = frozenset(
    {
        GlossaryScope.PROJECT,
        GlossaryScope.DOCUMENT,
        GlossaryScope.SECTION,
        GlossaryScope.PAGE,
        GlossaryScope.SEGMENT,
    }
)
_OPTIONALLY_REFERENCED_SCOPES = frozenset({GlossaryScope.DOMAIN, GlossaryScope.USER})


class ConflictType(StrEnum):
    TARGET_CONFLICT = "TARGET_CONFLICT"
    RULE_CONFLICT = "RULE_CONFLICT"
    SCOPE_CONFLICT = "SCOPE_CONFLICT"
    CONTEXT_CONFLICT = "CONTEXT_CONFLICT"


class ConflictResolutionStatus(StrEnum):
    AUTO_RESOLVED = "AUTO_RESOLVED"
    UNRESOLVED = "UNRESOLVED"


class InvalidConflictRuleError(ValueError):
    pass


@dataclass(frozen=True, order=True, slots=True)
class ContextCondition:
    key: str
    value: str

    def __post_init__(self) -> None:
        _validate_required_text(self.key, "Context condition key")
        _validate_required_text(self.value, "Context condition value")


@dataclass(frozen=True, slots=True)
class ConflictRule:
    term_id: str
    normalized_source_term: str
    rule_type: GlossaryRuleType
    scope: GlossaryScope
    scope_reference_id: str | None = None
    priority: int = 0
    target_term: str | None = None
    conditions: tuple[ContextCondition, ...] = ()
    active: bool = True

    def __post_init__(self) -> None:
        _validate_required_text(self.term_id, "Glossary term identifier")
        _validate_required_text(self.normalized_source_term, "Normalized source term")
        if not isinstance(self.rule_type, GlossaryRuleType):
            raise InvalidConflictRuleError("The glossary rule type is invalid.")
        if not isinstance(self.scope, GlossaryScope):
            raise InvalidConflictRuleError("The glossary scope is invalid.")
        if (
            isinstance(self.priority, bool)
            or not isinstance(self.priority, int)
            or self.priority < 0
        ):
            raise InvalidConflictRuleError("Glossary priority must be a non-negative integer.")
        if not isinstance(self.active, bool):
            raise InvalidConflictRuleError("Glossary active state must be a boolean.")
        _validate_scope_reference(self.scope, self.scope_reference_id)
        if self.target_term is not None:
            _validate_required_text(self.target_term, "Target term")
        if self.rule_type is GlossaryRuleType.TRANSLATE_AS and self.target_term is None:
            raise InvalidConflictRuleError("TRANSLATE_AS requires a target term.")
        if not isinstance(self.conditions, tuple) or not all(
            isinstance(condition, ContextCondition) for condition in self.conditions
        ):
            raise InvalidConflictRuleError(
                "Context conditions must be a tuple of ContextCondition values."
            )
        keys = [condition.key for condition in self.conditions]
        if len(keys) != len(set(keys)):
            raise InvalidConflictRuleError("Context condition keys must be unique per rule.")
        object.__setattr__(self, "conditions", tuple(sorted(self.conditions)))


@dataclass(frozen=True, slots=True)
class DetectedConflict:
    conflict_type: ConflictType
    normalized_source_term: str
    term_ids: tuple[str, str]
    resolution_status: ConflictResolutionStatus
    winner_term_id: str | None
    explanation: str

    @property
    def blocking(self) -> bool:
        return self.resolution_status is ConflictResolutionStatus.UNRESOLVED


class TranslationReadinessBlockedError(RuntimeError):
    def __init__(self, conflicts: tuple[DetectedConflict, ...]) -> None:
        super().__init__(
            f"Translation readiness is blocked by {len(conflicts)} unresolved glossary conflict(s)."
        )
        self.conflicts = conflicts


@dataclass(frozen=True, slots=True)
class ConflictDetectionResult:
    conflicts: tuple[DetectedConflict, ...]

    @property
    def blocking_conflicts(self) -> tuple[DetectedConflict, ...]:
        return tuple(conflict for conflict in self.conflicts if conflict.blocking)

    @property
    def translation_ready(self) -> bool:
        return not self.blocking_conflicts

    def require_translation_ready(self) -> None:
        blocking = self.blocking_conflicts
        if blocking:
            raise TranslationReadinessBlockedError(blocking)


class ConflictDetector:
    def detect(self, rules: Iterable[ConflictRule]) -> ConflictDetectionResult:
        materialized = tuple(rules)
        if not all(isinstance(rule, ConflictRule) for rule in materialized):
            raise InvalidConflictRuleError("Every conflict candidate must be a ConflictRule.")
        identifiers = [rule.term_id for rule in materialized]
        if len(identifiers) != len(set(identifiers)):
            raise InvalidConflictRuleError("Glossary term identifiers must be unique.")

        grouped: dict[str, list[ConflictRule]] = defaultdict(list)
        for rule in sorted((rule for rule in materialized if rule.active), key=_rule_order):
            grouped[rule.normalized_source_term].append(rule)

        conflicts: list[DetectedConflict] = []
        for normalized_source_term in sorted(grouped):
            source_rules = tuple(grouped[normalized_source_term])
            for first, second in combinations(source_rules, 2):
                conflict = _detect_pair(first, second, source_rules)
                if conflict is not None:
                    conflicts.append(conflict)

        return ConflictDetectionResult(conflicts=tuple(sorted(conflicts, key=_conflict_order)))


def _detect_pair(
    first: ConflictRule,
    second: ConflictRule,
    source_rules: tuple[ConflictRule, ...],
) -> DetectedConflict | None:
    if _behavior(first) == _behavior(second):
        return None
    if not _scope_contexts_overlap(first, second) or not _conditions_overlap(first, second):
        return None

    conflict_type = _classify_conflict(first, second)
    first_precedence = _precedence(first)
    second_precedence = _precedence(second)
    if first_precedence == second_precedence:
        if _has_common_dominating_rule(first, second, source_rules):
            return None
        resolution_status = ConflictResolutionStatus.UNRESOLVED
        winner_term_id = None
    else:
        resolution_status = ConflictResolutionStatus.AUTO_RESOLVED
        winner_term_id = first.term_id if first_precedence > second_precedence else second.term_id

    term_ids = (
        (first.term_id, second.term_id)
        if first.term_id < second.term_id
        else (second.term_id, first.term_id)
    )
    return DetectedConflict(
        conflict_type=conflict_type,
        normalized_source_term=first.normalized_source_term,
        term_ids=term_ids,
        resolution_status=resolution_status,
        winner_term_id=winner_term_id,
        explanation=_explanation(conflict_type, resolution_status),
    )


def _classify_conflict(first: ConflictRule, second: ConflictRule) -> ConflictType:
    if (
        first.scope is not second.scope
        or first.scope_reference_id != second.scope_reference_id
        or first.priority != second.priority
    ):
        return ConflictType.SCOPE_CONFLICT
    if first.conditions != second.conditions:
        return ConflictType.CONTEXT_CONFLICT
    if first.rule_type is not second.rule_type:
        return ConflictType.RULE_CONFLICT
    return ConflictType.TARGET_CONFLICT


def _scope_contexts_overlap(first: ConflictRule, second: ConflictRule) -> bool:
    if first.scope is not second.scope:
        return True
    if first.scope_reference_id == second.scope_reference_id:
        return True
    if first.scope in _OPTIONALLY_REFERENCED_SCOPES:
        return first.scope_reference_id is None or second.scope_reference_id is None
    return False


def _has_common_dominating_rule(
    first: ConflictRule,
    second: ConflictRule,
    source_rules: tuple[ConflictRule, ...],
) -> bool:
    if (
        first.scope is not second.scope
        or first.scope_reference_id != second.scope_reference_id
        or first.conditions != second.conditions
    ):
        return False
    return any(
        candidate.scope is first.scope
        and candidate.scope_reference_id == first.scope_reference_id
        and candidate.conditions == first.conditions
        and candidate.priority > first.priority
        for candidate in source_rules
    )


def _conditions_overlap(first: ConflictRule, second: ConflictRule) -> bool:
    first_conditions = {condition.key: condition.value for condition in first.conditions}
    second_conditions = {condition.key: condition.value for condition in second.conditions}
    return all(
        first_conditions[key] == second_conditions[key]
        for key in first_conditions.keys() & second_conditions.keys()
    )


def _precedence(rule: ConflictRule) -> tuple[int, int]:
    return scope_priority(rule.scope), rule.priority


def _behavior(rule: ConflictRule) -> tuple[GlossaryRuleType, str | None]:
    return rule.rule_type, rule.target_term


def _rule_order(rule: ConflictRule) -> tuple[object, ...]:
    return (
        rule.normalized_source_term,
        -scope_priority(rule.scope),
        -rule.priority,
        rule.scope_reference_id or "",
        rule.conditions,
        rule.rule_type.value,
        rule.target_term or "",
        rule.term_id,
    )


def _conflict_order(conflict: DetectedConflict) -> tuple[object, ...]:
    return (
        conflict.normalized_source_term,
        conflict.conflict_type.value,
        conflict.term_ids,
    )


def _explanation(
    conflict_type: ConflictType,
    resolution_status: ConflictResolutionStatus,
) -> str:
    if resolution_status is ConflictResolutionStatus.AUTO_RESOLVED:
        return "A more specific or higher-priority glossary rule deterministically wins."
    return {
        ConflictType.TARGET_CONFLICT: (
            "Equal-priority glossary rules require different target terms."
        ),
        ConflictType.RULE_CONFLICT: (
            "Equal-priority glossary rules require incompatible rule behavior."
        ),
        ConflictType.SCOPE_CONFLICT: (
            "Overlapping scope rules have equal effective priority and incompatible behavior."
        ),
        ConflictType.CONTEXT_CONFLICT: (
            "Overlapping context conditions select incompatible glossary behavior."
        ),
    }[conflict_type]


def _validate_scope_reference(scope: GlossaryScope, value: str | None) -> None:
    if value is not None:
        _validate_required_text(value, "Scope reference")
    if scope in _REFERENCED_SCOPES and value is None:
        raise InvalidConflictRuleError("The selected scope requires a reference identifier.")
    if scope is GlossaryScope.SYSTEM and value is not None:
        raise InvalidConflictRuleError("System scope cannot have a reference identifier.")


def _validate_required_text(value: object, label: str) -> None:
    if (
        not isinstance(value, str)
        or not value.strip()
        or value != value.strip()
        or not value.isprintable()
    ):
        raise InvalidConflictRuleError(f"{label} must be a valid string.")
