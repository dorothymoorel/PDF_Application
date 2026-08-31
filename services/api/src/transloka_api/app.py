from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any, Literal

from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool
from starlette.exceptions import HTTPException
from starlette.middleware.base import RequestResponseEndpoint
from starlette.middleware.cors import CORSMiddleware
from transloka_core.backup.restore import (
    MAINTENANCE_MARKER_FILENAME,
    ApplicationMutationLock,
    FileRestoreCoordinator,
    RestoreWorkflow,
)
from transloka_core.database import create_session_factory, create_sqlite_engine
from transloka_worker.queue import (
    create_analysis_producer,
    create_backup_producer,
    create_ocr_producer,
    create_reconstruction_producer,
    create_translation_producer,
    resolve_queue_configuration,
)

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
from transloka_api.routers.backups import router as backups_router
from transloka_api.routers.benchmarks import router as benchmarks_router
from transloka_api.routers.documents import document_router as document_detail_router
from transloka_api.routers.documents import router as documents_router
from transloka_api.routers.exports import router as exports_router
from transloka_api.routers.glossaries import router as glossaries_router
from transloka_api.routers.jobs import router as jobs_router
from transloka_api.routers.maintenance import router as maintenance_router
from transloka_api.routers.models import router as models_router
from transloka_api.routers.ocr import router as ocr_router
from transloka_api.routers.pages import router as pages_router
from transloka_api.routers.projects import router as projects_router
from transloka_api.routers.reconstruction import router as reconstruction_router
from transloka_api.routers.review import router as review_router
from transloka_api.routers.revisions import router as revisions_router
from transloka_api.routers.segments import router as segments_router
from transloka_api.routers.settings import router as settings_router
from transloka_api.routers.translation import router as translation_router
from transloka_api.routers.warnings import router as warnings_router
from transloka_api.schemas import ErrorResponse
from transloka_api.services.benchmarks import (
    ProductionFullBenchmarkRunner,
    ProductionQuickBenchmarkRunner,
)

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
        session_factory = create_session_factory(engine)
        try:
            analysis_queue_owner = create_analysis_producer(
                resolve_queue_configuration(effective_settings.data_directories.root)
            )
            try:
                translation_queue_owner = create_translation_producer(
                    resolve_queue_configuration(effective_settings.data_directories.root)
                )
                try:
                    ocr_queue_owner = create_ocr_producer(
                        resolve_queue_configuration(effective_settings.data_directories.root)
                    )
                    try:
                        reconstruction_queue_owner = create_reconstruction_producer(
                            resolve_queue_configuration(effective_settings.data_directories.root)
                        )
                        try:
                            backup_queue_owner = create_backup_producer(
                                resolve_queue_configuration(
                                    effective_settings.data_directories.root
                                )
                            )
                        except Exception:
                            reconstruction_queue_owner.close()
                            raise
                    except Exception:
                        ocr_queue_owner.close()
                        raise
                except Exception:
                    translation_queue_owner.close()
                    raise
            except Exception:
                analysis_queue_owner.close()
                raise
        except Exception:
            engine.dispose()
            raise
        application.state.session_factory = session_factory
        application.state.analysis_queue_owner = analysis_queue_owner
        application.state.analysis_queue = analysis_queue_owner.queue
        application.state.translation_queue_owner = translation_queue_owner
        application.state.translation_queue = translation_queue_owner.queue
        application.state.ocr_queue_owner = ocr_queue_owner
        application.state.ocr_queue = ocr_queue_owner.queue
        application.state.reconstruction_queue_owner = reconstruction_queue_owner
        application.state.reconstruction_queue = reconstruction_queue_owner.queue
        application.state.backup_queue_owner = backup_queue_owner
        application.state.backup_queue = backup_queue_owner.queue
        application.state.quick_benchmark_runner = ProductionQuickBenchmarkRunner(session_factory)
        application.state.full_benchmark_runner = ProductionFullBenchmarkRunner(session_factory)

        def close_database() -> None:
            engine.dispose()

        def reopen_database() -> None:
            nonlocal engine, session_factory
            engine.dispose()
            engine = create_sqlite_engine(effective_settings.data_directories)
            session_factory = create_session_factory(engine)
            application.state.session_factory = session_factory
            application.state.quick_benchmark_runner = ProductionQuickBenchmarkRunner(
                session_factory
            )
            application.state.full_benchmark_runner = ProductionFullBenchmarkRunner(session_factory)

        coordinator = FileRestoreCoordinator(
            effective_settings.data_directories,
            close_database=close_database,
            reopen_database=reopen_database,
        )
        application.state.restore_workflow = RestoreWorkflow(
            effective_settings.data_directories,
            coordinator=coordinator,
        )
        try:
            yield
        finally:
            backup_queue_owner.close()
            reconstruction_queue_owner.close()
            ocr_queue_owner.close()
            translation_queue_owner.close()
            analysis_queue_owner.close()
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

    @application.middleware("http")
    async def enforce_maintenance_mode(
        request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        marker = effective_settings.data_directories.root / MAINTENANCE_MARKER_FILENAME
        if marker.is_file() and not _maintenance_request_allowed(request):
            return await _maintenance_response(request)
        if (
            request.method not in {"POST", "PUT", "PATCH", "DELETE"}
            or _is_restore_request(request)
            or _is_maintenance_request(request)
        ):
            return await call_next(request)

        mutation_lock = ApplicationMutationLock(effective_settings.data_directories)
        await run_in_threadpool(mutation_lock.acquire)
        try:
            if marker.is_file():
                return await _maintenance_response(request)
            return await call_next(request)
        finally:
            mutation_lock.release()

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

    @application.middleware("http")
    async def expose_job_poll_hint(
        request: Request, call_next: RequestResponseEndpoint
    ) -> Response:
        response = await call_next(request)
        if request.url.path.startswith("/api/v1/jobs/") and "Retry-After" in response.headers:
            response.headers["Access-Control-Expose-Headers"] = ", ".join(
                (*CORS_EXPOSE_HEADERS, "Retry-After")
            )
        return response

    application.add_exception_handler(TransLokaError, transloka_exception_handler)
    application.add_exception_handler(RequestValidationError, request_validation_exception_handler)
    application.add_exception_handler(HTTPException, http_exception_handler)
    application.include_router(backups_router)
    application.include_router(benchmarks_router)
    application.include_router(documents_router)
    application.include_router(document_detail_router)
    application.include_router(exports_router)
    application.include_router(glossaries_router)
    application.include_router(jobs_router)
    application.include_router(maintenance_router)
    application.include_router(models_router)
    application.include_router(ocr_router)
    application.include_router(pages_router)
    application.include_router(projects_router)
    application.include_router(reconstruction_router)
    application.include_router(review_router)
    application.include_router(revisions_router)
    application.include_router(segments_router)
    application.include_router(settings_router)
    application.include_router(translation_router)
    application.include_router(warnings_router)

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


def _maintenance_request_allowed(request: Request) -> bool:
    if request.method == "OPTIONS":
        return True
    path = request.url.path.rstrip("/") or "/"
    if path in {"/health", "/api/v1/system/health"}:
        return request.method in {"GET", "HEAD"}
    parts = path.split("/")
    return (
        request.method in {"GET", "HEAD"}
        and len(parts) == 5
        and parts[1:4] == ["api", "v1", "jobs"]
        and bool(parts[4])
    )


def _is_restore_request(request: Request) -> bool:
    parts = request.url.path.rstrip("/").split("/")
    return (
        request.method == "POST"
        and len(parts) == 6
        and parts[1:4] == ["api", "v1", "backups"]
        and bool(parts[4])
        and parts[5] == "restore"
    )


def _is_maintenance_request(request: Request) -> bool:
    parts = request.url.path.rstrip("/").split("/")
    return (
        request.method == "POST"
        and len(parts) == 5
        and parts[1:4] == ["api", "v1", "maintenance"]
        and bool(parts[4])
    )


async def _maintenance_response(request: Request) -> Response:
    return await transloka_exception_handler(
        request,
        TransLokaError(
            code="APPLICATION_IN_MAINTENANCE_MODE",
            message="The application is temporarily unavailable during maintenance.",
            status_code=503,
        ),
    )
