import importlib
import socket
import sys
import time
from threading import Thread

import pytest
from transloka_worker.app import HeartbeatState, Worker, WorkerStatus, main


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


def _wait_for_heartbeat(worker: Worker) -> bool:
    for _ in range(100):
        if worker.heartbeat_state().sequence > 0:
            return True
        time.sleep(0.01)
    return False
