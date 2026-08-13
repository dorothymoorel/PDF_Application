from typing import Any, Never

from fastapi import APIRouter, Request
from pydantic import BaseModel
from transloka_api.exception_handlers import TransLokaError
from transloka_api.middleware import get_request_id
from transloka_api.schemas import ErrorResponse
from transloka_api.schemas.projects import ResponseMeta
from transloka_translation.providers import ProviderHealthStatus, TranslationProviderError
from transloka_translation.providers.ollama import (
    OllamaTranslationProvider,
    RemoteOllamaEndpointError,
)

_ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    403: {
        "description": "A remote Ollama endpoint was blocked.",
        "model": ErrorResponse,
    },
    503: {
        "description": "The local Ollama service is unavailable.",
        "model": ErrorResponse,
    },
}

router = APIRouter(prefix="/api/v1/models", tags=["Models"])


class OllamaHealthData(BaseModel):
    status: ProviderHealthStatus
    base_url: str
    version: str


class OllamaHealthResponse(BaseModel):
    data: OllamaHealthData
    meta: ResponseMeta


class DetectedLocalModel(BaseModel):
    ollama_model_name: str
    disk_size_bytes: int | None


class DetectedLocalModelsResponse(BaseModel):
    data: list[DetectedLocalModel]
    meta: ResponseMeta


@router.get(
    "/ollama/health",
    operation_id="get_ollama_health",
    response_model=OllamaHealthResponse,
    responses=_ERROR_RESPONSES,
)
async def get_ollama_health(request: Request) -> OllamaHealthResponse:
    provider = _provider(request)
    health = await provider.health_check()
    return OllamaHealthResponse(
        data=OllamaHealthData(
            status=health.status,
            base_url=provider.base_url,
            version=health.version or "unknown",
        ),
        meta=ResponseMeta(request_id=_request_id()),
    )


@router.get(
    "",
    operation_id="list_detected_local_models",
    response_model=DetectedLocalModelsResponse,
    responses=_ERROR_RESPONSES,
)
async def list_detected_local_models(request: Request) -> DetectedLocalModelsResponse:
    provider = _provider(request)
    try:
        models = await provider.list_models()
    except TranslationProviderError as exc:
        _raise_ollama_unavailable(exc)
    return DetectedLocalModelsResponse(
        data=[
            DetectedLocalModel(
                ollama_model_name=model.name,
                disk_size_bytes=model.size_bytes,
            )
            for model in models
        ],
        meta=ResponseMeta(request_id=_request_id()),
    )


def _provider(request: Request) -> OllamaTranslationProvider:
    configured = getattr(request.app.state, "ollama_provider", None)
    if configured is not None:
        if not isinstance(configured, OllamaTranslationProvider):
            raise RuntimeError("The Ollama provider is not configured correctly.")
        return configured
    try:
        return OllamaTranslationProvider()
    except RemoteOllamaEndpointError as exc:
        raise TransLokaError(
            code="REMOTE_OLLAMA_BLOCKED",
            message="The configured Ollama endpoint is not local.",
            status_code=403,
        ) from exc


def _request_id() -> str:
    request_id = get_request_id()
    if request_id is None:
        raise RuntimeError("The request ID middleware is not configured.")
    return request_id


def _raise_ollama_unavailable(exc: TranslationProviderError) -> Never:
    raise TransLokaError(
        code="OLLAMA_UNAVAILABLE",
        message="The local Ollama service is unavailable.",
        status_code=503,
    ) from exc
