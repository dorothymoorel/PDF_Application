"""Integrity, orphan scanning, cleanup, and vacuum services."""

from __future__ import annotations

import hashlib
import os
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from transloka_core.backup.restore import FileRestoreCoordinator, RestoreBusyError
from transloka_core.database import DATABASE_FILENAME
from transloka_core.database.models import documents as _documents_model  # noqa: F401
from transloka_core.database.models import projects as _projects_model  # noqa: F401
from transloka_core.database.models.files import FileRole, FileStatus, StoredFile
from transloka_core.database.models.jobs import ApplicationJob, JobStatus
from transloka_core.storage import LocalDataDirectories


class MaintenanceError(RuntimeError):
    """Raised when a maintenance operation cannot be completed safely."""


class MaintenanceBusyError(MaintenanceError):
    """Raised when a maintenance operation conflicts with an active job."""


class MaintenanceOperation(StrEnum):
    DATABASE_INTEGRITY_CHECK = "DATABASE_INTEGRITY_CHECK"
    FILE_INTEGRITY_CHECK = "FILE_INTEGRITY_CHECK"
    ORPHAN_FILE_SCAN = "ORPHAN_FILE_SCAN"
    TEMP_CLEANUP = "TEMP_CLEANUP"
    CACHE_CLEANUP = "CACHE_CLEANUP"
    VACUUM = "VACUUM"


@dataclass(frozen=True, slots=True)
class MaintenanceReport:
    """Stable, path-redacted result returned by every maintenance action."""

    operation: MaintenanceOperation
    healthy: bool
    dry_run: bool
    checked_count: int = 0
    issue_count: int = 0
    issues: tuple[str, ...] = ()
    orphans: tuple[str, ...] = ()
    candidates: tuple[str, ...] = ()
    deleted: tuple[str, ...] = ()
    protected: tuple[str, ...] = ()


_ACTIVE_JOB_STATUSES = {
    JobStatus.CREATED.value,
    JobStatus.QUEUED.value,
    JobStatus.RUNNING.value,
    JobStatus.RETRYING.value,
    JobStatus.CANCELLATION_REQUESTED.value,
}


