from __future__ import annotations

import asyncio
from collections.abc import Callable, Sequence
from time import perf_counter
from typing import Any, Protocol
from uuid import uuid4

from transloka_translation.parsing import ResponseParseError
from transloka_translation.providers import (
    CancellationSignal,
    LocalModel,
    ProviderHealthStatus,
    TranslationProviderError,
)
from transloka_translation.schemas import TranslationSchemaError

from .cases import extract_placeholders
from .full_cases import CONTEXT_LENGTHS, FULL_BENCHMARK_CASES, FullBenchmarkCase
from .hardware import HardwareProfile, detect_hardware_profile
from .models import (
    BenchmarkFailure,
    FullBenchmarkAttemptResult,
    FullBenchmarkRecommendation,
    FullBenchmarkResult,
    FullBenchmarkStatus,
)
from .runner import _coerce_response, _parse_failure

FULL_BENCHMARK_VERSION = "0.1"
DEFAULT_FULL_DATASET_VERSION = "translation_benchmark_en_id_0.1"


class FullBenchmarkProvider(Protocol):
    async def health_check(self) -> Any: ...

    async def list_models(self) -> list[LocalModel]: ...

    async def translate(
        self,
        request: Any,
        *,
        cancellation: CancellationSignal | None = None,
    ) -> object: ...


