import json
import os
from pathlib import Path
from typing import cast
from uuid import UUID

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker
from transloka_api.app import create_app
from transloka_api.middleware import (
    CLIENT_HEADER,
    CLIENT_HEADER_VALUE,
    CLIENT_VERSION_HEADER,
    CLIENT_VERSION_VALUE,
)
from transloka_core.database import (
    create_session_factory,
    create_sqlite_engine,
    transaction_scope,
)
from transloka_core.database.models.document_ir import (
    BlockType,
    DocumentBlock,
    DocumentSegment,
    ReviewStatus,
    SegmentStatus,
    SemanticRole,
)
from transloka_core.database.models.documents import Document, DocumentClass, DocumentStatus
from transloka_core.database.models.files import FileRole, FileStatus, StoredFile
from transloka_core.database.models.jobs import ApplicationJob, JobStatus
from transloka_core.database.models.models import LocalModelRecord, ModelLicenseStatus
from transloka_core.database.models.pages import DocumentPage, PageType
from transloka_core.database.models.projects import Project
from transloka_core.database.models.translation import (
    SegmentTranslation,
    TranslationBatch,
)
from transloka_core.storage.local import LocalFileStorage
from transloka_worker.queue import create_huey, resolve_queue_configuration
from transloka_worker.tasks.translation import (
    TRANSLATION_TASK_NAME,
    register_translation_task,
)
from transloka_worker.translation import (
    DatabaseTranslationOperationLoader,
    ProductionTranslationJobRunner,
)

REPOSITORY_ROOT = Path(__file__).parents[3]
ALEMBIC_CONFIGURATION = REPOSITORY_ROOT / "alembic.ini"
CLIENT_HEADERS = {
    CLIENT_HEADER: CLIENT_HEADER_VALUE,
    CLIENT_VERSION_HEADER: CLIENT_VERSION_VALUE,
}
PROJECT = {
    "name": "Production Runtime Project",
    "description": None,
    "source_language": "en",
    "target_language": "id",
    "document_type": "TECHNICAL_BOOK",
    "translation_style": "PROFESSIONAL",
    "reconstruction_mode": "HYBRID",
}
CREATED_AT = "2026-08-27T00:00:00.000Z"


def _id(prefix: str, value: int) -> str:
    return f"{prefix}{UUID(int=value)}"


ORIGINAL_FILE_ID = _id("fil_", 1)
DOCUMENT_ID = _id("doc_", 2)
PAGE_ID = _id("pag_", 3)
BLOCK_ID = _id("blk_", 4)
SEGMENT_ID = _id("seg_", 5)
MODEL_ID = _id("mdl_", 6)


class HealthyProvider:
    async def health_check(self) -> object:
        from transloka_translation.providers import ProviderHealth, ProviderHealthStatus

        return ProviderHealth(status=ProviderHealthStatus.AVAILABLE, version="test")


class DeterministicProvider:
    async def translate(self, request: object, *, cancellation: object = None) -> str:
        del cancellation
        source_data = request.source_data["source_data"]  # type: ignore[attr-defined]
        return json.dumps(
            {
                "segments": [
                    {
                        "segment_id": item["segment_id"],
                        "translated_text": "Alur kerja dimulai.",
                    }
                    for item in source_data["segments"]
                ]
            }
        )


def test_production_translation_runtime_crosses_api_queue_worker_boundary(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    initial_artifacts = _database_artifacts()
    data_root = tmp_path / "production translation runtime"
    monkeypatch.setenv("TRANSLOKA_DATA_DIR", str(data_root))
    command.upgrade(Config(str(ALEMBIC_CONFIGURATION)), "head")

    application = create_app()
    with TestClient(application) as client:
        application.state.ollama_provider = HealthyProvider()
        project_response = client.post(
            "/api/v1/projects",
            headers=CLIENT_HEADERS,
            json=PROJECT,
        )
        assert project_response.status_code == 201
        project_id = cast(str, project_response.json()["data"]["id"])
        factory = cast(sessionmaker[Session], application.state.session_factory)
        _seed_translation_inputs(factory, project_id)

        start = client.post(
            f"/api/v1/projects/{project_id}/translation/start",
            headers={**CLIENT_HEADERS, "Idempotency-Key": "production-runtime-e2e"},
            json={"model_id": MODEL_ID},
        )
        assert start.status_code == 202, start.text
        job_id = cast(str, start.json()["data"]["job_id"])
        assert application.state.translation_queue_owner.huey.pending_count() == 1

    configuration = resolve_queue_configuration(data_root)
    huey = create_huey(configuration)
    engine = create_sqlite_engine(configuration.directories)
    factory = create_session_factory(engine)
    runner = ProductionTranslationJobRunner(
        DatabaseTranslationOperationLoader(
            factory,
            LocalFileStorage(configuration.directories),
        ),
        factory,
        configuration.directories.temporary,
        provider_factory=lambda _model_name: DeterministicProvider(),
        worker_identifier="translation-runtime-e2e",
    )
    try:
        register_translation_task(huey, runner.run)
        task = huey.dequeue()
        assert task is not None
        assert task.name == TRANSLATION_TASK_NAME
        assert task.data == ((job_id,), {})
        huey.execute(task)
        assert huey.pending_count() == 0
    finally:
        huey.storage.close()
        engine.dispose()

    status_application = create_app()
    with TestClient(status_application) as client:
        status_response = client.get(
            f"/api/v1/projects/{project_id}/translation/status",
            headers=CLIENT_HEADERS,
        )
        assert status_response.status_code == 200
        status_body = status_response.json()
        assert status_body["data"]["status"] == "COMPLETED"
        assert status_body["data"]["completed_segments"] == 1
        assert status_body["data"]["progress"] == 1.0

        factory = cast(sessionmaker[Session], status_application.state.session_factory)
        with factory() as session:
            job = session.get(ApplicationJob, job_id)
            segment = session.get(DocumentSegment, SEGMENT_ID)
            assert job is not None and job.status == JobStatus.COMPLETED.value
            assert segment is not None
            assert segment.machine_translation == "Alur kerja dimulai."
            assert session.scalar(select(func.count()).select_from(TranslationBatch)) == 1
            assert session.scalar(select(func.count()).select_from(SegmentTranslation)) == 1

    assert _database_artifacts() == initial_artifacts


def _seed_translation_inputs(
    factory: sessionmaker[Session],
    project_id: str,
) -> None:
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
                title="Runtime document",
                author=None,
                document_type="TECHNICAL_BOOK",
                document_class=DocumentClass.DIGITAL_PDF.value,
                source_language="en",
                target_language="id",
                page_count=1,
                word_count_estimate=3,
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
        session.add_all(
            [
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
                ),
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
                ),
            ]
        )
        project = session.get(Project, project_id)
        assert project is not None
        project.active_document_id = DOCUMENT_ID


def _database_artifacts() -> frozenset[Path]:
    artifacts: set[Path] = set()
    ignored = {".git", ".next", ".venv", "node_modules", "test-results"}
    for current, directories, filenames in os.walk(REPOSITORY_ROOT):
        directories[:] = [name for name in directories if name not in ignored]
        artifacts.update(
            Path(current) / filename
            for filename in filenames
            if Path(filename).suffix.casefold() in {".db", ".sqlite", ".sqlite3"}
        )
    return frozenset(artifacts)
