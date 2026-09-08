import hashlib
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import event, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker
from transloka_api.startup import recover_stale_jobs
from transloka_core.database import create_session_factory, create_sqlite_engine, transaction_scope
from transloka_core.database.models.document_ir import DocumentBlock, DocumentSegment
from transloka_core.database.models.documents import Document
from transloka_core.database.models.files import StoredFile
from transloka_core.database.models.jobs import ApplicationJob, JobAttempt, JobStatus, JobType
from transloka_core.database.models.pages import DocumentPage
from transloka_core.database.models.projects import Project
from transloka_core.jobs.dispatch import JobDispatchService
from transloka_core.jobs.recovery import (
    JobRecoveryService,
    RecoveryArtifact,
    RecoveryArtifactError,
    RecoveryArtifactState,
)
from transloka_core.jobs.retry import JobRetryService
from transloka_core.storage import LocalDataDirectories, resolve_local_data_directories

REPOSITORY_ROOT = Path(__file__).parents[2]
ALEMBIC_CONFIGURATION = REPOSITORY_ROOT / "alembic.ini"
RECOVERY_TIME = datetime(2026, 8, 8, 12, 0, tzinfo=UTC)
STALE_THRESHOLD = timedelta(minutes=5)


class RecordingQueue:
    name = "test-recovery"

    def enqueue(self, _job_id: str) -> None:
        pass


