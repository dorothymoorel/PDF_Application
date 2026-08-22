"""Canonical backup manifests and on-disk verification."""

import hashlib
import json
import re
from collections.abc import Mapping
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from enum import StrEnum
from os import PathLike
from pathlib import Path, PurePosixPath
from typing import cast

MANIFEST_FORMAT_VERSION = 1
_SHA256_PATTERN = re.compile(r"[0-9a-f]{64}\Z")


class BackupManifestError(ValueError):
    """Raised when a backup manifest is invalid or cannot be verified."""


class BackupManifestVersionError(BackupManifestError):
    """Raised when a manifest uses an unsupported format version."""


class BackupManifestMissingFileError(BackupManifestError):
    """Raised when a manifest entry is not present below the verification root."""


class BackupManifestChecksumError(BackupManifestError):
    """Raised when a manifest entry does not match its recorded checksum."""


class BackupManifestSizeError(BackupManifestError):
    """Raised when a manifest entry does not match its recorded size."""


class BackupType(StrEnum):
    """Supported backup scopes."""

    DATABASE_ONLY = "DATABASE_ONLY"
    METADATA = "METADATA"
    FULL_PROJECTS = "FULL_PROJECTS"
    FULL_APPLICATION = "FULL_APPLICATION"
    PRE_RESTORE = "PRE_RESTORE"


@dataclass(frozen=True, slots=True)
class BackupManifestFile:
    """One relative file and the bytes expected in a backup archive."""

    path: str
    size_bytes: int
    checksum_sha256: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "path", _normalise_relative_path(self.path))
        if isinstance(self.size_bytes, bool) or not isinstance(self.size_bytes, int):
            raise BackupManifestError("Manifest file size must be an integer.")
        if self.size_bytes < 0:
            raise BackupManifestError("Manifest file size cannot be negative.")
        _validate_checksum(self.checksum_sha256)

    def to_dict(self) -> dict[str, object]:
        return {
            "path": self.path,
            "size_bytes": self.size_bytes,
            "checksum_sha256": self.checksum_sha256,
        }

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> "BackupManifestFile":
        try:
            path = payload["path"]
            size_bytes = payload["size_bytes"]
            checksum_sha256 = payload["checksum_sha256"]
        except KeyError as exc:
            raise BackupManifestError("Manifest file metadata is incomplete.") from exc
        if not isinstance(path, str) or not isinstance(checksum_sha256, str):
            raise BackupManifestError("Manifest file metadata has an invalid type.")
        if isinstance(size_bytes, bool) or not isinstance(size_bytes, int):
            raise BackupManifestError("Manifest file size must be an integer.")
        return cls(path=path, size_bytes=size_bytes, checksum_sha256=checksum_sha256)


ManifestFile = BackupManifestFile


