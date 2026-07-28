import os
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Engine, inspect
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, sessionmaker
from transloka_api.services.projects import CreateProject, ProjectService, UpdateProject
from transloka_core.database import (
    create_session_factory,
    create_sqlite_engine,
    transaction_scope,
)
from transloka_core.database.models.projects import (
    DocumentType,
    Project,
    ProjectStatus,
    ReconstructionMode,
    TranslationStyle,
)
from transloka_core.repositories.projects import (
    InvalidProjectStateError,
    InvalidProjectValueError,
    ProjectNotFoundError,
    ProjectsRepository,
)
from transloka_core.storage import resolve_local_data_directories

REPOSITORY_ROOT = Path(__file__).parents[3]
ALEMBIC_CONFIGURATION = REPOSITORY_ROOT / "alembic.ini"
PARENT_REVISION = "0002_application_settings"


@pytest.fixture
def project_database(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> Iterator[tuple[Path, Engine, sessionmaker[Session]]]:
    root = tmp_path / "Project Data_日本語"
    monkeypatch.setenv("TRANSLOKA_DATA_DIR", str(root))
    command.upgrade(Config(str(ALEMBIC_CONFIGURATION)), "head")
    engine = create_sqlite_engine(resolve_local_data_directories(root))
    yield root, engine, create_session_factory(engine)
    engine.dispose()


def _command(name: str = "System Design Book") -> CreateProject:
    return CreateProject(
        name=name,
        description=None,
        source_language="en",
        target_language="id",
        document_type=DocumentType.TECHNICAL_BOOK,
        translation_style=TranslationStyle.PROFESSIONAL,
        reconstruction_mode=ReconstructionMode.HYBRID,
    )


def test_project_migration_has_exact_columns_constraints_and_indexes(
    project_database: tuple[Path, Engine, sessionmaker[Session]],
) -> None:
    _root, engine, _factory = project_database
    database = inspect(engine)

    assert [column["name"] for column in database.get_columns("projects")] == [
        "id",
        "name",
        "description",
        "status",
        "source_language",
        "target_language",
        "document_type",
        "translation_style",
        "reconstruction_mode",
        "progress",
        "active_document_id",
        "settings_json",
        "created_at",
        "updated_at",
        "archived_at",
        "deleted_at",
    ]
    assert database.get_pk_constraint("projects")["constrained_columns"] == ["id"]
    assert {index["name"] for index in database.get_indexes("projects")} == {
        "ix_projects_status",
        "ix_projects_updated_at",
    }
    assert database.get_foreign_keys("projects") == []
    with engine.connect() as connection:
        definition = connection.exec_driver_sql(
            "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'projects'"
        ).scalar_one()
    assert definition.rstrip().endswith("STRICT")
    assert "ck_projects_progress" in definition
    assert "ck_projects_settings_json_valid" in definition
    assert "user_id" not in definition
    assert "billing" not in definition


def test_project_migration_downgrades_only_projects_and_reupgrades(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "migration data"
    monkeypatch.setenv("TRANSLOKA_DATA_DIR", str(root))
    configuration = Config(str(ALEMBIC_CONFIGURATION))
    command.upgrade(configuration, "head")
    command.downgrade(configuration, PARENT_REVISION)

    engine = create_sqlite_engine(resolve_local_data_directories(root))
    try:
        assert set(inspect(engine).get_table_names()) == {
            "alembic_version",
            "app_metadata",
            "app_settings",
        }
    finally:
        engine.dispose()

    command.upgrade(configuration, "head")
    command.upgrade(configuration, "head")
    engine = create_sqlite_engine(resolve_local_data_directories(root))
    try:
        assert "projects" in inspect(engine).get_table_names()
    finally:
        engine.dispose()


def test_create_get_list_update_and_archive(
    project_database: tuple[Path, Engine, sessionmaker[Session]],
) -> None:
    _root, _engine, factory = project_database
    with transaction_scope(factory) as session:
        first = ProjectService(ProjectsRepository(session)).create(_command("First"))
        second = ProjectService(ProjectsRepository(session)).create(_command("Second"))

    with transaction_scope(factory) as session:
        service = ProjectService(ProjectsRepository(session))
        fetched = service.get(first.id)
        updated = service.update(
            first.id,
            UpdateProject(
                name="Updated First",
                status=ProjectStatus.WAITING_FOR_SETTINGS,
                translation_style=TranslationStyle.ACADEMIC,
                progress=0.25,
            ),
        )
        archived = service.archive(second.id)

    assert fetched.name == "First"
    assert fetched.status is ProjectStatus.CREATED
    assert fetched.progress == 0.0
    assert fetched.settings == {}
    assert updated.name == "Updated First"
    assert updated.status is ProjectStatus.WAITING_FOR_SETTINGS
    assert updated.translation_style is TranslationStyle.ACADEMIC
    assert updated.progress == 0.25
    assert archived.status is ProjectStatus.ARCHIVED
    assert archived.archived_at is not None

    with factory() as session:
        repository = ProjectsRepository(session)
        assert {project.id for project in repository.list()} == {first.id, second.id}
        assert [project.id for project in repository.list(ProjectStatus.ARCHIVED)] == [second.id]


def test_repository_does_not_commit_implicitly(
    project_database: tuple[Path, Engine, sessionmaker[Session]],
) -> None:
    _root, _engine, factory = project_database
    with factory() as session:
        project = ProjectService(ProjectsRepository(session)).create(_command())
        assert session.in_transaction()
        session.rollback()

    with factory() as session, pytest.raises(ProjectNotFoundError):
        ProjectsRepository(session).get(project.id)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("progress", -0.01),
        ("progress", 1.01),
        ("progress", float("nan")),
        ("status", "CUSTOM"),
        ("translation_style", "CUSTOM"),
        ("reconstruction_mode", "CUSTOM"),
    ],
)
def test_invalid_progress_and_enums_are_rejected_before_write(
    field: str,
    value: object,
    project_database: tuple[Path, Engine, sessionmaker[Session]],
) -> None:
    _root, _engine, factory = project_database
    with transaction_scope(factory) as session:
        project = ProjectService(ProjectsRepository(session)).create(_command())

    command_values: dict[str, object] = {field: value}
    update = UpdateProject(**command_values)  # type: ignore[arg-type]
    with factory() as session, pytest.raises(InvalidProjectValueError):
        ProjectService(ProjectsRepository(session)).update(project.id, update)


