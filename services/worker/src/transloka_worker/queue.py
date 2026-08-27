from collections.abc import Callable
from dataclasses import dataclass
from os import PathLike
from pathlib import Path
from typing import Any, Never

from huey import SqliteHuey  # type: ignore[import-untyped]
from huey.signals import SIGNAL_INTERRUPTED  # type: ignore[import-untyped]
from transloka_core.storage import (
    LocalDataDirectories,
    ensure_local_data_directories,
    resolve_local_data_directories,
)

from transloka_worker.maintenance import MaintenanceGate
from transloka_worker.tasks.ocr import register_ocr_task
from transloka_worker.tasks.translation import register_translation_task

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


@dataclass(slots=True)
class TranslationQueueProducer:
    queue: HueyJobQueue
    huey: Any

    def close(self) -> None:
        self.huey.storage.close()


@dataclass(slots=True)
class OCRQueueProducer:
    queue: HueyJobQueue
    huey: Any

    def close(self) -> None:
        self.huey.storage.close()


def resolve_queue_configuration(
    data_root: str | PathLike[str] | None = None,
    *,
    workers: int = DEFAULT_WORKER_COUNT,
) -> QueueConfiguration:
    return QueueConfiguration(resolve_local_data_directories(data_root), workers)


def create_huey(configuration: QueueConfiguration | None = None) -> Any:
    effective_configuration = configuration or resolve_queue_configuration()
    ensure_local_data_directories(effective_configuration.directories)
    huey = SqliteHuey(
        QUEUE_NAME,
        filename=str(effective_configuration.database_path),
    )
    maintenance_gate = MaintenanceGate(effective_configuration.directories)

    @huey.pre_execute("transloka-maintenance-gate")  # type: ignore[untyped-decorator]
    def enforce_maintenance_gate(_task: object) -> None:
        maintenance_gate.start_task(_task)

    @huey.post_execute("transloka-maintenance-release")  # type: ignore[untyped-decorator]
    def release_maintenance_gate(
        task: object,
        _task_value: object,
        _exception: BaseException | None,
    ) -> None:
        maintenance_gate.finish_task(task)

    @huey.signal(SIGNAL_INTERRUPTED)  # type: ignore[untyped-decorator]
    def release_interrupted_task(
        _signal: str,
        task: object,
        *_args: object,
        **_kwargs: object,
    ) -> None:
        maintenance_gate.finish_task(task)

    return huey


def create_translation_producer(
    configuration: QueueConfiguration | None = None,
) -> TranslationQueueProducer:
    huey = create_huey(configuration)

    def producer_only(_job_id: str) -> Never:
        raise RuntimeError("The API translation producer cannot execute tasks.")

    task = register_translation_task(huey, producer_only)
    return TranslationQueueProducer(HueyJobQueue(task), huey)


def create_ocr_producer(
    configuration: QueueConfiguration | None = None,
) -> OCRQueueProducer:
    huey = create_huey(configuration)

    def producer_only(_job_id: str) -> Never:
        raise RuntimeError("The API OCR producer cannot execute tasks.")

    task = register_ocr_task(huey, producer_only)
    return OCRQueueProducer(HueyJobQueue(task), huey)


def create_consumer(
    configuration: QueueConfiguration | None = None,
    *,
    register_tasks: Callable[[Any], None] | None = None,
) -> Any:
    effective_configuration = configuration or resolve_queue_configuration()
    huey = create_huey(effective_configuration)
    try:
        if register_tasks is not None:
            register_tasks(huey)
        return huey.create_consumer(
            workers=effective_configuration.workers,
            worker_type="thread",
        )
    except Exception:
        huey.storage.close()
        raise
