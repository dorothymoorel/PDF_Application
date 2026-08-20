from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field, replace
from enum import StrEnum
from types import MappingProxyType
from uuid import NAMESPACE_URL, uuid5


class OCRWarningType(StrEnum):
    LOW_CONFIDENCE = "LOW_OCR_CONFIDENCE"
    UNRESOLVED_BLOCK = "UNRESOLVED_OCR_BLOCK"
    READING_ORDER_UNCERTAINTY = "READING_ORDER_UNCERTAIN"
    POSSIBLE_TEXT_IN_IMAGE = "POSSIBLE_TEXT_IN_IMAGE"
    TABLE_UNCERTAINTY = "TABLE_UNCERTAINTY"


class OCRWarningSeverity(StrEnum):
    INFO = "INFO"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class OCRWarningStatus(StrEnum):
    OPEN = "OPEN"
    RESOLVED = "RESOLVED"
    ACCEPTED = "ACCEPTED"
    FALSE_POSITIVE = "FALSE_POSITIVE"


class OCRWarningResolution(StrEnum):
    USER_FIXED = "USER_FIXED"
    USER_ACCEPTED = "USER_ACCEPTED"
    FALSE_POSITIVE = "FALSE_POSITIVE"


@dataclass(frozen=True, slots=True)
class OCRWarningPolicy:
    """Thresholds and blocking rules for OCR quality warnings."""

    low_confidence_threshold: float = 0.75
    critical_confidence_threshold: float = 0.50
    non_overridable_critical_types: frozenset[OCRWarningType] = frozenset(
        {OCRWarningType.UNRESOLVED_BLOCK}
    )

    def __post_init__(self) -> None:
        for name, value in (
            ("low_confidence_threshold", self.low_confidence_threshold),
            ("critical_confidence_threshold", self.critical_confidence_threshold),
        ):
            if not math.isfinite(value) or not 0.0 <= value <= 1.0:
                raise ValueError(f"{name} must be between 0 and 1.")
        if self.critical_confidence_threshold > self.low_confidence_threshold:
            raise ValueError("critical_confidence_threshold must not exceed the low threshold.")
        if any(type(value) is not OCRWarningType for value in self.non_overridable_critical_types):
            raise TypeError("Non-overridable warning types must be OCRWarningType values.")

    @property
    def confidence_threshold(self) -> float:
        return self.low_confidence_threshold


@dataclass(frozen=True, slots=True)
class OCRPageQuality:
    """Page-scoped OCR evidence from detection, normalization, and table mapping."""

    page_number: int
    page_id: str | None = None
    confidence: float | None = None
    block_confidences: Mapping[str, float] = field(default_factory=dict)
    unresolved_blocks: tuple[str, ...] = ()
    reading_order_uncertainty: tuple[str, ...] = ()
    possible_text_in_image: bool = False
    table_uncertainty: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.page_number < 1:
            raise ValueError("OCR page number must be at least 1.")
        if self.page_id is not None and not self.page_id.strip():
            raise ValueError("OCR page ID must be non-empty when supplied.")
        if self.confidence is not None:
            _validate_confidence(self.confidence, "OCR page confidence")
        normalized_confidences = dict(self.block_confidences)
        for block_id, confidence in normalized_confidences.items():
            if not block_id.strip():
                raise ValueError("OCR block IDs must be non-empty.")
            _validate_confidence(confidence, "OCR block confidence")
        object.__setattr__(self, "block_confidences", MappingProxyType(normalized_confidences))
        for field_name in ("unresolved_blocks", "reading_order_uncertainty", "table_uncertainty"):
            values = tuple(getattr(self, field_name))
            if any(not value.strip() for value in values):
                raise ValueError(f"{field_name} values must be non-empty.")
            object.__setattr__(self, field_name, values)


@dataclass(frozen=True, slots=True)
class OCRWarning:
    id: str
    warning_type: OCRWarningType
    severity: OCRWarningSeverity
    message: str
    page_number: int
    page_id: str | None = None
    block_id: str | None = None
    table_id: str | None = None
    status: OCRWarningStatus = OCRWarningStatus.OPEN
    resolution: OCRWarningResolution | None = None
    resolution_note: str | None = None

    def __post_init__(self) -> None:
        if not self.id.startswith("wrn_"):
            raise ValueError("OCR warning ID must use the wrn_ prefix.")
        if type(self.warning_type) is not OCRWarningType:
            raise TypeError("OCR warning type must be an OCRWarningType.")
        if type(self.severity) is not OCRWarningSeverity:
            raise TypeError("OCR warning severity must be an OCRWarningSeverity.")
        if self.page_number < 1:
            raise ValueError("OCR warning page number must be at least 1.")
        if not self.message.strip() or not self.message.isprintable():
            raise ValueError("OCR warning message must be printable and non-empty.")
        for value, label in (
            (self.page_id, "page ID"),
            (self.block_id, "block ID"),
            (self.table_id, "table ID"),
        ):
            if value is not None and not value.strip():
                raise ValueError(f"OCR warning {label} must be non-empty when supplied.")
        if self.status is OCRWarningStatus.OPEN and self.resolution is not None:
            raise ValueError("Open OCR warnings cannot have a resolution.")
        if self.status is not OCRWarningStatus.OPEN and self.resolution is None:
            raise ValueError("Resolved OCR warnings must record a resolution.")
        if self.resolution_note is not None and (
            not self.resolution_note.strip() or not self.resolution_note.isprintable()
        ):
            raise ValueError("OCR warning resolution note must be printable and non-empty.")


