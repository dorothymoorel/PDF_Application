import argparse
import sqlite3
from collections.abc import Sequence
from contextlib import closing
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
from alembic.util.exc import CommandError

from transloka_core.database import DATABASE_FILENAME
from transloka_core.storage import (
    LocalDataDirectories,
    LocalDataDirectoryError,
    resolve_local_data_directories,
)

_SUCCESS = 0
_FAILURE = 1


def main(arguments: Sequence[str] | None = None) -> int:
    parser = _build_parser()
    parsed = parser.parse_args(arguments)

    if parsed.command == "db" and parsed.database_command == "integrity-check":
        return _run_integrity_check()

    parser.error("Unsupported command.")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="transloka")
    commands = parser.add_subparsers(dest="command", required=True)
    database = commands.add_parser("db", help="Database maintenance commands.")
    database_commands = database.add_subparsers(dest="database_command", required=True)
    database_commands.add_parser(
        "integrity-check",
        help="Check the local database without modifying it.",
    )
    return parser


def _run_integrity_check() -> int:
    try:
        directories = resolve_local_data_directories()
    except LocalDataDirectoryError:
        _print_result("data_directory", False, "configuration is invalid")
        return _FAILURE

    data_directory_ok = _data_directory_is_available(directories)
    _print_result(
        "data_directory",
        data_directory_ok,
        "layout is available" if data_directory_ok else "required directories are unavailable",
    )
    if not data_directory_ok:
        return _FAILURE

    database_path = directories.database / DATABASE_FILENAME
    if not database_path.is_file():
        _print_unavailable_database_results("database file is unavailable")
        return _FAILURE

    expected_heads = _expected_schema_heads()
    try:
        results = _inspect_database(database_path, expected_heads)
    except sqlite3.Error:
        _print_unavailable_database_results("database could not be read safely")
        return _FAILURE

    for name, passed, detail in results:
        _print_result(name, passed, detail)

    if all(passed for _name, passed, _detail in results):
        print("Database integrity check passed.")
        return _SUCCESS

    print("Database integrity check failed.")
    return _FAILURE


def _data_directory_is_available(directories: LocalDataDirectories) -> bool:
    return all(path.is_dir() for _name, path in directories.items())


def _expected_schema_heads() -> set[str] | None:
    configuration_path = Path.cwd() / "alembic.ini"
    if not configuration_path.is_file():
        return None

    try:
        scripts = ScriptDirectory.from_config(Config(str(configuration_path)))
        return set(scripts.get_heads())
    except (CommandError, OSError):
        return None


def _inspect_database(
    database_path: Path,
    expected_heads: set[str] | None,
) -> tuple[tuple[str, bool, str], ...]:
    database_uri = f"{database_path.as_uri()}?mode=ro"
    with closing(sqlite3.connect(database_uri, uri=True)) as connection:
        integrity_rows = tuple(
            str(row[0]).casefold() for row in connection.execute("PRAGMA integrity_check")
        )
        integrity_ok = integrity_rows == ("ok",)

        connection.execute("PRAGMA foreign_keys = ON")
        foreign_keys_enabled = connection.execute("PRAGMA foreign_keys").fetchone() == (1,)
        foreign_key_violations = tuple(connection.execute("PRAGMA foreign_key_check"))
        foreign_keys_ok = foreign_keys_enabled and not foreign_key_violations

        try:
            current_heads = {
                str(row[0]) for row in connection.execute("SELECT version_num FROM alembic_version")
            }
        except sqlite3.Error:
            current_heads = set()
        schema_ok = expected_heads is not None and current_heads == expected_heads

    return (
        (
            "sqlite_integrity",
            integrity_ok,
            "ok" if integrity_ok else "integrity errors detected",
        ),
        (
            "foreign_keys",
            foreign_keys_ok,
            "ok" if foreign_keys_ok else "violations detected",
        ),
        (
            "schema_revision",
            schema_ok,
            "current" if schema_ok else "revision does not match migration head",
        ),
    )


def _print_unavailable_database_results(detail: str) -> None:
    for name in ("sqlite_integrity", "foreign_keys", "schema_revision"):
        _print_result(name, False, detail)
    print("Database integrity check failed.")


def _print_result(name: str, passed: bool, detail: str) -> None:
    status = "PASS" if passed else "FAIL"
    print(f"[{status}] {name}: {detail}")


if __name__ == "__main__":
    raise SystemExit(main())
