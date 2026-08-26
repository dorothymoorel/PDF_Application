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
from transloka_core.database.models.glossary import GlossaryConflict
from transloka_core.database.models.jobs import ApplicationJob
from transloka_core.database.models.models import LocalModelRecord, ModelLicenseStatus
from transloka_core.database.models.pages import DocumentPage, PageType
from transloka_core.database.models.projects import Project
from transloka_translation.providers import ProviderHealth, ProviderHealthStatus

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


class RecordingQueue:
    name = "translation"

    def enqueue(self, _job_id: str) -> None:
        pass


@pytest.fixture
def translation_api(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> Iterator[tuple[TestClient, sessionmaker[Session], str, FastAPI]]:
    root = tmp_path / "translation api"
    monkeypatch.setenv("TRANSLOKA_DATA_DIR", str(root))
    command.upgrade(Config(str(ALEMBIC_CONFIGURATION)), "head")
    application = create_app()
    application.state.ollama_provider = HealthyProvider()
    application.state.translation_queue = RecordingQueue()
    with TestClient(application) as client:
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


def test_translation_cancel_and_retry_failed(
    translation_api: tuple[TestClient, sessionmaker[Session], str, FastAPI],
) -> None:
    client, _factory, project_id, _application = translation_api
    start = client.post(
        f"/api/v1/projects/{project_id}/translation/start",
        headers={**CLIENT_HEADERS, "Idempotency-Key": "translation-lifecycle"},
        json={"model_id": MODEL_ID},
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

    status_response = client.get(f"/api/v1/projects/{project_id}/translation/status")
    assert status_response.status_code == 200
    assert status_response.json()["data"]["active_job_id"] == start.json()["data"]["job_id"]