@dataclass(frozen=True, slots=True)
class OCRWarningReport:
    warnings: tuple[OCRWarning, ...]

    def __post_init__(self) -> None:
        if any(type(warning) is not OCRWarning for warning in self.warnings):
            raise TypeError("OCR warning reports must contain OCRWarning values.")
        identifiers = [warning.id for warning in self.warnings]
        if len(identifiers) != len(set(identifiers)):
            raise ValueError("OCR warning IDs must be unique within a report.")

    @property
    def open_warnings(self) -> tuple[OCRWarning, ...]:
        return tuple(
            warning for warning in self.warnings if warning.status is OCRWarningStatus.OPEN
        )

    @property
    def critical_warnings(self) -> tuple[OCRWarning, ...]:
        return tuple(
            warning
            for warning in self.open_warnings
            if warning.severity is OCRWarningSeverity.CRITICAL
        )

    @property
    def blocking_warnings(self) -> tuple[OCRWarning, ...]:
        return self.critical_warnings

    @property
    def translation_blocked(self) -> bool:
        return bool(self.blocking_warnings)

    @property
    def blocks_translation(self) -> bool:
        return self.translation_blocked

    @property
    def can_translate(self) -> bool:
        return not self.translation_blocked

    @property
    def accepted(self) -> bool:
        return not self.translation_blocked

    def resolve(
        self,
        warning_id: str,
        *,
        resolution: OCRWarningResolution,
        note: str | None = None,
        policy: OCRWarningPolicy | None = None,
    ) -> OCRWarningReport:
        """Resolve one warning while retaining it in the report history."""

        effective_policy = policy or OCRWarningPolicy()
        if type(resolution) is not OCRWarningResolution:
            raise TypeError("OCR warning resolution must be an OCRWarningResolution.")
        for index, warning in enumerate(self.warnings):
            if warning.id != warning_id:
                continue
            if warning.status is not OCRWarningStatus.OPEN:
                raise OCRWarningResolutionError("The OCR warning has already been resolved.")
            if (
                resolution is not OCRWarningResolution.USER_FIXED
                and warning.warning_type in effective_policy.non_overridable_critical_types
                and warning.severity is OCRWarningSeverity.CRITICAL
            ):
                raise OCRWarningPolicyError("This critical OCR warning cannot be overridden.")
            status = {
                OCRWarningResolution.USER_FIXED: OCRWarningStatus.RESOLVED,
                OCRWarningResolution.USER_ACCEPTED: OCRWarningStatus.ACCEPTED,
                OCRWarningResolution.FALSE_POSITIVE: OCRWarningStatus.FALSE_POSITIVE,
            }[resolution]
            updated = replace(
                warning,
                status=status,
                resolution=resolution,
                resolution_note=note,
            )
            values = list(self.warnings)
            values[index] = updated
            return OCRWarningReport(tuple(values))
        raise OCRWarningNotFoundError("The OCR warning was not found.")

    def raise_for_blocking(self) -> None:
        if self.translation_blocked:
            raise OCRQualityGateError(self.blocking_warnings)


class OCRWarningError(ValueError):
    pass


class OCRWarningNotFoundError(OCRWarningError):
    pass


class OCRWarningResolutionError(OCRWarningError):
    pass


class OCRWarningPolicyError(OCRWarningError):
    pass


class OCRQualityGateError(OCRWarningError):
    def __init__(self, warnings: tuple[OCRWarning, ...]) -> None:
        if not warnings or any(
            warning.severity is not OCRWarningSeverity.CRITICAL for warning in warnings
        ):
            raise ValueError("OCRQualityGateError requires critical warnings.")
        self.warnings = warnings
        codes = ", ".join(sorted({warning.warning_type.value for warning in warnings}))
        super().__init__(f"Critical OCR quality warnings block translation: {codes}.")


