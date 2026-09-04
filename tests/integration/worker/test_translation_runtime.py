import json
import stat
import time
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import cast
from uuid import UUID

import pytest
from alembic import command as alembic_command
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
    DocumentSection,
    DocumentSegment,
    ReviewStatus,
    SectionType,
    SegmentStatus,
    SemanticRole,
)
from transloka_core.database.models.documents import Document, DocumentClass, DocumentStatus
from transloka_core.database.models.files import FileRole, FileStatus, StoredFile
from transloka_core.database.models.glossary import GlossarySnapshot
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
from transloka_core.storage.local import LocalFileStorage
from transloka_translation.batching import BatchLimits
from transloka_translation.orchestration import TranslationRunStatus
from transloka_translation.providers import (
    ProviderErrorCode,
    ProviderHealth,
    ProviderHealthStatus,
    TranslationProviderError,
)
from transloka_worker.health import PersistedWorkerHeartbeat, WorkerStatus
from transloka_worker.translation import (
    TRANSLATION_COMMAND_SCHEMA,
    DatabaseCancellationSignal,
    DatabaseTranslationOperationLoader,
    LoadedTranslationJob,
    ProductionTranslationJobRunner,
    TranslationCommand,
    TranslationWorkerError,
)


def _id(prefix: str, value: int) -> str:
    return f"{prefix}{UUID(int=value)}"


PROJECT_ID = _id("prj_", 1)
DOCUMENT_ID = _id("doc_", 2)
MODEL_ID = _id("mdl_", 3)
SNAPSHOT_ID = _id("gsn_", 4)
SECTION_ID = _id("sec_", 5)
SECTION_2_ID = _id("sec_", 6)
PAGE_ID = _id("pag_", 7)
PAGE_2_ID = _id("pag_", 8)
BLOCK_ID = _id("blk_", 9)
BLOCK_2_ID = _id("blk_", 10)
SEGMENT_ID = _id("seg_", 11)
SEGMENT_2_ID = _id("seg_", 12)
ORIGINAL_FILE_ID = _id("fil_", 13)
CREATED_AT = "2026-08-27T00:00:00.000Z"
REPOSITORY_ROOT = Path(__file__).parents[3]
ALEMBIC_CONFIGURATION = REPOSITORY_ROOT / "alembic.ini"
CLIENT_HEADERS = {
    CLIENT_HEADER: CLIENT_HEADER_VALUE,
    CLIENT_VERSION_HEADER: CLIENT_VERSION_VALUE,
}


class HealthyProvider:
    async def health_check(self) -> ProviderHealth:
        return ProviderHealth(status=ProviderHealthStatus.AVAILABLE, version="test")


class RecordingQueue:
    name = "translation"

    def enqueue(self, _job_id: str) -> None:
        return None


class StaticWorkerHeartbeatStore:
    def read(self) -> PersistedWorkerHeartbeat:
        return PersistedWorkerHeartbeat(
            worker_name="transloka-worker",
            worker_identifier="test-worker",
            status=WorkerStatus.RUNNING,
            sequence=1,
            recorded_at=time.time(),
        )


class RuntimeProvider:
    def __init__(
        self,
        responses: list[str | TranslationProviderError] | None = None,
        *,
        on_translate: object | None = None,
    ) -> None:
        self._responses = responses or []
        self._on_translate = on_translate
        self.calls = 0

    async def translate(self, request: object, *, cancellation: object = None) -> str:
        del cancellation
        if callable(self._on_translate):
            self._on_translate()
        source_data = request.source_data["source_data"]  # type: ignore[attr-defined]
        segments = source_data["segments"]
        if self.calls < len(self._responses):
            response = self._responses[self.calls]
            self.calls += 1
            if isinstance(response, TranslationProviderError):
                raise response
            return response
        self.calls += 1
        return json.dumps(
            {
                "segments": [
                    {
                        "segment_id": segment["segment_id"],
                        "translated_text": f"Terjemahan {segment['source_text']}",
                    }
                    for segment in segments
                ]
            }
        )


