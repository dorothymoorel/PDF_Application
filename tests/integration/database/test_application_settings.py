import math
import os
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, inspect, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker
from transloka_core.database import (
    create_session_factory,
    create_sqlite_engine,
    transaction_scope,
)
from transloka_core.database.models.application import (
    ApplicationMetadata,
    ApplicationSetting,
    SettingCategory,
)
from transloka_core.repositories.settings import (
    CorruptSettingValueError,
    InvalidSettingCategoryError,
    InvalidSettingValueError,
    SettingAlreadyExistsError,
    SettingNotFoundError,
    SettingsRepository,
    UnknownSettingKeyError,
)
from transloka_core.storage import resolve_local_data_directories

REPOSITORY_ROOT = Path(__file__).parents[3]
ALEMBIC_CONFIGURATION = REPOSITORY_ROOT / "alembic.ini"
BASELINE_REVISION = "0001_baseline"


@pytest.fixture
def migrated_database(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> Iterator[tuple[Path, Engine, sessionmaker[Session]]]:
    root = tmp_path / "settings data"
    monkeypatch.setenv("TRANSLOKA_DATA_DIR", str(root))
    command.upgrade(Config(str(ALEMBIC_CONFIGURATION)), "head")
    engine = create_sqlite_engine(resolve_local_data_directories(root))
    yield root, engine, create_session_factory(engine)
    engine.dispose()


def test_migration_creates_exact_strict_application_schema(
    migrated_database: tuple[Path, Engine, sessionmaker[Session]],
) -> None:
    _root, engine, _factory = migrated_database
    database = inspect(engine)

    assert set(database.get_table_names()) == {
        "alembic_version",
        "app_metadata",
        "app_settings",
        "projects",
    }
    assert [
        (column["name"], str(column["type"]), column["nullable"])
        for column in database.get_columns("app_metadata")
    ] == [
        ("key", "TEXT", False),
        ("value", "TEXT", False),
        ("updated_at", "TEXT", False),
    ]
    assert [
        (column["name"], str(column["type"]), column["nullable"])
        for column in database.get_columns("app_settings")
    ] == [
        ("key", "TEXT", False),
        ("value_json", "TEXT", False),
        ("category", "TEXT", False),
        ("updated_at", "TEXT", False),
    ]
    assert database.get_pk_constraint("app_metadata")["constrained_columns"] == ["key"]
    assert database.get_pk_constraint("app_settings")["constrained_columns"] == ["key"]
    with engine.connect() as connection:
        definitions: dict[str, str] = {
            str(name): str(sql)
            for name, sql in connection.exec_driver_sql(
                "SELECT name, sql FROM sqlite_master "
                "WHERE type = 'table' AND name IN ('app_metadata', 'app_settings')"
            ).tuples()
        }
    assert all(definition.rstrip().endswith("STRICT") for definition in definitions.values())
    assert "json_valid(value_json)" in definitions["app_settings"]
    assert "ck_app_settings_key_category" in definitions["app_settings"]


def test_migration_downgrades_to_baseline_and_reupgrades(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "Data Pengguna_日本語"
    monkeypatch.setenv("TRANSLOKA_DATA_DIR", str(root))
    configuration = Config(str(ALEMBIC_CONFIGURATION))
    command.upgrade(configuration, "head")
    command.downgrade(configuration, BASELINE_REVISION)

    engine = create_sqlite_engine(resolve_local_data_directories(root))
    try:
        assert inspect(engine).get_table_names() == ["alembic_version"]
    finally:
        engine.dispose()

    command.upgrade(configuration, "head")
    command.upgrade(configuration, "head")
    engine = create_sqlite_engine(resolve_local_data_directories(root))
    try:
        assert set(inspect(engine).get_table_names()) == {
            "alembic_version",
            "app_metadata",
            "app_settings",
            "projects",
        }
    finally:
        engine.dispose()


def test_metadata_model_persists_only_canonical_columns(
    migrated_database: tuple[Path, Engine, sessionmaker[Session]],
) -> None:
    _root, _engine, factory = migrated_database
    with transaction_scope(factory) as session:
        session.add(
            ApplicationMetadata(
                key="application_version",
                value="0.1.0",
                updated_at="2026-07-28T00:00:00.000Z",
            )
        )

    with factory() as session:
        row = session.get(ApplicationMetadata, "application_version")
        assert row is not None
        assert (row.key, row.value, row.updated_at) == (
            "application_version",
            "0.1.0",
            "2026-07-28T00:00:00.000Z",
        )


def test_repository_create_read_update_and_filter(
    migrated_database: tuple[Path, Engine, sessionmaker[Session]],
) -> None:
    _root, _engine, factory = migrated_database
    with transaction_scope(factory) as session:
        repository = SettingsRepository(session)
        created = repository.create("translation_batch_size", 5)
        repository.create("ocr_concurrency", 1)

    assert created.category is SettingCategory.TRANSLATION
    assert created.value == 5
    with transaction_scope(factory) as session:
        updated = SettingsRepository(session).update("translation_batch_size", 10)
    assert updated.value == 10

    with factory() as session:
        repository = SettingsRepository(session)
        assert repository.get("translation_batch_size").value == 10
        assert [record.key for record in repository.list()] == [
            "ocr_concurrency",
            "translation_batch_size",
        ]
        assert [record.key for record in repository.list(SettingCategory.OCR)] == [
            "ocr_concurrency"
        ]


def test_repository_never_commits_its_own_work(
    migrated_database: tuple[Path, Engine, sessionmaker[Session]],
) -> None:
    _root, _engine, factory = migrated_database
    with factory() as session:
        SettingsRepository(session).create("ocr_concurrency", 1)
        assert session.in_transaction()
        session.rollback()

    with factory() as session, pytest.raises(SettingNotFoundError):
        SettingsRepository(session).get("ocr_concurrency")


def test_duplicate_and_missing_setting_behavior(
    migrated_database: tuple[Path, Engine, sessionmaker[Session]],
) -> None:
    _root, _engine, factory = migrated_database
    with transaction_scope(factory) as session:
        SettingsRepository(session).create("ocr_concurrency", 1)

    with factory() as session:
        with pytest.raises(SettingAlreadyExistsError):
            SettingsRepository(session).create("ocr_concurrency", 2)
        session.rollback()
        with pytest.raises(SettingNotFoundError):
            SettingsRepository(session).update("translation_batch_size", 5)


@pytest.mark.parametrize(
    "key",
    [
        "password",
        "api_key",
        "access_token",
        "refresh_token",
        "database_password",
        "custom.setting",
        "OCR_CONCURRENCY",
    ],
)
def test_unknown_and_secret_setting_keys_fail_closed(
    key: str,
    migrated_database: tuple[Path, Engine, sessionmaker[Session]],
) -> None:
    _root, _engine, factory = migrated_database
    private_value = "private-value"
    with factory() as session, pytest.raises(UnknownSettingKeyError) as caught:
        SettingsRepository(session).create(key, private_value)

    assert private_value not in str(caught.value)


@pytest.mark.parametrize(
    ("key", "value"),
    [
        ("translation_batch_size", 0),
        ("translation_batch_size", 11),
        ("translation_batch_size", True),
        ("translation_batch_size", "5"),
        ("translation_batch_size", math.nan),
        ("translation_batch_size", math.inf),
        ("translation_batch_size", -math.inf),
        ("translation_batch_size", b"5"),
        ("translation_batch_size", {5}),
        ("translation_batch_size", (5,)),
        ("translation_batch_size", {1: 5}),
        ("ocr_concurrency", 0),
        ("ocr_concurrency", 9),
    ],
)
def test_invalid_json_and_setting_specific_values_are_rejected(
    key: str,
    value: object,
    migrated_database: tuple[Path, Engine, sessionmaker[Session]],
) -> None:
    _root, _engine, factory = migrated_database
    with factory() as session, pytest.raises(InvalidSettingValueError):
        SettingsRepository(session).create(key, value)


def test_recursive_json_value_is_rejected(
    migrated_database: tuple[Path, Engine, sessionmaker[Session]],
) -> None:
    _root, _engine, factory = migrated_database
    recursive: list[object] = []
    recursive.append(recursive)

    with factory() as session, pytest.raises(InvalidSettingValueError):
        SettingsRepository(session).create("translation_batch_size", recursive)


def test_invalid_category_cannot_be_supplied(
    migrated_database: tuple[Path, Engine, sessionmaker[Session]],
) -> None:
    _root, _engine, factory = migrated_database
    with factory() as session, pytest.raises(InvalidSettingCategoryError):
        SettingsRepository(session).list("SECRETS")  # type: ignore[arg-type]


def test_database_constraints_reinforce_json_key_and_category_validation(
    migrated_database: tuple[Path, Engine, sessionmaker[Session]],
) -> None:
    _root, _engine, factory = migrated_database
    invalid_rows = (
        ApplicationSetting(
            key="ocr_concurrency",
            value_json="not-json",
            category="OCR",
            updated_at="2026-07-28T00:00:00.000Z",
        ),
        ApplicationSetting(
            key="unknown",
            value_json="1",
            category="GENERAL",
            updated_at="2026-07-28T00:00:00.000Z",
        ),
        ApplicationSetting(
            key="ocr_concurrency",
            value_json="1",
            category="TRANSLATION",
            updated_at="2026-07-28T00:00:00.000Z",
        ),
    )

    for row in invalid_rows:
        with factory() as session, pytest.raises(IntegrityError):
            session.add(row)
            session.flush()


def test_corrupt_persisted_json_fails_safely(
    migrated_database: tuple[Path, Engine, sessionmaker[Session]],
) -> None:
    _root, engine, factory = migrated_database
    with engine.begin() as connection:
        connection.exec_driver_sql("PRAGMA ignore_check_constraints = ON")
        connection.execute(
            text(
                "INSERT INTO app_settings (key, value_json, category, updated_at) "
                "VALUES (:key, :value_json, :category, :updated_at)"
            ),
            {
                "key": "ocr_concurrency",
                "value_json": "not-json",
                "category": "OCR",
                "updated_at": "2026-07-28T00:00:00.000Z",
            },
        )
        connection.exec_driver_sql("PRAGMA ignore_check_constraints = OFF")

    with factory() as session, pytest.raises(CorruptSettingValueError):
        SettingsRepository(session).get("ocr_concurrency")


def test_setting_persists_after_engine_disposal_and_restart(
    migrated_database: tuple[Path, Engine, sessionmaker[Session]],
) -> None:
    root, first_engine, first_factory = migrated_database
    with transaction_scope(first_factory) as session:
        SettingsRepository(session).create("translation_batch_size", 5)
    first_engine.dispose()

    second_engine = create_sqlite_engine(resolve_local_data_directories(root))
    try:
        second_factory = create_session_factory(second_engine)
        with second_factory() as session:
            record = SettingsRepository(session).get("translation_batch_size")
            assert record.value == 5
            assert type(record.value) is int
    finally:
        second_engine.dispose()


@pytest.mark.parametrize(
    "statement",
    [
        "import transloka_core.database.models.application",
        "import transloka_core.repositories.settings",
        "import transloka_api.routers.settings",
    ],
)
def test_m2_t04_imports_create_no_database(statement: str, tmp_path: Path) -> None:
    root = tmp_path / "import data"
    environment = os.environ.copy()
    environment["TRANSLOKA_DATA_DIR"] = str(root)

    result = subprocess.run(
        [sys.executable, "-c", statement],
        cwd=REPOSITORY_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert not root.exists()