@pytest.fixture
def recovery_database(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> Iterator[tuple[LocalDataDirectories, Engine, sessionmaker[Session]]]:
    root = tmp_path / "recovery data"
    monkeypatch.setenv("TRANSLOKA_DATA_DIR", str(root))
    command.upgrade(Config(str(ALEMBIC_CONFIGURATION)), "head")
    directories = resolve_local_data_directories(root)
    engine = create_sqlite_engine(directories)
    factory = create_session_factory(engine)
    try:
        yield directories, engine, factory
    finally:
        engine.dispose()


def _running_job(factory: sessionmaker[Session], key: str, heartbeat_at: str) -> str:
    job_id = (
        JobDispatchService(factory, RecordingQueue())
        .dispatch(
            job_type=JobType.MAINTENANCE,
            idempotency_key=key,
        )
        .job_id
    )
    with transaction_scope(factory) as session:
        row = session.get(ApplicationJob, job_id)
        assert row is not None
        row.status = JobStatus.RUNNING.value
        row.progress = 0.4
        row.current_stage = "PROCESSING"
        row.started_at = "2026-08-08T11:00:00.000Z"
        row.heartbeat_at = heartbeat_at
    return job_id


def _service(
    factory: sessionmaker[Session], directories: LocalDataDirectories
) -> JobRecoveryService:
    return JobRecoveryService(
        factory,
        data_root=directories.root,
        temporary_root=directories.temporary,
    )


def test_stale_running_job_is_visible_and_healthy_job_is_untouched(
    recovery_database: tuple[LocalDataDirectories, Engine, sessionmaker[Session]],
) -> None:
    directories, _engine, factory = recovery_database
    stale_id = _running_job(factory, "stale-job", "2026-08-08T11:54:59.000Z")
    healthy_id = _running_job(factory, "healthy-job", "2026-08-08T11:55:01.000Z")

    results = _service(factory, directories).recover(
        stale_threshold=STALE_THRESHOLD,
        now=RECOVERY_TIME,
    )

    assert [(result.job_id, result.status) for result in results] == [(stale_id, JobStatus.STALE)]
    assert results[0].retry_available
    with factory() as session:
        stale = session.get(ApplicationJob, stale_id)
        healthy = session.get(ApplicationJob, healthy_id)
        assert stale is not None
        assert healthy is not None
        assert stale.status == JobStatus.STALE.value
        assert stale.current_stage == JobStatus.STALE.value
        assert stale.error_code == "WORKER_HEARTBEAT_STALE"
        assert stale.completed_at == "2026-08-08T12:00:00.000Z"
        assert healthy.status == JobStatus.RUNNING.value
        assert healthy.current_stage == "PROCESSING"
        attempt = session.scalar(select(JobAttempt).where(JobAttempt.job_id == stale_id))
        assert attempt is not None
        assert attempt.status == "STALE"


def test_incomplete_temporary_output_is_removed(
    recovery_database: tuple[LocalDataDirectories, Engine, sessionmaker[Session]],
) -> None:
    directories, _engine, factory = recovery_database
    job_id = _running_job(factory, "incomplete-output", "2026-08-08T11:00:00.000Z")
    incomplete = directories.temporary / "job-output.partial"
    incomplete.parent.mkdir(parents=True, exist_ok=True)
    incomplete.write_bytes(b"incomplete")

    result = _service(factory, directories).recover(
        stale_threshold=STALE_THRESHOLD,
        artifacts={job_id: RecoveryArtifact(incomplete_outputs=(incomplete,))},
        now=RECOVERY_TIME,
    )

    assert result[0].artifact_state is RecoveryArtifactState.INCOMPLETE_REMOVED
    assert not incomplete.exists()


def test_valid_atomic_output_is_preserved_but_does_not_auto_complete(
    recovery_database: tuple[LocalDataDirectories, Engine, sessionmaker[Session]],
) -> None:
    directories, _engine, factory = recovery_database
    job_id = _running_job(factory, "valid-atomic-output", "2026-08-08T11:00:00.000Z")
    final_output = directories.projects / "project-1" / "final.pdf"
    final_output.parent.mkdir(parents=True, exist_ok=True)
    content = b"validated final output"
    final_output.write_bytes(content)
    with transaction_scope(factory) as session:
        row = session.get(ApplicationJob, job_id)
        assert row is not None
        row.result_json = '{"artifact_id":"valid-prior-result"}'

    result = _service(factory, directories).recover(
        stale_threshold=STALE_THRESHOLD,
        artifacts={
            job_id: RecoveryArtifact(
                final_output=final_output,
                checksum_sha256=hashlib.sha256(content).hexdigest(),
                size_bytes=len(content),
            )
        },
        now=RECOVERY_TIME,
    )

    assert result[0].artifact_state is RecoveryArtifactState.VALID_ATOMIC
    assert final_output.read_bytes() == content
    with factory() as session:
        row = session.get(ApplicationJob, job_id)
        assert row is not None
        assert row.status == JobStatus.STALE.value
        assert row.result_json == '{"artifact_id":"valid-prior-result"}'

    retry = JobRetryService(factory).request(
        job_id,
        idempotency_key="recovery-retry",
        retry_failed_items_only=True,
        reason="USER_CONFIRMED_STALE_RECOVERY",
    )
    assert retry.status is JobStatus.RETRYING
    assert final_output.read_bytes() == content


def test_file_existence_without_integrity_metadata_is_not_completion_evidence(
    recovery_database: tuple[LocalDataDirectories, Engine, sessionmaker[Session]],
) -> None:
    directories, _engine, factory = recovery_database
    job_id = _running_job(factory, "unverified-output", "2026-08-08T11:00:00.000Z")
    final_output = directories.projects / "project-1" / "unverified.pdf"
    final_output.parent.mkdir(parents=True, exist_ok=True)
    final_output.write_bytes(b"file existence is insufficient")

    result = _service(factory, directories).recover(
        stale_threshold=STALE_THRESHOLD,
        artifacts={job_id: RecoveryArtifact(final_output=final_output)},
        now=RECOVERY_TIME,
    )

    assert result[0].status is JobStatus.STALE
    assert result[0].artifact_state is RecoveryArtifactState.PRESENT_UNVERIFIED
    assert final_output.exists()


def test_application_restart_runs_recovery_once_without_duplicate_work(
    recovery_database: tuple[LocalDataDirectories, Engine, sessionmaker[Session]],
) -> None:
    directories, engine, factory = recovery_database
    job_id = _running_job(factory, "restart-job", "2026-08-08T11:00:00.000Z")
    incomplete = directories.temporary / "restart.partial"
    incomplete.parent.mkdir(parents=True, exist_ok=True)
    incomplete.write_bytes(b"interrupted")
    engine.dispose()

    restarted_engine = create_sqlite_engine(directories)
    restarted_factory = create_session_factory(restarted_engine)
    try:
        first = recover_stale_jobs(
            restarted_factory,
            directories,
            stale_threshold=STALE_THRESHOLD,
            artifacts={job_id: RecoveryArtifact(incomplete_outputs=(incomplete,))},
            now=RECOVERY_TIME,
        )
        second = recover_stale_jobs(
            restarted_factory,
            directories,
            stale_threshold=STALE_THRESHOLD,
            artifacts={job_id: RecoveryArtifact(incomplete_outputs=(incomplete,))},
            now=RECOVERY_TIME,
        )

        assert [result.job_id for result in first] == [job_id]
        assert second == ()
        assert not incomplete.exists()
        with restarted_factory() as session:
            assert session.scalar(select(JobAttempt).where(JobAttempt.job_id == job_id)) is not None
            assert len(session.scalars(select(JobAttempt)).all()) == 1
    finally:
        restarted_engine.dispose()


def test_recovery_rejects_cleanup_outside_temporary_storage(
    recovery_database: tuple[LocalDataDirectories, Engine, sessionmaker[Session]],
    tmp_path: Path,
) -> None:
    directories, _engine, factory = recovery_database
    job_id = _running_job(factory, "unsafe-cleanup", "2026-08-08T11:00:00.000Z")
    outside = tmp_path / "outside.partial"
    outside.write_bytes(b"must remain")

    with pytest.raises(RecoveryArtifactError):
        _service(factory, directories).recover(
            stale_threshold=STALE_THRESHOLD,
            artifacts={job_id: RecoveryArtifact(incomplete_outputs=(outside,))},
            now=RECOVERY_TIME,
        )

    assert outside.exists()
    with factory() as session:
        row = session.get(ApplicationJob, job_id)
        assert row is not None
        assert row.status == JobStatus.RUNNING.value


def _translation_segments(factory: sessionmaker[Session]) -> tuple[str, str, str]:
    project_id, document_id, file_id, page_id, block_id = (
        f"{prefix}_{uuid4()}" for prefix in ("prj", "doc", "fil", "pag", "blk")
    )
    segment_id = f"seg_{uuid4()}"
    timestamp = "2026-08-08T11:00:00.000Z"
    with transaction_scope(factory) as session:
        session.add(
            Project(
                id=project_id,
                name="Recovery test",
                status="CREATED",
                source_language="en",
                target_language="id",
                document_type="TECHNICAL_BOOK",
                translation_style="PROFESSIONAL",
                reconstruction_mode="HYBRID",
                progress=0.0,
                settings_json="{}",
                created_at=timestamp,
                updated_at=timestamp,
            )
        )
        session.flush()
        session.add(
            StoredFile(
                id=file_id,
                project_id=project_id,
                file_role="ORIGINAL",
                storage_key=f"projects/{project_id}/original/source.pdf",
                safe_filename="source.pdf",
                mime_type="application/pdf",
                size_bytes=100,
                checksum_sha256="a" * 64,
                is_immutable=1,
                status="AVAILABLE",
                created_at=timestamp,
            )
        )
        session.flush()
        session.add(
            Document(
                id=document_id,
                project_id=project_id,
                original_file_id=file_id,
                ir_version="0.1",
                document_type="TECHNICAL_BOOK",
                document_class="DIGITAL_PDF",
                source_language="en",
                target_language="id",
                page_count=1,
                word_count_estimate=2,
                has_text_layer=1,
                scanned_page_count=0,
                image_count=0,
                table_count=0,
                status="STRUCTURED",
                created_at=timestamp,
                updated_at=timestamp,
            )
        )
        session.flush()
        session.add(
            DocumentPage(
                id=page_id,
                document_id=document_id,
                source_page_number=1,
                width_points=595.0,
                height_points=842.0,
                rotation_degrees=0.0,
                page_type="DIGITAL",
                column_count=1,
                reading_direction="LTR",
                status="STRUCTURED",
                created_at=timestamp,
                updated_at=timestamp,
            )
        )
        session.flush()
        session.add(
            DocumentBlock(
                id=block_id,
                page_id=page_id,
                block_type="PARAGRAPH",
                semantic_role="BODY_TEXT",
                page_reading_order=0,
                global_reading_order=0,
                source_text="Original text.",
                normalized_source_text="Original text.",
                source_geometry_json="{}",
                status="STRUCTURED",
                created_at=timestamp,
                updated_at=timestamp,
            )
        )
        session.flush()
        session.add(
            DocumentSegment(
                id=segment_id,
                block_id=block_id,
                segment_order=0,
                source_text="Original text.",
                resolved_source_text="Original text.",
                normalized_source_text="Original text.",
                source_language="en",
                target_language="id",
                status="TRANSLATING",
                review_status="NOT_REVIEWED",
                is_locked=0,
                current_revision=2,
                created_at=timestamp,
                updated_at=timestamp,
            )
        )
    return project_id, document_id, segment_id


def _translation_job(
    factory: sessionmaker[Session],
    project_id: str,
    document_id: str,
    status: JobStatus,
) -> str:
    job_id = (
        JobDispatchService(factory, RecordingQueue())
        .dispatch(
            job_type=JobType.TRANSLATE_DOCUMENT,
            idempotency_key=str(uuid4()),
            project_id=project_id,
            document_id=document_id,
        )
        .job_id
    )
    with transaction_scope(factory) as session:
        row = session.get(ApplicationJob, job_id)
        assert row is not None
        row.status = status.value
        row.heartbeat_at = "2026-08-08T12:00:00.000Z"
    return job_id


@pytest.mark.parametrize(
    "status",
    [
        JobStatus.FAILED,
        JobStatus.CANCELLED,
        JobStatus.STALE,
        JobStatus.COMPLETED,
        JobStatus.COMPLETED_WITH_WARNINGS,
        JobStatus.PARTIALLY_COMPLETED,
    ],
)
@pytest.mark.parametrize("machine_text", [None, "", " \t\r\n", "Teks hasil mesin."])
def test_terminal_translation_recovers_only_status_and_is_idempotent(
    recovery_database: tuple[LocalDataDirectories, Engine, sessionmaker[Session]],
    status: JobStatus,
    machine_text: str | None,
) -> None:
    directories, _engine, factory = recovery_database
    project_id, document_id, segment_id = _translation_segments(factory)
    _translation_job(factory, project_id, document_id, status)
    with transaction_scope(factory) as session:
        row = session.get(DocumentSegment, segment_id)
        assert row is not None
        row.machine_translation = machine_text
    with factory() as session:
        before = dict(session.execute(select(DocumentSegment.__table__)).mappings().one())

    assert recover_stale_jobs(factory, directories, now=RECOVERY_TIME) == ()
    with factory() as session:
        after = dict(session.execute(select(DocumentSegment.__table__)).mappings().one())
    expected = dict(before)
    has_machine_text = bool(machine_text and machine_text.strip())
    expected.update(
        status="NEEDS_REVIEW" if has_machine_text else "READY_FOR_TRANSLATION",
        review_status="REVIEW_REQUIRED" if has_machine_text else "NOT_REVIEWED",
        updated_at="2026-08-08T12:00:00.000Z",
    )
    assert after == expected
    assert recover_stale_jobs(factory, directories, now=RECOVERY_TIME + timedelta(hours=1)) == ()
    with factory() as session:
        assert dict(session.execute(select(DocumentSegment.__table__)).mappings().one()) == after


@pytest.mark.parametrize(
    "status",
    [
        JobStatus.CREATED,
        JobStatus.QUEUED,
        JobStatus.RUNNING,
        JobStatus.RETRYING,
        JobStatus.CANCELLATION_REQUESTED,
    ],
)
def test_active_translation_prevents_recovery_despite_older_terminal_job(
    recovery_database: tuple[LocalDataDirectories, Engine, sessionmaker[Session]],
    status: JobStatus,
) -> None:
    directories, _engine, factory = recovery_database
    project_id, document_id, segment_id = _translation_segments(factory)
    _translation_job(factory, project_id, document_id, JobStatus.FAILED)
    _translation_job(factory, project_id, document_id, status)
    # An unrelated document must still be recovered; the active-job guard is document-local.
    other_project, other_document, other_segment = _translation_segments(factory)
    _translation_job(factory, other_project, other_document, JobStatus.FAILED)
    recover_stale_jobs(factory, directories, now=RECOVERY_TIME)
    with factory() as session:
        row = session.get(DocumentSegment, segment_id)
        other = session.get(DocumentSegment, other_segment)
        assert row is not None and row.status == "TRANSLATING"
        assert other is not None and other.status == "READY_FOR_TRANSLATION"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("is_locked", 1),
        ("status", "LOCKED"),
        ("status", "APPROVED"),
        ("status", "USER_EDITED"),
        ("status", "MACHINE_TRANSLATED"),
        ("status", "NEEDS_REVIEW"),
        ("review_status", "APPROVED"),
        ("review_status", "EDITED"),
        ("review_status", "IN_REVIEW"),
        ("review_status", "REJECTED"),
        ("reviewed_translation", "Hasil pengguna."),
        ("final_text", "Hasil final."),
        ("resolved_source_text", " \t\n"),
    ],
)
def test_translation_recovery_preserves_protected_or_unready_segments(
    recovery_database: tuple[LocalDataDirectories, Engine, sessionmaker[Session]],
    field: str,
    value: object,
) -> None:
    directories, _engine, factory = recovery_database
    project_id, document_id, segment_id = _translation_segments(factory)
    _translation_job(factory, project_id, document_id, JobStatus.FAILED)
    with transaction_scope(factory) as session:
        row = session.get(DocumentSegment, segment_id)
        assert row is not None
        setattr(row, field, value)
    with factory() as session:
        before = dict(session.execute(select(DocumentSegment.__table__)).mappings().one())
    recover_stale_jobs(factory, directories, now=RECOVERY_TIME)
    with factory() as session:
        assert dict(session.execute(select(DocumentSegment.__table__)).mappings().one()) == before