@dataclass(frozen=True, slots=True)
class BackupManifest:
    """A manifest that is unverified until :meth:`verify` succeeds."""

    backup_type: BackupType
    application_version: str
    database_schema_version: str
    included_content: tuple[str, ...]
    files: tuple[BackupManifestFile, ...]
    created_at: str
    format_version: int = MANIFEST_FORMAT_VERSION
    verified: bool = False

    def __post_init__(self) -> None:
        if isinstance(self.backup_type, str):
            try:
                backup_type = BackupType(self.backup_type)
            except ValueError as exc:
                raise BackupManifestError("The backup type is unsupported.") from exc
            object.__setattr__(self, "backup_type", backup_type)
        if not isinstance(self.backup_type, BackupType):
            raise BackupManifestError("The backup type is unsupported.")
        if not isinstance(self.format_version, int) or isinstance(self.format_version, bool):
            raise BackupManifestVersionError("The manifest format version is invalid.")
        if self.format_version != MANIFEST_FORMAT_VERSION:
            raise BackupManifestVersionError(
                f"Manifest format version {self.format_version} is not supported."
            )
        _validate_text(self.application_version, "application version")
        _validate_text(self.database_schema_version, "database schema version")
        _validate_text(self.created_at, "created_at")
        if not self.included_content:
            raise BackupManifestError("A manifest must include at least one content path.")
        normalised_content = tuple(_normalise_relative_path(path) for path in self.included_content)
        if len(set(normalised_content)) != len(normalised_content):
            raise BackupManifestError("Manifest content paths must be unique.")
        object.__setattr__(self, "included_content", normalised_content)
        normalised_files = tuple(self.files)
        file_paths = tuple(file.path for file in normalised_files)
        if len(set(file_paths)) != len(file_paths):
            raise BackupManifestError("Manifest file paths must be unique.")
        if set(file_paths) != set(normalised_content):
            raise BackupManifestError("Included content and manifest files must match.")
        object.__setattr__(self, "files", normalised_files)
        if not isinstance(self.verified, bool):
            raise BackupManifestError("Manifest verification state is invalid.")

    @property
    def is_verified(self) -> bool:
        """Whether all manifest files passed verification in this process."""

        return self.verified

    def require_verified(self) -> None:
        """Reject use of a manifest that has not passed :meth:`verify`."""

        if not self.verified:
            raise BackupManifestError("The backup manifest must be verified before use.")

    def verify(self, root: str | PathLike[str]) -> "BackupManifest":
        """Verify every recorded file below *root* and return a verified copy."""

        root_path = Path(root).expanduser().resolve(strict=True)
        if not root_path.is_dir():
            raise BackupManifestMissingFileError("The backup verification root is not a directory.")
        for entry in self.files:
            path = _safe_child(root_path, entry.path)
            if not path.is_file():
                raise BackupManifestMissingFileError(f"The manifest file is missing: {entry.path}.")
            actual_size = path.stat().st_size
            if actual_size != entry.size_bytes:
                raise BackupManifestSizeError(
                    f"The manifest file size does not match: {entry.path}."
                )
            actual_checksum = _sha256_file(path)
            if actual_checksum != entry.checksum_sha256:
                raise BackupManifestChecksumError(
                    f"The manifest file checksum does not match: {entry.path}."
                )
        return replace(self, verified=True)

    def to_dict(self) -> dict[str, object]:
        """Return the canonical JSON-compatible representation."""

        return {
            "format_version": self.format_version,
            "backup_type": self.backup_type.value,
            "application_version": self.application_version,
            "database_schema_version": self.database_schema_version,
            "created_at": self.created_at,
            "included_content": list(self.included_content),
            "files": [file.to_dict() for file in self.files],
        }

    def to_json(self) -> bytes:
        """Serialize the manifest deterministically without verification metadata."""

        return json.dumps(
            self.to_dict(),
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")

    @classmethod
    def from_dict(cls, payload: Mapping[str, object]) -> "BackupManifest":
        """Parse a manifest and reset verification state until files are checked."""

        try:
            raw_format_version = payload["format_version"]
            raw_backup_type = payload["backup_type"]
            raw_application_version = payload["application_version"]
            raw_schema_version = payload["database_schema_version"]
            raw_created_at = payload["created_at"]
            raw_content = payload["included_content"]
            raw_files = payload["files"]
        except KeyError as exc:
            raise BackupManifestError("The backup manifest is missing required fields.") from exc
        if not isinstance(raw_format_version, int) or isinstance(raw_format_version, bool):
            raise BackupManifestVersionError("The manifest format version is invalid.")
        if not isinstance(raw_backup_type, str):
            raise BackupManifestError("The backup type is invalid.")
        if not isinstance(raw_application_version, str):
            raise BackupManifestError("The application version is invalid.")
        if not isinstance(raw_schema_version, str):
            raise BackupManifestError("The database schema version is invalid.")
        if not isinstance(raw_created_at, str):
            raise BackupManifestError("The manifest timestamp is invalid.")
        if not isinstance(raw_content, list) or not all(
            isinstance(path, str) for path in raw_content
        ):
            raise BackupManifestError("Manifest included content must be a list of paths.")
        if not isinstance(raw_files, list):
            raise BackupManifestError("Manifest files must be a list.")
        files = tuple(
            BackupManifestFile.from_dict(cast(Mapping[str, object], file))
            if isinstance(file, Mapping)
            else _invalid_file_entry()
            for file in raw_files
        )
        try:
            backup_type = BackupType(raw_backup_type)
        except ValueError as exc:
            raise BackupManifestError("The backup type is unsupported.") from exc
        return cls(
            backup_type=backup_type,
            application_version=raw_application_version,
            database_schema_version=raw_schema_version,
            included_content=tuple(raw_content),
            files=files,
            created_at=raw_created_at,
            format_version=raw_format_version,
        )

    @classmethod
    def from_json(cls, payload: bytes | str) -> "BackupManifest":
        if isinstance(payload, bytes):
            payload = payload.decode("utf-8")
        try:
            decoded = json.loads(payload)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise BackupManifestError("The backup manifest JSON is invalid.") from exc
        if not isinstance(decoded, Mapping):
            raise BackupManifestError("The backup manifest must be a JSON object.")
        return cls.from_dict(decoded)


def build_manifest(
    *,
    backup_type: BackupType | str,
    application_version: str,
    database_schema_version: str,
    root: str | PathLike[str],
    included_content: tuple[str, ...] | list[str],
    created_at: str | None = None,
) -> BackupManifest:
    """Build a manifest from files below *root* without marking it verified."""

    root_path = Path(root).expanduser().resolve(strict=True)
    if not root_path.is_dir():
        raise BackupManifestMissingFileError("The backup manifest root is not a directory.")
    files = tuple(_file_metadata(_safe_child(root_path, path), path) for path in included_content)
    timestamp = _timestamp(created_at)
    try:
        manifest_type = BackupType(backup_type)
    except ValueError as exc:
        raise BackupManifestError("The backup type is unsupported.") from exc
    return BackupManifest(
        backup_type=manifest_type,
        application_version=application_version,
        database_schema_version=database_schema_version,
        included_content=tuple(included_content),
        files=files,
        created_at=timestamp,
    )


create_manifest = build_manifest


def verify_manifest(
    manifest: BackupManifest,
    root: str | PathLike[str],
) -> BackupManifest:
    """Verify a manifest and return the verified copy."""

    if not isinstance(manifest, BackupManifest):
        raise TypeError("A BackupManifest is required.")
    return manifest.verify(root)


def load_manifest(payload: bytes | str) -> BackupManifest:
    """Load a manifest from canonical JSON while keeping it unverified."""

    return BackupManifest.from_json(payload)


def _file_metadata(path: Path, relative_path: str) -> BackupManifestFile:
    if not path.is_file():
        raise BackupManifestMissingFileError(f"The manifest file is missing: {relative_path}.")
    return BackupManifestFile(
        path=relative_path,
        size_bytes=path.stat().st_size,
        checksum_sha256=_sha256_file(path),
    )


def _safe_child(root: Path, relative_path: str) -> Path:
    normalised = _normalise_relative_path(relative_path)
    path = (root / Path(*PurePosixPath(normalised).parts)).resolve(strict=False)
    if not path.is_relative_to(root):
        raise BackupManifestError(f"The manifest path escapes its root: {relative_path}.")
    return path


def _normalise_relative_path(value: str) -> str:
    if not isinstance(value, str) or not value or "\x00" in value:
        raise BackupManifestError("Manifest paths must be non-empty text without NUL bytes.")
    if "\\" in value or ":" in value:
        raise BackupManifestError("Manifest paths must use safe relative POSIX syntax.")
    path = PurePosixPath(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise BackupManifestError("Manifest paths must be safe relative paths.")
    normalised = path.as_posix()
    if normalised != value:
        raise BackupManifestError("Manifest paths must be canonical relative POSIX paths.")
    return normalised


def _validate_checksum(value: str) -> None:
    if not isinstance(value, str) or _SHA256_PATTERN.fullmatch(value) is None:
        raise BackupManifestError("Manifest checksums must be lowercase SHA-256 digests.")


def _validate_text(value: str, name: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise BackupManifestError(f"The {name} must be non-empty text.")


def _timestamp(value: str | None) -> str:
    if value is not None:
        _validate_text(value, "created_at")
        return value
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _invalid_file_entry() -> BackupManifestFile:
    raise BackupManifestError("Manifest file entries must be JSON objects.")


__all__ = [
    "BackupManifest",
    "BackupManifestChecksumError",
    "BackupManifestError",
    "BackupManifestFile",
    "BackupManifestMissingFileError",
    "BackupManifestSizeError",
    "BackupManifestVersionError",
    "BackupType",
    "MANIFEST_FORMAT_VERSION",
    "ManifestFile",
    "build_manifest",
    "create_manifest",
    "load_manifest",
    "verify_manifest",
]
