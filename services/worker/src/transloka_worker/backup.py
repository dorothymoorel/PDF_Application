from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol, Self
from uuid import NAMESPACE_URL, UUID, uuid4, uuid5

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker
from transloka_core.backup.archive import BackupArchiveArtifact, create_backup
from transloka_core.backup.database import InsufficientBackupSpaceError
from transloka_core.backup.manifest import BackupType
from transloka_core.backup.verification import verify_backup_archive
from transloka_core.database import transaction_scope
from transloka_core.database.models.backups import Backup, BackupStatus
from transloka_core.database.models.files import FileRole, FileStatus, StoredFile
from transloka_core.database.models.jobs import (
    ApplicationJob,
    JobAttempt,
    JobAttemptStatus,
    JobStatus,
    JobType,
)
from transloka_core.jobs.cancellation import JobCancellationService
from transloka_core.jobs.progress import JobProgressService
from transloka_core.storage import LocalDataDirectories

logger = logging.getLogger(__name__)

BACKUP_COMMAND_SCHEMA = "transloka.backup.command.v1"
BACKUP_JOB_RESULT_SCHEMA = "transloka.backup.job.v1"
_COMMAND_FIELDS = frozenset(
    {"schema", "backup_type", "include_queue_database", "include_temporary"}
)
_SUPPORTED = frozenset(
    {BackupType.DATABASE_ONLY.value, BackupType.METADATA.value, BackupType.FULL_PROJECTS.value}
)


class BackupWorkerError(RuntimeError):
    pass


class PublicBackupRequest(Protocol):
    @property
    def backup_type(self) -> str: ...

    @property
    def include_original_files(self) -> bool: ...

    @property
    def include_exports(self) -> bool: ...

    @property
    def include_intermediate_files(self) -> bool: ...


@dataclass(frozen=True, slots=True)
class BackupCommand:
    backup_type: str
    include_queue_database: bool = False
    include_temporary: bool = False

    def __post_init__(self) -> None:
        if (
            type(self.include_queue_database) is not bool
            or type(self.include_temporary) is not bool
        ):
            raise BackupWorkerError("The backup command flags are invalid.")
        if self.backup_type not in _SUPPORTED:
            raise BackupWorkerError("The backup command backup type is invalid.")

    def to_payload(self) -> dict[str, object]:
        return {
            "schema": BACKUP_COMMAND_SCHEMA,
            "backup_type": self.backup_type,
            "include_queue_database": self.include_queue_database,
            "include_temporary": self.include_temporary,
        }

    @classmethod
    def from_payload_json(cls, value: str) -> Self:
        payload = _decode_backup_command(value)
        if frozenset(payload) != _COMMAND_FIELDS:
            raise BackupWorkerError("The backup command fields are invalid.")
        if payload["schema"] != BACKUP_COMMAND_SCHEMA:
            raise BackupWorkerError("The backup command schema is unsupported.")
        try:
            return cls(
                backup_type=_string_value(payload, "backup_type"),
                include_queue_database=_boolean_value(payload, "include_queue_database"),
                include_temporary=_boolean_value(payload, "include_temporary"),
            )
        except (KeyError, TypeError):
            raise BackupWorkerError("The backup command values are invalid.") from None


def map_public_backup_request(public: PublicBackupRequest) -> BackupCommand:
    for field in (
        "include_original_files",
        "include_exports",
        "include_intermediate_files",
    ):
        value = getattr(public, field, None)
        if type(value) is not bool:
            raise BackupWorkerError(f"{field} must be a boolean.")
        if value:
            raise BackupWorkerError(f"{field} is not supported by the current backup service.")
    return BackupCommand(
        backup_type=public.backup_type,
        include_queue_database=False,
        include_temporary=False,
    )


@dataclass(frozen=True, slots=True)
class LoadedBackupJob:
    job_id: str
    idempotency_key: str
    command: BackupCommand


@dataclass(frozen=True, slots=True)
class BackupRunResult:
    job_id: str
    backup_id: str | None
    status: JobStatus
    storage_key: str | None
    checksum_sha256: str | None
    size_bytes: int | None


