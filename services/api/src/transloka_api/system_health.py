from __future__ import annotations

import importlib.util
import os
import time
from collections.abc import Callable
from typing import Literal, Protocol, cast

from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker
from transloka_core.storage import LocalDataDirectories
from transloka_documents.ocr.base import OCRHealth
from transloka_documents.ocr.paddle import PaddleOCRProviderAdapter
from transloka_translation.providers import ProviderHealth, ProviderHealthStatus
from transloka_translation.providers.ollama import OllamaTranslationProvider
from transloka_worker.health import PersistedWorkerHeartbeat, WorkerHeartbeatStore, WorkerStatus

from transloka_api.schemas.projects import ResponseMeta

ComponentStatus = Literal["AVAILABLE", "DEGRADED", "UNAVAILABLE"]
SystemStatus = Literal["HEALTHY", "DEGRADED", "UNHEALTHY"]
WORKER_HEARTBEAT_MAX_AGE_SECONDS = 15.0


class ComponentHealth(BaseModel):
    status: ComponentStatus


class SystemComponents(BaseModel):
    database: ComponentHealth
    filesystem: ComponentHealth
    worker: ComponentHealth
    ollama: ComponentHealth
    ocr: ComponentHealth


class SystemHealthData(BaseModel):
    status: SystemStatus
    components: SystemComponents


class SystemHealthResponse(BaseModel):
    data: SystemHealthData
    meta: ResponseMeta


class WorkerHeartbeatReader(Protocol):
    def read(self) -> PersistedWorkerHeartbeat | None: ...


class OllamaHealthProvider(Protocol):
    async def health_check(self) -> ProviderHealth: ...


class OCRHealthProvider(Protocol):
    def health_check(self) -> OCRHealth: ...


async def inspect_system_health(
    *,
    application_state: object,
    directories: LocalDataDirectories,
    session_factory: sessionmaker[Session],
    request_id: str,
    clock: Callable[[], float] = time.time,
) -> SystemHealthResponse:
    components = SystemComponents(
        database=_database_health(session_factory),
        filesystem=_filesystem_health(directories),
        worker=_worker_health(application_state, clock),
        ollama=await _ollama_health(application_state),
        ocr=_ocr_health(application_state, directories),
    )
    return SystemHealthResponse(
        data=SystemHealthData(
            status=_overall_status(components),
            components=components,
        ),
        meta=ResponseMeta(request_id=request_id),
    )


def _database_health(session_factory: sessionmaker[Session]) -> ComponentHealth:
    try:
        with session_factory() as session:
            if session.scalar(text("SELECT 1")) != 1:
                return ComponentHealth(status="UNAVAILABLE")
    except Exception:
        return ComponentHealth(status="UNAVAILABLE")
    return ComponentHealth(status="AVAILABLE")


def _filesystem_health(directories: LocalDataDirectories) -> ComponentHealth:
    try:
        available = all(
            path.is_dir() and os.access(path, os.R_OK | os.W_OK) for _, path in directories.items()
        )
    except OSError:
        available = False
    return ComponentHealth(status="AVAILABLE" if available else "UNAVAILABLE")


def _worker_health(
    application_state: object,
    clock: Callable[[], float],
) -> ComponentHealth:
    reader = cast(
        WorkerHeartbeatReader | None,
        getattr(application_state, "worker_heartbeat_store", None),
    )
    if reader is None:
        queue_owner = getattr(application_state, "translation_queue_owner", None)
        huey = getattr(queue_owner, "huey", None)
        if huey is None:
            return ComponentHealth(status="UNAVAILABLE")
        reader = WorkerHeartbeatStore(huey)
    try:
        heartbeat = reader.read()
        age_seconds = clock() - heartbeat.recorded_at if heartbeat is not None else -1.0
    except Exception:
        return ComponentHealth(status="UNAVAILABLE")
    available = (
        heartbeat is not None
        and heartbeat.status is WorkerStatus.RUNNING
        and 0.0 <= age_seconds <= WORKER_HEARTBEAT_MAX_AGE_SECONDS
    )
    return ComponentHealth(status="AVAILABLE" if available else "UNAVAILABLE")


async def _ollama_health(application_state: object) -> ComponentHealth:
    provider = cast(
        OllamaHealthProvider,
        getattr(application_state, "ollama_provider", None) or OllamaTranslationProvider(),
    )
    try:
        health = await provider.health_check()
    except Exception:
        return ComponentHealth(status="UNAVAILABLE")
    return ComponentHealth(status=_provider_status(health.status))


def _ocr_health(
    application_state: object,
    directories: LocalDataDirectories,
) -> ComponentHealth:
    provider = cast(
        OCRHealthProvider | None,
        getattr(application_state, "ocr_health_provider", None),
    )
    if provider is not None:
        try:
            return ComponentHealth(status=_provider_status(provider.health_check().status))
        except Exception:
            return ComponentHealth(status="UNAVAILABLE")

    try:
        local_provider = PaddleOCRProviderAdapter(model_cache_dir=directories.cache / "paddleocr")
        runtime_available = importlib.util.find_spec("paddleocr") is not None
        models_available = (
            local_provider.detection_model_path.is_dir()
            and local_provider.recognition_model_path.is_dir()
        )
    except (ImportError, OSError, ValueError):
        return ComponentHealth(status="UNAVAILABLE")
    return ComponentHealth(
        status="AVAILABLE" if runtime_available and models_available else "UNAVAILABLE"
    )


def _provider_status(status: object) -> ComponentStatus:
    value = getattr(status, "value", status)
    if value == ProviderHealthStatus.AVAILABLE.value:
        return "AVAILABLE"
    if value == ProviderHealthStatus.DEGRADED.value:
        return "DEGRADED"
    return "UNAVAILABLE"


def _overall_status(components: SystemComponents) -> SystemStatus:
    statuses = [component.status for component in components.__dict__.values()]
    if components.database.status == "UNAVAILABLE" or components.filesystem.status == "UNAVAILABLE":
        return "UNHEALTHY"
    if all(status == "AVAILABLE" for status in statuses):
        return "HEALTHY"
    return "DEGRADED"
