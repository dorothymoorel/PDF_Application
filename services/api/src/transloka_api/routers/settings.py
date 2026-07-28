from typing import Any, Never, cast

from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session, sessionmaker
from transloka_api.exception_handlers import TransLokaError
from transloka_api.schemas import ErrorResponse
from transloka_core.database import transaction_scope
from transloka_core.database.models.application import SettingCategory
from transloka_core.repositories.settings import (
    CorruptSettingValueError,
    InvalidSettingValueError,
    SettingNotFoundError,
    SettingRecord,
    SettingsRepository,
    SettingsRepositoryError,
    UnknownSettingKeyError,
    validate_setting_value,
)

_ERROR_RESPONSES: dict[int | str, dict[str, Any]] = {
    400: {"description": "The setting key is not allowed.", "model": ErrorResponse},
    404: {"description": "The setting was not found.", "model": ErrorResponse},
    422: {"description": "The setting value is invalid.", "model": ErrorResponse},
    500: {"description": "Stored setting data is invalid.", "model": ErrorResponse},
}

router = APIRouter(prefix="/api/v1/settings", tags=["Settings"])


class UpdateSettingRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    value: object


class ValidateSettingsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    settings: dict[str, object] = Field(min_length=1)


class SettingResponse(BaseModel):
    key: str
    value: object
    category: SettingCategory
    updated_at: str


class SettingDataResponse(BaseModel):
    data: SettingResponse


class SettingsListResponse(BaseModel):
    data: list[SettingResponse]


class SettingsValidationData(BaseModel):
    valid: bool


class SettingsValidationResponse(BaseModel):
    data: SettingsValidationData


@router.get(
    "",
    operation_id="list_settings",
    response_model=SettingsListResponse,
    responses=_ERROR_RESPONSES,
)
def list_settings(
    request: Request,
    category: SettingCategory | None = None,
) -> SettingsListResponse:
    try:
        with _session_factory(request)() as session:
            records = SettingsRepository(session).list(category)
    except SettingsRepositoryError as exc:
        _raise_api_error(exc)
    return SettingsListResponse(data=[_response(record) for record in records])


@router.get(
    "/{key}",
    operation_id="get_setting",
    response_model=SettingDataResponse,
    responses=_ERROR_RESPONSES,
)
def get_setting(key: str, request: Request) -> SettingDataResponse:
    try:
        with _session_factory(request)() as session:
            record = SettingsRepository(session).get(key)
    except SettingsRepositoryError as exc:
        _raise_api_error(exc)
    return SettingDataResponse(data=_response(record))


@router.patch(
    "/{key}",
    operation_id="update_setting",
    response_model=SettingDataResponse,
    responses=_ERROR_RESPONSES,
)
def update_setting(
    key: str,
    payload: UpdateSettingRequest,
    request: Request,
) -> SettingDataResponse:
    try:
        with transaction_scope(_session_factory(request)) as session:
            record = SettingsRepository(session).update(key, payload.value)
    except SettingsRepositoryError as exc:
        _raise_api_error(exc)
    return SettingDataResponse(data=_response(record))


@router.post(
    "/validate",
    operation_id="validate_settings",
    response_model=SettingsValidationResponse,
    responses=_ERROR_RESPONSES,
)
def validate_settings(payload: ValidateSettingsRequest) -> SettingsValidationResponse:
    try:
        for key, value in payload.settings.items():
            validate_setting_value(key, value)
    except SettingsRepositoryError as exc:
        _raise_api_error(exc)
    return SettingsValidationResponse(data=SettingsValidationData(valid=True))


def _session_factory(request: Request) -> sessionmaker[Session]:
    try:
        factory = request.app.state.session_factory
    except AttributeError as exc:
        raise RuntimeError("The settings database is not configured.") from exc
    if not callable(factory):
        raise RuntimeError("The settings database is not configured.")
    return cast(sessionmaker[Session], factory)


def _response(record: SettingRecord) -> SettingResponse:
    return SettingResponse(
        key=record.key,
        value=record.value,
        category=record.category,
        updated_at=record.updated_at,
    )


def _raise_api_error(exc: SettingsRepositoryError) -> Never:
    if isinstance(exc, UnknownSettingKeyError):
        code, message, status_code = (
            "SETTING_KEY_NOT_ALLOWED",
            "The setting key is not allowed.",
            400,
        )
    elif isinstance(exc, SettingNotFoundError):
        code, message, status_code = (
            "RESOURCE_NOT_FOUND",
            "The requested resource was not found.",
            404,
        )
    elif isinstance(exc, InvalidSettingValueError):
        code, message, status_code = (
            "SETTING_VALUE_INVALID",
            "The setting value is invalid.",
            422,
        )
    elif isinstance(exc, CorruptSettingValueError):
        code, message, status_code = (
            "SETTINGS_DATA_CORRUPT",
            "The stored setting is invalid.",
            500,
        )
    else:
        code, message, status_code = (
            "SETTINGS_OPERATION_FAILED",
            "The settings operation could not be completed.",
            409,
        )
    raise TransLokaError(code=code, message=message, status_code=status_code) from exc
