from itertools import permutations
from typing import Any, cast

import pytest
from transloka_core.database.models.glossary import GlossaryRuleType, GlossaryScope
from transloka_glossary.conflicts import (
    ConflictDetector,
    ConflictResolutionStatus,
    ConflictRule,
    ConflictType,
    ContextCondition,
    InvalidConflictRuleError,
    TranslationReadinessBlockedError,
)


def _rule(
    term_id: str,
    target: str | None,
    *,
    rule_type: GlossaryRuleType = GlossaryRuleType.TRANSLATE_AS,
    scope: GlossaryScope = GlossaryScope.PROJECT,
    reference: str | None = "prj_1",
    priority: int = 0,
    conditions: tuple[ContextCondition, ...] = (),
    active: bool = True,
) -> ConflictRule:
    return ConflictRule(
        term_id=term_id,
        normalized_source_term="framework",
        rule_type=rule_type,
        scope=scope,
        scope_reference_id=reference,
        priority=priority,
        target_term=target,
        conditions=conditions,
        active=active,
    )


def test_different_targets_at_equal_priority_require_manual_resolution() -> None:
    result = ConflictDetector().detect(
        [_rule("term-b", "kerangka kerja"), _rule("term-a", "kerangka")]
    )

    assert len(result.conflicts) == 1
    conflict = result.conflicts[0]
    assert conflict.conflict_type is ConflictType.TARGET_CONFLICT
    assert conflict.term_ids == ("term-a", "term-b")
    assert conflict.resolution_status is ConflictResolutionStatus.UNRESOLVED
    assert conflict.winner_term_id is None
    assert conflict.blocking
    assert not result.translation_ready

    with pytest.raises(TranslationReadinessBlockedError) as error:
        result.require_translation_ready()
    assert error.value.conflicts == (conflict,)
    assert "framework" not in str(error.value)


def test_different_rule_types_are_reported_as_rule_conflict() -> None:
    translate = _rule("translate", "kerangka")
    preserve = _rule(
        "preserve",
        None,
        rule_type=GlossaryRuleType.KEEP_ORIGINAL,
    )

    conflict = ConflictDetector().detect([preserve, translate]).conflicts[0]

    assert conflict.conflict_type is ConflictType.RULE_CONFLICT
    assert conflict.resolution_status is ConflictResolutionStatus.UNRESOLVED
    assert conflict.blocking


def test_more_specific_scope_is_auto_resolved_and_does_not_block_translation() -> None:
    project = _rule("project", "kerangka")
    document = _rule(
        "document",
        "framework",
        scope=GlossaryScope.DOCUMENT,
        reference="doc_1",
    )

    result = ConflictDetector().detect([project, document])

    assert len(result.conflicts) == 1
    conflict = result.conflicts[0]
    assert conflict.conflict_type is ConflictType.SCOPE_CONFLICT
    assert conflict.resolution_status is ConflictResolutionStatus.AUTO_RESOLVED
    assert conflict.winner_term_id == "document"
    assert not conflict.blocking
    assert result.translation_ready
    result.require_translation_ready()


def test_higher_numeric_priority_auto_resolves_within_one_scope() -> None:
    lower = _rule("lower", "kerangka", priority=1)
    higher = _rule("higher", "framework", priority=2)

    conflict = ConflictDetector().detect([higher, lower]).conflicts[0]

    assert conflict.conflict_type is ConflictType.SCOPE_CONFLICT
    assert conflict.resolution_status is ConflictResolutionStatus.AUTO_RESOLVED
    assert conflict.winner_term_id == "higher"


def test_shadowed_lower_priority_disagreement_does_not_block_translation() -> None:
    winner = _rule("winner", "kerangka", priority=2)
    lower_a = _rule("lower-a", "framework", priority=1)
    lower_b = _rule("lower-b", "rangka kerja", priority=1)

    result = ConflictDetector().detect([lower_b, winner, lower_a])

    assert result.translation_ready
    assert all(
        conflict.resolution_status is ConflictResolutionStatus.AUTO_RESOLVED
        for conflict in result.conflicts
    )
    assert {conflict.winner_term_id for conflict in result.conflicts} == {"winner"}


