from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from enum import StrEnum
from types import MappingProxyType


class QualityReportType(StrEnum):
    EXTRACTION = "EXTRACTION"
    OCR = "OCR"
    TRANSLATION = "TRANSLATION"
    TERMINOLOGY = "TERMINOLOGY"
    RECONSTRUCTION = "RECONSTRUCTION"
    FINAL_EXPORT = "FINAL_EXPORT"


class QualityReportStatus(StrEnum):
    NOT_RUN = "NOT_RUN"
    RUNNING = "RUNNING"
    PASSED = "PASSED"
    PASSED_WITH_WARNINGS = "PASSED_WITH_WARNINGS"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


class QualityCheckStatus(StrEnum):
    NOT_RUN = "NOT_RUN"
    RUNNING = "RUNNING"
    PASSED = "PASSED"
    PASSED_WITH_WARNINGS = "PASSED_WITH_WARNINGS"
    FAILED = "FAILED"
    SKIPPED = "SKIPPED"


class QualitySeverity(StrEnum):
    INFO = "INFO"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class QualityWarningStatus(StrEnum):
    OPEN = "OPEN"
    RESOLVED = "RESOLVED"
    ACCEPTED = "ACCEPTED"
    FALSE_POSITIVE = "FALSE_POSITIVE"
    IGNORED_BY_POLICY = "IGNORED_BY_POLICY"


class QualityWarningResolution(StrEnum):
    AUTO_FIXED = "AUTO_FIXED"
    USER_FIXED = "USER_FIXED"
    USER_ACCEPTED = "USER_ACCEPTED"
    FALSE_POSITIVE = "FALSE_POSITIVE"
    IGNORED_BY_POLICY = "IGNORED_BY_POLICY"
    REQUIRES_REPROCESSING = "REQUIRES_REPROCESSING"


NON_OVERRIDEABLE_CRITICAL_WARNING_TYPES = frozenset(
    {
        "MISSING_TRANSLATED_SEGMENT",
        "PLACEHOLDER_RESTORATION_FAILED",
        "OUTPUT_PDF_CORRUPTED",
        "ORIGINAL_FILE_CHECKSUM_MISMATCH",
        "PATH_TRAVERSAL_DETECTED",
        "TABLE_STRUCTURE_CORRUPTED_CRITICAL",
        "CRITICAL_TEXT_CLIPPING",
        "CRITICAL_LAYOUT_COLLISION",
    }
)
NON_OVERRIDEABLE_CRITICAL_TYPES = NON_OVERRIDEABLE_CRITICAL_WARNING_TYPES


class QualityReportError(ValueError):
    pass


class QualityWarningNotFoundError(QualityReportError):
    pass


class QualityWarningResolutionError(QualityReportError):
    pass


class QualityWarningPolicyError(QualityReportError):
    pass


class QualityGateError(QualityReportError):
    def __init__(self, warnings: tuple[QualityWarning, ...]) -> None:
        if not warnings or any(
            warning.severity is not QualitySeverity.CRITICAL for warning in warnings
        ):
            raise ValueError("QualityGateError requires critical warnings.")
        self.warnings = warnings
        super().__init__("Critical quality warnings block completion.")


@dataclass(frozen=True, slots=True)
class QualityWarning:
    id: str
    warning_type: str
    severity: QualitySeverity
    message: str
    status: QualityWarningStatus = QualityWarningStatus.OPEN
    resolution: QualityWarningResolution | None = None
    resolution_note: str | None = None
    details: Mapping[str, object] = MappingProxyType({})

    def __post_init__(self) -> None:
        if not self.id.strip():
            raise ValueError("Quality warning ID must be non-empty.")
        if not self.warning_type.strip():
            raise ValueError("Quality warning type must be non-empty.")
        if type(self.severity) is not QualitySeverity:
            raise TypeError("Quality warning severity must be a QualitySeverity.")
        if type(self.status) is not QualityWarningStatus:
            raise TypeError("Quality warning status must be a QualityWarningStatus.")
        if self.resolution is not None and type(self.resolution) is not QualityWarningResolution:
            raise TypeError("Quality warning resolution must be a QualityWarningResolution.")
        if not self.message.strip() or not self.message.isprintable():
            raise ValueError("Quality warning message must be printable and non-empty.")
        if self.status is QualityWarningStatus.OPEN and self.resolution is not None:
            raise ValueError("Open quality warnings cannot have a resolution.")
        if self.status is not QualityWarningStatus.OPEN and self.resolution is None:
            raise ValueError("Resolved quality warnings must record a resolution.")
        if self.resolution_note is not None and (
            not self.resolution_note.strip() or not self.resolution_note.isprintable()
        ):
            raise ValueError("Quality warning resolution note must be printable and non-empty.")
        if not isinstance(self.details, Mapping):
            raise TypeError("Quality warning details must be a mapping.")
        object.__setattr__(self, "details", MappingProxyType(dict(self.details)))


@dataclass(frozen=True, slots=True)
class QualityCheck:
    id: str
    check_type: str
    scope_type: str
    scope_id: str
    status: QualityCheckStatus
    score: float | None = None
    details: Mapping[str, object] = MappingProxyType({})

    def __post_init__(self) -> None:
        if not self.id.strip() or not self.check_type.strip():
            raise ValueError("Quality check ID and type must be non-empty.")
        if not self.scope_type.strip() or not self.scope_id.strip():
            raise ValueError("Quality check scope must be non-empty.")
        if type(self.status) is not QualityCheckStatus:
            raise TypeError("Quality check status must be a QualityCheckStatus.")
        if self.score is not None and not 0.0 <= self.score <= 1.0:
            raise ValueError("Quality check score must be between 0 and 1.")
        if not isinstance(self.details, Mapping):
            raise TypeError("Quality check details must be a mapping.")
        object.__setattr__(self, "details", MappingProxyType(dict(self.details)))


