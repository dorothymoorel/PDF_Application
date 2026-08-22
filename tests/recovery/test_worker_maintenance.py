from pathlib import Path
from threading import Event, Thread

from huey.signals import SIGNAL_INTERRUPTED  # type: ignore[import-untyped]
from transloka_core.backup.restore import FileRestoreCoordinator
from transloka_core.storage import resolve_local_data_directories
from transloka_worker.maintenance import MaintenanceGate
from transloka_worker.queue import QueueConfiguration, create_huey


def test_restore_waits_for_running_task_and_releases_queued_task(tmp_path: Path) -> None:
    directories = resolve_local_data_directories(tmp_path / "worker data")
    gate = MaintenanceGate(directories)
    coordinator = FileRestoreCoordinator(directories)
    running_task = object()
    queued_task = object()
    pause_completed = Event()
    queued_started = Event()

    def pause_worker() -> None:
        coordinator.pause_worker()
        pause_completed.set()

    def run_queued_task() -> None:
        gate.start_task(queued_task)
        queued_started.set()
        gate.finish_task(queued_task)

    gate.start_task(running_task)
    coordinator.enter_maintenance()
    try:
        assert gate.is_active() is True
        pause_thread = Thread(target=pause_worker, daemon=True)
        pause_thread.start()

        # The coordinator must wait for the already-running mutation to release its lease.
        assert pause_completed.wait(0.1) is False
        gate.finish_task(running_task)
        assert pause_completed.wait(2.0) is True

        queued_thread = Thread(target=run_queued_task, daemon=True)
        queued_thread.start()

        # A dequeued task remains blocked, rather than being cancelled, during restore.
        assert queued_started.wait(0.1) is False
        coordinator.resume_worker()
        coordinator.exit_maintenance()
        assert queued_started.wait(2.0) is True
        pause_thread.join(timeout=2.0)
        queued_thread.join(timeout=2.0)
    finally:
        gate.finish_task(running_task)
        gate.finish_task(queued_task)
        coordinator.resume_worker()
        coordinator.exit_maintenance()

    assert gate.is_active() is False


def test_huey_holds_dequeued_task_until_maintenance_finishes(tmp_path: Path) -> None:
    directories = resolve_local_data_directories(tmp_path / "queue data")
    huey = create_huey(QueueConfiguration(directories))
    coordinator = FileRestoreCoordinator(directories)
    task = object()
    pre_execute_completed = Event()

    def run_pre_execute() -> None:
        huey._run_pre_execute(task)
        pre_execute_completed.set()

    try:
        coordinator.enter_maintenance()
        coordinator.pause_worker()
        worker_thread = Thread(target=run_pre_execute, daemon=True)
        worker_thread.start()

        assert pre_execute_completed.wait(0.1) is False
        coordinator.resume_worker()
        coordinator.exit_maintenance()
        assert pre_execute_completed.wait(2.0) is True
        huey._run_post_execute(task, None, None)
        worker_thread.join(timeout=2.0)
    finally:
        coordinator.resume_worker()
        coordinator.exit_maintenance()
        huey.storage.close()


def test_huey_releases_execution_lease_when_task_is_interrupted(tmp_path: Path) -> None:
    directories = resolve_local_data_directories(tmp_path / "interrupted queue data")
    huey = create_huey(QueueConfiguration(directories))
    coordinator = FileRestoreCoordinator(directories)
    task = object()
    pause_completed = Event()

    def pause_worker() -> None:
        coordinator.pause_worker()
        pause_completed.set()

    huey._run_pre_execute(task)
    huey._emit(SIGNAL_INTERRUPTED, task)
    coordinator.enter_maintenance()
    pause_thread = Thread(target=pause_worker, daemon=True)
    pause_thread.start()
    try:
        assert pause_completed.wait(2.0) is True
    finally:
        huey._run_post_execute(task, None, KeyboardInterrupt())
        coordinator.resume_worker()
        coordinator.exit_maintenance()
        pause_thread.join(timeout=2.0)
        huey.storage.close()
