import json
from collections import defaultdict
from io import BytesIO
from pathlib import Path

import pytest
from pypdf import PdfWriter
from transloka_core.storage import resolve_local_data_directories
from transloka_core.storage.local import LocalFileStorage
from transloka_document_ir.enums import PageType
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
from transloka_documents.ocr.detection import ScannedPageDetection, ScannedPageSignals
from transloka_documents.ocr.orchestration import (
    OCRPageOrchestrator,
    OCRPageRequest,
    OCRRawOutputStore,
    OCRRunStatus,
)

PROJECT_ID = "prj_550e8400-e29b-41d4-a716-446655440000"


class ScriptedProvider:
    def __init__(self, failures: dict[int, list[OCRProviderError]] | None = None) -> None:
        self.failures = defaultdict(list, failures or {})
        self.calls: list[OCRPage] = []
        self.attempts: dict[int, int] = defaultdict(int)

    def health_check(self) -> OCRHealth:
        return OCRHealth(status=OCRHealthStatus.AVAILABLE, provider="test")

    def analyze_page(
        self,
        page: OCRPage,
        *,
        settings: OCRSettings | None = None,
    ) -> OCRResult:
        self.calls.append(page)
        self.attempts[page.page_number] += 1
        if self.failures[page.page_number]:
            raise self.failures[page.page_number].pop(0)
        effective_settings = settings or OCRSettings()
        return OCRResult(
            page_number=page.page_number,
            text=f"OCR page {page.page_number}",
            blocks=(
                OCRTextBlock(
                    text=f"OCR page {page.page_number}",
                    geometry=OCRGeometry(x=10, y=10, width=100, height=24),
                    confidence=0.91,
                ),
            ),
            confidence=0.91,
            settings=effective_settings,
            provider="test",
        )


@pytest.fixture
def storage(tmp_path: Path) -> tuple[Path, LocalFileStorage]:
    root = tmp_path / "ocr orchestration"
    return root, LocalFileStorage(resolve_local_data_directories(root))


def test_selected_pages_render_ocr_and_persist_raw_output(
    storage: tuple[Path, LocalFileStorage],
) -> None:
    root, file_storage = storage
    provider = ScriptedProvider()
    request = OCRPageRequest(
        job_id="job-selected",
        project_id=PROJECT_ID,
        source_pdf=_pdf_bytes(page_count=3),
        page_numbers=(2,),
    )

    result = OCRPageOrchestrator(
        provider,
        file_storage,
        raw_output_store=OCRRawOutputStore(file_storage),
    ).run(request)

    assert result.status is OCRRunStatus.COMPLETED
    assert result.completed_page_numbers == (2,)
    assert [page.page_number for page in provider.calls] == [2]
    output = result.outputs[0]
    raw_path = root / Path(output.raw_output.storage_key)
    assert raw_path.is_file()
    assert json.loads(raw_path.read_text(encoding="utf-8"))["text"] == "OCR page 2"
    assert output.render.render.file_role == "PAGE_RENDER"


def test_auto_pages_only_process_detections_that_require_ocr(
    storage: tuple[Path, LocalFileStorage],
) -> None:
    _root, file_storage = storage
    detections = (
        _detection(1, requires_ocr=False, page_type=PageType.IMAGE_ONLY),
        _detection(2, requires_ocr=True, page_type=PageType.SCANNED),
        _detection(3, requires_ocr=True, page_type=PageType.HYBRID),
    )
    provider = ScriptedProvider()
    request = OCRPageRequest.for_auto_pages(
        job_id="job-auto",
        project_id=PROJECT_ID,
        source_pdf=_pdf_bytes(page_count=3),
        detections=detections,
    )

    result = OCRPageOrchestrator(provider, file_storage).run(request)

    assert result.selected_page_numbers == (2, 3)
    assert result.completed_page_numbers == (2, 3)
    assert [page.page_number for page in provider.calls] == [2, 3]


