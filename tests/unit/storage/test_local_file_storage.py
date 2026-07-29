import hashlib
import os
import stat
from io import BytesIO
from pathlib import Path

import pytest
from transloka_core.storage import resolve_local_data_directories
from transloka_core.storage.local import (
    ImmutableStoredFileError,
    LocalFileStorage,
    LocalFileStorageError,
    StoredFileExistsError,
    StoredFileNotFoundError,
    UnsafeStorageKeyError,
)

CONTENT = b"%PDF-1.7\nmanaged document\n"
STORAGE_KEY = "projects/prj_123/original/source.pdf"


@pytest.fixture
def storage(tmp_path: Path) -> LocalFileStorage:
    return LocalFileStorage(resolve_local_data_directories(tmp_path / "data"))


def test_temporary_write_atomic_commit_read_and_checksum(storage: LocalFileStorage) -> None:
    temporary = storage.write_temporary(BytesIO(CONTENT))
    artifact = storage.commit(temporary, STORAGE_KEY)

    assert artifact.storage_key == STORAGE_KEY
    assert artifact.size_bytes == len(CONTENT)
    assert artifact.checksum_sha256 == hashlib.sha256(CONTENT).hexdigest()
    assert artifact.is_immutable is False
    assert not temporary.path.exists()
    with storage.open_read(STORAGE_KEY) as stored:
        assert stored.read() == CONTENT
    assert storage.checksum(STORAGE_KEY) == artifact.checksum_sha256


@pytest.mark.parametrize(
    "storage_key",
    (
        "../outside.pdf",
        "projects/../../outside.pdf",
        "C:/Windows/System32/file.pdf",
        "\\\\server\\share\\file.pdf",
        "/home/user/file.pdf",
        "projects/prj_123/original/../file.pdf",
        "projects//file.pdf",
        "projects/prj_123/original/file.pdf\x00",
        "database/transloka.db",
    ),
)
def test_traversal_absolute_and_unmanaged_paths_are_rejected(
    storage: LocalFileStorage,
    storage_key: str,
) -> None:
    temporary = storage.write_temporary(BytesIO(CONTENT))

    with pytest.raises(UnsafeStorageKeyError):
        storage.commit(temporary, storage_key)

    assert not temporary.path.exists()


@pytest.mark.parametrize("filename", ("CON", "con.txt", "PRN.pdf", "COM1", "LPT9.txt"))
def test_reserved_windows_filenames_are_rejected(
    storage: LocalFileStorage,
    filename: str,
) -> None:
    temporary = storage.write_temporary(BytesIO(CONTENT))

    with pytest.raises(UnsafeStorageKeyError):
        storage.commit(temporary, f"projects/prj_123/original/{filename}")


def test_symlink_escape_is_rejected(storage: LocalFileStorage, tmp_path: Path) -> None:
    temporary = storage.write_temporary(BytesIO(CONTENT))
    projects = temporary.path.parents[1] / "projects"
    outside = tmp_path / "outside"
    projects.rmdir()
    outside.mkdir()
    try:
        projects.symlink_to(outside, target_is_directory=True)
    except OSError:
        pytest.skip("Directory symlinks are unavailable.")

    with pytest.raises(UnsafeStorageKeyError):
        storage.commit(temporary, STORAGE_KEY)

    assert list(outside.iterdir()) == []


def test_atomic_commit_failure_leaves_no_final_or_temporary_file(
    storage: LocalFileStorage,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    temporary = storage.write_temporary(BytesIO(CONTENT))

    def interrupt_commit(_source: Path, _destination: Path) -> None:
        raise OSError

    monkeypatch.setattr(os, "link", interrupt_commit)

    with pytest.raises(LocalFileStorageError):
        storage.commit(temporary, STORAGE_KEY)

    assert not temporary.path.exists()
    with pytest.raises(StoredFileNotFoundError):
        storage.open_read(STORAGE_KEY)


def test_duplicate_filename_never_overwrites_existing_file(storage: LocalFileStorage) -> None:
    storage.commit(storage.write_temporary(BytesIO(CONTENT)), STORAGE_KEY)
    duplicate = storage.write_temporary(BytesIO(b"different"))

    with pytest.raises(StoredFileExistsError):
        storage.commit(duplicate, STORAGE_KEY)

    assert not duplicate.path.exists()
    with storage.open_read(STORAGE_KEY) as stored:
        assert stored.read() == CONTENT


def test_delete_is_contained_and_immutable_file_is_protected(
    storage: LocalFileStorage,
    tmp_path: Path,
) -> None:
    immutable = storage.commit(
        storage.write_temporary(BytesIO(CONTENT)),
        STORAGE_KEY,
        immutable=True,
    )
    stored_path = tmp_path / "data" / Path(STORAGE_KEY)

    try:
        assert immutable.is_immutable is True
        assert not stored_path.stat().st_mode & (stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH)
        with pytest.raises(ImmutableStoredFileError):
            storage.delete(STORAGE_KEY)

        outside = tmp_path / "outside.pdf"
        outside.write_bytes(b"private")
        with pytest.raises(UnsafeStorageKeyError):
            storage.delete("../outside.pdf")
        assert outside.read_bytes() == b"private"
    finally:
        stored_path.chmod(stat.S_IREAD | stat.S_IWRITE)


def test_delete_removes_only_requested_managed_file(storage: LocalFileStorage) -> None:
    other_key = "projects/prj_123/original/other.pdf"
    storage.commit(storage.write_temporary(BytesIO(CONTENT)), STORAGE_KEY)
    storage.commit(storage.write_temporary(BytesIO(b"other")), other_key)

    storage.delete(STORAGE_KEY)

    with pytest.raises(StoredFileNotFoundError):
        storage.open_read(STORAGE_KEY)
    with storage.open_read(other_key) as stored:
        assert stored.read() == b"other"
