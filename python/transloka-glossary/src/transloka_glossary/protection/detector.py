import re
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from types import MappingProxyType

from transloka_core.database.models.glossary import ProtectedItemType

from transloka_glossary.matching import GlossaryMatcher, MatchRule
from transloka_glossary.placeholders.generator import PlaceholderGenerator

_URL_PATTERN = re.compile(r"(?i)(?:https?://|www\.)[^\s<>\"']+")
_EMAIL_PATTERN = re.compile(
    r"(?i)(?<![\w.!#$%&'*+/=?^`{|}~-])"
    r"[a-z0-9.!#$%&'*+/=?^_`{|}~-]+@"
    r"(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+"
    r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?"
    r"(?![\w-])"
)
_FENCED_CODE_PATTERN = re.compile(r"```[\s\S]*?```")
_INLINE_CODE_PATTERN = re.compile(r"`[^`\r\n]+`")
_CODE_IDENTIFIER_PATTERN = re.compile(
    r"(?<![\w])(?:"
    r"[A-Za-z][A-Za-z0-9]*_[A-Za-z0-9_]+"
    r"|[a-z]+[A-Z][A-Za-z0-9]*"
    r"|[A-Za-z][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)+"
    r")(?:\(\))?(?![\w])"
)
_METHOD_ENDPOINT_PATTERN = re.compile(
    r"(?i)(?<![A-Z])(?:GET|POST|PUT|PATCH|DELETE|HEAD|OPTIONS)\s+"
    r"/[A-Za-z0-9._~{}:/-]+"
)
_API_ENDPOINT_PATTERN = re.compile(
    r"(?<![\w/])/(?:api|v[0-9]+)(?:/[A-Za-z0-9._~{}:-]+)+",
    re.IGNORECASE,
)
_WINDOWS_PATH_PATTERN = re.compile(
    r"(?<![\w])(?:[A-Za-z]:\\|\\\\[A-Za-z0-9._$-]+\\)"
    r"(?:[^\\\s<>:\"|?*]+\\)*[^\\\s<>:\"|?*,;!]+"
)
_POSIX_PATH_PATTERN = re.compile(r"(?<![\w])/(?:[A-Za-z0-9._~-]+/)+[A-Za-z0-9._~-]*[A-Za-z0-9_~)-]")
_RELATIVE_PATH_PATTERN = re.compile(
    r"(?<![\w])(?:[A-Za-z0-9._~-]+[\\/])+"
    r"[A-Za-z0-9._~-]*[A-Za-z0-9_~)-](?![\w])"
)
_NUMERIC_CITATION_PATTERN = re.compile(r"\[(?:\d{1,4})(?:\s*[-,;]\s*\d{1,4})*\]")
_AUTHOR_YEAR_CITATION_PATTERN = re.compile(
    r"\([A-Z][\w'-]+(?:\s+et\s+al\.)?(?:\s*&\s*[A-Z][\w'-]+)?,\s*"
    r"(?:19|20)\d{2}[a-z]?\)"
)
_ACRONYM_PATTERN = re.compile(r"(?<![\w])(?:[A-Z]{2,}[0-9]*|[A-Z][0-9][A-Z0-9]*)(?![\w])")

_TYPE_PRECEDENCE = {
    ProtectedItemType.CODE: 0,
    ProtectedItemType.URL: 1,
    ProtectedItemType.EMAIL: 2,
    ProtectedItemType.ENDPOINT: 3,
    ProtectedItemType.FILE_PATH: 4,
    ProtectedItemType.CITATION: 5,
    ProtectedItemType.TERM: 6,
    ProtectedItemType.ACRONYM: 7,
}


@dataclass(frozen=True, slots=True)
class ProtectedContent:
    item_type: ProtectedItemType
    start_offset: int
    end_offset: int
    source_value: str
    term_id: str | None = None

    @property
    def length(self) -> int:
        return self.end_offset - self.start_offset


@dataclass(frozen=True, slots=True)
class ProtectedInventoryItem:
    placeholder: str
    item_type: ProtectedItemType
    source_value: str
    start_offset: int
    end_offset: int
    term_id: str | None


@dataclass(frozen=True, slots=True)
class ProtectedDocument:
    text: str
    inventory: tuple[ProtectedInventoryItem, ...]

    @property
    def restoration_map(self) -> Mapping[str, str]:
        return MappingProxyType({item.placeholder: item.source_value for item in self.inventory})


