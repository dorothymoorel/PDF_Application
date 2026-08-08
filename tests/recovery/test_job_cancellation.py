from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from transloka_core.database import create_session_factory, create_sqlite_engine, transaction_scope
from transloka_core.database.models.jobs import ApplicationJob, JobStatus, JobType
from transloka_core.jobs.cancellation import (
    CancellationCleanupError,
    JobCancellationService,
    JobCannotBeCancelledError,
)
from transloka_core.jobs.dispatch import JobDispatchService
from transloka_core.jobs.progress import JobProgressService
from transloka_core.storage import resolve_local_data_directories

REPOSITORY_ROOT = Path(__file__).parents[2]
ALEMBIC_CONFIGURATION = REPOSITORY_ROOT / "alembic.ini"


class RecordingQueue:
    name = "test-cancellation"

    def enqueue(self, _job_id: str) -> None:
        pass


@pytest.fixture
def cancellation_database(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> Iterator[tuple[Path, Engine, sessionmaker[Session], str]]:
    root = tmp_path / "cancellation data"
    monkeypatch.setenv("TRANSLOKA_DATA_DIR", str(root))
    command.upgrade(Config(str(ALEMBIC_CONFIGURATION)), "head")
    directories = resolve_local_data_directories(root)
    engine = create_sqlite_engine(directories)
    factory = create_session_factory(engine)
    job_id = (
        JobDispatchService(factory, RecordingQueue())
        .dispatch(
            job_type=JobType.MAINTENANCE,
            idempotency_key="cancel-job",
        )
        .job_id
    )
    try:
        yield root, engine, factory, job_id
    finally:
        engine.dispose()


def test_queued_cancellation_is_immediate_and_idempotent(
    cancellation_database: tuple[Path, Engine, sessionmaker[Session], str],
) -> None:
    root, _engine, factory, job_id = cancellation_database
    service = JobCancellationService(factory, root / "temp")

    first = service.request(job_id, reason="Cancelled by user.")
    second = service.request(job_id, reason="Cancelled by user.")

    assert first.status is JobStatus.CANCELLED
    assert first.cancelled_at is not None
    assert second == first
    assert service.checkpoint(job_id)
    with factory() as session:
        row = session.get(ApplicationJob, job_id)
        assert row is not None
        assert row.status == JobStatus.CANCELLED.value
        assert row.completed_at == row.cancelled_at
        assert row.progress == 0.0


def test_running_cancellation_waits_for_checkpoint_and_cleans_incomplete_output(
    cancellation_database: tuple[Path, Engine, sessionmaker[Session], str],
) -> None:
    root, _engine, factory, job_id = cancellation_database
    JobProgressService(factory).update(job_id, progress=0.4, current_stage="ATOMIC_UNIT")
    with transaction_scope(factory) as session:
        row = session.get(ApplicationJob, job_id)
        assert row is not None
        row.result_json = '{"artifact_id":"valid-prior-result"}'

    incomplete = root / "temp" / "job-output.partial"
    incomplete.parent.mkdir(parents=True, exist_ok=True)
    incomplete.write_bytes(b"incomplete")
    service = JobCancellationService(factory, root / "temp")

    requested = service.request(job_id, reason="Cancelled by user.")

    assert requested.status is JobStatus.CANCELLATION_REQUESTED
    assert incomplete.exists()
    assert service.request(job_id, reason="Cancelled again.") == requested
    assert service.checkpoint(job_id, incomplete_outputs=(incomplete,))
    assert not incomplete.exists()
    with factory() as session:
        row = session.get(ApplicationJob, job_id)
        assert row is not None
        assert row.status == JobStatus.CANCELLED.value
        assert row.current_stage == JobStatus.CANCELLED.value
        assert row.progress == 0.4
        assert row.cancelled_at == row.completed_at
        assert row.result_json == '{"artifact_id":"valid-prior-result"}'


def test_checkpoint_without_request_preserves_current_atomic_output(
    cancellation_database: tuple[Path, Engine, sessionmaker[Session], str],
) -> None:
    root, _engine, factory, job_id = cancellation_database
    JobProgressService(factory).update(job_id, progress=0.2, current_stage="ATOMIC_UNIT")
    incomplete = root / "temp" / "still-in-use.partial"
    incomplete.parent.mkdir(parents=True, exist_ok=True)
    incomplete.write_bytes(b"current operation")

    assert not JobCancellationService(factory, root / "temp").checkpoint(
        job_id,
        incomplete_outputs=(incomplete,),
    )
    assert incomplete.exists()


def test_completed_job_cannot_be_cancelled_and_keeps_valid_result(
    cancellation_database: tuple[Path, Engine, sessionmaker[Session], str],
) -> None:
    root, _engine, factory, job_id = cancellation_database
    with transaction_scope(factory) as session:
        row = session.get(ApplicationJob, job_id)
        assert row is not None
        row.status = JobStatus.COMPLETED.value
        row.progress = 1.0
        row.completed_at = "2026-08-08T00:00:00.000Z"
        row.result_json = '{"artifact_id":"final-result"}'

    with pytest.raises(JobCannotBeCancelledError):
        JobCancellationService(factory, root / "temp").request(
            job_id,
            reason="Too late.",
        )

    with factory() as session:
        row = session.get(ApplicationJob, job_id)
        assert row is not None
        assert row.status == JobStatus.COMPLETED.value
        assert row.progress == 1.0
        assert row.result_json == '{"artifact_id":"final-result"}'


def test_checkpoint_rejects_outputs_outside_temporary_storage(
    cancellation_database: tuple[Path, Engine, sessionmaker[Session], str],
) -> None:
    root, _engine, factory, job_id = cancellation_database
    JobProgressService(factory).update(job_id, progress=0.5, current_stage="ATOMIC_UNIT")
    valid_result = root / "projects" / "valid.pdf"
    valid_result.parent.mkdir(parents=True, exist_ok=True)
    valid_result.write_bytes(b"valid result")
    service = JobCancellationService(factory, root / "temp")
    service.request(job_id, reason="Cancelled by user.")

    with pytest.raises(CancellationCleanupError):
        service.checkpoint(job_id, incomplete_outputs=(valid_result,))

    assert valid_result.read_bytes() == b"valid result"
    with factory() as session:
        row = session.get(ApplicationJob, job_id)
        assert row is not None
        assert row.status == JobStatus.CANCELLATION_REQUESTED.value