@dataclass(frozen=True, slots=True)
class QualityReport:
    report_type: QualityReportType
    version: str
    checks: tuple[QualityCheck, ...] = ()
    warnings: tuple[QualityWarning, ...] = ()
    overall_score: float | None = None
    status: QualityReportStatus | None = None

    def __post_init__(self) -> None:
        if type(self.report_type) is not QualityReportType:
            raise TypeError("Quality report type must be a QualityReportType.")
        if not self.version.strip():
            raise ValueError("Quality report version must be non-empty.")
        if self.overall_score is not None and not 0.0 <= self.overall_score <= 1.0:
            raise ValueError("Quality report score must be between 0 and 1.")
        if any(type(check) is not QualityCheck for check in self.checks):
            raise TypeError("Quality reports must contain QualityCheck values.")
        if any(type(warning) is not QualityWarning for warning in self.warnings):
            raise TypeError("Quality reports must contain QualityWarning values.")
        identifiers = [check.id for check in self.checks]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("Quality check IDs must be unique within a report.")
        identifiers = [warning.id for warning in self.warnings]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("Quality warning IDs must be unique within a report.")
        if self.status is not None and type(self.status) is not QualityReportStatus:
            raise TypeError("Quality report status must be a QualityReportStatus.")

    @property
    def effective_status(self) -> QualityReportStatus:
        if self.status is not None:
            return self.status
        if any(check.status is QualityCheckStatus.FAILED for check in self.checks):
            return QualityReportStatus.FAILED
        if self.blocking_warnings:
            return QualityReportStatus.FAILED
        if any(warning.status is QualityWarningStatus.OPEN for warning in self.warnings):
            return QualityReportStatus.PASSED_WITH_WARNINGS
        if any(check.status is QualityCheckStatus.PASSED for check in self.checks):
            return QualityReportStatus.PASSED
        return QualityReportStatus.NOT_RUN

    @property
    def severity_counts(self) -> dict[QualitySeverity, int]:
        return {
            severity: sum(warning.severity is severity for warning in self.warnings)
            for severity in QualitySeverity
        }

    @property
    def open_severity_counts(self) -> dict[QualitySeverity, int]:
        return {
            severity: sum(
                warning.severity is severity and warning.status is QualityWarningStatus.OPEN
                for warning in self.warnings
            )
            for severity in QualitySeverity
        }

    @property
    def critical_warnings(self) -> tuple[QualityWarning, ...]:
        return tuple(
            warning
            for warning in self.warnings
            if warning.severity is QualitySeverity.CRITICAL
            and warning.status is QualityWarningStatus.OPEN
        )

    @property
    def blocking_warnings(self) -> tuple[QualityWarning, ...]:
        return self.critical_warnings

    @property
    def blocks_completion(self) -> bool:
        return bool(self.blocking_warnings)

    def resolve_warning(
        self,
        warning_id: str,
        *,
        resolution: QualityWarningResolution,
        note: str | None = None,
    ) -> QualityReport:
        if type(resolution) is not QualityWarningResolution:
            raise TypeError("Quality warning resolution must be a QualityWarningResolution.")
        for index, warning in enumerate(self.warnings):
            if warning.id != warning_id:
                continue
            if warning.status is not QualityWarningStatus.OPEN:
                raise QualityWarningResolutionError(
                    "The quality warning has already been resolved."
                )
            if (
                resolution is not QualityWarningResolution.USER_FIXED
                and warning.severity is QualitySeverity.CRITICAL
                and warning.warning_type in NON_OVERRIDEABLE_CRITICAL_WARNING_TYPES
            ):
                raise QualityWarningPolicyError(
                    "This critical quality warning cannot be overridden."
                )
            status = {
                QualityWarningResolution.AUTO_FIXED: QualityWarningStatus.RESOLVED,
                QualityWarningResolution.USER_FIXED: QualityWarningStatus.RESOLVED,
                QualityWarningResolution.USER_ACCEPTED: QualityWarningStatus.ACCEPTED,
                QualityWarningResolution.FALSE_POSITIVE: QualityWarningStatus.FALSE_POSITIVE,
                QualityWarningResolution.IGNORED_BY_POLICY: QualityWarningStatus.IGNORED_BY_POLICY,
                QualityWarningResolution.REQUIRES_REPROCESSING: QualityWarningStatus.OPEN,
            }[resolution]
            if status is QualityWarningStatus.OPEN:
                raise QualityWarningResolutionError(
                    "Reprocessing is not a terminal warning resolution."
                )
            updated = replace(
                warning,
                status=status,
                resolution=resolution,
                resolution_note=note,
            )
            values = list(self.warnings)
            values[index] = updated
            return replace(self, warnings=tuple(values))
        raise QualityWarningNotFoundError("The quality warning was not found.")

    def raise_for_blocking(self) -> None:
        if self.blocking_warnings:
            raise QualityGateError(self.blocking_warnings)


__all__ = [
    "NON_OVERRIDEABLE_CRITICAL_WARNING_TYPES",
    "NON_OVERRIDEABLE_CRITICAL_TYPES",
    "QualityCheck",
    "QualityCheckStatus",
    "QualityGateError",
    "QualityReport",
    "QualityReportError",
    "QualityReportStatus",
    "QualityReportType",
    "QualitySeverity",
    "QualityWarning",
    "QualityWarningNotFoundError",
    "QualityWarningPolicyError",
    "QualityWarningResolution",
    "QualityWarningResolutionError",
    "QualityWarningStatus",
]
