import pytest
from transloka_quality.reports import (
    QualityCheck,
    QualityCheckStatus,
    QualityGateError,
    QualityReport,
    QualityReportStatus,
    QualityReportType,
    QualitySeverity,
    QualityWarning,
    QualityWarningPolicyError,
    QualityWarningResolution,
)


def _warning(
    warning_id: str,
    severity: QualitySeverity,
    warning_type: str = "TERM_INCONSISTENT",
) -> QualityWarning:
    return QualityWarning(
        id=warning_id,
        warning_type=warning_type,
        severity=severity,
        message=f"Warning {warning_id}",
    )


def test_report_contains_checks_and_warning_history() -> None:
    report = QualityReport(
        report_type=QualityReportType.TRANSLATION,
        version="qa_0.1",
        checks=(
            QualityCheck(
                id="check_1",
                check_type="NUMERICAL_INTEGRITY",
                scope_type="DOCUMENT",
                scope_id="doc_1",
                status=QualityCheckStatus.PASSED,
                score=1.0,
            ),
        ),
        warnings=(_warning("warning_1", QualitySeverity.MEDIUM),),
    )

    assert report.effective_status is QualityReportStatus.PASSED_WITH_WARNINGS
    assert report.checks[0].scope_id == "doc_1"
    assert report.warnings[0].id == "warning_1"


def test_report_counts_warning_severity_and_open_warnings() -> None:
    report = QualityReport(
        report_type=QualityReportType.OCR,
        version="qa_0.1",
        warnings=(
            _warning("warning_1", QualitySeverity.CRITICAL, "UNRESOLVED_BLOCK"),
            _warning("warning_2", QualitySeverity.HIGH),
            _warning("warning_3", QualitySeverity.HIGH),
        ),
    )

    assert report.severity_counts[QualitySeverity.CRITICAL] == 1
    assert report.severity_counts[QualitySeverity.HIGH] == 2
    assert report.open_severity_counts[QualitySeverity.HIGH] == 2
    assert report.blocks_completion


def test_resolving_warning_keeps_the_warning_in_history() -> None:
    report = QualityReport(
        report_type=QualityReportType.TERMINOLOGY,
        version="qa_0.1",
        warnings=(_warning("warning_1", QualitySeverity.MEDIUM),),
    )

    resolved = report.resolve_warning(
        "warning_1",
        resolution=QualityWarningResolution.USER_FIXED,
        note="Term corrected.",
    )

    assert len(resolved.warnings) == 1
    assert resolved.warnings[0].id == "warning_1"
    assert resolved.warnings[0].resolution is QualityWarningResolution.USER_FIXED


def test_non_overrideable_critical_warning_blocks_acceptance() -> None:
    report = QualityReport(
        report_type=QualityReportType.FINAL_EXPORT,
        version="qa_0.1",
        warnings=(_warning("warning_1", QualitySeverity.CRITICAL, "OUTPUT_PDF_CORRUPTED"),),
    )

    assert report.blocks_completion
    with pytest.raises(QualityGateError):
        report.raise_for_blocking()
    with pytest.raises(QualityWarningPolicyError):
        report.resolve_warning(
            "warning_1",
            resolution=QualityWarningResolution.USER_ACCEPTED,
        )

    resolved = report.resolve_warning(
        "warning_1",
        resolution=QualityWarningResolution.USER_FIXED,
    )
    assert resolved.blocking_warnings == ()
