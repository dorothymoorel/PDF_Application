import sys
import time
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from types import ModuleType

import pytest
from PIL import Image
from transloka_documents.ocr import (
    OCRGeometry,
    OCRHealth,
    OCRHealthStatus,
    OCRPage,
    OCRProviderError,
    OCRProviderErrorCode,
    OCRResult,
    OCRSettings,
    OCRTextBlock,
)
from transloka_documents.ocr.paddle import (
    LocalPaddleOCRProvider,
    PaddleOCRModelMissingError,
    PaddleOCRUnavailableError,
)


def _page() -> OCRPage:
    image = Image.new("RGB", (2, 2), "white")
    output = BytesIO()
    try:
        image.save(output, format="PNG")
    finally:
        image.close()
    return OCRPage(
        page_number=1,
        width_px=1200,
        height_px=1600,
        image=output.getvalue(),
    )


def _result(*, geometry: OCRGeometry, confidence: float = 0.94) -> OCRResult:
    return OCRResult(
        page_number=1,
        text="Recognized text",
        blocks=(
            OCRTextBlock(
                text="Recognized text",
                geometry=geometry,
                confidence=confidence,
            ),
        ),
        confidence=confidence,
        settings=OCRSettings(),
        provider="paddleocr",
    )


@dataclass
class StubBackend:
    result: OCRResult
    delay_seconds: float = 0.0

    def __post_init__(self) -> None:
        self.pages: list[OCRPage] = []

    def health_check(self) -> OCRHealth:
        return OCRHealth(status=OCRHealthStatus.AVAILABLE, provider="stub", version="test")

    def analyze_page(self, page: OCRPage, *, settings: OCRSettings) -> OCRResult:
        self.pages.append(page)
        if self.delay_seconds:
            time.sleep(self.delay_seconds)
        return self.result


def test_clean_scan_is_processed_as_one_local_page() -> None:
    backend = StubBackend(
        result=_result(geometry=OCRGeometry(x=12, y=24, width=280, height=42)),
    )
    provider = LocalPaddleOCRProvider(backend=backend)

    result = provider.analyze_page(_page(), settings=OCRSettings(timeout_seconds=1.0))

    assert result.text == "Recognized text"
    assert result.confidence == pytest.approx(0.94)
    assert result.geometry == OCRGeometry(x=12, y=24, width=280, height=42)
    assert backend.pages == [_page()]
    assert provider.device == "cpu"


def test_local_runtime_is_constructed_in_cpu_mode_and_parses_geometry(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    model_path = tmp_path / "paddle-model"
    model_path.mkdir()
    (model_path / "PP-OCRv5_mobile_det").mkdir()
    (model_path / "en_PP-OCRv4_mobile_rec").mkdir()
    captured: dict[str, object] = {}

    class FakePaddleOCR:
        __version__ = "test-runtime"

        def __init__(self, **options: object) -> None:
            captured.update(options)

        def predict(self, *, input: object) -> list[dict[str, object]]:
            assert getattr(input, "shape", None) == (2, 2, 3)
            return [
                {
                    "rec_texts": ["Recognized text"],
                    "rec_scores": [0.91],
                    "rec_boxes": [[10, 20, 220, 70]],
                }
            ]

    fake_module = ModuleType("paddleocr")
    fake_module.__dict__["PaddleOCR"] = FakePaddleOCR
    monkeypatch.setitem(sys.modules, "paddleocr", fake_module)
    provider = LocalPaddleOCRProvider(model_cache_dir=tmp_path, model_name="paddle-model")

    result = provider.analyze_page(_page())

    assert captured["device"] == "cpu"
    assert captured["enable_mkldnn"] is False
    assert captured["text_detection_model_dir"] == str(model_path / "PP-OCRv5_mobile_det")
    assert captured["text_recognition_model_dir"] == str(model_path / "en_PP-OCRv4_mobile_rec")
    assert result.text == "Recognized text"
    assert result.confidence == pytest.approx(0.91)
    assert result.geometry == OCRGeometry(x=10, y=20, width=210, height=50)


def test_rotated_scan_preserves_the_backend_geometry() -> None:
    rotated_bounds = OCRGeometry(x=180, y=90, width=72, height=260)
    backend = StubBackend(result=_result(geometry=rotated_bounds))
    provider = LocalPaddleOCRProvider(backend=backend)

    result = provider.analyze_page(_page())

    assert result.blocks[0].geometry == rotated_bounds
    assert result.blocks[0].geometry.x + result.blocks[0].geometry.width <= 1200
    assert result.blocks[0].geometry.y + result.blocks[0].geometry.height <= 1600


def test_provider_unavailable_does_not_fallback_to_a_remote_runtime(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    model_path = tmp_path / "paddle-model"
    model_path.mkdir()
    (model_path / "PP-OCRv5_mobile_det").mkdir()
    (model_path / "en_PP-OCRv4_mobile_rec").mkdir()

    monkeypatch.setitem(sys.modules, "paddleocr", None)
    provider = LocalPaddleOCRProvider(model_cache_dir=tmp_path, model_name="paddle-model")

    health = provider.health_check()

    assert health.status is OCRHealthStatus.UNAVAILABLE
    with pytest.raises(PaddleOCRUnavailableError):
        provider.analyze_page(_page())


def test_missing_model_is_reported_before_runtime_initialization(tmp_path: Path) -> None:
    provider = LocalPaddleOCRProvider(model_cache_dir=tmp_path, model_name="missing-model")

    assert provider.health_check().status is OCRHealthStatus.UNAVAILABLE
    with pytest.raises(PaddleOCRModelMissingError):
        provider.analyze_page(_page())


def test_page_timeout_is_normalized_and_retryable() -> None:
    backend = StubBackend(
        result=_result(geometry=OCRGeometry(x=12, y=24, width=280, height=42)),
        delay_seconds=0.05,
    )
    provider = LocalPaddleOCRProvider(backend=backend)

    with pytest.raises(OCRProviderError) as raised:
        provider.analyze_page(_page(), settings=OCRSettings(timeout_seconds=0.001))

    assert raised.value.code is OCRProviderErrorCode.TIMEOUT
    assert raised.value.retryable is True


def test_remote_model_cache_urls_are_rejected() -> None:
    with pytest.raises(ValueError, match="local filesystem"):
        LocalPaddleOCRProvider(model_cache_dir="https://example.test/models")
