from __future__ import annotations

import asyncio
from collections import Counter
from collections.abc import Callable, Iterable, Sequence
from time import perf_counter
from typing import Any, Protocol
from uuid import uuid4

from transloka_translation.parsing import ResponseParseError, parse_translation_response
from transloka_translation.providers import (
    CancellationSignal,
    LocalModel,
    ProviderHealthStatus,
    TranslationProviderError,
)
from transloka_translation.schemas import TranslationResponse, TranslationSchemaError

from .cases import QUICK_BENCHMARK_CASES, QuickBenchmarkCase, extract_placeholders
from .models import (
    BenchmarkCaseResult,
    BenchmarkFailure,
    QuickBenchmarkRecommendation,
    QuickBenchmarkResult,
    QuickBenchmarkStatus,
)

BENCHMARK_VERSION = "0.1"
DEFAULT_DATASET_VERSION = "translation_benchmark_en_id_0.1"


class BenchmarkProvider(Protocol):
    async def health_check(self) -> Any: ...

    async def list_models(self) -> list[LocalModel]: ...

    async def translate(
        self,
        request: Any,
        *,
        cancellation: CancellationSignal | None = None,
    ) -> object: ...


class QuickBenchmarkRunner:
    """Run the bounded, one-pass benchmark without downloading or mutating models."""

    def __init__(
        self,
        provider: BenchmarkProvider,
        *,
        cases: Sequence[QuickBenchmarkCase] = QUICK_BENCHMARK_CASES,
        clock: Callable[[], float] = perf_counter,
    ) -> None:
        if not 5 <= len(cases) <= 8:
            raise ValueError("Quick benchmark must contain between 5 and 8 cases.")
        self._provider = provider
        self._cases = tuple(cases)
        self._clock = clock

    async def run(
        self,
        model_id: str,
        *,
        dataset_version: str = DEFAULT_DATASET_VERSION,
        temperature: float = 0.1,
        batch_sizes: Iterable[int] = (1, 5),
        cancellation: CancellationSignal | None = None,
        benchmark_id: str | None = None,
    ) -> QuickBenchmarkResult:
        if not model_id.strip():
            raise ValueError("model_id must not be empty.")
        if not dataset_version.strip():
            raise ValueError("dataset_version must not be empty.")
        if not 0 <= temperature <= 2:
            raise ValueError("temperature must be between 0 and 2.")
        normalized_batch_sizes = _normalize_batch_sizes(batch_sizes)
        run_id = benchmark_id or f"bmk_quick_{uuid4().hex}"

        preflight_failure = await self._preflight(model_id)
        if preflight_failure is not None:
            return self._result(
                run_id,
                model_id,
                dataset_version,
                temperature,
                normalized_batch_sizes,
                (),
                QuickBenchmarkStatus.FAILED,
                preflight_failure,
            )

        if _is_cancelled(cancellation):
            return self._result(
                run_id,
                model_id,
                dataset_version,
                temperature,
                normalized_batch_sizes,
                (),
                QuickBenchmarkStatus.CANCELLED,
                BenchmarkFailure("BENCHMARK_INTERRUPTED", "The benchmark was interrupted."),
            )

        results: list[BenchmarkCaseResult] = []
        interrupted = False
        for case in self._cases:
            if _is_cancelled(cancellation):
                interrupted = True
                break
            started = self._clock()
            try:
                response = await self._provider.translate(
                    case.to_request(),
                    cancellation=cancellation,
                )
                parsed = _coerce_response(response, case.case_id)
                latency = max(0.0, self._clock() - started)
                placeholder_failure = _placeholder_failure(case, parsed)
                if placeholder_failure is not None:
                    results.append(
                        BenchmarkCaseResult(
                            case.case_id,
                            "FAILED",
                            latency,
                            True,
                            False,
                            placeholder_failure,
                        )
                    )
                else:
                    results.append(
                        BenchmarkCaseResult(case.case_id, "COMPLETED", latency, True, True)
                    )
            except asyncio.CancelledError:
                interrupted = True
                results.append(
                    BenchmarkCaseResult(
                        case.case_id,
                        "INTERRUPTED",
                        max(0.0, self._clock() - started),
                        False,
                        False,
                        BenchmarkFailure(
                            "BENCHMARK_INTERRUPTED",
                            "The benchmark was interrupted.",
                        ),
                    )
                )
                break
            except ResponseParseError as error:
                results.append(
                    _failed_case(
                        case.case_id,
                        max(0.0, self._clock() - started),
                        _parse_failure(error),
                    )
                )
            except TranslationProviderError as error:
                results.append(
                    _failed_case(
                        case.case_id,
                        max(0.0, self._clock() - started),
                        BenchmarkFailure(error.code.value, str(error)),
                    )
                )
            except (TranslationSchemaError, ValueError) as error:
                results.append(
                    _failed_case(
                        case.case_id,
                        max(0.0, self._clock() - started),
                        BenchmarkFailure("SCHEMA_VALIDATION_FAILED", str(error), critical=True),
                    )
                )
            except Exception as error:  # provider boundary: convert unexpected failures to a result
                results.append(
                    _failed_case(
                        case.case_id,
                        max(0.0, self._clock() - started),
                        BenchmarkFailure("PROVIDER_ERROR", str(error)),
                    )
                )

        status = _status(results, interrupted)
        failure = (
            BenchmarkFailure("BENCHMARK_INTERRUPTED", "The benchmark was interrupted.")
            if interrupted
            else None
        )
        return self._result(
            run_id,
            model_id,
            dataset_version,
            temperature,
            normalized_batch_sizes,
            tuple(results),
            status,
            failure,
        )

    async def _preflight(self, model_id: str) -> BenchmarkFailure | None:
        try:
            health = await self._provider.health_check()
            health_status = getattr(health.status, "value", health.status)
            if health_status != ProviderHealthStatus.AVAILABLE.value:
                return BenchmarkFailure(
                    "OLLAMA_UNAVAILABLE",
                    "The local translation provider is unavailable.",
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
        temperature: float,
        batch_sizes: tuple[int, ...],
        cases: tuple[BenchmarkCaseResult, ...],
        status: QuickBenchmarkStatus,
        failure: BenchmarkFailure | None,
    ) -> QuickBenchmarkResult:
        latencies = [case.latency_seconds for case in cases if case.latency_seconds is not None]
        return QuickBenchmarkResult(
            benchmark_id=benchmark_id,
            benchmark_version=BENCHMARK_VERSION,
            dataset_version=dataset_version,
            model_id=model_id,
            status=status,
            recommendation=_recommendation(status, cases, failure),
            cases=cases,
            average_latency_seconds=(sum(latencies) / len(latencies) if latencies else None),
            batch_sizes=batch_sizes,
            temperature=temperature,
            failure=failure,
        )


