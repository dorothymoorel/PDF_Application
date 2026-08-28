# mypy: ignore-errors
import json
import logging
from pathlib import Path
from uuid import UUID

import pytest
from alembic import command as alembic_command
from alembic.config import Config
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker
from transloka_core.backup.verification import BackupVerificationError, verify_backup_archive
from transloka_core.database import create_session_factory, create_sqlite_engine, transaction_scope
from transloka_core.database.models.backups import Backup, BackupStatus
from transloka_core.database.models.documents import Document  # noqa: F401
from transloka_core.database.models.files import FileRole, FileStatus, StoredFile
from transloka_core.database.models.jobs import (
    ApplicationJob,
    JobAttempt,
    JobAttemptStatus,
    JobStatus,
    JobType,
)
from transloka_core.database.models.projects import Project  # noqa: F401
from transloka_core.jobs.cancellation import JobCancellationService
from transloka_core.storage import resolve_local_data_directories
from transloka_worker.backup import (
    BackupCommand,
    DatabaseBackupRequestLoader,
    ProductionBackupJobRunner,
)

REPOSITORY_ROOT = Path(__file__).parents[3]
ALEMBIC_CONFIGURATION = REPOSITORY_ROOT / "alembic.ini"


def _id(prefix: str, value: int) -> str:
    return f"{prefix}{UUID(int=value)}"


JOB_ID = _id("job_", 200)
JOB_2_ID = _id("job_", 201)


