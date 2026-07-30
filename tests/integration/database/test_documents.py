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
from transloka_core.database.models.pages import DocumentPage, PageType
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
PAGE_PARENT_REVISION = "0006_application_jobs"
PROJECT_ID = "prj_550e8400-e29b-41d4-a716-446655440000"
ORIGINAL_FILE_ID = "fil_550e8400-e29b-41d4-a716-446655440000"
DOCUMENT_ID = "doc_550e8400-e29b-41d4-a716-446655440000"
OTHER_DOCUMENT_ID = "doc_29a7d2d8-f955-4a87-a99a-ecae61088c12"
PAGE_ID = "pag_550e8400-e29b-41d4-a716-446655440000"
OTHER_PAGE_ID = "pag_29a7d2d8-f955-4a87-a99a-ecae61088c12"
RENDER_FILE_ID = "fil_29a7d2d8-f955-4a87-a99a-ecae61088c12"
THUMBNAIL_FILE_ID = "fil_7b8772aa-9e28-4b21-827f-2da5ebc54cc0"
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


def _page(**overrides: object) -> DocumentPage:
    values: dict[str, object] = {
        "id": PAGE_ID,
        "document_id": DOCUMENT_ID,
        "source_page_number": 1,
        "logical_page_number": "i",
        "width_points": 595.28,
        "height_points": 841.89,
        "rotation_degrees": 0.0,
        "page_type": PageType.DIGITAL.value,
        "page_classification": "SINGLE_COLUMN",
        "column_count": 1,
        "reading_direction": "LTR",
        "status": DocumentStatus.ANALYZED.value,
        "render_file_id": None,
        "thumbnail_file_id": None,
        "native_extraction_confidence": 0.98,
        "ocr_confidence": None,
        "structure_confidence": 0.94,
        "metadata_json": '{"has_text_layer":true}',
        "created_at": CREATED_AT,
        "updated_at": CREATED_AT,
    }
    values.update(overrides)
    return DocumentPage(**values)


def _persist_document(factory: sessionmaker[Session]) -> None:
    with transaction_scope(factory) as session:
        session.add(_document())


def _persist_page_artifacts(factory: sessionmaker[Session]) -> None:
    with transaction_scope(factory) as session:
        repository = StoredFilesRepository(session)
        for file_id, role, suffix, mime_type in (
            (RENDER_FILE_ID, FileRole.PAGE_RENDER, "png", "image/png"),
            (THUMBNAIL_FILE_ID, FileRole.THUMBNAIL, "webp", "image/webp"),
        ):
            repository.create(
                file_id=file_id,
                project_id=PROJECT_ID,
                document_id=DOCUMENT_ID,
                file_role=role,
                storage_key=f"projects/{PROJECT_ID}/pages/{file_id}.{suffix}",
                original_filename=None,
                safe_filename=f"{file_id}.{suffix}",
                mime_type=mime_type,
                size_bytes=100,
                checksum_sha256=("b" if role is FileRole.PAGE_RENDER else "c") * 64,
                is_immutable=False,
                status=FileStatus.AVAILABLE,
                metadata=None,
                created_at=CREATED_AT,
            )


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


def test_page_migration_has_exact_schema_indexes_and_foreign_keys(
    document_database: tuple[Path, Engine, sessionmaker[Session]],
) -> None:
    _root, engine, _factory = document_database
    database = inspect(engine)

    assert [column["name"] for column in database.get_columns("document_pages")] == [
        "id",
        "document_id",
        "source_page_number",
        "logical_page_number",
        "width_points",
        "height_points",
        "rotation_degrees",
        "page_type",
        "page_classification",
        "column_count",
        "reading_direction",
        "status",
        "render_file_id",
        "thumbnail_file_id",
        "native_extraction_confidence",
        "ocr_confidence",
        "structure_confidence",
        "metadata_json",
        "created_at",
        "updated_at",
    ]
    assert {
        (foreign_key["constrained_columns"][0], foreign_key["referred_table"])
        for foreign_key in database.get_foreign_keys("document_pages")
    } == {
        ("document_id", "documents"),
        ("render_file_id", "stored_files"),
        ("thumbnail_file_id", "stored_files"),
    }
    assert {index["name"]: index["unique"] for index in database.get_indexes("document_pages")} == {
        "ix_document_pages_status": 0,
        "ix_document_pages_type": 0,
        "uq_document_pages_number": 1,
    }
    with engine.connect() as connection:
        definition = connection.exec_driver_sql(
            "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'document_pages'"
        ).scalar_one()
    assert definition.rstrip().endswith("STRICT")
    assert "ck_document_pages_geometry" in definition
    assert "ck_document_pages_rotation" in definition
    assert "ck_document_pages_native_confidence" in definition
    assert all(
        "BLOB" not in str(column["type"]).upper()
        for column in database.get_columns("document_pages")
    )


