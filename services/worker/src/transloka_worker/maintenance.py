"""Cross-process maintenance gate used to pause new queue mutations."""

from pathlib import Path

from huey import CancelExecution  # type: ignore[import-untyped]
from transloka_core.backup.restore import MAINTENANCE_MARKER_FILENAME
from transloka_core.storage import LocalDataDirectories


class MaintenanceGate:
    """Reject task execution while an API restore owns maintenance mode."""

    def __init__(self, directories: LocalDataDirectories) -> None:
        self._marker = directories.root / MAINTENANCE_MARKER_FILENAME

    @property
    def marker_path(self) -> Path:
        return self._marker

    def is_active(self) -> bool:
        return self._marker.is_file()

    def ensure_available(self) -> None:
        if self.is_active():
            raise CancelExecution("The worker is paused for an application restore.")


__all__ = ["MaintenanceGate"]
