"""Validate and atomically restore a managed TransLoka backup."""

from __future__ import annotations

import hashlib
import importlib
import os
import shutil
import sqlite3
import tempfile
import time
from collections.abc import Callable
from contextlib import closing
from dataclasses import dataclass
from pathlib import Path
from typing import Any, BinaryIO, Protocol, cast
from zipfile import ZipFile

from transloka_core.backup.archive import BackupArchiveArtifact, create_full_project_backup
from transloka_core.backup.manifest import BackupType
from transloka_core.backup.verification import (
    BackupVerificationError,
    BackupVerificationResult,
    verify_backup_archive,
)
from transloka_core.database import DATABASE_FILENAME
from transloka_core.storage import (
    LocalDataDirectories,
    ensure_local_data_directories,
)

MAINTENANCE_MARKER_FILENAME = ".maintenance.lock"
APPLICATION_MUTATION_LOCK_FILENAME = ".application-mutation.lock"
WORKER_EXECUTION_LOCK_FILENAME = ".worker-execution.lock"
QUEUE_DATABASE_FILENAME = "tasks.db"
_MANIFEST_FILENAME = "manifest.json"
_WARNING_FILENAME = "backup-warning.txt"
_CONFIRMATION = "RESTORE"
_LOCK_POLL_INTERVAL_SECONDS = 0.05


class RestoreError(RuntimeError):
    """Base error raised when a restore cannot be completed safely."""


class RestoreConfirmationError(RestoreError):
    """Raised when the explicit restore confirmation is missing."""


class RestoreValidationError(RestoreError):
    """Raised when an archive cannot be validated for restoration."""


class RestoreBusyError(RestoreError):
    """Raised when another restore already owns the maintenance lock."""


class RestoreRollbackError(RestoreError):
    """Raised when the previous state cannot be restored after a failure."""


class _CrossProcessFileLock:
    """One exclusive byte-range lock held through an open file handle."""

    def __init__(self, directories: LocalDataDirectories, filename: str) -> None:
        self._directories = directories
        self._path = directories.root / filename
        self._stream: BinaryIO | None = None

    @property
    def acquired(self) -> bool:
        return self._stream is not None

    def acquire(self) -> None:
        if self._stream is not None:
            return
        ensure_local_data_directories(self._directories)
        stream = self._path.open("a+b")
        try:
            stream.seek(0, os.SEEK_END)
            if stream.tell() == 0:
                stream.write(b"\0")
                stream.flush()
                os.fsync(stream.fileno())
            while True:
                stream.seek(0)
                try:
                    _lock_stream(stream)
                except OSError:
                    time.sleep(_LOCK_POLL_INTERVAL_SECONDS)
                    continue
                self._stream = stream
                return
        except BaseException:
            stream.close()
            raise

    def release(self) -> None:
        stream = self._stream
        if stream is None:
            return
        self._stream = None
        try:
            stream.seek(0)
            _unlock_stream(stream)
        finally:
            stream.close()


class WorkerExecutionLock(_CrossProcessFileLock):
    """Cross-process lease held while a worker mutation executes."""

    def __init__(self, directories: LocalDataDirectories) -> None:
        super().__init__(directories, WORKER_EXECUTION_LOCK_FILENAME)


class ApplicationMutationLock(_CrossProcessFileLock):
    """Cross-process lease held while an API mutation executes."""

    def __init__(self, directories: LocalDataDirectories) -> None:
        super().__init__(directories, APPLICATION_MUTATION_LOCK_FILENAME)


class RestoreCoordinator(Protocol):
    """Application and worker lifecycle hooks used by the restore workflow."""

    def enter_maintenance(self) -> None: ...

    def pause_worker(self) -> None: ...

    def close_database(self) -> None: ...

    def reopen_database(self) -> None: ...

    def restart_checks(self) -> None: ...

    def resume_worker(self) -> None: ...

    def exit_maintenance(self) -> None: ...


@dataclass(frozen=True, slots=True)
class RestoreResult:
    """Evidence returned after the replacement and restart checks succeed."""

    archive_path: Path
    backup_type: BackupType
    restored_content: tuple[str, ...]
    pre_restore_backup: BackupArchiveArtifact