def test_page_persists_stable_number_geometry_and_render_references(
    document_database: tuple[Path, Engine, sessionmaker[Session]],
) -> None:
    _root, _engine, factory = document_database
    _persist_document(factory)
    _persist_page_artifacts(factory)

    with transaction_scope(factory) as session:
        session.add(
            _page(
                render_file_id=RENDER_FILE_ID,
                thumbnail_file_id=THUMBNAIL_FILE_ID,
            )
        )

    with factory() as session:
        stored = session.get(DocumentPage, PAGE_ID)

    assert stored is not None
    assert stored.document_id == DOCUMENT_ID
    assert stored.source_page_number == 1
    assert stored.logical_page_number == "i"
    assert stored.width_points == 595.28
    assert stored.height_points == 841.89
    assert stored.page_type == PageType.DIGITAL.value
    assert stored.render_file_id == RENDER_FILE_ID
    assert stored.thumbnail_file_id == THUMBNAIL_FILE_ID


def test_source_page_number_is_positive_and_unique_per_document(
    document_database: tuple[Path, Engine, sessionmaker[Session]],
) -> None:
    _root, _engine, factory = document_database
    _persist_document(factory)
    with transaction_scope(factory) as session:
        session.add(_page())

    for page in (
        _page(id=OTHER_PAGE_ID),
        _page(id=OTHER_PAGE_ID, source_page_number=0),
    ):
        with factory() as session, pytest.raises(IntegrityError):
            session.add(page)
            session.flush()


@pytest.mark.parametrize("rotation", (0.0, 90.0, 180.0, 270.0))
def test_canonical_page_rotations_are_persisted(
    rotation: float,
    document_database: tuple[Path, Engine, sessionmaker[Session]],
) -> None:
    _root, _engine, factory = document_database
    _persist_document(factory)

    with transaction_scope(factory) as session:
        session.add(_page(rotation_degrees=rotation))

    with factory() as session:
        stored = session.get(DocumentPage, PAGE_ID)

    assert stored is not None
    assert stored.rotation_degrees == rotation


@pytest.mark.parametrize(
    "overrides",
    (
        {"width_points": 0.0},
        {"height_points": 0.0},
        {"width_points": -1.0},
        {"rotation_degrees": 45.0},
        {"column_count": -1},
    ),
)
def test_invalid_page_geometry_is_rejected(
    overrides: dict[str, object],
    document_database: tuple[Path, Engine, sessionmaker[Session]],
) -> None:
    _root, _engine, factory = document_database
    _persist_document(factory)

    with factory() as session, pytest.raises(IntegrityError):
        session.add(_page(**overrides))
        session.flush()


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("native_extraction_confidence", -0.01),
        ("native_extraction_confidence", 1.01),
        ("ocr_confidence", -0.01),
        ("ocr_confidence", 1.01),
        ("structure_confidence", -0.01),
        ("structure_confidence", 1.01),
    ),
)
def test_invalid_page_confidence_is_rejected(
    field: str,
    value: float,
    document_database: tuple[Path, Engine, sessionmaker[Session]],
) -> None:
    _root, _engine, factory = document_database
    _persist_document(factory)

    with factory() as session, pytest.raises(IntegrityError):
        session.add(_page(**{field: value}))
        session.flush()


@pytest.mark.parametrize(
    "overrides",
    (
        {"document_id": OTHER_DOCUMENT_ID},
        {"render_file_id": RENDER_FILE_ID},
        {"thumbnail_file_id": THUMBNAIL_FILE_ID},
        {"page_type": "CUSTOM"},
        {"metadata_json": "{invalid"},
    ),
)
def test_invalid_page_references_and_values_are_rejected(
    overrides: dict[str, object],
    document_database: tuple[Path, Engine, sessionmaker[Session]],
) -> None:
    _root, _engine, factory = document_database
    _persist_document(factory)

    with factory() as session, pytest.raises(IntegrityError):
        session.add(_page(**overrides))
        session.flush()


def test_page_model_import_creates_no_database(tmp_path: Path) -> None:
    root = tmp_path / "page import data"
    environment = os.environ.copy()
    environment["TRANSLOKA_DATA_DIR"] = str(root)

    result = subprocess.run(
        [sys.executable, "-c", "import transloka_core.database.models.pages"],
        cwd=REPOSITORY_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert not root.exists()


def test_page_migration_downgrades_only_page_table_and_reupgrades(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "page migration"
    monkeypatch.setenv("TRANSLOKA_DATA_DIR", str(root))
    configuration = Config(str(ALEMBIC_CONFIGURATION))
    command.upgrade(configuration, "head")
    command.downgrade(configuration, PAGE_PARENT_REVISION)

    engine = create_sqlite_engine(resolve_local_data_directories(root))
    try:
        tables = set(inspect(engine).get_table_names())
        assert "document_pages" not in tables
        assert {"documents", "application_jobs", "job_attempts"} <= tables
    finally:
        engine.dispose()

    command.upgrade(configuration, "head")
    command.upgrade(configuration, "head")
    engine = create_sqlite_engine(resolve_local_data_directories(root))
    try:
        assert "document_pages" in inspect(engine).get_table_names()
    finally:
        engine.dispose()
