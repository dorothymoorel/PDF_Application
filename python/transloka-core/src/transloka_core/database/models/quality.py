from enum import StrEnum

from sqlalchemy import REAL, CheckConstraint, ForeignKey, Index, Integer, Text
from sqlalchemy.orm import Mapped, mapped_column
from transloka_core.database.models.application import Base
from transloka_core.database.models.warnings import (
    Warning,
    WarningResolutionType,
    WarningSeverity,
    WarningStatus,
    WarningType,
)


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


class QualityScopeType(StrEnum):
    PROJECT = "PROJECT"
    DOCUMENT = "DOCUMENT"
    PAGE = "PAGE"
    BLOCK = "BLOCK"
    SEGMENT = "SEGMENT"
    JOB = "JOB"
    EXPORT = "EXPORT"


class QualityCheckType(StrEnum):
    TEXT_EXTRACTION = "TEXT_EXTRACTION"
    OCR_CONFIDENCE = "OCR_CONFIDENCE"
    NUMERICAL_INTEGRITY = "NUMERICAL_INTEGRITY"
    TERMINOLOGY = "TERMINOLOGY"
    TRANSLATION_COMPLETENESS = "TRANSLATION_COMPLETENESS"
    PLACEHOLDER_INTEGRITY = "PLACEHOLDER_INTEGRITY"
    RECONSTRUCTION_LAYOUT = "RECONSTRUCTION_LAYOUT"
    FINAL_PDF = "FINAL_PDF"
    SOURCE_CHECKSUM = "SOURCE_CHECKSUM"
    ACTIVE_CONTENT = "ACTIVE_CONTENT"


def _sql_values(enum_type: type[StrEnum]) -> str:
    return ", ".join(f"'{member.value}'" for member in enum_type)


class QualityReport(Base):
    __tablename__ = "quality_reports"
    __table_args__ = (
        CheckConstraint("trim(id) <> ''", name="ck_quality_reports_id"),
        CheckConstraint(
            f"report_type IN ({_sql_values(QualityReportType)})",
            name="ck_quality_reports_type",
        ),
        CheckConstraint(
            f"status IN ({_sql_values(QualityReportStatus)})",
            name="ck_quality_reports_status",
        ),
        CheckConstraint(
            "overall_score IS NULL OR overall_score BETWEEN 0.0 AND 1.0",
            name="ck_quality_reports_score",
        ),
        CheckConstraint(
            "critical_warning_count >= 0 AND high_warning_count >= 0 AND "
            "medium_warning_count >= 0 AND low_warning_count >= 0",
            name="ck_quality_reports_warning_counts",
        ),
        CheckConstraint(
            "summary_json IS NULL OR json_valid(summary_json)",
            name="ck_quality_reports_summary_json_valid",
        ),
        CheckConstraint("trim(version) <> ''", name="ck_quality_reports_version"),
        CheckConstraint("trim(created_at) <> ''", name="ck_quality_reports_created_at"),
        {"sqlite_strict": True},
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    project_id: Mapped[str] = mapped_column(
        Text,
        ForeignKey("projects.id", ondelete="CASCADE"),
        nullable=False,
    )
    document_id: Mapped[str] = mapped_column(
        Text,
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
    )
    report_type: Mapped[str] = mapped_column(Text, nullable=False)
    version: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    overall_score: Mapped[float | None] = mapped_column(REAL, nullable=True)
    critical_warning_count: Mapped[int] = mapped_column(Integer, nullable=False)
    high_warning_count: Mapped[int] = mapped_column(Integer, nullable=False)
    medium_warning_count: Mapped[int] = mapped_column(Integer, nullable=False)
    low_warning_count: Mapped[int] = mapped_column(Integer, nullable=False)
    summary_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[str] = mapped_column(Text, nullable=False)


class QualityCheck(Base):
    __tablename__ = "quality_checks"
    __table_args__ = (
        CheckConstraint("trim(id) <> ''", name="ck_quality_checks_id"),
        CheckConstraint("trim(check_type) <> ''", name="ck_quality_checks_type"),
        CheckConstraint("trim(scope_type) <> ''", name="ck_quality_checks_scope_type"),
        CheckConstraint("trim(scope_id) <> ''", name="ck_quality_checks_scope_id"),
        CheckConstraint(
            f"status IN ({_sql_values(QualityCheckStatus)})",
            name="ck_quality_checks_status",
        ),
        CheckConstraint(
            "score IS NULL OR score BETWEEN 0.0 AND 1.0",
            name="ck_quality_checks_score",
        ),
        CheckConstraint(
            "details_json IS NULL OR json_valid(details_json)",
            name="ck_quality_checks_details_json_valid",
        ),
        CheckConstraint("trim(created_at) <> ''", name="ck_quality_checks_created_at"),
        {"sqlite_strict": True},
    )

    id: Mapped[str] = mapped_column(Text, primary_key=True)
    report_id: Mapped[str] = mapped_column(
        Text,
        ForeignKey("quality_reports.id", ondelete="CASCADE"),
        nullable=False,
    )
    check_type: Mapped[str] = mapped_column(Text, nullable=False)
    scope_type: Mapped[str] = mapped_column(Text, nullable=False)
    scope_id: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False)
    score: Mapped[float | None] = mapped_column(REAL, nullable=True)
    details_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[str] = mapped_column(Text, nullable=False)


Index(
    "ix_quality_reports_project_status",
    QualityReport.project_id,
    QualityReport.status,
)
Index(
    "ix_quality_reports_project_type",
    QualityReport.project_id,
    QualityReport.report_type,
)
Index("ix_quality_checks_report_status", QualityCheck.report_id, QualityCheck.status)
Index("ix_quality_checks_scope", QualityCheck.scope_type, QualityCheck.scope_id)


NON_OVERRIDEABLE_CRITICAL_WARNING_TYPES = frozenset(
    {
        WarningType.MISSING_TRANSLATED_SEGMENT.value,
        WarningType.PLACEHOLDER_RESTORATION_FAILED.value,
        WarningType.OUTPUT_PDF_CORRUPTED.value,
        WarningType.ORIGINAL_FILE_CHECKSUM_MISMATCH.value,
        WarningType.PATH_TRAVERSAL_DETECTED.value,
        WarningType.TABLE_STRUCTURE_CORRUPTED_CRITICAL.value,
        WarningType.CRITICAL_TEXT_CLIPPING.value,
        WarningType.CRITICAL_LAYOUT_COLLISION.value,
    }
)
NON_OVERRIDEABLE_CRITICAL_TYPES = NON_OVERRIDEABLE_CRITICAL_WARNING_TYPES


def is_non_overrideable_critical_warning(
    warning_type: str,
    severity: str,
) -> bool:
    """Return whether a warning must remain blocking until it is fixed."""

    return (
        severity == WarningSeverity.CRITICAL.value
        and warning_type in NON_OVERRIDEABLE_CRITICAL_WARNING_TYPES
    )


__all__ = [
    "NON_OVERRIDEABLE_CRITICAL_WARNING_TYPES",
    "NON_OVERRIDEABLE_CRITICAL_TYPES",
    "QualityCheck",
    "QualityCheckStatus",
    "QualityCheckType",
    "QualityReport",
    "QualityReportStatus",
    "QualityReportType",
    "QualityScopeType",
    "Warning",
    "WarningResolutionType",
    "WarningSeverity",
    "WarningStatus",
    "WarningType",
    "is_non_overrideable_critical_warning",
]
