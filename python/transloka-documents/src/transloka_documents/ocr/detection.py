from __future__ import annotations

import math
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from typing import Protocol

from transloka_document_ir.enums import PageType

from transloka_documents.extraction.models import ExtractedPage, TextGeometry


class _GeometryProvider(Protocol):
    source_geometry: TextGeometry


@dataclass(frozen=True, slots=True)
class ScannedPageDetectionSettings:
    """Thresholds used to decide whether a page should be sent to OCR.

    The detector intentionally requires a page-sized image (or an explicit
    text-bearing image signal) before treating a page with no native text as
    scanned. This prevents decorative illustrations from creating needless OCR
    jobs.
    """

    low_text_coverage_threshold: float = 0.05
    image_dominance_threshold: float = 0.65
    full_page_image_threshold: float = 0.80
    poor_native_extraction_threshold: float = 0.60
    minimum_image_threshold: float = 0.02

    def __post_init__(self) -> None:
        thresholds = (
            self.low_text_coverage_threshold,
            self.image_dominance_threshold,
            self.full_page_image_threshold,
            self.poor_native_extraction_threshold,
            self.minimum_image_threshold,
        )
        if any(not math.isfinite(value) or not 0.0 <= value <= 1.0 for value in thresholds):
            raise ValueError("Page detection thresholds must be finite values between 0 and 1.")
        if self.minimum_image_threshold > self.image_dominance_threshold:
            raise ValueError(
                "Minimum image threshold must not exceed the image dominance threshold."
            )
        if self.full_page_image_threshold < self.image_dominance_threshold:
            raise ValueError(
                "Full-page image threshold must be at least the image dominance threshold."
            )

    @property
    def text_coverage_threshold(self) -> float:
        """Compatibility name for callers that use a shorter threshold name."""

        return self.low_text_coverage_threshold

    @property
    def native_confidence_threshold(self) -> float:
        """Compatibility name for the poor-native-extraction threshold."""

        return self.poor_native_extraction_threshold


@dataclass(frozen=True, slots=True)
class ScannedPageSignals:
    """Auditable evidence used by :class:`ScannedPageDetector`."""

    has_text: bool
    no_text: bool
    text_coverage: float
    low_text_coverage: bool
    image_coverage: float
    image_dominant: bool
    full_page_image: bool
    poor_native_extraction: bool
    native_confidence: float | None
    image_has_text_signal: bool

    @property
    def no_text_signal(self) -> bool:
        return self.no_text


@dataclass(frozen=True, slots=True)
class ScannedPageDetection:
    """Classification and OCR decision for one extracted page."""

    page_number: int
    page_type: PageType
    requires_ocr: bool
    confidence: float
    signals: ScannedPageSignals
    reasons: tuple[str, ...]

    @property
    def needs_ocr(self) -> bool:
        return self.requires_ocr

    @property
    def classification(self) -> PageType:
        return self.page_type

    @property
    def reason_codes(self) -> tuple[str, ...]:
        return self.reasons


