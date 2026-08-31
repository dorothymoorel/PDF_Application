import json
from collections.abc import Iterator
from io import BytesIO
from pathlib import Path
from typing import cast
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
from transloka_core.database.models.documents import Document, DocumentClass, DocumentStatus
from transloka_core.database.models.exports import Export, ExportProfile, ExportStatus, ExportType
from transloka_core.database.models.files import FileRole, FileStatus, StoredFile
from transloka_core.database.models.jobs import ApplicationJob, JobStatus, JobType
from transloka_core.database.models.pages import DocumentPage, PageType
from transloka_core.database.models.projects import Project
from transloka_core.database.models.reconstruction import (
    ReconstructionJob,
    ReconstructionPage,
    ReconstructionStatus,
    ReconstructionStrategy,
)
from transloka_core.database.models.warnings import Warning, WarningSeverity, WarningStatus
from transloka_core.storage.local import LocalFileStorage

REPOSITORY_ROOT = Path(__file__).parents[3]
ALEMBIC_CONFIGURATION = REPOSITORY_ROOT / "alembic.ini"
CREATED_AT = "2026-08-22T00:00:00.000Z"
CLIENT_HEADERS = {
    CLIENT_HEADER: CLIENT_HEADER_VALUE,
    CLIENT_VERSION_HEADER: CLIENT_VERSION_VALUE,
}
PROJECT = {
    "name": "Reconstruction API Project",
    "description": None,
    "source_language": "en",
    "target_language": "id",
    "document_type": "TECHNICAL_BOOK",
    "translation_style": "PROFESSIONAL",
    "reconstruction_mode": "HYBRID",
}


def _id(prefix: str, value: int) -> str:
    return f"{prefix}{UUID(int=value)}"


ORIGINAL_FILE_ID = _id("fil_", 500)
DOCUMENT_ID = _id("doc_", 501)
PAGE_ID = _id("pag_", 502)


class RecordingQueue:
    name = "reconstruction"

    def enqueue(self, _job_id: str) -> None:
        pass


class ReconstructionStateQueue:
    name = "reconstruction"

    def __init__(self, factory: sessionmaker[Session]) -> None:
        self.factory = factory
        self.job_ids: list[str] = []
        self.reconstruction_exists_before_enqueue = False

    def enqueue(self, job_id: str) -> None:
        with self.factory() as session:
            self.reconstruction_exists_before_enqueue = (
                session.scalar(
                    select(ReconstructionJob).where(ReconstructionJob.application_job_id == job_id)
                )
                is not None
            )
        self.job_ids.append(job_id)


