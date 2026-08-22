import hashlib
import json
import stat
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile, ZipInfo

import pytest
from alembic import command
from alembic.config import Config
from transloka_core.backup.archive import create_full_project_backup
from transloka_core.backup.verification import (
    BackupArchiveBombError,
    BackupChecksumError,
    BackupManifestMissingError,
    BackupPathError,
    BackupSchemaError,
    BackupSymlinkError,
    BackupVerificationError,
    BackupVerificationLimits,
    verify_backup_archive,
)
from transloka_core.storage import LocalDataDirectories, resolve_local_data_directories

REPOSITORY_ROOT = Path(__file__).parents[3]
ALEMBIC_CONFIGURATION = REPOSITORY_ROOT / "alembic.ini"


@pytest.fixture
def valid_backup(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> tuple[LocalDataDirectories, Path, str]:
    directories = resolve_local_data_directories(tmp_path / "verification data")
    monkeypatch.setenv("TRANSLOKA_DATA_DIR", str(directories.root))
    command.upgrade(Config(str(ALEMBIC_CONFIGURATION)), "head")
    artifact = create_full_project_backup(directories)
    return (
        directories,
        directories.root / Path(artifact.storage_key),
        artifact.checksum_sha256,
    )


def test_valid_archive_verifies_manifest_checksum_and_database(
    valid_backup: tuple[LocalDataDirectories, Path, str],
) -> None:
    directories, archive_path, checksum = valid_backup

    result = verify_backup_archive(
        archive_path,
        data_root=directories.root,
        expected_checksum_sha256=checksum,
    )

    assert result.archive_path == archive_path.resolve()
    assert result.checksum_sha256 == checksum
    assert result.manifest.is_verified is True
    assert "database/transloka.db" in result.verified_files


def test_zip_slip_entry_is_rejected_before_any_extraction(tmp_path: Path) -> None:
    archive_path = tmp_path / "zip-slip.zip"
    outside = tmp_path / "outside.txt"
    with ZipFile(archive_path, mode="w", compression=ZIP_DEFLATED) as archive:
        archive.writestr("../outside.txt", b"must not be written")

    with pytest.raises(BackupPathError):
        verify_backup_archive(archive_path)

    assert not outside.exists()


def test_symlink_entry_is_rejected(tmp_path: Path) -> None:
    archive_path = tmp_path / "symlink.zip"
    symlink = ZipInfo("projects/link")
    symlink.create_system = 3
    symlink.external_attr = (stat.S_IFLNK | 0o777) << 16
    with ZipFile(archive_path, mode="w") as archive:
        archive.writestr(symlink, b"../private")

    with pytest.raises(BackupSymlinkError):
        verify_backup_archive(archive_path)


def test_archive_bomb_is_rejected_by_decompressed_size_limit(tmp_path: Path) -> None:
    archive_path = tmp_path / "bomb.zip"
    with ZipFile(archive_path, mode="w", compression=ZIP_DEFLATED) as archive:
        archive.writestr("payload.bin", b"0" * (256 * 1024))

    limits = BackupVerificationLimits(max_total_uncompressed_bytes=64 * 1024)
    with pytest.raises(BackupArchiveBombError):
        verify_backup_archive(archive_path, limits=limits)


def test_corrupted_archive_is_rejected(
    valid_backup: tuple[LocalDataDirectories, Path, str],
) -> None:
    _directories, archive_path, _checksum = valid_backup
    corrupted_path = archive_path.with_name("corrupted.zip")
    payload = bytearray(archive_path.read_bytes())
    payload[len(payload) // 2] ^= 0xFF
    corrupted_path.write_bytes(payload)

    with pytest.raises(BackupVerificationError):
        verify_backup_archive(corrupted_path)


def test_corrupted_database_is_rejected_after_checksum_verification(
    valid_backup: tuple[LocalDataDirectories, Path, str],
) -> None:
    _directories, archive_path, _checksum = valid_backup
    corrupted_path = archive_path.with_name("corrupted-database.zip")
    corrupted_database = b"not a SQLite database"
    with (
        ZipFile(archive_path, mode="r") as source,
        ZipFile(
            corrupted_path,
            mode="w",
            compression=ZIP_DEFLATED,
        ) as destination,
    ):
        manifest = json.loads(source.read("manifest.json"))
        for file_entry in manifest["files"]:
            if file_entry["path"] == "database/transloka.db":
                file_entry["size_bytes"] = len(corrupted_database)
                file_entry["checksum_sha256"] = hashlib.sha256(corrupted_database).hexdigest()
        for info in source.infolist():
            if info.filename == "database/transloka.db":
                destination.writestr(info.filename, corrupted_database)
            elif info.filename == "manifest.json":
                destination.writestr(
                    info.filename,
                    json.dumps(manifest, sort_keys=True, separators=(",", ":")),
                )
            else:
                destination.writestr(info, source.read(info))

    with pytest.raises(BackupSchemaError):
        verify_backup_archive(corrupted_path)


def test_archive_without_manifest_is_rejected(tmp_path: Path) -> None:
    archive_path = tmp_path / "missing-manifest.zip"
    with ZipFile(archive_path, mode="w", compression=ZIP_DEFLATED) as archive:
        archive.writestr("database/transloka.db", b"not a database")

    with pytest.raises(BackupManifestMissingError):
        verify_backup_archive(archive_path)


def test_expected_archive_checksum_mismatch_is_rejected(
    valid_backup: tuple[LocalDataDirectories, Path, str],
) -> None:
    _directories, archive_path, _checksum = valid_backup

    with pytest.raises(BackupChecksumError):
        verify_backup_archive(archive_path, expected_checksum_sha256="a" * 64)


def test_verification_does_not_modify_archive(
    valid_backup: tuple[LocalDataDirectories, Path, str],
) -> None:
    _directories, archive_path, checksum = valid_backup
    before = archive_path.read_bytes()

    verify_backup_archive(archive_path, expected_checksum_sha256=checksum)

    assert archive_path.read_bytes() == before
    assert archive_path.exists()
