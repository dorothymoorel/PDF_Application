import os
import subprocess
import sys
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
from transloka_core.database.models.documents import (
    Document,
    DocumentClass,
    DocumentStatus,
)
from transloka_core.database.models.files import FileRole, FileStatus
from transloka_core.database.models.jobs import (
    ApplicationJob,
    JobAttempt,
    JobAttemptStatus,
    JobDependency,
    JobDependencyType,
    JobStatus,
    JobType,
)
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
PARENT_REVISION = "0005_documents"
PROJECT_ID = "prj_550e8400-e29b-41d4-a716-446655440000"
ORIGINAL_FILE_ID = "fil_550e8400-e29b-41d4-a716-446655440000"
DOCUMENT_ID = "doc_550e8400-e29b-41d4-a716-446655440000"
CREATED_AT = "2026-07-29T00:00:00.000Z"


@pytest.fixture
def job_database(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> Iterator[tuple[Path, Engine, sessionmaker[Session]]]:
    root = tmp_path / "Job Data_日本語"
    monkeypatch.setenv("TRANSLOKA_DATA_DIR", str(root))
    command.upgrade(Config(str(ALEMBIC_CONFIGURATION)), "head")
    engine = create_sqlite_engine(resolve_local_data_directories(root))
    factory = create_session_factory(engine)
    with transaction_scope(factory) as session:
        ProjectsRepository(session).create(
            project_id=PROJECT_ID,
            name="Job Project",
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
        session.add(
            Document(
                id=DOCUMENT_ID,
                project_id=PROJECT_ID,
                original_file_id=ORIGINAL_FILE_ID,
                ir_version="0.1",
                title="Job Document",
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
                status=DocumentStatus.CREATED.value,
                metadata_json=None,
                analysis_json=None,
                created_at=CREATED_AT,
                updated_at=CREATED_AT,
            )
        )
    yield root, engine, factory
    engine.dispose()


def _job_id(value: int) -> str:
    return f"job_{UUID(int=value)}"


def _job(index: int = 1, **overrides: object) -> ApplicationJob:
    values: dict[str, object] = {
        "id": _job_id(index),
        "project_id": PROJECT_ID,
        "document_id": DOCUMENT_ID,
        "parent_job_id": None,
        "job_type": JobType.IMPORT_DOCUMENT.value,
        "queue_name": "default",
        "status": JobStatus.CREATED.value,
        "progress": 0.0,
        "current_stage": None,
        "idempotency_key": f"job-key-{index}",
        "payload_json": '{"document_id":"doc_123"}',
        "result_json": None,
        "retry_count": 0,
        "max_retries": 3,
        "error_code": None,
        "error_message": None,
        "created_at": CREATED_AT,
        "queued_at": None,
        "started_at": None,
        "completed_at": None,
        "cancelled_at": None,
        "heartbeat_at": None,
    }
    values.update(overrides)
    return ApplicationJob(**values)


def test_job_migration_has_exact_schema_constraints_indexes_and_foreign_keys(
    job_database: tuple[Path, Engine, sessionmaker[Session]],
) -> None:
    _root, engine, _factory = job_database
    database = inspect(engine)

    assert [column["name"] for column in database.get_columns("application_jobs")] == [
        "id",
        "project_id",
        "document_id",
        "parent_job_id",
        "job_type",
        "queue_name",
        "status",
        "progress",
        "current_stage",
        "idempotency_key",
        "payload_json",
        "result_json",
        "retry_count",
        "max_retries",
        "error_code",
        "error_message",
        "created_at",
        "queued_at",
        "started_at",
        "completed_at",
        "cancelled_at",
        "heartbeat_at",
    ]
    assert [column["name"] for column in database.get_columns("job_attempts")] == [
        "id",
        "job_id",
        "attempt_number",
        "status",
        "worker_identifier",
        "started_at",
        "completed_at",
        "duration_ms",
        "error_code",
        "error_message",
        "details_json",
    ]
    assert [column["name"] for column in database.get_columns("job_dependencies")] == [
        "job_id",
        "depends_on_job_id",
        "dependency_type",
    ]
    assert {
        column["name"] for column in database.get_columns("application_jobs") if column["nullable"]
    } == {
        "project_id",
        "document_id",
        "parent_job_id",
        "current_stage",
        "result_json",
        "error_code",
        "error_message",
        "queued_at",
        "started_at",
        "completed_at",
        "cancelled_at",
        "heartbeat_at",
    }
    assert {
        column["name"] for column in database.get_columns("job_attempts") if column["nullable"]
    } == {
        "worker_identifier",
        "completed_at",
        "duration_ms",
        "error_code",
        "error_message",
        "details_json",
    }
    assert all(not column["nullable"] for column in database.get_columns("job_dependencies"))
    assert database.get_pk_constraint("application_jobs")["constrained_columns"] == ["id"]
    assert database.get_pk_constraint("job_attempts")["constrained_columns"] == ["id"]
    assert database.get_pk_constraint("job_dependencies")["constrained_columns"] == [
        "job_id",
        "depends_on_job_id",
    ]
    assert {
        (foreign_key["constrained_columns"][0], foreign_key["referred_table"])
        for foreign_key in database.get_foreign_keys("application_jobs")
    } == {
        ("project_id", "projects"),
        ("document_id", "documents"),
    }
    assert {
        (foreign_key["constrained_columns"][0], foreign_key["referred_table"])
        for foreign_key in database.get_foreign_keys("job_attempts")
    } == {("job_id", "application_jobs")}
    assert {
        (foreign_key["constrained_columns"][0], foreign_key["referred_table"])
        for foreign_key in database.get_foreign_keys("job_dependencies")
    } == {
        ("job_id", "application_jobs"),
        ("depends_on_job_id", "application_jobs"),
    }
    assert {
        index["name"]: index["unique"] for index in database.get_indexes("application_jobs")
    } == {
        "ix_application_jobs_heartbeat": 0,
        "ix_application_jobs_project_status": 0,
        "ix_application_jobs_type_status": 0,
        "uq_application_jobs_idempotency_key": 1,
    }
    assert {index["name"]: index["unique"] for index in database.get_indexes("job_attempts")} == {
        "uq_job_attempts_number": 1
    }

    with engine.connect() as connection:
        definitions = {
            table: connection.exec_driver_sql(
                "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = ?",
                (table,),
            ).scalar_one()
            for table in ("application_jobs", "job_attempts", "job_dependencies")
        }
    assert all(definition.rstrip().endswith("STRICT") for definition in definitions.values())
    assert "ck_application_jobs_progress" in definitions["application_jobs"]
    assert "ck_application_jobs_payload_json_valid" in definitions["application_jobs"]
    assert "ck_job_attempts_number" in definitions["job_attempts"]
    assert "ck_job_dependencies_type" in definitions["job_dependencies"]
    all_columns = {
        column["name"]
        for table in ("application_jobs", "job_attempts", "job_dependencies")
        for column in database.get_columns(table)
    }
    assert not any(
        forbidden in column
        for column in all_columns
        for forbidden in ("secret", "token", "traceback", "absolute_path")
    )
    assert all(
        "BLOB" not in str(column["type"]).upper()
        for table in ("application_jobs", "job_attempts", "job_dependencies")
        for column in database.get_columns(table)
    )


def test_all_canonical_job_and_attempt_values_are_persisted(
    job_database: tuple[Path, Engine, sessionmaker[Session]],
) -> None:
    _root, _engine, factory = job_database
    job_types = list(JobType)
    job_statuses = list(JobStatus)
    assert len(job_types) == len(job_statuses)

    with transaction_scope(factory) as session:
        for index, (job_type, status) in enumerate(
            zip(job_types, job_statuses, strict=True),
            start=1,
        ):
            session.add(
                _job(
                    index,
                    job_type=job_type.value,
                    status=status.value,
                    progress=1.0 if status is JobStatus.COMPLETED else 0.0,
                )
            )
        for index, attempt_status in enumerate(JobAttemptStatus, start=1):
            session.add(
                JobAttempt(
                    id=str(UUID(int=100 + index)),
                    job_id=_job_id(1),
                    attempt_number=index,
                    status=attempt_status.value,
                    worker_identifier=None,
                    started_at=CREATED_AT,
                    completed_at=None,
                    duration_ms=None,
                    error_code=None,
                    error_message=None,
                    details_json=None,
                )
            )

    with factory() as session:
        assert {row.job_type for row in session.query(ApplicationJob)} == {
            member.value for member in JobType
        }
        assert {row.status for row in session.query(ApplicationJob)} == {
            member.value for member in JobStatus
        }
        assert {row.status for row in session.query(JobAttempt)} == {
            member.value for member in JobAttemptStatus
        }


def test_database_rejects_invalid_job_values(
    job_database: tuple[Path, Engine, sessionmaker[Session]],
) -> None:
    _root, _engine, factory = job_database
    invalid_values: tuple[dict[str, object], ...] = (
        {"id": "job_invalid"},
        {"job_type": "CUSTOM"},
        {"status": "CUSTOM"},
        {"progress": -0.01},
        {"progress": 1.01},
        {"progress": float("nan")},
        {"retry_count": -1},
        {"max_retries": -1},
        {"payload_json": "{invalid"},
        {"payload_json": "NaN"},
        {"result_json": "Infinity"},
        {"project_id": "prj_29a7d2d8-f955-4a87-a99a-ecae61088c12"},
        {"document_id": "doc_29a7d2d8-f955-4a87-a99a-ecae61088c12"},
        {"queue_name": None},
    )

    for index, overrides in enumerate(invalid_values, start=100):
        with factory() as session, pytest.raises(IntegrityError):
            session.add(_job(index, **overrides))
            session.flush()


def test_idempotency_attempt_and_dependency_constraints(
    job_database: tuple[Path, Engine, sessionmaker[Session]],
) -> None:
    _root, _engine, factory = job_database
    with transaction_scope(factory) as session:
        session.add_all((_job(1), _job(2)))
        session.add(
            JobAttempt(
                id=str(UUID(int=1)),
                job_id=_job_id(1),
                attempt_number=1,
                status=JobAttemptStatus.RUNNING.value,
                worker_identifier="worker-1",
                started_at=CREATED_AT,
                completed_at=None,
                duration_ms=None,
                error_code=None,
                error_message=None,
                details_json="{}",
            )
        )
        session.add(
            JobDependency(
                job_id=_job_id(2),
                depends_on_job_id=_job_id(1),
                dependency_type=JobDependencyType.REQUIRED.value,
            )
        )

    invalid_attempts: tuple[dict[str, object], ...] = (
        {"attempt_number": 1},
        {"attempt_number": 0},
        {"attempt_number": 2, "status": "CUSTOM"},
        {"attempt_number": 2, "duration_ms": -1},
        {"attempt_number": 2, "details_json": "{invalid"},
        {"attempt_number": 2, "job_id": _job_id(99)},
    )
    for index, overrides in enumerate(invalid_attempts, start=10):
        values: dict[str, object] = {
            "id": str(UUID(int=index)),
            "job_id": _job_id(1),
            "attempt_number": 2,
            "status": JobAttemptStatus.RUNNING.value,
            "worker_identifier": None,
            "started_at": CREATED_AT,
            "completed_at": None,
            "duration_ms": None,
            "error_code": None,
            "error_message": None,
            "details_json": None,
        }
        values.update(overrides)
        with factory() as session, pytest.raises(IntegrityError):
            session.add(JobAttempt(**values))
            session.flush()

    invalid_dependencies = (
        JobDependency(
            job_id=_job_id(1),
            depends_on_job_id=_job_id(2),
            dependency_type="CUSTOM",
        ),
        JobDependency(
            job_id=_job_id(99),
            depends_on_job_id=_job_id(1),
            dependency_type=JobDependencyType.REQUIRED.value,
        ),
    )
    for dependency in invalid_dependencies:
        with factory() as session, pytest.raises(IntegrityError):
            session.add(dependency)
            session.flush()

    with factory() as session, pytest.raises(IntegrityError):
        session.add(_job(3, idempotency_key="job-key-1"))
        session.flush()


def test_job_persists_after_engine_disposal_and_restart(
    job_database: tuple[Path, Engine, sessionmaker[Session]],
) -> None:
    root, first_engine, first_factory = job_database
    with transaction_scope(first_factory) as session:
        session.add(_job())
    first_engine.dispose()

    second_engine = create_sqlite_engine(resolve_local_data_directories(root))
    try:
        with create_session_factory(second_engine)() as session:
            persisted = session.get(ApplicationJob, _job_id(1))
            assert persisted is not None
            assert persisted.job_type == JobType.IMPORT_DOCUMENT.value
            assert persisted.status == JobStatus.CREATED.value
            assert persisted.payload_json == '{"document_id":"doc_123"}'
            assert persisted.result_json is None
            assert persisted.created_at == CREATED_AT
    finally:
        second_engine.dispose()


def test_job_migration_downgrades_only_job_tables_and_reupgrades(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "job migration"
    monkeypatch.setenv("TRANSLOKA_DATA_DIR", str(root))
    configuration = Config(str(ALEMBIC_CONFIGURATION))
    command.upgrade(configuration, "head")
    command.downgrade(configuration, PARENT_REVISION)

    engine = create_sqlite_engine(resolve_local_data_directories(root))
    try:
        tables = set(inspect(engine).get_table_names())
        assert "application_jobs" not in tables
        assert "job_attempts" not in tables
        assert "job_dependencies" not in tables
        assert {"projects", "stored_files", "documents"} <= tables
    finally:
        engine.dispose()

    command.upgrade(configuration, "head")
    command.upgrade(configuration, "head")
    engine = create_sqlite_engine(resolve_local_data_directories(root))
    try:
        assert {
            "application_jobs",
            "job_attempts",
            "job_dependencies",
        } <= set(inspect(engine).get_table_names())
    finally:
        engine.dispose()


def test_job_model_import_creates_no_database(tmp_path: Path) -> None:
    root = tmp_path / "job import data"
    environment = os.environ.copy()
    environment["TRANSLOKA_DATA_DIR"] = str(root)

    result = subprocess.run(
        [sys.executable, "-c", "import transloka_core.database.models.jobs"],
        cwd=REPOSITORY_ROOT,
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert not root.exists()