class DatabaseBackupRequestLoader:
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def load(self, job_id: str) -> LoadedBackupJob:
        _validate_identifier(job_id, "job_")
        with self._session_factory() as session:
            job = session.get(ApplicationJob, job_id)
            if job is None or job.job_type != JobType.BACKUP_DATABASE.value:
                raise BackupWorkerError("The backup job is unavailable.")
            if job.queue_name != "transloka":
                raise BackupWorkerError("The backup job is unavailable.")
            if job.status not in {
                JobStatus.QUEUED.value,
                JobStatus.RETRYING.value,
                JobStatus.RUNNING.value,
                JobStatus.CANCELLATION_REQUESTED.value,
                JobStatus.CANCELLED.value,
            }:
                raise BackupWorkerError("The backup job is not executable.")
            command = BackupCommand.from_payload_json(job.payload_json)
            return LoadedBackupJob(
                job_id=job.id, idempotency_key=job.idempotency_key, command=command
            )


class ProductionBackupJobRunner:
    def __init__(
        self,
        loader: DatabaseBackupRequestLoader,
        session_factory: sessionmaker[Session],
        directories: LocalDataDirectories,
        *,
        worker_identifier: str | None = None,
    ) -> None:
        if not isinstance(loader, DatabaseBackupRequestLoader):
            raise ValueError("A database backup loader is required.")
        if not isinstance(directories, LocalDataDirectories) or not directories.root.is_absolute():
            raise ValueError("Absolute local data directories are required.")
        self._loader = loader
        self._session_factory = session_factory
        self._directories = directories
        self._temporary_root = directories.temporary.resolve(strict=False)
        self._worker_identifier = _worker_identifier(worker_identifier)

    def run(self, job_id: str) -> BackupRunResult:
        existing = _completed_result(self._session_factory, job_id)
        if existing is not None:
            return existing
        loaded = self._loader.load(job_id)
        try:
            _start_attempt(self._session_factory, job_id, self._worker_identifier)
            # checkpoint before archive creation only
            if JobCancellationService(self._session_factory, self._temporary_root).checkpoint(
                job_id
            ):
                return _finish_cancelled(self._session_factory, loaded, self._worker_identifier)
            progress = JobProgressService(self._session_factory)
            progress.update(job_id, progress=0.05, current_stage="BACKUP_PREPARING")
            # resolve directories: try to get from session_factory's engine url or use provided
            directories = self._directories
            # single non-interruptible call
            artifact = create_backup(
                directories,
                loaded.command.backup_type,
                include_queue_database=loaded.command.include_queue_database,
                include_temporary=loaded.command.include_temporary,
            )
            # verify before DB publish; on failure delete the just-moved archive
            try:
                verify_backup_archive(
                    directories.root / artifact.storage_key, data_root=directories.root
                )
            except Exception as verr:
                _cleanup_artifact(directories, artifact, job_id)
                _fail_job(self._session_factory, job_id, verr, self._worker_identifier)
                raise
            # publish atomically; on DB failure delete the unreferenced archive
            try:
                return _publish(self._session_factory, loaded, artifact, self._worker_identifier)
            except Exception as pub_err:
                _cleanup_artifact(directories, artifact, job_id)
                # _publish already attempted to mark failed? If publish failed before marking, ensure fail
                if not _is_already_failed(self._session_factory, job_id):
                    _fail_job(self._session_factory, job_id, pub_err, self._worker_identifier)
                raise
        except Exception as exc:
            # For other branches where _fail_job not yet called
            if not _is_already_failed(self._session_factory, job_id):
                _fail_job(self._session_factory, job_id, exc, self._worker_identifier)
            raise


