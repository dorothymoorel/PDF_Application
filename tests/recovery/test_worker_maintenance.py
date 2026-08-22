from pathlib import Path

import pytest
from huey import CancelExecution  # type: ignore[import-untyped]
from transloka_core.backup.restore import FileRestoreCoordinator
from transloka_core.storage import resolve_local_data_directories
from transloka_worker.maintenance import MaintenanceGate
from transloka_worker.queue import QueueConfiguration, create_huey


def test_worker_gate_rejects_new_tasks_during_maintenance(tmp_path: Path) -> None:
    directories = resolve_local_data_directories(tmp_path / "worker data")
    gate = MaintenanceGate(directories)
    coordinator = FileRestoreCoordinator(directories)

    gate.ensure_available()
    coordinator.enter_maintenance()
    try:
        assert gate.is_active() is True
        with pytest.raises(CancelExecution):
            gate.ensure_available()
    finally:
        coordinator.exit_maintenance()

    assert gate.is_active() is False


def test_huey_registers_the_maintenance_gate(tmp_path: Path) -> None:
    directories = resolve_local_data_directories(tmp_path / "queue data")
    huey = create_huey(QueueConfiguration(directories))
    coordinator = FileRestoreCoordinator(directories)
    try:
        coordinator.enter_maintenance()
        with pytest.raises(CancelExecution):
            huey._run_pre_execute(object())
    finally:
        coordinator.exit_maintenance()
        huey.storage.close()
