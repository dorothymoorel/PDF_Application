from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType


def _benchmark_module() -> ModuleType:
    path = Path(__file__).with_name("performance_benchmark.py")
    specification = importlib.util.spec_from_file_location("transloka_benchmark_script", path)
    if specification is None or specification.loader is None:
        raise RuntimeError("Could not load benchmark script.")
    module = importlib.util.module_from_spec(specification)
    sys.modules[specification.name] = module
    specification.loader.exec_module(module)
    return module


def test_performance_benchmark_covers_canonical_page_sizes() -> None:
    benchmark = _benchmark_module()
    report = benchmark.run_benchmark(page_counts=benchmark.PAGE_COUNTS)

    assert benchmark.PAGE_COUNTS == (10, 50, 100, 250)
    assert tuple(case.page_count for case in report.cases) == benchmark.PAGE_COUNTS

    for case in report.cases:
        assert case.page_count in benchmark.PAGE_COUNTS
        assert case.import_seconds >= 0
        assert case.extraction_seconds >= 0
        assert case.ocr_seconds >= 0
        assert case.translation_seconds >= 0
        assert case.reconstruction_seconds >= 0
        assert case.query_seconds >= 0
        assert case.ram_peak_mb >= 0
        assert case.disk_bytes > 0


def test_performance_report_records_hardware_settings_and_scope() -> None:
    report = _benchmark_module().run_benchmark(page_counts=(10,))
    payload = report.to_dict()

    assert payload["hardware"]
    assert payload["settings"]["translation_provider"] == "fake"
    assert payload["settings"]["ocr_provider"] == "fake"
    assert "not comparable" in payload["comparison_policy"]