def test_database_rejects_invalid_project_values(
    project_database: tuple[Path, Engine, sessionmaker[Session]],
) -> None:
    _root, _engine, factory = project_database
    invalid_rows = (
        Project(
            id="prj_invalid",
            name="Invalid ID",
            description=None,
            status="CREATED",
            source_language="en",
            target_language="id",
            document_type="TECHNICAL_BOOK",
            translation_style="PROFESSIONAL",
            reconstruction_mode="HYBRID",
            progress=0.0,
            active_document_id=None,
            settings_json="{}",
            created_at="2026-07-28T00:00:00.000Z",
            updated_at="2026-07-28T00:00:00.000Z",
            archived_at=None,
            deleted_at=None,
        ),
        Project(
            id="prj_550e8400-e29b-41d4-a716-446655440000",
            name="Invalid Progress",
            description=None,
            status="CREATED",
            source_language="en",
            target_language="id",
            document_type="TECHNICAL_BOOK",
            translation_style="PROFESSIONAL",
            reconstruction_mode="HYBRID",
            progress=2.0,
            active_document_id=None,
            settings_json="{}",
            created_at="2026-07-28T00:00:00.000Z",
            updated_at="2026-07-28T00:00:00.000Z",
            archived_at=None,
            deleted_at=None,
        ),
    )
    for row in invalid_rows:
        with factory() as session, pytest.raises(IntegrityError):
            session.add(row)
            session.flush()


def test_archived_and_soft_deleted_projects_cannot_be_mutated_or_read(
    project_database: tuple[Path, Engine, sessionmaker[Session]],
) -> None:
    _root, _engine, factory = project_database
    with transaction_scope(factory) as session:
        service = ProjectService(ProjectsRepository(session))
        archived = service.archive(service.create(_command("Archived")).id)
        deleted = service.create(_command("Deleted"))
        row = session.get(Project, deleted.id)
        assert row is not None
        row.deleted_at = "2026-07-28T02:00:00.000Z"

    with factory() as session:
        repository = ProjectsRepository(session)
        with pytest.raises(InvalidProjectStateError):
            repository.update(
                archived.id,
                name=archived.name,
                description=archived.description,
                status=archived.status,
                translation_style=archived.translation_style,
                reconstruction_mode=archived.reconstruction_mode,
                progress=archived.progress,
                updated_at="2026-07-28T03:00:00.000Z",
            )
        with pytest.raises(ProjectNotFoundError):
            repository.get(deleted.id)
        assert deleted.id not in {project.id for project in repository.list()}


def test_unarchive_restores_project_to_safe_created_state(
    project_database: tuple[Path, Engine, sessionmaker[Session]],
) -> None:
    _root, _engine, factory = project_database
    with transaction_scope(factory) as session:
        service = ProjectService(ProjectsRepository(session))
        project = service.create(_command())
        archived = service.archive(project.id)
        restored = service.unarchive(project.id)

    assert archived.status is ProjectStatus.ARCHIVED
    assert archived.archived_at is not None
    assert restored.status is ProjectStatus.CREATED
    assert restored.archived_at is None

    with factory() as session:
        repository = ProjectsRepository(session)
        with pytest.raises(InvalidProjectStateError):
            repository.unarchive(
                restored.id,
                "2026-07-28T04:00:00.000Z",
            )


def test_project_persists_after_engine_disposal_and_restart(
    project_database: tuple[Path, Engine, sessionmaker[Session]],
) -> None:
    root, first_engine, first_factory = project_database
    with transaction_scope(first_factory) as session:
        created = ProjectService(ProjectsRepository(session)).create(_command())
    first_engine.dispose()

    second_engine = create_sqlite_engine(resolve_local_data_directories(root))
    try:
        with create_session_factory(second_engine)() as session:
            persisted = ProjectsRepository(session).get(created.id)
            assert persisted == created
    finally:
        second_engine.dispose()


@pytest.mark.parametrize(
    "statement",
    [
        "import transloka_core.database.models.projects",
        "import transloka_core.repositories.projects",
        "import transloka_api.services.projects",
    ],
)
def test_project_imports_create_no_database(statement: str, tmp_path: Path) -> None:
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