def test_partial_failure_preserves_successful_pages(
    storage: tuple[Path, LocalFileStorage],
) -> None:
    root, file_storage = storage
    provider = ScriptedProvider(
        failures={
            2: [
                OCRProviderError(
                    OCRProviderErrorCode.INVALID_REQUEST,
                    "page cannot be read",
                    retryable=False,
                )
            ]
        }
    )
    request = OCRPageRequest(
        job_id="job-partial",
        project_id=PROJECT_ID,
        source_pdf=_pdf_bytes(page_count=3),
        page_numbers=(1, 2, 3),
    )

    result = OCRPageOrchestrator(provider, file_storage).run(request)

    assert result.status is OCRRunStatus.PARTIALLY_COMPLETED
    assert result.completed_page_numbers == (1, 3)
    assert result.failed_page_numbers == (2,)
    assert (root / Path(result.outputs[0].raw_output.storage_key)).is_file()
    assert (root / Path(result.outputs[1].raw_output.storage_key)).is_file()
    assert result.failures[0].error_code == "INVALID_REQUEST"


def test_cancellation_stops_remaining_pages_after_completed_output(
    storage: tuple[Path, LocalFileStorage],
) -> None:
    _root, file_storage = storage
    provider = ScriptedProvider()
    callback_count = 0

    def cancel_check() -> bool:
        return callback_count >= 2

    def progress(_value: float, _stage: str) -> None:
        nonlocal callback_count
        callback_count += 1

    request = OCRPageRequest(
        job_id="job-cancel",
        project_id=PROJECT_ID,
        source_pdf=_pdf_bytes(page_count=3),
        page_numbers=(1, 2, 3),
    )
    result = OCRPageOrchestrator(provider, file_storage).run(
        request,
        cancel_check=cancel_check,
        progress_callback=progress,
    )

    assert result.status is OCRRunStatus.CANCELLED
    assert result.completed_page_numbers == (1,)
    assert result.cancelled_page_numbers == (2, 3)
    assert [page.page_number for page in provider.calls] == [1]


def test_retryable_provider_error_retries_the_same_page(
    storage: tuple[Path, LocalFileStorage],
) -> None:
    _root, file_storage = storage
    provider = ScriptedProvider(
        failures={
            1: [
                OCRProviderError(
                    OCRProviderErrorCode.TIMEOUT,
                    "temporary timeout",
                    retryable=True,
                )
            ]
        }
    )
    request = OCRPageRequest(
        job_id="job-retry",
        project_id=PROJECT_ID,
        source_pdf=_pdf_bytes(),
        page_numbers=(1,),
        max_attempts=2,
    )

    result = OCRPageOrchestrator(provider, file_storage).run(request)

    assert result.status is OCRRunStatus.COMPLETED
    assert result.outputs[0].attempts == 2
    assert provider.attempts[1] == 2


def _detection(
    page_number: int, *, requires_ocr: bool, page_type: PageType
) -> ScannedPageDetection:
    signals = ScannedPageSignals(
        has_text=page_type is not PageType.IMAGE_ONLY,
        no_text=page_type is PageType.IMAGE_ONLY,
        text_coverage=0.2 if page_type is not PageType.IMAGE_ONLY else 0.0,
        low_text_coverage=False,
        image_coverage=0.9 if requires_ocr else 0.2,
        image_dominant=requires_ocr,
        full_page_image=page_type is PageType.SCANNED,
        poor_native_extraction=False,
        native_confidence=0.9,
        image_has_text_signal=page_type is PageType.HYBRID,
    )
    return ScannedPageDetection(
        page_number=page_number,
        page_type=page_type,
        requires_ocr=requires_ocr,
        confidence=0.9,
        signals=signals,
        reasons=("TEST",),
    )


def _pdf_bytes(*, page_count: int = 1) -> bytes:
    output = BytesIO()
    writer = PdfWriter()
    for _ in range(page_count):
        writer.add_blank_page(width=612, height=792)
    writer.write(output)
    return output.getvalue()
