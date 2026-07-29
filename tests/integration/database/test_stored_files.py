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
from transloka_core.database import (
    create_session_factory,
    create_sqlite_engine,
    transaction_scope,
)
from transloka_core.database.models.files import FileRole, FileStatus, StoredFile
from transloka_core.database.models.projects import (
    DocumentType,
    ReconstructionMode,
    TranslationStyle,
)
from transloka_core.repositories.files import (
    InvalidStoredFileValueError,
    StoredFileRecord,
    StoredFilesRepository,
    StoredFileStorageKeyExistsError,
)
from transloka_core.repositories.projects import ProjectsRepository
from transloka_core.storage import resolve_local_data_directories

REPOSITORY_ROOT = Path(__file__).parents[3]
ALEMBIC_CONFIGURATION = REPOSITORY_ROOT / "alembic.ini"
PARENT_REVISION = "0003_projects"
PROJECT_ID = "prj_550e8400-e29b-41d4-a716-446655440000"
FILE_ID = "fil_550e8400-e29b-41d4-a716-446655440000"
OTHER_FILE_ID = "fil_29a7d2d8-f955-4a87-a99a-ecae61088c12"
CHECKSUM = "a" * 64
CREATED_AT = "2026-07-28T00:00:00.000Z"


@pytest.fixture
def stored_file_database(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> Iterator[tuple[Path, Engine, sessionmaker[Session]]]:
    root = tmp_path / "Stored File Data_日本語"
    monkeypatch.setenv("TRANSLOKA_DATA_DIR", str(root))
    command.upgrade(Config(str(ALEMBIC_CONFIGURATION)), "head")
    engine = create_sqlite_engine(resolve_local_data_directories(root))
    factory = create_session_factory(engine)
    with transaction_scope(factory) as session:
        ProjectsRepository(session).create(
            project_id=PROJECT_ID,
            name="Stored File Project",
            description=None,
            source_language="en",
            target_language="id",
            document_type=DocumentType.TECHNICAL_BOOK,
            translation_style=TranslationStyle.PROFESSIONAL,
            reconstruction_mode=ReconstructionMode.HYBRID,
            created_at=CREATED_AT,
        )
    yield root, engine, factory
    engine.dispose()


def _create_file(
    repository: StoredFilesRepository,
    *,
    file_id: str = FILE_ID,
    storage_key: str = "projects/prj_123/original/source.pdf",
    size_bytes: int = 12,
    is_immutable: bool = True,
) -> StoredFileRecord:
    return repository.create(
        file_id=file_id,
        project_id=PROJECT_ID,
        document_id=None,
        file_role=FileRole.ORIGINAL,
        storage_key=storage_key,
        original_filename="Source Document.pdf",
        safe_filename="source.pdf",
        mime_type="application/pdf",
        size_bytes=size_bytes,
        checksum_sha256=CHECKSUM,
        is_immutable=is_immutable,
        status=FileStatus.AVAILABLE,
        metadata={"source": "upload", "pages": 3},
        created_at=CREATED_AT,
    )


def test_stored_file_migration_has_exact_columns_constraints_indexes_and_no_blob(
    stored_file_database: tuple[Path, Engine, sessionmaker[Session]],
) -> None:
    _root, engine, _factory = stored_file_database
    database = inspect(engine)

    assert [column["name"] for column in database.get_columns("stored_files")] == [
        "id",
        "project_id",
        "document_id",
        "file_role",
        "storage_key",
        "original_filename",
        "safe_filename",
        "mime_type",
        "size_bytes",
        "checksum_sha256",
        "is_immutable",
        "status",
        "metadata_json",
        "created_at",
        "deleted_at",
    ]
    assert {index["name"]: index["unique"] for index in database.get_indexes("stored_files")} == {
        "ix_stored_files_checksum": 0,
        "ix_stored_files_project_role": 0,
        "uq_stored_files_storage_key": 1,
    }
    assert {
        (foreign_key["constrained_columns"][0], foreign_key["referred_table"])
        for foreign_key in database.get_foreign_keys("stored_files")
    } == {
        ("project_id", "projects"),
        ("document_id", "documents"),
    }
    assert all(
        "BLOB" not in str(column["type"]).upper() for column in database.get_columns("stored_files")
    )
    with engine.connect() as connection:
        definition = connection.exec_driver_sql(
            "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'stored_files'"
        ).scalar_one()
    assert definition.rstrip().endswith("STRICT")
    assert "ck_stored_files_relative_storage_key" in definition
    assert "ck_stored_files_metadata_json_valid" in definition


def test_repository_creates_and_reads_relative_file_metadata(
    stored_file_database: tuple[Path, Engine, sessionmaker[Session]],
) -> None:
    _root, _engine, factory = stored_file_database
    with transaction_scope(factory) as session:
        created = _create_file(StoredFilesRepository(session))

    with factory() as session:
        fetched = StoredFilesRepository(session).get(FILE_ID)

    assert fetched == created
    assert fetched.storage_key == "projects/prj_123/original/source.pdf"
    assert fetched.file_role is FileRole.ORIGINAL
    assert fetched.status is FileStatus.AVAILABLE
    assert fetched.is_immutable is True
    assert fetched.metadata == {"pages": 3, "source": "upload"}
    assert not any(column.type.python_type is bytes for column in StoredFile.__table__.columns)


def test_storage_key_is_unique(
    stored_file_database: tuple[Path, Engine, sessionmaker[Session]],
) -> None:
    _root, _engine, factory = stored_file_database
    with transaction_scope(factory) as session:
        repository = StoredFilesRepository(session)
        _create_file(repository)
        with pytest.raises(StoredFileStorageKeyExistsError):
            _create_file(repository, file_id=OTHER_FILE_ID)


def test_negative_size_and_invalid_immutable_flag_are_rejected_by_database(
    stored_file_database: tuple[Path, Engine, sessionmaker[Session]],
) -> None:
    _root, _engine, factory = stored_file_database
    invalid_rows = (
        StoredFile(
            id=FILE_ID,
            project_id=PROJECT_ID,
            document_id=None,
            file_role=FileRole.ORIGINAL.value,
            storage_key="projects/prj_123/original/negative.pdf",
            original_filename=None,
            safe_filename="negative.pdf",
            mime_type="application/pdf",
            size_bytes=-1,
            checksum_sha256=CHECKSUM,
            is_immutable=1,
            status=FileStatus.AVAILABLE.value,
            metadata_json=None,
            created_at=CREATED_AT,
            deleted_at=None,
        ),
        StoredFile(
            id=OTHER_FILE_ID,
            project_id=PROJECT_ID,
            document_id=None,
            file_role=FileRole.ORIGINAL.value,
            storage_key="projects/prj_123/original/invalid-boolean.pdf",
            original_filename=None,
            safe_filename="invalid-boolean.pdf",
            mime_type="application/pdf",
            size_bytes=1,
            checksum_sha256=CHECKSUM,
            is_immutable=2,
            status=FileStatus.AVAILABLE.value,
            metadata_json=None,
            created_at=CREATED_AT,
            deleted_at=None,
        ),
    )
    for row in invalid_rows:
        with factory() as session, pytest.raises(IntegrityError):
            session.add(row)
            session.flush()


@pytest.mark.parametrize(
    "storage_key",
    (
        "C:/Users/name/source.pdf",
        "/home/name/source.pdf",
        "\\\\server\\share\\source.pdf",
        "../source.pdf",
        "projects/../source.pdf",
        "projects\\source.pdf",
        "file:///source.pdf",
    ),
)
def test_absolute_and_unsafe_storage_keys_are_rejected(
    storage_key: str,
    stored_file_database: tuple[Path, Engine, sessionmaker[Session]],
) -> None:
    _root, _engine, factory = stored_file_database
    with factory() as session, pytest.raises(InvalidStoredFileValueError):
        _create_file(StoredFilesRepository(session), storage_key=storage_key)


def test_migration_downgrades_only_stored_files_and_reupgrades(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "migration-data"
    monkeypatch.setenv("TRANSLOKA_DATA_DIR", str(root))
    configuration = Config(str(ALEMBIC_CONFIGURATION))
    command.upgrade(configuration, "head")
    command.downgrade(configuration, PARENT_REVISION)

    engine = create_sqlite_engine(resolve_local_data_directories(root))
    try:
        tables = set(inspect(engine).get_table_names())
        assert "stored_files" not in tables
        assert "projects" in tables
    finally:
        engine.dispose()

    command.upgrade(configuration, "head")
    engine = create_sqlite_engine(resolve_local_data_directories(root))
    try:
        assert "stored_files" in inspect(engine).get_table_names()
    finally:
        engine.dispose()


@pytest.mark.parametrize(
    "statement",
    (
        "import transloka_core.database.models.files",
        "import transloka_core.repositories.files",
    ),
)
def test_stored_file_imports_create_no_database(statement: str, tmp_path: Path) -> None:
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