@pytest.mark.parametrize("unrelated_job", [False, True])
def test_translation_recovery_requires_terminal_translation_evidence(
    recovery_database: tuple[LocalDataDirectories, Engine, sessionmaker[Session]],
    unrelated_job: bool,
) -> None:
    directories, _engine, factory = recovery_database
    project_id, document_id, segment_id = _translation_segments(factory)
    if unrelated_job:
        job_id = _translation_job(factory, project_id, document_id, JobStatus.FAILED)
        with transaction_scope(factory) as session:
            row = session.get(ApplicationJob, job_id)
            assert row is not None
            row.job_type = JobType.OCR_DOCUMENT.value
    recover_stale_jobs(factory, directories, now=RECOVERY_TIME)
    with factory() as session:
        segment = session.get(DocumentSegment, segment_id)
        assert segment is not None and segment.status == "TRANSLATING"


def test_newly_stale_translation_recovers_segments_in_same_startup(
    recovery_database: tuple[LocalDataDirectories, Engine, sessionmaker[Session]],
) -> None:
    directories, _engine, factory = recovery_database
    project_id, document_id, segment_id = _translation_segments(factory)
    job_id = _translation_job(factory, project_id, document_id, JobStatus.RUNNING)
    with transaction_scope(factory) as session:
        row = session.get(ApplicationJob, job_id)
        assert row is not None
        row.heartbeat_at = "2026-08-08T11:00:00.000Z"
    results = recover_stale_jobs(factory, directories, now=RECOVERY_TIME)
    assert len(results) == 1 and results[0].job_id == job_id
    assert results[0].status is JobStatus.STALE
    with factory() as session:
        segment = session.get(DocumentSegment, segment_id)
        assert segment is not None and segment.status == "READY_FOR_TRANSLATION"


