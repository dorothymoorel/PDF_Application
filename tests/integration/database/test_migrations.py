import os
import shutil
import subprocess
import sys
from io import StringIO
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from alembic.util.exc import CommandError
from transloka_core.database import DATABASE_FILENAME, create_sqlite_engine
from transloka_core.storage import resolve_local_data_directories

REPOSITORY_ROOT = Path(__file__).parents[3]
ALEMBIC_CONFIGURATION = REPOSITORY_ROOT / "alembic.ini"
MIGRATION_DIRECTORY = REPOSITORY_ROOT / "infrastructure" / "migrations"
BASELINE_REVISION = "0001_baseline"
PARENT_REVISION = "0014_reconstruction"
HEAD_REVISION = "0015_exports"
APPLICATION_TABLES = {
    "alembic_version",
    "application_jobs",
    "app_metadata",
    "app_settings",
    "document_pages",
    "document_annotations",
    "document_assets",
    "document_blocks",
    "document_relationships",
    "document_sections",
    "document_segments",
    "document_table_cells",
    "document_tables",
    "documents",
    "glossaries",
    "glossary_conflicts",
    "glossary_revisions",
    "glossary_snapshots",
    "glossary_terms",
    "job_attempts",
    "job_dependencies",
    "local_models",
    "projects",
    "protected_items",
    "stored_files",
    "term_candidates",
    "term_occurrences",
    "translation_batches",
    "translation_batch_segments",
    "translation_attempts",
    "segment_translations",
    "translation_validations",
    "segment_revisions",
    "warnings",
    "reconstruction_jobs",
    "reconstruction_pages",
    "reconstruction_blocks",
    "target_page_mappings",
    "exports",
}


def _configuration() -> Config:
    return Config(str(ALEMBIC_CONFIGURATION))


def _set_temporary_data_root(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    name: str = "data",
) -> Path:
    root = tmp_path / name
    monkeypatch.setenv("TRANSLOKA_DATA_DIR", str(root))
    return root


def _current_revision(root: Path) -> str | None:
    engine = create_sqlite_engine(resolve_local_data_directories(root))
    try:
        with engine.connect() as connection:
            return MigrationContext.configure(connection).get_current_revision()
    finally:
        engine.dispose()


def _table_names(root: Path) -> set[str]:
    engine = create_sqlite_engine(resolve_local_data_directories(root))
    try:
        with engine.connect() as connection:
            return set(
                connection.exec_driver_sql(
                    "SELECT name FROM sqlite_master WHERE type = 'table'"
                ).scalars()
            )
    finally:
        engine.dispose()


def test_configuration_and_revision_layout_are_deterministic() -> None:
    configuration_text = ALEMBIC_CONFIGURATION.read_text(encoding="utf-8")
    configuration = _configuration()
    scripts = ScriptDirectory.from_config(configuration)
    script_location = configuration.get_main_option("script_location")

    assert script_location is not None
    assert Path(script_location) == MIGRATION_DIRECTORY
    assert configuration.get_main_option("file_template") == "%(rev)s_%(slug)s"
    assert configuration.get_main_option("sqlalchemy.url") is None
    assert "sqlite:" not in configuration_text
    assert "F:\\" not in configuration_text
    assert scripts.get_current_head() == HEAD_REVISION
    assert scripts.get_revision(HEAD_REVISION) is not None
    assert scripts.get_revision(HEAD_REVISION).down_revision == PARENT_REVISION