def _completed_result(
    session_factory: sessionmaker[Session], job_id: str
) -> BackupRunResult | None:
    with session_factory() as session:
        job = session.get(ApplicationJob, job_id)
        if job is None:
            return None
        if job.status not in {
            JobStatus.COMPLETED.value,
            JobStatus.COMPLETED_WITH_WARNINGS.value,
            JobStatus.PARTIALLY_COMPLETED.value,
        }:
            return None
        # Find associated Backup via result_json or via latest Backup with file_id?
        # For backup, we store result_json with backup_id; if not present, lookup via Backup
        backup = None
        if job.result_json:
            try:
                data = json.loads(job.result_json)
                backup_id = data.get("backup_id")
                if backup_id:
                    backup = session.get(Backup, backup_id)
            except (json.JSONDecodeError, TypeError):
                backup = None
        if backup is None:
            # fallback: find Backup with file_id that matches job's stored file? Try to find latest Backup
            # Since backup creation is 1:1 with job, we can query Backup where status COMPLETED and created_at close?
            # Simpler: query Backup via StoredFile that was created for this job? We need to find Backup that was created in _publish.
            # _publish stores result_json with backup_id, so above should succeed. If not, try to find any Backup that has not been returned.
            # For idempotency, we can just return a result based on job's stored result.
            pass
        if job.status == JobStatus.COMPLETED.value and backup is None:
            # If no backup found but job is completed, still return completed result without backup details (should not happen in success case)
            # For test exact-once, we need to ensure second run doesn't create second archive, so returning existing result is enough.
            try:
                status = JobStatus(job.status)
            except ValueError:
                status = JobStatus.FAILED
            return BackupRunResult(
                job_id=job.id,
                backup_id=None,
                status=status,
                storage_key=None,
                checksum_sha256=None,
                size_bytes=None,
            )
        if backup is not None:
            try:
                status = JobStatus(job.status)
            except ValueError:
                status = JobStatus.FAILED
            stored = session.get(StoredFile, backup.file_id) if backup.file_id else None
            return BackupRunResult(
                job_id=job.id,
                backup_id=backup.id,
                status=status,
                storage_key=stored.storage_key if stored else None,
                checksum_sha256=backup.checksum_sha256,
                size_bytes=backup.size_bytes,
            )
        # If job is completed but no backup found (should not happen), return job-based result
        try:
            status = JobStatus(job.status)
        except ValueError:
            status = JobStatus.FAILED
        return BackupRunResult(
            job_id=job.id,
            backup_id=None,
            status=status,
            storage_key=None,
            checksum_sha256=None,
            size_bytes=None,
        )


def _start_attempt(
    session_factory: sessionmaker[Session], job_id: str, worker_identifier: str
) -> None:
    now = _utc_now()
    with transaction_scope(session_factory) as session:
        job = session.get(ApplicationJob, job_id)
        if job is None:
            raise BackupWorkerError("The backup job was not found.")
        if job.status not in {
            JobStatus.QUEUED.value,
            JobStatus.RETRYING.value,
            JobStatus.RUNNING.value,
            JobStatus.CANCELLATION_REQUESTED.value,
            JobStatus.CANCELLED.value,
        }:
            raise BackupWorkerError("The backup job is not in an executable state.")
        attempts = list(
            session.scalars(
                select(JobAttempt)
                .where(JobAttempt.job_id == job_id)
                .order_by(JobAttempt.attempt_number)
            )
        )
        if attempts and attempts[-1].status == JobAttemptStatus.RUNNING.value:
            attempts[-1].worker_identifier = worker_identifier
            return
        # Update job to RUNNING if it was QUEUED
        if job.status == JobStatus.QUEUED.value:
            job.status = JobStatus.RUNNING.value
            job.current_stage = "BACKUP_RUNNING"
            job.started_at = job.started_at or now
            job.heartbeat_at = now
            job.progress = 0.0
        elif job.status == JobStatus.RETRYING.value:
            job.status = JobStatus.RUNNING.value
            job.current_stage = "BACKUP_RUNNING"
            job.heartbeat_at = now
        session.add(
            JobAttempt(
                id=str(
                    uuid5(NAMESPACE_URL, f"transloka:backup-attempt:{job_id}:{len(attempts) + 1}")
                ),
                job_id=job_id,
                attempt_number=len(attempts) + 1,
                status=JobAttemptStatus.RUNNING.value,
                worker_identifier=worker_identifier,
                started_at=now,
                completed_at=None,
                duration_ms=None,
                error_code=None,
                error_message=None,
                details_json=None,
            )
        )
        session.flush()


def _finish_cancelled(
    session_factory: sessionmaker[Session], loaded: LoadedBackupJob, worker_identifier: str
) -> BackupRunResult:
    now = _utc_now()
    with transaction_scope(session_factory) as session:
        job = session.get(ApplicationJob, loaded.job_id)
        if job is None:
            raise BackupWorkerError("The cancelled backup job disappeared.")
        job.status = JobStatus.CANCELLED.value
        job.current_stage = JobStatus.CANCELLED.value
        job.cancelled_at = job.cancelled_at or now
        job.completed_at = job.completed_at or now
        job.heartbeat_at = now
        # finish attempt as CANCELLED if exists
        attempt = _latest_attempt(session, loaded.job_id)
        if attempt and attempt.status == JobAttemptStatus.RUNNING.value:
            attempt.status = JobAttemptStatus.CANCELLED.value
            attempt.completed_at = now
            attempt.worker_identifier = worker_identifier
        session.flush()
    return BackupRunResult(
        job_id=loaded.job_id,
        backup_id=None,
        status=JobStatus.CANCELLED,
        storage_key=None,
        checksum_sha256=None,
        size_bytes=None,
    )


