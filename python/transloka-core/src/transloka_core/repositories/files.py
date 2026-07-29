import json
import math
from collections.abc import Iterable
from dataclasses import dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session
from transloka_core.database.models.files import FileRole, FileStatus, StoredFile


class StoredFileRepositoryError(ValueError):
    pass


class InvalidStoredFileValueError(StoredFileRepositoryError):
    pass


class StoredFileAlreadyExistsError(StoredFileRepositoryError):
    pass


class StoredFileStorageKeyExistsError(StoredFileRepositoryError):
    pass


class StoredFileNotFoundError(StoredFileRepositoryError):
    pass


class CorruptStoredFileError(StoredFileRepositoryError):
    pass


@dataclass(frozen=True)
class StoredFileRecord:
    id: str
    project_id: str | None
    document_id: str | None
    file_role: FileRole
    storage_key: str
    original_filename: str | None
    safe_filename: str
    mime_type: str
    size_bytes: int
    checksum_sha256: str
    is_immutable: bool
    status: FileStatus
    metadata: dict[str, object] | None
    created_at: str
    deleted_at: str | None


class StoredFilesRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def create(
        self,
        *,
        file_id: str,
        project_id: str | None,
        document_id: str | None,
        file_role: FileRole,
        storage_key: str,
        original_filename: str | None,
        safe_filename: str,
        mime_type: str,
        size_bytes: int,
        checksum_sha256: str,
        is_immutable: bool,
        status: FileStatus,
        metadata: dict[str, object] | None,
        created_at: str,
    ) -> StoredFileRecord:
        _validate_identifier(file_id, "fil_")
        _validate_optional_identifier(project_id, "prj_")
        _validate_optional_identifier(document_id, "doc_")
        _validate_enum(file_role, FileRole)
        _validate_storage_key(storage_key)
        _validate_optional_filename(original_filename)
        _validate_filename(safe_filename)
        _validate_mime_type(mime_type)
        _validate_size(size_bytes)
        _validate_checksum(checksum_sha256)
        if not isinstance(is_immutable, bool):
            raise InvalidStoredFileValueError("The immutable flag is invalid.")
        _validate_enum(status, FileStatus)
        metadata_json = _serialize_metadata(metadata)
        _validate_text(created_at)

        if self._session.get(StoredFile, file_id) is not None:
            raise StoredFileAlreadyExistsError("The stored file already exists.")
        existing_key = self._session.scalar(
            select(StoredFile.id).where(StoredFile.storage_key == storage_key)
        )
        if existing_key is not None:
            raise StoredFileStorageKeyExistsError("The storage key already exists.")

        row = StoredFile(
            id=file_id,
            project_id=project_id,
            document_id=document_id,
            file_role=file_role.value,
            storage_key=storage_key,
            original_filename=original_filename,
            safe_filename=safe_filename,
            mime_type=mime_type,
            size_bytes=size_bytes,
            checksum_sha256=checksum_sha256,
            is_immutable=int(is_immutable),
            status=status.value,
            metadata_json=metadata_json,
            created_at=created_at,
            deleted_at=None,
        )
        self._session.add(row)
        self._session.flush()
        return _record(row)

    def get(self, file_id: str) -> StoredFileRecord:
        _validate_identifier(file_id, "fil_")
        row = self._session.get(StoredFile, file_id)
        if row is None:
            raise StoredFileNotFoundError("The stored file was not found.")
        return _record(row)


def _validate_identifier(value: str, prefix: str) -> None:
    if not isinstance(value, str) or not value.startswith(prefix):
        raise InvalidStoredFileValueError("The stored file identifier is invalid.")
    try:
        parsed = UUID(value[len(prefix) :])
    except (ValueError, AttributeError):
        raise InvalidStoredFileValueError("The stored file identifier is invalid.") from None
    if value != f"{prefix}{parsed}":
        raise InvalidStoredFileValueError("The stored file identifier is invalid.")


def _validate_optional_identifier(value: str | None, prefix: str) -> None:
    if value is not None:
        _validate_identifier(value, prefix)


def _validate_enum(value: object, enum_type: type[FileRole | FileStatus]) -> None:
    if not isinstance(value, enum_type):
        raise InvalidStoredFileValueError("The stored file enum value is invalid.")