class FileRestoreCoordinator:
    """Coordinate restore state with a cross-process maintenance marker.

    The worker uses the same marker to reject new Huey task execution. API
    integrations can provide database lifecycle callbacks so the active engine
    is disposed before replacement and recreated before restart checks.
    """

    def __init__(
        self,
        directories: LocalDataDirectories,
        *,
        close_database: Callable[[], None] | None = None,
        reopen_database: Callable[[], None] | None = None,
        restart_checks: Callable[[], None] | None = None,
    ) -> None:
        self._directories = directories
        self._marker = directories.root / MAINTENANCE_MARKER_FILENAME
        self._close_database = close_database or _noop
        self._reopen_database = reopen_database or _noop
        self._restart_checks = restart_checks or self._check_database
        self._owns_marker = False
        self._application_lock = ApplicationMutationLock(directories)
        self._worker_lock = WorkerExecutionLock(directories)

    def enter_maintenance(self) -> None:
        ensure_local_data_directories(self._directories)
        try:
            descriptor = os.open(
                self._marker,
                os.O_CREAT | os.O_EXCL | os.O_WRONLY,
                0o600,
            )
        except FileExistsError as exc:
            raise RestoreBusyError("Another restore is already in maintenance mode.") from exc
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as marker:
                marker.write("restore\n")
                marker.flush()
                os.fsync(marker.fileno())
        except OSError:
            self._marker.unlink(missing_ok=True)
            raise
        self._owns_marker = True
        try:
            self._application_lock.acquire()
        except BaseException:
            self._marker.unlink(missing_ok=True)
            self._owns_marker = False
            raise
        if not self._marker.is_file():
            self._application_lock.release()
            self._owns_marker = False
            raise RestoreError("Maintenance mode ended before API mutations were paused.")

    def pause_worker(self) -> None:
        if not self._owns_marker or not self._marker.is_file():
            raise RestoreError("Maintenance mode was not entered before pausing the worker.")
        self._worker_lock.acquire()
        if not self._owns_marker or not self._marker.is_file():
            self._worker_lock.release()
            raise RestoreError("Maintenance mode ended before the worker was paused.")

    def close_database(self) -> None:
        self._close_database()

    def reopen_database(self) -> None:
        self._reopen_database()

    def restart_checks(self) -> None:
        self._restart_checks()

    def resume_worker(self) -> None:
        self._worker_lock.release()

    def exit_maintenance(self) -> None:
        self._worker_lock.release()
        if self._owns_marker:
            self._marker.unlink(missing_ok=True)
            self._owns_marker = False
        self._application_lock.release()

    def _check_database(self) -> None:
        database = self._directories.database / DATABASE_FILENAME
        if not database.is_file() or database.is_symlink():
            raise RestoreError("The restored application database is unavailable.")
        try:
            with closing(sqlite3.connect(f"{database.as_uri()}?mode=ro", uri=True)) as connection:
                if connection.execute("PRAGMA integrity_check").fetchone() != ("ok",):
                    raise RestoreError("The restored application database failed integrity checks.")
                if tuple(connection.execute("PRAGMA foreign_key_check")):
                    raise RestoreError(
                        "The restored application database has foreign-key violations."
                    )
                self._check_managed_files(connection)
        except RestoreError:
            raise
        except sqlite3.Error as exc:
            raise RestoreError("The restored application database could not be opened.") from exc

    def _check_managed_files(self, connection: sqlite3.Connection) -> None:
        rows = connection.execute(
            """
            SELECT storage_key, size_bytes, checksum_sha256
            FROM stored_files
            WHERE status IN ('AVAILABLE', 'VALIDATED')
            ORDER BY id
            """
        )
        for storage_key, size_bytes, checksum_sha256 in rows:
            try:
                path = _managed_file(self._directories.root, str(storage_key))
                if path.stat().st_size != int(size_bytes):
                    raise RestoreError("A restored managed file has an invalid size.")
                if _sha256_file(path) != str(checksum_sha256):
                    raise RestoreError("A restored managed file failed its checksum.")
            except RestoreError:
                raise
            except (OSError, TypeError, ValueError) as exc:
                raise RestoreError("A restored managed file is unavailable.") from exc


