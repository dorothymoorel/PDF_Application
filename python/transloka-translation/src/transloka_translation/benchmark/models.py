from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import StrEnum
from typing import Any

from .hardware import HardwareProfile


class QuickBenchmarkStatus(StrEnum):
    COMPLETED = "COMPLETED"
    PARTIALLY_COMPLETED = "PARTIALLY_COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class QuickBenchmarkRecommendation(StrEnum):
    RECOMMENDED_DEFAULT = "RECOMMENDED_DEFAULT"
    FALLBACK_ONLY = "FALLBACK_ONLY"
    EXPERIMENTAL = "EXPERIMENTAL"
    REJECTED = "REJECTED"


class FullBenchmarkStatus(StrEnum):
    COMPLETED = "COMPLETED"
    PARTIALLY_COMPLETED = "PARTIALLY_COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class FullBenchmarkRecommendation(StrEnum):
    RECOMMENDED_DEFAULT = "RECOMMENDED_DEFAULT"
    FALLBACK_ONLY = "FALLBACK_ONLY"
    EXPERIMENTAL = "EXPERIMENTAL"
    REJECTED = "REJECTED"


@dataclass(frozen=True, slots=True)
class BenchmarkFailure:
    code: str
    message: str
    critical: bool = False


@dataclass(frozen=True, slots=True)
class BenchmarkCaseResult:
    case_id: str
    status: str
    latency_seconds: float | None
    structured_output_valid: bool
    placeholder_integrity: bool
    failure: BenchmarkFailure | None = None


@dataclass(frozen=True, slots=True)
class QuickBenchmarkResult:
    benchmark_id: str
    benchmark_version: str
    dataset_version: str
    model_id: str
    status: QuickBenchmarkStatus
    recommendation: QuickBenchmarkRecommendation
    cases: tuple[BenchmarkCaseResult, ...]
    average_latency_seconds: float | None
    batch_sizes: tuple[int, ...]
    temperature: float
    failure: BenchmarkFailure | None = None

    @property
    def total_cases(self) -> int:
        return len(self.cases)

    @property
    def successful_cases(self) -> int:
        return sum(case.status == "COMPLETED" for case in self.cases)

    @property
    def failed_cases(self) -> int:
        return sum(case.status == "FAILED" for case in self.cases)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["status"] = self.status.value
        payload["recommendation"] = self.recommendation.value
        payload["cases"] = [
            {
                **asdict(case),
                "failure": asdict(case.failure) if case.failure is not None else None,
            }
            for case in self.cases
        ]
        payload["failure"] = asdict(self.failure) if self.failure is not None else None
        payload["total_cases"] = self.total_cases
        payload["successful_cases"] = self.successful_cases
        payload["failed_cases"] = self.failed_cases
        return payload


@dataclass(frozen=True, slots=True)
class FullBenchmarkAttemptResult:
    case_id: str
    repetition: int
    batch_size: int
    context_length: str
    status: str
    latency_seconds: float | None
    structured_output_valid: bool
    placeholder_integrity: bool
    quality_score: float
    failure: BenchmarkFailure | None = None


@dataclass(frozen=True, slots=True)
class FullBenchmarkResult:
    benchmark_id: str
    benchmark_version: str
    dataset_version: str
    model_id: str
    hardware_profile: HardwareProfile
    status: FullBenchmarkStatus
    recommendation: FullBenchmarkRecommendation
    attempts: tuple[FullBenchmarkAttemptResult, ...]
    total_runs: int
    next_run_index: int
    batch_sizes: tuple[int, ...]
    context_lengths: tuple[str, ...]
    average_latency_seconds: float | None
    quality_score: float | None
    failure: BenchmarkFailure | None = None

    @property
    def completed_runs(self) -> int:
        return len(self.attempts)

    @property
    def successful_runs(self) -> int:
        return sum(attempt.status == "COMPLETED" for attempt in self.attempts)

    @property
    def failed_runs(self) -> int:
        return sum(attempt.status == "FAILED" for attempt in self.attempts)

    @property
    def critical_failure_count(self) -> int:
        return sum(
            attempt.failure is not None and attempt.failure.critical for attempt in self.attempts
        )

    @property
    def success_rate(self) -> float | None:
        if self.completed_runs == 0:
            return None
        return self.successful_runs / self.completed_runs

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["status"] = self.status.value
        payload["recommendation"] = self.recommendation.value
        payload["hardware_profile"] = self.hardware_profile.to_dict()
        payload["attempts"] = [
            {
                **asdict(attempt),
                "failure": asdict(attempt.failure) if attempt.failure is not None else None,
            }
            for attempt in self.attempts
        ]
        payload["completed_runs"] = self.completed_runs
        payload["successful_runs"] = self.successful_runs
        payload["failed_runs"] = self.failed_runs
        payload["critical_failure_count"] = self.critical_failure_count
        payload["success_rate"] = self.success_rate
        payload["failure"] = asdict(self.failure) if self.failure is not None else None
        return payload
