"""Maintenance endpoints backed by the local maintenance service."""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime
from typing import Annotated, Any, Literal, cast
from uuid import uuid4

from fastapi import APIRouter, Body, Request, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session, sessionmaker
from transloka_api.exception_handlers import TransLokaError
from transloka_api.middleware.request_id import get_request_id
from transloka_api.schemas import ErrorResponse
from transloka_api.schemas.projects import ResponseMeta
from transloka_core.database import transaction_scope
from transloka_core.database.models.jobs import ApplicationJob, JobStatus, JobType
from transloka_core.maintenance import (
    MaintenanceBusyError,
    MaintenanceError,
    MaintenanceOperation,
    MaintenanceReport,
    MaintenanceService,
)

_ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    409: {"description": "Maintenance conflicts with an active job.", "model": ErrorResponse},
    422: {"description": "The maintenance request is invalid.", "model": ErrorResponse},
    500: {"description": "Maintenance could not be completed safely.", "model": ErrorResponse},
}
_QUEUE_NAME = "transloka-api"

router = APIRouter(prefix="/api/v1/maintenance", tags=["Maintenance"])


class MaintenanceRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    older_than_days: int = Field(default=7, ge=1, le=3650)
    dry_run: bool = True


class MaintenanceData(BaseModel):
    job_id: str
    operation: MaintenanceOperation
    status: Literal["COMPLETED"] = "COMPLETED"
    healthy: bool
    dry_run: bool
    checked_count: int = Field(ge=0)
    issue_count: int = Field(ge=0)
    issues: list[str]
    orphans: list[str]
    candidates: list[str]
    deleted: list[str]
    protected: list[str]


class MaintenanceResponse(BaseModel):
    data: MaintenanceData
    meta: ResponseMeta


@router.post(
    "/database-integrity-check",
    operation_id="run_database_integrity_check",
    response_model=MaintenanceResponse,
    responses=_ERROR_RESPONSES,
    status_code=status.HTTP_202_ACCEPTED,
)
def database_integrity_check(request: Request) -> MaintenanceResponse:
    return _run(request, "database_integrity_check")


@router.post(
    "/file-integrity-check",
    operation_id="run_file_integrity_check",
    response_model=MaintenanceResponse,
    responses=_ERROR_RESPONSES,
    status_code=status.HTTP_202_ACCEPTED,
)
def file_integrity_check(request: Request) -> MaintenanceResponse:
    return _run(request, "file_integrity_check")


@router.post(
    "/orphan-file-scan",
    operation_id="run_orphan_file_scan",
    response_model=MaintenanceResponse,
    responses=_ERROR_RESPONSES,
    status_code=status.HTTP_202_ACCEPTED,
)
def orphan_file_scan(request: Request) -> MaintenanceResponse:
    return _run(request, "orphan_file_scan")


@router.post(
    "/temp-cleanup",
    operation_id="run_temp_cleanup",
    response_model=MaintenanceResponse,
    responses=_ERROR_RESPONSES,
    status_code=status.HTTP_202_ACCEPTED,
)
def temp_cleanup(
    request: Request,
    payload: Annotated[MaintenanceRequest | None, Body()] = None,
) -> MaintenanceResponse:
    options = payload or MaintenanceRequest()
    return _run(request, "temp_cleanup", options)


@router.post(
    "/cache-cleanup",
    operation_id="run_cache_cleanup",
    response_model=MaintenanceResponse,
    responses=_ERROR_RESPONSES,
    status_code=status.HTTP_202_ACCEPTED,
)
def cache_cleanup(
    request: Request,
    payload: Annotated[MaintenanceRequest | None, Body()] = None,
) -> MaintenanceResponse:
    options = payload or MaintenanceRequest()
    return _run(request, "cache_cleanup", options)


@router.post(
    "/database-vacuum",
    operation_id="run_database_vacuum",
    response_model=MaintenanceResponse,
    responses=_ERROR_RESPONSES,
    status_code=status.HTTP_202_ACCEPTED,
)
def database_vacuum(
    request: Request,
    payload: Annotated[MaintenanceRequest | None, Body()] = None,
) -> MaintenanceResponse:
    options = payload or MaintenanceRequest()
    return _run(request, "vacuum", options)