class RestoreWorkflow:
    """Perform a validated, maintenance-gated, atomic restore."""

    def __init__(
        self,
        directories: LocalDataDirectories,
        *,
        coordinator: RestoreCoordinator | None = None,
    ) -> None:
        self._directories = directories
        self._coordinator = coordinator or FileRestoreCoordinator(directories)

    def restore(
        self,
        archive_path: str | os.PathLike[str],
        *,
        confirmation: str,
        restore_files: bool = True,
        completion: Callable[[RestoreResult], None] | None = None,
    ) -> RestoreResult:
        if confirmation != _CONFIRMATION:
            raise RestoreConfirmationError("Restore requires the exact confirmation token RESTORE.")
        if not isinstance(restore_files, bool):
            raise RestoreValidationError("The restore-files option must be a boolean.")
        ensure_local_data_directories(self._directories)
        source_archive = self._resolve_archive(archive_path)
        entered = False
        paused = False
        replacement: _ReplacementState | None = None
        database_closed = False
        rollback_failed = False
        staging_root: Path | None = None
        pre_restore_backup: BackupArchiveArtifact | None = None
        result: RestoreResult | None = None
        try:
            self._coordinator.enter_maintenance()
            entered = True
            self._coordinator.pause_worker()
            paused = True

            pre_restore_backup = create_full_project_backup(self._directories)
            verify_backup_archive(
                self._directories.root / Path(pre_restore_backup.storage_key),
                expected_checksum_sha256=pre_restore_backup.checksum_sha256,
                data_root=self._directories.root,
            )
            verified = self._verify_source(source_archive)
            staging_root = self._stage_archive(source_archive, verified)

            self._coordinator.close_database()
            database_closed = True
            replacement = self._replace_active_state(
                staging_root,
                verified.manifest.backup_type,
                restore_files=restore_files,
            )
            self._coordinator.reopen_database()
            database_closed = False
            self._coordinator.restart_checks()
            result = RestoreResult(
                archive_path=source_archive,
                backup_type=verified.manifest.backup_type,
                restored_content=verified.verified_files,
                pre_restore_backup=pre_restore_backup,
            )
            if completion is not None:
                completion(result)
        except BaseException as exc:
            if replacement is not None:
                try:
                    if not database_closed:
                        self._coordinator.close_database()
                        database_closed = True
                    self._rollback(replacement)
                    self._coordinator.reopen_database()
                    database_closed = False
                except Exception as rollback_exc:
                    rollback_failed = True
                    raise RestoreRollbackError(
                        "The restore failed and the previous state could not be restored."
                    ) from rollback_exc
            elif database_closed:
                try:
                    self._coordinator.reopen_database()
                except Exception as reopen_exc:
                    raise RestoreRollbackError(
                        "The restore failed while the database was closed."
                    ) from reopen_exc
            if isinstance(exc, (KeyboardInterrupt, SystemExit)):
                raise
            if isinstance(exc, RestoreError):
                raise
            raise RestoreError("The restore could not be completed safely.") from exc
        finally:
            if replacement is not None and pre_restore_backup is not None and not rollback_failed:
                self._cleanup_replacement(replacement)
            if staging_root is not None:
                _remove_tree(staging_root)
            try:
                if paused:
                    self._coordinator.resume_worker()
            finally:
                if entered:
                    self._coordinator.exit_maintenance()

        if result is None:
            raise RestoreError("The restore result was not created.")
        return result

    def _resolve_archive(self, archive_path: str | os.PathLike[str]) -> Path:
        try:
            candidate = Path(archive_path)
        except TypeError as exc:
            raise RestoreValidationError("The restore archive path is invalid.") from exc
        if not candidate.is_absolute():
            candidate = self._directories.root / candidate
        if candidate.is_symlink():
            raise RestoreValidationError("The restore archive must not be a symbolic link.")
        try:
            resolved = candidate.resolve(strict=True)
        except OSError as exc:
            raise RestoreValidationError("The restore archive could not be resolved.") from exc
        backups_root = self._directories.backups.resolve(strict=False)
        if (
            resolved.is_symlink()
            or not resolved.is_file()
            or not resolved.is_relative_to(backups_root)
        ):
            raise RestoreValidationError("The restore archive must be a regular file in backups.")
        return resolved

    def _verify_source(self, archive_path: Path) -> BackupVerificationResult:
        try:
            verified = verify_backup_archive(archive_path, data_root=self._directories.root)
        except BackupVerificationError as exc:
            raise RestoreValidationError("The restore archive failed validation.") from exc
        if verified.manifest.backup_type not in {
            BackupType.DATABASE_ONLY,
            BackupType.METADATA,
            BackupType.FULL_PROJECTS,
        }:
            raise RestoreValidationError("The restore archive type is not restorable.")
        return verified

    def _stage_archive(self, archive_path: Path, verified: BackupVerificationResult) -> Path:
        staging_root = Path(
            tempfile.mkdtemp(prefix="transloka-restore-", dir=self._directories.temporary)
        )
        try:
            with ZipFile(archive_path, mode="r") as archive:
                for relative_path in verified.manifest.included_content:
                    if relative_path in {_MANIFEST_FILENAME, _WARNING_FILENAME}:
                        continue
                    if not _is_restore_path(relative_path, verified.manifest.backup_type):
                        raise RestoreValidationError(
                            "The restore archive contains unsupported application data."
                        )
                    target = _safe_child(staging_root, relative_path)
                    target.parent.mkdir(parents=True, exist_ok=True)
                    with (
                        archive.open(relative_path, mode="r") as source,
                        target.open("wb") as output,
                    ):
                        shutil.copyfileobj(source, output)
                        output.flush()
                        os.fsync(output.fileno())
            if not (staging_root / "database" / DATABASE_FILENAME).is_file():
                raise RestoreValidationError("The restore archive has no application database.")
            if verified.manifest.backup_type is BackupType.FULL_PROJECTS:
                (staging_root / "projects").mkdir(parents=True, exist_ok=True)
            return staging_root
        except RestoreError:
            _remove_tree(staging_root)
            raise
        except (OSError, KeyError, ValueError) as exc:
            _remove_tree(staging_root)
            raise RestoreValidationError("The restore archive could not be staged safely.") from exc

    def _replace_active_state(
        self,
        staging_root: Path,
        backup_type: BackupType,
        *,
        restore_files: bool,
    ) -> _ReplacementState:
        rollback_root = Path(
            tempfile.mkdtemp(prefix="transloka-rollback-", dir=self._directories.temporary)
        )
        state = _ReplacementState(rollback_root=rollback_root)
        try:
            database_stage = staging_root / "database" / DATABASE_FILENAME
            state.database = _replace_file(
                database_stage,
                self._directories.database / DATABASE_FILENAME,
                rollback_root / "database" / DATABASE_FILENAME,
            )
            queue_stage = staging_root / "database" / QUEUE_DATABASE_FILENAME
            if queue_stage.is_file():
                state.queue = _replace_file(
                    queue_stage,
                    self._directories.database / QUEUE_DATABASE_FILENAME,
                    rollback_root / "database" / QUEUE_DATABASE_FILENAME,
                )
            staged_projects = staging_root / "projects"
            if restore_files and backup_type is BackupType.FULL_PROJECTS:
                state.projects = _replace_directory(
                    staged_projects,
                    self._directories.projects,
                    rollback_root / "projects",
                )
            elif restore_files and backup_type is BackupType.METADATA:
                state.metadata = _replace_metadata_files(
                    staged_projects,
                    self._directories.projects,
                    rollback_root / "projects",
                )
            return state
        except BaseException:
            try:
                self._rollback(state)
            except Exception as rollback_exc:
                raise RestoreRollbackError(
                    "The restore failed during replacement and rollback was incomplete."
                ) from rollback_exc
            _remove_tree(rollback_root)
            raise

    def _rollback(self, state: _ReplacementState) -> None:
        for target, backup, created in reversed(state.metadata):
            if created:
                _remove_file(target)
            if backup is not None and backup.exists():
                target.parent.mkdir(parents=True, exist_ok=True)
                os.replace(backup, target)
        if state.projects is not None:
            _rollback_directory(state.projects)
        if state.queue is not None:
            _rollback_file(state.queue)
        if state.database is not None:
            _rollback_file(state.database)

    def _cleanup_replacement(self, state: _ReplacementState) -> None:
        _remove_tree(state.rollback_root)


