import os
from collections.abc import Iterator
from pathlib import Path
from uuid import UUID

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, inspect
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker
from transloka_core.backup.manifest import BackupType
from transloka_core.database import create_session_factory, create_sqlite_engine, transaction_scope
from transloka_core.database.models.backups import Backup, BackupStatus
from transloka_core.storage import resolve_local_data_directories

REPOSITORY_ROOT = Path(__file__).parents[3]
ALEMBIC_CONFIGURATION = REPOSITORY_ROOT / "alembic.ini"
PARENT_REVISION = "0016_quality"
CREATED_AT = "2026-08-22T00:00:00.000Z"


@pytest.fixture
def backup_database(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> Iterator[tuple[Engine, sessionmaker[Session]]]:
    root = tmp_path / "backup data"
    monkeypatch.setenv("TRANSLOKA_DATA_DIR", os.fspath(root))
    command.upgrade(Config(str(ALEMBIC_CONFIGURATION)), "head")
    engine = create_sqlite_engine(resolve_local_data_directories(root))
    factory = create_session_factory(engine)
    try:
        yield engine, factory
    finally:
        engine.dispose()


def _backup(**overrides: object) -> Backup:
    values: dict[str, object] = {
        "id": f"bkp_{UUID(int=800)}",
        "backup_type": BackupType.DATABASE_ONLY.value,
        "file_id": None,
        "application_version": "0.1.0",
        "database_schema_version": "0017_backups",
        "status": BackupStatus.CREATED.value,
        "size_bytes": None,
        "checksum_sha256": None,
        "included_content_json": '["database/transloka.db"]',
        "created_at": CREATED_AT,
        "completed_at": None,
        "error_code": None,
    }
    values.update(overrides)
    return Backup(**values)


def test_backup_migration_has_expected_columns_indexes_and_strict_mode(
    backup_database: tuple[Engine, sessionmaker[Session]],
) -> None:
    engine, _factory = backup_database
    database = inspect(engine)
    assert [column["name"] for column in database.get_columns("backups")] == [
        "id",
        "backup_type",
        "file_id",
        "application_version",
        "database_schema_version",
        "status",
        "size_bytes",
        "checksum_sha256",
        "included_content_json",
        "created_at",
        "completed_at",
        "error_code",
    ]
    assert {index["name"]: index["unique"] for index in database.get_indexes("backups")} == {
        "ix_backups_status": 0,
        "ix_backups_type": 0,
    }
    with engine.connect() as connection:
        table_sql = connection.exec_driver_sql(
            "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'backups'"
        ).scalar_one()
        assert table_sql.rstrip().endswith("STRICT")


def test_backup_record_persists_before_verification(
    backup_database: tuple[Engine, sessionmaker[Session]],
) -> None:
    _engine, factory = backup_database
    backup = _backup()
    with transaction_scope(factory) as session:
        session.add(backup)

    with factory() as session:
        persisted = session.get(Backup, backup.id)
        assert persisted is not None
        assert persisted.status == BackupStatus.CREATED.value
        assert persisted.checksum_sha256 is None
        assert persisted.completed_at is None


@pytest.mark.parametrize(
    "overrides",
    (
        {"backup_type": "UNKNOWN"},
        {"status": "UNKNOWN"},
        {"size_bytes": -1},
        {"checksum_sha256": "not-a-checksum"},
        {"included_content_json": '{"path":"database/transloka.db"}'},
        {"status": BackupStatus.COMPLETED.value},
    ),
)
def test_backup_constraints_reject_invalid_values(
    backup_database: tuple[Engine, sessionmaker[Session]],
    overrides: dict[str, object],
) -> None:
    _engine, factory = backup_database
    with factory() as session, pytest.raises(IntegrityError):
        session.add(_backup(**overrides))
        session.flush()


def test_backup_migration_downgrades_and_reupgrades_cleanly(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "backup migration"
    monkeypatch.setenv("TRANSLOKA_DATA_DIR", os.fspath(root))
    configuration = Config(str(ALEMBIC_CONFIGURATION))
    command.upgrade(configuration, "head")
    command.downgrade(configuration, PARENT_REVISION)
    engine = create_sqlite_engine(resolve_local_data_directories(root))
    try:
        assert "backups" not in inspect(engine).get_table_names()
    finally:
        engine.dispose()
    command.upgrade(configuration, "head")
    engine = create_sqlite_engine(resolve_local_data_directories(root))
    try:
        assert "backups" in inspect(engine).get_table_names()
    finally:
        engine.dispose()