def _response(*pairs: tuple[str, str]) -> str:
    return json.dumps(
        {
            "segments": [
                {"segment_id": segment_id, "translated_text": text} for segment_id, text in pairs
            ]
        }
    )


@dataclass(frozen=True, slots=True)
class LoaderFixture:
    client: TestClient
    factory: sessionmaker[Session]
    project_id: str
    storage: LocalFileStorage
    data_root: Path

    def start(self, **overrides: object) -> str:
        payload: dict[str, object] = {"model_id": MODEL_ID, "batch_size": 5}
        payload.update(overrides)
        response = self.client.post(
            f"/api/v1/projects/{self.project_id}/translation/start",
            headers={**CLIENT_HEADERS, "Idempotency-Key": "translation-runtime-1"},
            json=payload,
        )
        assert response.status_code == 202, response.text
        return cast(str, response.json()["data"]["job_id"])

    def load(self, job_id: str) -> LoadedTranslationJob:
        return DatabaseTranslationOperationLoader(self.factory, self.storage).load(job_id)


@pytest.fixture
def loader_fixture(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> Iterator[LoaderFixture]:
    root = tmp_path / "translation worker"
    monkeypatch.setenv("TRANSLOKA_DATA_DIR", str(root))
    alembic_command.upgrade(Config(str(ALEMBIC_CONFIGURATION)), "head")
    application: FastAPI = create_app()
    application.state.ollama_provider = HealthyProvider()
    application.state.translation_queue = RecordingQueue()
    application.state.worker_heartbeat_store = StaticWorkerHeartbeatStore()
    with TestClient(application) as client:
        response = client.post(
            "/api/v1/projects",
            headers=CLIENT_HEADERS,
            json={
                "name": "Worker Translation Project",
                "description": None,
                "source_language": "en",
                "target_language": "id",
                "document_type": "TECHNICAL_BOOK",
                "translation_style": "PROFESSIONAL",
                "reconstruction_mode": "HYBRID",
            },
        )
        assert response.status_code == 201
        project_id = cast(str, response.json()["data"]["id"])
        factory = cast(sessionmaker[Session], application.state.session_factory)
        _seed_loader_state(factory, project_id)
        yield LoaderFixture(
            client=client,
            factory=factory,
            project_id=project_id,
            storage=LocalFileStorage(application.state.settings.data_directories),
            data_root=application.state.settings.data_directories.root,
        )


def _seed_loader_state(factory: sessionmaker[Session], project_id: str) -> None:
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
                page_count=2,
                word_count_estimate=5,
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
        session.add_all(
            [
                DocumentSection(
                    id=SECTION_ID,
                    document_id=DOCUMENT_ID,
                    parent_section_id=None,
                    section_type=SectionType.SECTION.value,
                    level=1,
                    section_order=1,
                    title_segment_id=SEGMENT_ID,
                    start_page_id=PAGE_ID,
                    end_page_id=PAGE_ID,
                    source_summary=None,
                    context_json=None,
                    created_at=CREATED_AT,
                    updated_at=CREATED_AT,
                ),
                DocumentSection(
                    id=SECTION_2_ID,
                    document_id=DOCUMENT_ID,
                    parent_section_id=None,
                    section_type=SectionType.SECTION.value,
                    level=1,
                    section_order=2,
                    title_segment_id=None,
                    start_page_id=PAGE_2_ID,
                    end_page_id=PAGE_2_ID,
                    source_summary=None,
                    context_json=None,
                    created_at=CREATED_AT,
                    updated_at=CREATED_AT,
                ),
            ]
        )
        session.add_all(
            [
                _page(PAGE_ID, 1),
                _page(PAGE_2_ID, 2),
            ]
        )
        session.flush()
        session.add_all(
            [
                _block(BLOCK_ID, PAGE_ID, SECTION_ID, 0),
                _block(BLOCK_2_ID, PAGE_2_ID, SECTION_2_ID, 0),
            ]
        )
        session.flush()
        session.add_all(
            [
                _segment(SEGMENT_ID, BLOCK_ID, SECTION_ID, 0, "First source."),
                _segment(SEGMENT_2_ID, BLOCK_2_ID, SECTION_2_ID, 1, "Second source."),
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


def _page(page_id: str, number: int) -> DocumentPage:
    return DocumentPage(
        id=page_id,
        document_id=DOCUMENT_ID,
        source_page_number=number,
        logical_page_number=str(number),
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


def _block(
    block_id: str,
    page_id: str,
    section_id: str,
    order: int,
) -> DocumentBlock:
    return DocumentBlock(
        id=block_id,
        page_id=page_id,
        section_id=section_id,
        parent_block_id=None,
        block_type=BlockType.PARAGRAPH.value,
        semantic_role=SemanticRole.BODY_TEXT.value,
        page_reading_order=order,
        global_reading_order=order,
        source_text="Source",
        normalized_source_text="source",
        source_geometry_json='{"x":1,"y":1,"width":10,"height":10}',
        target_geometry_json=None,
        style_json=None,
        detail_json=None,
        status=DocumentStatus.STRUCTURED.value,
        confidence=0.99,
        created_at=CREATED_AT,
        updated_at=CREATED_AT,
    )


def _segment(
    segment_id: str,
    block_id: str,
    section_id: str,
    order: int,
    text: str,
) -> DocumentSegment:
    return DocumentSegment(
        id=segment_id,
        block_id=block_id,
        section_id=section_id,
        segment_order=order,
        global_order=order,
        source_text=text,
        native_text=text,
        ocr_text=None,
        resolved_source_text=text,
        normalized_source_text=text.lower(),
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


def _command(**overrides: object) -> TranslationCommand:
    values: dict[str, object] = {
        "project_id": PROJECT_ID,
        "document_id": DOCUMENT_ID,
        "scope": "FULL_DOCUMENT",
        "section_ids": (),
        "page_ids": (),
        "segment_ids": (),
        "model_id": MODEL_ID,
        "translation_style": "PROFESSIONAL",
        "batch_size": 5,
        "context_mode": "STANDARD",
        "retranslate_existing": False,
        "skip_locked_segments": True,
        "run_semantic_validation": False,
        "glossary_snapshot_id": SNAPSHOT_ID,
    }
    values.update(overrides)
    return TranslationCommand(**values)  # type: ignore[arg-type]


def test_translation_command_round_trips_canonically() -> None:
    command = _command()

    payload = command.to_payload()

    assert payload["schema"] == TRANSLATION_COMMAND_SCHEMA
    assert (
        TranslationCommand.from_payload_json(
            json.dumps(payload, sort_keys=True, separators=(",", ":"))
        )
        == command
    )


def test_translation_command_rejects_unknown_fields() -> None:
    payload = _command().to_payload()
    payload["unexpected"] = True

    with pytest.raises(TranslationWorkerError, match="fields"):
        TranslationCommand.from_payload_json(json.dumps(payload))


@pytest.mark.parametrize(
    "payload_change",
    [
        {"schema": "transloka.translation.command.v2"},
        {"project_id": "prj_invalid"},
        {"batch_size": 0},
        {"batch_size": 101},
        {"context_mode": "UNBOUNDED"},
        {"skip_locked_segments": 1},
        {"section_ids": "not-a-list"},
    ],
)
def test_translation_command_rejects_invalid_values(
    payload_change: dict[str, object],
) -> None:
    payload = _command().to_payload()
    payload.update(payload_change)

    with pytest.raises(TranslationWorkerError):
        TranslationCommand.from_payload_json(json.dumps(payload))


def test_translation_command_requires_matching_scope_selector() -> None:
    payload = _command(scope="SECTION", section_ids=(SECTION_ID,)).to_payload()
    assert TranslationCommand.from_payload_json(json.dumps(payload)).section_ids == (SECTION_ID,)

    payload["page_ids"] = [_id("pag_", 6)]
    with pytest.raises(TranslationWorkerError, match="selector"):
        TranslationCommand.from_payload_json(json.dumps(payload))


def test_loader_binds_authoritative_translation_operation(
    loader_fixture: LoaderFixture,
) -> None:
    loaded = loader_fixture.load(loader_fixture.start(batch_size=7))

    assert loaded.ollama_model_name == "translation-test:latest"
    assert loaded.operation is not None
    assert loaded.operation.model_id == MODEL_ID
    assert loaded.operation.idempotency_key == "translation-runtime-1"
    assert loaded.operation.batch_limits == BatchLimits(max_segments=7)
    assert tuple(segment.segment_id for segment in loaded.operation.segments) == (
        SEGMENT_ID,
        SEGMENT_2_ID,
    )
    assert loaded.operation.segments[0].context.heading == "First source."
    assert loaded.operation.segments[0].context.previous_text is None
    assert loaded.operation.segments[0].context.next_text == "Second source."
    assert loaded.operation.segments[1].context.previous_text == "First source."
    assert loaded.operation.segments[1].context.next_text is None


@pytest.mark.parametrize(
    ("payload", "expected"),
    [
        ({"scope": "FULL_DOCUMENT"}, (SEGMENT_ID, SEGMENT_2_ID)),
        (
            {"scope": "SECTION", "section_ids": [SECTION_2_ID]},
            (SEGMENT_2_ID,),
        ),
        ({"scope": "PAGE", "page_ids": [PAGE_ID]}, (SEGMENT_ID,)),
        (
            {"scope": "SELECTED_SEGMENTS", "segment_ids": [SEGMENT_2_ID]},
            (SEGMENT_2_ID,),
        ),
        ({"scope": "UNTRANSLATED_ONLY"}, (SEGMENT_2_ID,)),
        (
            {"scope": "UNREVIEWED_ONLY", "retranslate_existing": True},
            (SEGMENT_2_ID,),
        ),
    ],
)
def test_loader_applies_translation_scope(
    loader_fixture: LoaderFixture,
    payload: dict[str, object],
    expected: tuple[str, ...],
) -> None:
    if payload["scope"] in {"UNTRANSLATED_ONLY", "UNREVIEWED_ONLY"}:
        with transaction_scope(loader_fixture.factory) as session:
            first = session.get(DocumentSegment, SEGMENT_ID)
            assert first is not None
            first.machine_translation = "Terjemahan lama."
            if payload["scope"] == "UNREVIEWED_ONLY":
                first.review_status = ReviewStatus.APPROVED.value

    loaded = loader_fixture.load(loader_fixture.start(**payload))

    assert loaded.selected_segment_ids == expected


def test_loader_excludes_locked_unless_both_flags_allow_retranslation(
    loader_fixture: LoaderFixture,
) -> None:
    with transaction_scope(loader_fixture.factory) as session:
        second = session.get(DocumentSegment, SEGMENT_2_ID)
        assert second is not None
        second.is_locked = 1
        second.status = SegmentStatus.LOCKED.value

    skipped = loader_fixture.load(loader_fixture.start())
    assert skipped.selected_segment_ids == (SEGMENT_ID,)

    with transaction_scope(loader_fixture.factory) as session:
        job = session.get(ApplicationJob, skipped.job_id)
        assert job is not None
        command = TranslationCommand.from_payload_json(job.payload_json)
        payload = command.to_payload()
        payload["skip_locked_segments"] = False
        job.payload_json = json.dumps(payload, sort_keys=True, separators=(",", ":"))

    still_skipped = loader_fixture.load(skipped.job_id)
    assert still_skipped.selected_segment_ids == (SEGMENT_ID,)

    with transaction_scope(loader_fixture.factory) as session:
        job = session.get(ApplicationJob, skipped.job_id)
        assert job is not None
        payload = TranslationCommand.from_payload_json(job.payload_json).to_payload()
        payload["retranslate_existing"] = True
        job.payload_json = json.dumps(payload, sort_keys=True, separators=(",", ":"))

    included = loader_fixture.load(skipped.job_id)
    assert included.selected_segment_ids == (SEGMENT_ID, SEGMENT_2_ID)
    assert included.operation is not None
    assert included.operation.segments[1].locked is False


def test_loader_returns_successful_noop_for_empty_valid_selection(
    loader_fixture: LoaderFixture,
) -> None:
    job_id = loader_fixture.start()
    with transaction_scope(loader_fixture.factory) as session:
        for segment_id, status in (
            (SEGMENT_ID, SegmentStatus.IGNORED.value),
            (SEGMENT_2_ID, SegmentStatus.NOT_TRANSLATABLE.value),
        ):
            segment = session.get(DocumentSegment, segment_id)
            assert segment is not None
            segment.status = status

    loaded = loader_fixture.load(job_id)

    assert loaded.operation is None
    assert loaded.selected_segment_ids == ()


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        ("wrong_type", "unavailable"),
        ("terminal_status", "not executable"),
        ("inactive_document", "inconsistent"),
        ("uninstalled_model", "model is unavailable"),
        ("missing_model", "model is unavailable"),
        ("missing_snapshot", "snapshot"),
        ("corrupt_snapshot", "snapshot"),
        ("semantic_validation", "Semantic validation is unavailable"),
        ("foreign_segment", "selector"),
        ("malformed_command", "command"),
    ],
)
def test_loader_fails_closed_for_inconsistent_state(
    loader_fixture: LoaderFixture,
    mutation: str,
    message: str,
) -> None:
    job_id = loader_fixture.start()
    corrupt_path: Path | None = None
    with transaction_scope(loader_fixture.factory) as session:
        job = session.get(ApplicationJob, job_id)
        assert job is not None
        if mutation == "wrong_type":
            job.job_type = JobType.OCR_DOCUMENT.value
        elif mutation == "terminal_status":
            job.status = JobStatus.COMPLETED.value
        elif mutation == "inactive_document":
            project = session.get(Project, loader_fixture.project_id)
            assert project is not None
            project.active_document_id = None
        elif mutation == "uninstalled_model":
            model = session.get(LocalModelRecord, MODEL_ID)
            assert model is not None
            model.is_installed = 0
        elif mutation == "missing_model":
            model = session.get(LocalModelRecord, MODEL_ID)
            assert model is not None
            session.delete(model)
        elif mutation in {"missing_snapshot", "corrupt_snapshot"}:
            payload = TranslationCommand.from_payload_json(job.payload_json).to_payload()
            snapshot = session.get(GlossarySnapshot, payload["glossary_snapshot_id"])
            assert snapshot is not None
            if mutation == "missing_snapshot":
                session.delete(snapshot)
            else:
                stored_file = session.get(StoredFile, snapshot.snapshot_file_id)
                assert stored_file is not None
                corrupt_path = loader_fixture.data_root.joinpath(
                    *stored_file.storage_key.split("/")
                )
        elif mutation == "malformed_command":
            job.payload_json = "{}"
        else:
            payload = TranslationCommand.from_payload_json(job.payload_json).to_payload()
            if mutation == "semantic_validation":
                payload["run_semantic_validation"] = True
            else:
                payload["scope"] = "SELECTED_SEGMENTS"
                payload["segment_ids"] = [_id("seg_", 999)]
            job.payload_json = json.dumps(payload, sort_keys=True, separators=(",", ":"))

    if corrupt_path is not None:
        corrupt_path.chmod(stat.S_IREAD | stat.S_IWRITE)
        corrupt_path.write_bytes(b"corrupt")

    with pytest.raises(TranslationWorkerError, match=message):
        loader_fixture.load(job_id)


def test_production_runner_persists_successful_lifecycle(
    loader_fixture: LoaderFixture,
) -> None:
    job_id = loader_fixture.start()
    provider_models: list[str] = []

    def provider_factory(model_name: str) -> RuntimeProvider:
        provider_models.append(model_name)
        return RuntimeProvider()

    result = ProductionTranslationJobRunner(
        DatabaseTranslationOperationLoader(loader_fixture.factory, loader_fixture.storage),
        loader_fixture.factory,
        loader_fixture.data_root / "temporary",
        provider_factory=provider_factory,
        worker_identifier="test-worker",
    ).run(job_id)

    assert result.status is TranslationRunStatus.COMPLETED
    assert provider_models == ["translation-test:latest"]
    with loader_fixture.factory() as session:
        job = session.get(ApplicationJob, job_id)
        assert job is not None
        assert job.status == JobStatus.COMPLETED.value
        assert job.progress == 1.0
        assert json.loads(job.result_json or "")["schema"] == (
            "transloka.translation.job-result.v1"
        )
        attempt = session.scalar(select(JobAttempt).where(JobAttempt.job_id == job_id))
        assert attempt is not None
        assert attempt.status == JobAttemptStatus.COMPLETED.value
        assert attempt.worker_identifier == "test-worker"


def test_production_runner_completes_empty_selection_without_provider(
    loader_fixture: LoaderFixture,
) -> None:
    job_id = loader_fixture.start()
    with transaction_scope(loader_fixture.factory) as session:
        for segment_id in (SEGMENT_ID, SEGMENT_2_ID):
            segment = session.get(DocumentSegment, segment_id)
            assert segment is not None
            segment.status = SegmentStatus.IGNORED.value

    def unexpected_provider(_model_name: str) -> object:
        raise AssertionError("provider must not be constructed for a no-op")

    result = ProductionTranslationJobRunner(
        DatabaseTranslationOperationLoader(loader_fixture.factory, loader_fixture.storage),
        loader_fixture.factory,
        loader_fixture.data_root / "temporary",
        provider_factory=unexpected_provider,
    ).run(job_id)

    assert result.status is TranslationRunStatus.COMPLETED
    assert result.completed_segment_ids == ()
    with loader_fixture.factory() as session:
        job = session.get(ApplicationJob, job_id)
        assert job is not None
        assert job.status == JobStatus.COMPLETED.value
        assert job.progress == 1.0


@pytest.mark.parametrize(
    ("responses", "expected_run", "expected_job"),
    [
        (
            [
                _response((SEGMENT_ID, "Terjemahan " + "panjang " * 20)),
                _response((SEGMENT_2_ID, "Terjemahan " + "panjang " * 20)),
            ],
            TranslationRunStatus.COMPLETED_WITH_WARNINGS,
            JobStatus.COMPLETED_WITH_WARNINGS,
        ),
        (
            [
                TranslationProviderError(
                    ProviderErrorCode.TIMEOUT,
                    "provider timed out",
                    retryable=True,
                ),
                TranslationProviderError(
                    ProviderErrorCode.TIMEOUT,
                    "provider timed out",
                    retryable=True,
                ),
            ],
            TranslationRunStatus.FAILED,
            JobStatus.FAILED,
        ),
    ],
)
def test_production_runner_maps_terminal_statuses(
    loader_fixture: LoaderFixture,
    responses: list[str | TranslationProviderError],
    expected_run: TranslationRunStatus,
    expected_job: JobStatus,
) -> None:
    job_id = loader_fixture.start()
    provider = RuntimeProvider(responses)
    result = ProductionTranslationJobRunner(
        DatabaseTranslationOperationLoader(loader_fixture.factory, loader_fixture.storage),
        loader_fixture.factory,
        loader_fixture.data_root / "temporary",
        provider_factory=lambda _model: provider,
    ).run(job_id)

    assert result.status is expected_run
    with loader_fixture.factory() as session:
        job = session.get(ApplicationJob, job_id)
        assert job is not None
        assert job.status == expected_job.value


def test_production_runner_persists_partial_failure_and_failed_segment(
    loader_fixture: LoaderFixture,
) -> None:
    job_id = loader_fixture.start(batch_size=1)
    provider = RuntimeProvider(
        [
            _response((SEGMENT_ID, "Sumber pertama.")),
            TranslationProviderError(
                ProviderErrorCode.TIMEOUT,
                "provider timed out",
                retryable=True,
            ),
        ]
    )
    result = ProductionTranslationJobRunner(
        DatabaseTranslationOperationLoader(loader_fixture.factory, loader_fixture.storage),
        loader_fixture.factory,
        loader_fixture.data_root / "temporary",
        provider_factory=lambda _model: provider,
    ).run(job_id)

    assert result.status is TranslationRunStatus.PARTIALLY_COMPLETED
    with loader_fixture.factory() as session:
        job = session.get(ApplicationJob, job_id)
        failed = session.get(DocumentSegment, SEGMENT_2_ID)
        assert job is not None and failed is not None
        assert job.status == JobStatus.PARTIALLY_COMPLETED.value
        assert failed.status == SegmentStatus.TRANSLATION_FAILED.value


def test_production_runner_checkpoints_cancellation(
    loader_fixture: LoaderFixture,
) -> None:
    job_id = loader_fixture.start()

    def request_cancellation() -> None:
        with transaction_scope(loader_fixture.factory) as session:
            job = session.get(ApplicationJob, job_id)
            project = session.get(Project, loader_fixture.project_id)
            document = session.get(Document, DOCUMENT_ID)
            first = session.get(DocumentSegment, SEGMENT_ID)
            assert job is not None and project is not None and document is not None
            assert first is not None
            assert job.status == JobStatus.RUNNING.value
            assert project.status == "TRANSLATING"
            assert document.status == DocumentStatus.TRANSLATING.value
            assert first.status == SegmentStatus.TRANSLATING.value
            job.status = JobStatus.CANCELLATION_REQUESTED.value

    provider = RuntimeProvider(on_translate=request_cancellation)
    result = ProductionTranslationJobRunner(
        DatabaseTranslationOperationLoader(loader_fixture.factory, loader_fixture.storage),
        loader_fixture.factory,
        loader_fixture.data_root / "temporary",
        provider_factory=lambda _model: provider,
    ).run(job_id)

    assert result.status is TranslationRunStatus.CANCELLED
    with loader_fixture.factory() as session:
        job = session.get(ApplicationJob, job_id)
        document = session.get(Document, DOCUMENT_ID)
        first = session.get(DocumentSegment, SEGMENT_ID)
        second = session.get(DocumentSegment, SEGMENT_2_ID)
        assert job is not None and document is not None
        assert first is not None and second is not None
        assert job.status == JobStatus.CANCELLED.value
        assert document.status == DocumentStatus.STRUCTURED.value
        assert first.status == SegmentStatus.READY_FOR_TRANSLATION.value
        assert second.status == SegmentStatus.READY_FOR_TRANSLATION.value
        assert first.machine_translation is None
        assert second.machine_translation is None


def test_production_runner_sanitizes_unexpected_failure_and_reraises(
    loader_fixture: LoaderFixture,
) -> None:
    job_id = loader_fixture.start()

    with pytest.raises(RuntimeError, match="unsafe details"):
        ProductionTranslationJobRunner(
            DatabaseTranslationOperationLoader(loader_fixture.factory, loader_fixture.storage),
            loader_fixture.factory,
            loader_fixture.data_root / "temporary",
            provider_factory=lambda _model: (_ for _ in ()).throw(
                RuntimeError("unsafe details\nwith control")
            ),
        ).run(job_id)

    with loader_fixture.factory() as session:
        job = session.get(ApplicationJob, job_id)
        attempt = session.scalar(select(JobAttempt).where(JobAttempt.job_id == job_id))
        assert job is not None and attempt is not None
        assert job.status == JobStatus.FAILED.value
        assert job.error_code == "RUNTIMEERROR"
        assert job.error_message == "Translation job failed."
        assert attempt.status == JobAttemptStatus.FAILED.value


def test_database_cancellation_signal_reads_persisted_state(
    loader_fixture: LoaderFixture,
) -> None:
    job_id = loader_fixture.start()
    signal = DatabaseCancellationSignal(loader_fixture.factory, job_id)
    assert signal.is_cancelled is False

    with transaction_scope(loader_fixture.factory) as session:
        job = session.get(ApplicationJob, job_id)
        assert job is not None
        job.status = JobStatus.CANCELLATION_REQUESTED.value

    assert signal.is_cancelled is True