class MaintenanceService:
    """Run bounded maintenance actions against one local data root."""

    def __init__(
        self,
        directories: LocalDataDirectories,
        session_factory: sessionmaker[Session],
        *,
        current_job_id: str | None = None,
    ) -> None:
        if not callable(session_factory):
            raise TypeError("The maintenance session factory is invalid.")
        self._directories = directories
        self._session_factory = session_factory
        self._current_job_id = current_job_id
        self._root = directories.root.resolve(strict=False)

    def database_integrity_check(self) -> MaintenanceReport:
        issues: list[str] = []
        database = self._database_path()
        if not database.is_file() or database.is_symlink():
            issues.append("database/transloka.db")
            return self._report(
                MaintenanceOperation.DATABASE_INTEGRITY_CHECK,
                issues=issues,
            )

        try:
            with sqlite3.connect(f"{database.as_uri()}?mode=ro", uri=True) as connection:
                integrity = tuple(connection.execute("PRAGMA integrity_check"))
                if integrity != (("ok",),):
                    issues.extend(str(row[0]) for row in integrity)
                foreign_keys = tuple(connection.execute("PRAGMA foreign_key_check"))
                if foreign_keys:
                    issues.append("foreign_key_violations")
        except sqlite3.Error:
            issues.append("database_could_not_be_read_safely")

        return self._report(
            MaintenanceOperation.DATABASE_INTEGRITY_CHECK,
            issues=issues,
        )

    def file_integrity_check(self) -> MaintenanceReport:
        issues: list[str] = []
        checked = 0
        for row in self._stored_files():
            if row.status == FileStatus.DELETED.value:
                continue
            checked += 1
            path = self._safe_managed_path(row.storage_key)
            if path is None or not path.is_file() or path.is_symlink():
                issues.append(row.storage_key)
                continue
            try:
                if path.stat().st_size != row.size_bytes or _sha256(path) != row.checksum_sha256:
                    issues.append(row.storage_key)
            except OSError:
                issues.append(row.storage_key)

        return self._report(
            MaintenanceOperation.FILE_INTEGRITY_CHECK,
            checked_count=checked,
            issues=issues,
        )

    def orphan_file_scan(self) -> MaintenanceReport:
        referenced = {
            row.storage_key
            for row in self._stored_files()
            if row.status != FileStatus.DELETED.value
        }
        orphans = tuple(
            sorted(
                relative
                for root in self._managed_roots()
                for relative in _files_under(root, self._root)
                if relative not in referenced
            )
        )
        return self._report(
            MaintenanceOperation.ORPHAN_FILE_SCAN,
            checked_count=len(referenced),
            orphans=orphans,
        )

    def temp_cleanup(self, *, older_than_days: int = 7, dry_run: bool = True) -> MaintenanceReport:
        return self._cleanup(
            MaintenanceOperation.TEMP_CLEANUP,
            self._directories.temporary,
            older_than_days=older_than_days,
            dry_run=dry_run,
        )

    def cache_cleanup(self, *, older_than_days: int = 7, dry_run: bool = True) -> MaintenanceReport:
        return self._cleanup(
            MaintenanceOperation.CACHE_CLEANUP,
            self._directories.cache,
            older_than_days=older_than_days,
            dry_run=dry_run,
        )

    def vacuum(self, *, dry_run: bool = True) -> MaintenanceReport:
        self._raise_if_active_jobs()
        if dry_run:
            return self._report(MaintenanceOperation.VACUUM, dry_run=True)

        with self._maintenance_lock():
            self._raise_if_active_jobs()
            try:
                with sqlite3.connect(self._database_path()) as connection:
                    connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                    connection.execute("VACUUM")
            except sqlite3.Error as exc:
                raise MaintenanceError("The database could not be vacuumed safely.") from exc
        return self._report(MaintenanceOperation.VACUUM)

    def _cleanup(
        self,
        operation: MaintenanceOperation,
        root: Path,
        *,
        older_than_days: int,
        dry_run: bool,
    ) -> MaintenanceReport:
        if isinstance(older_than_days, bool) or older_than_days < 1:
            raise ValueError("The cleanup age must be a positive number of days.")
        if not isinstance(dry_run, bool):
            raise ValueError("The dry-run flag must be a boolean.")

        protected = self._protected_storage_keys()
        cutoff = datetime.now(UTC).timestamp() - timedelta(days=older_than_days).total_seconds()
        candidates = self._cleanup_candidates(root, cutoff, protected)
        protected_candidates = self._protected_candidates(root, cutoff, protected)
        if dry_run:
            return self._report(
                operation,
                dry_run=True,
                candidates=candidates,
                protected=protected_candidates,
            )

        self._raise_if_active_jobs()
        with self._maintenance_lock():
            self._raise_if_active_jobs()
            deleted: list[str] = []
            for relative in self._cleanup_candidates(root, cutoff, protected):
                path = self._root / Path(*relative.split("/"))
                try:
                    path.unlink()
                except OSError as exc:
                    raise MaintenanceError(
                        "A cleanup candidate could not be removed safely."
                    ) from exc
                deleted.append(relative)
        return self._report(
            operation,
            candidates=candidates,
            deleted=tuple(deleted),
            protected=protected_candidates,
        )

    def _stored_files(self) -> list[StoredFile]:
        with self._session_factory() as session:
            return list(session.scalars(select(StoredFile)))

    def _protected_storage_keys(self) -> set[str]:
        return {
            row.storage_key
            for row in self._stored_files()
            if row.status != FileStatus.DELETED.value
            and row.file_role in {FileRole.ORIGINAL.value, FileRole.EXPORT.value}
        }

    def _raise_if_active_jobs(self) -> None:
        statement = select(ApplicationJob.id).where(ApplicationJob.status.in_(_ACTIVE_JOB_STATUSES))
        if self._current_job_id is not None:
            statement = statement.where(ApplicationJob.id != self._current_job_id)
        with self._session_factory() as session:
            active = session.scalar(statement.limit(1))
        if active is not None:
            raise MaintenanceBusyError("Maintenance is blocked by an active application job.")

    def _cleanup_candidates(
        self,
        root: Path,
        cutoff: float,
        protected: set[str],
    ) -> tuple[str, ...]:
        candidates: list[str] = []
        for relative in _files_under(root, self._root):
            if relative in protected:
                continue
            path = self._root / Path(*relative.split("/"))
            try:
                if path.stat().st_mtime < cutoff:
                    candidates.append(relative)
            except OSError:
                continue
        return tuple(sorted(candidates))

    def _protected_candidates(
        self,
        root: Path,
        cutoff: float,
        protected: set[str],
    ) -> tuple[str, ...]:
        return tuple(
            sorted(
                relative
                for relative in _files_under(root, self._root)
                if relative in protected
                and _is_older_than(self._root / Path(*relative.split("/")), cutoff)
            )
        )

    @contextmanager
    def _maintenance_lock(self) -> Iterator[None]:
        coordinator = FileRestoreCoordinator(self._directories)
        try:
            coordinator.enter_maintenance()
        except RestoreBusyError as exc:
            raise MaintenanceBusyError("Maintenance is blocked by an active restore.") from exc
        try:
            coordinator.pause_worker()
            yield
        finally:
            coordinator.resume_worker()
            coordinator.exit_maintenance()

    def _database_path(self) -> Path:
        database = self._directories.database / DATABASE_FILENAME
        if database.parent.resolve(strict=False) != (self._root / "database").resolve(strict=False):
            raise MaintenanceError("The maintenance database path is inconsistent.")
        return database

    def _safe_managed_path(self, storage_key: str) -> Path | None:
        if (
            not storage_key
            or not storage_key.isprintable()
            or "\\" in storage_key
            or ":" in storage_key
        ):
            return None
        parts = storage_key.split("/")
        if any(not part or part in {".", ".."} for part in parts):
            return None
        candidate = self._root.joinpath(*parts)
        current = self._root
        for part in parts:
            current /= part
            if current.is_symlink():
                return None
        try:
            resolved = candidate.resolve(strict=False)
        except OSError:
            return None
        if not resolved.is_relative_to(self._root):
            return None
        return resolved

    def _managed_roots(self) -> tuple[Path, ...]:
        return (
            self._directories.projects,
            self._directories.cache,
            self._directories.backups,
            self._directories.temporary,
        )

    @staticmethod
    def _report(
        operation: MaintenanceOperation,
        *,
        dry_run: bool = False,
        checked_count: int = 0,
        issues: list[str] | tuple[str, ...] = (),
        orphans: tuple[str, ...] = (),
        candidates: tuple[str, ...] = (),
        deleted: tuple[str, ...] = (),
        protected: tuple[str, ...] = (),
    ) -> MaintenanceReport:
        issue_tuple = tuple(issues)
        return MaintenanceReport(
            operation=operation,
            healthy=not issue_tuple,
            dry_run=dry_run,
            checked_count=checked_count,
            issue_count=len(issue_tuple),
            issues=issue_tuple,
            orphans=orphans,
            candidates=candidates,
            deleted=deleted,
            protected=protected,
        )


def _files_under(root: Path, repository_root: Path) -> Iterator[str]:
    if not root.is_dir() or root.is_symlink():
        return
    for current, directories, filenames in os.walk(root, followlinks=False):
        current_path = Path(current)
        directories[:] = [name for name in directories if not (current_path / name).is_symlink()]
        for filename in filenames:
            path = current_path / filename
            try:
                relative = path.resolve(strict=False).relative_to(repository_root).as_posix()
            except ValueError:
                continue
            if path.is_symlink():
                continue
            yield relative


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _is_older_than(path: Path, cutoff: float) -> bool:
    try:
        return path.stat().st_mtime < cutoff
    except OSError:
        return False


__all__ = [
    "MaintenanceBusyError",
    "MaintenanceError",
    "MaintenanceOperation",
    "MaintenanceReport",
    "MaintenanceService",
]
