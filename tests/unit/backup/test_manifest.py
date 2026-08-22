import hashlib
import json
from pathlib import Path

import pytest
from transloka_core.backup.manifest import (
    BackupManifest,
    BackupManifestChecksumError,
    BackupManifestError,
    BackupManifestMissingFileError,
    BackupManifestVersionError,
    BackupType,
    build_manifest,
    verify_manifest,
)


def test_manifest_records_content_and_requires_verification(tmp_path: Path) -> None:
    database = tmp_path / "database" / "transloka.db"
    database.parent.mkdir()
    database.write_bytes(b"database bytes")

    manifest = build_manifest(
        backup_type=BackupType.DATABASE_ONLY,
        application_version="0.1.0",
        database_schema_version="0017_backups",
        root=tmp_path,
        included_content=["database/transloka.db"],
        created_at="2026-08-22T00:00:00.000Z",
    )

    assert manifest.backup_type is BackupType.DATABASE_ONLY
    assert manifest.files[0].size_bytes == len(b"database bytes")
    assert manifest.files[0].checksum_sha256 == hashlib.sha256(b"database bytes").hexdigest()
    assert manifest.is_verified is False
    with pytest.raises(BackupManifestError, match="must be verified"):
        manifest.require_verified()

    verified = verify_manifest(manifest, tmp_path)
    verified.require_verified()
    assert verified.is_verified is True
    assert BackupManifest.from_json(manifest.to_json()).is_verified is False


def test_manifest_rejects_invalid_checksum_after_file_changes(tmp_path: Path) -> None:
    payload = tmp_path / "metadata.json"
    payload.write_text('{"ok":true}', encoding="utf-8")
    manifest = build_manifest(
        backup_type="METADATA",
        application_version="0.1.0",
        database_schema_version="0017_backups",
        root=tmp_path,
        included_content=["metadata.json"],
    )
    payload.write_text('{"ok":TRUE}', encoding="utf-8")

    with pytest.raises(BackupManifestChecksumError, match="checksum does not match"):
        manifest.verify(tmp_path)


def test_manifest_rejects_missing_file(tmp_path: Path) -> None:
    payload = tmp_path / "metadata.json"
    payload.write_text("metadata", encoding="utf-8")
    manifest = build_manifest(
        backup_type="METADATA",
        application_version="0.1.0",
        database_schema_version="0017_backups",
        root=tmp_path,
        included_content=["metadata.json"],
    )
    payload.unlink()

    with pytest.raises(BackupManifestMissingFileError, match="file is missing"):
        manifest.verify(tmp_path)


def test_manifest_rejects_unsupported_version() -> None:
    payload = {
        "format_version": 99,
        "backup_type": "DATABASE_ONLY",
        "application_version": "0.1.0",
        "database_schema_version": "0017_backups",
        "created_at": "2026-08-22T00:00:00.000Z",
        "included_content": ["database/transloka.db"],
        "files": [
            {
                "path": "database/transloka.db",
                "size_bytes": 1,
                "checksum_sha256": "a" * 64,
            }
        ],
    }

    with pytest.raises(BackupManifestVersionError, match="not supported"):
        BackupManifest.from_dict(payload)


@pytest.mark.parametrize("path", ["../outside", "/absolute", "C:/outside", "database\\db"])
def test_manifest_rejects_unsafe_paths(path: str, tmp_path: Path) -> None:
    with pytest.raises(BackupManifestError):
        build_manifest(
            backup_type="DATABASE_ONLY",
            application_version="0.1.0",
            database_schema_version="0017_backups",
            root=tmp_path,
            included_content=[path],
        )


def test_manifest_json_is_canonical(tmp_path: Path) -> None:
    payload = tmp_path / "a.txt"
    payload.write_text("a", encoding="utf-8")
    manifest = build_manifest(
        backup_type="DATABASE_ONLY",
        application_version="0.1.0",
        database_schema_version="0017_backups",
        root=tmp_path,
        included_content=["a.txt"],
    )

    decoded = json.loads(manifest.to_json())
    assert list(decoded) == sorted(decoded)
    assert decoded["files"][0]["path"] == "a.txt"
