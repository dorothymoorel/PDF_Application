import hashlib
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker
from transloka_core.database import transaction_scope
from transloka_core.database.models.jobs import (
    ApplicationJob,
    JobAttempt,
    JobAttemptStatus,
    JobStatus,
)

DEFAULT_STALE_THRESHOLD = timedelta(minutes=5)
_STALE_ERROR_CODE = "WORKER_HEARTBEAT_STALE"
_STALE_ERROR_MESSAGE = "The worker heartbeat expired before the job completed."
_CHUNK_SIZE = 1024 * 1024


class RecoveryArtifactState(StrEnum):
    NONE = "NONE"
    INCOMPLETE_REMOVED = "INCOMPLETE_REMOVED"
    PRESENT_UNVERIFIED = "PRESENT_UNVERIFIED"
    VALID_ATOMIC = "VALID_ATOMIC"


class JobRecoveryError(RuntimeError):
    pass


class RecoveryArtifactError(JobRecoveryError):
    pass


@dataclass(frozen=True, slots=True)
class RecoveryArtifact:
    incomplete_outputs: tuple[Path, ...] = ()
    final_output: Path | None = None
    checksum_sha256: str | None = None
    size_bytes: int | None = None


@dataclass(frozen=True, slots=True)
class JobRecoveryResult:
    job_id: str
    status: JobStatus
    artifact_state: RecoveryArtifactState
    retry_available: bool


@dataclass(frozen=True, slots=True)
class _Candidate:
    job_id: str
    heartbeat_at: str | None
    started_at: str | None
    created_at: str


class JobRecoveryService:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        *,
        data_root: Path,
        temporary_root: Path,
    ) -> None:
        if not data_root.is_absolute() or not temporary_root.is_absolute():
            raise ValueError("Recovery storage roots must be absolute paths.")
        resolved_data_root = data_root.resolve(strict=False)
        resolved_temporary_root = temporary_root.resolve(strict=False)
        if (
            resolved_temporary_root == resolved_data_root
            or not resolved_temporary_root.is_relative_to(resolved_data_root)
        ):
            raise ValueError("Temporary storage must remain below the data root.")
        self._session_factory = session_factory
        self._data_root = resolved_data_root
        self._temporary_root = resolved_temporary_root

    def recover(
        self,
        *,
        stale_threshold: timedelta = DEFAULT_STALE_THRESHOLD,
        artifacts: Mapping[str, RecoveryArtifact] | None = None,
        now: datetime | None = None,
    ) -> tuple[JobRecoveryResult, ...]:
        threshold = _validate_threshold(stale_threshold)
        recovery_time = _validate_now(now or datetime.now(UTC))
        cutoff = recovery_time - threshold
        artifact_map = artifacts or {}
        results: list[JobRecoveryResult] = []

        for candidate in self._running_jobs():
            if not _is_stale(candidate, cutoff):
                continue
            artifact = artifact_map.get(candidate.job_id, RecoveryArtifact())
            if not isinstance(artifact, RecoveryArtifact):
                raise RecoveryArtifactError("Recovery artifact metadata is invalid.")
            prepared = self._prepare_artifact(artifact)
            if not self._mark_stale(candidate.job_id, cutoff, recovery_time):
                continue
            artifact_state = self._inspect_and_cleanup(prepared)
            with self._session_factory() as session:
                row = session.get(ApplicationJob, candidate.job_id)
                if row is None:
                    raise JobRecoveryError("A recovered job could not be read.")
                results.append(
                    JobRecoveryResult(
                        job_id=row.id,
                        status=JobStatus(row.status),
                        artifact_state=artifact_state,
                        retry_available=row.retry_count < row.max_retries,
                    )
                )
        return tuple(results)

    def _running_jobs(self) -> tuple[_Candidate, ...]:
        with self._session_factory() as session:
            rows = session.scalars(
                select(ApplicationJob)
                .where(ApplicationJob.status == JobStatus.RUNNING.value)
                .order_by(ApplicationJob.created_at, ApplicationJob.id)
            ).all()
            return tuple(
                _Candidate(
                    job_id=row.id,
                    heartbeat_at=row.heartbeat_at,
                    started_at=row.started_at,
                    created_at=row.created_at,
                )
                for row in rows
            )

    def _mark_stale(self, job_id: str, cutoff: datetime, recovery_time: datetime) -> bool:
        completed_at = _format_timestamp(recovery_time)
        with transaction_scope(self._session_factory) as session:
            row = session.get(ApplicationJob, job_id)
            if row is None:
                return False
            candidate = _Candidate(
                job_id=row.id,
                heartbeat_at=row.heartbeat_at,
                started_at=row.started_at,
                created_at=row.created_at,
            )
            if row.status != JobStatus.RUNNING.value or not _is_stale(candidate, cutoff):
                return False

            row.status = JobStatus.STALE.value
            row.current_stage = JobStatus.STALE.value
            row.completed_at = completed_at
            row.error_code = _STALE_ERROR_CODE
            row.error_message = _STALE_ERROR_MESSAGE
            _finalize_attempt(session, row, completed_at)
            session.flush()
            return True

    def _prepare_artifact(self, artifact: RecoveryArtifact) -> RecoveryArtifact:
        incomplete_outputs = tuple(
            self._controlled_temporary_output(path) for path in artifact.incomplete_outputs
        )
        final_output = (
            self._controlled_final_output(artifact.final_output)
            if artifact.final_output is not None
            else None
        )
        if (artifact.checksum_sha256 is None) != (artifact.size_bytes is None):
            raise RecoveryArtifactError(
                "Final artifact checksum and size must be supplied together."
            )
        if final_output is None and artifact.checksum_sha256 is not None:
            raise RecoveryArtifactError(
                "Final artifact integrity metadata requires a final output."
            )
        if artifact.checksum_sha256 is not None:
            _validate_checksum(artifact.checksum_sha256)
            if (
                isinstance(artifact.size_bytes, bool)
                or not isinstance(artifact.size_bytes, int)
                or artifact.size_bytes < 0
            ):
                raise RecoveryArtifactError("Final artifact size is invalid.")
        return RecoveryArtifact(
            incomplete_outputs=incomplete_outputs,
            final_output=final_output,
            checksum_sha256=artifact.checksum_sha256,
            size_bytes=artifact.size_bytes,
        )

    def _controlled_temporary_output(self, path: Path) -> Path:
        resolved = _validate_absolute_file_path(path)
        if resolved == self._temporary_root or not resolved.is_relative_to(self._temporary_root):
            raise RecoveryArtifactError("Incomplete outputs must remain in temporary storage.")
        return resolved

    def _controlled_final_output(self, path: Path) -> Path:
        resolved = _validate_absolute_file_path(path)
        if (
            resolved == self._data_root
            or not resolved.is_relative_to(self._data_root)
            or resolved.is_relative_to(self._temporary_root)
        ):
            raise RecoveryArtifactError("Final artifacts must remain in managed final storage.")
        return resolved

    @staticmethod
    def _inspect_and_cleanup(artifact: RecoveryArtifact) -> RecoveryArtifactState:
        try:
            for path in artifact.incomplete_outputs:
                path.unlink(missing_ok=True)
        except OSError as exc:
            raise RecoveryArtifactError(
                "An incomplete recovery output could not be removed."
            ) from exc

        if artifact.final_output is None:
            return (
                RecoveryArtifactState.INCOMPLETE_REMOVED
                if artifact.incomplete_outputs
                else RecoveryArtifactState.NONE
            )
        if artifact.final_output.is_symlink() or not artifact.final_output.is_file():
            return RecoveryArtifactState.PRESENT_UNVERIFIED
        if artifact.checksum_sha256 is None or artifact.size_bytes is None:
            return RecoveryArtifactState.PRESENT_UNVERIFIED
        try:
            valid = (
                artifact.final_output.stat().st_size == artifact.size_bytes
                and _checksum(artifact.final_output) == artifact.checksum_sha256
            )
        except OSError as exc:
            raise RecoveryArtifactError(
                "The final recovery artifact could not be inspected."
            ) from exc
        return (
            RecoveryArtifactState.VALID_ATOMIC
            if valid
            else RecoveryArtifactState.PRESENT_UNVERIFIED
        )


