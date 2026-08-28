# mypy: ignore-errors
import json
from pathlib import Path
from uuid import UUID

import pytest
from alembic import command as alembic_command
from alembic.config import Config
from transloka_core.database import create_session_factory, create_sqlite_engine
from transloka_core.database.models.documents import Document  # noqa: F401
from transloka_core.database.models.files import StoredFile  # noqa: F401
from transloka_core.database.models.jobs import ApplicationJob, JobStatus, JobType
from transloka_core.database.models.projects import Project  # noqa: F401
from transloka_core.storage import resolve_local_data_directories
from transloka_worker.backup import BackupCommand, BackupWorkerError, DatabaseBackupRequestLoader

REPOSITORY_ROOT = Path(__file__).parents[3]
ALEMBIC_CONFIGURATION = REPOSITORY_ROOT / "alembic.ini"


def _id(prefix: str, value: int) -> str:
    return f"{prefix}{UUID(int=value)}"


JOB_ID = _id("job_", 100)
OTHER_JOB_ID = _id("job_", 101)


@pytest.fixture
def loader_setup(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    root = tmp_path / "backup loader"
    monkeypatch.setenv("TRANSLOKA_DATA_DIR", str(root))
    alembic_command.upgrade(Config(str(ALEMBIC_CONFIGURATION)), "head")
    directories = resolve_local_data_directories(root)
    engine = create_sqlite_engine(directories)
    factory = create_session_factory(engine)
    # create a valid BACKUP_DATABASE job
    from transloka_core.database import transaction_scope
    from transloka_worker.backup import BackupCommand

    cmd = BackupCommand(backup_type="METADATA")
    payload = json.dumps(cmd.to_payload(), sort_keys=True, separators=(",", ":"))
    with transaction_scope(factory) as session:
        session.add(
            ApplicationJob(
                id=JOB_ID,
                project_id=None,
                document_id=None,
                parent_job_id=None,
                job_type=JobType.BACKUP_DATABASE.value,
                queue_name="transloka",
                status=JobStatus.QUEUED.value,
                progress=0.0,
                current_stage="QUEUED",
                idempotency_key="loader-test-1",
                payload_json=payload,
                result_json=None,
                retry_count=0,
                max_retries=3,
                error_code=None,
                error_message=None,
                created_at="2026-08-27T00:00:00.000Z",
                queued_at="2026-08-27T00:00:00.000Z",
                started_at=None,
                completed_at=None,
                cancelled_at=None,
                heartbeat_at=None,
            )
        )
    loader = DatabaseBackupRequestLoader(factory)
    yield loader, factory, engine
    engine.dispose()


def test_loader_loads_backup_command_after_api_dispatch_commits(loader_setup) -> None:
    loader, factory, engine = loader_setup
    loaded = loader.load(JOB_ID)
    assert loaded.job_id == JOB_ID
    assert loaded.command.backup_type == "METADATA"


def test_loader_rejects_wrong_job_type(
    loader_setup, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    loader, factory, engine = loader_setup
    # create a TRANSLATE job with same id pattern
    from transloka_core.database import transaction_scope

    cmd = BackupCommand(backup_type="DATABASE_ONLY")
    payload = json.dumps(cmd.to_payload(), sort_keys=True, separators=(",", ":"))
    other_id = OTHER_JOB_ID
    with transaction_scope(factory) as session:
        session.add(
            ApplicationJob(
                id=other_id,
                project_id=None,
                document_id=None,
                parent_job_id=None,
                job_type=JobType.TRANSLATE_DOCUMENT.value,
                queue_name="transloka",
                status=JobStatus.QUEUED.value,
                progress=0.0,
                current_stage="QUEUED",
                idempotency_key="other-job",
                payload_json=payload,
                result_json=None,
                retry_count=0,
                max_retries=3,
                error_code=None,
                error_message=None,
                created_at="2026-08-27T00:00:00.000Z",
                queued_at="2026-08-27T00:00:00.000Z",
                started_at=None,
                completed_at=None,
                cancelled_at=None,
                heartbeat_at=None,
            )
        )
    with pytest.raises(BackupWorkerError, match="unavailable"):
        loader.load(other_id)


def test_loader_rejects_missing_job(loader_setup) -> None:
    loader, factory, engine = loader_setup
    with pytest.raises(BackupWorkerError):
        loader.load(_id("job_", 9999))


def test_loader_rejects_corrupt_payload_json(loader_setup) -> None:
    loader, factory, engine = loader_setup
    from transloka_core.database import transaction_scope

    with transaction_scope(factory) as session:
        job = session.get(ApplicationJob, JOB_ID)
        assert job is not None
        job.payload_json = json.dumps({"not": "a backup command"})
    with pytest.raises(BackupWorkerError):
        loader.load(JOB_ID)


def test_loader_rejects_unsupported_backup_type_in_payload(loader_setup) -> None:
    loader, factory, engine = loader_setup
    from transloka_core.database import transaction_scope

    with transaction_scope(factory) as session:
        job = session.get(ApplicationJob, JOB_ID)
        assert job is not None
        job.payload_json = json.dumps(
            {
                "schema": "transloka.backup.command.v1",
                "backup_type": "FULL_APPLICATION",
                "include_queue_database": False,
                "include_temporary": False,
            },
            sort_keys=True,
            separators=(",", ":"),
        )
    with pytest.raises(BackupWorkerError):
        loader.load(JOB_ID)


def test_loader_rejects_queue_mismatch(loader_setup) -> None:
    loader, factory, engine = loader_setup
    from transloka_core.database import transaction_scope

    with transaction_scope(factory) as session:
        job = session.get(ApplicationJob, JOB_ID)
        assert job is not None
        job.queue_name = "transloka-api"
    with pytest.raises(BackupWorkerError, match="unavailable"):
        loader.load(JOB_ID)
