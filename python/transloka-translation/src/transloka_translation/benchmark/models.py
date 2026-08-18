from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import StrEnum
from typing import Any


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
