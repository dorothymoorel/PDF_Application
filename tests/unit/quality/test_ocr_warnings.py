import pytest
from transloka_quality.ocr import (
    OCRQualityGateError,
    OCRWarningPolicy,
    OCRWarningPolicyError,
    OCRWarningResolution,
    OCRWarningSeverity,
    OCRWarningStatus,
    OCRWarningType,
    collect_ocr_warnings,
)


def test_confidence_threshold_emits_high_and_critical_warnings() -> None:
    report = collect_ocr_warnings(
        3,
        confidence=0.74,
        block_confidences={"blk_low": 0.42, "blk_ok": 0.90},
    )

    assert [warning.warning_type for warning in report.warnings] == [
        OCRWarningType.LOW_CONFIDENCE,
        OCRWarningType.LOW_CONFIDENCE,
    ]
    assert report.warnings[0].severity is OCRWarningSeverity.HIGH
    assert report.warnings[1].severity is OCRWarningSeverity.CRITICAL
    assert report.translation_blocked is True
    assert report.can_translate is False

    clear = collect_ocr_warnings(3, confidence=0.75, block_confidences={"blk_ok": 0.90})
    assert clear.warnings == ()


def test_warnings_keep_page_scope_and_each_uncertainty_type() -> None:
    report = collect_ocr_warnings(
        7,
        page_id="pag_7",
        confidence=0.90,
        unresolved_blocks=("blk_unresolved",),
        reading_order_uncertainty=("OVERLAPPING_BLOCKS",),
        possible_text_in_image=True,
        table_uncertainty=("tbl_uncertain",),
    )

    assert {warning.warning_type for warning in report.warnings} == {
        OCRWarningType.UNRESOLVED_BLOCK,
        OCRWarningType.READING_ORDER_UNCERTAINTY,
        OCRWarningType.POSSIBLE_TEXT_IN_IMAGE,
        OCRWarningType.TABLE_UNCERTAINTY,
    }
    assert all(
        warning.page_number == 7 and warning.page_id == "pag_7" for warning in report.warnings
    )
    assert report.warnings[0].block_id == "blk_unresolved"
    assert (
        next(warning for warning in report.warnings if warning.table_id is not None).table_id
        == "tbl_uncertain"
    )


def test_resolution_preserves_history_and_unblocks_fixed_warning() -> None:
    report = collect_ocr_warnings(2, confidence=0.42)
    warning_id = report.warnings[0].id

    resolved = report.resolve(
        warning_id,
        resolution=OCRWarningResolution.USER_FIXED,
        note="Reviewer corrected the source text.",
    )

    assert len(resolved.warnings) == 1
    assert resolved.warnings[0].id == warning_id
    assert resolved.warnings[0].status is OCRWarningStatus.RESOLVED
    assert resolved.warnings[0].resolution is OCRWarningResolution.USER_FIXED
    assert resolved.translation_blocked is False


def test_non_overridable_unresolved_block_cannot_be_accepted() -> None:
    report = collect_ocr_warnings(4, unresolved_blocks=("blk_1",))

    with pytest.raises(OCRWarningPolicyError):
        report.resolve(
            report.warnings[0].id,
            resolution=OCRWarningResolution.USER_ACCEPTED,
        )
    with pytest.raises(OCRQualityGateError):
        report.raise_for_blocking()


def test_policy_can_lower_threshold_without_changing_page_scope() -> None:
    report = collect_ocr_warnings(
        5,
        confidence=0.64,
        policy=OCRWarningPolicy(low_confidence_threshold=0.65, critical_confidence_threshold=0.4),
    )

    assert len(report.warnings) == 1
    assert report.warnings[0].severity is OCRWarningSeverity.HIGH
    assert report.warnings[0].page_number == 5