def _finalize_attempt(session: Session, row: ApplicationJob, completed_at: str) -> None:
    attempts = list(
        session.scalars(
            select(JobAttempt)
            .where(JobAttempt.job_id == row.id)
            .order_by(JobAttempt.attempt_number)
        )
    )
    expected_numbers = list(range(1, len(attempts) + 1))
    if [attempt.attempt_number for attempt in attempts] != expected_numbers:
        raise JobRecoveryError("The stored job attempt history is incomplete.")
    if any(attempt.status == JobAttemptStatus.RUNNING.value for attempt in attempts[:-1]):
        raise JobRecoveryError("The stored job attempt history is invalid.")

    if attempts and attempts[-1].status == JobAttemptStatus.RUNNING.value:
        attempt = attempts[-1]
        attempt.status = JobAttemptStatus.STALE.value
        attempt.completed_at = completed_at
        attempt.error_code = _STALE_ERROR_CODE
        attempt.error_message = _STALE_ERROR_MESSAGE
        return

    attempt_number = len(attempts) + 1
    session.add(
        JobAttempt(
            id=str(uuid5(NAMESPACE_URL, f"transloka:job-attempt:{row.id}:{attempt_number}")),
            job_id=row.id,
            attempt_number=attempt_number,
            status=JobAttemptStatus.STALE.value,
            worker_identifier=None,
            started_at=row.started_at or row.created_at,
            completed_at=completed_at,
            duration_ms=None,
            error_code=_STALE_ERROR_CODE,
            error_message=_STALE_ERROR_MESSAGE,
            details_json=None,
        )
    )


def _is_stale(candidate: _Candidate, cutoff: datetime) -> bool:
    timestamp = candidate.heartbeat_at or candidate.started_at or candidate.created_at
    try:
        return _parse_timestamp(timestamp) <= cutoff
    except ValueError:
        return True


def _parse_timestamp(value: str) -> datetime:
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError
    return parsed.astimezone(UTC)


def _validate_threshold(value: timedelta) -> timedelta:
    if not isinstance(value, timedelta) or value <= timedelta(0):
        raise ValueError("The stale threshold must be positive.")
    return value


def _validate_now(value: datetime) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise ValueError("Recovery time must include a timezone.")
    return value.astimezone(UTC)


def _validate_absolute_file_path(path: Path) -> Path:
    if not isinstance(path, Path) or not path.is_absolute() or path.is_symlink():
        raise RecoveryArtifactError("Recovery artifacts must use safe absolute paths.")
    if path.exists() and not path.is_file():
        raise RecoveryArtifactError("Recovery artifacts must be regular files.")
    return path.resolve(strict=False)


def _validate_checksum(value: str) -> None:
    if len(value) != 64 or any(character not in "0123456789abcdef" for character in value):
        raise RecoveryArtifactError("Final artifact checksum is invalid.")


def _checksum(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(_CHUNK_SIZE), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _format_timestamp(value: datetime) -> str:
    return value.isoformat(timespec="milliseconds").replace("+00:00", "Z")
