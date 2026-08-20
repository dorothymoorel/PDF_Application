import pytest
from transloka_documents.ocr import (
    FakeOCRProvider,
    OCRGeometry,
    OCRHealthStatus,
    OCRPage,
    OCRProvider,
    OCRProviderError,
    OCRProviderErrorCode,
    OCRResult,
    OCRSettings,
    OCRTextBlock,
    PaddleOCRProvider,
)


def _page() -> OCRPage:
    return OCRPage(page_number=1, width_px=1200, height_px=1600, image=b"fake-image")


def _result(
    *,
    text: str = "Scanned text",
    confidence: float = 0.96,
    blocks: tuple[OCRTextBlock, ...] | None = None,
) -> OCRResult:
    return OCRResult(
        page_number=1,
        text=text,
        blocks=blocks
        if blocks is not None
        else (
            OCRTextBlock(
                text=text,
                geometry=OCRGeometry(x=10, y=20, width=300, height=40),
                confidence=confidence,
            ),
        ),
        confidence=confidence,
        settings=OCRSettings(),
        provider="fake",
    )


def test_fake_success_satisfies_ocr_and_paddle_protocols() -> None:
    provider = FakeOCRProvider(result=_result())

    assert isinstance(provider, OCRProvider)
    assert isinstance(provider, PaddleOCRProvider)
    assert provider.health_check().status is OCRHealthStatus.AVAILABLE

    result = provider.analyze_page(_page())

    assert result.text == "Scanned text"
    assert result.geometry == OCRGeometry(x=10, y=20, width=300, height=40)
    assert result.confidence == pytest.approx(0.96)
    assert provider.requests == (_page(),)


def test_fake_empty_result_is_explicit_and_has_no_geometry() -> None:
    result = FakeOCRProvider().analyze_page(_page())

    assert result.is_empty is True
    assert result.geometry is None
    assert result.confidence == 0.0


def test_low_confidence_result_is_reported_without_discarding_text() -> None:
    settings = OCRSettings(low_confidence_threshold=0.75)
    result = FakeOCRProvider(
        result=OCRResult(
            page_number=1,
            text="Uncertain text",
            blocks=(
                OCRTextBlock(
                    text="Uncertain text",
                    geometry=OCRGeometry(x=0, y=0, width=100, height=20),
                    confidence=0.42,
                ),
            ),
            confidence=0.42,
            settings=settings,
            provider="fake",
        )
    ).analyze_page(_page(), settings=settings)

    assert result.text == "Uncertain text"
    assert result.is_low_confidence is True
    assert result.blocks[0].confidence == pytest.approx(0.42)


def test_fake_timeout_is_normalized_and_retryable() -> None:
    provider = FakeOCRProvider(delay_seconds=2.0, timeout_seconds=1.0)

    with pytest.raises(OCRProviderError) as raised:
        provider.analyze_page(_page())

    assert raised.value.code is OCRProviderErrorCode.TIMEOUT
    assert raised.value.retryable is True
