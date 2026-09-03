import logging
import math
import signal
import time
from collections.abc import Callable
from dataclasses import dataclass
from threading import Event, Lock, Thread
from types import FrameType
from typing import Protocol, cast

from transloka_core.database import create_session_factory, create_sqlite_engine
from transloka_core.storage.local import LocalFileStorage
from transloka_documents.ocr import OCRProvider
from transloka_documents.ocr.orchestration import OCRPageOrchestrator, OCRRawOutputStore
from transloka_documents.ocr.paddle import PaddleOCRProviderAdapter

from transloka_worker.analysis import DatabaseAnalysisJobRunner
from transloka_worker.backup import DatabaseBackupRequestLoader, ProductionBackupJobRunner
from transloka_worker.health import WORKER_NAME, WorkerHeartbeatStore, WorkerStatus
from transloka_worker.ocr import DatabaseOCRRequestLoader, OCRJobRunner
from transloka_worker.queue import QueueConfiguration, create_consumer, resolve_queue_configuration
from transloka_worker.reconstruction import (
    DatabaseReconstructionRequestLoader,
    ProductionReconstructionJobRunner,
)
from transloka_worker.tasks.analysis import register_analysis_task
from transloka_worker.tasks.backup import register_backup_task
from transloka_worker.tasks.ocr import register_ocr_task
from transloka_worker.tasks.reconstruction import register_reconstruction_task
from transloka_worker.tasks.translation import register_translation_task
from transloka_worker.translation import (
    DatabaseTranslationOperationLoader,
    ProductionTranslationJobRunner,
)

logger = logging.getLogger(__name__)

DEFAULT_HEARTBEAT_INTERVAL_SECONDS = 5.0


@dataclass(frozen=True, slots=True)
class HeartbeatState:
    worker_name: str
    status: WorkerStatus
    sequence: int
    recorded_at: float | None


class Consumer(Protocol):
    def run(self) -> None: ...

    def stop(self, graceful: bool = False) -> None: ...


class WorkerProcess(Protocol):
    def run(self) -> None: ...

    def stop(self) -> None: ...


class QueueWorker:
    def __init__(
        self,
        consumer: Consumer,
        *,
        close_resources: Callable[[], None] | None = None,
        heartbeat_store: WorkerHeartbeatStore | None = None,
        heartbeat_interval_seconds: float = DEFAULT_HEARTBEAT_INTERVAL_SECONDS,
    ) -> None:
        if not math.isfinite(heartbeat_interval_seconds) or heartbeat_interval_seconds <= 0:
            raise ValueError("Heartbeat interval must be a positive finite number.")
        self._consumer = consumer
        self._close_resources = close_resources
        self._heartbeat_store = heartbeat_store
        self._heartbeat_interval_seconds = heartbeat_interval_seconds
        self._heartbeat_stop = Event()

    def run(self) -> None:
        heartbeat_thread: Thread | None = None
        try:
            if self._heartbeat_store is not None:
                self._heartbeat_store.record(WorkerStatus.RUNNING)
                heartbeat_thread = Thread(
                    target=self._emit_heartbeats,
                    name="transloka-worker-heartbeat",
                    daemon=True,
                )
                heartbeat_thread.start()
            self._consumer.run()
        finally:
            self._heartbeat_stop.set()
            if heartbeat_thread is not None:
                heartbeat_thread.join(timeout=self._heartbeat_interval_seconds + 1.0)
            self._record_stopped_heartbeat()
            self.close_resources()

    def stop(self) -> None:
        self._consumer.stop(graceful=True)

    def close_resources(self) -> None:
        if self._close_resources is not None:
            self._close_resources()

    def _emit_heartbeats(self) -> None:
        while not self._heartbeat_stop.wait(self._heartbeat_interval_seconds):
            try:
                if self._heartbeat_store is not None:
                    self._heartbeat_store.record(WorkerStatus.RUNNING)
            except Exception as exc:
                logger.error(
                    "Worker heartbeat failed",
                    extra={
                        "worker_name": WORKER_NAME,
                        "error_type": type(exc).__name__,
                    },
                )
                self._consumer.stop(graceful=True)
                return

    def _record_stopped_heartbeat(self) -> None:
        if self._heartbeat_store is None:
            return
        try:
            self._heartbeat_store.record(WorkerStatus.STOPPED)
        except Exception as exc:
            logger.error(
                "Worker stopped heartbeat failed",
                extra={
                    "worker_name": WORKER_NAME,
                    "error_type": type(exc).__name__,
                },
            )