class ProtectedContentDetector:
    def __init__(self) -> None:
        self._glossary_matcher = GlossaryMatcher()

    def detect(
        self,
        text: str,
        glossary_rules: Iterable[MatchRule] = (),
    ) -> tuple[ProtectedContent, ...]:
        if not isinstance(text, str):
            raise TypeError("Protected content detection requires text input.")

        candidates = self._glossary_candidates(text, glossary_rules)
        candidates.extend(_pattern_candidates(text))
        return _resolve_overlaps(candidates)

    def protect(
        self,
        text: str,
        glossary_rules: Iterable[MatchRule] = (),
        *,
        reserved_placeholders: Iterable[str] = (),
    ) -> ProtectedDocument:
        detected = self.detect(text, glossary_rules)
        generator = PlaceholderGenerator("\n".join((text, *reserved_placeholders)))
        inventory: list[ProtectedInventoryItem] = []
        protected_parts: list[str] = []
        source_offset = 0

        for item in detected:
            protected_parts.append(text[source_offset : item.start_offset])
            placeholder = generator.generate(item.item_type, item.source_value)
            protected_parts.append(placeholder.placeholder)
            inventory.append(
                ProtectedInventoryItem(
                    placeholder=placeholder.placeholder,
                    item_type=item.item_type,
                    source_value=item.source_value,
                    start_offset=item.start_offset,
                    end_offset=item.end_offset,
                    term_id=item.term_id,
                )
            )
            source_offset = item.end_offset

        protected_parts.append(text[source_offset:])
        return ProtectedDocument(
            text="".join(protected_parts),
            inventory=tuple(inventory),
        )

    def _glossary_candidates(
        self,
        text: str,
        glossary_rules: Iterable[MatchRule],
    ) -> list[ProtectedContent]:
        return [
            ProtectedContent(
                item_type=ProtectedItemType.TERM,
                start_offset=match.start_offset,
                end_offset=match.end_offset,
                source_value=match.matched_text,
                term_id=match.term_id,
            )
            for match in self._glossary_matcher.find_candidates(text, glossary_rules)
        ]


def _pattern_candidates(text: str) -> list[ProtectedContent]:
    candidates: list[ProtectedContent] = []
    for pattern, item_type in (
        (_FENCED_CODE_PATTERN, ProtectedItemType.CODE),
        (_INLINE_CODE_PATTERN, ProtectedItemType.CODE),
        (_URL_PATTERN, ProtectedItemType.URL),
        (_EMAIL_PATTERN, ProtectedItemType.EMAIL),
        (_METHOD_ENDPOINT_PATTERN, ProtectedItemType.ENDPOINT),
        (_API_ENDPOINT_PATTERN, ProtectedItemType.ENDPOINT),
        (_WINDOWS_PATH_PATTERN, ProtectedItemType.FILE_PATH),
        (_POSIX_PATH_PATTERN, ProtectedItemType.FILE_PATH),
        (_RELATIVE_PATH_PATTERN, ProtectedItemType.FILE_PATH),
        (_NUMERIC_CITATION_PATTERN, ProtectedItemType.CITATION),
        (_AUTHOR_YEAR_CITATION_PATTERN, ProtectedItemType.CITATION),
        (_CODE_IDENTIFIER_PATTERN, ProtectedItemType.CODE),
        (_ACRONYM_PATTERN, ProtectedItemType.ACRONYM),
    ):
        for match in pattern.finditer(text):
            start, end = match.span()
            if item_type is ProtectedItemType.URL:
                end = _trim_url_end(text, start, end)
            elif item_type in {ProtectedItemType.ENDPOINT, ProtectedItemType.FILE_PATH}:
                end = _trim_sentence_punctuation(text, start, end)
            if end <= start:
                continue
            candidates.append(
                ProtectedContent(
                    item_type=item_type,
                    start_offset=start,
                    end_offset=end,
                    source_value=text[start:end],
                )
            )
    return candidates


def _trim_url_end(text: str, start: int, end: int) -> int:
    end = _trim_sentence_punctuation(text, start, end)
    pairs = (("(", ")"), ("[", "]"), ("{", "}"))
    changed = True
    while changed and end > start:
        changed = False
        value = text[start:end]
        for opening, closing in pairs:
            if value.endswith(closing) and value.count(closing) > value.count(opening):
                end -= 1
                changed = True
                break
    return end


def _trim_sentence_punctuation(text: str, start: int, end: int) -> int:
    while end > start and text[end - 1] in ".,;:!?":
        end -= 1
    return end


def _resolve_overlaps(candidates: Iterable[ProtectedContent]) -> tuple[ProtectedContent, ...]:
    unique = {
        (
            candidate.start_offset,
            candidate.end_offset,
            candidate.item_type,
            candidate.term_id,
        ): candidate
        for candidate in candidates
    }
    selected: list[ProtectedContent] = []
    for candidate in sorted(unique.values(), key=_resolution_order):
        if any(_overlaps(candidate, existing) for existing in selected):
            continue
        selected.append(candidate)
    return tuple(sorted(selected, key=_source_order))


def _resolution_order(candidate: ProtectedContent) -> tuple[object, ...]:
    return (
        -candidate.length,
        candidate.start_offset,
        _TYPE_PRECEDENCE[candidate.item_type],
        candidate.end_offset,
        candidate.term_id or "",
        candidate.source_value,
    )


def _source_order(candidate: ProtectedContent) -> tuple[object, ...]:
    return (
        candidate.start_offset,
        candidate.end_offset,
        _TYPE_PRECEDENCE[candidate.item_type],
        candidate.term_id or "",
    )


def _overlaps(first: ProtectedContent, second: ProtectedContent) -> bool:
    return first.start_offset < second.end_offset and second.start_offset < first.end_offset
