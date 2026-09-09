import json
import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any, cast
from uuid import UUID

import pytest
from alembic import command
from alembic.config import Config
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker
from transloka_api.app import create_app
from transloka_api.middleware import (
    CLIENT_HEADER,
    CLIENT_HEADER_VALUE,
    CLIENT_VERSION_HEADER,
    CLIENT_VERSION_VALUE,
)
from transloka_core.database import transaction_scope
from transloka_core.database.models.document_ir import (
    BlockType,
    DocumentBlock,
    DocumentSegment,
    ReviewStatus,
    SegmentStatus,
    SemanticRole,
)
from transloka_core.database.models.documents import (
    Document,
    DocumentClass,
    DocumentStatus,
)
from transloka_core.database.models.files import FileRole, FileStatus, StoredFile
from transloka_core.database.models.glossary import GlossaryConflict, GlossarySnapshot
from transloka_core.database.models.jobs import (
    ApplicationJob,
    JobAttempt,
    JobAttemptStatus,
    JobStatus,
    JobType,
)
from transloka_core.database.models.models import LocalModelRecord, ModelLicenseStatus
from transloka_core.database.models.pages import DocumentPage, PageType
from transloka_core.database.models.projects import Project
from transloka_translation.providers import ProviderHealth, ProviderHealthStatus
from transloka_worker.health import PersistedWorkerHeartbeat, WorkerStatus
from transloka_worker.translation import TranslationCommand

REPOSITORY_ROOT = Path(__file__).parents[3]
ALEMBIC_CONFIGURATION = REPOSITORY_ROOT / "alembic.ini"
CLIENT_HEADERS = {
    CLIENT_HEADER: CLIENT_HEADER_VALUE,
    CLIENT_VERSION_HEADER: CLIENT_VERSION_VALUE,
}
CREATED_AT = "2026-08-18T00:00:00.000Z"
PROJECT = {
    "name": "Translation API Project",
    "description": None,
    "source_language": "en",
    "target_language": "id",
    "document_type": "TECHNICAL_BOOK",
    "translation_style": "PROFESSIONAL",
    "reconstruction_mode": "HYBRID",
}


def _id(prefix: str, value: int) -> str:
    return f"{prefix}{UUID(int=value)}"


ORIGINAL_FILE_ID = _id("fil_", 100)
DOCUMENT_ID = _id("doc_", 101)
PAGE_ID = _id("pag_", 102)
BLOCK_ID = _id("blk_", 103)
SEGMENT_ID = _id("seg_", 104)
MODEL_ID = _id("mdl_", 105)


class HealthyProvider:
    async def health_check(self) -> ProviderHealth:
        return ProviderHealth(status=ProviderHealthStatus.AVAILABLE, version="test")


class UnavailableProvider:
    async def health_check(self) -> ProviderHealth:
        return ProviderHealth(status=ProviderHealthStatus.UNAVAILABLE, detail="test")


class UnexpectedProvider:
    async def health_check(self) -> ProviderHealth:
        pytest.fail("An unselected provider must not be contacted.")


class RecordingQueue:
    name = "translation"

    def __init__(self) -> None:
        self.enqueued: list[str] = []

    def enqueue(self, job_id: str) -> None:
        self.enqueued.append(job_id)


class UnavailableQueue:
    name = "translation"

    def enqueue(self, _job_id: str) -> None:
        raise OSError("queue unavailable")


class StaticWorkerHeartbeatStore:
    def __init__(
        self,
        status: WorkerStatus | None = WorkerStatus.RUNNING,
        *,
        recorded_at: float | None = None,
    ) -> None:
        self._status = status
        self._recorded_at = time.time() if recorded_at is None else recorded_at

    def read(self) -> PersistedWorkerHeartbeat | None:
        if self._status is None:
            return None
        return PersistedWorkerHeartbeat(
            worker_name="transloka-worker",
            worker_identifier="test-worker",
            status=self._status,
            sequence=1,
            recorded_at=self._recorded_at,
        )


