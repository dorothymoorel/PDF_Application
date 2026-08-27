import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any
from uuid import UUID

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from transloka_core.database import create_session_factory, create_sqlite_engine
from transloka_core.database.models.jobs import ApplicationJob, JobStatus, JobType
from transloka_core.jobs.dispatch import (
    QUEUE_DISPATCH_FAILED,
    InvalidJobDispatchError,
    JobDispatchService,
    JobIdempotencyConflictError,
    JobQueueUnavailableError,
)
from transloka_core.storage import resolve_local_data_directories
from transloka_worker.queue import HueyJobQueue, create_huey, resolve_queue_configuration

REPOSITORY_ROOT = Path(__file__).parents[3]
ALEMBIC_CONFIGURATION = REPOSITORY_ROOT / "alembic.ini"
PAGE_ID = "pag_550e8400-e29b-41d4-a716-446655440000"


class UnavailableQueue:
    name = "transloka"

    def enqueue(self, _job_id: str) -> None:
        raise OSError("queue unavailable")


class InspectingQueue:
    name = "transloka"

    def __init__(self, factory: sessionmaker[Session]) -> None:
        self._factory = factory
        self.observed_statuses: list[str] = []

    def enqueue(self, job_id: str) -> None:
        with self._factory() as session:
            row = session.get(ApplicationJob, job_id)
            assert row is not None
            self.observed_statuses.append(row.status)


