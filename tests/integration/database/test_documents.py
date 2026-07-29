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
from transloka_core.database.models.documents import (
    Document,
    DocumentClass,
    DocumentStatus,
)
from transloka_core.database.models.files import FileRole, FileStatus
from transloka_core.database.models.projects import (
    DocumentType,
    ReconstructionMode,
    TranslationStyle,
)
from transloka_core.repositories.files import StoredFilesRepository
from transloka_core.repositories.projects import ProjectsRepository
from transloka_core.storage import resolve_local_data_directories

REPOSITORY_ROOT = Path(__file__).parents[3]
ALEMBIC_CONFIGURATION = REPOSITORY_ROOT / "alembic.ini"
PARENT_REVISION = "0004_stored_files"
PROJECT_ID = "prj_550e8400-e29b-41d4-a716-446655440000"
ORIGINAL_FILE_ID = "fil_550e8400-e29b-41d4-a716-446655440000"
DOCUMENT_ID = "doc_550e8400-e29b-41d4-a716-446655440000"
OTHER_DOCUMENT_ID = "doc_29a7d2d8-f955-4a87-a99a-ecae61088c12"
CREATED_AT = "2026-07-29T00:00:00.000Z"


@pytest.fixture
def document_database(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> Iterator[tuple[Path, Engine, sessionmaker[Session]]]:
    root = tmp_path / "Document Data_日本語"
    monkeypatch.setenv("TRANSLOKA_DATA_DIR", str(root))
    command.upgrade(Config(str(ALEMBIC_CONFIGURATION)), "head")
    engine = create_sqlite_engine(resolve_local_data_directories(root))
    factory = create_session_factory(engine)
    with transaction_scope(factory) as session:
        ProjectsRepository(session).create(
            project_id=PROJECT_ID,
            name="Document Project",
            description=None,
            source_language="en",
            target_language="id",
            document_type=DocumentType.TECHNICAL_BOOK,
            translation_style=TranslationStyle.PROFESSIONAL,
            reconstruction_mode=ReconstructionMode.HYBRID,
            created_at=CREATED_AT,
        )
        StoredFilesRepository(session).create(
            file_id=ORIGINAL_FILE_ID,
            project_id=PROJECT_ID,
            document_id=None,
            file_role=FileRole.ORIGINAL,
            storage_key=f"projects/{PROJECT_ID}/original/{ORIGINAL_FILE_ID}.pdf",
            original_filename="source.pdf",
            safe_filename=f"{ORIGINAL_FILE_ID}.pdf",
            mime_type="application/pdf",
            size_bytes=100,
            checksum_sha256="a" * 64,
            is_immutable=True,
            status=FileStatus.VALIDATED,
            metadata=None,
            created_at=CREATED_AT,
        )
    yield root, engine, factory
    engine.dispose()


def _document(**overrides: object) -> Document:
    values: dict[str, object] = {
        "id": DOCUMENT_ID,
        "project_id": PROJECT_ID,
        "original_file_id": ORIGINAL_FILE_ID,
        "ir_version": "0.1",
        "title": "System Design",
        "author": "TransLoka",
        "document_type": DocumentType.TECHNICAL_BOOK.value,
        "document_class": DocumentClass.DIGITAL_PDF.value,
        "source_language": "en",
        "target_language": "id",
        "page_count": 4,
        "word_count_estimate": 1200,
        "has_text_layer": 1,
        "scanned_page_count": 0,
        "image_count": 2,
        "table_count": 1,
        "status": DocumentStatus.CREATED.value,
        "metadata_json": '{"pdf_version":"1.7"}',
        "analysis_json": '{"validated":true}',
        "created_at": CREATED_AT,
        "updated_at": CREATED_AT,
    }
    values.update(overrides)
    return Document(**values)


def test_document_migration_has_exact_schema_foreign_keys_and_no_binary(
    document_database: tuple[Path, Engine, sessionmaker[Session]],
) -> None:
    _root, engine, _factory = document_database
    database = inspect(engine)

    assert [column["name"] for column in database.get_columns("documents")] == [
        "id",
        "project_id",
        "original_file_id",
        "ir_version",
        "title",
        "author",
        "document_type",
        "document_class",
        "source_language",
        "target_language",
        "page_count",
        "word_count_estimate",
        "has_text_layer",
        "scanned_page_count",
        "image_count",
        "table_count",
        "status",
        "metadata_json",
        "analysis_json",
        "created_at",
        "updated_at",
    ]
    assert {
        (foreign_key["constrained_columns"][0], foreign_key["referred_table"])
        for foreign_key in database.get_foreign_keys("documents")
    } == {
        ("project_id", "projects"),
        ("original_file_id", "stored_files"),
    }
    assert {
        (foreign_key["constrained_columns"][0], foreign_key["referred_table"])
        for foreign_key in database.get_foreign_keys("stored_files")
    } == {
        ("project_id", "projects"),
        ("document_id", "documents"),
    }
    assert {index["name"]: index["unique"] for index in database.get_indexes("documents")} == {
        "uq_documents_project_original_file": 1
    }
    assert all(
        "BLOB" not in str(column["type"]).upper() for column in database.get_columns("documents")
    )
    with engine.connect() as connection:
        definition = connection.exec_driver_sql(
            "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'documents'"
        ).scalar_one()
        stored_files_definition = connection.exec_driver_sql(
            "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'stored_files'"
        ).scalar_one()
    assert definition.rstrip().endswith("STRICT")
    assert stored_files_definition.rstrip().endswith("STRICT")
    assert "ck_documents_scanned_page_count" in definition
    assert "ck_documents_metadata_json_valid" in definition


def test_valid_document_references_project_and_original_file(
    document_database: tuple[Path, Engine, sessionmaker[Session]],
) -> None:
    _root, _engine, factory = document_database
    with transaction_scope(factory) as session:
        created = _document()
        session.add(created)

    with factory() as session:
        stored = session.get(Document, DOCUMENT_ID)

    assert stored is not None
    assert stored.project_id == PROJECT_ID
    assert stored.original_file_id == ORIGINAL_FILE_ID
    assert stored.document_class == DocumentClass.DIGITAL_PDF.value
    assert stored.status == DocumentStatus.CREATED.value
    assert stored.page_count == 4
    assert stored.scanned_page_count == 0
    assert stored.image_count == 2
    assert stored.table_count == 1


def test_project_original_pair_is_unique(
    document_database: tuple[Path, Engine, sessionmaker[Session]],
) -> None:
    _root, _engine, factory = document_database
    with transaction_scope(factory) as session:
        session.add(_document())

    with factory() as session, pytest.raises(IntegrityError):
        session.add(_document(id=OTHER_DOCUMENT_ID))
        session.flush()


@pytest.mark.parametrize(
    "overrides",
    (
        {"page_count": -1},
        {"word_count_estimate": -1},
        {"has_text_layer": 2},
        {"scanned_page_count": -1},
        {"page_count": 1, "scanned_page_count": 2},
        {"image_count": -1},
        {"table_count": -1},
    ),
)
def test_invalid_counts_are_rejected(
    overrides: dict[str, object],
    document_database: tuple[Path, Engine, sessionmaker[Session]],
) -> None:
    _root, _engine, factory = document_database
    with factory() as session, pytest.raises(IntegrityError):
        session.add(_document(**overrides))
        session.flush()


@pytest.mark.parametrize(
    "overrides",
    (
        {"project_id": "prj_29a7d2d8-f955-4a87-a99a-ecae61088c12"},
        {"original_file_id": "fil_29a7d2d8-f955-4a87-a99a-ecae61088c12"},
    ),
)
def test_missing_project_and_original_file_are_rejected(
    overrides: dict[str, object],
    document_database: tuple[Path, Engine, sessionmaker[Session]],
) -> None:
    _root, _engine, factory = document_database
    with factory() as session, pytest.raises(IntegrityError):
        session.add(_document(**overrides))
        session.flush()


@pytest.mark.parametrize("field", ("metadata_json", "analysis_json"))
def test_invalid_metadata_json_is_rejected(
    field: str,
    document_database: tuple[Path, Engine, sessionmaker[Session]],
) -> None:
    _root, _engine, factory = document_database
    with factory() as session, pytest.raises(IntegrityError):
        session.add(_document(**{field: "{invalid"}))
        session.flush()


def test_document_migration_downgrades_and_reupgrades(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "document migration"
    monkeypatch.setenv("TRANSLOKA_DATA_DIR", str(root))
    configuration = Config(str(ALEMBIC_CONFIGURATION))
    command.upgrade(configuration, "head")
    command.downgrade(configuration, PARENT_REVISION)

    engine = create_sqlite_engine(resolve_local_data_directories(root))
    try:
        database = inspect(engine)
        assert "documents" not in database.get_table_names()
        assert {
            (foreign_key["constrained_columns"][0], foreign_key["referred_table"])
            for foreign_key in database.get_foreign_keys("stored_files")
        } == {("project_id", "projects")}
    finally:
        engine.dispose()

    command.upgrade(configuration, "head")
    engine = create_sqlite_engine(resolve_local_data_directories(root))
    try:
        assert "documents" in inspect(engine).get_table_names()
    finally:
        engine.dispose()


def test_document_model_import_creates_no_database(tmp_path: Path) -> None:
    root = tmp_path / "import data"
    environment = os.environ.copy()
    environment["TRANSLOKA_DATA_DIR"] = str(root)

    result = subprocess.run(
        [sys.executable, "-c", "import transloka_core.database.models.documents"],
        cwd=REPOSITORY_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert not root.exists()
