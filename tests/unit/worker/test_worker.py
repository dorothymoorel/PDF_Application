import importlib
import socket
import sys
import time
from pathlib import Path
from threading import Event, Thread
from typing import Any

import pytest
from transloka_worker.app import HeartbeatState, QueueWorker, Worker, main
from transloka_worker.health import WORKER_HEARTBEAT_KEY, WorkerHeartbeatStore, WorkerStatus
from transloka_worker.queue import create_huey, resolve_queue_configuration


def test_worker_package_imports() -> None:
    assert importlib.import_module("transloka_worker") is sys.modules["transloka_worker"]


def test_import_does_not_bind_a_network_socket(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail_bind(_socket: socket.socket, _address: object) -> None:
        raise AssertionError("Importing the worker bound a network socket.")

    monkeypatch.setattr(socket.socket, "bind", fail_bind)

    importlib.reload(importlib.import_module("transloka_worker"))


def test_worker_starts_heartbeats_and_stops_cleanly() -> None:
    worker = Worker(heartbeat_interval_seconds=0.01)
    initial = worker.heartbeat_state()
    thread = Thread(target=worker.run)

    thread.start()
    assert _wait_for_heartbeat(worker)

    running = worker.heartbeat_state()
    worker.stop()
    thread.join(timeout=1)
    stopped = worker.heartbeat_state()

    assert initial == HeartbeatState(
        worker_name="transloka-worker",
        status=WorkerStatus.STOPPED,
        sequence=0,
        recorded_at=None,
    )
    assert running.status is WorkerStatus.RUNNING
    assert running.sequence >= 1
    assert running.recorded_at is not None
    assert not thread.is_alive()
    assert stopped.status is WorkerStatus.STOPPED
    assert stopped.sequence >= running.sequence
    assert stopped.recorded_at is not None


def test_worker_rejects_invalid_heartbeat_interval() -> None:
    with pytest.raises(ValueError, match="positive finite"):
        Worker(heartbeat_interval_seconds=0)


def test_entrypoint_starts_and_stops_worker() -> None:
    worker = Worker(heartbeat_interval_seconds=0.01)
    worker.stop()

    exit_code = main(worker)

    assert exit_code == 0
    assert worker.heartbeat_state().status is WorkerStatus.STOPPED
    assert worker.heartbeat_state().sequence == 1


def test_worker_has_no_fake_completed_state() -> None:
    assert "COMPLETED" not in {status.value for status in WorkerStatus}


def test_queue_worker_persists_running_heartbeats_and_stopped_state() -> None:
    huey = FakeHuey()
    consumer = BlockingConsumer()
    resources_closed = Event()
    heartbeat_store = WorkerHeartbeatStore(huey, worker_identifier="test-worker")
    worker = QueueWorker(
        consumer,
        close_resources=resources_closed.set,
        heartbeat_store=heartbeat_store,
        heartbeat_interval_seconds=0.01,
    )
    thread = Thread(target=worker.run)

    thread.start()
    assert consumer.started.wait(timeout=1)
    assert _wait_for_persisted_heartbeat(heartbeat_store, minimum_sequence=2)
    running = heartbeat_store.read()

    worker.stop()
    thread.join(timeout=1)
    stopped = heartbeat_store.read()

    assert running is not None
    assert running.status is WorkerStatus.RUNNING
    assert running.worker_identifier == "test-worker"
    assert stopped is not None
    assert stopped.status is WorkerStatus.STOPPED
    assert stopped.sequence > running.sequence
    assert not thread.is_alive()
    assert resources_closed.is_set()


def test_persisted_heartbeat_rejects_invalid_payload() -> None:
    huey = FakeHuey()
    heartbeat_store = WorkerHeartbeatStore(huey, worker_identifier="test-worker")
    huey.values[WORKER_HEARTBEAT_KEY] = {"schema": "unsupported"}

    assert heartbeat_store.read() is None


def test_persisted_heartbeat_round_trips_through_sqlite_huey(tmp_path: Path) -> None:
    huey = create_huey(resolve_queue_configuration(tmp_path))
    try:
        writer = WorkerHeartbeatStore(
            huey,
            worker_identifier="test-worker",
            clock=lambda: 1_725_000_000.0,
        )

        recorded = writer.record(WorkerStatus.RUNNING)
        persisted = WorkerHeartbeatStore(huey, worker_identifier="reader").read()

        assert persisted == recorded
    finally:
        huey.storage.close()


def test_queue_worker_stops_if_persistent_heartbeat_fails() -> None:
    huey = FailingHeartbeatHuey()
    consumer = BlockingConsumer()
    resources_closed = Event()
    worker = QueueWorker(
        consumer,
        close_resources=resources_closed.set,
        heartbeat_store=WorkerHeartbeatStore(huey, worker_identifier="test-worker"),
        heartbeat_interval_seconds=0.01,
    )
    thread = Thread(target=worker.run)

    thread.start()
    assert consumer.started.wait(timeout=1)
    thread.join(timeout=1)

    assert consumer.stopped.is_set()
    assert resources_closed.is_set()
    assert not thread.is_alive()


def _wait_for_heartbeat(worker: Worker) -> bool:
    for _ in range(100):
        if worker.heartbeat_state().sequence > 0:
            return True
        time.sleep(0.01)
    return False


def _wait_for_persisted_heartbeat(
    heartbeat_store: WorkerHeartbeatStore,
    *,
    minimum_sequence: int,
) -> bool:
    for _ in range(100):
        heartbeat = heartbeat_store.read()
        if heartbeat is not None and heartbeat.sequence >= minimum_sequence:
            return True
        time.sleep(0.01)
    return False


class FakeHuey:
    def __init__(self) -> None:
        self.values: dict[str, object] = {}

    def put(self, key: str, value: object) -> None:
        self.values[key] = value

    def get(self, key: str, *, peek: bool = False) -> Any:
        assert peek
        return self.values.get(key)


class FailingHeartbeatHuey(FakeHuey):
    def __init__(self) -> None:
        super().__init__()
        self.put_count = 0

    def put(self, key: str, value: object) -> None:
        self.put_count += 1
        if self.put_count > 1:
            raise RuntimeError("heartbeat unavailable")
        super().put(key, value)


class BlockingConsumer:
    def __init__(self) -> None:
        self.started = Event()
        self.stopped = Event()

    def run(self) -> None:
        self.started.set()
        self.stopped.wait(timeout=1)

    def stop(self, graceful: bool = False) -> None:
        assert graceful
        self.stopped.set()