def test_equal_priority_overlapping_scope_references_require_manual_resolution() -> None:
    domain_default = _rule(
        "domain-default",
        "kerangka",
        scope=GlossaryScope.DOMAIN,
        reference=None,
    )
    software_domain = _rule(
        "software-domain",
        "framework",
        scope=GlossaryScope.DOMAIN,
        reference="software",
    )

    conflict = ConflictDetector().detect([software_domain, domain_default]).conflicts[0]

    assert conflict.conflict_type is ConflictType.SCOPE_CONFLICT
    assert conflict.resolution_status is ConflictResolutionStatus.UNRESOLVED
    assert conflict.blocking


def test_overlapping_context_conditions_are_a_blocking_context_conflict() -> None:
    technical = ContextCondition("document_type", "technical")
    abstract = ContextCondition("section", "abstract")
    broad = _rule("broad", "kerangka", conditions=(technical,))
    narrow = _rule("narrow", "framework", conditions=(technical, abstract))

    conflict = ConflictDetector().detect([narrow, broad]).conflicts[0]

    assert conflict.conflict_type is ConflictType.CONTEXT_CONFLICT
    assert conflict.resolution_status is ConflictResolutionStatus.UNRESOLVED
    assert conflict.blocking


def test_mutually_exclusive_contexts_and_scopes_do_not_conflict() -> None:
    legal = _rule(
        "legal",
        "kerangka hukum",
        conditions=(ContextCondition("document_type", "legal"),),
    )
    technical = _rule(
        "technical",
        "kerangka teknis",
        conditions=(ContextCondition("document_type", "technical"),),
    )
    other_project = _rule(
        "other-project",
        "framework",
        reference="prj_2",
    )

    result = ConflictDetector().detect([legal, technical, other_project])

    assert result.conflicts == ()
    assert result.translation_ready


def test_inactive_and_behaviorally_identical_rules_are_ignored() -> None:
    active = _rule("active", "kerangka")
    inactive = _rule("inactive", "framework", active=False)
    identical = _rule("identical", "kerangka")

    result = ConflictDetector().detect([inactive, identical, active])

    assert result.conflicts == ()
    assert result.translation_ready


def test_detection_is_deterministic_for_input_order() -> None:
    rules = (
        _rule("target-a", "kerangka"),
        _rule("target-b", "framework"),
        _rule(
            "system",
            None,
            rule_type=GlossaryRuleType.KEEP_ORIGINAL,
            scope=GlossaryScope.SYSTEM,
            reference=None,
        ),
    )
    detector = ConflictDetector()
    expected = detector.detect(rules)

    for ordering in permutations(rules):
        assert detector.detect(ordering) == expected


def test_duplicate_identifiers_and_non_rule_inputs_are_rejected() -> None:
    rule = _rule("term", "kerangka")
    detector = ConflictDetector()

    with pytest.raises(InvalidConflictRuleError):
        detector.detect([rule, rule])
    with pytest.raises(InvalidConflictRuleError):
        cast(Any, detector.detect)([rule, "not-a-rule"])


@pytest.mark.parametrize(
    "values",
    [
        {"term_id": "", "normalized_source_term": "framework"},
        {"term_id": "term", "normalized_source_term": " framework"},
        {"term_id": "term", "normalized_source_term": "framework", "priority": True},
        {
            "term_id": "term",
            "normalized_source_term": "framework",
            "scope": GlossaryScope.PROJECT,
            "scope_reference_id": None,
        },
        {
            "term_id": "term",
            "normalized_source_term": "framework",
            "conditions": (ContextCondition("kind", "one"), ContextCondition("kind", "two")),
        },
    ],
)
def test_invalid_conflict_rules_are_rejected(values: dict[str, object]) -> None:
    defaults: dict[str, object] = {
        "term_id": "term",
        "normalized_source_term": "framework",
        "rule_type": GlossaryRuleType.TRANSLATE_AS,
        "scope": GlossaryScope.PROJECT,
        "scope_reference_id": "prj_1",
        "target_term": "kerangka",
    }
    defaults.update(values)

    with pytest.raises(InvalidConflictRuleError):
        cast(Any, ConflictRule)(**defaults)
