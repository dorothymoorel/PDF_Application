from pathlib import Path
from typing import Any

import pytest
from transloka_worker.app import QueueWorker
from transloka_worker.queue import (
    DEFAULT_WORKER_COUNT,
    create_consumer,
    create_huey,
    create_translation_producer,
    resolve_queue_configuration,
)
from transloka_worker.tasks.translation import (
    TRANSLATION_TASK_NAME,
    register_translation_task,
)

JOB_ID = "job_00000000-0000-0000-0000-000000000001"


class RecordingConsumer:
    def __init__(self) -> None:
        self.ran = False
        self.graceful: bool | None = None

    def run(self) -> None:
        self.ran = True

    def stop(self, graceful: bool = False) -> None:
        self.graceful = graceful


def test_task_can_be_enqueued_and_executed(tmp_path: Path) -> None:
    huey = create_huey(resolve_queue_configuration(tmp_path / "data"))
    try:

        @huey.task(name="tests.worker.double")  # type: ignore[untyped-decorator]
        def double(value: int) -> int:
            return value * 2

        result = double(4)
        task = huey.dequeue()

        assert huey.pending_count() == 0
        assert task is not None
        huey.execute(task)
        assert result.get() == 8
    finally:
        huey.storage.close()


def test_pending_task_survives_queue_restart(tmp_path: Path) -> None:
    configuration = resolve_queue_configuration(tmp_path / "data")
    first_huey = create_huey(configuration)
    try:

        @first_huey.task(name="tests.worker.increment")  # type: ignore[untyped-decorator]
        def increment(value: int) -> int:
            return value + 1

        result = increment(9)
        task_id = result.id
        assert first_huey.pending_count() == 1
    finally:
        first_huey.storage.close()

    restarted_huey = create_huey(configuration)
    try:

        @restarted_huey.task(  # type: ignore[untyped-decorator]
            name="tests.worker.increment"
        )
        def increment_after_restart(value: int) -> int:
            return value + 1

        task = restarted_huey.dequeue()
        assert task is not None
        assert task.id == task_id

        restarted_huey.execute(task)
        assert restarted_huey.result(task_id) == 10
    finally:
        restarted_huey.storage.close()


def test_translation_task_survives_producer_consumer_restart(tmp_path: Path) -> None:
    configuration = resolve_queue_configuration(tmp_path / "data")
    producer = create_translation_producer(configuration)
    try:
        producer.queue.enqueue(JOB_ID)
        assert producer.huey.pending_count() == 1
    finally:
        producer.close()

    received: list[str] = []
    consumer_huey = create_huey(configuration)
    try:
        register_translation_task(consumer_huey, lambda job_id: received.append(job_id))
        task = consumer_huey.dequeue()
        assert task is not None
        assert task.name == TRANSLATION_TASK_NAME == "transloka.translation.execute"
        assert task.data == ((JOB_ID,), {})
        consumer_huey.execute(task)
        assert received == [JOB_ID]
    finally:
        consumer_huey.storage.close()


def test_translation_producers_own_independent_huey_resources(tmp_path: Path) -> None:
    first = create_translation_producer(resolve_queue_configuration(tmp_path / "first"))
    second = create_translation_producer(resolve_queue_configuration(tmp_path / "second"))
    assert first.huey is not second.huey

    first.close()
    second.close()

    assert first.huey.storage.close() is False
    assert second.huey.storage.close() is False


def test_queue_database_is_separate_from_application_database(tmp_path: Path) -> None:
    configuration = resolve_queue_configuration(tmp_path / "data")
    application_database = configuration.directories.database / "transloka.db"
    huey = create_huey(configuration)
    try:
        assert configuration.database_path == configuration.directories.database / "tasks.db"
        assert configuration.database_path.exists()
        assert configuration.database_path != application_database
        assert not application_database.exists()
    finally:
        huey.storage.close()


def test_consumer_defaults_to_one_worker_and_stops_gracefully(tmp_path: Path) -> None:
    configuration = resolve_queue_configuration(tmp_path / "data")
    consumer: Any = create_consumer(configuration)
    try:
        assert configuration.workers == DEFAULT_WORKER_COUNT == 1
        assert consumer.workers == 1
    finally:
        consumer.huey.storage.close()

    recording_consumer = RecordingConsumer()
    closed: list[bool] = []
    worker = QueueWorker(
        recording_consumer,
        close_resources=lambda: closed.append(True),
    )
    worker.run()
    worker.stop()

    assert recording_consumer.ran
    assert recording_consumer.graceful is True
    assert closed == [True]


def test_worker_count_must_be_positive(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="positive integer"):
        resolve_queue_configuration(tmp_path / "data", workers=0)
