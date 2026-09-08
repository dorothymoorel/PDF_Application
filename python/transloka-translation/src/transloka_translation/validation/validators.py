from __future__ import annotations

import re
from collections import Counter
from collections.abc import Iterable

from transloka_translation.schemas import (
    TranslatedSegment,
    TranslationPlaceholder,
    TranslationRequest,
    TranslationRequestSegment,
    TranslationResponse,
)

from .models import ValidationCode, ValidationIssue, ValidationReport, ValidationSeverity

_PLACEHOLDER_PATTERN = re.compile(r"__TLK_[A-Z_]+_[0-9]{4,}_[0-9A-F]{2}__")
_PLACEHOLDER_LIKE_PATTERN = re.compile(r"__TLK[A-Za-z0-9_]*")
_URL_PATTERN = re.compile(r"(?i)(?:https?://|www\.)[^\s<>\"']+")
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
_LABELLED_CITATION_PATTERN = re.compile(
    r"(?i)\b(?:fig(?:ure)?|table|eq(?:uation)?)\.?\s+\d+(?:\.\d+)*\b"
)
_VERSION_PATTERN = re.compile(r"(?<![\w])v?\d+(?:\.\d+){2,}(?![\w])", re.IGNORECASE)
_DATE_PATTERN = re.compile(r"(?<![\w])\d{1,4}[-/]\d{1,2}[-/]\d{1,4}(?![\w])")
_DECADE_PATTERN = re.compile(r"(?<!\w)(\d{3}0)(?:['’]?s|-?an)(?!\w)", re.IGNORECASE)
_NUMBER_PATTERN = re.compile(
    r"(?i)(?<![\w])"
    r"(?P<currency>(?:USD|IDR|EUR|GBP|JPY|Rp|[$€£¥])\s*)?"
    r"(?P<number>[+-]?(?:\d{1,3}(?:[.,]\d{3})+|\d+)(?:[.,]\d+)?)"
    r"(?P<percent>\s*%)?(?![\w])"
)
_WORD_PATTERN = re.compile(r"[^\W\d_]+", re.UNICODE)

_ENGLISH_MARKERS = frozenset(
    {
        "and",
        "are",
        "as",
        "by",
        "for",
        "from",
        "in",
        "is",
        "not",
        "of",
        "on",
        "that",
        "the",
        "this",
        "to",
        "was",
        "were",
        "with",
    }
)
_INDONESIAN_MARKERS = frozenset(
    {
        "adalah",
        "akan",
        "atau",
        "dalam",
        "dan",
        "dari",
        "dengan",
        "di",
        "ini",
        "itu",
        "oleh",
        "pada",
        "sebagai",
        "telah",
        "tidak",
        "untuk",
        "yang",
    }
)
_ENGLISH_NEGATIONS = frozenset({"no", "not", "never", "neither", "without"})
_INDONESIAN_NEGATIONS = frozenset({"belum", "bukan", "jangan", "tak", "tanpa", "tidak"})


class TranslationValidator:
    def __init__(
        self,
        *,
        minimum_length_ratio: float = 0.5,
        maximum_length_ratio: float = 2.0,
    ) -> None:
        self._minimum_length_ratio, self._maximum_length_ratio = _length_bounds(
            minimum_length_ratio,
            maximum_length_ratio,
        )

    def validate(
        self,
        request: TranslationRequest,
        response: TranslationResponse,
    ) -> ValidationReport:
        if type(request) is not TranslationRequest:
            raise TypeError("Translation validation requires a TranslationRequest.")
        if type(response) is not TranslationResponse:
            raise TypeError("Translation validation requires a TranslationResponse.")

        issues = list(validate_segment_mapping(request, response))
        translated_by_id = {segment.segment_id: segment for segment in response.segments}
        placeholders_by_id = _placeholders_by_segment(request.placeholders)

        for source_segment in request.segments:
            translated_segment = translated_by_id.get(source_segment.segment_id)
            if translated_segment is None:
                continue
            issues.extend(
                validate_placeholder_integrity(
                    source_segment,
                    translated_segment,
                    placeholders_by_id.get(source_segment.segment_id, ()),
                )
            )
            issues.extend(validate_empty_translation(translated_segment))
            issues.extend(validate_number_integrity(source_segment, translated_segment))
            issues.extend(validate_url_integrity(source_segment, translated_segment))
            issues.extend(validate_code_integrity(source_segment, translated_segment))
            issues.extend(validate_citation_integrity(source_segment, translated_segment))
            issues.extend(
                validate_target_language(
                    translated_segment,
                    target_language=request.context.target_language,
                )
            )
            issues.extend(
                validate_untranslated_source_fragments(
                    source_segment,
                    translated_segment,
                    target_language=request.context.target_language,
                )
            )
            issues.extend(
                validate_suspicious_length(
                    source_segment,
                    translated_segment,
                    minimum_ratio=self._minimum_length_ratio,
                    maximum_ratio=self._maximum_length_ratio,
                )
            )
            issues.extend(validate_negation(source_segment, translated_segment))

        return ValidationReport(issues=tuple(issues))


