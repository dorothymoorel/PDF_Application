from itertools import permutations
from typing import Any, cast

import pytest
from transloka_core.database.models.glossary import GlossaryMatchMode
from transloka_glossary.matching import (
    GlossaryMatch,
    GlossaryMatcher,
    InvalidMatchRuleError,
    MatchRule,
    resolve_overlaps,
)


def _rule(
    term_id: str,
    source_term: str,
    *,
    mode: GlossaryMatchMode = GlossaryMatchMode.PHRASE,
    case_sensitive: bool = False,
    whole_word: bool = True,
) -> MatchRule:
    return MatchRule(
        term_id=term_id,
        source_term=source_term,
        match_mode=mode,
        case_sensitive=case_sensitive,
        whole_word=whole_word,
    )


def test_exact_mode_matches_only_the_complete_text() -> None:
    matcher = GlossaryMatcher()
    exact = _rule("exact", "workflow", mode=GlossaryMatchMode.EXACT)
    phrase = _rule("phrase", "workflow")

    assert matcher.match("A workflow exists.", [exact]) == ()
    assert matcher.match("WORKFLOW", [exact]) == (
        GlossaryMatch(
            term_id="exact",
            source_term="workflow",
            start_offset=0,
            end_offset=8,
            matched_text="WORKFLOW",
            match_mode=GlossaryMatchMode.EXACT,
            case_sensitive=False,
            whole_word=True,
        ),
    )
    assert [match.term_id for match in matcher.match("A workflow exists.", [exact, phrase])] == [
        "phrase"
    ]


def test_longest_nested_phrase_wins() -> None:
    rules = (
        _rule("machine", "machine"),
        _rule("machine-learning", "machine learning"),
        _rule("learning", "learning"),
    )

    candidates = GlossaryMatcher().find_candidates("machine learning model", rules)
    matches = GlossaryMatcher().match("machine learning model", rules)

    assert [(match.term_id, match.start_offset, match.end_offset) for match in candidates] == [
        ("machine", 0, 7),
        ("machine-learning", 0, 16),
        ("learning", 8, 16),
    ]
    assert [(match.term_id, match.matched_text) for match in matches] == [
        ("machine-learning", "machine learning")
    ]


def test_equal_length_phrase_overlap_uses_earliest_source_position() -> None:
    rules = (
        _rule("first", "abcd", whole_word=False),
        _rule("second", "bcde", whole_word=False),
    )

    matches = GlossaryMatcher().match("abcde", rules)

    assert [(match.term_id, match.matched_text) for match in matches] == [("first", "abcd")]


def test_case_sensitive_and_case_insensitive_rules_are_distinct() -> None:
    matcher = GlossaryMatcher()
    sensitive = _rule("sensitive", "API", case_sensitive=True)
    insensitive = _rule("insensitive", "api")

    sensitive_matches = matcher.match("API Api api", [sensitive])
    insensitive_matches = matcher.match("API Api api", [insensitive])

    assert [match.matched_text for match in sensitive_matches] == ["API"]
    assert [match.matched_text for match in insensitive_matches] == ["API", "Api", "api"]


def test_whole_word_accepts_punctuation_and_rejects_identifier_substrings() -> None:
    matcher = GlossaryMatcher()
    whole_word = _rule("whole", "API")
    substring = _rule("substring", "API", whole_word=False)
    text = "(API), API-driven API_client myAPI"

    assert [match.start_offset for match in matcher.match(text, [whole_word])] == [1, 7]
    assert [match.start_offset for match in matcher.match(text, [substring])] == [1, 7, 18, 31]


def test_punctuation_around_phrase_preserves_exact_offsets() -> None:
    text = "Use ‘machine learning’, then machine learning."
    matches = GlossaryMatcher().match(text, [_rule("term", "machine learning")])

    assert [(match.start_offset, match.end_offset, match.matched_text) for match in matches] == [
        (5, 21, "machine learning"),
        (29, 45, "machine learning"),
    ]