@dataclass(frozen=True, slots=True)
class ScannedPageDetector:
    settings: ScannedPageDetectionSettings = ScannedPageDetectionSettings()

    def detect(
        self,
        page: ExtractedPage,
        *,
        image_geometries: Sequence[TextGeometry | _GeometryProvider] = (),
        image_coverage: float | None = None,
        native_confidence: float | None = None,
        native_extraction_confidence: float | None = None,
        image_has_text_signal: bool = False,
        text_coverage: float | None = None,
    ) -> ScannedPageDetection:
        """Classify one extracted page and decide whether OCR is required.

        ``image_coverage`` is useful when a renderer or PDF parser already
        calculated an occlusion ratio. Otherwise it is calculated from image
        geometries (including ``ExtractedAsset`` instances). The optional native
        confidence is deliberately caller-supplied because native extraction
        does not currently produce a confidence score itself.
        """

        if native_confidence is not None and native_extraction_confidence is not None:
            if native_confidence != native_extraction_confidence:
                raise ValueError("Native confidence values must agree when both are supplied.")
        effective_native_confidence = (
            native_confidence if native_confidence is not None else native_extraction_confidence
        )
        _validate_confidence(effective_native_confidence, "Native extraction confidence")
        _validate_ratio(text_coverage, "Text coverage")
        _validate_ratio(image_coverage, "Image coverage")

        effective_text_coverage = (
            _page_text_coverage(page) if text_coverage is None else text_coverage
        )
        effective_image_coverage = (
            _geometry_coverage(
                page.width_points,
                page.height_points,
                (_source_geometry(image) for image in image_geometries),
            )
            if image_coverage is None
            else image_coverage
        )
        has_text = any(word.normalized_text.strip() for word in page.words)
        low_text_coverage = effective_text_coverage < self.settings.low_text_coverage_threshold
        no_text = not has_text
        image_dominant = effective_image_coverage >= self.settings.image_dominance_threshold
        full_page_image = effective_image_coverage >= self.settings.full_page_image_threshold
        poor_native_extraction = (
            effective_native_confidence is not None
            and effective_native_confidence < self.settings.poor_native_extraction_threshold
        )
        signals = ScannedPageSignals(
            has_text=has_text,
            no_text=no_text,
            text_coverage=effective_text_coverage,
            low_text_coverage=low_text_coverage,
            image_coverage=effective_image_coverage,
            image_dominant=image_dominant,
            full_page_image=full_page_image,
            poor_native_extraction=poor_native_extraction,
            native_confidence=effective_native_confidence,
            image_has_text_signal=image_has_text_signal,
        )
        page_type, requires_ocr, reasons = _classify(signals, self.settings)
        return ScannedPageDetection(
            page_number=page.page_number,
            page_type=page_type,
            requires_ocr=requires_ocr,
            confidence=_confidence(signals, page_type, self.settings),
            signals=signals,
            reasons=reasons,
        )


def detect_scanned_page(
    page: ExtractedPage,
    *,
    image_geometries: Sequence[TextGeometry | _GeometryProvider] = (),
    image_coverage: float | None = None,
    native_confidence: float | None = None,
    native_extraction_confidence: float | None = None,
    image_has_text_signal: bool = False,
    text_coverage: float | None = None,
    settings: ScannedPageDetectionSettings | None = None,
) -> ScannedPageDetection:
    """Functional convenience wrapper around :class:`ScannedPageDetector`."""

    return ScannedPageDetector(settings or ScannedPageDetectionSettings()).detect(
        page,
        image_geometries=image_geometries,
        image_coverage=image_coverage,
        native_confidence=native_confidence,
        native_extraction_confidence=native_extraction_confidence,
        image_has_text_signal=image_has_text_signal,
        text_coverage=text_coverage,
    )


def _classify(
    signals: ScannedPageSignals,
    settings: ScannedPageDetectionSettings,
) -> tuple[PageType, bool, tuple[str, ...]]:
    reasons: list[str] = []
    if signals.no_text:
        reasons.append("NO_TEXT")
    if signals.low_text_coverage:
        reasons.append("LOW_TEXT_COVERAGE")
    if signals.image_dominant:
        reasons.append("IMAGE_DOMINANT")
    if signals.poor_native_extraction:
        reasons.append("POOR_NATIVE_EXTRACTION")
    if signals.image_has_text_signal:
        reasons.append("IMAGE_TEXT_SIGNAL")

    image_present = signals.image_coverage >= settings.minimum_image_threshold
    if signals.no_text:
        # A full-page image is the strongest safe scan signal. A caller may
        # explicitly identify text-bearing imagery when the image is smaller.
        scanned = signals.full_page_image or (
            image_present and signals.image_has_text_signal and signals.image_dominant
        )
        if scanned:
            reasons.append(
                "FULL_PAGE_SCAN_IMAGE" if signals.full_page_image else "IMAGE_TEXT_SIGNAL"
            )
            return PageType.SCANNED, True, tuple(dict.fromkeys(reasons))
        reasons.append("NO_NATIVE_TEXT")
        reasons.append("NO_TEXT_SIGNAL_FOR_OCR")
        return PageType.IMAGE_ONLY, False, tuple(dict.fromkeys(reasons))

    hybrid = signals.image_dominant or (signals.low_text_coverage and image_present)
    if hybrid:
        reasons.append("TEXT_AND_IMAGE_CONTENT")
        return PageType.HYBRID, True, tuple(dict.fromkeys(reasons))

    reasons.append("NATIVE_TEXT_CONTENT")
    return PageType.DIGITAL, False, tuple(dict.fromkeys(reasons))