@pytest.fixture
def job_database(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> Iterator[tuple[Path, Engine, sessionmaker[Session]]]:
    root = tmp_path / "dispatch data"
    monkeypatch.setenv("TRANSLOKA_DATA_DIR", str(root))
    command.upgrade(Config(str(ALEMBIC_CONFIGURATION)), "head")
    engine = create_sqlite_engine(resolve_local_data_directories(root))
    try:
        yield root, engine, create_session_factory(engine)
    finally:
        engine.dispose()


def test_successful_dispatch_persists_job_and_enqueues_only_job_id(
    job_database: tuple[Path, Engine, sessionmaker[Session]],
) -> None:
    root, _engine, factory = job_database
    huey = create_huey(resolve_queue_configuration(root))
    executed: list[str] = []
    try:

        @huey.task(name="tests.worker.execute_job")  # type: ignore[untyped-decorator]
        def execute_job(job_id: str) -> None:
            executed.append(job_id)

        service = JobDispatchService(factory, HueyJobQueue(execute_job))
        result = service.dispatch(
            job_type=JobType.MAINTENANCE,
            idempotency_key="maintenance-1",
            page_ids=(PAGE_ID,),
        )

        assert result.status is JobStatus.QUEUED
        assert result.created
        assert result.job_id == f"job_{UUID(result.job_id[4:])}"

        task: Any = huey.dequeue()
        assert task is not None
        assert task.args == (result.job_id,)
        assert task.kwargs == {}
        huey.execute(task)
        assert executed == [result.job_id]

        with factory() as session:
            row = session.get(ApplicationJob, result.job_id)
            assert row is not None
            assert row.status == JobStatus.QUEUED.value
            assert row.queued_at is not None
            assert row.error_code is None
            assert json.loads(row.payload_json) == {
                "document_id": None,
                "page_ids": [PAGE_ID],
                "project_id": None,
            }
    finally:
        huey.storage.close()


def test_queue_failure_persists_failed_job_instead_of_false_queued(
    job_database: tuple[Path, Engine, sessionmaker[Session]],
) -> None:
    _root, _engine, factory = job_database
    service = JobDispatchService(factory, UnavailableQueue())

    with pytest.raises(JobQueueUnavailableError) as captured:
        service.dispatch(
            job_type=JobType.MAINTENANCE,
            idempotency_key="unavailable-queue",
        )

    with factory() as session:
        row = session.get(ApplicationJob, captured.value.job_id)
        assert row is not None
        assert row.status == JobStatus.FAILED.value
        assert row.error_code == QUEUE_DISPATCH_FAILED
        assert row.error_message == "The job could not be queued."
        assert row.queued_at is None
        assert row.completed_at is not None


def test_dispatch_commits_queued_state_before_enqueuing(
    job_database: tuple[Path, Engine, sessionmaker[Session]],
) -> None:
    _root, _engine, factory = job_database
    queue = InspectingQueue(factory)

    result = JobDispatchService(factory, queue).dispatch(
        job_type=JobType.TRANSLATE_DOCUMENT,
        idempotency_key="translation-race-safe",
    )

    assert result.status is JobStatus.QUEUED
    assert queue.observed_statuses == [JobStatus.QUEUED.value]


def test_dispatch_persists_canonical_extended_command(
    job_database: tuple[Path, Engine, sessionmaker[Session]],
) -> None:
    _root, _engine, factory = job_database
    queue = InspectingQueue(factory)
    command_payload = {
        "schema": "transloka.translation.command.v1",
        "project_id": None,
        "document_id": None,
        "model_id": "mdl_550e8400-e29b-41d4-a716-446655440000",
        "segment_ids": ["seg_550e8400-e29b-41d4-a716-446655440001"],
    }

    result = JobDispatchService(factory, queue).dispatch(
        job_type=JobType.TRANSLATE_DOCUMENT,
        idempotency_key="translation-command-1",
        command_payload=command_payload,
    )

    with factory() as session:
        row = session.get(ApplicationJob, result.job_id)
        assert row is not None
        assert json.loads(row.payload_json) == command_payload
        assert row.payload_json == json.dumps(
            command_payload,
            ensure_ascii=False,
            allow_nan=False,
            sort_keys=True,
            separators=(",", ":"),
        )


def test_dispatch_rejects_non_json_command_without_creating_job(
    job_database: tuple[Path, Engine, sessionmaker[Session]],
) -> None:
    _root, _engine, factory = job_database

    with pytest.raises(InvalidJobDispatchError, match="JSON-safe"):
        JobDispatchService(factory, UnavailableQueue()).dispatch(
            job_type=JobType.TRANSLATE_DOCUMENT,
            idempotency_key="translation-command-invalid",
            command_payload={"schema": object()},
        )

    with factory() as session:
        assert session.scalar(select(ApplicationJob.id)) is None


def test_duplicate_key_reuses_matching_job_without_duplicate_queue_task(
    job_database: tuple[Path, Engine, sessionmaker[Session]],
) -> None:
    root, _engine, factory = job_database
    huey = create_huey(resolve_queue_configuration(root))
    try:

        @huey.task(name="tests.worker.idempotent_job")  # type: ignore[untyped-decorator]
        def execute_job(_job_id: str) -> None:
            pass

        service = JobDispatchService(factory, HueyJobQueue(execute_job))
        first = service.dispatch(
            job_type=JobType.MAINTENANCE,
            idempotency_key="same-operation",
        )
        second = service.dispatch(
            job_type=JobType.MAINTENANCE,
            idempotency_key="same-operation",
        )

        assert first.created
        assert not second.created
        assert second.job_id == first.job_id
        assert huey.pending_count() == 1
        with factory() as session:
            assert len(session.scalars(select(ApplicationJob)).all()) == 1

        with pytest.raises(JobIdempotencyConflictError):
            service.dispatch(
                job_type=JobType.BACKUP_DATABASE,
                idempotency_key="same-operation",
            )
    finally:
        huey.storage.close()


def test_dispatch_rejects_binary_or_non_identifier_payload_values(
    job_database: tuple[Path, Engine, sessionmaker[Session]],
) -> None:
    _root, _engine, factory = job_database
    service = JobDispatchService(factory, UnavailableQueue())

    with pytest.raises(InvalidJobDispatchError, match="Page identifiers"):
        service.dispatch(
            job_type=JobType.MAINTENANCE,
            idempotency_key="binary-payload",
            page_ids=b"%PDF",  # type: ignore[arg-type]
        )

    with factory() as session:
        assert session.scalar(select(ApplicationJob.id)) is None
