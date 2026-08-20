import json
import math
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from types import MappingProxyType
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session
from transloka_core.database.models.warnings import (
    Warning,
    WarningResolutionType,
    WarningSeverity,
    WarningStatus,
    WarningType,
)


class WarningRepositoryError(ValueError):
    pass


class InvalidWarningError(WarningRepositoryError):
    pass


class WarningNotFoundError(WarningRepositoryError):
    pass


class WarningAlreadyResolvedError(WarningRepositoryError):
    pass


class CriticalWarningPolicyError(WarningRepositoryError):
    pass


NON_OVERRIDEABLE_CRITICAL_TYPES = frozenset(
    {
        WarningType.MISSING_TRANSLATED_SEGMENT.value,
        WarningType.PLACEHOLDER_RESTORATION_FAILED.value,
        WarningType.OUTPUT_PDF_CORRUPTED.value,
        WarningType.ORIGINAL_FILE_CHECKSUM_MISMATCH.value,
        WarningType.PATH_TRAVERSAL_DETECTED.value,
        WarningType.TABLE_STRUCTURE_CORRUPTED_CRITICAL.value,
        WarningType.CRITICAL_TEXT_CLIPPING.value,
        WarningType.CRITICAL_LAYOUT_COLLISION.value,
    }
)


JsonValue = None | bool | int | float | str | list["JsonValue"] | dict[str, "JsonValue"]


@dataclass(frozen=True)
class WarningRecord:
    id: str
    project_id: str
    document_id: str | None
    page_id: str | None
    block_id: str | None
    segment_id: str | None
    job_id: str | None
    warning_type: WarningType
    severity: WarningSeverity
    message: str
    details: dict[str, JsonValue]
    status: WarningStatus
    resolution_type: WarningResolutionType | None
    resolution_note: str | None
    created_at: str
    resolved_at: str | None


class WarningsRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def create(
        self,
        *,
        warning_id: str,
        project_id: str,
        warning_type: WarningType,
        severity: WarningSeverity,
        message: str,
        details: Mapping[str, JsonValue] | None,
        created_at: str,
        document_id: str | None = None,
        page_id: str | None = None,
        block_id: str | None = None,
        segment_id: str | None = None,
        job_id: str | None = None,
    ) -> WarningRecord:
        _validate_warning_id(warning_id)
        _validate_enum(warning_type, WarningType, "The warning type is invalid.")
        _validate_enum(severity, WarningSeverity, "The warning severity is invalid.")
        _validate_text(message, "The warning message")
        _validate_text(created_at, "The warning timestamp")
        details_json = _serialize_details(details)
        if self._session.get(Warning, warning_id) is not None:
            raise InvalidWarningError("The warning already exists.")

        row = Warning(
            id=warning_id,
            project_id=project_id,
            document_id=document_id,
            page_id=page_id,
            block_id=block_id,
            segment_id=segment_id,
            job_id=job_id,
            warning_type=warning_type.value,
            severity=severity.value,
            message=message,
            details_json=details_json,
            status=WarningStatus.OPEN.value,
            resolution_type=None,
            resolution_note=None,
            created_at=created_at,
            resolved_at=None,
        )
        self._session.add(row)
        self._session.flush()
        return _record(row)

    def get(self, warning_id: str) -> WarningRecord:
        row = self._session.get(Warning, warning_id)
        if row is None:
            raise WarningNotFoundError("The warning was not found.")
        return _record(row)

    def list(
        self,
        *,
        project_id: str,
        status: WarningStatus | None = None,
        severity: WarningSeverity | None = None,
        warning_type: WarningType | None = None,
        page_id: str | None = None,
        segment_id: str | None = None,
        offset: int = 0,
        limit: int = 50,
    ) -> tuple[list[WarningRecord], bool]:
        if offset < 0 or limit < 1:
            raise InvalidWarningError("The warning pagination is invalid.")
        for value, enum_type, label in (
            (status, WarningStatus, "The warning status is invalid."),
            (severity, WarningSeverity, "The warning severity is invalid."),
            (warning_type, WarningType, "The warning type is invalid."),
        ):
            if value is not None:
                _validate_enum(value, enum_type, label)

        statement = select(Warning).where(Warning.project_id == project_id)
        if status is not None:
            statement = statement.where(Warning.status == status.value)
        if severity is not None:
            statement = statement.where(Warning.severity == severity.value)
        if warning_type is not None:
            statement = statement.where(Warning.warning_type == warning_type.value)
        if page_id is not None:
            statement = statement.where(Warning.page_id == page_id)
        if segment_id is not None:
            statement = statement.where(Warning.segment_id == segment_id)

        rows = list(
            self._session.scalars(
                statement.order_by(Warning.created_at.desc(), Warning.id.desc())
                .offset(offset)
                .limit(limit + 1)
            )
        )
        has_more = len(rows) > limit
        return [_record(row) for row in rows[:limit]], has_more

    def resolve(self, warning_id: str, *, note: str | None) -> WarningRecord:
        return self._transition(
            warning_id,
            status=WarningStatus.RESOLVED,
            resolution_type=WarningResolutionType.USER_FIXED,
            note=note,
            allow_non_overrideable=True,
        )

    def accept(self, warning_id: str, *, note: str | None) -> WarningRecord:
        return self._transition(
            warning_id,
            status=WarningStatus.ACCEPTED,
            resolution_type=WarningResolutionType.USER_ACCEPTED,
            note=note,
            allow_non_overrideable=False,
        )

    def false_positive(self, warning_id: str, *, note: str | None) -> WarningRecord:
        return self._transition(
            warning_id,
            status=WarningStatus.FALSE_POSITIVE,
            resolution_type=WarningResolutionType.FALSE_POSITIVE,
            note=note,
            allow_non_overrideable=False,
        )

    def _transition(
        self,
        warning_id: str,
        *,
        status: WarningStatus,
        resolution_type: WarningResolutionType,
        note: str | None,
        allow_non_overrideable: bool,
    ) -> WarningRecord:
        row = self._session.get(Warning, warning_id)
        if row is None:
            raise WarningNotFoundError("The warning was not found.")
        if row.status != WarningStatus.OPEN.value:
            raise WarningAlreadyResolvedError("The warning has already been resolved.")
        if (
            not allow_non_overrideable
            and row.severity == WarningSeverity.CRITICAL.value
            and row.warning_type in NON_OVERRIDEABLE_CRITICAL_TYPES
        ):
            raise CriticalWarningPolicyError("This critical warning cannot be overridden.")
        _validate_optional_note(note)

        row.status = status.value
        row.resolution_type = resolution_type.value
        row.resolution_note = note
        row.resolved_at = _utc_now()
        self._session.flush()
        return _record(row)