def _confidence(
    signals: ScannedPageSignals,
    page_type: PageType,
    settings: ScannedPageDetectionSettings,
) -> float:
    if page_type is PageType.SCANNED:
        evidence = [signals.image_coverage]
        if signals.native_confidence is not None:
            evidence.append(1.0 - signals.native_confidence)
        return _bounded(sum(evidence) / len(evidence))
    if page_type is PageType.HYBRID:
        text_evidence = min(
            1.0,
            signals.text_coverage / max(settings.low_text_coverage_threshold, 1e-9),
        )
        return _bounded((signals.image_coverage + text_evidence) / 2.0)
    if page_type is PageType.DIGITAL:
        return _bounded(max(signals.text_coverage, 1.0 - signals.image_coverage))
    return _bounded(max(1.0 - signals.image_coverage, 1.0 - signals.text_coverage))


def _page_text_coverage(page: ExtractedPage) -> float:
    return _geometry_coverage(
        page.width_points,
        page.height_points,
        (word.geometry for word in page.words if word.normalized_text.strip()),
    )


def _geometry_coverage(
    page_width: float,
    page_height: float,
    geometries: Iterable[TextGeometry],
) -> float:
    if not math.isfinite(page_width) or not math.isfinite(page_height):
        raise ValueError("Page dimensions must be finite.")
    if page_width <= 0 or page_height <= 0:
        raise ValueError("Page dimensions must be positive.")
    rectangles: list[tuple[float, float, float, float]] = []
    for geometry in geometries:
        left = max(0.0, min(page_width, geometry.x))
        top = max(0.0, min(page_height, geometry.y))
        right = max(left, min(page_width, geometry.x + geometry.width))
        bottom = max(top, min(page_height, geometry.y + geometry.height))
        if right > left and bottom > top:
            rectangles.append((left, top, right, bottom))
    if not rectangles:
        return 0.0
    area = _union_area(rectangles)
    return _bounded(area / (page_width * page_height))


def _union_area(rectangles: Sequence[tuple[float, float, float, float]]) -> float:
    x_edges = sorted({edge for left, _top, right, _bottom in rectangles for edge in (left, right)})
    area = 0.0
    for left, right in zip(x_edges, x_edges[1:], strict=False):
        if right <= left:
            continue
        spans = sorted(
            (top, bottom)
            for rectangle_left, top, rectangle_right, bottom in rectangles
            if rectangle_left < right and rectangle_right > left
        )
        covered_height = 0.0
        current_start: float | None = None
        current_end = 0.0
        for top, bottom in spans:
            if current_start is None:
                current_start, current_end = top, bottom
            elif top > current_end:
                covered_height += current_end - current_start
                current_start, current_end = top, bottom
            else:
                current_end = max(current_end, bottom)
        if current_start is not None:
            covered_height += current_end - current_start
        area += (right - left) * covered_height
    return area


def _source_geometry(image: TextGeometry | _GeometryProvider) -> TextGeometry:
    return image if isinstance(image, TextGeometry) else image.source_geometry


def _validate_ratio(value: float | None, label: str) -> None:
    if value is not None and (not math.isfinite(value) or not 0.0 <= value <= 1.0):
        raise ValueError(f"{label} must be between 0 and 1.")


def _validate_confidence(value: float | None, label: str) -> None:
    _validate_ratio(value, label)


def _bounded(value: float) -> float:
    return max(0.0, min(1.0, value))


# Compatibility aliases make the result/settings discoverable under the names
# commonly used by callers while keeping the canonical detector names explicit.
PageDetectionResult = ScannedPageDetection
PageDetectionSignals = ScannedPageSignals
DetectionSettings = ScannedPageDetectionSettings