@dataclass
class _ReplacementState:
    rollback_root: Path
    database: tuple[Path, Path, bool] | None = None
    queue: tuple[Path, Path, bool] | None = None
    projects: tuple[Path, Path, bool] | None = None
    metadata: list[tuple[Path, Path | None, bool]] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.metadata is None:
            self.metadata = []


def _replace_file(stage: Path, target: Path, rollback: Path) -> tuple[Path, Path, bool]:
    _validate_target_file(target)
    rollback.parent.mkdir(parents=True, exist_ok=True)
    existed = target.exists()
    if existed:
        os.replace(target, rollback)
    target.parent.mkdir(parents=True, exist_ok=True)
    os.replace(stage, target)
    _remove_file(target.with_name(f"{target.name}-wal"))
    _remove_file(target.with_name(f"{target.name}-shm"))
    return target, rollback, existed


def _replace_directory(stage: Path, target: Path, rollback: Path) -> tuple[Path, Path, bool]:
    if target.exists() and (target.is_symlink() or not target.is_dir()):
        raise RestoreValidationError("The active projects directory is unsafe.")
    rollback.parent.mkdir(parents=True, exist_ok=True)
    existed = target.exists()
    if existed:
        os.replace(target, rollback)
    os.replace(stage, target)
    return target, rollback, existed