def _record(row: Warning) -> WarningRecord:
    try:
        details = json.loads(
            row.details_json or "{}",
            parse_constant=lambda _value: _raise_corrupt_warning(),
        )
        if not isinstance(details, dict) or not all(isinstance(key, str) for key in details):
            raise ValueError
        _validate_json_value(details, set())
        return WarningRecord(
            id=row.id,
            project_id=row.project_id,
            document_id=row.document_id,
            page_id=row.page_id,
            block_id=row.block_id,
            segment_id=row.segment_id,
            job_id=row.job_id,
            warning_type=WarningType(row.warning_type),
            severity=WarningSeverity(row.severity),
            message=row.message,
            details=details,
            status=WarningStatus(row.status),
            resolution_type=(
                WarningResolutionType(row.resolution_type)
                if row.resolution_type is not None
                else None
            ),
            resolution_note=row.resolution_note,
            created_at=row.created_at,
            resolved_at=row.resolved_at,
        )
    except (ValueError, TypeError, json.JSONDecodeError):
        raise InvalidWarningError("The stored warning is invalid.") from None


def _validate_warning_id(value: str) -> None:
    if not isinstance(value, str) or not value.startswith("wrn_"):
        raise InvalidWarningError("The warning identifier is invalid.")
    try:
        parsed = UUID(value[4:])
    except (ValueError, AttributeError):
        raise InvalidWarningError("The warning identifier is invalid.") from None
    if value != f"wrn_{parsed}":
        raise InvalidWarningError("The warning identifier is invalid.")


def _validate_enum(
    value: object, enum_type: type[WarningType | WarningSeverity | WarningStatus], message: str
) -> None:
    if not isinstance(value, enum_type):
        raise InvalidWarningError(message)


def _validate_text(value: object, label: str) -> None:
    if not isinstance(value, str) or not value.strip() or not value.isprintable():
        raise InvalidWarningError(f"{label} is invalid.")


def _validate_optional_note(value: str | None) -> None:
    if value is not None and (not value.strip() or not value.isprintable()):
        raise InvalidWarningError("The warning resolution note is invalid.")


def _serialize_details(details: Mapping[str, JsonValue] | None) -> str:
    values: Mapping[str, JsonValue] = details or MappingProxyType({})
    if not all(isinstance(key, str) for key in values):
        raise InvalidWarningError("The warning details are invalid.")
    _validate_json_value(dict(values), set())
    try:
        return json.dumps(
            dict(values),
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
    except (TypeError, ValueError, RecursionError) as exc:
        raise InvalidWarningError("The warning details are invalid.") from exc


def _validate_json_value(value: object, ancestors: set[int]) -> None:
    if value is None or isinstance(value, (bool, int, str)):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise InvalidWarningError("The warning details are invalid.")
        return
    if isinstance(value, list):
        identity = id(value)
        if identity in ancestors:
            raise InvalidWarningError("The warning details are invalid.")
        ancestors.add(identity)
        try:
            for item in value:
                _validate_json_value(item, ancestors)
        finally:
            ancestors.remove(identity)
        return
    if isinstance(value, dict):
        identity = id(value)
        if identity in ancestors or not all(isinstance(key, str) for key in value):
            raise InvalidWarningError("The warning details are invalid.")
        ancestors.add(identity)
        try:
            for item in value.values():
                _validate_json_value(item, ancestors)
        finally:
            ancestors.remove(identity)
        return
    raise InvalidWarningError("The warning details are invalid.")


def _raise_corrupt_warning() -> None:
    raise InvalidWarningError("The stored warning is invalid.")


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")
