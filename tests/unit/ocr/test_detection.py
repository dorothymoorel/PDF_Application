import pytest
from transloka_document_ir.enums import PageType
from transloka_documents.extraction.models import ExtractedPage, ExtractedWord, TextGeometry
from transloka_documents.ocr.detection import (
    DetectionSettings,
    ScannedPageDetectionSettings,
    detect_scanned_page,
)


def _page(*, word_geometry: TextGeometry | None = None) -> ExtractedPage:
    words: tuple[ExtractedWord, ...] = ()
    if word_geometry is not None:
        words = (
            ExtractedWord(
                source_text="native text",
                normalized_text="native text",
                geometry=word_geometry,
                character_indexes=(),
                normalization_boundaries=(),
                font_name=None,
                font_size=None,
                upright=True,
            ),
        )
    return ExtractedPage(
        page_number=1,
        width_points=100,
        height_points=100,
        characters=(),
        words=words,
        lines=(),
        block_candidates=(),
    )


def test_digital_page_uses_native_text_without_ocr() -> None:
    result = detect_scanned_page(
        _page(word_geometry=TextGeometry(x=5, y=5, width=80, height=80)),
        image_coverage=0.05,
    )

    assert result.page_type is PageType.DIGITAL
    assert result.requires_ocr is False
    assert result.signals.text_coverage == pytest.approx(0.64)
    assert "NATIVE_TEXT_CONTENT" in result.reasons


def test_full_page_image_without_native_text_is_scanned() -> None:
    result = detect_scanned_page(_page(), image_coverage=0.95)

    assert result.page_type is PageType.SCANNED
    assert result.requires_ocr is True
    assert result.signals.no_text is True
    assert result.signals.full_page_image is True


def test_text_and_dominant_image_is_hybrid() -> None:
    result = detect_scanned_page(
        _page(word_geometry=TextGeometry(x=5, y=5, width=20, height=20)),
        image_coverage=0.70,
        native_confidence=0.90,
    )

    assert result.page_type is PageType.HYBRID
    assert result.requires_ocr is True
    assert result.signals.image_dominant is True


def test_image_only_illustration_without_text_signal_does_not_require_ocr() -> None:
    result = detect_scanned_page(_page(), image_coverage=0.30)

    assert result.page_type is PageType.IMAGE_ONLY
    assert result.requires_ocr is False
    assert "NO_TEXT_SIGNAL_FOR_OCR" in result.reasons


def test_thresholds_are_explicit_and_boundary_is_deterministic() -> None:
    settings = ScannedPageDetectionSettings(
        low_text_coverage_threshold=0.05,
        image_dominance_threshold=0.65,
    )
    result = detect_scanned_page(
        _page(word_geometry=TextGeometry(x=0, y=0, width=5, height=100)),
        image_coverage=0.65,
        settings=settings,
    )

    assert result.signals.text_coverage == pytest.approx(0.05)
    assert result.signals.low_text_coverage is False
    assert result.signals.image_dominant is True
    assert result.page_type is PageType.HYBRID
    assert DetectionSettings is ScannedPageDetectionSettings


def test_asset_geometries_are_unioned_for_image_coverage() -> None:
    result = detect_scanned_page(
        _page(),
        image_geometries=(
            TextGeometry(x=0, y=0, width=100, height=40),
            TextGeometry(x=0, y=40, width=100, height=40),
        ),
    )

    assert result.signals.image_coverage == pytest.approx(0.80)
    assert result.page_type is PageType.SCANNED


def test_invalid_ratios_are_rejected() -> None:
    with pytest.raises(ValueError, match="Image coverage"):
        detect_scanned_page(_page(), image_coverage=1.01)
    with pytest.raises(ValueError, match="Native extraction confidence"):
        detect_scanned_page(_page(), native_confidence=-0.1)
