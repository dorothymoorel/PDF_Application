from datetime import UTC, datetime
from typing import Annotated, Any, Never, cast
from uuid import uuid4

from fastapi import APIRouter, Query, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select, update
from sqlalchemy.orm import Session, sessionmaker
from transloka_api.exception_handlers import TransLokaError
from transloka_api.middleware import get_request_id
from transloka_api.schemas import ErrorResponse
from transloka_api.schemas.projects import ResponseMeta
from transloka_core.database import transaction_scope
from transloka_core.database.models.models import (
    LocalModelRecord,
    ModelLicenseStatus,
    ModelRole,
)
from transloka_translation.providers import LocalModel as DetectedProviderModel
from transloka_translation.providers import (
    ProviderHealthStatus,
    TranslationProviderError,
)
from transloka_translation.providers.ollama import (
    OllamaTranslationProvider,
    RemoteOllamaEndpointError,
)

_ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    403: {
        "description": "A remote Ollama endpoint was blocked.",
        "model": ErrorResponse,
    },
    404: {"description": "The local model was not found.", "model": ErrorResponse},
    409: {
        "description": "The local model is unavailable or cannot be selected.",
        "model": ErrorResponse,
    },
    422: {"description": "The request contains invalid values.", "model": ErrorResponse},
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
    id: str
    ollama_model_name: str
    model_family: str | None
    parameter_class: str | None
    quantization: str | None
    disk_size_bytes: int | None
    license_status: ModelLicenseStatus
    is_installed: bool
    is_selected_translation: bool
    is_selected_validation: bool


class ModelWarning(BaseModel):
    code: str
    message: str
    model_id: str


class ModelResponseMeta(ResponseMeta):
    warnings: list[ModelWarning] = Field(default_factory=list)


class DetectedLocalModelsResponse(BaseModel):
    data: list[DetectedLocalModel]
    meta: ModelResponseMeta


class DetectedLocalModelResponse(BaseModel):
    data: DetectedLocalModel
    meta: ModelResponseMeta


class SelectModelRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: ModelRole


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
async def list_detected_local_models(
    request: Request,
    installed: Annotated[bool | None, Query()] = None,
    selected_for_translation: Annotated[bool | None, Query()] = None,
    selected_for_validation: Annotated[bool | None, Query()] = None,
) -> DetectedLocalModelsResponse:
    return _list_persisted_models(
        request,
        installed=installed,
        selected_for_translation=selected_for_translation,
        selected_for_validation=selected_for_validation,
    )


@router.post(
    "/refresh",
    operation_id="refresh_local_models",
    response_model=DetectedLocalModelsResponse,
    responses=_ERROR_RESPONSES,
)
async def refresh_local_models(request: Request) -> DetectedLocalModelsResponse:
    try:
        detected = await _provider(request).list_models()
    except TranslationProviderError as exc:
        _raise_ollama_unavailable(exc)

    with transaction_scope(_session_factory(request)) as session:
        _persist_refresh(session, detected, _utc_now())
    return _list_persisted_models(request)


@router.post(
    "/{model_id}/select",
    operation_id="select_local_model",
    response_model=DetectedLocalModelResponse,
    responses=_ERROR_RESPONSES,
)
async def select_local_model(
    model_id: str,
    payload: SelectModelRequest,
    request: Request,
) -> DetectedLocalModelResponse:
    factory = _session_factory(request)
    with factory() as session:
        candidate = session.get(LocalModelRecord, model_id)
        if candidate is None:
            _raise_model_not_found()
        if not candidate.is_installed:
            _raise_model_not_installed()

    health = await _provider(request).health_check()
    if health.status is not ProviderHealthStatus.AVAILABLE:
        _raise_ollama_health_unavailable()

    selected_field = (
        "is_selected_translation"
        if payload.role is ModelRole.TRANSLATION
        else "is_selected_validation"
    )
    with transaction_scope(factory) as session:
        candidate = session.get(LocalModelRecord, model_id)
        if candidate is None:
            _raise_model_not_found()
        if not candidate.is_installed:
            _raise_model_not_installed()
        session.execute(
            update(LocalModelRecord)
            .where(getattr(LocalModelRecord, selected_field) == 1)
            .values({selected_field: 0})
        )
        setattr(candidate, selected_field, 1)

    with factory() as session:
        selected_row = session.get(LocalModelRecord, model_id)
        if selected_row is None:
            _raise_model_not_found()
        return DetectedLocalModelResponse(
            data=_model_response(selected_row),
            meta=ModelResponseMeta(
                request_id=_request_id(),
                warnings=_license_warnings([selected_row]),
            ),
        )