def test_loading_revision_scripts_creates_no_database_storage(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root = _set_temporary_data_root(monkeypatch, tmp_path)

    list(ScriptDirectory.from_config(_configuration()).walk_revisions())

    assert not root.exists()


def test_offline_upgrade_generates_sql_without_creating_database(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root = _set_temporary_data_root(monkeypatch, tmp_path)
    output = StringIO()
    configuration = Config(str(ALEMBIC_CONFIGURATION), output_buffer=output)

    command.upgrade(configuration, "head", sql=True)

    sql = output.getvalue()
    assert "CREATE TABLE alembic_version" in sql
    assert "CREATE TABLE app_metadata" in sql
    assert "CREATE TABLE app_settings" in sql
    assert "CREATE TABLE projects" in sql
    assert "CREATE TABLE stored_files" in sql
    assert "CREATE TABLE documents" in sql
    assert "CREATE TABLE document_pages" in sql
    assert "CREATE TABLE document_sections" in sql
    assert "CREATE TABLE document_blocks" in sql
    assert "CREATE TABLE document_segments" in sql
    assert "CREATE TABLE document_assets" in sql
    assert "CREATE TABLE document_tables" in sql
    assert "CREATE TABLE document_table_cells" in sql
    assert "CREATE TABLE document_annotations" in sql
    assert "CREATE TABLE document_relationships" in sql
    assert "CREATE TABLE application_jobs" in sql
    assert "CREATE TABLE job_attempts" in sql
    assert "CREATE TABLE job_dependencies" in sql
    assert "CREATE TABLE local_models" in sql
    assert "CREATE TABLE translation_batches" in sql
    assert "CREATE TABLE translation_batch_segments" in sql
    assert "CREATE TABLE translation_attempts" in sql
    assert "CREATE TABLE segment_translations" in sql
    assert "CREATE TABLE translation_validations" in sql
    assert "CREATE TABLE segment_revisions" in sql
    assert "CREATE TABLE warnings" in sql
    assert "CREATE TABLE reconstruction_jobs" in sql
    assert "CREATE TABLE reconstruction_pages" in sql
    assert "CREATE TABLE reconstruction_blocks" in sql
    assert "CREATE TABLE target_page_mappings" in sql
    assert HEAD_REVISION in sql
    assert str(root) not in sql
    assert not root.exists()


@pytest.mark.parametrize("directory_name", ["Data With Spaces", "Data Pengguna_日本語"])
def test_online_upgrade_uses_canonical_temporary_database(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    directory_name: str,
) -> None:
    root = _set_temporary_data_root(monkeypatch, tmp_path, directory_name)
    database_path = root / "database" / DATABASE_FILENAME

    assert not database_path.exists()
    command.upgrade(_configuration(), "head")

    assert database_path.is_file()
    assert database_path.is_relative_to(tmp_path)
    assert _current_revision(root) == HEAD_REVISION
    assert _table_names(root) == APPLICATION_TABLES


def test_current_history_and_repeated_upgrade_are_stable(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root = _set_temporary_data_root(monkeypatch, tmp_path)
    command.upgrade(_configuration(), "head")
    command.upgrade(_configuration(), "head")

    current_output = StringIO()
    command.current(Config(str(ALEMBIC_CONFIGURATION), stdout=current_output))
    history_output = StringIO()
    command.history(Config(str(ALEMBIC_CONFIGURATION), stdout=history_output))

    assert _current_revision(root) == HEAD_REVISION
    assert HEAD_REVISION in current_output.getvalue()
    assert "(head)" in current_output.getvalue()
    assert HEAD_REVISION in history_output.getvalue()
    assert _table_names(root) == APPLICATION_TABLES


def test_baseline_downgrade_is_reversible(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    root = _set_temporary_data_root(monkeypatch, tmp_path)
    command.upgrade(_configuration(), "head")

    command.downgrade(_configuration(), "base")
    assert _current_revision(root) is None
    assert _table_names(root) == {"alembic_version"}

    command.upgrade(_configuration(), "head")
    assert _current_revision(root) == HEAD_REVISION


def test_invalid_revision_fails_clearly(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _set_temporary_data_root(monkeypatch, tmp_path)

    with pytest.raises(CommandError, match="revision identified"):
        command.upgrade(_configuration(), "not_a_revision")


def test_cli_upgrade_current_and_history_use_temporary_database(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    root = _set_temporary_data_root(monkeypatch, tmp_path)
    executable = shutil.which("alembic")
    assert executable is not None
    environment = os.environ.copy()

    for arguments in (
        ("upgrade", "head"),
        ("current",),
        ("history",),
    ):
        result = subprocess.run(
            [executable, "-c", str(ALEMBIC_CONFIGURATION), *arguments],
            cwd=REPOSITORY_ROOT,
            env=environment,
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode == 0, result.stderr

    assert _current_revision(root) == HEAD_REVISION


def test_migration_resources_are_disposed(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    root = _set_temporary_data_root(monkeypatch, tmp_path)
    database_path = root / "database" / DATABASE_FILENAME
    command.upgrade(_configuration(), "head")

    database_path.unlink()

    assert not database_path.exists()


@pytest.mark.parametrize(
    "statement",
    (
        "import transloka_core.database",
        "from transloka_api.main import app; print(app.title)",
        "import transloka_worker",
        "from transloka_api.main import app; app.openapi()",
    ),
)
def test_application_imports_do_not_run_migrations(statement: str, tmp_path: Path) -> None:
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


def test_no_runtime_database_exists_in_repository() -> None:
    artifacts = [
        path
        for pattern in ("*.db", "*.sqlite", "*.sqlite3")
        for path in REPOSITORY_ROOT.rglob(pattern)
        if ".mypy_cache" not in path.parts
    ]

    assert artifacts == []
