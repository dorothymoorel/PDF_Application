from collections.abc import Iterable
from dataclasses import dataclass

from transloka_core.database.models.glossary import GlossaryMatchMode


class InvalidMatchRuleError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class MatchRule:
    term_id: str
    source_term: str
    match_mode: GlossaryMatchMode = GlossaryMatchMode.PHRASE
    case_sensitive: bool = False
    whole_word: bool = True

    def __post_init__(self) -> None:
        if not self.term_id or not self.term_id.isprintable():
            raise InvalidMatchRuleError("A match rule requires a stable term identifier.")
        if (
            not self.source_term
            or not self.source_term.strip()
            or self.source_term != self.source_term.strip()
            or not self.source_term.isprintable()
        ):
            raise InvalidMatchRuleError("A match rule requires a valid source term.")
        if not isinstance(self.match_mode, GlossaryMatchMode):
            raise InvalidMatchRuleError("The glossary match mode is invalid.")
        if not isinstance(self.case_sensitive, bool) or not isinstance(self.whole_word, bool):
            raise InvalidMatchRuleError("Glossary matching flags must be booleans.")


@dataclass(frozen=True, slots=True)
class GlossaryMatch:
    term_id: str
    source_term: str
    start_offset: int
    end_offset: int
    matched_text: str
    match_mode: GlossaryMatchMode
    case_sensitive: bool
    whole_word: bool

    @property
    def length(self) -> int:
        return self.end_offset - self.start_offset


class GlossaryMatcher:
    def find_candidates(
        self,
        text: str,
        rules: Iterable[MatchRule],
    ) -> tuple[GlossaryMatch, ...]:
        _validate_text(text)
        ordered_rules = _ordered_rules(rules)
        candidates: dict[tuple[int, int, str], GlossaryMatch] = {}
        folded_text: _FoldedText | None = None

        for rule in ordered_rules:
            if rule.match_mode is GlossaryMatchMode.EXACT:
                spans = _exact_spans(text, rule)
            elif rule.case_sensitive:
                spans = _case_sensitive_phrase_spans(text, rule.source_term)
            else:
                if folded_text is None:
                    folded_text = _fold_text(text)
                spans = _case_insensitive_phrase_spans(folded_text, rule.source_term)

            for start, end in spans:
                if rule.whole_word and not _is_whole_word(text, start, end):
                    continue
                match = GlossaryMatch(
                    term_id=rule.term_id,
                    source_term=rule.source_term,
                    start_offset=start,
                    end_offset=end,
                    matched_text=text[start:end],
                    match_mode=rule.match_mode,
                    case_sensitive=rule.case_sensitive,
                    whole_word=rule.whole_word,
                )
                candidates[(start, end, rule.term_id)] = match

        return tuple(sorted(candidates.values(), key=_text_order))

    def match(
        self,
        text: str,
        rules: Iterable[MatchRule],
    ) -> tuple[GlossaryMatch, ...]:
        return resolve_overlaps(self.find_candidates(text, rules))


def resolve_overlaps(matches: Iterable[GlossaryMatch]) -> tuple[GlossaryMatch, ...]:
    candidates = tuple(matches)
    for match in candidates:
        if match.start_offset < 0 or match.end_offset <= match.start_offset:
            raise ValueError("A glossary match has invalid source offsets.")

    selected: list[GlossaryMatch] = []
    for candidate in sorted(candidates, key=_resolution_order):
        if any(_overlaps(candidate, existing) for existing in selected):
            continue
        selected.append(candidate)
    return tuple(sorted(selected, key=_text_order))


@dataclass(frozen=True, slots=True)
class _FoldedText:
    value: str
    starts: tuple[int, ...]
    ends: tuple[int, ...]
    valid_starts: frozenset[int]
    valid_ends: frozenset[int]


def _ordered_rules(rules: Iterable[MatchRule]) -> tuple[MatchRule, ...]:
    materialized = tuple(rules)
    if not all(isinstance(rule, MatchRule) for rule in materialized):
        raise InvalidMatchRuleError("Every glossary rule must be a MatchRule.")
    identifiers = [rule.term_id for rule in materialized]
    if len(identifiers) != len(set(identifiers)):
        raise InvalidMatchRuleError("Glossary term identifiers must be unique.")
    return tuple(
        sorted(
            materialized,
            key=lambda rule: (
                rule.source_term.casefold(),
                rule.source_term,
                rule.match_mode.value,
                not rule.case_sensitive,
                not rule.whole_word,
                rule.term_id,
            ),
        )
    )


def _validate_text(text: str) -> None:
    if not isinstance(text, str):
        raise TypeError("Glossary matching requires text input.")


def _exact_spans(text: str, rule: MatchRule) -> tuple[tuple[int, int], ...]:
    if rule.case_sensitive:
        matches = text == rule.source_term
    else:
        matches = text.casefold() == rule.source_term.casefold()
    return ((0, len(text)),) if matches and text else ()


def _case_sensitive_phrase_spans(text: str, term: str) -> tuple[tuple[int, int], ...]:
    spans: list[tuple[int, int]] = []
    start = 0
    while True:
        index = text.find(term, start)
        if index < 0:
            return tuple(spans)
        spans.append((index, index + len(term)))
        start = index + 1


def _case_insensitive_phrase_spans(
    text: _FoldedText,
    term: str,
) -> tuple[tuple[int, int], ...]:
    folded_term = term.casefold()
    spans: set[tuple[int, int]] = set()
    start = 0
    while True:
        index = text.value.find(folded_term, start)
        if index < 0:
            return tuple(sorted(spans))
        folded_end = index + len(folded_term)
        if (
            index in text.valid_starts
            and folded_end in text.valid_ends
            and index < len(text.starts)
            and folded_end > 0
        ):
            spans.add((text.starts[index], text.ends[folded_end - 1]))
        start = index + 1


def _fold_text(text: str) -> _FoldedText:
    folded: list[str] = []
    starts: list[int] = []
    ends: list[int] = []
    valid_starts: set[int] = set()
    valid_ends: set[int] = set()
    for index, character in enumerate(text):
        value = character.casefold()
        valid_starts.add(len(folded))
        folded.extend(value)
        starts.extend(index for _ in value)
        ends.extend(index + 1 for _ in value)
        valid_ends.add(len(folded))
    return _FoldedText(
        value="".join(folded),
        starts=tuple(starts),
        ends=tuple(ends),
        valid_starts=frozenset(valid_starts),
        valid_ends=frozenset(valid_ends),
    )


def _is_whole_word(text: str, start: int, end: int) -> bool:
    left_boundary = start == 0 or not _is_word_character(text[start - 1])
    right_boundary = end == len(text) or not _is_word_character(text[end])
    return left_boundary and right_boundary


def _is_word_character(character: str) -> bool:
    return character == "_" or character.isalnum()


def _resolution_order(match: GlossaryMatch) -> tuple[object, ...]:
    return (
        -match.length,
        match.start_offset,
        match.end_offset,
        0 if match.match_mode is GlossaryMatchMode.EXACT else 1,
        not match.case_sensitive,
        not match.whole_word,
        match.source_term.casefold(),
        match.source_term,
        match.term_id,
    )


def _text_order(match: GlossaryMatch) -> tuple[object, ...]:
    return (
        match.start_offset,
        match.end_offset,
        match.term_id,
        match.source_term,
    )


def _overlaps(first: GlossaryMatch, second: GlossaryMatch) -> bool:
    return first.start_offset < second.end_offset and second.start_offset < first.end_offset
