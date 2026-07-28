import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from functools import partial
from pathlib import Path
from typing import cast

from sqlalchemy import event
from sqlalchemy.engine import URL, Engine, create_engine
from sqlalchemy.engine.interfaces import DBAPIConnection
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import ConnectionPoolEntry

from transloka_core.storage import LocalDataDirectories, ensure_local_data_directories

DATABASE_FILENAME = "transloka.db"
_EXPECTED_PRAGMAS: tuple[tuple[str, int | str], ...] = (
    ("foreign_keys", 1),
    ("journal_mode", "wal"),
    ("busy_timeout", 5000),
    ("synchronous", 1),
)


class DatabaseConfigurationError(RuntimeError):
    """Raised when the local SQLite database cannot be configured safely."""


def create_sqlite_engine(directories: LocalDataDirectories) -> Engine:
    database_path = _database_path(directories)
    engine = create_engine(
        URL.create("sqlite+pysqlite", database=str(database_path)),
    )
    event.listen(
        engine,
        "do_connect",
        partial(_prepare_database_connection, directories, database_path),
    )
    event.listen(engine, "connect", _apply_required_pragmas)
    return engine


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(
        bind=engine,
        autoflush=False,
        expire_on_commit=False,
    )


@contextmanager
def transaction_scope(
    session_factory: sessionmaker[Session],
) -> Iterator[Session]:
    session = session_factory()
    try:
        yield session
        session.commit()
    except BaseException:
        session.rollback()
        raise
    finally:
        session.close()


def _database_path(directories: LocalDataDirectories) -> Path:
    if not directories.root.is_absolute() or not directories.database.is_absolute():
        raise DatabaseConfigurationError("The local database layout must use absolute paths.")

    root = directories.root.resolve(strict=False)
    database_directory = directories.database.resolve(strict=False)
    expected_directory = (root / "database").resolve(strict=False)
    if database_directory != expected_directory:
        raise DatabaseConfigurationError("The local database directory is inconsistent.")
    return database_directory / DATABASE_FILENAME


def _prepare_database_connection(
    directories: LocalDataDirectories,
    database_path: Path,
    *_event_arguments: object,
) -> None:
    ensure_local_data_directories(directories)
    if database_path.exists() and database_path.is_dir():
        raise DatabaseConfigurationError("The local database location is occupied by a directory.")


def _apply_required_pragmas(
    dbapi_connection: DBAPIConnection,
    _connection_record: ConnectionPoolEntry,
) -> None:
    connection = cast(sqlite3.Connection, dbapi_connection)
    previous_autocommit = connection.autocommit
    connection.autocommit = True
    cursor = connection.cursor()
    try:
        cursor.execute("PRAGMA foreign_keys = ON")
        cursor.execute("PRAGMA journal_mode = WAL")
        cursor.execute("PRAGMA busy_timeout = 5000")
        cursor.execute("PRAGMA synchronous = NORMAL")

        actual = {
            name: cursor.execute(f"PRAGMA {name}").fetchone()[0]
            for name, _expected in _EXPECTED_PRAGMAS
        }
    finally:
        cursor.close()
        connection.autocommit = previous_autocommit

    for name, expected in _EXPECTED_PRAGMAS:
        value = actual[name]
        if isinstance(expected, str):
            value = str(value).casefold()
        if value != expected:
            raise DatabaseConfigurationError(
                f"The required SQLite setting '{name}' could not be established."
            )