def validate_translation(
    request: TranslationRequest,
    response: TranslationResponse,
    *,
    minimum_length_ratio: float = 0.5,
    maximum_length_ratio: float = 2.0,
) -> ValidationReport:
    return TranslationValidator(
        minimum_length_ratio=minimum_length_ratio,
        maximum_length_ratio=maximum_length_ratio,
    ).validate(request, response)


def validate_segment_mapping(
    request: TranslationRequest,
    response: TranslationResponse,
) -> tuple[ValidationIssue, ...]:
    expected = request.segment_ids
    observed = tuple(segment.segment_id for segment in response.segments)
    if observed == expected:
        return ()
    return (
        _critical(
            ValidationCode.SEGMENT_MAPPING_MISMATCH,
            None,
            "Translation response segment mapping does not match the request.",
        ),
    )


def validate_placeholder_integrity(
    source: TranslationRequestSegment,
    translated: TranslatedSegment,
    placeholders: Iterable[TranslationPlaceholder],
) -> tuple[ValidationIssue, ...]:
    expected = tuple(placeholder.placeholder for placeholder in placeholders)
    observed = tuple(_PLACEHOLDER_PATTERN.findall(translated.translated_text))
    malformed = tuple(
        token
        for token in _PLACEHOLDER_LIKE_PATTERN.findall(translated.translated_text)
        if _PLACEHOLDER_PATTERN.fullmatch(token) is None
    )
    if observed == expected and not malformed:
        return ()
    return (
        _critical(
            ValidationCode.PLACEHOLDER_MISMATCH,
            source.segment_id,
            "Translated text does not preserve the expected placeholder inventory.",
        ),
    )


def validate_number_integrity(
    source: TranslationRequestSegment,
    translated: TranslatedSegment,
) -> tuple[ValidationIssue, ...]:
    if _number_inventory(source.source_text) == _number_inventory(translated.translated_text):
        return ()
    return (
        _critical(
            ValidationCode.NUMBER_MISMATCH,
            source.segment_id,
            "Translated text does not preserve the source number inventory.",
        ),
    )


def validate_url_integrity(
    source: TranslationRequestSegment,
    translated: TranslatedSegment,
) -> tuple[ValidationIssue, ...]:
    if _url_inventory(source.source_text) == _url_inventory(translated.translated_text):
        return ()
    return (
        _critical(
            ValidationCode.URL_MISMATCH,
            source.segment_id,
            "Translated text does not preserve the source URL inventory.",
        ),
    )


def validate_code_integrity(
    source: TranslationRequestSegment,
    translated: TranslatedSegment,
) -> tuple[ValidationIssue, ...]:
    if _code_inventory(source.source_text) == _code_inventory(translated.translated_text):
        return ()
    return (
        _critical(
            ValidationCode.CODE_MISMATCH,
            source.segment_id,
            "Translated text does not preserve the source code inventory.",
        ),
    )


def validate_citation_integrity(
    source: TranslationRequestSegment,
    translated: TranslatedSegment,
) -> tuple[ValidationIssue, ...]:
    if _citation_inventory(source.source_text) == _citation_inventory(translated.translated_text):
        return ()
    return (
        _critical(
            ValidationCode.CITATION_MISMATCH,
            source.segment_id,
            "Translated text does not preserve the source citation inventory.",
        ),
    )


