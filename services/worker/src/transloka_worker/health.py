import math
import os
import time
from collections.abc import Callable
from dataclasses import dataclass
from enum import StrEnum
from threading import Lock
from typing import Any

WORKER_HEARTBEAT_KEY = "transloka.worker.heartbeat.v1"
WORKER_HEARTBEAT_SCHEMA = "transloka.worker.heartbeat.v1"
WORKER_NAME = "transloka-worker"


class WorkerStatus(StrEnum):
    STOPPED = "STOPPED"
    RUNNING = "RUNNING"


@dataclass(frozen=True, slots=True)
class PersistedWorkerHeartbeat:
    worker_name: str
    worker_identifier: str
    status: WorkerStatus
    sequence: int
    recorded_at: float


class WorkerHeartbeatStore:
    def __init__(
        self,
        huey: Any,
        *,
        worker_identifier: str | None = None,
        clock: Callable[[], float] = time.time,
    ) -> None:
        identifier = worker_identifier or f"{WORKER_NAME}-{os.getpid()}"
        if not identifier or identifier != identifier.strip() or not identifier.isprintable():
            raise ValueError("Worker identifier is invalid.")
        self._huey = huey
        self._worker_identifier = identifier
        self._clock = clock
        self._sequence = 0
        self._lock = Lock()

    def record(self, status: WorkerStatus) -> PersistedWorkerHeartbeat:
        with self._lock:
            recorded_at = self._clock()
            if not math.isfinite(recorded_at) or recorded_at < 0:
                raise ValueError("Heartbeat time must be a non-negative finite number.")
            self._sequence += 1
            heartbeat = PersistedWorkerHeartbeat(
                worker_name=WORKER_NAME,
                worker_identifier=self._worker_identifier,
                status=status,
                sequence=self._sequence,
                recorded_at=recorded_at,
            )
            self._huey.put(
                WORKER_HEARTBEAT_KEY,
                {
                    "schema": WORKER_HEARTBEAT_SCHEMA,
                    "worker_name": heartbeat.worker_name,
                    "worker_identifier": heartbeat.worker_identifier,
                    "status": heartbeat.status.value,
                    "sequence": heartbeat.sequence,
                    "recorded_at": heartbeat.recorded_at,
                },
            )
            return heartbeat

    def read(self) -> PersistedWorkerHeartbeat | None:
        value = self._huey.get(WORKER_HEARTBEAT_KEY, peek=True)
        if not isinstance(value, dict) or set(value) != {
            "schema",
            "worker_name",
            "worker_identifier",
            "status",
            "sequence",
            "recorded_at",
        }:
            return None
        if value["schema"] != WORKER_HEARTBEAT_SCHEMA or value["worker_name"] != WORKER_NAME:
            return None
        identifier = value["worker_identifier"]
        sequence = value["sequence"]
        recorded_at = value["recorded_at"]
        if (
            not isinstance(identifier, str)
            or not identifier
            or identifier != identifier.strip()
            or not identifier.isprintable()
            or isinstance(sequence, bool)
            or not isinstance(sequence, int)
            or sequence < 1
            or isinstance(recorded_at, bool)
            or not isinstance(recorded_at, (int, float))
            or not math.isfinite(recorded_at)
            or recorded_at < 0
        ):
            return None
        try:
            status = WorkerStatus(value["status"])
        except (TypeError, ValueError):
            return None
        return PersistedWorkerHeartbeat(
            worker_name=WORKER_NAME,
            worker_identifier=identifier,
            status=status,
            sequence=sequence,
            recorded_at=float(recorded_at),
        )
