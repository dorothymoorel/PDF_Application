"""Cross-process maintenance gate used to pause queue mutations safely."""

from pathlib import Path
from threading import Lock
from time import sleep

from transloka_core.backup.restore import (
    MAINTENANCE_MARKER_FILENAME,
    WorkerExecutionLock,
)
from transloka_core.storage import LocalDataDirectories


class MaintenanceGate:
    """Hold worker task leases so restore can wait for safe quiescence."""

    def __init__(self, directories: LocalDataDirectories) -> None:
        self._directories = directories
        self._marker = directories.root / MAINTENANCE_MARKER_FILENAME
        self._leases: dict[int, WorkerExecutionLock] = {}
        self._leases_lock = Lock()

    @property
    def marker_path(self) -> Path:
        return self._marker

    def is_active(self) -> bool:
        return self._marker.is_file()

    def start_task(self, task: object) -> None:
        key = id(task)
        with self._leases_lock:
            if key in self._leases:
                raise RuntimeError("The worker task already owns an execution lease.")

        lease = WorkerExecutionLock(self._directories)
        lease.acquire()
        while self.is_active():
            lease.release()
            while self.is_active():
                # Poll the cross-process marker; no in-process condition can observe API state.
                sleep(0.05)
            lease.acquire()

        with self._leases_lock:
            self._leases[key] = lease

    def finish_task(self, task: object) -> None:
        with self._leases_lock:
            lease = self._leases.pop(id(task), None)
        if lease is not None:
            lease.release()


__all__ = ["MaintenanceGate"]
