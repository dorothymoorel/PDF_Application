import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, datetime
from io import BytesIO
from uuid import NAMESPACE_URL, uuid5

from pydantic import ValidationError
from transloka_core.database.models.files import FileRole, FileStatus
from transloka_core.repositories.files import (
    StoredFileAlreadyExistsError,
    StoredFileNotFoundError,
    StoredFileRecord,
    StoredFilesRepository,
    StoredFileStorageKeyExistsError,
)
from transloka_core.storage.local import (
    LocalFileStorage,
    LocalFileStorageError,
    StoredFileExistsError,
)

from transloka_document_ir.models import Document


class IRSnapshotError(RuntimeError):
    pass


class IRSnapshotVersionConflictError(IRSnapshotError):
    pass


class IRSnapshotIntegrityError(IRSnapshotError):
    pass


class IRSnapshotStorageError(IRSnapshotError):
    pass


@dataclass(frozen=True, slots=True)
class IRSnapshotIdentity:
    document_id: str
    ir_version: str
    revision: int


def canonical_document_json(document: Document) -> bytes:
    if not isinstance(document, Document):
        raise TypeError("An IR snapshot requires a Document instance.")
    try:
        payload = document.model_dump(mode="json", round_trip=True)
        serialized = json.dumps(
            payload,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
    except (TypeError, ValueError, RecursionError) as exc:
        raise IRSnapshotIntegrityError("The Document IR cannot be serialized canonically.") from exc
    return serialized.encode("utf-8")


def create_ir_snapshot(
    document: Document,
    *,
    storage: LocalFileStorage,
    repository: StoredFilesRepository,
    created_at: datetime | None = None,
) -> StoredFileRecord:
    payload = canonical_document_json(document)
    checksum = hashlib.sha256(payload).hexdigest()
    created_at_text = _timestamp(created_at)
    identity = IRSnapshotIdentity(
        document_id=document.document_id,
        ir_version=document.ir_version,
        revision=document.revision,
    )
    file_id = _snapshot_file_id(document.project_id, identity)
    safe_filename = _snapshot_filename(identity)
    storage_key = (
        f"projects/{document.project_id}/document_ir/{document.document_id}/{safe_filename}"
    )
    metadata: dict[str, object] = {
        "document_id": identity.document_id,
        "ir_version": identity.ir_version,
        "revision": identity.revision,
    }

    try:
        existing = repository.get(file_id)
    except StoredFileNotFoundError:
        pass
    else:
        if not _matches_snapshot_record(
            existing,
            document=document,
            storage_key=storage_key,
            safe_filename=safe_filename,
            checksum=checksum,
            size_bytes=len(payload),
            metadata=metadata,
        ):
            raise IRSnapshotVersionConflictError(
                "The Document IR revision already belongs to a different snapshot."
            )
        restored = load_ir_snapshot(existing, storage=storage)
        if canonical_document_json(restored) != payload:
            raise IRSnapshotVersionConflictError(
                "The Document IR revision already contains different content."
            )
        return existing

    try:
        temporary = storage.write_temporary(BytesIO(payload))
    except LocalFileStorageError as exc:
        raise IRSnapshotStorageError("The IR snapshot could not be staged.") from exc
    if temporary.checksum_sha256 != checksum or temporary.size_bytes != len(payload):
        temporary.path.unlink(missing_ok=True)
        raise IRSnapshotStorageError("The staged IR snapshot does not match its canonical JSON.")
    try:
        artifact = storage.commit(temporary, storage_key, immutable=True)
    except StoredFileExistsError as exc:
        raise IRSnapshotVersionConflictError(
            "The Document IR revision storage destination already exists."
        ) from exc
    except LocalFileStorageError as exc:
        raise IRSnapshotStorageError("The IR snapshot could not be stored.") from exc

    try:
        return repository.create(
            file_id=file_id,
            project_id=document.project_id,
            document_id=document.document_id,
            file_role=FileRole.IR_SNAPSHOT,
            storage_key=artifact.storage_key,
            original_filename=None,
            safe_filename=safe_filename,
            mime_type="application/json",
            size_bytes=artifact.size_bytes,
            checksum_sha256=artifact.checksum_sha256,
            is_immutable=True,
            status=FileStatus.AVAILABLE,
            metadata=metadata,
            created_at=created_at_text,
        )
    except (StoredFileAlreadyExistsError, StoredFileStorageKeyExistsError) as exc:
        raise IRSnapshotVersionConflictError(
            "The Document IR revision file record already exists."
        ) from exc


def load_ir_snapshot(
    record: StoredFileRecord,
    *,
    storage: LocalFileStorage,
) -> Document:
    identity = _record_identity(record)
    project_id = record.project_id
    if not isinstance(project_id, str):
        raise IRSnapshotIntegrityError("The IR snapshot project identity is invalid.")
    safe_filename = _snapshot_filename(identity)
    expected_storage_key = (
        f"projects/{project_id}/document_ir/{identity.document_id}/{safe_filename}"
    )
    if (
        record.id != _snapshot_file_id(project_id, identity)
        or record.file_role is not FileRole.IR_SNAPSHOT
        or record.storage_key != expected_storage_key
        or record.original_filename is not None
        or record.safe_filename != safe_filename
        or record.mime_type != "application/json"
        or not record.is_immutable
        or record.status is not FileStatus.AVAILABLE
        or record.document_id != identity.document_id
    ):
        raise IRSnapshotIntegrityError("The IR snapshot file record is invalid.")
    try:
        stored_checksum = storage.checksum(record.storage_key)
        with storage.open_read(record.storage_key) as source:
            payload = source.read()
    except LocalFileStorageError as exc:
        raise IRSnapshotIntegrityError("The IR snapshot file is unavailable.") from exc
    if (
        not isinstance(payload, bytes)
        or len(payload) != record.size_bytes
        or stored_checksum != record.checksum_sha256
        or hashlib.sha256(payload).hexdigest() != record.checksum_sha256
    ):
        raise IRSnapshotIntegrityError("The IR snapshot checksum does not match its file record.")
    try:
        document = Document.model_validate_json(payload)
    except (ValidationError, ValueError) as exc:
        raise IRSnapshotIntegrityError("The IR snapshot JSON is invalid.") from exc
    if (
        document.document_id != identity.document_id
        or document.project_id != record.project_id
        or document.ir_version != identity.ir_version
        or document.revision != identity.revision
        or canonical_document_json(document) != payload
    ):
        raise IRSnapshotIntegrityError(
            "The IR snapshot content does not match its identity or canonical form."
        )
    return document


def _record_identity(record: StoredFileRecord) -> IRSnapshotIdentity:
    metadata = record.metadata
    if metadata is None:
        raise IRSnapshotIntegrityError("The IR snapshot identity metadata is missing.")
    document_id = metadata.get("document_id")
    ir_version = metadata.get("ir_version")
    revision = metadata.get("revision")
    if (
        not isinstance(document_id, str)
        or not document_id
        or not isinstance(ir_version, str)
        or not ir_version
        or isinstance(revision, bool)
        or not isinstance(revision, int)
        or revision < 1
    ):
        raise IRSnapshotIntegrityError("The IR snapshot identity metadata is invalid.")
    return IRSnapshotIdentity(
        document_id=document_id,
        ir_version=ir_version,
        revision=revision,
    )


def _matches_snapshot_record(
    record: StoredFileRecord,
    *,
    document: Document,
    storage_key: str,
    safe_filename: str,
    checksum: str,
    size_bytes: int,
    metadata: dict[str, object],
) -> bool:
    return (
        record.project_id == document.project_id
        and record.document_id == document.document_id
        and record.file_role is FileRole.IR_SNAPSHOT
        and record.storage_key == storage_key
        and record.original_filename is None
        and record.safe_filename == safe_filename
        and record.mime_type == "application/json"
        and record.size_bytes == size_bytes
        and record.checksum_sha256 == checksum
        and record.is_immutable
        and record.status is FileStatus.AVAILABLE
        and record.metadata == metadata
    )


def _snapshot_file_id(project_id: str, identity: IRSnapshotIdentity) -> str:
    value = (
        f"transloka:document-ir:{project_id}:{identity.document_id}:"
        f"{identity.ir_version}:{identity.revision}"
    )
    return f"fil_{uuid5(NAMESPACE_URL, value)}"


def _snapshot_filename(identity: IRSnapshotIdentity) -> str:
    return f"document-ir-r{identity.revision:06d}-v{identity.ir_version}.json"


def _timestamp(value: datetime | None) -> str:
    timestamp = datetime.now(UTC) if value is None else value
    if timestamp.tzinfo is None:
        raise ValueError("The IR snapshot timestamp must include a timezone.")
    return timestamp.astimezone(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")
