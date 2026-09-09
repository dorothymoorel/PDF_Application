from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class ValidationSeverity(StrEnum):
    WARNING = "WARNING"
    CRITICAL = "CRITICAL"


class ValidationCode(StrEnum):
    NMT_REVIEW_REQUIRED = "NMT_REVIEW_REQUIRED"
    NMT_LOCAL_FALLBACK_USED = "NMT_LOCAL_FALLBACK_USED"
    SEGMENT_MAPPING_MISMATCH = "SEGMENT_MAPPING_MISMATCH"
    PLACEHOLDER_MISMATCH = "PLACEHOLDER_MISMATCH"
    NUMBER_MISMATCH = "NUMBER_MISMATCH"
    URL_MISMATCH = "URL_MISMATCH"
    CODE_MISMATCH = "CODE_MISMATCH"
    CITATION_MISMATCH = "CITATION_MISMATCH"
    TARGET_LANGUAGE_MISMATCH = "TARGET_LANGUAGE_MISMATCH"
    UNTRANSLATED_SOURCE_FRAGMENT = "UNTRANSLATED_SOURCE_FRAGMENT"
    EMPTY_TRANSLATION = "EMPTY_TRANSLATION"
    SUSPICIOUS_LENGTH = "SUSPICIOUS_LENGTH"
    NEGATION_MISMATCH = "NEGATION_MISMATCH"


@dataclass(frozen=True, slots=True)
class ValidationIssue:
    code: ValidationCode
    severity: ValidationSeverity
    segment_id: str | None
    message: str

    def __post_init__(self) -> None:
        if type(self.code) is not ValidationCode:
            raise TypeError("Validation issue code must be a ValidationCode.")
        if type(self.severity) is not ValidationSeverity:
            raise TypeError("Validation issue severity must be a ValidationSeverity.")
        if self.segment_id is not None and (
            type(self.segment_id) is not str or not self.segment_id.strip()
        ):
            raise ValueError("Validation issue segment ID must be non-empty or None.")
        if type(self.message) is not str or not self.message.strip():
            raise ValueError("Validation issue message must be non-empty.")


@dataclass(frozen=True, slots=True)
class ValidationReport:
    issues: tuple[ValidationIssue, ...]

    def __post_init__(self) -> None:
        if type(self.issues) is not tuple or any(
            type(issue) is not ValidationIssue for issue in self.issues
        ):
            raise TypeError("Validation report must contain ValidationIssue values.")

    @property
    def passed(self) -> bool:
        return not self.issues

    @property
    def accepted(self) -> bool:
        return not any(issue.severity is ValidationSeverity.CRITICAL for issue in self.issues)

    @property
    def critical_issues(self) -> tuple[ValidationIssue, ...]:
        return tuple(
            issue for issue in self.issues if issue.severity is ValidationSeverity.CRITICAL
        )

    @property
    def warnings(self) -> tuple[ValidationIssue, ...]:
        return tuple(issue for issue in self.issues if issue.severity is ValidationSeverity.WARNING)

    def raise_for_critical(self) -> None:
        if self.critical_issues:
            raise TranslationIntegrityError(self.critical_issues)


class TranslationIntegrityError(ValueError):
    def __init__(self, issues: tuple[ValidationIssue, ...]) -> None:
        if not issues or any(issue.severity is not ValidationSeverity.CRITICAL for issue in issues):
            raise ValueError("TranslationIntegrityError requires critical validation issues.")
        self.issues = issues
        codes = ", ".join(sorted({issue.code.value for issue in issues}))
        super().__init__(f"Critical translation integrity failure: {codes}.")
