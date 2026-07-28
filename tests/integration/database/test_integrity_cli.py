import hashlib
import os
import shutil
import sqlite3
import subprocess
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from transloka_core.database import DATABASE_FILENAME
from transloka_core.storage import (
    ensure_local_data_directories,
    resolve_local_data_directories,
)

REPOSITORY_ROOT = Path(__file__).parents[3]
ALEMBIC_CONFIGURATION = REPOSITORY_ROOT / "alembic.ini"


def _migrate_database(monkeypatch: pytest.MonkeyPatch, root: Path) -> Path:
    monkeypatch.setenv("TRANSLOKA_DATA_DIR", str(root))
    command.upgrade(Config(str(ALEMBIC_CONFIGURATION)), "head")
    return root / "database" / DATABASE_FILENAME


def _run_integrity_check(root: Path) -> subprocess.CompletedProcess[str]:
    executable = shutil.which("transloka")
    assert executable is not None
    environment = os.environ.copy()
    environment["TRANSLOKA_DATA_DIR"] = str(root)
    return subprocess.run(
        [executable, "db", "integrity-check"],
        cwd=REPOSITORY_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )


def test_integrity_check_reports_healthy_database(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "healthy-data"
    _migrate_database(monkeypatch, root)

    result = _run_integrity_check(root)

    assert result.returncode == 0, result.stderr
    assert "[PASS] data_directory" in result.stdout
    assert "[PASS] sqlite_integrity" in result.stdout
    assert "[PASS] foreign_keys" in result.stdout
    assert "[PASS] schema_revision" in result.stdout
    assert str(root) not in result.stdout


def test_integrity_check_rejects_foreign_key_violation(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "foreign-key-data"
    database_path = _migrate_database(monkeypatch, root)
    with sqlite3.connect(database_path) as connection:
        connection.executescript(
            """
            CREATE TABLE integrity_parent (id INTEGER PRIMARY KEY);
            CREATE TABLE integrity_child (
                parent_id INTEGER REFERENCES integrity_parent(id)
            );
            INSERT INTO integrity_child (parent_id) VALUES (999);
            """
        )

    result = _run_integrity_check(root)

    assert result.returncode != 0
    assert "[PASS] sqlite_integrity" in result.stdout
    assert "[FAIL] foreign_keys: violations detected" in result.stdout
    assert "[PASS] schema_revision" in result.stdout


def test_integrity_check_rejects_corrupted_copy_without_modifying_it(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    source_root = tmp_path / "source-data"
    source_database = _migrate_database(monkeypatch, source_root)
    corrupted_root = tmp_path / "corrupted-data"
    corrupted_directories = resolve_local_data_directories(corrupted_root)
    ensure_local_data_directories(corrupted_directories)
    corrupted_database = corrupted_directories.database / DATABASE_FILENAME
    shutil.copyfile(source_database, corrupted_database)
    with corrupted_database.open("r+b") as file:
        file.write(b"not a sqlite db!")
    checksum_before = hashlib.sha256(corrupted_database.read_bytes()).digest()

    result = _run_integrity_check(corrupted_root)

    assert result.returncode != 0
    assert "[FAIL] sqlite_integrity" in result.stdout
    assert "database could not be read safely" in result.stdout
    assert hashlib.sha256(corrupted_database.read_bytes()).digest() == checksum_before
