import os
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
from transloka_core.database.models.documents import Document, DocumentClass, DocumentStatus
from transloka_core.database.models.exports import Export, ExportStatus, ExportType
from transloka_core.database.models.files import FileRole, FileStatus, StoredFile
from transloka_core.database.models.projects import (
    DocumentType,
    Project,
    ReconstructionMode,
    TranslationStyle,
)
from transloka_core.storage import resolve_local_data_directories

REPOSITORY_ROOT = Path(__file__).parents[3]
ALEMBIC_CONFIGURATION = REPOSITORY_ROOT / "alembic.ini"
PARENT_REVISION = "0014_reconstruction"
CREATED_AT = "2026-08-22T00:00:00.000Z"
PROJECT_ID = f"prj_{UUID(int=100)}"
DOCUMENT_ID = f"doc_{UUID(int=101)}"
ORIGINAL_FILE_ID = f"fil_{UUID(int=102)}"
EXPORT_FILE_ID = f"fil_{UUID(int=103)}"
RECONSTRUCTION_JOB_ID = f"rcj_{UUID(int=104)}"
CHECKSUM = "a" * 64


@pytest.fixture
def export_database(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> Iterator[tuple[Path, Engine, sessionmaker[Session]]]:
    root = tmp_path / "Export Data_日本語"
    monkeypatch.setenv("TRANSLOKA_DATA_DIR", os.fspath(root))
    command.upgrade(Config(str(ALEMBIC_CONFIGURATION)), "head")
    engine = create_sqlite_engine(resolve_local_data_directories(root))
    factory = create_session_factory(engine)
    try:
        with transaction_scope(factory) as session:
            session.add(
                Project(
                    id=PROJECT_ID,
                    name="Export Project",
                    description=None,
                    status="READY_FOR_EXPORT",
                    source_language="en",
                    target_language="id",
                    document_type=DocumentType.TECHNICAL_BOOK.value,
                    translation_style=TranslationStyle.PROFESSIONAL.value,
                    reconstruction_mode=ReconstructionMode.HYBRID.value,
                    progress=1.0,
                    active_document_id=None,
                    settings_json="{}",
                    created_at=CREATED_AT,
                    updated_at=CREATED_AT,
                    archived_at=None,
                    deleted_at=None,
                )
            )
            session.flush()
            session.add(
                StoredFile(
                    id=ORIGINAL_FILE_ID,
                    project_id=PROJECT_ID,
                    document_id=None,
                    file_role=FileRole.ORIGINAL.value,
                    storage_key=f"projects/{PROJECT_ID}/original/source.pdf",
                    original_filename="source.pdf",
                    safe_filename="source.pdf",
                    mime_type="application/pdf",
                    size_bytes=100,
                    checksum_sha256=CHECKSUM,
                    is_immutable=1,
                    status=FileStatus.VALIDATED.value,
                    metadata_json=None,
                    created_at=CREATED_AT,
                    deleted_at=None,
                )
            )
            session.flush()
            session.add(
                Document(
                    id=DOCUMENT_ID,
                    project_id=PROJECT_ID,
                    original_file_id=ORIGINAL_FILE_ID,
                    ir_version="0.1",
                    title="Export Document",
                    author=None,
                    document_type=DocumentType.TECHNICAL_BOOK.value,
                    document_class=DocumentClass.DIGITAL_PDF.value,
                    source_language="en",
                    target_language="id",
                    page_count=1,
                    word_count_estimate=100,
                    has_text_layer=1,
                    scanned_page_count=0,
                    image_count=0,
                    table_count=0,
                    status=DocumentStatus.REVIEWED.value,
                    metadata_json=None,
                    analysis_json=None,
                    created_at=CREATED_AT,
                    updated_at=CREATED_AT,
                )
            )
        yield root, engine, factory
    finally:
        engine.dispose()


def _export(index: int = 1, **overrides: object) -> Export:
    values: dict[str, object] = {
        "id": f"exp_{UUID(int=200 + index)}",
        "project_id": PROJECT_ID,
        "document_id": DOCUMENT_ID,
        "reconstruction_job_id": None,
        "file_id": None,
        "export_type": ExportType.TRANSLATED_PDF.value,
        "output_profile": "STANDARD",
        "version_number": index,
        "status": ExportStatus.CREATED.value,
        "page_count": None,
        "size_bytes": None,
        "checksum_sha256": None,
        "validation_report_id": None,
        "settings_json": "{}",
        "created_at": CREATED_AT,
        "completed_at": None,
        "error_code": None,
    }
    values.update(overrides)
    return Export(**values)


def test_export_migration_has_schema_indexes_and_strict_mode(
    export_database: tuple[Path, Engine, sessionmaker[Session]],
) -> None:
    _root, engine, _factory = export_database
    database = inspect(engine)
    assert [column["name"] for column in database.get_columns("exports")] == [
        "id",
        "project_id",
        "document_id",
        "reconstruction_job_id",
        "file_id",
        "export_type",
        "output_profile",
        "version_number",
        "status",
        "page_count",
        "size_bytes",
        "checksum_sha256",
        "validation_report_id",
        "settings_json",
        "created_at",
        "completed_at",
        "error_code",
    ]
    assert database.get_pk_constraint("exports")["constrained_columns"] == ["id"]
    assert {index["name"]: index["unique"] for index in database.get_indexes("exports")} == {
        "uq_exports_project_type_version": 1,
        "ix_exports_project_status": 0,
    }
    with engine.connect() as connection:
        table_sql = connection.exec_driver_sql(
            "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'exports'"
        ).scalar_one()
    assert table_sql.rstrip().endswith("STRICT")


def test_export_versions_are_persisted_and_old_versions_are_not_overwritten(
    export_database: tuple[Path, Engine, sessionmaker[Session]],
) -> None:
    _root, _engine, factory = export_database
    with transaction_scope(factory) as session:
        session.add(_export(1))
        session.add(_export(2))
        session.add(_export(3, export_type=ExportType.BILINGUAL_PDF.value))

    with factory() as session:
        rows = session.query(Export).order_by(Export.version_number).all()
        assert [(row.export_type, row.version_number) for row in rows] == [
            (ExportType.TRANSLATED_PDF.value, 1),
            (ExportType.TRANSLATED_PDF.value, 2),
            (ExportType.BILINGUAL_PDF.value, 3),
        ]

    with factory() as session, pytest.raises(IntegrityError):
        session.add(_export(4, id=f"exp_{UUID(int=204)}", version_number=2))
        session.flush()


def test_completed_export_requires_file_size_page_count_checksum_and_completion_time(
    export_database: tuple[Path, Engine, sessionmaker[Session]],
) -> None:
    _root, _engine, factory = export_database
    with factory() as session, pytest.raises(IntegrityError):
        session.add(_export(10, status=ExportStatus.COMPLETED.value))
        session.flush()

    with transaction_scope(factory) as session:
        session.add(
            StoredFile(
                id=EXPORT_FILE_ID,
                project_id=PROJECT_ID,
                document_id=DOCUMENT_ID,
                file_role=FileRole.EXPORT.value,
                storage_key=f"projects/{PROJECT_ID}/exports/export-v1.pdf",
                original_filename="export-v1.pdf",
                safe_filename="export-v1.pdf",
                mime_type="application/pdf",
                size_bytes=2048,
                checksum_sha256=CHECKSUM,
                is_immutable=1,
                status=FileStatus.VALIDATED.value,
                metadata_json=None,
                created_at=CREATED_AT,
                deleted_at=None,
            )
        )
        session.flush()
        session.add(
            _export(
                11,
                file_id=EXPORT_FILE_ID,
                status=ExportStatus.COMPLETED.value,
                page_count=12,
                size_bytes=2048,
                checksum_sha256=CHECKSUM,
                validation_report_id="val_1",
                completed_at=CREATED_AT,
            )
        )

    with factory() as session:
        completed = session.get(Export, f"exp_{UUID(int=211)}")
        assert completed is not None
        assert completed.status == ExportStatus.COMPLETED.value
        assert completed.file_id == EXPORT_FILE_ID
        assert completed.validation_report_id == "val_1"


@pytest.mark.parametrize(
    "overrides",
    (
        {"export_type": "UNKNOWN"},
        {"output_profile": ""},
        {"version_number": 0},
        {"status": "UNKNOWN"},
        {"page_count": -1},
        {"size_bytes": -1},
        {"checksum_sha256": "not-a-sha256"},
        {"settings_json": "{invalid"},
    ),
)
def test_export_constraints_reject_invalid_values(
    export_database: tuple[Path, Engine, sessionmaker[Session]],
    overrides: dict[str, object],
) -> None:
    _root, _engine, factory = export_database
    with factory() as session, pytest.raises(IntegrityError):
        session.add(_export(30, **overrides))
        session.flush()


def test_missing_foreign_key_file_is_rejected(
    export_database: tuple[Path, Engine, sessionmaker[Session]],
) -> None:
    _root, _engine, factory = export_database
    with factory() as session, pytest.raises(IntegrityError):
        session.add(
            _export(
                40,
                file_id=f"fil_{UUID(int=999)}",
                status=ExportStatus.COMPLETED.value,
                page_count=1,
                size_bytes=1,
                checksum_sha256=CHECKSUM,
                completed_at=CREATED_AT,
            )
        )
        session.flush()


def test_export_migration_downgrades_and_reupgrades_cleanly(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "export-migration"
    monkeypatch.setenv("TRANSLOKA_DATA_DIR", os.fspath(root))
    configuration = Config(str(ALEMBIC_CONFIGURATION))
    command.upgrade(configuration, "head")
    command.downgrade(configuration, PARENT_REVISION)
    engine = create_sqlite_engine(resolve_local_data_directories(root))
    try:
        assert "exports" not in inspect(engine).get_table_names()
    finally:
        engine.dispose()

    command.upgrade(configuration, "head")
    engine = create_sqlite_engine(resolve_local_data_directories(root))
    try:
        assert "exports" in inspect(engine).get_table_names()
    finally:
        engine.dispose()
