from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any, Literal

from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, Field
from starlette.exceptions import HTTPException
from starlette.middleware.base import RequestResponseEndpoint
from starlette.middleware.cors import CORSMiddleware
from transloka_core.database import create_session_factory, create_sqlite_engine

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
    ClientHeaderMiddleware,
    OriginValidationMiddleware,
    RequestIdMiddleware,
)
from transloka_api.routers.documents import router as documents_router
from transloka_api.routers.projects import router as projects_router
from transloka_api.schemas import ErrorResponse

_HEALTH_ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    403: {
        "description": "The request origin is not allowed.",
        "model": ErrorResponse,
    },
    500: {
        "description": "An unexpected server error was normalized.",
        "model": ErrorResponse,
    },
}


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

    @asynccontextmanager
    async def lifespan(application: FastAPI) -> AsyncIterator[None]:
        engine = create_sqlite_engine(effective_settings.data_directories)
        application.state.session_factory = create_session_factory(engine)
        try:
            yield
        finally:
            engine.dispose()

    application = FastAPI(
        title="TransLoka",
        version=__version__,
        debug=False,
        lifespan=lifespan,
    )
    application.state.settings = effective_settings

    @application.middleware("http")
    async def normalize_unexpected_errors(
        request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        try:
            return await call_next(request)
        except Exception as exc:
            return await unexpected_exception_handler(request, exc)

    application.add_middleware(ClientHeaderMiddleware)
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
    application.include_router(documents_router)
    application.include_router(projects_router)

    @application.get(
        "/health",
        operation_id="get_health",
        response_model=HealthResponse,
        responses=_HEALTH_ERROR_RESPONSES,
        summary="Get API health",
        tags=["System"],
    )
    def get_health() -> HealthResponse:
        return HealthResponse()

    @application.get(
        "/api/v1/system/health",
        operation_id="get_system_health",
        response_model=SystemHealthResponse,
        responses=_HEALTH_ERROR_RESPONSES,
        summary="Get placeholder system health",
        tags=["System"],
    )
    def get_system_health() -> SystemHealthResponse:
        return SystemHealthResponse()

    return application