class FullBenchmarkRunner:
    """Run a deterministic 30-case benchmark with resumable repeated attempts."""

    def __init__(
        self,
        provider: FullBenchmarkProvider,
        *,
        cases: Sequence[FullBenchmarkCase] = FULL_BENCHMARK_CASES,
        hardware_profile: HardwareProfile | None = None,
        repeat_count: int = 3,
        clock: Callable[[], float] = perf_counter,
    ) -> None:
        if not 30 <= len(cases) <= 50:
            raise ValueError("Full benchmark must contain between 30 and 50 cases.")
        if type(repeat_count) is not int or not 1 <= repeat_count <= 3:
            raise ValueError("repeat_count must be between 1 and 3.")
        self._provider = provider
        self._cases = tuple(cases)
        self._hardware_profile = hardware_profile
        self._repeat_count = repeat_count
        self._clock = clock

    async def run(
        self,
        model_id: str,
        *,
        dataset_version: str = DEFAULT_FULL_DATASET_VERSION,
        temperature: float = 0.1,
        batch_sizes: Sequence[int] = (1, 5),
        context_lengths: Sequence[str] = CONTEXT_LENGTHS,
        cancellation: CancellationSignal | None = None,
        benchmark_id: str | None = None,
        resume_from: FullBenchmarkResult | None = None,
    ) -> FullBenchmarkResult:
        if not model_id.strip():
            raise ValueError("model_id must not be empty.")
        if not dataset_version.strip():
            raise ValueError("dataset_version must not be empty.")
        if not 0 <= temperature <= 2:
            raise ValueError("temperature must be between 0 and 2.")
        normalized_batch_sizes = _normalize_batch_sizes(batch_sizes)
        normalized_context_lengths = _normalize_context_lengths(context_lengths)
        total_runs = len(self._cases) * self._repeat_count
        profile = self._hardware_profile or detect_hardware_profile()
        attempts: list[FullBenchmarkAttemptResult] = []
        start_index = 0
        run_id = benchmark_id or f"bmk_full_{uuid4().hex}"
        if resume_from is not None:
            _validate_resume(
                resume_from,
                model_id=model_id,
                dataset_version=dataset_version,
                total_runs=total_runs,
                batch_sizes=normalized_batch_sizes,
                context_lengths=normalized_context_lengths,
            )
            run_id = resume_from.benchmark_id
            attempts.extend(resume_from.attempts)
            start_index = resume_from.next_run_index

        preflight_failure = await self._preflight(model_id)
        if preflight_failure is not None:
            return self._result(
                run_id,
                model_id,
                dataset_version,
                profile,
                normalized_batch_sizes,
                normalized_context_lengths,
                attempts,
                start_index,
                FullBenchmarkStatus.FAILED,
                preflight_failure,
            )

        for run_index in range(start_index, total_runs):
            if _is_cancelled(cancellation):
                return self._result(
                    run_id,
                    model_id,
                    dataset_version,
                    profile,
                    normalized_batch_sizes,
                    normalized_context_lengths,
                    attempts,
                    run_index,
                    FullBenchmarkStatus.PARTIALLY_COMPLETED
                    if attempts
                    else FullBenchmarkStatus.CANCELLED,
                    BenchmarkFailure("BENCHMARK_INTERRUPTED", "The benchmark was interrupted."),
                )

            case = self._cases[run_index // self._repeat_count]
            repetition = run_index % self._repeat_count + 1
            batch_size = normalized_batch_sizes[run_index % len(normalized_batch_sizes)]
            context_length = normalized_context_lengths[run_index % len(normalized_context_lengths)]
            started = self._clock()
            try:
                response = await self._provider.translate(
                    case.to_request(context_length=context_length),
                    cancellation=cancellation,
                )
                parsed = _coerce_response(response, case.case_id)
                latency = max(0.0, self._clock() - started)
                placeholder_failure = _placeholder_failure(case, parsed)
                if placeholder_failure is None:
                    attempts.append(
                        FullBenchmarkAttemptResult(
                            case.case_id,
                            repetition,
                            batch_size,
                            context_length,
                            "COMPLETED",
                            latency,
                            True,
                            True,
                            1.0,
                        )
                    )
                else:
                    attempts.append(
                        FullBenchmarkAttemptResult(
                            case.case_id,
                            repetition,
                            batch_size,
                            context_length,
                            "FAILED",
                            latency,
                            True,
                            False,
                            0.0,
                            placeholder_failure,
                        )
                    )
            except asyncio.CancelledError:
                return self._result(
                    run_id,
                    model_id,
                    dataset_version,
                    profile,
                    normalized_batch_sizes,
                    normalized_context_lengths,
                    attempts,
                    run_index,
                    FullBenchmarkStatus.PARTIALLY_COMPLETED
                    if attempts
                    else FullBenchmarkStatus.CANCELLED,
                    BenchmarkFailure("BENCHMARK_INTERRUPTED", "The benchmark was interrupted."),
                )
            except ResponseParseError as error:
                attempts.append(
                    _failed_attempt(
                        case.case_id,
                        repetition,
                        batch_size,
                        context_length,
                        max(0.0, self._clock() - started),
                        _parse_failure(error),
                    )
                )
            except TranslationProviderError as error:
                attempts.append(
                    _failed_attempt(
                        case.case_id,
                        repetition,
                        batch_size,
                        context_length,
                        max(0.0, self._clock() - started),
                        BenchmarkFailure(error.code.value, str(error)),
                    )
                )
            except (TranslationSchemaError, ValueError) as error:
                attempts.append(
                    _failed_attempt(
                        case.case_id,
                        repetition,
                        batch_size,
                        context_length,
                        max(0.0, self._clock() - started),
                        BenchmarkFailure("SCHEMA_VALIDATION_FAILED", str(error), critical=True),
                    )
                )
            except Exception as error:
                attempts.append(
                    _failed_attempt(
                        case.case_id,
                        repetition,
                        batch_size,
                        context_length,
                        max(0.0, self._clock() - started),
                        BenchmarkFailure("PROVIDER_ERROR", str(error)),
                    )
                )

        final_status = (
            FullBenchmarkStatus.COMPLETED
            if all(attempt.status == "COMPLETED" for attempt in attempts)
            else FullBenchmarkStatus.FAILED
        )
        return self._result(
            run_id,
            model_id,
            dataset_version,
            profile,
            normalized_batch_sizes,
            normalized_context_lengths,
            attempts,
            total_runs,
            final_status,
            None,
        )

    async def _preflight(self, model_id: str) -> BenchmarkFailure | None:
        try:
            health = await self._provider.health_check()
            health_status = getattr(health.status, "value", health.status)
            if health_status != ProviderHealthStatus.AVAILABLE.value:
                return BenchmarkFailure(
                    "OLLAMA_UNAVAILABLE", "The local translation provider is unavailable."
                )
            models = await self._provider.list_models()
        except TranslationProviderError as error:
            return BenchmarkFailure(error.code.value, str(error))
        except Exception as error:
            return BenchmarkFailure("OLLAMA_UNAVAILABLE", str(error))
        if not any(model.name == model_id for model in models):
            return BenchmarkFailure(
                "MODEL_NOT_INSTALLED",
                "The requested local model is not installed; benchmark will not download it.",
            )
        return None

    def _result(
        self,
        benchmark_id: str,
        model_id: str,
        dataset_version: str,
        hardware_profile: HardwareProfile,
        batch_sizes: tuple[int, ...],
        context_lengths: tuple[str, ...],
        attempts: list[FullBenchmarkAttemptResult],
        next_run_index: int,
        status: FullBenchmarkStatus,
        failure: BenchmarkFailure | None,
    ) -> FullBenchmarkResult:
        latencies = [
            attempt.latency_seconds for attempt in attempts if attempt.latency_seconds is not None
        ]
        quality_scores = [attempt.quality_score for attempt in attempts]
        return FullBenchmarkResult(
            benchmark_id=benchmark_id,
            benchmark_version=FULL_BENCHMARK_VERSION,
            dataset_version=dataset_version,
            model_id=model_id,
            hardware_profile=hardware_profile,
            status=status,
            recommendation=_recommendation(status, attempts, failure),
            attempts=tuple(attempts),
            total_runs=len(self._cases) * self._repeat_count,
            next_run_index=next_run_index,
            batch_sizes=batch_sizes,
            context_lengths=context_lengths,
            average_latency_seconds=(sum(latencies) / len(latencies) if latencies else None),
            quality_score=(sum(quality_scores) / len(quality_scores) if quality_scores else None),
            failure=failure,
        )


def _normalize_batch_sizes(values: Sequence[int]) -> tuple[int, ...]:
    normalized = tuple(values)
    if not normalized or any(
        type(value) is not int or not 1 <= value <= 100 for value in normalized
    ):
        raise ValueError("batch_sizes must contain integers between 1 and 100.")
    return normalized


def _normalize_context_lengths(values: Sequence[str]) -> tuple[str, ...]:
    normalized = tuple(value.upper() for value in values)
    if not normalized or any(value not in CONTEXT_LENGTHS for value in normalized):
        raise ValueError("context_lengths must use SHORT, MEDIUM, or LONG.")
    return normalized


def _validate_resume(
    result: FullBenchmarkResult,
    *,
    model_id: str,
    dataset_version: str,
    total_runs: int,
    batch_sizes: tuple[int, ...],
    context_lengths: tuple[str, ...],
) -> None:
    if result.model_id != model_id or result.dataset_version != dataset_version:
        raise ValueError("resume_from belongs to a different benchmark configuration.")
    if (
        result.total_runs != total_runs
        or result.batch_sizes != batch_sizes
        or result.context_lengths != context_lengths
    ):
        raise ValueError("resume_from parameters do not match the benchmark configuration.")
    if (
        result.next_run_index != len(result.attempts)
        or not 0 <= result.next_run_index <= total_runs
    ):
        raise ValueError("resume_from has an invalid next_run_index.")


def _placeholder_failure(case: FullBenchmarkCase, response: Any) -> BenchmarkFailure | None:
    translated = response.segments[0].translated_text
    if sorted(extract_placeholders(translated)) != sorted(case.placeholders):
        return BenchmarkFailure(
            "PLACEHOLDER_MISMATCH",
            "The model did not preserve benchmark placeholders exactly.",
            critical=True,
        )
    return None


def _failed_attempt(
    case_id: str,
    repetition: int,
    batch_size: int,
    context_length: str,
    latency: float,
    failure: BenchmarkFailure,
) -> FullBenchmarkAttemptResult:
    return FullBenchmarkAttemptResult(
        case_id,
        repetition,
        batch_size,
        context_length,
        "FAILED",
        latency,
        False,
        False,
        0.0,
        failure,
    )


def _recommendation(
    status: FullBenchmarkStatus,
    attempts: Sequence[FullBenchmarkAttemptResult],
    failure: BenchmarkFailure | None,
) -> FullBenchmarkRecommendation:
    if failure is not None and failure.code != "BENCHMARK_INTERRUPTED":
        return FullBenchmarkRecommendation.REJECTED
    if any(attempt.failure is not None and attempt.failure.critical for attempt in attempts):
        return FullBenchmarkRecommendation.REJECTED
    if status is FullBenchmarkStatus.COMPLETED:
        successful = sum(attempt.status == "COMPLETED" for attempt in attempts)
        if successful / len(attempts) < 0.98:
            return FullBenchmarkRecommendation.REJECTED
        return FullBenchmarkRecommendation.RECOMMENDED_DEFAULT
    if status in {FullBenchmarkStatus.CANCELLED, FullBenchmarkStatus.PARTIALLY_COMPLETED}:
        return FullBenchmarkRecommendation.EXPERIMENTAL
    return FullBenchmarkRecommendation.FALLBACK_ONLY


def _is_cancelled(signal: CancellationSignal | None) -> bool:
    return signal is not None and signal.is_cancelled


__all__ = ["FullBenchmarkProvider", "FullBenchmarkRunner"]
