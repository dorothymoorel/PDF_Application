import asyncio
from collections.abc import Callable
from dataclasses import dataclass

from transloka_translation.benchmark import (
    QUICK_BENCHMARK_CASES,
    QuickBenchmarkRecommendation,
    QuickBenchmarkRunner,
    QuickBenchmarkStatus,
)
from transloka_translation.providers import (
    CancellationSignal,
    LocalModel,
    ProviderHealth,
    ProviderHealthStatus,
)
from transloka_translation.schemas import TranslationRequest


def _response(case_id: str, text: str) -> str:
    import json

    return json.dumps({"segments": [{"segment_id": case_id, "translated_text": text}]})


@dataclass
class Provider:
    response_factory: Callable[[str, str], str]
    stop_after: int | None = None
    calls: int = 0

    async def health_check(self) -> ProviderHealth:
        return ProviderHealth(ProviderHealthStatus.AVAILABLE, version="test")

    async def list_models(self) -> list[LocalModel]:
        return [LocalModel(name="qwen3:1.7b")]

    async def translate(
        self,
        request: TranslationRequest,
        *,
        cancellation: CancellationSignal | None = None,
    ) -> str:
        del cancellation
        self.calls += 1
        if self.stop_after is not None and self.calls > self.stop_after:
            raise asyncio.CancelledError
        case_id = request.segments[0].segment_id
        text = self.response_factory(case_id, request.segments[0].source_text)
        return text


def test_quick_benchmark_completes_six_cases_and_recommends_valid_model() -> None:
    provider = Provider(
        response_factory=lambda case_id, source: _response(case_id, source),
    )
    result = asyncio.run(QuickBenchmarkRunner(provider, clock=lambda: 1.0).run("qwen3:1.7b"))

    assert len(QUICK_BENCHMARK_CASES) == 6
    assert result.status is QuickBenchmarkStatus.COMPLETED
    assert result.recommendation is QuickBenchmarkRecommendation.RECOMMENDED_DEFAULT
    assert result.successful_cases == 6
    assert result.average_latency_seconds == 0.0


def test_schema_failure_rejects_model() -> None:
    provider = Provider(response_factory=lambda _case_id, _source: "not-json")

    result = asyncio.run(QuickBenchmarkRunner(provider).run("qwen3:1.7b"))

    assert result.status is QuickBenchmarkStatus.FAILED
    assert result.recommendation is QuickBenchmarkRecommendation.REJECTED
    assert result.cases[0].failure is not None
    assert result.cases[0].failure.code == "INVALID_JSON"
    assert result.cases[0].failure.critical is True


def test_placeholder_failure_is_critical_and_not_recommended() -> None:
    provider = Provider(
        response_factory=lambda case_id, source: _response(
            case_id,
            source.replace("__TLK_TERM_0001_A7F2__", "term"),
        )
    )

    result = asyncio.run(QuickBenchmarkRunner(provider).run("qwen3:1.7b"))

    placeholder_case = next(
        case for case in result.cases if case.case_id == "quick_003_placeholders"
    )
    assert placeholder_case.failure is not None
    assert placeholder_case.failure.code == "PLACEHOLDER_MISMATCH"
    assert result.recommendation is QuickBenchmarkRecommendation.REJECTED


def test_interrupted_benchmark_keeps_completed_cases_and_marks_partial() -> None:
    provider = Provider(
        response_factory=lambda case_id, source: _response(case_id, source),
        stop_after=2,
    )

    result = asyncio.run(QuickBenchmarkRunner(provider).run("qwen3:1.7b"))

    assert result.status is QuickBenchmarkStatus.PARTIALLY_COMPLETED
    assert result.successful_cases == 2
    assert result.recommendation is QuickBenchmarkRecommendation.EXPERIMENTAL
    assert result.failure is not None
    assert result.failure.code == "BENCHMARK_INTERRUPTED"
