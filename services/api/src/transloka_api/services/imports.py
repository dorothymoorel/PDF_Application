from dataclasses import dataclass
from typing import BinaryIO, cast

from transloka_core.storage.local import (
    LocalFileStorage,
    LocalFileStorageError,
    TemporaryStoredFile,
)

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