def _list_persisted_models(
    request: Request,
    *,
    installed: bool | None = None,
    selected_for_translation: bool | None = None,
    selected_for_validation: bool | None = None,
) -> DetectedLocalModelsResponse:
    statement = select(LocalModelRecord)
    if installed is not None:
        statement = statement.where(LocalModelRecord.is_installed == int(installed))
    if selected_for_translation is not None:
        statement = statement.where(
            LocalModelRecord.is_selected_translation == int(selected_for_translation)
        )
    if selected_for_validation is not None:
        statement = statement.where(
            LocalModelRecord.is_selected_validation == int(selected_for_validation)
        )
    with _session_factory(request)() as session:
        models = list(session.scalars(statement.order_by(LocalModelRecord.ollama_model_name)))
    return DetectedLocalModelsResponse(
        data=[_model_response(model) for model in models],
        meta=ModelResponseMeta(
            request_id=_request_id(),
            warnings=_license_warnings(models),
        ),
    )


def _persist_refresh(
    session: Session,
    detected: list[DetectedProviderModel],
    detected_at: str,
) -> None:
    detected_by_name = {model.name: model for model in detected}
    persisted = list(session.scalars(select(LocalModelRecord)))
    persisted_by_name = {model.ollama_model_name: model for model in persisted}

    for name, detected_model in detected_by_name.items():
        record = persisted_by_name.get(name)
        if record is None:
            session.add(
                LocalModelRecord(
                    id=f"mdl_{uuid4()}",
                    ollama_model_name=name,
                    model_family=None,
                    parameter_class=None,
                    quantization=None,
                    disk_size_bytes=detected_model.size_bytes,
                    license_name=None,
                    license_status=ModelLicenseStatus.UNKNOWN.value,
                    is_installed=1,
                    is_selected_translation=0,
                    is_selected_validation=0,
                    metadata_json=None,
                    last_detected_at=detected_at,
                )
            )
            continue
        record.disk_size_bytes = detected_model.size_bytes
        record.is_installed = 1
        record.last_detected_at = detected_at

    for record in persisted:
        if record.ollama_model_name not in detected_by_name:
            record.is_installed = 0
            record.is_selected_translation = 0
            record.is_selected_validation = 0


def _model_response(record: LocalModelRecord) -> DetectedLocalModel:
    return DetectedLocalModel(
        id=record.id,
        ollama_model_name=record.ollama_model_name,
        model_family=record.model_family,
        parameter_class=record.parameter_class,
        quantization=record.quantization,
        disk_size_bytes=record.disk_size_bytes,
        license_status=ModelLicenseStatus(record.license_status),
        is_installed=bool(record.is_installed),
        is_selected_translation=bool(record.is_selected_translation),
        is_selected_validation=bool(record.is_selected_validation),
    )


def _license_warnings(records: list[LocalModelRecord]) -> list[ModelWarning]:
    return [
        ModelWarning(
            code="MODEL_LICENSE_UNKNOWN",
            message="Review the model license before permanent use.",
            model_id=record.id,
        )
        for record in records
        if record.license_status == ModelLicenseStatus.UNKNOWN.value
    ]


def _session_factory(request: Request) -> sessionmaker[Session]:
    try:
        factory = request.app.state.session_factory
    except AttributeError as exc:
        raise RuntimeError("The local model database is not configured.") from exc
    if not callable(factory):
        raise RuntimeError("The local model database is not configured.")
    return cast(sessionmaker[Session], factory)


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


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


def _raise_ollama_health_unavailable() -> Never:
    raise TransLokaError(
        code="OLLAMA_UNAVAILABLE",
        message="The local Ollama service is unavailable.",
        status_code=503,
    )


def _raise_model_not_found() -> Never:
    raise TransLokaError(
        code="MODEL_NOT_FOUND",
        message="The requested local model was not found.",
        status_code=404,
    )


def _raise_model_not_installed() -> Never:
    raise TransLokaError(
        code="OLLAMA_MODEL_NOT_INSTALLED",
        message="The selected local model is not installed.",
        status_code=409,
    )
