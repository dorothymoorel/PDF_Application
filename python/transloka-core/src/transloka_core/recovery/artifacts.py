import hashlib
from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path

_CHUNK_SIZE = 1024 * 1024


class ArtifactRecoveryError(RuntimeError):
    """Raised when a recovery request is unsafe or cannot be completed."""


class ArtifactKind(StrEnum):
    PAGE = "PAGE"
    EXPORT = "EXPORT"
    SNAPSHOT = "SNAPSHOT"
    BACKUP = "BACKUP"


class ArtifactRecoveryState(StrEnum):
    NONE = "NONE"
    INCOMPLETE_REMOVED = "INCOMPLETE_REMOVED"
    VALID_PRIOR_RESULT = "VALID_PRIOR_RESULT"
    PRESENT_UNVERIFIED = "PRESENT_UNVERIFIED"


@dataclass(frozen=True, slots=True)
class ArtifactDatabaseState:
    """The durable state and integrity metadata read from the database."""

    status: str
    is_complete: bool
    checksum_sha256: str | None = None
    size_bytes: int | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.status, str) or not self.status.strip():
            raise ValueError("Artifact database status must be a non-empty string.")
        if not isinstance(self.is_complete, bool):
            raise ValueError("Artifact database completion state must be boolean.")
        if (self.checksum_sha256 is None) != (self.size_bytes is None):
            raise ValueError("Artifact checksum and size must be supplied together.")
        if self.checksum_sha256 is not None:
            if len(self.checksum_sha256) != 64 or any(
                character not in "0123456789abcdef" for character in self.checksum_sha256
            ):
                raise ValueError("Artifact checksum must be a lowercase SHA-256 digest.")
            if (
                isinstance(self.size_bytes, bool)
                or not isinstance(self.size_bytes, int)
                or self.size_bytes < 0
            ):
                raise ValueError("Artifact size must be a non-negative integer.")


@dataclass(frozen=True, slots=True)
class ArtifactRecoveryCandidate:
    """One artifact and the durable evidence used to recover it."""

    artifact_id: str
    kind: ArtifactKind
    temporary_paths: tuple[Path, ...] = ()
    final_path: Path | None = None
    completion_marker: Path | None = None
    database_state: ArtifactDatabaseState | None = None


@dataclass(frozen=True, slots=True)
class ArtifactRecoveryResult:
    artifact_id: str
    kind: ArtifactKind
    state: ArtifactRecoveryState
    removed_temporary_paths: tuple[Path, ...]
    preserved_final_path: Path | None
    database_status: str | None


@dataclass(frozen=True, slots=True)
class RecoveryReport:
    """A deterministic record of one stale-artifact recovery pass."""

    results: tuple[ArtifactRecoveryResult, ...]
    scanned_temporary_paths: tuple[Path, ...]
    removed_temporary_paths: tuple[Path, ...]


@dataclass(frozen=True, slots=True)
class _PreparedCandidate:
    artifact_id: str
    kind: ArtifactKind
    temporary_paths: tuple[Path, ...]
    final_path: Path | None
    completion_marker: Path | None
    database_state: ArtifactDatabaseState | None


