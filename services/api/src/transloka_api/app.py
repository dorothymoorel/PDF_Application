from typing import Literal

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, Field
from starlette.exceptions import HTTPException

from transloka_api import __version__
from transloka_api.config import Settings
from transloka_api.exception_handlers import (
    TransLokaError,
    http_exception_handler,
    request_validation_exception_handler,
    transloka_exception_handler,
)
from transloka_api.middleware import RequestIdMiddleware


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
