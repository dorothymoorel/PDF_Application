from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from transloka_core.database import create_session_factory, create_sqlite_engine
from transloka_core.database.models.jobs import ApplicationJob, JobStatus, JobType
from transloka_core.jobs.dispatch import JobDispatchService
from transloka_core.jobs.progress import (
    InvalidJobProgressError,
    JobNotActiveError,
    JobProgressService,
)
from transloka_core.storage import resolve_local_data_directories

REPOSITORY_ROOT = Path(__file__).parents[3]
ALEMBIC_CONFIGURATION = REPOSITORY_ROOT / "alembic.ini"


class RecordingQueue:
    name = "test-progress"

    def enqueue(self, _job_id: str) -> None:
        pass


@pytest.fixture
def job_database(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> Iterator[tuple[Engine, sessionmaker[Session], str]]:
    root = tmp_path / "job progress"
    monkeypatch.setenv("TRANSLOKA_DATA_DIR", str(root))
    command.upgrade(Config(str(ALEMBIC_CONFIGURATION)), "head")
    engine = create_sqlite_engine(resolve_local_data_directories(root))
    factory = create_session_factory(engine)
    job_id = (
        JobDispatchService(factory, RecordingQueue())
        .dispatch(
            job_type=JobType.MAINTENANCE,
            idempotency_key="job-progress",
        )
        .job_id
    )
    try:
        yield engine, factory, job_id
    finally:
        engine.dispose()


def test_valid_update_starts_job_and_persists_latest_progress(
    job_database: tuple[Engine, sessionmaker[Session], str],
) -> None:
    _engine, factory, job_id = job_database

    result = JobProgressService(factory).update(
        job_id,
        progress=0.35,
        current_stage="EXTRACT_TEXT",
    )

    assert result.status is JobStatus.RUNNING
    assert result.progress == 0.35
    assert result.current_stage == "EXTRACT_TEXT"
    assert result.heartbeat_at is not None
    with factory() as session:
        row = session.get(ApplicationJob, job_id)
        assert row is not None
        assert row.status == JobStatus.RUNNING.value
        assert row.started_at is not None
        assert row.progress == 0.35
        assert row.current_stage == "EXTRACT_TEXT"
        assert row.heartbeat_at == result.heartbeat_at


@pytest.mark.parametrize("progress", [-0.01, 1.01, float("nan"), float("inf"), True])
def test_invalid_progress_is_rejected_without_mutating_job(
    progress: float,
    job_database: tuple[Engine, sessionmaker[Session], str],
) -> None:
    _engine, factory, job_id = job_database

    with pytest.raises(InvalidJobProgressError):
        JobProgressService(factory).update(
            job_id,
            progress=progress,
            current_stage="EXTRACT_TEXT",
        )

    with factory() as session:
        row = session.get(ApplicationJob, job_id)
        assert row is not None
        assert row.status == JobStatus.QUEUED.value
        assert row.progress == 0.0
        assert row.current_stage is None
        assert row.heartbeat_at is None


def test_heartbeat_is_persisted_for_running_job(
    job_database: tuple[Engine, sessionmaker[Session], str],
) -> None:
    _engine, factory, job_id = job_database
    service = JobProgressService(factory)
    service.update(job_id, progress=0.1, current_stage="STARTED")

    result = service.heartbeat(job_id)

    assert result.status is JobStatus.RUNNING
    assert result.heartbeat_at is not None
    with factory() as session:
        row = session.get(ApplicationJob, job_id)
        assert row is not None
        assert row.heartbeat_at == result.heartbeat_at


def test_completed_job_cannot_be_updated_or_heartbeat_again(
    job_database: tuple[Engine, sessionmaker[Session], str],
) -> None:
    _engine, factory, job_id = job_database
    with factory.begin() as session:
        row = session.get(ApplicationJob, job_id)
        assert row is not None
        row.status = JobStatus.COMPLETED.value
        row.progress = 1.0
        row.completed_at = "2026-08-05T00:00:00.000Z"

    service = JobProgressService(factory)
    with pytest.raises(JobNotActiveError):
        service.update(job_id, progress=0.5, current_stage="TOO_LATE")
    with pytest.raises(JobNotActiveError):
        service.heartbeat(job_id)

    with factory() as session:
        row = session.get(ApplicationJob, job_id)
        assert row is not None
        assert row.status == JobStatus.COMPLETED.value
        assert row.progress == 1.0
        assert row.current_stage is None
        assert row.heartbeat_at is None
