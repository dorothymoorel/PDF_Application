"""Run the local, deterministic performance benchmark matrix.

The benchmark intentionally uses fake OCR/translation providers.  It measures
pipeline and storage overhead on the current host; it is not a cross-machine
scorecard and never contacts Ollama or writes to the repository.
"""

from __future__ import annotations

import argparse
import asyncio
import io
import json
import sqlite3
import tempfile
import tracemalloc
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter

from pypdf import PdfReader, PdfWriter
from transloka_documents.extraction import extract_digital_text
from transloka_documents.ocr import (
    FakeOCRProvider,
    OCRPage,
    OCRResult,
    OCRSettings,
)
from transloka_reconstruction.overlay import (
    OverlayDependencyError,
    OverlayPageGenerator,
    OverlayText,
)
from transloka_translation.benchmark import detect_hardware_profile
from transloka_translation.providers import FakeTranslationProvider
from transloka_translation.schemas import (
    TranslatedSegment,
    TranslationContext,
    TranslationRequest,
    TranslationRequestSegment,
    TranslationResponse,
    TranslationStyle,
)

PAGE_COUNTS: tuple[int, ...] = (10, 50, 100, 250)
REPORT_VERSION = "1.0"


@dataclass(frozen=True, slots=True)
class PerformanceCase:
    page_count: int
    import_seconds: float
    extraction_seconds: float
    ocr_seconds: float
    translation_seconds: float
    reconstruction_seconds: float
    query_seconds: float
    ram_peak_mb: float
    disk_bytes: int

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class PerformanceReport:
    report_version: str
    generated_at: str
    hardware: dict[str, object]
    settings: dict[str, object]
    comparison_policy: str
    cases: tuple[PerformanceCase, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "report_version": self.report_version,
            "generated_at": self.generated_at,
            "hardware": self.hardware,
            "settings": self.settings,
            "comparison_policy": self.comparison_policy,
            "cases": [case.to_dict() for case in self.cases],
        }


def run_benchmark(*, page_counts: Sequence[int] = PAGE_COUNTS) -> PerformanceReport:
    """Measure every requested document size and return a machine-readable report."""

    sizes = _validate_page_counts(page_counts)
    cases: list[PerformanceCase] = []
    renderer = OverlayPageGenerator()
    renderer_setting = "OverlayPageGenerator (pypdf blank-page fallback if unavailable)"

    for page_count in sizes:
        cases.append(_run_case(page_count, renderer))

    return PerformanceReport(
        report_version=REPORT_VERSION,
        generated_at=_utc_now(),
        hardware=detect_hardware_profile().to_dict(),
        settings={
            "page_counts": list(sizes),
            "pdf_fixture": "synthetic blank pages generated with pypdf",
            "ocr_provider": "fake",
            "translation_provider": "fake",
            "reconstruction_renderer": renderer_setting,
            "query_backend": "sqlite3 in-memory",
            "ram_measurement": "tracemalloc peak per case",
            "disk_measurement": "input and reconstructed PDF bytes in a temporary directory",
            "parallelism": 1,
        },
        comparison_policy=(
            "Results are comparable only within this report and host; results from different "
            "hardware are not comparable."
        ),
        cases=tuple(cases),
    )


def write_report(report: PerformanceReport, destination: str | Path) -> None:
    """Write a UTF-8 JSON report to a caller-selected path."""

    path = Path(destination)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(report.to_dict(), ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--pages",
        nargs="+",
        type=int,
        metavar="N",
        help="page counts to measure (default: 10 50 100 250)",
    )
    parser.add_argument("--output", type=Path, help="optional JSON report destination")
    args = parser.parse_args(argv)

    report = run_benchmark(page_counts=tuple(args.pages) if args.pages else PAGE_COUNTS)
    if args.output is not None:
        write_report(report, args.output)
    print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2, sort_keys=True))
    return 0


def _run_case(page_count: int, renderer: OverlayPageGenerator) -> PerformanceCase:
    with tempfile.TemporaryDirectory(prefix="transloka-benchmark-") as temporary:
        workspace = Path(temporary)
        pdf_bytes = _build_pdf(page_count)
        input_path = workspace / "input.pdf"
        input_path.write_bytes(pdf_bytes)

        _, import_seconds, import_peak = _measure(
            lambda: _import_pdf(pdf_bytes),
        )
        extracted, extraction_seconds, extraction_peak = _measure(
            lambda: extract_digital_text(io.BytesIO(pdf_bytes)),
        )
        _, ocr_seconds, ocr_peak = _measure(lambda: _run_ocr(page_count))
        _, translation_seconds, translation_peak = _measure(
            lambda: asyncio.run(_run_translation(page_count)),
        )
        reconstructed, reconstruction_seconds, reconstruction_peak = _measure(
            lambda: _reconstruct(page_count, renderer),
        )
        output_path = workspace / "reconstructed.pdf"
        output_path.write_bytes(reconstructed)
        _, query_seconds, query_peak = _measure(lambda: _run_queries(page_count))

        if extracted.page_count != page_count:
            raise RuntimeError("The extraction benchmark returned an unexpected page count.")
        disk_bytes = input_path.stat().st_size + output_path.stat().st_size
        return PerformanceCase(
            page_count=page_count,
            import_seconds=import_seconds,
            extraction_seconds=extraction_seconds,
            ocr_seconds=ocr_seconds,
            translation_seconds=translation_seconds,
            reconstruction_seconds=reconstruction_seconds,
            query_seconds=query_seconds,
            ram_peak_mb=max(
                import_peak,
                extraction_peak,
                ocr_peak,
                translation_peak,
                reconstruction_peak,
                query_peak,
            ),
            disk_bytes=disk_bytes,
        )


