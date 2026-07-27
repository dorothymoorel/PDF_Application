from typing import Literal

from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, Field
from starlette.exceptions import HTTPException
from starlette.middleware.base import RequestResponseEndpoint
from starlette.middleware.cors import CORSMiddleware

from transloka_api import __version__
from transloka_api.config import Settings
from transloka_api.exception_handlers import (
    TransLokaError,
    http_exception_handler,
    request_validation_exception_handler,
    transloka_exception_handler,
    unexpected_exception_handler,
)
from transloka_api.middleware import (
    CORS_ALLOWED_HEADERS,
    CORS_ALLOWED_METHODS,
    CORS_EXPOSE_HEADERS,
    OriginValidationMiddleware,
    RequestIdMiddleware,
)


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    service: Literal["transloka-api"] = "transloka-api"
    version: str = __version__


class ComponentHealth(BaseModel):
    status: Literal["UNAVAILABLE"] = "UNAVAILABLE"


class SystemComponents(BaseModel):
    database: ComponentHealth = Field(default_factory=ComponentHealth)
    filesystem: ComponentHealth = Field(default_factory=ComponentHealth)
    worker: ComponentHealth = Field(default_factory=ComponentHealth)
    ollama: ComponentHealth = Field(default_factory=ComponentHealth)
    ocr: ComponentHealth = Field(default_factory=ComponentHealth)


class SystemHealthData(BaseModel):
    status: Literal["DEGRADED"] = "DEGRADED"
    components: SystemComponents = Field(default_factory=SystemComponents)


class SystemHealthResponse(BaseModel):
    data: SystemHealthData = Field(default_factory=SystemHealthData)


def create_app(settings: Settings | None = None) -> FastAPI:
    effective_settings = settings or Settings()
    application = FastAPI(title="TransLoka", version=__version__, debug=False)
    application.state.settings = effective_settings

    @application.middleware("http")
    async def normalize_unexpected_errors(
        request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        try:
            return await call_next(request)
        except Exception as exc:
            return await unexpected_exception_handler(request, exc)

    application.add_middleware(
        CORSMiddleware,
        allow_origins=list(effective_settings.web_origins),
        allow_credentials=False,
        allow_methods=list(CORS_ALLOWED_METHODS),
        allow_headers=list(CORS_ALLOWED_HEADERS),
        expose_headers=list(CORS_EXPOSE_HEADERS),
    )
    application.add_middleware(
        OriginValidationMiddleware,
        allowed_origins=effective_settings.web_origins,
    )
    application.add_middleware(RequestIdMiddleware)
    application.add_exception_handler(TransLokaError, transloka_exception_handler)
    application.add_exception_handler(RequestValidationError, request_validation_exception_handler)
    application.add_exception_handler(HTTPException, http_exception_handler)

    @application.get(
        "/health",
        operation_id="get_health",
        response_model=HealthResponse,
        summary="Get API health",
        tags=["System"],
    )
    def get_health() -> HealthResponse:
        return HealthResponse()

    @application.get(
        "/api/v1/system/health",
        operation_id="get_system_health",
        response_model=SystemHealthResponse,
        summary="Get placeholder system health",
        tags=["System"],
    )
    def get_system_health() -> SystemHealthResponse:
        return SystemHealthResponse()

    return application
