import asyncio
import json
from collections.abc import Callable
from dataclasses import dataclass

from transloka_translation.benchmark import (
    FULL_BENCHMARK_CASES,
    FullBenchmarkRecommendation,
    FullBenchmarkRunner,
    FullBenchmarkStatus,
    HardwareProfile,
    detect_hardware_profile,
)
from transloka_translation.providers import (
    CancellationSignal,
    LocalModel,
    ProviderHealth,
    ProviderHealthStatus,
)
from transloka_translation.schemas import TranslationRequest


def _response(case_id: str, text: str) -> str:
    return json.dumps({"segments": [{"segment_id": case_id, "translated_text": text}]})


@dataclass
class Provider:
    response_factory: Callable[[str, str], str]
    cancellation_signal: "Signal | None" = None
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
        if self.cancellation_signal is not None and self.calls == 1:
            self.cancellation_signal.cancelled = True
        case_id = request.segments[0].segment_id
        return self.response_factory(case_id, request.segments[0].source_text)


@dataclass
class Signal:
    cancelled: bool = False

    @property
    def is_cancelled(self) -> bool:
        return self.cancelled


def _profile() -> HardwareProfile:
    return HardwareProfile(
        profile_id="hardware_test",
        operating_system="TestOS",
        operating_system_version="1",
        cpu_model="Test CPU",
        physical_cores=4,
        logical_cores=8,
        ram_total_gb=16.0,
        ram_available_gb=8.0,
        gpu_vendor=None,
        gpu_model=None,
        gpu_vram_total_gb=0.0,
        gpu_vram_available_gb=0.0,
        disk_type=None,
        disk_free_gb=100.0,
        ollama_version="test",
        created_at="2026-08-23T00:00:00Z",
    )


def test_full_benchmark_runs_repeated_cases_and_recommends_valid_model() -> None:
    provider = Provider(response_factory=lambda case_id, source: _response(case_id, source))

    result = asyncio.run(
        FullBenchmarkRunner(provider, hardware_profile=_profile(), clock=lambda: 1.0).run(
            "qwen3:1.7b"
        )
    )

    assert len(FULL_BENCHMARK_CASES) == 30
    assert result.status is FullBenchmarkStatus.COMPLETED
    assert result.total_runs == 90
    assert result.completed_runs == 90
    assert result.recommendation is FullBenchmarkRecommendation.RECOMMENDED_DEFAULT
    assert {attempt.context_length for attempt in result.attempts} == {"SHORT", "MEDIUM", "LONG"}
    assert {attempt.batch_size for attempt in result.attempts} == {1, 5}
    assert result.hardware_profile.profile_id == "hardware_test"


def test_full_benchmark_can_resume_after_cancellation() -> None:
    signal = Signal()
    provider = Provider(
        response_factory=lambda case_id, source: _response(case_id, source),
        cancellation_signal=signal,
    )
    runner = FullBenchmarkRunner(provider, hardware_profile=_profile(), clock=lambda: 1.0)

    partial = asyncio.run(runner.run("qwen3:1.7b", cancellation=signal))
    assert partial.status is FullBenchmarkStatus.PARTIALLY_COMPLETED
    assert partial.completed_runs == 1
    assert partial.next_run_index == 1

    signal.cancelled = False
    resumed = asyncio.run(runner.run("qwen3:1.7b", cancellation=signal, resume_from=partial))
    assert resumed.status is FullBenchmarkStatus.COMPLETED
    assert resumed.completed_runs == 90
    assert resumed.next_run_index == 90


def test_full_benchmark_critical_failure_rejects_model() -> None:
    provider = Provider(response_factory=lambda _case_id, _source: "not-json")

    result = asyncio.run(
        FullBenchmarkRunner(provider, hardware_profile=_profile()).run("qwen3:1.7b")
    )

    assert result.status is FullBenchmarkStatus.FAILED
    assert result.recommendation is FullBenchmarkRecommendation.REJECTED
    assert result.critical_failure_count > 0


def test_hardware_profile_uses_safe_stdlib_detection() -> None:
    profile = detect_hardware_profile()

    assert profile.profile_id.startswith("hardware_")
    assert profile.operating_system
    assert profile.logical_cores is None or profile.logical_cores > 0
    assert profile.ram_total_gb is not None and profile.ram_total_gb > 0
    assert profile.ram_available_gb is not None and profile.ram_available_gb >= 0
    assert profile.disk_free_gb is None or profile.disk_free_gb >= 0


def test_full_case_can_override_context_length_for_each_attempt() -> None:
    request = FULL_BENCHMARK_CASES[0].to_request(context_length="LONG")

    assert request.context.previous_text is not None
    assert request.context.next_text is not None