def validate_target_language(
    translated: TranslatedSegment,
    *,
    target_language: str,
) -> tuple[ValidationIssue, ...]:
    expected_markers, unexpected_markers = _language_markers(target_language)
    if expected_markers is None or unexpected_markers is None:
        return ()
    words = _words(_mask_placeholders(translated.translated_text))
    expected_score = sum(word in expected_markers for word in words)
    unexpected_score = sum(word in unexpected_markers for word in words)
    if unexpected_score < 2 or unexpected_score < expected_score + 2:
        return ()
    return (
        _warning(
            ValidationCode.TARGET_LANGUAGE_MISMATCH,
            translated.segment_id,
            "Translated text may not use the requested target language.",
        ),
    )


def validate_untranslated_source_fragments(
    source: TranslationRequestSegment,
    translated: TranslatedSegment,
    *,
    target_language: str,
) -> tuple[ValidationIssue, ...]:
    _, source_language_markers = _language_markers(target_language)
    if source_language_markers is None:
        return ()
    source_words = _words(_mask_placeholders(source.source_text))
    translated_words = _words(_mask_placeholders(translated.translated_text))
    if not source_words & source_language_markers & translated_words:
        return ()
    return (
        _warning(
            ValidationCode.UNTRANSLATED_SOURCE_FRAGMENT,
            translated.segment_id,
            "Translated text may contain an untranslated source-language fragment.",
        ),
    )


def validate_empty_translation(
    translated: TranslatedSegment,
) -> tuple[ValidationIssue, ...]:
    if translated.translated_text.strip():
        return ()
    return (
        _critical(
            ValidationCode.EMPTY_TRANSLATION,
            translated.segment_id,
            "Translated text must not be empty.",
        ),
    )


def validate_suspicious_length(
    source: TranslationRequestSegment,
    translated: TranslatedSegment,
    *,
    minimum_ratio: float = 0.5,
    maximum_ratio: float = 2.0,
) -> tuple[ValidationIssue, ...]:
    minimum_ratio, maximum_ratio = _length_bounds(minimum_ratio, maximum_ratio)
    source_length = _content_length(source.source_text)
    if source_length == 0:
        return ()
    ratio = _content_length(translated.translated_text) / source_length
    if minimum_ratio <= ratio <= maximum_ratio:
        return ()
    return (
        _warning(
            ValidationCode.SUSPICIOUS_LENGTH,
            source.segment_id,
            "Translated text has a suspicious source-to-target length ratio.",
        ),
    )


def validate_negation(
    source: TranslationRequestSegment,
    translated: TranslatedSegment,
) -> tuple[ValidationIssue, ...]:
    source_words = _words(_mask_placeholders(source.source_text))
    translated_words = _words(_mask_placeholders(translated.translated_text))
    source_negative = bool(source_words & (_ENGLISH_NEGATIONS | _INDONESIAN_NEGATIONS))
    translated_negative = bool(translated_words & (_ENGLISH_NEGATIONS | _INDONESIAN_NEGATIONS))
    if source_negative == translated_negative:
        return ()
    return (
        _warning(
            ValidationCode.NEGATION_MISMATCH,
            source.segment_id,
            "Translated text may have changed source negation.",
        ),
    )


def _placeholders_by_segment(
    placeholders: tuple[TranslationPlaceholder, ...],
) -> dict[str, tuple[TranslationPlaceholder, ...]]:
    result: dict[str, list[TranslationPlaceholder]] = {}
    for placeholder in placeholders:
        result.setdefault(placeholder.segment_id, []).append(placeholder)
    return {segment_id: tuple(values) for segment_id, values in result.items()}


def _number_inventory(text: str) -> Counter[str]:
    masked = _mask_placeholders(text)
    occupied: list[tuple[int, int]] = []
    inventory: list[str] = []
    for kind, pattern in (("VERSION", _VERSION_PATTERN), ("DATE", _DATE_PATTERN)):
        for match in pattern.finditer(masked):
            occupied.append(match.span())
            inventory.append(f"{kind}:{match.group(0).casefold()}")
    for match in _DECADE_PATTERN.finditer(masked):
        if not any(_overlaps(match.span(), span) for span in occupied):
            occupied.append(match.span())
            inventory.append(f"NUMBER::{match.group(1)}:")
    for match in _NUMBER_PATTERN.finditer(masked):
        if any(_overlaps(match.span(), span) for span in occupied):
            continue
        currency = (match.group("currency") or "").strip().casefold()
        percent = "%" if match.group("percent") else ""
        number = _canonical_number(match.group("number"))
        inventory.append(f"NUMBER:{currency}:{number}:{percent}")
    return Counter(inventory)