def test_repeated_and_self_overlapping_terms_resolve_deterministically() -> None:
    matcher = GlossaryMatcher()

    repeated = matcher.match("term, term; term", [_rule("term", "term")])
    overlapping_candidates = matcher.find_candidates(
        "banana",
        [_rule("ana", "ana", whole_word=False)],
    )
    overlapping_matches = matcher.match(
        "banana",
        [_rule("ana", "ana", whole_word=False)],
    )

    assert [(match.start_offset, match.end_offset) for match in repeated] == [
        (0, 4),
        (6, 10),
        (12, 16),
    ]
    assert [(match.start_offset, match.end_offset) for match in overlapping_candidates] == [
        (1, 4),
        (3, 6),
    ]
    assert [(match.start_offset, match.end_offset) for match in overlapping_matches] == [(1, 4)]


def test_unicode_casefold_preserves_original_source_offsets() -> None:
    match = GlossaryMatcher().match("Straße", [_rule("street", "STRASSE")])

    assert len(match) == 1
    assert match[0].matched_text == "Straße"
    assert match[0].start_offset == 0
    assert match[0].end_offset == 6


def test_rule_order_and_repeated_runs_do_not_change_resolution() -> None:
    rules = (
        _rule("z-rule", "workflow"),
        _rule("a-rule", "workflow"),
        _rule("long-rule", "workflow engine"),
    )
    matcher = GlossaryMatcher()
    expected = matcher.match("workflow engine and workflow", rules)

    for ordering in permutations(rules):
        assert matcher.match("workflow engine and workflow", ordering) == expected
        assert matcher.match("workflow engine and workflow", ordering) == expected

    assert [(match.term_id, match.matched_text) for match in expected] == [
        ("long-rule", "workflow engine"),
        ("a-rule", "workflow"),
    ]


def test_resolve_overlaps_prefers_exact_and_specific_flags_for_equal_span() -> None:
    phrase = GlossaryMatch(
        term_id="phrase",
        source_term="API",
        start_offset=0,
        end_offset=3,
        matched_text="API",
        match_mode=GlossaryMatchMode.PHRASE,
        case_sensitive=True,
        whole_word=True,
    )
    exact = GlossaryMatch(
        term_id="exact",
        source_term="API",
        start_offset=0,
        end_offset=3,
        matched_text="API",
        match_mode=GlossaryMatchMode.EXACT,
        case_sensitive=True,
        whole_word=True,
    )

    assert resolve_overlaps([phrase, exact]) == (exact,)


@pytest.mark.parametrize(
    "rule",
    [
        MatchRule(term_id="valid", source_term="term"),
        "not-a-rule",
    ],
)
def test_duplicate_or_non_rule_inputs_are_rejected(rule: object) -> None:
    matcher = GlossaryMatcher()
    if isinstance(rule, MatchRule):
        with pytest.raises(InvalidMatchRuleError):
            matcher.match("term", [rule, rule])
    else:
        with pytest.raises(InvalidMatchRuleError):
            cast(Any, matcher.match)("term", [rule])


@pytest.mark.parametrize(
    "values",
    [
        {"term_id": "", "source_term": "term"},
        {"term_id": "term", "source_term": ""},
        {"term_id": "term", "source_term": " term"},
        {"term_id": "term", "source_term": "term\n"},
        {"term_id": "term", "source_term": "term", "case_sensitive": 1},
    ],
)
def test_invalid_rules_are_rejected(values: dict[str, object]) -> None:
    with pytest.raises(InvalidMatchRuleError):
        cast(Any, MatchRule)(**values)


def test_empty_text_has_no_matches_and_non_text_is_rejected() -> None:
    matcher = GlossaryMatcher()
    rule = _rule("term", "term")

    assert matcher.match("", [rule]) == ()
    with pytest.raises(TypeError):
        matcher.match(cast(str, 123), [rule])