@pytest.fixture
def reconstruction_api(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> Iterator[tuple[TestClient, sessionmaker[Session], str, FastAPI]]:
    monkeypatch.setenv("TRANSLOKA_DATA_DIR", str(tmp_path / "reconstruction api"))
    command.upgrade(Config(str(ALEMBIC_CONFIGURATION)), "head")
    application = create_app()
    application.state.reconstruction_queue = RecordingQueue()
    with TestClient(application) as client:
        created = client.post("/api/v1/projects", headers=CLIENT_HEADERS, json=PROJECT)
        assert created.status_code == 201
        project_id = cast(str, created.json()["data"]["id"])
        factory = cast(sessionmaker[Session], application.state.session_factory)
        _seed_document(factory, project_id)
        yield client, factory, project_id, application


def _seed_document(factory: sessionmaker[Session], project_id: str) -> None:
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
                checksum_sha256="b" * 64,
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
                title="Reconstruction document",
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
                status=DocumentStatus.TRANSLATED.value,
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
                status=DocumentStatus.TRANSLATED.value,
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
        project = session.get(Project, project_id)
        assert project is not None
        project.active_document_id = DOCUMENT_ID


def test_completed_export_can_be_listed_and_checksum_verified_before_download(
    reconstruction_api: tuple[TestClient, sessionmaker[Session], str, FastAPI],
) -> None:
    client, factory, project_id, application = reconstruction_api
    export_id = _id("exp_", 510)
    export_file_id = _id("fil_", 511)
    filename = "translated-standard.pdf"
    storage_key = f"projects/{project_id}/exports/{filename}"
    storage = LocalFileStorage(application.state.settings.data_directories)
    temporary = storage.write_temporary(BytesIO(b"%PDF-1.7\nTransLoka export\n%%EOF"))
    artifact = storage.commit(temporary, storage_key, immutable=True)

    with transaction_scope(factory) as session:
        session.add(
            StoredFile(
                id=export_file_id,
                project_id=project_id,
                document_id=DOCUMENT_ID,
                file_role=FileRole.EXPORT.value,
                storage_key=artifact.storage_key,
                original_filename=None,
                safe_filename=filename,
                mime_type="application/pdf",
                size_bytes=artifact.size_bytes,
                checksum_sha256=artifact.checksum_sha256,
                is_immutable=1,
                status=FileStatus.VALIDATED.value,
                metadata_json=None,
                created_at=CREATED_AT,
                deleted_at=None,
            )
        )
        session.flush()
        session.add(
            Export(
                id=export_id,
                project_id=project_id,
                document_id=DOCUMENT_ID,
                reconstruction_job_id=None,
                file_id=export_file_id,
                export_type=ExportType.TRANSLATED_PDF.value,
                output_profile=ExportProfile.STANDARD.value,
                version_number=1,
                status=ExportStatus.COMPLETED.value,
                page_count=1,
                size_bytes=artifact.size_bytes,
                checksum_sha256=artifact.checksum_sha256,
                validation_report_id=None,
                settings_json="{}",
                created_at=CREATED_AT,
                completed_at=CREATED_AT,
                error_code=None,
            )
        )

    listed = client.get(f"/api/v1/projects/{project_id}/exports", headers=CLIENT_HEADERS)
    assert listed.status_code == 200, listed.text
    assert listed.json()["data"] == [
        {
            "id": export_id,
            "project_id": project_id,
            "document_id": DOCUMENT_ID,
            "reconstruction_job_id": None,
            "export_type": "TRANSLATED_PDF",
            "output_profile": "STANDARD",
            "version_number": 1,
            "status": "COMPLETED",
            "filename": filename,
            "page_count": 1,
            "size_bytes": artifact.size_bytes,
            "checksum_sha256": artifact.checksum_sha256,
            "created_at": CREATED_AT,
            "completed_at": CREATED_AT,
        }
    ]

    downloaded = client.get(f"/api/v1/exports/{export_id}/download", headers=CLIENT_HEADERS)
    assert downloaded.status_code == 200, downloaded.text
    assert downloaded.headers["content-type"] == "application/pdf"
    assert downloaded.content == b"%PDF-1.7\nTransLoka export\n%%EOF"


def test_reconstruction_readiness_and_preview(
    reconstruction_api: tuple[TestClient, sessionmaker[Session], str, FastAPI],
) -> None:
    client, _factory, project_id, _application = reconstruction_api

    readiness = client.get(f"/api/v1/projects/{project_id}/reconstruction-readiness")
    assert readiness.status_code == 200
    assert readiness.json()["data"]["ready"] is True
    assert readiness.json()["data"]["available_modes"] == ["OVERLAY", "REFLOW", "HYBRID"]

    preview = client.post(
        f"/api/v1/projects/{project_id}/reconstruction/preview",
        headers=CLIENT_HEADERS,
        json={"page_id": PAGE_ID, "mode": "HYBRID", "settings": {}},
    )
    assert preview.status_code == 200
    assert preview.json()["data"]["temporary"] is True
    assert preview.json()["data"]["status"] == "READY"


def test_reconstruction_start_and_duplicate_are_idempotent(
    reconstruction_api: tuple[TestClient, sessionmaker[Session], str, FastAPI],
) -> None:
    client, _factory, project_id, _application = reconstruction_api
    path = f"/api/v1/projects/{project_id}/reconstruction/start"
    first = client.post(
        path,
        headers={**CLIENT_HEADERS, "Idempotency-Key": "reconstruction-1"},
        json={"mode": "HYBRID"},
    )
    assert first.status_code == 202
    duplicate = client.post(
        path,
        headers={**CLIENT_HEADERS, "Idempotency-Key": "reconstruction-2"},
        json={"mode": "HYBRID"},
    )
    assert duplicate.status_code == 409
    assert duplicate.json()["error"]["code"] == "RECONSTRUCTION_ALREADY_RUNNING"
    repeated = client.post(
        path,
        headers={**CLIENT_HEADERS, "Idempotency-Key": "reconstruction-1"},
        json={"mode": "HYBRID"},
    )
    assert repeated.status_code == 202
    assert repeated.json()["data"] == first.json()["data"]


def test_reconstruction_start_persists_versioned_command_before_enqueue(
    reconstruction_api: tuple[TestClient, sessionmaker[Session], str, FastAPI],
) -> None:
    client, factory, project_id, application = reconstruction_api
    queue = ReconstructionStateQueue(factory)
    application.state.reconstruction_queue = queue

    response = client.post(
        f"/api/v1/projects/{project_id}/reconstruction/start",
        headers={**CLIENT_HEADERS, "Idempotency-Key": "reconstruction-command-v1"},
        json={"mode": "OVERLAY", "page_ids": [PAGE_ID]},
    )

    assert response.status_code == 202, response.text
    job_id = response.json()["data"]["job_id"]
    assert queue.job_ids == [job_id]
    assert queue.reconstruction_exists_before_enqueue is True
    with factory() as session:
        job = session.get(ApplicationJob, job_id)
        reconstruction = session.scalar(
            select(ReconstructionJob).where(ReconstructionJob.application_job_id == job_id)
        )
        assert job is not None
        assert reconstruction is not None
        command_payload = json.loads(job.payload_json)
        assert command_payload["schema"] == "transloka.reconstruction.command.v1"
        assert command_payload["page_ids"] == [PAGE_ID]
        assert command_payload["settings"]["mode"] == "OVERLAY"
        assert reconstruction.settings_version == "m11-rem-11"


def test_reconstruction_start_fails_closed_when_queue_is_not_configured(
    reconstruction_api: tuple[TestClient, sessionmaker[Session], str, FastAPI],
) -> None:
    client, factory, project_id, application = reconstruction_api
    application.state.reconstruction_queue = None

    response = client.post(
        f"/api/v1/projects/{project_id}/reconstruction/start",
        headers={**CLIENT_HEADERS, "Idempotency-Key": "reconstruction-no-queue"},
        json={"mode": "HYBRID"},
    )

    assert response.status_code == 503
    assert response.json()["error"]["code"] == "QUEUE_NOT_CONFIGURED"
    with factory() as session:
        assert session.scalars(select(ApplicationJob)).all() == []


def test_reconstruction_cancel(
    reconstruction_api: tuple[TestClient, sessionmaker[Session], str, FastAPI],
) -> None:
    client, _factory, project_id, _application = reconstruction_api
    start = client.post(
        f"/api/v1/projects/{project_id}/reconstruction/start",
        headers={**CLIENT_HEADERS, "Idempotency-Key": "reconstruction-cancel"},
        json={"mode": "HYBRID"},
    )
    assert start.status_code == 202
    cancelled = client.post(
        f"/api/v1/projects/{project_id}/reconstruction/cancel", headers=CLIENT_HEADERS
    )
    assert cancelled.status_code == 200
    assert cancelled.json()["data"]["status"] == ReconstructionStatus.CANCELLED.value
    current = client.get(f"/api/v1/projects/{project_id}/reconstruction/status")
    assert current.status_code == 200
    assert current.json()["data"]["active_job_id"] == start.json()["data"]["job_id"]


def test_reconstruction_retry_page(
    reconstruction_api: tuple[TestClient, sessionmaker[Session], str, FastAPI],
) -> None:
    client, factory, project_id, _application = reconstruction_api
    with transaction_scope(factory) as session:
        job_id = _id("job_", 510)
        reconstruction_id = _id("rcj_", 511)
        page_id = _id("rcp_", 512)
        session.add(
            ApplicationJob(
                id=job_id,
                project_id=project_id,
                document_id=DOCUMENT_ID,
                parent_job_id=None,
                job_type=JobType.RECONSTRUCT_DOCUMENT.value,
                queue_name="reconstruction",
                status=JobStatus.FAILED.value,
                progress=0.2,
                current_stage=None,
                idempotency_key="reconstruction-failed",
                payload_json='{"document_id":null,"page_ids":[],"project_id":null}',
                result_json=None,
                retry_count=0,
                max_retries=3,
                error_code="FAILED",
                error_message="failed",
                created_at=CREATED_AT,
                queued_at=CREATED_AT,
                started_at=CREATED_AT,
                completed_at=CREATED_AT,
                cancelled_at=None,
                heartbeat_at=None,
            )
        )
        session.flush()
        session.add(
            ReconstructionJob(
                id=reconstruction_id,
                project_id=project_id,
                document_id=DOCUMENT_ID,
                application_job_id=job_id,
                mode="HYBRID",
                settings_version="test",
                settings_json="{}",
                status=ReconstructionStatus.FAILED.value,
                progress=0.2,
                reconstruction_hash="retry-hash",
                created_at=CREATED_AT,
                started_at=CREATED_AT,
                completed_at=CREATED_AT,
                error_code="FAILED",
            )
        )
        session.add(
            ReconstructionPage(
                id=page_id,
                reconstruction_job_id=reconstruction_id,
                source_page_id=PAGE_ID,
                target_page_start=1,
                target_page_end=1,
                strategy=ReconstructionStrategy.RECONSTRUCT.value,
                status=ReconstructionStatus.FAILED.value,
                output_file_id=None,
                page_hash="page-hash",
                warning_count=0,
                metadata_json=None,
                created_at=CREATED_AT,
                updated_at=CREATED_AT,
            )
        )
    page = client.get(f"/api/v1/reconstruction/pages/{page_id}")
    assert page.status_code == 200
    assert page.json()["data"]["source_page_id"] == PAGE_ID
    retried = client.post(
        f"/api/v1/reconstruction/pages/{page_id}/retry",
        headers={**CLIENT_HEADERS, "Idempotency-Key": "page-retry-1"},
        json={"fallback_mode": "REFLOW", "override_settings": {"allow_column_change": True}},
    )
    assert retried.status_code == 202
    assert retried.json()["data"]["status"] == JobStatus.RETRYING.value


def test_reconstruction_blocking_warning(
    reconstruction_api: tuple[TestClient, sessionmaker[Session], str, FastAPI],
) -> None:
    client, factory, project_id, _application = reconstruction_api
    with transaction_scope(factory) as session:
        session.add(
            Warning(
                id=_id("wrn_", 520),
                project_id=project_id,
                document_id=DOCUMENT_ID,
                page_id=PAGE_ID,
                block_id=None,
                segment_id=None,
                job_id=None,
                warning_type="CRITICAL_LAYOUT_COLLISION",
                severity=WarningSeverity.CRITICAL.value,
                message="Critical layout collision.",
                details_json=None,
                status=WarningStatus.OPEN.value,
                resolution_type=None,
                resolution_note=None,
                created_at=CREATED_AT,
                resolved_at=None,
            )
        )
    response = client.post(
        f"/api/v1/projects/{project_id}/reconstruction/start",
        headers={**CLIENT_HEADERS, "Idempotency-Key": "reconstruction-blocked"},
        json={"mode": "HYBRID"},
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "RECONSTRUCTION_BLOCKED"
