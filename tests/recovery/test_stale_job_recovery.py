import hashlib
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from transloka_api.startup import recover_stale_jobs
from transloka_core.database import create_session_factory, create_sqlite_engine, transaction_scope
from transloka_core.database.models.jobs import ApplicationJob, JobAttempt, JobStatus, JobType
from transloka_core.jobs.dispatch import JobDispatchService
from transloka_core.jobs.recovery import (
    JobRecoveryService,
    RecoveryArtifact,
    RecoveryArtifactError,
    RecoveryArtifactState,
)
from transloka_core.jobs.retry import JobRetryService
from transloka_core.storage import LocalDataDirectories, resolve_local_data_directories

REPOSITORY_ROOT = Path(__file__).parents[2]
ALEMBIC_CONFIGURATION = REPOSITORY_ROOT / "alembic.ini"
RECOVERY_TIME = datetime(2026, 8, 8, 12, 0, tzinfo=UTC)
STALE_THRESHOLD = timedelta(minutes=5)


class RecordingQueue:
    name = "test-recovery"

    def enqueue(self, _job_id: str) -> None:
        pass


@pytest.fixture
def recovery_database(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> Iterator[tuple[LocalDataDirectories, Engine, sessionmaker[Session]]]:
    root = tmp_path / "recovery data"
    monkeypatch.setenv("TRANSLOKA_DATA_DIR", str(root))
    command.upgrade(Config(str(ALEMBIC_CONFIGURATION)), "head")
    directories = resolve_local_data_directories(root)
    engine = create_sqlite_engine(directories)
    factory = create_session_factory(engine)
    try:
        yield directories, engine, factory
    finally:
        engine.dispose()


def _running_job(factory: sessionmaker[Session], key: str, heartbeat_at: str) -> str:
    job_id = (
        JobDispatchService(factory, RecordingQueue())
        .dispatch(
            job_type=JobType.MAINTENANCE,
            idempotency_key=key,
        )
        .job_id
    )
    with transaction_scope(factory) as session:
        row = session.get(ApplicationJob, job_id)
        assert row is not None
        row.status = JobStatus.RUNNING.value
        row.progress = 0.4
        row.current_stage = "PROCESSING"
        row.started_at = "2026-08-08T11:00:00.000Z"
        row.heartbeat_at = heartbeat_at
    return job_id


def _service(
    factory: sessionmaker[Session], directories: LocalDataDirectories
) -> JobRecoveryService:
    return JobRecoveryService(
        factory,
        data_root=directories.root,
        temporary_root=directories.temporary,
    )


def test_stale_running_job_is_visible_and_healthy_job_is_untouched(
    recovery_database: tuple[LocalDataDirectories, Engine, sessionmaker[Session]],
) -> None:
    directories, _engine, factory = recovery_database
    stale_id = _running_job(factory, "stale-job", "2026-08-08T11:54:59.000Z")
    healthy_id = _running_job(factory, "healthy-job", "2026-08-08T11:55:01.000Z")

    results = _service(factory, directories).recover(
        stale_threshold=STALE_THRESHOLD,
        now=RECOVERY_TIME,
    )

    assert [(result.job_id, result.status) for result in results] == [(stale_id, JobStatus.STALE)]
    assert results[0].retry_available
    with factory() as session:
        stale = session.get(ApplicationJob, stale_id)
        healthy = session.get(ApplicationJob, healthy_id)
        assert stale is not None
        assert healthy is not None
        assert stale.status == JobStatus.STALE.value
        assert stale.current_stage == JobStatus.STALE.value
        assert stale.error_code == "WORKER_HEARTBEAT_STALE"
        assert stale.completed_at == "2026-08-08T12:00:00.000Z"
        assert healthy.status == JobStatus.RUNNING.value
        assert healthy.current_stage == "PROCESSING"
        attempt = session.scalar(select(JobAttempt).where(JobAttempt.job_id == stale_id))
        assert attempt is not None
        assert attempt.status == "STALE"


def test_incomplete_temporary_output_is_removed(
    recovery_database: tuple[LocalDataDirectories, Engine, sessionmaker[Session]],
) -> None:
    directories, _engine, factory = recovery_database
    job_id = _running_job(factory, "incomplete-output", "2026-08-08T11:00:00.000Z")
    incomplete = directories.temporary / "job-output.partial"
    incomplete.parent.mkdir(parents=True, exist_ok=True)
    incomplete.write_bytes(b"incomplete")

    result = _service(factory, directories).recover(
        stale_threshold=STALE_THRESHOLD,
        artifacts={job_id: RecoveryArtifact(incomplete_outputs=(incomplete,))},
        now=RECOVERY_TIME,
    )

    assert result[0].artifact_state is RecoveryArtifactState.INCOMPLETE_REMOVED
    assert not incomplete.exists()


def test_valid_atomic_output_is_preserved_but_does_not_auto_complete(
    recovery_database: tuple[LocalDataDirectories, Engine, sessionmaker[Session]],
) -> None:
    directories, _engine, factory = recovery_database
    job_id = _running_job(factory, "valid-atomic-output", "2026-08-08T11:00:00.000Z")
    final_output = directories.projects / "project-1" / "final.pdf"
    final_output.parent.mkdir(parents=True, exist_ok=True)
    content = b"validated final output"
    final_output.write_bytes(content)
    with transaction_scope(factory) as session:
        row = session.get(ApplicationJob, job_id)
        assert row is not None
        row.result_json = '{"artifact_id":"valid-prior-result"}'

    result = _service(factory, directories).recover(
        stale_threshold=STALE_THRESHOLD,
        artifacts={
            job_id: RecoveryArtifact(
                final_output=final_output,
                checksum_sha256=hashlib.sha256(content).hexdigest(),
                size_bytes=len(content),
            )
        },
        now=RECOVERY_TIME,
    )

    assert result[0].artifact_state is RecoveryArtifactState.VALID_ATOMIC
    assert final_output.read_bytes() == content
    with factory() as session:
        row = session.get(ApplicationJob, job_id)
        assert row is not None
        assert row.status == JobStatus.STALE.value
        assert row.result_json == '{"artifact_id":"valid-prior-result"}'

    retry = JobRetryService(factory).request(
        job_id,
        idempotency_key="recovery-retry",
        retry_failed_items_only=True,
        reason="USER_CONFIRMED_STALE_RECOVERY",
    )
    assert retry.status is JobStatus.RETRYING
    assert final_output.read_bytes() == content


def test_file_existence_without_integrity_metadata_is_not_completion_evidence(
    recovery_database: tuple[LocalDataDirectories, Engine, sessionmaker[Session]],
) -> None:
    directories, _engine, factory = recovery_database
    job_id = _running_job(factory, "unverified-output", "2026-08-08T11:00:00.000Z")
    final_output = directories.projects / "project-1" / "unverified.pdf"
    final_output.parent.mkdir(parents=True, exist_ok=True)
    final_output.write_bytes(b"file existence is insufficient")

    result = _service(factory, directories).recover(
        stale_threshold=STALE_THRESHOLD,
        artifacts={job_id: RecoveryArtifact(final_output=final_output)},
        now=RECOVERY_TIME,
    )

    assert result[0].status is JobStatus.STALE
    assert result[0].artifact_state is RecoveryArtifactState.PRESENT_UNVERIFIED
    assert final_output.exists()


def test_application_restart_runs_recovery_once_without_duplicate_work(
    recovery_database: tuple[LocalDataDirectories, Engine, sessionmaker[Session]],
) -> None:
    directories, engine, factory = recovery_database
    job_id = _running_job(factory, "restart-job", "2026-08-08T11:00:00.000Z")
    incomplete = directories.temporary / "restart.partial"
    incomplete.parent.mkdir(parents=True, exist_ok=True)
    incomplete.write_bytes(b"interrupted")
    engine.dispose()

    restarted_engine = create_sqlite_engine(directories)
    restarted_factory = create_session_factory(restarted_engine)
    try:
        first = recover_stale_jobs(
            restarted_factory,
            directories,
            stale_threshold=STALE_THRESHOLD,
            artifacts={job_id: RecoveryArtifact(incomplete_outputs=(incomplete,))},
            now=RECOVERY_TIME,
        )
        second = recover_stale_jobs(
            restarted_factory,
            directories,
            stale_threshold=STALE_THRESHOLD,
            artifacts={job_id: RecoveryArtifact(incomplete_outputs=(incomplete,))},
            now=RECOVERY_TIME,
        )

        assert [result.job_id for result in first] == [job_id]
        assert second == ()
        assert not incomplete.exists()
        with restarted_factory() as session:
            assert session.scalar(select(JobAttempt).where(JobAttempt.job_id == job_id)) is not None
            assert len(session.scalars(select(JobAttempt)).all()) == 1
    finally:
        restarted_engine.dispose()


def test_recovery_rejects_cleanup_outside_temporary_storage(
    recovery_database: tuple[LocalDataDirectories, Engine, sessionmaker[Session]],
    tmp_path: Path,
) -> None:
    directories, _engine, factory = recovery_database
    job_id = _running_job(factory, "unsafe-cleanup", "2026-08-08T11:00:00.000Z")
    outside = tmp_path / "outside.partial"
    outside.write_bytes(b"must remain")

    with pytest.raises(RecoveryArtifactError):
        _service(factory, directories).recover(
            stale_threshold=STALE_THRESHOLD,
            artifacts={job_id: RecoveryArtifact(incomplete_outputs=(outside,))},
            now=RECOVERY_TIME,
        )

    assert outside.exists()
    with factory() as session:
        row = session.get(ApplicationJob, job_id)
        assert row is not None
        assert row.status == JobStatus.RUNNING.value
