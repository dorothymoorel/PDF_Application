import os
import subprocess
import sys
from collections.abc import Iterator
from dataclasses import replace
from pathlib import Path

import pytest
from sqlalchemy import Engine, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from sqlalchemy.pool import QueuePool
from transloka_core.database import (
    DATABASE_FILENAME,
    DatabaseConfigurationError,
    create_session_factory,
    create_sqlite_engine,
    transaction_scope,
)
from transloka_core.storage import (
    LocalDataDirectoryError,
    ensure_local_data_directories,
    resolve_local_data_directories,
)

REPOSITORY_ROOT = Path(__file__).parents[3]


@pytest.fixture
def database_engine(tmp_path: Path) -> Iterator[Engine]:
    engine = create_sqlite_engine(resolve_local_data_directories(tmp_path / "data"))
    yield engine
    engine.dispose()


def test_engine_uses_canonical_absolute_path_without_construction_side_effects(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    directories = resolve_local_data_directories(tmp_path / "data")
    other_working_directory = tmp_path / "working"
    other_working_directory.mkdir()
    monkeypatch.chdir(other_working_directory)

    engine = create_sqlite_engine(directories)
    database_path = Path(engine.url.database or "")

    assert database_path == directories.database / DATABASE_FILENAME
    assert database_path.name == "transloka.db"
    assert database_path.is_absolute()
    assert not directories.root.exists()
    engine.dispose()


@pytest.mark.parametrize("directory_name", ["Data With Spaces", "Data Pengguna_日本語"])
def test_first_connection_supports_safe_absolute_paths(directory_name: str, tmp_path: Path) -> None:
    directories = resolve_local_data_directories(tmp_path / directory_name)
    engine = create_sqlite_engine(directories)
    database_path = directories.database / DATABASE_FILENAME

    try:
        assert not database_path.exists()
        with engine.connect() as connection:
            assert connection.exec_driver_sql("SELECT 1").scalar_one() == 1
        assert database_path.is_file()
        assert database_path.is_relative_to(tmp_path)
    finally:
        engine.dispose()


def test_file_engine_uses_local_queue_pool(database_engine: Engine) -> None:
    _positional, connection_arguments = database_engine.dialect.create_connect_args(
        database_engine.url
    )

    assert database_engine.url.drivername == "sqlite+pysqlite"
    assert database_engine.url.host is None
    assert isinstance(database_engine.pool, QueuePool)
    assert connection_arguments["check_same_thread"] is False


def test_required_pragmas_apply_to_multiple_new_connections(database_engine: Engine) -> None:
    expected = {
        "foreign_keys": 1,
        "journal_mode": "wal",
        "busy_timeout": 5000,
        "synchronous": 1,
    }

    with database_engine.connect() as first, database_engine.connect() as second:
        for connection in (first, second):
            actual = {
                name: connection.exec_driver_sql(f"PRAGMA {name}").scalar_one() for name in expected
            }
            actual["journal_mode"] = str(actual["journal_mode"]).casefold()
            assert actual == expected


def test_foreign_key_violations_are_rejected(database_engine: Engine) -> None:
    with database_engine.begin() as connection:
        connection.exec_driver_sql("CREATE TABLE parent (id INTEGER PRIMARY KEY)")
        connection.exec_driver_sql("CREATE TABLE child (parent_id INTEGER REFERENCES parent(id))")

    with pytest.raises(IntegrityError):
        with database_engine.begin() as connection:
            connection.exec_driver_sql("INSERT INTO child (parent_id) VALUES (999)")


def test_session_factory_creates_sqlalchemy_2_session(database_engine: Engine) -> None:
    factory = create_session_factory(database_engine)

    with factory() as session:
        assert isinstance(session, Session)
        assert session.execute(text("SELECT 1")).scalar_one() == 1

    assert factory.kw["autoflush"] is False
    assert factory.kw["expire_on_commit"] is False
    assert factory.kw.get("autocommit", False) is False


def test_transaction_scope_commits_once_and_closes(
    monkeypatch: pytest.MonkeyPatch, database_engine: Engine
) -> None:
    with database_engine.begin() as connection:
        connection.exec_driver_sql("CREATE TABLE test_values (value TEXT NOT NULL)")

    commits: list[Session] = []
    closed: list[Session] = []
    original_commit = Session.commit
    original_close = Session.close

    def track_commit(session: Session) -> None:
        commits.append(session)
        original_commit(session)

    def track_close(session: Session) -> None:
        closed.append(session)
        original_close(session)

    monkeypatch.setattr(Session, "commit", track_commit)
    monkeypatch.setattr(Session, "close", track_close)
    factory = create_session_factory(database_engine)

    with transaction_scope(factory) as session:
        session.execute(text("INSERT INTO test_values (value) VALUES ('committed')"))

    assert commits == [session]
    assert closed == [session]
    with database_engine.connect() as connection:
        assert connection.exec_driver_sql("SELECT value FROM test_values").scalar_one() == (
            "committed"
        )


def test_transaction_scope_rolls_back_reraises_and_closes(
    monkeypatch: pytest.MonkeyPatch, database_engine: Engine
) -> None:
    with database_engine.begin() as connection:
        connection.exec_driver_sql("CREATE TABLE test_values (value TEXT NOT NULL)")

    rollbacks: list[Session] = []
    closed: list[Session] = []
    original_rollback = Session.rollback
    original_close = Session.close

    def track_rollback(session: Session) -> None:
        rollbacks.append(session)
        original_rollback(session)

    def track_close(session: Session) -> None:
        closed.append(session)
        original_close(session)

    monkeypatch.setattr(Session, "rollback", track_rollback)
    monkeypatch.setattr(Session, "close", track_close)
    factory = create_session_factory(database_engine)
    expected_error = RuntimeError("transaction failed")

    with pytest.raises(RuntimeError) as caught:
        with transaction_scope(factory) as session:
            session.execute(text("INSERT INTO test_values (value) VALUES ('rolled back')"))
            raise expected_error

    assert caught.value is expected_error
    assert rollbacks == [session]
    assert closed == [session]
    with database_engine.connect() as connection:
        assert connection.exec_driver_sql("SELECT COUNT(*) FROM test_values").scalar_one() == 0


def test_database_directory_occupied_by_file_fails_safely(tmp_path: Path) -> None:
    directories = resolve_local_data_directories(tmp_path / "data")
    directories.root.mkdir()
    directories.database.write_text("occupied", encoding="utf-8")
    engine = create_sqlite_engine(directories)

    try:
        with pytest.raises(LocalDataDirectoryError) as caught:
            engine.connect()
        assert str(directories.database) not in str(caught.value)
    finally:
        engine.dispose()


def test_database_path_occupied_by_directory_fails_safely(tmp_path: Path) -> None:
    directories = resolve_local_data_directories(tmp_path / "data")
    ensure_local_data_directories(directories)
    database_path = directories.database / DATABASE_FILENAME
    database_path.mkdir()
    engine = create_sqlite_engine(directories)

    try:
        with pytest.raises(DatabaseConfigurationError) as caught:
            engine.connect()
        assert str(database_path) not in str(caught.value)
    finally:
        engine.dispose()


def test_tampered_database_layout_is_rejected_without_path_disclosure(tmp_path: Path) -> None:
    directories = resolve_local_data_directories(tmp_path / "data")
    tampered = replace(directories, database=tmp_path / "private-database")

    with pytest.raises(DatabaseConfigurationError) as caught:
        create_sqlite_engine(tampered)

    assert str(tampered.database) not in str(caught.value)
    assert not directories.root.exists()


def test_engine_connection_creates_no_application_tables(database_engine: Engine) -> None:
    with database_engine.connect() as connection:
        tables = connection.exec_driver_sql(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).scalars()
        assert list(tables) == []


def test_repeated_engine_creation_preserves_existing_data(tmp_path: Path) -> None:
    directories = resolve_local_data_directories(tmp_path / "data")
    first_engine = create_sqlite_engine(directories)
    with first_engine.begin() as connection:
        connection.exec_driver_sql("CREATE TABLE test_values (value TEXT NOT NULL)")
        connection.exec_driver_sql("INSERT INTO test_values VALUES ('preserved')")
    first_engine.dispose()

    second_engine = create_sqlite_engine(directories)
    try:
        with second_engine.connect() as connection:
            assert connection.exec_driver_sql("SELECT value FROM test_values").scalar_one() == (
                "preserved"
            )
    finally:
        second_engine.dispose()


def test_engine_disposal_releases_database_file(tmp_path: Path) -> None:
    directories = resolve_local_data_directories(tmp_path / "data")
    database_path = directories.database / DATABASE_FILENAME
    engine = create_sqlite_engine(directories)
    with engine.connect():
        pass

    engine.dispose()
    database_path.unlink()

    assert not database_path.exists()


def test_mandatory_pragma_failure_is_reported_safely(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    import transloka_core.database.sqlite as sqlite_module

    directories = resolve_local_data_directories(tmp_path / "data")
    monkeypatch.setattr(
        sqlite_module,
        "_EXPECTED_PRAGMAS",
        (("foreign_keys", 1), ("journal_mode", "impossible")),
    )
    engine = create_sqlite_engine(directories)

    try:
        with pytest.raises(DatabaseConfigurationError, match="journal_mode") as caught:
            engine.connect()
        assert str(directories.database) not in str(caught.value)
    finally:
        engine.dispose()


@pytest.mark.parametrize(
    "statement",
    (
        "import transloka_core.database",
        "from transloka_api.main import app; print(app.title)",
        "import transloka_worker",
        "from transloka_api.main import app; app.openapi()",
    ),
)
def test_imports_and_openapi_create_no_database_storage(statement: str, tmp_path: Path) -> None:
    root = tmp_path / "import-data"
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
