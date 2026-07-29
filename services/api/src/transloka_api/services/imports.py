from dataclasses import dataclass
from datetime import UTC, datetime
from typing import BinaryIO, cast
from uuid import NAMESPACE_URL, uuid5

from transloka_core.database.models.files import FileRole, FileStatus
from transloka_core.repositories.files import (
    StoredFileNotFoundError,
    StoredFileRecord,
    StoredFilesRepository,
)
from transloka_core.storage.local import (
    LocalFileStorage,
    LocalFileStorageError,
    StoredFileExistsError,
    TemporaryStoredFile,
)
from transloka_documents.validation import PdfValidationResult

_MAX_FILENAME_LENGTH = 255
_MAX_IDEMPOTENCY_KEY_LENGTH = 200
_TEMPORARY_PREFIX = "transloka-file-"
_TEMPORARY_SUFFIX = ".tmp"


class InvalidUploadMetadataError(ValueError):
    pass


class EmptyUploadError(ValueError):
    pass


class UploadTooLargeError(ValueError):
    pass


class UploadInterruptedError(RuntimeError):
    pass


class UploadStorageError(RuntimeError):
    pass


class ValidatedUploadMismatchError(ValueError):
    pass


class OriginalImportConflictError(ValueError):
    pass


@dataclass(frozen=True, slots=True)
class StagedUpload:
    project_id: str
    original_filename: str
    idempotency_key: str
    set_as_active: bool
    temporary: TemporaryStoredFile

    @property
    def upload_id(self) -> str:
        name = self.temporary.path.name
        token = name.removeprefix(_TEMPORARY_PREFIX).removesuffix(_TEMPORARY_SUFFIX)
        return f"upl_{token}"


class ImportService:
    def __init__(self, storage: LocalFileStorage, max_upload_bytes: int) -> None:
        if max_upload_bytes < 1:
            raise ValueError("The upload size limit must be positive.")
        self._storage = storage
        self._max_upload_bytes = max_upload_bytes

    def stage_upload(
        self,
        *,
        project_id: str,
        original_filename: str,
        idempotency_key: str,
        set_as_active: bool,
        stream: BinaryIO,
    ) -> StagedUpload:
        _validate_filename(original_filename)
        _validate_idempotency_key(idempotency_key)
        if not isinstance(set_as_active, bool):
            raise InvalidUploadMetadataError("The active document flag is invalid.")

        limited_stream = _LimitedStream(stream, self._max_upload_bytes)
        try:
            temporary = self._storage.write_temporary(cast(BinaryIO, limited_stream))
        except LocalFileStorageError as exc:
            cause = exc.__cause__
            if isinstance(cause, (UploadTooLargeError, UploadInterruptedError)):
                raise cause from exc
            raise UploadStorageError("The upload could not be staged.") from exc

        staged = StagedUpload(
            project_id=project_id,
            original_filename=original_filename,
            idempotency_key=idempotency_key,
            set_as_active=set_as_active,
            temporary=temporary,
        )
        if temporary.size_bytes == 0:
            self.discard(staged)
            raise EmptyUploadError("The uploaded file is empty.")
        return staged

    def store_original(
        self,
        staged: StagedUpload,
        validation: PdfValidationResult,
        repository: StoredFilesRepository,
    ) -> StoredFileRecord:
        if (
            validation.checksum_sha256 != staged.temporary.checksum_sha256
            or validation.size_bytes != staged.temporary.size_bytes
        ):
            self.discard(staged)
            raise ValidatedUploadMismatchError(
                "The validated PDF does not match the staged upload."
            )

        file_id = _original_file_id(staged)
        storage_key = f"projects/{staged.project_id}/original/{file_id}.pdf"
        try:
            existing = repository.get(file_id)
        except StoredFileNotFoundError:
            pass
        else:
            self.discard(staged)
            if not _is_matching_original(existing, staged, validation, storage_key):
                raise OriginalImportConflictError(
                    "The idempotency key belongs to a different original import."
                )
            try:
                stored_checksum = self._storage.checksum(storage_key)
            except LocalFileStorageError as exc:
                raise UploadStorageError("The stored original could not be verified.") from exc
            if stored_checksum != validation.checksum_sha256:
                raise OriginalImportConflictError(
                    "The stored original no longer matches its database record."
                )
            return existing

        try:
            artifact = self._storage.commit(
                staged.temporary,
                storage_key,
                immutable=True,
            )
        except StoredFileExistsError as exc:
            raise OriginalImportConflictError(
                "The original storage destination already exists."
            ) from exc
        except LocalFileStorageError as exc:
            raise UploadStorageError("The validated PDF could not be stored.") from exc

        return repository.create(
            file_id=file_id,
            project_id=staged.project_id,
            document_id=None,
            file_role=FileRole.ORIGINAL,
            storage_key=artifact.storage_key,
            original_filename=staged.original_filename,
            safe_filename=f"{file_id}.pdf",
            mime_type="application/pdf",
            size_bytes=artifact.size_bytes,
            checksum_sha256=artifact.checksum_sha256,
            is_immutable=True,
            status=FileStatus.VALIDATED,
            metadata=None,
            created_at=_utc_now(),
        )

    @staticmethod
    def discard(staged: StagedUpload) -> None:
        try:
            staged.temporary.path.unlink(missing_ok=True)
        except OSError as exc:
            raise UploadStorageError("The staged upload could not be removed.") from exc