def _normalize_batch_sizes(values: Iterable[int]) -> tuple[int, ...]:
    normalized = tuple(values)
    if not normalized or any(
        type(value) is not int or not 1 <= value <= 100 for value in normalized
    ):
        raise ValueError("batch_sizes must contain integers between 1 and 100.")
    return normalized


def _coerce_response(response: object, case_id: str) -> TranslationResponse:
    if isinstance(response, TranslationResponse):
        response.validate_segment_ids((case_id,))
        if any(not segment.translated_text.strip() for segment in response.segments):
            raise TranslationSchemaError("Translation response contains empty translated text.")
        return response
    if isinstance(response, str):
        return parse_translation_response(response, known_segment_ids=(case_id,))
    if isinstance(response, dict):
        parsed = TranslationResponse.from_dict(response, known_segment_ids=(case_id,))
        if any(not segment.translated_text.strip() for segment in parsed.segments):
            raise TranslationSchemaError("Translation response contains empty translated text.")
        return parsed
    raise TranslationSchemaError("Provider response must be JSON text or a translation response.")


def _placeholder_failure(
    case: QuickBenchmarkCase,
    response: TranslationResponse,
) -> BenchmarkFailure | None:
    translated = response.segments[0].translated_text
    expected = Counter(case.placeholders)
    actual = Counter(extract_placeholders(translated))
    if expected != actual:
        return BenchmarkFailure(
            "PLACEHOLDER_MISMATCH",
            "The model did not preserve benchmark placeholders exactly.",
            critical=True,
        )
    return None


def _parse_failure(error: ResponseParseError) -> BenchmarkFailure:
    code = error.code.value
    return BenchmarkFailure(
        code if code in {"INVALID_JSON", "MARKDOWN_WRAPPER"} else "SCHEMA_VALIDATION_FAILED",
        str(error),
        critical=True,
    )


def _failed_case(case_id: str, latency: float, failure: BenchmarkFailure) -> BenchmarkCaseResult:
    return BenchmarkCaseResult(case_id, "FAILED", latency, False, False, failure)


def _status(cases: Sequence[BenchmarkCaseResult], interrupted: bool) -> QuickBenchmarkStatus:
    if interrupted:
        return QuickBenchmarkStatus.PARTIALLY_COMPLETED if cases else QuickBenchmarkStatus.CANCELLED
    if cases and all(case.status == "COMPLETED" for case in cases):
        return QuickBenchmarkStatus.COMPLETED
    return QuickBenchmarkStatus.FAILED


def _recommendation(
    status: QuickBenchmarkStatus,
    cases: Sequence[BenchmarkCaseResult],
    failure: BenchmarkFailure | None,
) -> QuickBenchmarkRecommendation:
    if failure is not None and failure.code != "BENCHMARK_INTERRUPTED":
        return QuickBenchmarkRecommendation.REJECTED
    if any(case.failure is not None and case.failure.critical for case in cases):
        return QuickBenchmarkRecommendation.REJECTED
    if status is QuickBenchmarkStatus.COMPLETED:
        return QuickBenchmarkRecommendation.RECOMMENDED_DEFAULT
    if status in {QuickBenchmarkStatus.CANCELLED, QuickBenchmarkStatus.PARTIALLY_COMPLETED}:
        return QuickBenchmarkRecommendation.EXPERIMENTAL
    return QuickBenchmarkRecommendation.FALLBACK_ONLY


def _is_cancelled(signal: CancellationSignal | None) -> bool:
    return signal is not None and signal.is_cancelled
