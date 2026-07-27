import logging
import math
import signal
import time
from dataclasses import dataclass
from enum import StrEnum
from threading import Event, Lock
from types import FrameType

logger = logging.getLogger(__name__)

WORKER_NAME = "transloka-worker"
DEFAULT_HEARTBEAT_INTERVAL_SECONDS = 5.0


class WorkerStatus(StrEnum):
    STOPPED = "STOPPED"
    RUNNING = "RUNNING"


@dataclass(frozen=True, slots=True)
class HeartbeatState:
    worker_name: str
    status: WorkerStatus
    sequence: int
    recorded_at: float | None


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


def main(worker: Worker | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    active_worker = worker or Worker()

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
