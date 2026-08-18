from __future__ import annotations

from typing import Annotated, Protocol, cast

from fastapi import APIRouter, Header, Request, status
from pydantic import BaseModel, ConfigDict, Field
from transloka_api.exception_handlers.exceptions import TransLokaError
from transloka_api.middleware import get_request_id
from transloka_api.schemas.errors import ErrorResponse
from transloka_api.schemas.projects import ResponseMeta
from transloka_translation.benchmark import QuickBenchmarkResult


class _BenchmarkRunner(Protocol):
    async def run(
        self,
        model_id: str,
        *,
        dataset_version: str,
        temperature: float,
        batch_sizes: list[int],
        benchmark_id: str,
    ) -> QuickBenchmarkResult: ...


router = APIRouter(prefix="/api/v1/models", tags=["Benchmarks"])


class QuickBenchmarkRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dataset_version: str = Field(
        default="translation_benchmark_en_id_0.1", min_length=1, max_length=100
    )
    temperature: float = Field(default=0.1, ge=0, le=2)
    batch_sizes: list[int] = Field(default_factory=lambda: [1, 5], min_length=1, max_length=8)


class BenchmarkFailureResponse(BaseModel):
    code: str
    message: str
    critical: bool = False


class BenchmarkCaseResponse(BaseModel):
    case_id: str
    status: str
    latency_seconds: float | None
    structured_output_valid: bool
    placeholder_integrity: bool
    failure: BenchmarkFailureResponse | None = None


class QuickBenchmarkData(BaseModel):
    benchmark_id: str
    benchmark_version: str
    dataset_version: str
    model_id: str
    status: str
    recommendation: str
    cases: list[BenchmarkCaseResponse]
    total_cases: int = Field(ge=0)
    successful_cases: int = Field(ge=0)
    failed_cases: int = Field(ge=0)
    average_latency_seconds: float | None
    batch_sizes: list[int]
    temperature: float
    failure: BenchmarkFailureResponse | None = None


class QuickBenchmarkResponse(BaseModel):
    data: QuickBenchmarkData
    meta: ResponseMeta


@router.post(
    "/{model_id}/benchmarks/quick",
    operation_id="start_quick_benchmark",
    response_model=QuickBenchmarkResponse,
    responses={
        403: {
            "description": "The request was rejected by local security policy.",
            "model": ErrorResponse,
        },
        404: {"description": "The local model was not found.", "model": ErrorResponse},
        409: {
            "description": "The benchmark request conflicts with an existing run.",
            "model": ErrorResponse,
        },
        422: {"description": "The request contains invalid values.", "model": ErrorResponse},
        503: {"description": "The local model provider is unavailable.", "model": ErrorResponse},
    },
    status_code=status.HTTP_202_ACCEPTED,
)
async def start_quick_benchmark(
    model_id: str,
    payload: QuickBenchmarkRequest,
    request: Request,
    idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=200)],
) -> QuickBenchmarkResponse:
    runner = _runner(request)
    try:
        result = await runner.run(
            model_id,
            dataset_version=payload.dataset_version,
            temperature=payload.temperature,
            batch_sizes=payload.batch_sizes,
            benchmark_id=f"{model_id}:{idempotency_key}",
        )
    except ValueError as error:
        raise TransLokaError(
            code="VALIDATION_ERROR",
            message=str(error),
            status_code=422,
        ) from error

    if result.failure is not None and result.status.value == "FAILED" and not result.cases:
        if result.failure.code == "MODEL_NOT_INSTALLED":
            raise TransLokaError(
                code="MODEL_NOT_INSTALLED", message=result.failure.message, status_code=404
            )
        raise TransLokaError(
            code=result.failure.code, message=result.failure.message, status_code=503
        )
    return QuickBenchmarkResponse(
        data=_response_data(result),
        meta=ResponseMeta(request_id=_request_id()),
    )


def _runner(request: Request) -> _BenchmarkRunner:
    configured = getattr(request.app.state, "quick_benchmark_runner", None)
    if configured is not None and callable(getattr(configured, "run", None)):
        return cast(_BenchmarkRunner, configured)
    raise TransLokaError(
        code="BENCHMARK_NOT_CONFIGURED",
        message="The local benchmark provider is not configured.",
        status_code=503,
    )


def _response_data(result: QuickBenchmarkResult) -> QuickBenchmarkData:
    payload = result.to_dict()
    return QuickBenchmarkData.model_validate(payload)


def _request_id() -> str:
    request_id = get_request_id()
    if request_id is None:
        raise RuntimeError("The request ID middleware is not configured.")
    return request_id
