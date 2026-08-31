import json
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from transloka_core.database import create_session_factory, create_sqlite_engine, transaction_scope
from transloka_core.database.models.jobs import ApplicationJob, JobAttempt, JobStatus, JobType
from transloka_core.jobs.dispatch import JobDispatchService
from transloka_core.jobs.retry import (
    JobNotRetryableError,
    JobRetryLimitError,
    JobRetryService,
    RetryIdempotencyConflictError,
)
from transloka_core.storage import resolve_local_data_directories

REPOSITORY_ROOT = Path(__file__).parents[3]
ALEMBIC_CONFIGURATION = REPOSITORY_ROOT / "alembic.ini"


class RecordingQueue:
    name = "test-retry"

    def enqueue(self, _job_id: str) -> None:
        pass


@pytest.fixture
def retry_database(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> Iterator[tuple[Engine, sessionmaker[Session], str]]:
    root = tmp_path / "retry data"
    monkeypatch.setenv("TRANSLOKA_DATA_DIR", str(root))
    command.upgrade(Config(str(ALEMBIC_CONFIGURATION)), "head")
    engine = create_sqlite_engine(resolve_local_data_directories(root))
    factory = create_session_factory(engine)
    job_id = (
        JobDispatchService(factory, RecordingQueue())
        .dispatch(
            job_type=JobType.MAINTENANCE,
            idempotency_key="retry-source-job",
        )
        .job_id
    )
    try:
        yield engine, factory, job_id
    finally:
        engine.dispose()


def _fail_job(
    factory: sessionmaker[Session],
    job_id: str,
    *,
    error_code: str = "MODEL_TIMEOUT",
    error_message: str = "The local model timed out.",
) -> None:
    with transaction_scope(factory) as session:
        row = session.get(ApplicationJob, job_id)
        assert row is not None
        row.status = JobStatus.FAILED.value
        row.progress = 0.5
        row.current_stage = "TRANSLATE"
        row.result_json = '{"artifact_id":"valid-prior-result"}'
        row.error_code = error_code
        row.error_message = error_message
        row.started_at = "2026-08-08T01:00:00.000Z"
        row.completed_at = "2026-08-08T01:01:00.000Z"


def test_first_retry_creates_complete_attempt_history_and_preserves_result(
    retry_database: tuple[Engine, sessionmaker[Session], str],
) -> None:
    _engine, factory, job_id = retry_database
    _fail_job(factory, job_id)

    result = JobRetryService(factory).request(
        job_id,
        idempotency_key="retry-job-1",
        retry_failed_items_only=True,
        reason="USER_REQUESTED",
    )

    assert result.status is JobStatus.RETRYING
    assert result.retry_count == 1
    assert result.attempt_number == 2
    assert result.created
    with factory() as session:
        row = session.get(ApplicationJob, job_id)
        assert row is not None
        assert row.status == JobStatus.RETRYING.value
        assert row.retry_count == 1
        assert row.result_json == '{"artifact_id":"valid-prior-result"}'
        assert row.error_code == "MODEL_TIMEOUT"
        assert row.error_message == "The local model timed out."
        assert row.completed_at is None
        attempts = list(
            session.scalars(
                select(JobAttempt)
                .where(JobAttempt.job_id == job_id)
                .order_by(JobAttempt.attempt_number)
            )
        )
        assert [(attempt.attempt_number, attempt.status) for attempt in attempts] == [
            (1, "FAILED"),
            (2, "RUNNING"),
        ]
        assert attempts[0].error_code == "MODEL_TIMEOUT"
        assert attempts[0].error_message == "The local model timed out."
        assert json.loads(attempts[1].details_json or "") == {
            "retry": {
                "failed_items_only": True,
                "idempotency_key": "retry-job-1",
                "reason": "USER_REQUESTED",
            }
        }


def test_retry_replaces_job_payload_in_the_same_transaction(
    retry_database: tuple[Engine, sessionmaker[Session], str],
) -> None:
    _engine, factory, job_id = retry_database
    _fail_job(factory, job_id)

    JobRetryService(factory).request(
        job_id,
        idempotency_key="retry-replace-payload",
        retry_failed_items_only=True,
        reason="SMALLER_BATCH",
        replacement_payload_json='{"batch_size":4}',
    )

    with factory() as session:
        job = session.get(ApplicationJob, job_id)
        assert job is not None
        assert job.status == JobStatus.RETRYING.value
        assert job.payload_json == '{"batch_size":4}'


def test_same_retry_key_is_idempotent_and_conflicting_body_is_rejected(
    retry_database: tuple[Engine, sessionmaker[Session], str],
) -> None:
    _engine, factory, job_id = retry_database
    _fail_job(factory, job_id)
    service = JobRetryService(factory)

    first = service.request(
        job_id,
        idempotency_key="retry-idempotent",
        retry_failed_items_only=True,
        reason="USER_REQUESTED",
    )
    repeated = service.request(
        job_id,
        idempotency_key="retry-idempotent",
        retry_failed_items_only=True,
        reason="USER_REQUESTED",
    )

    assert repeated.attempt_id == first.attempt_id
    assert repeated.attempt_number == first.attempt_number
    assert repeated.retry_count == 1
    assert not repeated.created
    with pytest.raises(RetryIdempotencyConflictError):
        service.request(
            job_id,
            idempotency_key="retry-idempotent",
            retry_failed_items_only=False,
            reason="USER_REQUESTED",
        )
    with factory() as session:
        assert len(session.scalars(select(JobAttempt)).all()) == 2


def test_second_retry_finalizes_prior_attempt_without_erasing_older_error(
    retry_database: tuple[Engine, sessionmaker[Session], str],
) -> None:
    _engine, factory, job_id = retry_database
    _fail_job(factory, job_id)
    service = JobRetryService(factory)
    service.request(
        job_id,
        idempotency_key="retry-first",
        retry_failed_items_only=True,
        reason="USER_REQUESTED",
    )
    _fail_job(
        factory,
        job_id,
        error_code="VALIDATION_FAILED",
        error_message="The retry output failed validation.",
    )

    second = service.request(
        job_id,
        idempotency_key="retry-second",
        retry_failed_items_only=True,
        reason="USER_REQUESTED",
    )

    assert second.attempt_number == 3
    assert second.retry_count == 2
    with factory() as session:
        attempts = list(session.scalars(select(JobAttempt).order_by(JobAttempt.attempt_number)))
        assert [attempt.status for attempt in attempts] == ["FAILED", "FAILED", "RUNNING"]
        assert attempts[0].error_code == "MODEL_TIMEOUT"
        assert attempts[1].error_code == "VALIDATION_FAILED"
        assert attempts[1].error_message == "The retry output failed validation."


def test_retry_limit_is_enforced_without_creating_attempt(
    retry_database: tuple[Engine, sessionmaker[Session], str],
) -> None:
    _engine, factory, job_id = retry_database
    _fail_job(factory, job_id)
    with transaction_scope(factory) as session:
        row = session.get(ApplicationJob, job_id)
        assert row is not None
        row.retry_count = row.max_retries

    with pytest.raises(JobRetryLimitError):
        JobRetryService(factory).request(
            job_id,
            idempotency_key="retry-over-limit",
            retry_failed_items_only=True,
            reason="USER_REQUESTED",
        )

    with factory() as session:
        assert session.scalar(select(JobAttempt.id)) is None


def test_completed_and_already_retrying_jobs_reject_new_retry_keys(
    retry_database: tuple[Engine, sessionmaker[Session], str],
) -> None:
    _engine, factory, job_id = retry_database
    with transaction_scope(factory) as session:
        row = session.get(ApplicationJob, job_id)
        assert row is not None
        row.status = JobStatus.COMPLETED.value
        row.progress = 1.0
        row.completed_at = "2026-08-08T01:01:00.000Z"

    service = JobRetryService(factory)
    with pytest.raises(JobNotRetryableError):
        service.request(
            job_id,
            idempotency_key="retry-completed",
            retry_failed_items_only=True,
            reason="USER_REQUESTED",
        )

    _fail_job(factory, job_id)
    service.request(
        job_id,
        idempotency_key="retry-accepted",
        retry_failed_items_only=True,
        reason="USER_REQUESTED",
    )
    with pytest.raises(JobNotRetryableError):
        service.request(
            job_id,
            idempotency_key="retry-duplicate-operation",
            retry_failed_items_only=True,
            reason="USER_REQUESTED",
        )
