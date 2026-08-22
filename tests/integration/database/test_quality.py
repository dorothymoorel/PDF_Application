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
from transloka_core.database import create_session_factory, create_sqlite_engine, transaction_scope
from transloka_core.database.models.documents import Document, DocumentClass, DocumentStatus
from transloka_core.database.models.files import FileRole, FileStatus, StoredFile
from transloka_core.database.models.projects import (
    DocumentType,
    Project,
    ReconstructionMode,
    TranslationStyle,
)
from transloka_core.database.models.quality import (
    QualityCheck,
    QualityCheckStatus,
    QualityReport,
    QualityReportStatus,
    QualityReportType,
)
from transloka_core.storage import resolve_local_data_directories

REPOSITORY_ROOT = Path(__file__).parents[3]
ALEMBIC_CONFIGURATION = REPOSITORY_ROOT / "alembic.ini"
PARENT_REVISION = "0015_exports"
CREATED_AT = "2026-08-22T00:00:00.000Z"
PROJECT_ID = f"prj_{UUID(int=700)}"
DOCUMENT_ID = f"doc_{UUID(int=701)}"
FILE_ID = f"fil_{UUID(int=702)}"


@pytest.fixture
def quality_database(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> Iterator[tuple[Path, Engine, sessionmaker[Session]]]:
    root = tmp_path / "quality data"
    monkeypatch.setenv("TRANSLOKA_DATA_DIR", os.fspath(root))
    command.upgrade(Config(str(ALEMBIC_CONFIGURATION)), "head")
    engine = create_sqlite_engine(resolve_local_data_directories(root))
    factory = create_session_factory(engine)
    try:
        with transaction_scope(factory) as session:
            session.add(
                Project(
                    id=PROJECT_ID,
                    name="Quality project",
                    description=None,
                    status="READY_FOR_REVIEW",
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
                    id=FILE_ID,
                    project_id=PROJECT_ID,
                    document_id=None,
                    file_role=FileRole.ORIGINAL.value,
                    storage_key=f"projects/{PROJECT_ID}/original/source.pdf",
                    original_filename="source.pdf",
                    safe_filename="source.pdf",
                    mime_type="application/pdf",
                    size_bytes=1,
                    checksum_sha256="a" * 64,
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
                    original_file_id=FILE_ID,
                    ir_version="0.1",
                    title="Quality document",
                    author=None,
                    document_type=DocumentType.TECHNICAL_BOOK.value,
                    document_class=DocumentClass.DIGITAL_PDF.value,
                    source_language="en",
                    target_language="id",
                    page_count=1,
                    word_count_estimate=1,
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


def _report(**overrides: object) -> QualityReport:
    values: dict[str, object] = {
        "id": f"report_{UUID(int=710)}",
        "project_id": PROJECT_ID,
        "document_id": DOCUMENT_ID,
        "report_type": QualityReportType.TRANSLATION.value,
        "version": "qa_0.1",
        "status": QualityReportStatus.PASSED_WITH_WARNINGS.value,
        "overall_score": 0.9,
        "critical_warning_count": 0,
        "high_warning_count": 1,
        "medium_warning_count": 2,
        "low_warning_count": 3,
        "summary_json": '{"source":"test"}',
        "created_at": CREATED_AT,
    }
    values.update(overrides)
    return QualityReport(**values)


def test_quality_migration_has_expected_tables_columns_indexes_and_strict_mode(
    quality_database: tuple[Path, Engine, sessionmaker[Session]],
) -> None:
    _root, engine, _factory = quality_database
    database = inspect(engine)
    assert [column["name"] for column in database.get_columns("quality_reports")] == [
        "id",
        "project_id",
        "document_id",
        "report_type",
        "version",
        "status",
        "overall_score",
        "critical_warning_count",
        "high_warning_count",
        "medium_warning_count",
        "low_warning_count",
        "summary_json",
        "created_at",
    ]
    assert [column["name"] for column in database.get_columns("quality_checks")] == [
        "id",
        "report_id",
        "check_type",
        "scope_type",
        "scope_id",
        "status",
        "score",
        "details_json",
        "created_at",
    ]
    assert {
        index["name"]: index["unique"] for index in database.get_indexes("quality_reports")
    } == {
        "ix_quality_reports_project_status": 0,
        "ix_quality_reports_project_type": 0,
    }
    assert {index["name"]: index["unique"] for index in database.get_indexes("quality_checks")} == {
        "ix_quality_checks_report_status": 0,
        "ix_quality_checks_scope": 0,
    }
    with engine.connect() as connection:
        for table_name in ("quality_reports", "quality_checks"):
            table_sql = connection.exec_driver_sql(
                "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = ?",
                (table_name,),
            ).scalar_one()
            assert table_sql.rstrip().endswith("STRICT")


def test_quality_report_and_check_persist_and_check_cascade(
    quality_database: tuple[Path, Engine, sessionmaker[Session]],
) -> None:
    _root, engine, factory = quality_database
    report = _report()
    check = QualityCheck(
        id=f"check_{UUID(int=711)}",
        report_id=report.id,
        check_type="NUMERICAL_INTEGRITY",
        scope_type="DOCUMENT",
        scope_id=DOCUMENT_ID,
        status=QualityCheckStatus.PASSED.value,
        score=1.0,
        details_json='{"matched":1}',
        created_at=CREATED_AT,
    )
    with transaction_scope(factory) as session:
        session.add(report)
        session.flush()
        session.add(check)

    with factory() as session:
        persisted = session.get(QualityReport, report.id)
        assert persisted is not None
        assert persisted.high_warning_count == 1
        assert session.get(QualityCheck, check.id) is not None

    with engine.begin() as connection:
        connection.exec_driver_sql("DELETE FROM quality_reports WHERE id = ?", (report.id,))
    with factory() as session:
        assert session.get(QualityCheck, check.id) is None


@pytest.mark.parametrize(
    "overrides",
    (
        {"report_type": "UNKNOWN"},
        {"status": "UNKNOWN"},
        {"overall_score": 1.1},
        {"summary_json": "{invalid"},
        {"high_warning_count": -1},
    ),
)
def test_quality_report_constraints_reject_invalid_values(
    quality_database: tuple[Path, Engine, sessionmaker[Session]],
    overrides: dict[str, object],
) -> None:
    _root, _engine, factory = quality_database
    with factory() as session, pytest.raises(IntegrityError):
        session.add(_report(**overrides))
        session.flush()


def test_quality_migration_downgrades_and_reupgrades_cleanly(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "quality migration"
    monkeypatch.setenv("TRANSLOKA_DATA_DIR", os.fspath(root))
    configuration = Config(str(ALEMBIC_CONFIGURATION))
    command.upgrade(configuration, "head")
    command.downgrade(configuration, PARENT_REVISION)
    engine = create_sqlite_engine(resolve_local_data_directories(root))
    try:
        assert not {"quality_reports", "quality_checks"} & set(inspect(engine).get_table_names())
    finally:
        engine.dispose()
    command.upgrade(configuration, "head")
    engine = create_sqlite_engine(resolve_local_data_directories(root))
    try:
        assert {"quality_reports", "quality_checks"} <= set(inspect(engine).get_table_names())
    finally:
        engine.dispose()