def _validate_storage_key(value: str) -> None:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or not value.isprintable()
        or "\\" in value
        or ":" in value
        or value.startswith("/")
        or any(part in {"", ".", ".."} for part in value.split("/"))
    ):
        raise InvalidStoredFileValueError("The storage key must be a relative path.")


def _validate_optional_filename(value: str | None) -> None:
    if value is not None:
        _validate_filename(value)


def _validate_filename(value: str) -> None:
    if (
        not isinstance(value, str)
        or not value
        or value != value.strip()
        or not value.isprintable()
        or value in {".", ".."}
        or "/" in value
        or "\\" in value
    ):
        raise InvalidStoredFileValueError("The filename is invalid.")


def _validate_mime_type(value: str) -> None:
    if (
        not isinstance(value, str)
        or value != value.strip()
        or not value.isprintable()
        or value.count("/") != 1
        or any(
            not part or any(character.isspace() for character in part) for part in value.split("/")
        )
    ):
        raise InvalidStoredFileValueError("The MIME type is invalid.")


def _validate_size(value: int) -> None:
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise InvalidStoredFileValueError("The file size is invalid.")


def _validate_checksum(value: str) -> None:
    if (
        not isinstance(value, str)
        or len(value) != 64
        or any(character not in "0123456789abcdef" for character in value)
    ):
        raise InvalidStoredFileValueError("The SHA-256 checksum is invalid.")


def _validate_text(value: str) -> None:
    if not isinstance(value, str) or not value.strip() or not value.isprintable():
        raise InvalidStoredFileValueError("The stored file text value is invalid.")


def _serialize_metadata(metadata: dict[str, object] | None) -> str | None:
    if metadata is None:
        return None
    if not isinstance(metadata, dict):
        raise InvalidStoredFileValueError("The file metadata is invalid.")
    _validate_json_value(metadata, set())
    try:
        return json.dumps(
            metadata,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
    except (TypeError, ValueError, RecursionError) as exc:
        raise InvalidStoredFileValueError("The file metadata is invalid.") from exc


def _validate_json_value(value: object, ancestors: set[int]) -> None:
    if value is None or isinstance(value, (bool, int, str)):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise InvalidStoredFileValueError("The file metadata is invalid.")
        return
    if isinstance(value, list):
        _validate_json_collection(value, value, ancestors)
        return
    if isinstance(value, dict):
        if not all(isinstance(key, str) for key in value):
            raise InvalidStoredFileValueError("The file metadata is invalid.")
        _validate_json_collection(value, value.values(), ancestors)
        return
    raise InvalidStoredFileValueError("The file metadata is invalid.")


def _validate_json_collection(
    collection: list[object] | dict[object, object],
    values: Iterable[object],
    ancestors: set[int],
) -> None:
    identity = id(collection)
    if identity in ancestors:
        raise InvalidStoredFileValueError("The file metadata is invalid.")
    ancestors.add(identity)
    try:
        for item in values:
            _validate_json_value(item, ancestors)
    finally:
        ancestors.remove(identity)


def _record(row: StoredFile) -> StoredFileRecord:
    try:
        metadata = json.loads(row.metadata_json) if row.metadata_json is not None else None
        if metadata is not None and (
            not isinstance(metadata, dict) or not all(isinstance(key, str) for key in metadata)
        ):
            raise ValueError
        if row.is_immutable not in (0, 1):
            raise ValueError
        return StoredFileRecord(
            id=row.id,
            project_id=row.project_id,
            document_id=row.document_id,
            file_role=FileRole(row.file_role),
            storage_key=row.storage_key,
            original_filename=row.original_filename,
            safe_filename=row.safe_filename,
            mime_type=row.mime_type,
            size_bytes=row.size_bytes,
            checksum_sha256=row.checksum_sha256,
            is_immutable=bool(row.is_immutable),
            status=FileStatus(row.status),
            metadata=metadata,
            created_at=row.created_at,
            deleted_at=row.deleted_at,
        )
    except (ValueError, TypeError, json.JSONDecodeError):
        raise CorruptStoredFileError("The stored file metadata is invalid.") from None