def _canonical_number(value: str) -> str:
    sign = ""
    unsigned = value
    if value[:1] in {"+", "-"}:
        sign, unsigned = value[0], value[1:]
    if "." in unsigned and "," in unsigned:
        decimal_offset = max(unsigned.rfind("."), unsigned.rfind(","))
        whole = re.sub(r"[.,]", "", unsigned[:decimal_offset])
        fraction = unsigned[decimal_offset + 1 :].rstrip("0")
        return sign + whole + (f".{fraction}" if fraction else "")
    parts = re.split(r"[.,]", unsigned)
    if len(parts) > 1 and all(len(part) == 3 for part in parts[1:]):
        return sign + "".join(parts)
    if len(parts) == 2:
        fraction = parts[1].rstrip("0")
        return sign + parts[0] + (f".{fraction}" if fraction else "")
    return sign + unsigned


def _url_inventory(text: str) -> Counter[str]:
    values: list[str] = []
    for match in _URL_PATTERN.finditer(_mask_placeholders(text)):
        value = match.group(0).rstrip(".,;:!?")
        while value.endswith(")") and value.count(")") > value.count("("):
            value = value[:-1]
        values.append(value)
    return Counter(values)


def _code_inventory(text: str) -> Counter[str]:
    masked = _mask_placeholders(text)
    patterns = (
        _FENCED_CODE_PATTERN,
        _INLINE_CODE_PATTERN,
        _METHOD_ENDPOINT_PATTERN,
        _API_ENDPOINT_PATTERN,
        _WINDOWS_PATH_PATTERN,
        _POSIX_PATH_PATTERN,
        _RELATIVE_PATH_PATTERN,
        _CODE_IDENTIFIER_PATTERN,
    )
    return Counter(match.group(0) for pattern in patterns for match in pattern.finditer(masked))


def _citation_inventory(text: str) -> Counter[str]:
    masked = _mask_placeholders(text)
    patterns = (
        _NUMERIC_CITATION_PATTERN,
        _AUTHOR_YEAR_CITATION_PATTERN,
        _LABELLED_CITATION_PATTERN,
    )
    return Counter(match.group(0) for pattern in patterns for match in pattern.finditer(masked))


def _language_markers(
    target_language: str,
) -> tuple[frozenset[str] | None, frozenset[str] | None]:
    normalized = target_language.strip().casefold().replace("_", "-").split("-", 1)[0]
    if normalized in {"id", "indonesian", "bahasa indonesia", "indonesia"}:
        return _INDONESIAN_MARKERS, _ENGLISH_MARKERS
    if normalized in {"en", "english", "inggris", "bahasa inggris"}:
        return _ENGLISH_MARKERS, _INDONESIAN_MARKERS
    return None, None


def _words(text: str) -> frozenset[str]:
    normalized = text.casefold().replace("n't", " not")
    return frozenset(_WORD_PATTERN.findall(normalized))


def _mask_placeholders(text: str) -> str:
    return _PLACEHOLDER_LIKE_PATTERN.sub(" ", text)


def _content_length(text: str) -> int:
    return len("".join(_mask_placeholders(text).split()))


def _overlaps(first: tuple[int, int], second: tuple[int, int]) -> bool:
    return first[0] < second[1] and second[0] < first[1]


def _length_bounds(minimum: float, maximum: float) -> tuple[float, float]:
    if (
        type(minimum) not in (int, float)
        or type(maximum) not in (int, float)
        or minimum <= 0
        or maximum <= minimum
    ):
        raise ValueError("Length ratio bounds must be positive and increasing.")
    return float(minimum), float(maximum)


def _critical(
    code: ValidationCode,
    segment_id: str | None,
    message: str,
) -> ValidationIssue:
    return ValidationIssue(code, ValidationSeverity.CRITICAL, segment_id, message)


def _warning(
    code: ValidationCode,
    segment_id: str | None,
    message: str,
) -> ValidationIssue:
    return ValidationIssue(code, ValidationSeverity.WARNING, segment_id, message)