@pytest.mark.parametrize("concurrent_change", ["queue", "review"])
def test_translation_recovery_rechecks_guards_at_write_time(
    recovery_database: tuple[LocalDataDirectories, Engine, sessionmaker[Session]],
    concurrent_change: str,
) -> None:
    directories, engine, factory = recovery_database
    project_id, document_id, segment_id = _translation_segments(factory)
    _translation_job(factory, project_id, document_id, JobStatus.FAILED)
    changed = False

    def change_before_update(*args: object) -> None:
        nonlocal changed
        statement = str(args[2])
        if changed or not statement.startswith("UPDATE document_segments SET status="):
            return
        changed = True
        if concurrent_change == "queue":
            _translation_job(factory, project_id, document_id, JobStatus.QUEUED)
        else:
            with transaction_scope(factory) as session:
                segment = session.get(DocumentSegment, segment_id)
                assert segment is not None
                segment.reviewed_translation = "Hasil review bersamaan."
                segment.review_status = "EDITED"
                segment.current_revision += 1

    event.listen(engine, "before_cursor_execute", change_before_update)
    try:
        recover_stale_jobs(factory, directories, now=RECOVERY_TIME)
    finally:
        event.remove(engine, "before_cursor_execute", change_before_update)
    assert changed
    with factory() as session:
        segment = session.get(DocumentSegment, segment_id)
        assert segment is not None and segment.status == "TRANSLATING"
        if concurrent_change == "review":
            assert segment.reviewed_translation == "Hasil review bersamaan."
            assert segment.review_status == "EDITED"
            assert segment.current_revision == 3
