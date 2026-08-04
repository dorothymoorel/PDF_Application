from collections.abc import Callable
from dataclasses import dataclass
from os import PathLike
from pathlib import Path
from typing import Any

from huey import SqliteHuey  # type: ignore[import-untyped]
from transloka_core.storage import (
    LocalDataDirectories,
    ensure_local_data_directories,
    resolve_local_data_directories,
)

DEFAULT_WORKER_COUNT = 1
QUEUE_DATABASE_FILENAME = "tasks.db"
QUEUE_NAME = "transloka"


class HueyJobQueue:
    def __init__(
        self,
        task: Callable[[str], object],
        name: str = QUEUE_NAME,
    ) -> None:
        if not name or name != name.strip() or not name.isprintable():
            raise ValueError("Queue name is invalid.")
        self._task = task
        self._name = name

    @property
    def name(self) -> str:
        return self._name

    def enqueue(self, job_id: str) -> None:
        self._task(job_id)


@dataclass(frozen=True, slots=True)
class QueueConfiguration:
    directories: LocalDataDirectories
    workers: int = DEFAULT_WORKER_COUNT

    def __post_init__(self) -> None:
        if isinstance(self.workers, bool) or self.workers < 1:
            raise ValueError("Worker count must be a positive integer.")

    @property
    def database_path(self) -> Path:
        return self.directories.database / QUEUE_DATABASE_FILENAME


def resolve_queue_configuration(
    data_root: str | PathLike[str] | None = None,
    *,
    workers: int = DEFAULT_WORKER_COUNT,
) -> QueueConfiguration:
    return QueueConfiguration(resolve_local_data_directories(data_root), workers)


def create_huey(configuration: QueueConfiguration | None = None) -> Any:
    effective_configuration = configuration or resolve_queue_configuration()
    ensure_local_data_directories(effective_configuration.directories)
    return SqliteHuey(
        QUEUE_NAME,
        filename=str(effective_configuration.database_path),
    )


def create_consumer(configuration: QueueConfiguration | None = None) -> Any:
    effective_configuration = configuration or resolve_queue_configuration()
    huey = create_huey(effective_configuration)
    return huey.create_consumer(
        workers=effective_configuration.workers,
        worker_type="thread",
    )
