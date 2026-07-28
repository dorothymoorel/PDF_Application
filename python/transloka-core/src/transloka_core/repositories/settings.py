import json
import math
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from types import MappingProxyType
from typing import Literal

from sqlalchemy import select
from sqlalchemy.orm import Session
from transloka_core.database.models.application import ApplicationSetting, SettingCategory

type JsonValue = None | bool | int | float | str | list["JsonValue"] | dict[str, "JsonValue"]


class SettingsRepositoryError(ValueError):
    pass


class UnknownSettingKeyError(SettingsRepositoryError):
    pass


class InvalidSettingCategoryError(SettingsRepositoryError):
    pass


class InvalidSettingValueError(SettingsRepositoryError):
    pass


class SettingAlreadyExistsError(SettingsRepositoryError):
    pass


class SettingNotFoundError(SettingsRepositoryError):
    pass


class CorruptSettingValueError(SettingsRepositoryError):
    pass


@dataclass(frozen=True)
class SettingDefinition:
    category: SettingCategory
    json_type: Literal["integer"]
    default: int
    minimum: int
    maximum: int
    user_modifiable: bool


@dataclass(frozen=True)
class SettingRecord:
    key: str
    value: JsonValue
    category: SettingCategory
    updated_at: str


SETTING_DEFINITIONS = MappingProxyType(
    {
        "translation_batch_size": SettingDefinition(
            category=SettingCategory.TRANSLATION,
            json_type="integer",
            default=5,
            minimum=1,
            maximum=10,
            user_modifiable=True,
        ),
        "ocr_concurrency": SettingDefinition(
            category=SettingCategory.OCR,
            json_type="integer",
            default=1,
            minimum=1,
            maximum=8,
            user_modifiable=True,
        ),
    }
)


class SettingsRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def create(self, key: str, value: object) -> SettingRecord:
        definition, value_json = validate_setting_value(key, value)
        if self._session.get(ApplicationSetting, key) is not None:
            raise SettingAlreadyExistsError("The setting already exists.")

        row = ApplicationSetting(
            key=key,
            value_json=value_json,
            category=definition.category.value,
            updated_at=_utc_now(),
        )
        self._session.add(row)
        self._session.flush()
        return _record(row)

    def get(self, key: str) -> SettingRecord:
        _definition(key)
        row = self._session.get(ApplicationSetting, key)
        if row is None:
            raise SettingNotFoundError("The setting was not found.")
        return _record(row)

    def list(self, category: SettingCategory | None = None) -> list[SettingRecord]:
        if category is not None and not isinstance(category, SettingCategory):
            raise InvalidSettingCategoryError("The setting category is invalid.")

        statement = select(ApplicationSetting).order_by(ApplicationSetting.key)
        if category is not None:
            statement = statement.where(ApplicationSetting.category == category.value)
        return [_record(row) for row in self._session.scalars(statement)]

    def update(self, key: str, value: object) -> SettingRecord:
        definition, value_json = validate_setting_value(key, value)
        row = self._session.get(ApplicationSetting, key)
        if row is None:
            raise SettingNotFoundError("The setting was not found.")

        row.value_json = value_json
        row.category = definition.category.value
        row.updated_at = _utc_now()
        self._session.flush()
        return _record(row)


def validate_setting_value(key: str, value: object) -> tuple[SettingDefinition, str]:
    definition = _definition(key)
    _validate_json_value(value, set())
    if type(value) is not int or not definition.minimum <= value <= definition.maximum:
        raise InvalidSettingValueError("The setting value is invalid.")

    try:
        serialized = json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
    except (TypeError, ValueError, RecursionError) as exc:
        raise InvalidSettingValueError("The setting value is invalid.") from exc
    return definition, serialized


def _definition(key: str) -> SettingDefinition:
    if not isinstance(key, str):
        raise UnknownSettingKeyError("The setting key is not allowed.")
    try:
        return SETTING_DEFINITIONS[key]
    except KeyError:
        raise UnknownSettingKeyError("The setting key is not allowed.") from None


def _validate_json_value(value: object, ancestors: set[int]) -> None:
    if value is None or isinstance(value, (bool, int, str)):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise InvalidSettingValueError("The setting value is invalid.")
        return
    if isinstance(value, list):
        _validate_json_collection(value, value, ancestors)
        return
    if isinstance(value, dict):
        if not all(isinstance(key, str) for key in value):
            raise InvalidSettingValueError("The setting value is invalid.")
        _validate_json_collection(value, value.values(), ancestors)
        return
    raise InvalidSettingValueError("The setting value is invalid.")


def _validate_json_collection(
    collection: list[object] | dict[object, object],
    values: Iterable[object],
    ancestors: set[int],
) -> None:
    identity = id(collection)
    if identity in ancestors:
        raise InvalidSettingValueError("The setting value is invalid.")
    ancestors.add(identity)
    try:
        for item in values:
            _validate_json_value(item, ancestors)
    finally:
        ancestors.remove(identity)


def _record(row: ApplicationSetting) -> SettingRecord:
    definition = _definition(row.key)
    if row.category != definition.category.value:
        raise CorruptSettingValueError("The stored setting is invalid.")
    try:
        value = json.loads(
            row.value_json,
            parse_constant=lambda _constant: _raise_corrupt_setting(),
        )
        _validate_json_value(value, set())
        validate_setting_value(row.key, value)
    except (json.JSONDecodeError, InvalidSettingValueError):
        raise CorruptSettingValueError("The stored setting is invalid.") from None
    return SettingRecord(
        key=row.key,
        value=value,
        category=definition.category,
        updated_at=row.updated_at,
    )


def _raise_corrupt_setting() -> None:
    raise CorruptSettingValueError("The stored setting is invalid.")


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")