def assess_ocr_warnings(
    page: OCRPageQuality,
    *,
    policy: OCRWarningPolicy | None = None,
) -> OCRWarningReport:
    """Create deterministic, page-scoped OCR warnings from quality evidence."""

    effective_policy = policy or OCRWarningPolicy()
    warnings: list[OCRWarning] = []
    if page.confidence is not None and page.confidence < effective_policy.low_confidence_threshold:
        warnings.append(
            _warning(
                page,
                warning_type=OCRWarningType.LOW_CONFIDENCE,
                severity=_confidence_severity(page.confidence, effective_policy),
                scope="page",
                message=(
                    f"OCR confidence {_percent(page.confidence)} is below the "
                    f"{_percent(effective_policy.low_confidence_threshold)} threshold."
                ),
            )
        )
    for block_id, confidence in sorted(page.block_confidences.items()):
        if confidence < effective_policy.low_confidence_threshold:
            warnings.append(
                _warning(
                    page,
                    warning_type=OCRWarningType.LOW_CONFIDENCE,
                    severity=_confidence_severity(confidence, effective_policy),
                    scope=f"block:{block_id}",
                    block_id=block_id,
                    message=(
                        f"OCR block {block_id} confidence {_percent(confidence)} is below the "
                        f"{_percent(effective_policy.low_confidence_threshold)} threshold."
                    ),
                )
            )
    for block_id in page.unresolved_blocks:
        warnings.append(
            _warning(
                page,
                warning_type=OCRWarningType.UNRESOLVED_BLOCK,
                severity=OCRWarningSeverity.CRITICAL,
                scope=f"block:{block_id}",
                block_id=block_id,
                message=f"OCR block {block_id} has no resolved source text.",
            )
        )
    if page.reading_order_uncertainty:
        reasons = ", ".join(page.reading_order_uncertainty)
        warnings.append(
            _warning(
                page,
                warning_type=OCRWarningType.READING_ORDER_UNCERTAINTY,
                severity=OCRWarningSeverity.HIGH,
                scope=f"reading-order:{reasons}",
                message=f"Reading order is uncertain: {reasons}.",
            )
        )
    if page.possible_text_in_image:
        warnings.append(
            _warning(
                page,
                warning_type=OCRWarningType.POSSIBLE_TEXT_IN_IMAGE,
                severity=OCRWarningSeverity.MEDIUM,
                scope="possible-text-in-image",
                message="An image region may contain text that OCR did not resolve.",
            )
        )
    for table_id in page.table_uncertainty:
        warnings.append(
            _warning(
                page,
                warning_type=OCRWarningType.TABLE_UNCERTAINTY,
                severity=OCRWarningSeverity.HIGH,
                scope=f"table:{table_id}",
                table_id=table_id,
                message=f"OCR table {table_id} has uncertain structure.",
            )
        )
    return OCRWarningReport(tuple(warnings))


def collect_ocr_warnings(
    page_number: int,
    *,
    page_id: str | None = None,
    confidence: float | None = None,
    block_confidences: Mapping[str, float] | None = None,
    unresolved_blocks: Sequence[str] = (),
    reading_order_uncertainty: Sequence[str] = (),
    possible_text_in_image: bool = False,
    table_uncertainty: Sequence[str] = (),
    policy: OCRWarningPolicy | None = None,
) -> OCRWarningReport:
    """Convenience wrapper for callers that have individual OCR measurements."""

    return assess_ocr_warnings(
        OCRPageQuality(
            page_number=page_number,
            page_id=page_id,
            confidence=confidence,
            block_confidences=block_confidences or {},
            unresolved_blocks=tuple(unresolved_blocks),
            reading_order_uncertainty=tuple(reading_order_uncertainty),
            possible_text_in_image=possible_text_in_image,
            table_uncertainty=tuple(table_uncertainty),
        ),
        policy=policy,
    )


def _warning(
    page: OCRPageQuality,
    *,
    warning_type: OCRWarningType,
    severity: OCRWarningSeverity,
    scope: str,
    message: str,
    block_id: str | None = None,
    table_id: str | None = None,
) -> OCRWarning:
    identity = uuid5(
        NAMESPACE_URL,
        f"ocr-warning:{page.page_number}:{page.page_id or ''}:{warning_type.value}:{scope}",
    )
    return OCRWarning(
        id=f"wrn_{identity}",
        warning_type=warning_type,
        severity=severity,
        message=message,
        page_number=page.page_number,
        page_id=page.page_id,
        block_id=block_id,
        table_id=table_id,
    )


def _confidence_severity(confidence: float, policy: OCRWarningPolicy) -> OCRWarningSeverity:
    return (
        OCRWarningSeverity.CRITICAL
        if confidence < policy.critical_confidence_threshold
        else OCRWarningSeverity.HIGH
    )


def _percent(value: float) -> str:
    return f"{round(value * 100)}%"


def _validate_confidence(value: float, label: str) -> None:
    if not math.isfinite(value) or not 0.0 <= value <= 1.0:
        raise ValueError(f"{label} must be between 0 and 1.")


__all__ = [
    "OCRPageQuality",
    "OCRQualityGateError",
    "OCRWarning",
    "OCRWarningNotFoundError",
    "OCRWarningPolicy",
    "OCRWarningPolicyError",
    "OCRWarningReport",
    "OCRWarningResolution",
    "OCRWarningResolutionError",
    "OCRWarningSeverity",
    "OCRWarningStatus",
    "OCRWarningType",
    "assess_ocr_warnings",
    "collect_ocr_warnings",
]
