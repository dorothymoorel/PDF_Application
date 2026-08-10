from itertools import permutations
from typing import Any, cast

import pytest
from transloka_core.database.models.glossary import (
    GlossaryMatchMode,
    GlossaryRuleType,
    GlossaryScope,
)
from transloka_glossary.matching import GlossaryMatch
from transloka_glossary.resolution import (
    InvalidScopeResolutionError,
    ScopeContext,
    ScopedGlossaryMatch,
    ScopeResolver,
    scope_priority,
)


def _candidate(
    term_id: str,
    scope: GlossaryScope,
    reference: str | None,
    target: str,
    *,
    priority: int = 0,
    rule_type: GlossaryRuleType = GlossaryRuleType.TRANSLATE_AS,
) -> ScopedGlossaryMatch:
    return ScopedGlossaryMatch(
        match=GlossaryMatch(
            term_id=term_id,
            source_term="framework",
            start_offset=4,
            end_offset=13,
            matched_text="framework",
            match_mode=GlossaryMatchMode.PHRASE,
            case_sensitive=False,
            whole_word=True,
        ),
        scope=scope,
        scope_reference_id=reference,
        priority=priority,
        rule_type=rule_type,
        target_term=target,
    )


def test_project_overrides_system_regardless_of_numeric_priority() -> None:
    system = _candidate("system", GlossaryScope.SYSTEM, None, "kerangka", priority=100)
    project = _candidate("project", GlossaryScope.PROJECT, "prj_1", "framework", priority=0)

    result = ScopeResolver().resolve(
        [system, project],
        ScopeContext(project_id="prj_1"),
    )

    assert result.winner == project
    assert result.warnings == ()


def test_segment_overrides_document() -> None:
    document = _candidate("document", GlossaryScope.DOCUMENT, "doc_1", "kerangka")
    segment = _candidate("segment", GlossaryScope.SEGMENT, "seg_1", "framework")

    result = ScopeResolver().resolve(
        [document, segment],
        ScopeContext(document_id="doc_1", segment_id="seg_1"),
    )

    assert result.winner == segment


def test_page_is_more_specific_than_section_and_less_specific_than_segment() -> None:
    section = _candidate("section", GlossaryScope.SECTION, "sec_1", "bagian")
    page = _candidate("page", GlossaryScope.PAGE, "page_1", "halaman")
    segment = _candidate("segment", GlossaryScope.SEGMENT, "seg_1", "segmen")
    context = ScopeContext(section_id="sec_1", page_id="page_1", segment_id="seg_1")

    assert ScopeResolver().resolve([section, page], context).winner == page
    assert ScopeResolver().resolve([section, page, segment], context).winner == segment


def test_higher_numeric_priority_wins_within_the_same_scope() -> None:
    lower = _candidate("lower", GlossaryScope.PROJECT, "prj_1", "kerangka", priority=1)
    higher = _candidate("higher", GlossaryScope.PROJECT, "prj_1", "framework", priority=2)

    result = ScopeResolver().resolve([higher, lower], ScopeContext(project_id="prj_1"))

    assert result.winner == higher
    assert result.warnings == ()


def test_equal_effective_priority_conflict_has_warning_without_winner() -> None:
    first = _candidate("term-b", GlossaryScope.PROJECT, "prj_1", "kerangka", priority=5)
    second = _candidate("term-a", GlossaryScope.PROJECT, "prj_1", "framework", priority=5)

    result = ScopeResolver().resolve([first, second], ScopeContext(project_id="prj_1"))

    assert result.winner is None
    assert len(result.warnings) == 1
    assert result.warnings[0].code == "EQUAL_PRIORITY_CONFLICT"
    assert result.warnings[0].term_ids == ("term-a", "term-b")
    assert "framework" not in result.warnings[0].message


def test_compatible_equal_priority_rules_use_stable_term_identifier() -> None:
    first = _candidate("term-b", GlossaryScope.PROJECT, "prj_1", "kerangka", priority=5)
    second = _candidate("term-a", GlossaryScope.PROJECT, "prj_1", "kerangka", priority=5)
    resolver = ScopeResolver()
    context = ScopeContext(project_id="prj_1")

    for ordering in permutations([first, second]):
        result = resolver.resolve(ordering, context)
        assert result.winner == second
        assert result.warnings == ()


def test_rules_outside_the_active_context_are_ignored() -> None:
    other_segment = _candidate("segment", GlossaryScope.SEGMENT, "seg_other", "segmen")
    project = _candidate("project", GlossaryScope.PROJECT, "prj_1", "kerangka")

    result = ScopeResolver().resolve(
        [other_segment, project],
        ScopeContext(project_id="prj_1", segment_id="seg_1"),
    )

    assert result.winner == project
    assert result.considered == (project,)


def test_no_applicable_rules_returns_empty_resolution() -> None:
    candidate = _candidate("document", GlossaryScope.DOCUMENT, "doc_other", "kerangka")

    result = ScopeResolver().resolve([candidate], ScopeContext(document_id="doc_1"))

    assert result.winner is None
    assert result.warnings == ()
    assert result.considered == ()


def test_scope_priority_covers_the_complete_persisted_hierarchy() -> None:
    ordered = (
        GlossaryScope.SYSTEM,
        GlossaryScope.DOMAIN,
        GlossaryScope.USER,
        GlossaryScope.PROJECT,
        GlossaryScope.DOCUMENT,
        GlossaryScope.SECTION,
        GlossaryScope.PAGE,
        GlossaryScope.SEGMENT,
    )

    assert [scope_priority(scope) for scope in ordered] == list(range(len(ordered)))


@pytest.mark.parametrize(
    "values",
    [
        {"scope": GlossaryScope.PROJECT, "reference": None, "priority": 0},
        {"scope": GlossaryScope.SYSTEM, "reference": "system", "priority": 0},
        {"scope": GlossaryScope.PROJECT, "reference": "prj_1", "priority": -1},
        {"scope": GlossaryScope.PROJECT, "reference": "prj_1", "priority": True},
    ],
)
def test_invalid_scoped_candidates_are_rejected(values: dict[str, object]) -> None:
    with pytest.raises(InvalidScopeResolutionError):
        cast(Any, _candidate)(
            "term",
            values["scope"],
            values["reference"],
            "kerangka",
            priority=values["priority"],
        )


def test_duplicate_terms_or_mixed_occurrences_are_rejected() -> None:
    first = _candidate("term", GlossaryScope.SYSTEM, None, "kerangka")
    duplicate = _candidate("term", GlossaryScope.PROJECT, "prj_1", "framework")
    different_occurrence = ScopedGlossaryMatch(
        match=GlossaryMatch(
            term_id="other",
            source_term="framework",
            start_offset=20,
            end_offset=29,
            matched_text="framework",
            match_mode=GlossaryMatchMode.PHRASE,
            case_sensitive=False,
            whole_word=True,
        ),
        scope=GlossaryScope.PROJECT,
        scope_reference_id="prj_1",
        priority=0,
        rule_type=GlossaryRuleType.TRANSLATE_AS,
        target_term="kerangka",
    )
    resolver = ScopeResolver()
    context = ScopeContext(project_id="prj_1")

    with pytest.raises(InvalidScopeResolutionError):
        resolver.resolve([first, duplicate], context)
    with pytest.raises(InvalidScopeResolutionError):
        resolver.resolve([first, different_occurrence], context)