def _run(
    request: Request,
    method_name: str,
    options: MaintenanceRequest | None = None,
) -> MaintenanceResponse:
    factory = _session_factory(request)
    settings = request.app.state.settings
    job_id = f"job_{uuid4()}"
    service = MaintenanceService(
        settings.data_directories,
        factory,
        current_job_id=job_id,
    )
    started_at = _utc_now()
    payload_json = json.dumps(
        {
            "operation": method_name,
            "older_than_days": options.older_than_days if options else None,
            "dry_run": options.dry_run if options else True,
        },
        separators=(",", ":"),
        sort_keys=True,
    )
    _create_job(factory, job_id, payload_json, started_at)
    try:
        report = _invoke(service, method_name, options)
    except MaintenanceBusyError as exc:
        _fail_job(factory, job_id, "MAINTENANCE_BUSY", str(exc))
        raise TransLokaError(
            code="MAINTENANCE_ACTIVE_JOB",
            message="Maintenance is blocked by an active application job.",
            status_code=409,
        ) from exc
    except MaintenanceError as exc:
        _fail_job(factory, job_id, "MAINTENANCE_FAILED", str(exc))
        raise TransLokaError(
            code="MAINTENANCE_FAILED",
            message="Maintenance could not be completed safely.",
            status_code=500,
        ) from exc
    _complete_job(factory, job_id, report)
    return MaintenanceResponse(
        data=_maintenance_data(job_id, report),
        meta=ResponseMeta(request_id=_request_id()),
    )


def _invoke(
    service: MaintenanceService,
    method_name: str,
    options: MaintenanceRequest | None,
) -> MaintenanceReport:
    method = cast(Callable[..., MaintenanceReport], getattr(service, method_name))
    if method_name in {"temp_cleanup", "cache_cleanup", "vacuum"}:
        effective = options or MaintenanceRequest()
        if method_name == "vacuum":
            return method(dry_run=effective.dry_run)
        return method(
            older_than_days=effective.older_than_days,
            dry_run=effective.dry_run,
        )
    return method()


def _create_job(
    factory: sessionmaker[Session],
    job_id: str,
    payload_json: str,
    started_at: str,
) -> None:
    with transaction_scope(factory) as session:
        session.add(
            ApplicationJob(
                id=job_id,
                project_id=None,
                document_id=None,
                parent_job_id=None,
                job_type=JobType.MAINTENANCE.value,
                queue_name=_QUEUE_NAME,
                status=JobStatus.RUNNING.value,
                progress=0.0,
                current_stage="STARTING",
                idempotency_key=f"maintenance:{job_id}",
                payload_json=payload_json,
                result_json=None,
                retry_count=0,
                max_retries=0,
                error_code=None,
                error_message=None,
                created_at=started_at,
                queued_at=started_at,
                started_at=started_at,
                completed_at=None,
                cancelled_at=None,
                heartbeat_at=started_at,
            )
        )


def _complete_job(
    factory: sessionmaker[Session],
    job_id: str,
    report: MaintenanceReport,
) -> None:
    completed_at = _utc_now()
    result_json = json.dumps(_report_dict(report), separators=(",", ":"), sort_keys=True)
    with transaction_scope(factory) as session:
        row = session.get(ApplicationJob, job_id)
        if row is None:
            raise RuntimeError("The maintenance job was not persisted.")
        row.status = JobStatus.COMPLETED.value
        row.progress = 1.0
        row.current_stage = report.operation.value
        row.result_json = result_json
        row.completed_at = completed_at
        row.heartbeat_at = completed_at


def _fail_job(
    factory: sessionmaker[Session],
    job_id: str,
    error_code: str,
    error_message: str,
) -> None:
    completed_at = _utc_now()
    with transaction_scope(factory) as session:
        row = session.get(ApplicationJob, job_id)
        if row is None:
            return
        row.status = JobStatus.FAILED.value
        row.error_code = error_code
        row.error_message = error_message
        row.completed_at = completed_at
        row.heartbeat_at = completed_at


def _maintenance_data(job_id: str, report: MaintenanceReport) -> MaintenanceData:
    return MaintenanceData(
        job_id=job_id,
        operation=report.operation,
        status="COMPLETED",
        healthy=report.healthy,
        dry_run=report.dry_run,
        checked_count=report.checked_count,
        issue_count=report.issue_count,
        issues=list(report.issues),
        orphans=list(report.orphans),
        candidates=list(report.candidates),
        deleted=list(report.deleted),
        protected=list(report.protected),
    )


def _report_dict(report: MaintenanceReport) -> dict[str, object]:
    return {
        "operation": report.operation,
        "healthy": report.healthy,
        "dry_run": report.dry_run,
        "checked_count": report.checked_count,
        "issue_count": report.issue_count,
        "issues": list(report.issues),
        "orphans": list(report.orphans),
        "candidates": list(report.candidates),
        "deleted": list(report.deleted),
        "protected": list(report.protected),
    }


def _session_factory(request: Request) -> sessionmaker[Session]:
    factory = getattr(request.app.state, "session_factory", None)
    if not callable(factory):
        raise RuntimeError("The maintenance database is not configured.")
    return cast(sessionmaker[Session], factory)


def _request_id() -> str:
    request_id = get_request_id()
    if request_id is None:
        raise RuntimeError("The request identifier is unavailable.")
    return request_id


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


__all__ = [
    "MaintenanceData",
    "MaintenanceRequest",
    "MaintenanceResponse",
    "router",
]