def create_queue_worker(
    configuration: QueueConfiguration | None = None,
    *,
    provider_factory: Callable[[str], object] | None = None,
    ocr_provider_factory: Callable[[], OCRProvider] | None = None,
    worker_identifier: str | None = None,
) -> QueueWorker:
    effective_configuration = configuration or resolve_queue_configuration()
    directories = effective_configuration.directories
    engine = create_sqlite_engine(directories)
    session_factory = create_session_factory(engine)
    storage = LocalFileStorage(directories)
    analysis_runner = DatabaseAnalysisJobRunner(
        session_factory,
        storage,
        worker_identifier=worker_identifier,
    )
    loader = DatabaseTranslationOperationLoader(
        session_factory,
        storage,
    )
    runner = ProductionTranslationJobRunner(
        loader,
        session_factory,
        directories.temporary,
        provider_factory=provider_factory,
        worker_identifier=worker_identifier,
    )
    ocr_provider = (
        ocr_provider_factory()
        if ocr_provider_factory is not None
        else PaddleOCRProviderAdapter(model_cache_dir=directories.cache / "paddleocr")
    )
    ocr_loader = DatabaseOCRRequestLoader(session_factory, storage)
    ocr_runner = OCRJobRunner(
        OCRPageOrchestrator(
            ocr_provider,
            storage,
            raw_output_store=OCRRawOutputStore(storage, session_factory),
        ),
        ocr_loader,
        session_factory,
        directories.temporary,
        worker_identifier=worker_identifier,
    )
    reconstruction_loader = DatabaseReconstructionRequestLoader(session_factory, storage)
    reconstruction_runner = ProductionReconstructionJobRunner(
        reconstruction_loader,
        session_factory,
        storage,
        directories.temporary,
        worker_identifier=worker_identifier,
    )
    backup_loader = DatabaseBackupRequestLoader(session_factory)
    backup_runner = ProductionBackupJobRunner(
        backup_loader,
        session_factory,
        directories,
        worker_identifier=worker_identifier,
    )

    def register_tasks(huey: object) -> None:
        register_analysis_task(huey, analysis_runner.run)
        register_translation_task(huey, runner.run)
        register_ocr_task(huey, ocr_runner.run)
        register_reconstruction_task(huey, reconstruction_runner.run)
        register_backup_task(huey, backup_runner.run)

    try:
        consumer = cast(
            Consumer,
            create_consumer(
                effective_configuration,
                register_tasks=register_tasks,
            ),
        )
    except Exception:
        engine.dispose()
        raise

    closed = False

    def close_resources() -> None:
        nonlocal closed
        if closed:
            return
        closed = True
        cast(object, consumer).huey.storage.close()  # type: ignore[attr-defined]
        engine.dispose()

    heartbeat_store = WorkerHeartbeatStore(
        cast(object, consumer).huey,  # type: ignore[attr-defined]
        worker_identifier=worker_identifier,
    )
    return QueueWorker(
        consumer,
        close_resources=close_resources,
        heartbeat_store=heartbeat_store,
    )


class Worker:
    def __init__(
        self,
        heartbeat_interval_seconds: float = DEFAULT_HEARTBEAT_INTERVAL_SECONDS,
    ) -> None:
        if not math.isfinite(heartbeat_interval_seconds) or heartbeat_interval_seconds <= 0:
            raise ValueError("Heartbeat interval must be a positive finite number.")

        self._heartbeat_interval_seconds = heartbeat_interval_seconds
        self._stop_event = Event()
        self._state_lock = Lock()
        self._status = WorkerStatus.STOPPED
        self._heartbeat_sequence = 0
        self._heartbeat_recorded_at: float | None = None

    def heartbeat_state(self) -> HeartbeatState:
        with self._state_lock:
            return HeartbeatState(
                worker_name=WORKER_NAME,
                status=self._status,
                sequence=self._heartbeat_sequence,
                recorded_at=self._heartbeat_recorded_at,
            )

    def stop(self) -> None:
        self._stop_event.set()

    def run(self) -> None:
        with self._state_lock:
            if self._status is WorkerStatus.RUNNING:
                raise RuntimeError("Worker is already running.")
            self._status = WorkerStatus.RUNNING

        self._record_heartbeat()
        logger.info("Worker started", extra={"worker_name": WORKER_NAME})
        try:
            while not self._stop_event.wait(self._heartbeat_interval_seconds):
                self._record_heartbeat()
        finally:
            with self._state_lock:
                self._status = WorkerStatus.STOPPED
            logger.info("Worker stopped", extra={"worker_name": WORKER_NAME})

    def _record_heartbeat(self) -> None:
        with self._state_lock:
            self._heartbeat_sequence += 1
            self._heartbeat_recorded_at = time.monotonic()


def main(worker: WorkerProcess | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    active_worker = worker or create_queue_worker()

    def request_stop(_signal_number: int, _frame: FrameType | None) -> None:
        active_worker.stop()

    shutdown_signals = [signal.SIGINT, signal.SIGTERM]
    if hasattr(signal, "SIGBREAK"):
        shutdown_signals.append(signal.SIGBREAK)
    previous_handlers = {
        signal_number: signal.signal(signal_number, request_stop)
        for signal_number in shutdown_signals
    }
    try:
        active_worker.run()
    finally:
        for signal_number, previous_handler in previous_handlers.items():
            signal.signal(signal_number, previous_handler)
    return 0