def _replace_metadata_files(
    stage_root: Path,
    target_root: Path,
    rollback_root: Path,
) -> list[tuple[Path, Path | None, bool]]:
    replacements: list[tuple[Path, Path | None, bool]] = []
    for stage in sorted(path for path in stage_root.rglob("*") if path.is_file()):
        relative = stage.relative_to(stage_root)
        target = target_root / relative
        if target.exists() and (target.is_symlink() or not target.is_file()):
            raise RestoreValidationError("The active metadata path is unsafe.")
        backup = rollback_root / relative if target.exists() else None
        if backup is not None:
            backup.parent.mkdir(parents=True, exist_ok=True)
            os.replace(target, backup)
        target.parent.mkdir(parents=True, exist_ok=True)
        os.replace(stage, target)
        replacements.append((target, backup, backup is None))
    return replacements


def _rollback_file(state: tuple[Path, Path, bool]) -> None:
    target, backup, existed = state
    _remove_file(target)
    if existed and backup.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        os.replace(backup, target)


def _rollback_directory(state: tuple[Path, Path, bool]) -> None:
    target, backup, existed = state
    _remove_tree(target)
    if existed and backup.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        os.replace(backup, target)


def _validate_target_file(target: Path) -> None:
    if target.exists() and (target.is_symlink() or not target.is_file()):
        raise RestoreValidationError("The active database path is unsafe.")


def _is_restore_path(relative_path: str, backup_type: BackupType) -> bool:
    if relative_path in {
        f"database/{DATABASE_FILENAME}",
        f"database/{QUEUE_DATABASE_FILENAME}",
    }:
        return True
    if not relative_path.startswith("projects/"):
        return False
    if backup_type is BackupType.FULL_PROJECTS:
        return True
    if backup_type is BackupType.METADATA:
        return relative_path.rsplit("/", 1)[-1].casefold() in {
            "manifest.json",
            "metadata.json",
            "project.json",
        }
    return False


def _safe_child(root: Path, relative_path: str) -> Path:
    candidate = (root / Path(*relative_path.split("/"))).resolve(strict=False)
    if not candidate.is_relative_to(root.resolve(strict=True)):
        raise RestoreValidationError("The restore archive path escapes staging.")
    return candidate


def _managed_file(root: Path, storage_key: str) -> Path:
    if (
        not storage_key
        or not storage_key.isprintable()
        or "\\" in storage_key
        or ":" in storage_key
    ):
        raise RestoreError("A restored managed-file key is unsafe.")
    parts = storage_key.split("/")
    if any(not part or part in {".", ".."} for part in parts):
        raise RestoreError("A restored managed-file key is unsafe.")
    candidate = root.joinpath(*parts)
    current = root
    for part in parts:
        current /= part
        if current.is_symlink():
            raise RestoreError("A restored managed-file path is unsafe.")
    try:
        resolved = candidate.resolve(strict=True)
    except OSError as exc:
        raise RestoreError("A restored managed file is unavailable.") from exc
    if not resolved.is_relative_to(root.resolve(strict=True)) or not resolved.is_file():
        raise RestoreError("A restored managed file is unavailable.")
    return resolved


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _noop() -> None:
    return None


def _lock_stream(stream: BinaryIO) -> None:
    if os.name == "nt":
        import msvcrt

        msvcrt.locking(stream.fileno(), msvcrt.LK_NBLCK, 1)
        return
    fcntl = cast(Any, importlib.import_module("fcntl"))
    fcntl.flock(stream.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)


def _unlock_stream(stream: BinaryIO) -> None:
    if os.name == "nt":
        import msvcrt

        msvcrt.locking(stream.fileno(), msvcrt.LK_UNLCK, 1)
        return
    fcntl = cast(Any, importlib.import_module("fcntl"))
    fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def _remove_file(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except OSError:
        pass


def _remove_tree(path: Path | None) -> None:
    if path is None:
        return
    try:
        shutil.rmtree(path, ignore_errors=True)
    except OSError:
        pass


__all__ = [
    "APPLICATION_MUTATION_LOCK_FILENAME",
    "ApplicationMutationLock",
    "FileRestoreCoordinator",
    "MAINTENANCE_MARKER_FILENAME",
    "RestoreBusyError",
    "RestoreConfirmationError",
    "RestoreCoordinator",
    "RestoreError",
    "RestoreResult",
    "RestoreRollbackError",
    "RestoreValidationError",
    "RestoreWorkflow",
    "WORKER_EXECUTION_LOCK_FILENAME",
    "WorkerExecutionLock",
]