def _measure[T](action: Callable[[], T]) -> tuple[T, float, float]:
    tracemalloc.start()
    started = perf_counter()
    try:
        result = action()
        elapsed = max(0.0, perf_counter() - started)
        _, peak_bytes = tracemalloc.get_traced_memory()
        return result, elapsed, peak_bytes / (1024 * 1024)
    finally:
        tracemalloc.stop()


def _build_pdf(page_count: int) -> bytes:
    writer = PdfWriter()
    for _ in range(page_count):
        writer.add_blank_page(width=612, height=792)
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()


def _import_pdf(pdf_bytes: bytes) -> int:
    return len(PdfReader(io.BytesIO(pdf_bytes), strict=False).pages)


def _run_ocr(page_count: int) -> int:
    settings = OCRSettings(language="en", detect_tables=False, detect_formulas=False)
    provider = FakeOCRProvider(
        result=OCRResult(
            page_number=1,
            text="synthetic OCR text",
            confidence=1.0,
            settings=settings,
            provider="fake",
        )
    )
    # The fake provider returns page-specific empty results when the fixture is
    # absent; creating one provider per page keeps the benchmark deterministic.
    completed = 0
    for page_number in range(1, page_count + 1):
        page_provider = provider if page_number == 1 else FakeOCRProvider()
        page_provider.analyze_page(
            OCRPage(page_number=page_number, width_px=1, height_px=1, image=b"synthetic"),
            settings=settings,
        )
        completed += 1
    return completed


async def _run_translation(page_count: int) -> int:
    response = TranslationResponse(
        segments=(TranslatedSegment("segment-1", "Translated benchmark text"),)
    )
    provider = FakeTranslationProvider[TranslationRequest, TranslationResponse](response=response)
    completed = 0
    for page_number in range(1, page_count + 1):
        request = TranslationRequest(
            segments=(
                TranslationRequestSegment(
                    f"segment-{page_number}",
                    f"Synthetic source text for page {page_number}.",
                ),
            ),
            context=TranslationContext(
                source_language="en",
                target_language="id",
                document_type="benchmark",
            ),
            glossary=(),
            placeholders=(),
            style=TranslationStyle.PROFESSIONAL,
        )
        await provider.translate(request)
        completed += 1
    return completed


def _reconstruct(page_count: int, renderer: OverlayPageGenerator) -> bytes:
    writer = PdfWriter()
    for page_number in range(1, page_count + 1):
        page = writer.add_blank_page(width=612, height=792)
        try:
            overlay = renderer.build_overlay(
                612,
                792,
                texts=(OverlayText(text=f"Translated page {page_number}", x=72, y=700),),
            )
        except OverlayDependencyError:
            continue
        overlay_page = PdfReader(io.BytesIO(overlay), strict=False).pages[0]
        page.merge_page(overlay_page)
    output = io.BytesIO()
    writer.write(output)
    return output.getvalue()


def _run_queries(page_count: int) -> int:
    connection = sqlite3.connect(":memory:")
    try:
        connection.executescript(
            """
            CREATE TABLE segments (
                id INTEGER PRIMARY KEY,
                document_id TEXT NOT NULL,
                page_number INTEGER NOT NULL,
                translated_text TEXT NOT NULL
            );
            CREATE INDEX ix_segments_document_page
                ON segments(document_id, page_number);
            """
        )
        connection.executemany(
            "INSERT INTO segments(document_id, page_number, translated_text) VALUES (?, ?, ?)",
            [
                ("benchmark", page_number, f"Translated page {page_number}")
                for page_number in range(1, page_count + 1)
            ],
        )
        connection.commit()
        for page_number in range(1, page_count + 1):
            row = connection.execute(
                "SELECT translated_text FROM segments WHERE document_id = ? AND page_number = ?",
                ("benchmark", page_number),
            ).fetchone()
            if row is None:
                raise RuntimeError("The query benchmark did not find an inserted segment.")
        return page_count
    finally:
        connection.close()


def _validate_page_counts(values: Sequence[int]) -> tuple[int, ...]:
    normalized = tuple(values)
    if not normalized or any(type(value) is not int or value <= 0 for value in normalized):
        raise ValueError("page_counts must contain positive integers.")
    if len(set(normalized)) != len(normalized):
        raise ValueError("page_counts must not contain duplicates.")
    return normalized


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


if __name__ == "__main__":
    raise SystemExit(main())
