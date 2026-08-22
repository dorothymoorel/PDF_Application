import hashlib
import os
import sqlite3
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy.orm import Session, sessionmaker
from transloka_core.backup.restore import FileRestoreCoordinator
from transloka_core.database import create_session_factory, create_sqlite_engine, transaction_scope
from transloka_core.database.models.files import FileRole, FileStatus, StoredFile
from transloka_core.database.models.jobs import ApplicationJob, JobStatus, JobType
from transloka_core.maintenance import MaintenanceBusyError, MaintenanceService
from transloka_core.storage import LocalDataDirectories, resolve_local_data_directories

REPOSITORY_ROOT = Path(__file__).parents[3]
ALEMBIC_CONFIGURATION = REPOSITORY_ROOT / "alembic.ini"
CREATED_AT = "2026-08-22T00:00:00.000Z"


@pytest.fixture
def maintenance_data(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> Iterator[tuple[MaintenanceService, LocalDataDirectories, sessionmaker[Session]]]:
    root = tmp_path / "maintenance data"
    monkeypatch.setenv("TRANSLOKA_DATA_DIR", str(root))
    command.upgrade(Config(str(ALEMBIC_CONFIGURATION)), "head")
    directories = resolve_local_data_directories(root)
    engine = create_sqlite_engine(directories)
    factory = create_session_factory(engine)
    try:
        yield MaintenanceService(directories, factory), directories, factory
    finally:
        engine.dispose()


def _record_file(
    factory: sessionmaker[Session],
    directories: LocalDataDirectories,
    *,
    identifier: str,
    storage_key: str,
    role: FileRole = FileRole.PAGE_RENDER,
    content: bytes = b"managed content",
) -> Path:
    path = directories.root / storage_key
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    checksum = hashlib.sha256(content).hexdigest()
    with transaction_scope(factory) as session:
        session.add(
            StoredFile(
                id=identifier,
                project_id=None,
                document_id=None,
                file_role=role.value,
                storage_key=storage_key,
                original_filename=path.name,
                safe_filename=path.name,
                mime_type="application/octet-stream",
                size_bytes=len(content),
                checksum_sha256=checksum,
                is_immutable=1 if role is FileRole.ORIGINAL else 0,
                status=FileStatus.VALIDATED.value,
                metadata_json=None,
                created_at=CREATED_AT,
                deleted_at=None,
            )
        )
    return path


def _age(path: Path, days: int = 14) -> None:
    timestamp = (datetime.now(UTC) - timedelta(days=days)).timestamp()
    os.utime(path, (timestamp, timestamp))


def test_database_integrity_check_reports_healthy_database(
    maintenance_data: tuple[MaintenanceService, LocalDataDirectories, sessionmaker[Session]],
) -> None:
    service, _directories, _factory = maintenance_data

    report = service.database_integrity_check()

    assert report.healthy is True
    assert report.operation == "DATABASE_INTEGRITY_CHECK"
    assert report.issues == ()


def test_file_integrity_check_reports_missing_record(
    maintenance_data: tuple[MaintenanceService, LocalDataDirectories, sessionmaker[Session]],
) -> None:
    service, directories, factory = maintenance_data
    _record_file(
        factory,
        directories,
        identifier="fil_00000000-0000-4000-8000-000000000001",
        storage_key="projects/missing/source.pdf",
    ).unlink()

    report = service.file_integrity_check()

    assert report.healthy is False
    assert "projects/missing/source.pdf" in report.issues


def test_orphan_scan_reports_unreferenced_file(
    maintenance_data: tuple[MaintenanceService, LocalDataDirectories, sessionmaker[Session]],
) -> None:
    service, directories, _factory = maintenance_data
    orphan = directories.cache / "orphan.bin"
    orphan.write_bytes(b"orphan")

    report = service.orphan_file_scan()

    assert report.orphans == ("cache/orphan.bin",)


def test_cleanup_dry_run_and_protected_files(
    maintenance_data: tuple[MaintenanceService, LocalDataDirectories, sessionmaker[Session]],
) -> None:
    service, directories, factory = maintenance_data
    original = _record_file(
        factory,
        directories,
        identifier="fil_00000000-0000-4000-8000-000000000002",
        storage_key="projects/protected/original.pdf",
        role=FileRole.ORIGINAL,
    )
    export = _record_file(
        factory,
        directories,
        identifier="fil_00000000-0000-4000-8000-000000000003",
        storage_key="cache/protected/export.pdf",
        role=FileRole.EXPORT,
    )
    _age(export)
    temporary = directories.temporary / "old.tmp"
    temporary.write_bytes(b"temporary")
    _age(temporary)

    preview = service.temp_cleanup(older_than_days=7, dry_run=True)
    assert preview.dry_run is True
    assert preview.deleted == ()
    assert preview.candidates == ("temp/old.tmp",)
    assert original.is_file()
    assert export.is_file()

    cache_preview = service.cache_cleanup(older_than_days=7, dry_run=True)
    assert cache_preview.protected == ("cache/protected/export.pdf",)

    applied = service.temp_cleanup(older_than_days=7, dry_run=False)
    assert applied.deleted == ("temp/old.tmp",)
    assert not temporary.exists()
    assert original.is_file()
    assert export.is_file()


def test_vacuum_is_blocked_by_active_heavy_job(
    maintenance_data: tuple[MaintenanceService, LocalDataDirectories, sessionmaker[Session]],
) -> None:
    service, _directories, factory = maintenance_data
    with transaction_scope(factory) as session:
        session.add(
            ApplicationJob(
                id="job_00000000-0000-4000-8000-000000000001",
                project_id=None,
                document_id=None,
                parent_job_id=None,
                job_type=JobType.TRANSLATE_DOCUMENT.value,
                queue_name="test",
                status=JobStatus.RUNNING.value,
                progress=0.4,
                current_stage="TRANSLATING",
                idempotency_key="maintenance-active-job",
                payload_json="{}",
                result_json=None,
                retry_count=0,
                max_retries=3,
                error_code=None,
                error_message=None,
                created_at=CREATED_AT,
                queued_at=CREATED_AT,
                started_at=CREATED_AT,
                completed_at=None,
                cancelled_at=None,
                heartbeat_at=CREATED_AT,
            )
        )

    with pytest.raises(MaintenanceBusyError):
        service.vacuum(dry_run=False)


def test_database_vacuum_dry_run_does_not_modify_database(
    maintenance_data: tuple[MaintenanceService, LocalDataDirectories, sessionmaker[Session]],
) -> None:
    service, directories, _factory = maintenance_data
    database = directories.database / "transloka.db"
    before = database.stat().st_size

    report = service.vacuum(dry_run=True)

    assert report.dry_run is True
    assert report.deleted == ()
    assert database.stat().st_size == before
    with sqlite3.connect(database) as connection:
        assert connection.execute("PRAGMA integrity_check").fetchone() == ("ok",)


def test_cleanup_is_blocked_when_restore_maintenance_is_active(
    maintenance_data: tuple[MaintenanceService, LocalDataDirectories, sessionmaker[Session]],
) -> None:
    service, directories, _factory = maintenance_data
    coordinator = FileRestoreCoordinator(directories)
    coordinator.enter_maintenance()
    try:
        with pytest.raises(MaintenanceBusyError):
            service.temp_cleanup(dry_run=False)
    finally:
        coordinator.exit_maintenance()