@pytest.fixture
def translation_api(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> Iterator[tuple[TestClient, sessionmaker[Session], str, FastAPI]]:
    root = tmp_path / "translation api"
    monkeypatch.setenv("TRANSLOKA_DATA_DIR", str(root))
    monkeypatch.delenv("TRANSLOKA_CT2_OLLAMA_FALLBACK_MODEL", raising=False)
    command.upgrade(Config(str(ALEMBIC_CONFIGURATION)), "head")
    application = create_app()
    with TestClient(application) as client:
        application.state.ollama_provider = HealthyProvider()
        application.state.translation_queue = RecordingQueue()
        application.state.worker_heartbeat_store = StaticWorkerHeartbeatStore()
        project_response = client.post(
            "/api/v1/projects",
            headers=CLIENT_HEADERS,
            json=PROJECT,
        )
        assert project_response.status_code == 201
        project_id = cast(str, project_response.json()["data"]["id"])
        factory = cast(sessionmaker[Session], application.state.session_factory)
        _seed_translation_inputs(factory, project_id)
        yield client, factory, project_id, application


def _seed_translation_inputs(factory: sessionmaker[Session], project_id: str) -> None:
    with transaction_scope(factory) as session:
        session.add(
            StoredFile(
                id=ORIGINAL_FILE_ID,
                project_id=project_id,
                document_id=None,
                file_role=FileRole.ORIGINAL.value,
                storage_key=f"projects/{project_id}/original/source.pdf",
                original_filename="source.pdf",
                safe_filename="source.pdf",
                mime_type="application/pdf",
                size_bytes=100,
                checksum_sha256="a" * 64,
                is_immutable=1,
                status=FileStatus.AVAILABLE.value,
                metadata_json=None,
                created_at=CREATED_AT,
                deleted_at=None,
            )
        )
        session.flush()
        session.add(
            Document(
                id=DOCUMENT_ID,
                project_id=project_id,
                original_file_id=ORIGINAL_FILE_ID,
                ir_version="0.1",
                title="Translation document",
                author=None,
                document_type="TECHNICAL_BOOK",
                document_class=DocumentClass.DIGITAL_PDF.value,
                source_language="en",
                target_language="id",
                page_count=1,
                word_count_estimate=2,
                has_text_layer=1,
                scanned_page_count=0,
                image_count=0,
                table_count=0,
                status=DocumentStatus.STRUCTURED.value,
                metadata_json=None,
                analysis_json=None,
                created_at=CREATED_AT,
                updated_at=CREATED_AT,
            )
        )
        session.flush()
        session.add(
            DocumentPage(
                id=PAGE_ID,
                document_id=DOCUMENT_ID,
                source_page_number=1,
                logical_page_number="1",
                width_points=595.28,
                height_points=841.89,
                rotation_degrees=0.0,
                page_type=PageType.DIGITAL.value,
                page_classification="SINGLE_COLUMN",
                column_count=1,
                reading_direction="LTR",
                status=DocumentStatus.STRUCTURED.value,
                render_file_id=None,
                thumbnail_file_id=None,
                native_extraction_confidence=0.99,
                ocr_confidence=None,
                structure_confidence=0.95,
                metadata_json=None,
                created_at=CREATED_AT,
                updated_at=CREATED_AT,
            )
        )
        session.flush()
        session.add(
            DocumentBlock(
                id=BLOCK_ID,
                page_id=PAGE_ID,
                section_id=None,
                parent_block_id=None,
                block_type=BlockType.PARAGRAPH.value,
                semantic_role=SemanticRole.BODY_TEXT.value,
                page_reading_order=0,
                global_reading_order=0,
                source_text="The workflow starts.",
                normalized_source_text="The workflow starts.",
                source_geometry_json='{"x":1,"y":1,"width":10,"height":10}',
                target_geometry_json=None,
                style_json=None,
                detail_json=None,
                status=DocumentStatus.STRUCTURED.value,
                confidence=0.99,
                created_at=CREATED_AT,
                updated_at=CREATED_AT,
            )
        )
        session.flush()
        session.add(
            DocumentSegment(
                id=SEGMENT_ID,
                block_id=BLOCK_ID,
                section_id=None,
                segment_order=0,
                global_order=0,
                source_text="The workflow starts.",
                native_text="The workflow starts.",
                ocr_text=None,
                resolved_source_text="The workflow starts.",
                normalized_source_text="the workflow starts.",
                protected_source_text=None,
                machine_translation=None,
                reviewed_translation=None,
                final_text=None,
                source_language="en",
                target_language="id",
                status=SegmentStatus.READY_FOR_TRANSLATION.value,
                review_status=ReviewStatus.NOT_REVIEWED.value,
                is_locked=0,
                current_revision=0,
                confidence_overall=0.99,
                confidence_json=None,
                translation_settings_hash=None,
                created_at=CREATED_AT,
                updated_at=CREATED_AT,
            )
        )
        session.add(
            LocalModelRecord(
                id=MODEL_ID,
                ollama_model_name="translation-test:latest",
                model_family=None,
                parameter_class=None,
                quantization=None,
                disk_size_bytes=1024,
                license_name=None,
                license_status=ModelLicenseStatus.UNKNOWN.value,
                is_installed=1,
                is_selected_translation=1,
                is_selected_validation=0,
                metadata_json=None,
                last_detected_at=CREATED_AT,
            )
        )
        project = session.get(Project, project_id)
        assert project is not None
        project.active_document_id = DOCUMENT_ID


def _readiness(client: TestClient, project_id: str) -> Any:
    return client.get(f"/api/v1/projects/{project_id}/translation-readiness")


@pytest.mark.parametrize("batch_size", [1, 5, 10])
@pytest.mark.parametrize("job_status", ["RUNNING", "FAILED", "COMPLETED"])
def test_status_uses_saved_document_coverage_and_actual_job_batches(
    translation_api: tuple[TestClient, sessionmaker[Session], str, FastAPI],
    batch_size: int,
    job_status: str,
) -> None:
    client, factory, project_id, _application = translation_api
    response = client.post(
        f"/api/v1/projects/{project_id}/translation/start",
        headers={**CLIENT_HEADERS, "Idempotency-Key": "coverage-test"},
        json={"model_id": MODEL_ID, "batch_size": batch_size},
    )
    assert response.status_code == 202
    job_id = response.json()["data"]["job_id"]
    with transaction_scope(factory) as session:
        source = dict(session.execute(select(DocumentSegment.__table__)).mappings().one())
        for index in range(1, 6):
            copied = dict(
                source, id=_id("seg_", 200 + index), segment_order=index, global_order=index
            )
            if index <= 3:
                copied.update(machine_translation="Hasil tersimpan.", status="MACHINE_TRANSLATED")
            elif index == 4:
                copied.update(status="LOCKED", is_locked=1)  # Locking source is not translation.
            session.add(DocumentSegment(**copied))
        job = session.get(ApplicationJob, job_id)
        assert job is not None
        job.status = job_status
        job.progress = 0.0 if job_status != "COMPLETED" else 1.0
        job.result_json = json.dumps({"current_batch": 2, "total_batches": 7})
    status = client.get(f"/api/v1/projects/{project_id}/translation/status").json()["data"]
    assert status["total_segments"] == 6
    assert status["completed_segments"] == 3
    assert status["progress"] == 0.5
    assert (status["current_batch"], status["total_batches"]) == (2, 7)


@pytest.mark.parametrize(
    "batch_data",
    [
        None,
        {},
        {"current_batch": True, "total_batches": 2},
        {"current_batch": 3, "total_batches": 2},
    ],
)
def test_status_does_not_invent_unknown_batch_counts(
    translation_api: tuple[TestClient, sessionmaker[Session], str, FastAPI],
    batch_data: dict[str, object] | None,
) -> None:
    client, factory, project_id, _application = translation_api
    response = client.post(
        f"/api/v1/projects/{project_id}/translation/start",
        headers={**CLIENT_HEADERS, "Idempotency-Key": "unknown-batches"},
        json={"model_id": MODEL_ID},
    )
    with transaction_scope(factory) as session:
        job = session.get(ApplicationJob, response.json()["data"]["job_id"])
        assert job is not None
        job.status = "FAILED"
        job.progress = 0.8
        job.result_json = json.dumps(batch_data)
    status = client.get(f"/api/v1/projects/{project_id}/translation/status").json()["data"]
    assert (status["current_batch"], status["total_batches"]) == (0, 0)


def test_status_newer_success_is_not_hidden_by_old_failure(
    translation_api: tuple[TestClient, sessionmaker[Session], str, FastAPI],
) -> None:
    client, factory, project_id, _application = translation_api
    response = client.post(
        f"/api/v1/projects/{project_id}/translation/start",
        headers={**CLIENT_HEADERS, "Idempotency-Key": "old-failure"},
        json={"model_id": MODEL_ID},
    )
    new_job_id = _id("job_", 999)
    with transaction_scope(factory) as session:
        job = session.get(ApplicationJob, response.json()["data"]["job_id"])
        assert job is not None
        job.status = "FAILED"
        job.created_at = "2026-09-01T00:00:00.000Z"
        session.flush()
        copied = dict(session.execute(select(ApplicationJob.__table__)).mappings().one())
        copied.update(
            id=new_job_id,
            idempotency_key="new-success",
            status="COMPLETED",
            created_at="2026-09-02T00:00:00.000Z",
            progress=1.0,
        )
        session.add(ApplicationJob(**copied))
    status = client.get(f"/api/v1/projects/{project_id}/translation/status").json()["data"]
    assert status["active_job_id"] == new_job_id
    assert status["status"] == "COMPLETED"


def test_production_queue_is_owned_by_application_lifespan(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    root = tmp_path / "production queue"
    monkeypatch.setenv("TRANSLOKA_DATA_DIR", str(root))
    command.upgrade(Config(str(ALEMBIC_CONFIGURATION)), "head")
    application = create_app()

    with TestClient(application):
        producer = application.state.translation_queue_owner
        assert application.state.translation_queue is producer.queue
        assert producer.huey.pending_count() == 0
        assert Path(producer.huey.storage.filename) == root / "database" / "tasks.db"

    assert producer.huey.storage.close() is False


def test_production_queue_is_isolated_per_application(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    producers: list[Any] = []
    database_paths: list[Path] = []
    for name in ("first", "second"):
        root = tmp_path / name
        monkeypatch.setenv("TRANSLOKA_DATA_DIR", str(root))
        command.upgrade(Config(str(ALEMBIC_CONFIGURATION)), "head")
        application = create_app()
        with TestClient(application):
            producer = application.state.translation_queue_owner
            producers.append(producer)
            database_paths.append(Path(producer.huey.storage.filename))
        assert producer.huey.storage.close() is False

    assert producers[0].huey is not producers[1].huey
    assert database_paths == [
        tmp_path / "first" / "database" / "tasks.db",
        tmp_path / "second" / "database" / "tasks.db",
    ]


def test_translation_readiness_ready(
    translation_api: tuple[TestClient, sessionmaker[Session], str, FastAPI],
) -> None:
    client, _factory, project_id, _application = translation_api

    response = _readiness(client, project_id)

    assert response.status_code == 200
    assert response.json()["data"] == {
        "ready": True,
        "blocking_issues": [],
        "warnings": [],
        "segment_count": 1,
        "estimated_batches": 1,
    }


@pytest.mark.parametrize(
    ("blocker", "expected_code"),
    [
        ("model", "OLLAMA_MODEL_NOT_SELECTED"),
        ("ollama", "OLLAMA_UNAVAILABLE"),
        ("worker", "WORKER_UNAVAILABLE"),
        ("source", "UNRESOLVED_SOURCE"),
        ("glossary", "GLOSSARY_CONFLICT"),
        ("segments", "NO_SEGMENTS"),
    ],
)
def test_translation_readiness_reports_each_blocker(
    blocker: str,
    expected_code: str,
    translation_api: tuple[TestClient, sessionmaker[Session], str, FastAPI],
) -> None:
    client, factory, project_id, application = translation_api
    if blocker == "model":
        with transaction_scope(factory) as session:
            model = session.get(LocalModelRecord, MODEL_ID)
            assert model is not None
            model.is_selected_translation = 0
    elif blocker == "ollama":
        application.state.ollama_provider = UnavailableProvider()
    elif blocker == "source":
        with transaction_scope(factory) as session:
            segment = session.get(DocumentSegment, SEGMENT_ID)
            assert segment is not None
            segment.status = SegmentStatus.CREATED.value
    elif blocker == "worker":
        application.state.worker_heartbeat_store = StaticWorkerHeartbeatStore(WorkerStatus.STOPPED)
    elif blocker == "glossary":
        with transaction_scope(factory) as session:
            session.add(
                GlossaryConflict(
                    id=_id("gcf_", 106),
                    project_id=project_id,
                    source_term="workflow",
                    conflict_type="TARGET_CONFLICT",
                    rules_json="[]",
                    status="UNRESOLVED",
                    resolution_type=None,
                    resolution_json=None,
                    created_at=CREATED_AT,
                    resolved_at=None,
                )
            )
    elif blocker == "segments":
        with transaction_scope(factory) as session:
            segment = session.get(DocumentSegment, SEGMENT_ID)
            assert segment is not None
            segment.status = SegmentStatus.IGNORED.value

    response = _readiness(client, project_id)

    assert response.status_code == 200
    assert expected_code in {issue["code"] for issue in response.json()["data"]["blocking_issues"]}


@pytest.mark.parametrize(
    "heartbeat_store",
    [
        StaticWorkerHeartbeatStore(None),
        StaticWorkerHeartbeatStore(WorkerStatus.STOPPED),
        StaticWorkerHeartbeatStore(recorded_at=0.0),
        StaticWorkerHeartbeatStore(recorded_at=time.time() + 60.0),
    ],
    ids=("missing", "stopped", "stale", "future"),
)
def test_translation_start_fails_closed_when_worker_is_unavailable(
    heartbeat_store: StaticWorkerHeartbeatStore,
    translation_api: tuple[TestClient, sessionmaker[Session], str, FastAPI],
) -> None:
    client, factory, project_id, application = translation_api
    application.state.worker_heartbeat_store = heartbeat_store

    response = client.post(
        f"/api/v1/projects/{project_id}/translation/start",
        headers={**CLIENT_HEADERS, "Idempotency-Key": "translation-worker-unavailable"},
        json={"model_id": MODEL_ID},
    )

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "WORKER_UNAVAILABLE"
    assert cast(RecordingQueue, application.state.translation_queue).enqueued == []
    with factory() as session:
        assert session.scalars(select(ApplicationJob)).all() == []


def test_translation_start_is_idempotent_and_readiness_blocks_start(
    translation_api: tuple[TestClient, sessionmaker[Session], str, FastAPI],
) -> None:
    client, factory, project_id, _application = translation_api
    start_path = f"/api/v1/projects/{project_id}/translation/start"
    headers = {**CLIENT_HEADERS, "Idempotency-Key": "translation-start-1"}
    body = {"model_id": MODEL_ID}

    first = client.post(start_path, headers=headers, json=body)
    repeated = client.post(start_path, headers=headers, json=body)

    assert first.status_code == 202
    assert repeated.status_code == 202
    assert repeated.json()["data"] == first.json()["data"]

    job_id = first.json()["data"]["job_id"]
    duplicate = client.post(
        start_path,
        headers={**CLIENT_HEADERS, "Idempotency-Key": "translation-start-duplicate"},
        json=body,
    )
    assert duplicate.status_code == 429
    assert duplicate.json()["error"]["code"] == "TRANSLATION_ALREADY_RUNNING"
    assert duplicate.json()["error"]["details"] == {"job_id": job_id}

    with factory() as session:
        row = session.get(ApplicationJob, job_id)
        assert row is not None
        command = TranslationCommand.from_payload_json(row.payload_json)
        assert command.project_id == project_id
        assert command.document_id == DOCUMENT_ID
        assert command.model_id == MODEL_ID
        snapshot = session.get(GlossarySnapshot, command.glossary_snapshot_id)
        assert snapshot is not None

    conflict = client.post(
        start_path,
        headers=headers,
        json={"model_id": MODEL_ID, "batch_size": 6},
    )
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "IDEMPOTENCY_CONFLICT"

    with transaction_scope(factory) as session:
        model = session.get(LocalModelRecord, MODEL_ID)
        assert model is not None
        model.is_selected_translation = 0
    blocked = client.post(
        start_path,
        headers={**CLIENT_HEADERS, "Idempotency-Key": "translation-start-blocked"},
        json=body,
    )
    assert blocked.status_code == 409
    assert blocked.json()["error"]["code"] == "TRANSLATION_NOT_READY"


def test_translation_start_fails_closed_when_queue_is_not_configured(
    translation_api: tuple[TestClient, sessionmaker[Session], str, FastAPI],
) -> None:
    client, factory, project_id, application = translation_api
    application.state.translation_queue = None

    response = client.post(
        f"/api/v1/projects/{project_id}/translation/start",
        headers={**CLIENT_HEADERS, "Idempotency-Key": "translation-no-queue"},
        json={"model_id": MODEL_ID},
    )

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "QUEUE_NOT_CONFIGURED"
    with factory() as session:
        assert session.scalars(select(ApplicationJob)).all() == []


@pytest.mark.parametrize("configured", [None, "", "   "])
def test_ctranslate2_is_disabled_without_explicit_provisioning(
    translation_api: tuple[TestClient, sessionmaker[Session], str, FastAPI],
    monkeypatch: pytest.MonkeyPatch,
    configured: str | None,
) -> None:
    client, _, project_id, application = translation_api
    if configured is None:
        monkeypatch.delenv("TRANSLOKA_CT2_MODEL_DIR", raising=False)
    else:
        monkeypatch.setenv("TRANSLOKA_CT2_MODEL_DIR", configured)
    application.state.ctranslate2_provider = UnexpectedProvider()
    application.state.ollama_provider = UnexpectedProvider()
    application.state.groq_provider = UnexpectedProvider()
    selection = {"provider_type": "CTRANSLATE2", "model_id": "opus-mt-en-id-ct2-int8"}

    readiness = client.get(
        f"/api/v1/projects/{project_id}/translation-readiness",
        headers=CLIENT_HEADERS,
        params=selection,
    )
    assert readiness.status_code == 200
    assert readiness.json()["data"]["ready"] is False
    assert [issue["code"] for issue in readiness.json()["data"]["blocking_issues"]] == [
        "CTRANSLATE2_DISABLED"
    ]

    response = client.post(
        f"/api/v1/projects/{project_id}/translation/start",
        headers={**CLIENT_HEADERS, "Idempotency-Key": "ct2-disabled"},
        json=selection,
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "TRANSLATION_NOT_READY"
    assert application.state.translation_queue.enqueued == []


def test_ctranslate2_is_opt_in_and_dispatches_without_ollama_or_cloud(
    translation_api: tuple[TestClient, sessionmaker[Session], str, FastAPI],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    client, factory, project_id, application = translation_api
    model_dir = tmp_path / "private-ct2-model"
    monkeypatch.setenv("TRANSLOKA_CT2_MODEL_DIR", str(model_dir))
    monkeypatch.delenv("TRANSLOKA_CLOUD_TRANSLATION_ENABLED", raising=False)
    application.state.ctranslate2_provider = HealthyProvider()
    application.state.ollama_provider = UnavailableProvider()
    application.state.groq_provider = UnexpectedProvider()
    with transaction_scope(factory) as session:
        model = session.get(LocalModelRecord, MODEL_ID)
        assert model is not None
        session.delete(model)

    default_readiness = _readiness(client, project_id).json()["data"]
    assert default_readiness["ready"] is False
    assert "OLLAMA_UNAVAILABLE" in {issue["code"] for issue in default_readiness["blocking_issues"]}
    application.state.ollama_provider = UnexpectedProvider()
    selection = {"provider_type": "CTRANSLATE2", "model_id": "opus-mt-en-id-ct2-int8"}
    readiness = client.get(
        f"/api/v1/projects/{project_id}/translation-readiness",
        headers=CLIENT_HEADERS,
        params=selection,
    )
    assert readiness.status_code == 200
    assert readiness.json()["data"]["ready"] is True

    response = client.post(
        f"/api/v1/projects/{project_id}/translation/start",
        headers={**CLIENT_HEADERS, "Idempotency-Key": "ct2-v2-snapshot"},
        json={**selection, "scope": "UNTRANSLATED_ONLY", "batch_size": 3},
    )
    assert response.status_code == 202, response.text
    job_id = response.json()["data"]["job_id"]
    assert application.state.translation_queue.enqueued == [job_id]
    with factory() as session:
        job = session.get(ApplicationJob, job_id)
        assert job is not None
        command = TranslationCommand.from_payload_json(job.payload_json)
        assert command.provider_type == "CTRANSLATE2"
        assert command.model_id == "opus-mt-en-id-ct2-int8"
        assert command.scope == "UNTRANSLATED_ONLY"
        assert command.batch_size == 3
        assert command.cloud_model_name is None
        assert command.cloud_consent is False
        assert command.cloud_consent_version is None
        assert command.ctranslate2_settings is not None
        assert command.ctranslate2_settings.to_payload()["fallback"] is None
        assert str(model_dir) not in job.payload_json
        assert list(session.scalars(select(LocalModelRecord))) == []


@pytest.mark.parametrize(
    ("blocker", "expected_code"),
    [
        ("model", "CTRANSLATE2_MODEL_NOT_ALLOWED"),
        ("language", "CTRANSLATE2_LANGUAGE_UNSUPPORTED"),
        ("cloud", "CTRANSLATE2_PROVIDER_FIELDS_INVALID"),
        ("health", "CTRANSLATE2_UNAVAILABLE"),
        ("provisioning", "CTRANSLATE2_UNAVAILABLE"),
    ],
)
def test_ctranslate2_readiness_fails_closed(
    translation_api: tuple[TestClient, sessionmaker[Session], str, FastAPI],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    blocker: str,
    expected_code: str,
) -> None:
    client, factory, project_id, application = translation_api
    monkeypatch.setenv("TRANSLOKA_CT2_MODEL_DIR", str(tmp_path / "missing-model"))
    application.state.ollama_provider = UnexpectedProvider()
    application.state.groq_provider = UnexpectedProvider()
    params = {"provider_type": "CTRANSLATE2", "model_id": "opus-mt-en-id-ct2-int8"}
    if blocker == "health":
        application.state.ctranslate2_provider = UnavailableProvider()
    elif blocker != "provisioning":
        application.state.ctranslate2_provider = UnexpectedProvider()
    if blocker == "model":
        params["model_id"] = MODEL_ID
    elif blocker == "language":
        with transaction_scope(factory) as session:
            project = session.get(Project, project_id)
            assert project is not None
            project.source_language = "id"
            project.target_language = "en"
    elif blocker == "cloud":
        params["cloud_consent"] = "true"

    response = client.get(
        f"/api/v1/projects/{project_id}/translation-readiness",
        headers=CLIENT_HEADERS,
        params=params,
    )
    assert response.status_code == 200
    assert response.json()["data"]["ready"] is False
    assert [issue["code"] for issue in response.json()["data"]["blocking_issues"]] == [
        expected_code
    ]


@pytest.mark.parametrize(
    "fields",
    [
        {},
        {"model_id": MODEL_ID},
        {"model_id": "opus-mt-en-id-ct2-int8", "cloud_consent": True},
        {"model_id": "opus-mt-en-id-ct2-int8", "cloud_model_name": "qwen/qwen3.8-27b"},
    ],
)
def test_ctranslate2_start_rejects_invalid_provider_fields(
    translation_api: tuple[TestClient, sessionmaker[Session], str, FastAPI],
    fields: dict[str, object],
) -> None:
    client, _, project_id, application = translation_api
    response = client.post(
        f"/api/v1/projects/{project_id}/translation/start",
        headers={**CLIENT_HEADERS, "Idempotency-Key": "ct2-invalid-fields"},
        json={"provider_type": "CTRANSLATE2", **fields},
    )
    assert response.status_code == 422
    assert application.state.translation_queue.enqueued == []


def test_ctranslate2_dispatch_snapshots_optional_local_fallback_without_contacting_it(
    translation_api: tuple[TestClient, sessionmaker[Session], str, FastAPI],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    client, factory, project_id, application = translation_api
    monkeypatch.setenv("TRANSLOKA_CT2_MODEL_DIR", str(tmp_path / "private-model"))
    monkeypatch.setenv("TRANSLOKA_CT2_OLLAMA_FALLBACK_MODEL", "qwen2.5:3b")
    monkeypatch.setenv("TRANSLOKA_OLLAMA_URL", "http://127.0.0.1:11435")
    application.state.ctranslate2_provider = HealthyProvider()
    application.state.ollama_provider = UnexpectedProvider()
    application.state.groq_provider = UnexpectedProvider()
    response = client.post(
        f"/api/v1/projects/{project_id}/translation/start",
        headers={**CLIENT_HEADERS, "Idempotency-Key": "ct2-fallback-snapshot"},
        json={"provider_type": "CTRANSLATE2", "model_id": "opus-mt-en-id-ct2-int8"},
    )
    assert response.status_code == 202, response.text
    with factory() as session:
        job = session.get(ApplicationJob, response.json()["data"]["job_id"])
        assert job is not None
        command = TranslationCommand.from_payload_json(job.payload_json)
        assert command.ctranslate2_settings is not None
        assert command.ctranslate2_settings.fallback_model_name == "qwen2.5:3b"
        assert command.ctranslate2_settings.fallback_base_url == "http://127.0.0.1:11435"
        assert "private-model" not in job.payload_json


def test_ctranslate2_readiness_blocks_remote_fallback_configuration(
    translation_api: tuple[TestClient, sessionmaker[Session], str, FastAPI],
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    client, _, project_id, application = translation_api
    monkeypatch.setenv("TRANSLOKA_CT2_MODEL_DIR", str(tmp_path / "private-model"))
    monkeypatch.setenv("TRANSLOKA_CT2_OLLAMA_FALLBACK_MODEL", "qwen2.5:3b")
    monkeypatch.setenv("TRANSLOKA_OLLAMA_URL", "https://untrusted.example")
    application.state.ctranslate2_provider = UnexpectedProvider()
    application.state.ollama_provider = UnexpectedProvider()
    response = client.post(
        f"/api/v1/projects/{project_id}/translation/start",
        headers={**CLIENT_HEADERS, "Idempotency-Key": "ct2-remote-fallback"},
        json={"provider_type": "CTRANSLATE2", "model_id": "opus-mt-en-id-ct2-int8"},
    )
    assert response.status_code == 409
    assert [issue["code"] for issue in response.json()["error"]["details"]["blocking_issues"]] == [
        "CTRANSLATE2_FALLBACK_INVALID"
    ]
    assert application.state.translation_queue.enqueued == []
    assert "untrusted.example" not in response.text


def test_cloud_translation_is_disabled_by_default(
    translation_api: tuple[TestClient, sessionmaker[Session], str, FastAPI],
) -> None:
    client, _, project_id, application = translation_api
    application.state.groq_provider = HealthyProvider()

    response = client.post(
        f"/api/v1/projects/{project_id}/translation/start",
        headers={**CLIENT_HEADERS, "Idempotency-Key": "cloud-disabled"},
        json={
            "provider_type": "GROQ",
            "cloud_model_name": "qwen/qwen3.8-27b",
            "cloud_consent": True,
        },
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "TRANSLATION_NOT_READY"
    assert response.json()["error"]["details"]["blocking_issues"] == [
        {
            "code": "CLOUD_TRANSLATION_DISABLED",
            "message": "Cloud translation is disabled in this TransLoka process.",
        }
    ]


def test_cloud_readiness_does_not_require_a_local_model(
    translation_api: tuple[TestClient, sessionmaker[Session], str, FastAPI],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, factory, project_id, application = translation_api
    monkeypatch.setenv("TRANSLOKA_CLOUD_TRANSLATION_ENABLED", "true")
    application.state.groq_provider = HealthyProvider()
    with transaction_scope(factory) as session:
        model = session.get(LocalModelRecord, MODEL_ID)
        assert model is not None
        model.is_selected_translation = 0

    response = client.get(
        f"/api/v1/projects/{project_id}/translation-readiness",
        headers=CLIENT_HEADERS,
        params={
            "provider_type": "GROQ",
            "cloud_model_name": "qwen/qwen3.8-27b",
            "cloud_consent": "true",
        },
    )

    assert response.status_code == 200
    assert response.json()["data"]["ready"] is True
    assert response.json()["data"]["blocking_issues"] == []


def test_cloud_translation_dispatches_durable_v2_snapshot_without_local_model(
    translation_api: tuple[TestClient, sessionmaker[Session], str, FastAPI],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, factory, project_id, application = translation_api
    monkeypatch.setenv("TRANSLOKA_CLOUD_TRANSLATION_ENABLED", "true")
    application.state.groq_provider = HealthyProvider()
    with factory() as session:
        initial_models = len(list(session.scalars(select(LocalModelRecord))))

    response = client.post(
        f"/api/v1/projects/{project_id}/translation/start",
        headers={**CLIENT_HEADERS, "Idempotency-Key": "cloud-v2-snapshot"},
        json={
            "provider_type": "GROQ",
            "cloud_model_name": "qwen/qwen3.8-27b",
            "cloud_consent": True,
            "batch_size": 3,
        },
    )

    assert response.status_code == 202, response.text
    with factory() as session:
        job = session.get(ApplicationJob, response.json()["data"]["job_id"])
        assert job is not None
        command = TranslationCommand.from_payload_json(job.payload_json)
        assert command.provider_type == "GROQ"
        assert command.model_id is None
        assert command.cloud_model_name == "qwen/qwen3.8-27b"
        assert command.cloud_consent is True
        assert command.cloud_consent_version == "cloud_text_sharing_v1"
        assert len(list(session.scalars(select(LocalModelRecord)))) == initial_models
        assert "GROQ_API_KEY" not in job.payload_json


@pytest.mark.parametrize(
    "payload",
    [
        {"provider_type": "GROQ", "cloud_model_name": "qwen/qwen3.8-27b"},
        {
            "provider_type": "GROQ",
            "model_id": MODEL_ID,
            "cloud_model_name": "qwen/qwen3.8-27b",
            "cloud_consent": True,
        },
        {"provider_type": "OLLAMA", "model_id": MODEL_ID, "cloud_consent": True},
    ],
)
def test_translation_rejects_conflicting_provider_fields(
    translation_api: tuple[TestClient, sessionmaker[Session], str, FastAPI],
    payload: dict[str, object],
) -> None:
    client, _, project_id, _ = translation_api

    response = client.post(
        f"/api/v1/projects/{project_id}/translation/start",
        headers={**CLIENT_HEADERS, "Idempotency-Key": "invalid-provider-fields"},
        json=payload,
    )

    assert response.status_code == 422


def test_translation_status_prefers_running_job_over_newer_queued_job(
    translation_api: tuple[TestClient, sessionmaker[Session], str, FastAPI],
) -> None:
    client, factory, project_id, _application = translation_api
    start = client.post(
        f"/api/v1/projects/{project_id}/translation/start",
        headers={**CLIENT_HEADERS, "Idempotency-Key": "translation-running-status"},
        json={"model_id": MODEL_ID},
    )
    running_job_id = start.json()["data"]["job_id"]
    with transaction_scope(factory) as session:
        running = session.get(ApplicationJob, running_job_id)
        assert running is not None
        running.status = JobStatus.RUNNING.value
        running.progress = 0.5
        session.add(
            ApplicationJob(
                id=_id("job_", 112),
                project_id=project_id,
                document_id=DOCUMENT_ID,
                parent_job_id=None,
                job_type=JobType.TRANSLATE_DOCUMENT.value,
                queue_name="translation",
                status=JobStatus.QUEUED.value,
                progress=0.0,
                current_stage=None,
                idempotency_key="translation-newer-queued-status",
                payload_json=running.payload_json,
                result_json=None,
                retry_count=0,
                max_retries=3,
                error_code=None,
                error_message=None,
                created_at="2026-08-19T00:00:00.000Z",
                queued_at="2026-08-19T00:00:00.000Z",
                started_at=None,
                completed_at=None,
                cancelled_at=None,
                heartbeat_at=None,
            )
        )

    response = client.get(f"/api/v1/projects/{project_id}/translation/status")

    assert response.status_code == 200
    assert response.json()["data"]["active_job_id"] == running_job_id
    assert response.json()["data"]["status"] == "TRANSLATING"
    assert response.json()["data"]["progress"] == 0.0  # No saved translation yet.


def test_translation_cancel_and_retry_failed(
    translation_api: tuple[TestClient, sessionmaker[Session], str, FastAPI],
) -> None:
    client, factory, project_id, application = translation_api
    start = client.post(
        f"/api/v1/projects/{project_id}/translation/start",
        headers={**CLIENT_HEADERS, "Idempotency-Key": "translation-lifecycle"},
        json={"model_id": MODEL_ID, "batch_size": 8},
    )
    assert start.status_code == 202

    cancelled = client.post(
        f"/api/v1/projects/{project_id}/translation/cancel",
        headers=CLIENT_HEADERS,
        json={"reason": "User requested cancellation."},
    )
    assert cancelled.status_code == 200
    assert cancelled.json()["data"]["status"] == "CANCELLED"

    retried = client.post(
        f"/api/v1/projects/{project_id}/translation/retry-failed",
        headers={**CLIENT_HEADERS, "Idempotency-Key": "translation-retry-1"},
        json={"use_smaller_batch": True, "use_selected_model": True},
    )
    assert retried.status_code == 202
    assert retried.json()["data"]["status"] == "TRANSLATING"

    repeated = client.post(
        f"/api/v1/projects/{project_id}/translation/retry-failed",
        headers={**CLIENT_HEADERS, "Idempotency-Key": "translation-retry-1"},
        json={"use_smaller_batch": True, "use_selected_model": True},
    )
    assert repeated.status_code == 202
    queue = cast(RecordingQueue, application.state.translation_queue)
    assert queue.enqueued == [start.json()["data"]["job_id"], start.json()["data"]["job_id"]]
    with factory() as session:
        job = session.get(ApplicationJob, start.json()["data"]["job_id"])
        assert job is not None
        assert TranslationCommand.from_payload_json(job.payload_json).batch_size == 4

    status_response = client.get(f"/api/v1/projects/{project_id}/translation/status")
    assert status_response.status_code == 200
    assert status_response.json()["data"]["active_job_id"] == start.json()["data"]["job_id"]


def test_translation_retry_fails_closed_when_worker_is_unavailable(
    translation_api: tuple[TestClient, sessionmaker[Session], str, FastAPI],
) -> None:
    client, factory, project_id, application = translation_api
    start = client.post(
        f"/api/v1/projects/{project_id}/translation/start",
        headers={**CLIENT_HEADERS, "Idempotency-Key": "translation-worker-retry"},
        json={"model_id": MODEL_ID},
    )
    assert start.status_code == 202
    job_id = start.json()["data"]["job_id"]
    application.state.worker_heartbeat_store = StaticWorkerHeartbeatStore(WorkerStatus.STOPPED)
    cancelled = client.post(
        f"/api/v1/projects/{project_id}/translation/cancel",
        headers=CLIENT_HEADERS,
        json={"reason": "Prepare worker-unavailable retry."},
    )
    assert cancelled.status_code == 200

    response = client.post(
        f"/api/v1/projects/{project_id}/translation/retry-failed",
        headers={**CLIENT_HEADERS, "Idempotency-Key": "translation-worker-retry-1"},
        json={"use_smaller_batch": True, "use_selected_model": True},
    )

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "WORKER_UNAVAILABLE"
    assert cast(RecordingQueue, application.state.translation_queue).enqueued == [job_id]
    with factory() as session:
        job = session.get(ApplicationJob, job_id)
        assert job is not None
        assert job.status == JobStatus.CANCELLED.value
        assert job.retry_count == 0


def test_translation_retry_prefers_stale_job_over_newer_cancelled_job(
    translation_api: tuple[TestClient, sessionmaker[Session], str, FastAPI],
) -> None:
    client, factory, project_id, application = translation_api
    start = client.post(
        f"/api/v1/projects/{project_id}/translation/start",
        headers={**CLIENT_HEADERS, "Idempotency-Key": "translation-stale-retry"},
        json={"model_id": MODEL_ID, "batch_size": 8},
    )
    stale_job_id = start.json()["data"]["job_id"]
    with transaction_scope(factory) as session:
        stale_job = session.get(ApplicationJob, stale_job_id)
        assert stale_job is not None
        stale_job.status = JobStatus.STALE.value
        stale_job.current_stage = JobStatus.STALE.value
        stale_job.completed_at = "2026-08-19T00:00:00.000Z"
        session.add(
            ApplicationJob(
                id=_id("job_", 113),
                project_id=project_id,
                document_id=DOCUMENT_ID,
                parent_job_id=None,
                job_type=JobType.TRANSLATE_DOCUMENT.value,
                queue_name="translation",
                status=JobStatus.CANCELLED.value,
                progress=0.0,
                current_stage=JobStatus.CANCELLED.value,
                idempotency_key="translation-newer-cancelled-status",
                payload_json=stale_job.payload_json,
                result_json=None,
                retry_count=0,
                max_retries=3,
                error_code=None,
                error_message=None,
                created_at="2026-08-19T00:00:00.000Z",
                queued_at=None,
                started_at=None,
                completed_at="2026-08-19T00:00:00.000Z",
                cancelled_at="2026-08-19T00:00:00.000Z",
                heartbeat_at=None,
            )
        )

    retried = client.post(
        f"/api/v1/projects/{project_id}/translation/retry-failed",
        headers={**CLIENT_HEADERS, "Idempotency-Key": "translation-stale-retry-1"},
        json={"use_smaller_batch": True, "use_selected_model": True},
    )

    assert retried.status_code == 202
    assert retried.json()["data"]["active_job_id"] == stale_job_id
    queue = cast(RecordingQueue, application.state.translation_queue)
    assert queue.enqueued == [stale_job_id, stale_job_id]
    with factory() as session:
        stale_job = session.get(ApplicationJob, stale_job_id)
        cancelled_job = session.get(ApplicationJob, _id("job_", 113))
        assert stale_job is not None
        assert stale_job.status == JobStatus.RETRYING.value
        assert cancelled_job is not None
        assert cancelled_job.status == JobStatus.CANCELLED.value


def test_translation_retry_queue_failure_persists_terminal_state(
    translation_api: tuple[TestClient, sessionmaker[Session], str, FastAPI],
) -> None:
    client, factory, project_id, application = translation_api
    start = client.post(
        f"/api/v1/projects/{project_id}/translation/start",
        headers={**CLIENT_HEADERS, "Idempotency-Key": "translation-retry-queue-failure"},
        json={"model_id": MODEL_ID},
    )
    job_id = start.json()["data"]["job_id"]
    client.post(
        f"/api/v1/projects/{project_id}/translation/cancel",
        headers=CLIENT_HEADERS,
        json={"reason": "Prepare a retryable job."},
    )
    application.state.translation_queue = UnavailableQueue()

    response = client.post(
        f"/api/v1/projects/{project_id}/translation/retry-failed",
        headers={**CLIENT_HEADERS, "Idempotency-Key": "translation-retry-queue-failure-1"},
        json={"use_smaller_batch": True, "use_selected_model": True},
    )

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "QUEUE_UNAVAILABLE"
    with factory() as session:
        job = session.get(ApplicationJob, job_id)
        assert job is not None
        assert job.status == JobStatus.FAILED.value
        attempt = session.scalar(
            select(JobAttempt)
            .where(JobAttempt.job_id == job_id)
            .order_by(JobAttempt.attempt_number.desc())
            .limit(1)
        )
        assert attempt is not None
        assert attempt.status == JobAttemptStatus.FAILED.value