@pytest.fixture
def backup_runtime_setup(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    root = tmp_path / "backup runtime"
    monkeypatch.setenv("TRANSLOKA_DATA_DIR", str(root))
    alembic_command.upgrade(Config(str(ALEMBIC_CONFIGURATION)), "head")
    directories = resolve_local_data_directories(root)
    engine = create_sqlite_engine(directories)
    factory = create_session_factory(engine)
    # create a job
    _create_job(factory, JOB_ID, "METADATA")
    loader = DatabaseBackupRequestLoader(factory)
    runner = ProductionBackupJobRunner(
        loader, factory, directories, worker_identifier="test-worker"
    )
    yield runner, factory, directories, engine, root
    engine.dispose()


def _create_job(factory: sessionmaker[Session], job_id: str, backup_type: str):
    cmd = BackupCommand(backup_type=backup_type)
    payload = json.dumps(cmd.to_payload(), sort_keys=True, separators=(",", ":"))
    with transaction_scope(factory) as session:
        session.add(
            ApplicationJob(
                id=job_id,
                project_id=None,
                document_id=None,
                parent_job_id=None,
                job_type=JobType.BACKUP_DATABASE.value,
                queue_name="transloka",
                status=JobStatus.QUEUED.value,
                progress=0.0,
                current_stage="QUEUED",
                idempotency_key=f"backup-runtime-{job_id}",
                payload_json=payload,
                result_json=None,
                retry_count=0,
                max_retries=3,
                error_code=None,
                error_message=None,
                created_at="2026-08-27T00:00:00.000Z",
                queued_at="2026-08-27T00:00:00.000Z",
                started_at=None,
                completed_at=None,
                cancelled_at=None,
                heartbeat_at=None,
            )
        )


def test_backup_runner_creates_validated_stored_file_and_backup_and_completes_job(
    backup_runtime_setup,
) -> None:
    runner, factory, directories, engine, root = backup_runtime_setup
    result = runner.run(JOB_ID)
    assert result.status == JobStatus.COMPLETED
    assert result.backup_id is not None and result.backup_id.startswith("bkp_")
    with factory() as session:
        stored = session.scalar(
            session.query(StoredFile)
            .filter(StoredFile.file_role == FileRole.BACKUP.value)
            .statement
        )  # type: ignore
        stored = session.scalar(
            select(StoredFile).where(StoredFile.file_role == FileRole.BACKUP.value)
        )
        assert stored is not None
        assert stored.status == FileStatus.VALIDATED.value
        assert stored.is_immutable == 1
        assert stored.storage_key.startswith("backups/")
        backup = session.get(Backup, result.backup_id)
        assert backup is not None
        assert backup.status == BackupStatus.COMPLETED.value
        assert backup.file_id == stored.id
        assert backup.size_bytes is not None and backup.checksum_sha256 is not None
        job = session.get(ApplicationJob, JOB_ID)
        assert job is not None
        assert job.status == JobStatus.COMPLETED.value
        assert job.progress == 1.0
        assert json.loads(job.result_json or "null")["schema"] == "transloka.backup.job.v1"
        attempt = session.scalar(select(JobAttempt).where(JobAttempt.job_id == JOB_ID))
        assert attempt is not None
        assert attempt.status == JobAttemptStatus.COMPLETED.value
        # verify archive
        v = verify_backup_archive(directories.root / stored.storage_key, data_root=directories.root)
        assert v.manifest.backup_type.value == "METADATA"
        assert "backup-warning.txt" in v.verified_files


def test_backup_runner_fails_on_insufficient_disk(
    backup_runtime_setup, monkeypatch: pytest.MonkeyPatch
) -> None:
    from transloka_core.backup.database import InsufficientBackupSpaceError

    runner, factory, directories, engine, root = backup_runtime_setup
    monkeypatch.setattr("transloka_core.backup.archive.get_free_disk_bytes", lambda _d: 0)
    # also need to patch backup.py's imported get_free_disk_bytes? It's imported in archive, not in runner. Patching archive should be enough.
    # But runner imports create_backup from archive, which internally checks get_free_disk_bytes.
    with pytest.raises(InsufficientBackupSpaceError):
        runner.run(JOB_ID)
    with factory() as session:
        job = session.get(ApplicationJob, JOB_ID)
        assert job is not None
        assert job.status == JobStatus.FAILED.value
        assert job.error_code == "INSUFFICIENT_DISK"
    # no backup file left
    assert list(directories.backups.iterdir()) == [] or all(
        not p.is_file() for p in directories.backups.iterdir()
    )


def test_backup_runner_cancellation_before_archive_leaves_no_backup_row(
    backup_runtime_setup,
) -> None:
    runner, factory, directories, engine, root = backup_runtime_setup
    # request cancellation before run
    JobCancellationService(factory, directories.temporary).request(
        JOB_ID, reason="test cancel before"
    )
    result = runner.run(JOB_ID)
    assert result.status == JobStatus.CANCELLED
    with factory() as session:
        from sqlalchemy import select

        backup = session.scalar(select(Backup))
        assert backup is None
        job = session.get(ApplicationJob, JOB_ID)
        assert job is not None
        assert job.status == JobStatus.CANCELLED.value
        attempt = session.scalar(select(JobAttempt).where(JobAttempt.job_id == JOB_ID))
        assert attempt is not None
        assert attempt.status == JobAttemptStatus.CANCELLED.value


def test_backup_runner_cancellation_during_archive_still_publishes_safely(
    backup_runtime_setup, monkeypatch: pytest.MonkeyPatch
) -> None:
    runner, factory, directories, engine, root = backup_runtime_setup
    # Simulate cancellation requested after create_backup entered: we set flag after runner starts but before publish?
    # Since checkpoint is only before create_backup, this should still publish.
    # We can monkeypatch JobCancellationService.checkpoint to return False first, then True after create_backup, but our runner only checks before.
    # So we simulate by not requesting before, and ensure runner still completes.
    # To test during-archive still publishes, we request cancellation after runner has started but before it checks second time (there is no second check).
    # Our runner only checks before create_backup, so requesting after that should not affect.
    # We'll request after a short delay via monkeypatching create_backup to request cancellation mid-way
    original_create = __import__(
        "transloka_core.backup.archive", fromlist=["create_backup"]
    ).create_backup

    def fake_create(*args, **kwargs):
        # request cancellation during create_backup
        try:
            JobCancellationService(factory, directories.temporary).request(JOB_ID, reason="during")
        except Exception:
            pass
        return original_create(*args, **kwargs)

    monkeypatch.setattr("transloka_worker.backup.create_backup", fake_create)
    result = runner.run(JOB_ID)
    # Since checkpoint is before only, this should still COMPLETE, not CANCELLED
    assert result.status == JobStatus.COMPLETED
    with factory() as session:
        from sqlalchemy import select

        backup = session.scalar(select(Backup))
        assert backup is not None
        assert backup.status == BackupStatus.COMPLETED.value


def test_backup_runner_exact_once_on_already_completed_does_not_create_second_archive(
    backup_runtime_setup,
) -> None:
    runner, factory, directories, engine, root = backup_runtime_setup
    first = runner.run(JOB_ID)
    assert first.status == JobStatus.COMPLETED
    from sqlalchemy import select

    with factory() as session:
        count_before = len(session.scalars(select(Backup)).all())
        count_files_before = len(list(directories.backups.iterdir()))
    second = runner.run(JOB_ID)
    assert second.status == JobStatus.COMPLETED
    assert second.backup_id == first.backup_id
    with factory() as session:
        count_after = len(session.scalars(select(Backup)).all())
        count_files_after = len(list(directories.backups.iterdir()))
    assert count_after == count_before
    assert count_files_after == count_files_before


def test_backup_runner_verification_failure_deletes_unreferenced_archive(
    backup_runtime_setup, monkeypatch: pytest.MonkeyPatch, caplog
) -> None:
    runner, factory, directories, engine, root = backup_runtime_setup
    monkeypatch.setattr(
        "transloka_worker.backup.verify_backup_archive",
        lambda *a, **kw: (_ for _ in ()).throw(BackupVerificationError("verify failed")),
    )
    with pytest.raises(BackupVerificationError):
        runner.run(JOB_ID)
    with factory() as session:
        job = session.get(ApplicationJob, JOB_ID)
        assert job is not None
        assert job.status == JobStatus.FAILED.value
    # archive should be deleted
    assert list(directories.backups.iterdir()) == []
    # Successful cleanup is silent.
    assert "BACKUP_CLEANUP_FAILED" not in caplog.text
    assert "backups/" not in caplog.text


def test_backup_runner_cleanup_failure_logs_only_safe_fields(
    backup_runtime_setup, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    runner, factory, directories, _engine, _root = backup_runtime_setup
    monkeypatch.setattr(
        "transloka_worker.backup.verify_backup_archive",
        lambda *a, **kw: (_ for _ in ()).throw(BackupVerificationError("verify failed")),
    )
    original_unlink = Path.unlink

    def fail_archive_cleanup(path: Path, *, missing_ok: bool = False) -> None:
        if path.parent == directories.backups:
            raise OSError("cleanup denied at a sensitive absolute path")
        original_unlink(path, missing_ok=missing_ok)

    monkeypatch.setattr(Path, "unlink", fail_archive_cleanup)
    caplog.set_level(logging.WARNING, logger="transloka_worker.backup")

    with pytest.raises(BackupVerificationError):
        runner.run(JOB_ID)

    assert list(directories.backups.iterdir())
    records = [record for record in caplog.records if record.message == "BACKUP_CLEANUP_FAILED"]
    assert len(records) == 1
    assert records[0].job_id == JOB_ID
    assert records[0].error_code == "BACKUP_CLEANUP_FAILED"
    assert "backups/" not in caplog.text
    assert str(directories.root) not in caplog.text


def test_backup_runner_db_commit_failure_deletes_unreferenced_archive(
    backup_runtime_setup, monkeypatch: pytest.MonkeyPatch, caplog
) -> None:
    runner, factory, directories, engine, root = backup_runtime_setup
    from transloka_worker import backup as backup_module

    def fake_publish(*args, **kwargs):
        raise RuntimeError("publish commit failed")

    monkeypatch.setattr(backup_module, "_publish", fake_publish)
    with pytest.raises(RuntimeError):
        runner.run(JOB_ID)
    with factory() as session:
        job = session.get(ApplicationJob, JOB_ID)
        assert job is not None
        assert job.status == JobStatus.FAILED.value
    assert list(directories.backups.iterdir()) == []
    # No storage_key in log
    assert "backups/" not in caplog.text