class ArtifactRecoveryService:
    """Safely remove stale temporary artifacts and validate prior results.

    Recovery never deletes a final artifact. A final file is considered a valid
    prior result only when the database says the operation completed and its
    recorded size and checksum match the bytes on disk.
    """

    def __init__(self, *, data_root: Path, temporary_root: Path) -> None:
        self._data_root = _validate_root(data_root, "data")
        self._temporary_root = _validate_root(temporary_root, "temporary")
        if self._temporary_root == self._data_root or not self._temporary_root.is_relative_to(
            self._data_root
        ):
            raise ArtifactRecoveryError("Temporary storage must remain below the data root.")

    def recover(self, candidates: Iterable[ArtifactRecoveryCandidate] = ()) -> RecoveryReport:
        prepared = self._prepare_candidates(candidates)
        scanned = self.scan_temporary_artifacts()
        removable = set(scanned)
        for candidate in prepared:
            removable.update(candidate.temporary_paths)

        existing_removable = tuple(sorted(path for path in removable if path.is_file()))
        removed: list[Path] = []
        results: list[ArtifactRecoveryResult] = []
        claimed: set[Path] = set()

        for candidate in prepared:
            candidate_removed = tuple(
                path for path in candidate.temporary_paths if path in existing_removable
            )
            for path in candidate_removed:
                claimed.add(path)
                self._remove_temporary(path)
                removed.append(path)

            state = self._inspect_final(candidate)
            results.append(
                ArtifactRecoveryResult(
                    artifact_id=candidate.artifact_id,
                    kind=candidate.kind,
                    state=(
                        ArtifactRecoveryState.INCOMPLETE_REMOVED
                        if candidate_removed and state is ArtifactRecoveryState.NONE
                        else state
                    ),
                    removed_temporary_paths=candidate_removed,
                    preserved_final_path=(
                        candidate.final_path
                        if state is ArtifactRecoveryState.VALID_PRIOR_RESULT
                        else None
                    ),
                    database_status=(
                        candidate.database_state.status
                        if candidate.database_state is not None
                        else None
                    ),
                )
            )

        for path in existing_removable:
            if path in claimed:
                continue
            self._remove_temporary(path)
            removed.append(path)

        return RecoveryReport(
            results=tuple(results),
            scanned_temporary_paths=tuple(sorted(scanned)),
            removed_temporary_paths=tuple(sorted(removed)),
        )

    def scan_temporary_artifacts(self) -> tuple[Path, ...]:
        """Return regular temporary files that are eligible for stale cleanup."""

        return self._scan_temporary_root()

    def _prepare_candidates(
        self, candidates: Iterable[ArtifactRecoveryCandidate]
    ) -> tuple[_PreparedCandidate, ...]:
        try:
            values = tuple(candidates)
        except TypeError as exc:
            raise ArtifactRecoveryError("Recovery candidates must be iterable.") from exc

        prepared: list[_PreparedCandidate] = []
        seen_ids: set[str] = set()
        seen_temporary_paths: set[Path] = set()
        for candidate in values:
            if not isinstance(candidate, ArtifactRecoveryCandidate):
                raise ArtifactRecoveryError("Recovery candidate metadata is invalid.")
            if (
                not isinstance(candidate.artifact_id, str)
                or not candidate.artifact_id.strip()
                or candidate.artifact_id in seen_ids
            ):
                raise ArtifactRecoveryError("Recovery artifact identifiers must be unique.")
            if not isinstance(candidate.kind, ArtifactKind):
                raise ArtifactRecoveryError("Recovery artifact kind is invalid.")
            seen_ids.add(candidate.artifact_id)
            temporary_paths = tuple(
                self._controlled_temporary_path(path) for path in candidate.temporary_paths
            )
            if len(set(temporary_paths)) != len(
                temporary_paths
            ) or seen_temporary_paths.intersection(temporary_paths):
                raise ArtifactRecoveryError("Temporary artifacts may belong to only one candidate.")
            seen_temporary_paths.update(temporary_paths)
            final_path = (
                self._controlled_final_path(candidate.final_path)
                if candidate.final_path is not None
                else None
            )
            completion_marker = (
                self._controlled_final_path(candidate.completion_marker)
                if candidate.completion_marker is not None
                else None
            )
            if completion_marker is not None and final_path is None:
                raise ArtifactRecoveryError("A completion marker requires a final artifact.")
            if candidate.database_state is not None and not isinstance(
                candidate.database_state, ArtifactDatabaseState
            ):
                raise ArtifactRecoveryError("Artifact database state is invalid.")
            prepared.append(
                _PreparedCandidate(
                    artifact_id=candidate.artifact_id,
                    kind=candidate.kind,
                    temporary_paths=temporary_paths,
                    final_path=final_path,
                    completion_marker=completion_marker,
                    database_state=candidate.database_state,
                )
            )
        return tuple(prepared)

    def _scan_temporary_root(self) -> tuple[Path, ...]:
        if not self._temporary_root.exists():
            return ()
        if self._temporary_root.is_symlink() or not self._temporary_root.is_dir():
            raise ArtifactRecoveryError("Temporary storage must be a regular directory.")
        found: list[Path] = []
        try:
            for path in self._temporary_root.rglob("*"):
                if path.is_symlink() or not path.is_file():
                    continue
                resolved = path.resolve(strict=False)
                if resolved.is_relative_to(self._temporary_root):
                    found.append(resolved)
        except OSError as exc:
            raise ArtifactRecoveryError("Temporary artifacts could not be scanned.") from exc
        return tuple(sorted(set(found)))

    def _controlled_temporary_path(self, path: Path) -> Path:
        resolved = _validate_path(path, "temporary artifact")
        if resolved == self._temporary_root or not resolved.is_relative_to(self._temporary_root):
            raise ArtifactRecoveryError("Temporary artifacts must remain in temporary storage.")
        return resolved

    def _controlled_final_path(self, path: Path) -> Path:
        resolved = _validate_path(path, "final artifact")
        if (
            resolved == self._data_root
            or not resolved.is_relative_to(self._data_root)
            or resolved.is_relative_to(self._temporary_root)
        ):
            raise ArtifactRecoveryError("Final artifacts must remain in managed final storage.")
        return resolved

    @staticmethod
    def _remove_temporary(path: Path) -> None:
        try:
            if path.is_symlink() or not path.is_file():
                return
            path.unlink(missing_ok=True)
        except OSError as exc:
            raise ArtifactRecoveryError(
                "An incomplete temporary artifact could not be removed."
            ) from exc

    @staticmethod
    def _inspect_final(candidate: _PreparedCandidate) -> ArtifactRecoveryState:
        if candidate.final_path is None:
            return ArtifactRecoveryState.NONE
        final_path = candidate.final_path
        if final_path.is_symlink() or not final_path.is_file():
            return ArtifactRecoveryState.PRESENT_UNVERIFIED
        state = candidate.database_state
        if state is None or not state.is_complete:
            return ArtifactRecoveryState.PRESENT_UNVERIFIED
        if candidate.completion_marker is not None:
            marker = candidate.completion_marker
            if marker.is_symlink() or not marker.is_file():
                return ArtifactRecoveryState.PRESENT_UNVERIFIED
        if state.checksum_sha256 is None or state.size_bytes is None:
            return ArtifactRecoveryState.PRESENT_UNVERIFIED
        try:
            if final_path.stat().st_size != state.size_bytes:
                return ArtifactRecoveryState.PRESENT_UNVERIFIED
            return (
                ArtifactRecoveryState.VALID_PRIOR_RESULT
                if _checksum(final_path) == state.checksum_sha256
                else ArtifactRecoveryState.PRESENT_UNVERIFIED
            )
        except OSError as exc:
            raise ArtifactRecoveryError("The final artifact could not be inspected.") from exc


def _validate_root(path: Path, label: str) -> Path:
    if not isinstance(path, Path) or not path.is_absolute():
        raise ArtifactRecoveryError(f"The {label} storage root must be absolute.")
    resolved = path.resolve(strict=False)
    if resolved == Path(resolved.anchor):
        raise ArtifactRecoveryError(f"The {label} storage root is unsafe.")
    return resolved


def _validate_path(path: Path, label: str) -> Path:
    if not isinstance(path, Path) or not path.is_absolute() or path.is_symlink():
        raise ArtifactRecoveryError(f"The {label} path must be a safe absolute path.")
    if path.exists() and not path.is_file():
        raise ArtifactRecoveryError(f"The {label} path must be a regular file.")
    return path.resolve(strict=False)


def _checksum(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(_CHUNK_SIZE), b""):
            digest.update(chunk)
    return digest.hexdigest()
