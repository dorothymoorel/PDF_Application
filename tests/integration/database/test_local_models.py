from collections.abc import Iterator
from pathlib import Path
from uuid import UUID

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, inspect
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker
from transloka_core.database import (
    create_session_factory,
    create_sqlite_engine,
    transaction_scope,
)
from transloka_core.database.models.models import LocalModelRecord, ModelLicenseStatus
from transloka_core.storage import resolve_local_data_directories

REPOSITORY_ROOT = Path(__file__).parents[3]
ALEMBIC_CONFIGURATION = REPOSITORY_ROOT / "alembic.ini"
PARENT_REVISION = "0009_glossary"
DETECTED_AT = "2026-08-13T00:00:00.000Z"


@pytest.fixture
def model_database(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> Iterator[tuple[Path, Engine, sessionmaker[Session]]]:
    root = tmp_path / "Local Model Data_日本語"
    monkeypatch.setenv("TRANSLOKA_DATA_DIR", str(root))
    command.upgrade(Config(str(ALEMBIC_CONFIGURATION)), "head")
    engine = create_sqlite_engine(resolve_local_data_directories(root))
    try:
        yield root, engine, create_session_factory(engine)
    finally:
        engine.dispose()


def _model(index: int, **overrides: object) -> LocalModelRecord:
    values: dict[str, object] = {
        "id": f"mdl_{UUID(int=index)}",
        "ollama_model_name": f"model-{index}:latest",
        "model_family": None,
        "parameter_class": None,
        "quantization": None,
        "disk_size_bytes": 1024,
        "license_name": None,
        "license_status": ModelLicenseStatus.UNKNOWN.value,
        "is_installed": 1,
        "is_selected_translation": 0,
        "is_selected_validation": 0,
        "metadata_json": None,
        "last_detected_at": DETECTED_AT,
    }
    values.update(overrides)
    return LocalModelRecord(**values)


def test_local_models_migration_has_exact_schema_and_selection_indexes(
    model_database: tuple[Path, Engine, sessionmaker[Session]],
) -> None:
    _root, engine, _factory = model_database
    database = inspect(engine)

    assert [column["name"] for column in database.get_columns("local_models")] == [
        "id",
        "ollama_model_name",
        "model_family",
        "parameter_class",
        "quantization",
        "disk_size_bytes",
        "license_name",
        "license_status",
        "is_installed",
        "is_selected_translation",
        "is_selected_validation",
        "metadata_json",
        "last_detected_at",
    ]
    assert database.get_pk_constraint("local_models")["constrained_columns"] == ["id"]
    assert {
        column["name"] for column in database.get_columns("local_models") if column["nullable"]
    } == {
        "model_family",
        "parameter_class",
        "quantization",
        "disk_size_bytes",
        "license_name",
        "metadata_json",
    }
    assert {index["name"]: index["unique"] for index in database.get_indexes("local_models")} == {
        "uq_local_models_ollama_name": 1,
        "uq_local_models_selected_translation": 1,
        "uq_local_models_selected_validation": 1,
    }
    with engine.connect() as connection:
        table_sql = connection.exec_driver_sql(
            "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'local_models'"
        ).scalar_one()
        index_sql = {
            row[0]: row[1]
            for row in connection.exec_driver_sql(
                "SELECT name, sql FROM sqlite_master "
                "WHERE type = 'index' AND tbl_name = 'local_models' AND sql IS NOT NULL"
            )
        }
    assert table_sql.rstrip().endswith("STRICT")
    assert "ck_local_models_prefixed_uuid" in table_sql
    assert "ck_local_models_license_status" in table_sql
    assert "json_valid(metadata_json)" in table_sql
    assert "WHERE is_selected_translation = 1" in index_sql["uq_local_models_selected_translation"]
    assert "WHERE is_selected_validation = 1" in index_sql["uq_local_models_selected_validation"]


@pytest.mark.parametrize(
    "overrides",
    (
        {"id": "mdl_invalid"},
        {"ollama_model_name": ""},
        {"disk_size_bytes": -1},
        {"license_status": "CUSTOM"},
        {"is_installed": 2},
        {"is_selected_translation": -1},
        {"is_selected_validation": 3},
        {"metadata_json": "{invalid"},
        {"last_detected_at": ""},
    ),
)
def test_database_rejects_invalid_model_records(
    model_database: tuple[Path, Engine, sessionmaker[Session]],
    overrides: dict[str, object],
) -> None:
    _root, _engine, factory = model_database

    with factory() as session, pytest.raises(IntegrityError):
        session.add(_model(1, **overrides))
        session.flush()


def test_database_enforces_unique_name_and_one_selection_per_role(
    model_database: tuple[Path, Engine, sessionmaker[Session]],
) -> None:
    _root, _engine, factory = model_database
    with transaction_scope(factory) as session:
        session.add(_model(1, is_selected_translation=1, is_selected_validation=1))

    invalid_records = (
        _model(2, ollama_model_name="model-1:latest"),
        _model(3, is_selected_translation=1),
        _model(4, is_selected_validation=1),
    )
    for record in invalid_records:
        with factory() as session, pytest.raises(IntegrityError):
            session.add(record)
            session.flush()


def test_local_models_migration_downgrades_only_model_table_and_reupgrades(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "local-model-migration"
    monkeypatch.setenv("TRANSLOKA_DATA_DIR", str(root))
    configuration = Config(str(ALEMBIC_CONFIGURATION))
    command.upgrade(configuration, "head")
    command.downgrade(configuration, PARENT_REVISION)

    engine = create_sqlite_engine(resolve_local_data_directories(root))
    try:
        tables = set(inspect(engine).get_table_names())
        assert "local_models" not in tables
        assert {"glossaries", "glossary_terms"} <= tables
    finally:
        engine.dispose()

    command.upgrade(configuration, "head")
    command.upgrade(configuration, "head")
    engine = create_sqlite_engine(resolve_local_data_directories(root))
    try:
        assert "local_models" in inspect(engine).get_table_names()
    finally:
        engine.dispose()