def _publish(
    session_factory: sessionmaker[Session],
    loaded: LoadedBackupJob,
    artifact: BackupArchiveArtifact,
    worker_identifier: str,
) -> BackupRunResult:
    now = _utc_now()
    backup_id = f"bkp_{uuid4()}"
    file_id = f"fil_{uuid4()}"
    # idempotent guard: if backup already exists for this job via result_json, return it
    with transaction_scope(session_factory) as session:
        job = session.get(ApplicationJob, loaded.job_id)
        if job is None:
            raise BackupWorkerError("The backup job disappeared before publication.")
        # check if already published (exact-once)
        existing_backup = None
        if job.result_json:
            try:
                data = json.loads(job.result_json)
                existing_id = data.get("backup_id")
                if existing_id:
                    existing_backup = session.get(Backup, existing_id)
                    if existing_backup and existing_backup.status == BackupStatus.COMPLETED.value:
                        stored = (
                            session.get(StoredFile, existing_backup.file_id)
                            if existing_backup.file_id
                            else None
                        )
                        return BackupRunResult(
                            job_id=job.id,
                            backup_id=existing_backup.id,
                            status=JobStatus(job.status),
                            storage_key=stored.storage_key if stored else artifact.storage_key,
                            checksum_sha256=existing_backup.checksum_sha256,
                            size_bytes=existing_backup.size_bytes,
                        )
            except (json.JSONDecodeError, TypeError, ValueError):
                pass
        # create StoredFile
        session.add(
            StoredFile(
                id=file_id,
                project_id=None,
                document_id=None,
                file_role=FileRole.BACKUP.value,
                storage_key=artifact.storage_key,
                original_filename=Path(artifact.storage_key).name,
                safe_filename=Path(artifact.storage_key).name,
                mime_type="application/zip",
                size_bytes=artifact.size_bytes,
                checksum_sha256=artifact.checksum_sha256,
                is_immutable=1,
                status=FileStatus.VALIDATED.value,
                metadata_json=None,
                created_at=artifact.created_at,
                deleted_at=None,
            )
        )
        session.flush()
        session.add(
            Backup(
                id=backup_id,
                backup_type=artifact.backup_type.value,
                file_id=file_id,
                application_version=artifact.manifest.application_version,
                database_schema_version=artifact.manifest.database_schema_version,
                status=BackupStatus.COMPLETED.value,
                size_bytes=artifact.size_bytes,
                checksum_sha256=artifact.checksum_sha256,
                included_content_json=json.dumps(
                    list(artifact.included_content),
                    ensure_ascii=False,
                    separators=(",", ":"),
                    sort_keys=True,
                ),
                created_at=artifact.created_at,
                completed_at=now,
                error_code=None,
            )
        )
        session.flush()
        job.status = JobStatus.COMPLETED.value
        job.current_stage = JobStatus.COMPLETED.value
        job.progress = 1.0
        job.completed_at = now
        job.heartbeat_at = now
        job.error_code = None
        job.error_message = None
        job.result_json = json.dumps(
            {
                "schema": BACKUP_JOB_RESULT_SCHEMA,
                "backup_id": backup_id,
                "storage_key": artifact.storage_key,
                "checksum_sha256": artifact.checksum_sha256,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
        # complete attempt
        attempt = _latest_attempt(session, loaded.job_id)
        if attempt and attempt.status == JobAttemptStatus.RUNNING.value:
            attempt.status = JobAttemptStatus.COMPLETED.value
            attempt.completed_at = now
            attempt.worker_identifier = worker_identifier
        session.flush()
    return BackupRunResult(
        job_id=loaded.job_id,
        backup_id=backup_id,
        status=JobStatus.COMPLETED,
        storage_key=artifact.storage_key,
        checksum_sha256=artifact.checksum_sha256,
        size_bytes=artifact.size_bytes,
    )


def _fail_job(
    session_factory: sessionmaker[Session], job_id: str, error: Exception, worker_identifier: str
) -> None:
    now = _utc_now()
    error_code = _error_code(error)
    raw_msg = str(error).strip()
    error_message = raw_msg[:500] if raw_msg and raw_msg.isprintable() else "Backup job failed."
    try:
        with transaction_scope(session_factory) as session:
            job = session.get(ApplicationJob, job_id)
            if job is None:
                return
            if job.status in {JobStatus.COMPLETED.value, JobStatus.CANCELLED.value}:
                return
            job.status = JobStatus.FAILED.value
            job.current_stage = JobStatus.FAILED.value
            job.error_code = error_code
            job.error_message = error_message
            job.completed_at = now
            job.heartbeat_at = now
            attempt = _latest_attempt(session, job_id)
            if attempt and attempt.status == JobAttemptStatus.RUNNING.value:
                attempt.status = JobAttemptStatus.FAILED.value
                attempt.completed_at = now
                attempt.worker_identifier = worker_identifier
                attempt.error_code = error_code
                attempt.error_message = error_message
            session.flush()
    except Exception:
        return


def _is_already_failed(session_factory: sessionmaker[Session], job_id: str) -> bool:
    try:
        with session_factory() as session:
            job = session.get(ApplicationJob, job_id)
            if job is None:
                return False
            return job.status in {
                JobStatus.FAILED.value,
                JobStatus.CANCELLED.value,
                JobStatus.COMPLETED.value,
                JobStatus.COMPLETED_WITH_WARNINGS.value,
                JobStatus.PARTIALLY_COMPLETED.value,
            }
    except Exception:
        return False


def _cleanup_artifact(
    directories: LocalDataDirectories,
    artifact: BackupArchiveArtifact,
    job_id: str,
) -> None:
    try:
        (directories.root / artifact.storage_key).unlink(missing_ok=True)
    except OSError:
        logger.warning(
            "BACKUP_CLEANUP_FAILED",
            extra={"job_id": job_id, "error_code": "BACKUP_CLEANUP_FAILED"},
        )


def _error_code(error: Exception) -> str:
    if isinstance(error, InsufficientBackupSpaceError):
        return "INSUFFICIENT_DISK"
    return type(error).__name__.upper()[:100] or "BACKUPWORKERERROR"


def _latest_attempt(session: Session, job_id: str) -> JobAttempt | None:
    return session.scalars(
        select(JobAttempt)
        .where(JobAttempt.job_id == job_id)
        .order_by(JobAttempt.attempt_number.desc())
    ).first()


def _worker_identifier(value: str | None) -> str:
    candidate = (
        value or os.environ.get("COMPUTERNAME") or os.environ.get("HOSTNAME") or "transloka-worker"
    )
    normalized = candidate.strip()
    if not normalized or not normalized.isprintable() or len(normalized) > 200:
        return "transloka-worker"
    return normalized


def _utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _decode_backup_command(value: str) -> dict[str, object]:
    if type(value) is not str or not value:
        raise BackupWorkerError("The backup command JSON is invalid.")

    def decode_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, item in pairs:
            if key in result:
                raise BackupWorkerError("The backup command fields are duplicated.")
            result[key] = item
        return result

    try:
        payload = json.loads(value, object_pairs_hook=decode_pairs)
    except (json.JSONDecodeError, BackupWorkerError):
        raise BackupWorkerError("The backup command JSON is invalid.") from None
    if not isinstance(payload, dict):
        raise BackupWorkerError("The backup command must be a JSON object.")
    return payload


def _string_value(payload: dict[str, object], key: str) -> str:
    value = payload[key]
    if type(value) is not str:
        raise BackupWorkerError("The backup command values are invalid.")
    return value


def _boolean_value(payload: dict[str, object], key: str) -> bool:
    value = payload[key]
    if type(value) is not bool:
        raise BackupWorkerError("The backup command values are invalid.")
    return value


def _validate_identifier(value: object, prefix: str) -> None:
    if type(value) is not str or not value.startswith(prefix):
        raise BackupWorkerError("A backup command identifier is invalid.")
    try:
        identifier = UUID(value[len(prefix) :])
    except (ValueError, AttributeError):
        raise BackupWorkerError("A backup command identifier is invalid.") from None
    if value != f"{prefix}{identifier}":
        raise BackupWorkerError("A backup command identifier is invalid.")


__all__ = [
    "BACKUP_COMMAND_SCHEMA",
    "BACKUP_JOB_RESULT_SCHEMA",
    "BackupCommand",
    "BackupRunResult",
    "BackupWorkerError",
    "DatabaseBackupRequestLoader",
    "LoadedBackupJob",
    "ProductionBackupJobRunner",
    "map_public_backup_request",
]