class _LimitedStream:
    def __init__(self, source: BinaryIO, max_bytes: int) -> None:
        self._source = source
        self._max_bytes = max_bytes
        self._bytes_read = 0

    def read(self, size: int = -1) -> bytes:
        requested = self._max_bytes - self._bytes_read + 1
        if size >= 0:
            requested = min(size, requested)
        try:
            chunk = self._source.read(requested)
        except Exception as exc:
            raise UploadInterruptedError("The upload stream was interrupted.") from exc
        if not isinstance(chunk, bytes):
            raise UploadInterruptedError("The upload stream returned invalid data.")

        self._bytes_read += len(chunk)
        if self._bytes_read > self._max_bytes:
            raise UploadTooLargeError("The uploaded file exceeds the configured size limit.")
        return chunk


def _validate_filename(filename: str) -> None:
    if (
        not isinstance(filename, str)
        or not filename
        or len(filename) > _MAX_FILENAME_LENGTH
        or filename != filename.strip()
        or not filename.isprintable()
        or filename in {".", ".."}
        or "/" in filename
        or "\\" in filename
    ):
        raise InvalidUploadMetadataError("The upload filename is invalid.")


def _validate_idempotency_key(key: str) -> None:
    if (
        not isinstance(key, str)
        or not key
        or len(key) > _MAX_IDEMPOTENCY_KEY_LENGTH
        or key != key.strip()
        or not key.isprintable()
    ):
        raise InvalidUploadMetadataError("The idempotency key is invalid.")


def _original_file_id(staged: StagedUpload) -> str:
    import_key = f"transloka:original:{staged.project_id}:{staged.idempotency_key}"
    return f"fil_{uuid5(NAMESPACE_URL, import_key)}"


def _is_matching_original(
    existing: StoredFileRecord,
    staged: StagedUpload,
    validation: PdfValidationResult,
    storage_key: str,
) -> bool:
    return (
        existing.project_id == staged.project_id
        and existing.document_id is None
        and existing.file_role is FileRole.ORIGINAL
        and existing.storage_key == storage_key
        and existing.original_filename == staged.original_filename
        and existing.safe_filename == f"{existing.id}.pdf"
        and existing.mime_type == "application/pdf"
        and existing.size_bytes == validation.size_bytes
        and existing.checksum_sha256 == validation.checksum_sha256
        and existing.is_immutable
        and existing.status is FileStatus.VALIDATED
    )


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")
