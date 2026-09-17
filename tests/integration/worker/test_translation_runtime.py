import json
import stat
import time
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any, cast
from uuid import UUID

import pytest
from alembic import command as alembic_command
from alembic.config import Config
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import event, select
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
from transloka_core.database.models.translation import (
    SegmentTranslation,
    TranslationAttempt,
    TranslationBatch,
)
from transloka_core.jobs.recovery import JobRecoveryService
from transloka_core.storage.local import LocalFileStorage
from transloka_translation.batching import BatchLimits
from transloka_translation.orchestration import TranslationRunStatus
from transloka_translation.providers import (
    ProviderErrorCode,
    ProviderHealth,
    ProviderHealthStatus,
    TranslationProviderError,
)
from transloka_translation.providers.ctranslate2 import MODEL_ID as CT2_MODEL_ID
from transloka_translation.providers.ollama import OllamaTranslationProvider
from transloka_worker.ctranslate2 import (
    CTranslate2ConfigurationError,
    CTranslate2Settings,
    ctranslate2_settings_from_environment,
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
    _run_loaded_translation_job,
    _start_translation_job,
    _translation_provider,
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
        idempotency_key = overrides.pop("idempotency_key", "translation-runtime-1")
        assert isinstance(idempotency_key, str)
        model_id = CT2_MODEL_ID if overrides.get("provider_type") == "CTRANSLATE2" else MODEL_ID
        payload: dict[str, object] = {"model_id": model_id, "batch_size": 5}
        payload.update(overrides)
        response = self.client.post(
            f"/api/v1/projects/{self.project_id}/translation/start",
            headers={**CLIENT_HEADERS, "Idempotency-Key": idempotency_key},
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
    monkeypatch.setenv("TRANSLOKA_CT2_MODEL_DIR", str(tmp_path / "private-ct2-model"))
    monkeypatch.delenv("TRANSLOKA_CT2_OLLAMA_FALLBACK_MODEL", raising=False)
    alembic_command.upgrade(Config(str(ALEMBIC_CONFIGURATION)), "head")
    application: FastAPI = create_app()
    application.state.ollama_provider = HealthyProvider()
    application.state.ctranslate2_provider = HealthyProvider()
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
        {"schema": "transloka.translation.command.v3"},
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


def test_translation_command_decodes_queued_v1_as_ollama() -> None:
    payload = _command().to_payload()
    payload["schema"] = "transloka.translation.command.v1"
    for key in (
        "provider_type",
        "cloud_model_name",
        "cloud_consent",
        "cloud_consent_version",
    ):
        payload.pop(key)

    command = TranslationCommand.from_payload_json(json.dumps(payload))

    assert command.provider_type == "OLLAMA"
    assert command.model_id == MODEL_ID
    assert command.cloud_model_name is None
    assert command.cloud_consent is False


def test_ctranslate2_command_round_trips_without_cloud_or_model_path() -> None:
    command = _command(provider_type="CTRANSLATE2", model_id=CT2_MODEL_ID)
    payload = command.to_payload()
    assert payload["schema"] == "transloka.translation.command.v2"
    assert payload["provider_type"] == "CTRANSLATE2"
    assert payload["model_id"] == CT2_MODEL_ID
    assert payload["cloud_model_name"] is None
    assert payload["cloud_consent"] is False
    assert payload["cloud_consent_version"] is None
    assert "model_dir" not in payload
    assert TranslationCommand.from_payload_json(json.dumps(payload)) == command


def test_ctranslate2_snapshot_round_trips_provenance_generation_and_fallback() -> None:
    settings = CTranslate2Settings("qwen2.5:3b", "http://127.0.0.1:11434")
    command = _command(
        provider_type="CTRANSLATE2", model_id=CT2_MODEL_ID, ctranslate2_settings=settings
    )
    payload = command.to_payload()
    assert TranslationCommand.from_payload_json(json.dumps(payload)) == command
    snapshot = settings.to_payload()
    provenance = cast(dict[str, object], snapshot["provenance"])
    generation = cast(dict[str, object], snapshot["generation"])
    assert provenance["model_id"] == CT2_MODEL_ID
    assert provenance["source_model"] == "Helsinki-NLP/opus-mt-en-id"
    assert provenance["source_revision"] == "6e4c52d61a6b16fe3509b0267cbfec65011b860b"
    assert provenance["files"]
    assert generation["device"] == "cpu"
    assert generation["compute_type"] == "int8"
    assert (generation["beam_size"], generation["retry_beam_size"]) == (1, 4)
    assert generation["max_decoding_length"] == 512
    assert snapshot["fallback"] == {
        "provider_type": "OLLAMA",
        "model_name": "qwen2.5:3b",
        "base_url": "http://127.0.0.1:11434",
        "temperature": 0.1,
        "translation_timeout_seconds": 600.0,
    }


@pytest.mark.parametrize("field", ["provenance", "generation", "fallback", "schema"])
def test_ctranslate2_command_rejects_mutated_snapshot(field: str) -> None:
    payload = _command(
        provider_type="CTRANSLATE2",
        model_id=CT2_MODEL_ID,
        ctranslate2_settings=CTranslate2Settings(),
    ).to_payload()
    settings = cast(dict[str, object], payload["ctranslate2_settings"])
    settings[field] = {"provider_type": "GROQ", "model_name": "qwen/qwen3.8-27b"}
    with pytest.raises(TranslationWorkerError):
        TranslationCommand.from_payload_json(json.dumps(payload))


def test_ctranslate2_settings_cannot_be_attached_to_another_provider() -> None:
    with pytest.raises(TranslationWorkerError, match="conflicts"):
        _command(ctranslate2_settings=CTranslate2Settings())


@pytest.mark.parametrize("value", [None, "", "  "])
def test_ctranslate2_fallback_is_disabled_by_default(
    monkeypatch: pytest.MonkeyPatch, value: str | None
) -> None:
    if value is None:
        monkeypatch.delenv("TRANSLOKA_CT2_OLLAMA_FALLBACK_MODEL", raising=False)
    else:
        monkeypatch.setenv("TRANSLOKA_CT2_OLLAMA_FALLBACK_MODEL", value)
    monkeypatch.setenv("TRANSLOKA_OLLAMA_URL", "https://untrusted.example")
    assert ctranslate2_settings_from_environment().to_payload()["fallback"] is None


@pytest.mark.parametrize(
    "url",
    ["https://untrusted.example", "http://192.0.2.1:11434", "http://user:secret@localhost:11434"],
)
def test_ctranslate2_fallback_requires_a_loopback_endpoint(
    monkeypatch: pytest.MonkeyPatch, url: str
) -> None:
    monkeypatch.setenv("TRANSLOKA_CT2_OLLAMA_FALLBACK_MODEL", "qwen2.5:3b")
    monkeypatch.setenv("TRANSLOKA_OLLAMA_URL", url)
    with pytest.raises(CTranslate2ConfigurationError, match="endpoint is invalid"):
        ctranslate2_settings_from_environment()


@pytest.mark.parametrize(
    "changes",
    [
        {"model_id": None},
        {"model_id": MODEL_ID},
        {"model_id": "/private/model"},
        {"cloud_model_name": "qwen/qwen3.8-27b"},
        {"cloud_consent": True},
        {"cloud_consent_version": "cloud_text_sharing_v1"},
    ],
)
def test_ctranslate2_command_rejects_conflicting_fields(changes: dict[str, object]) -> None:
    payload = _command(provider_type="CTRANSLATE2", model_id=CT2_MODEL_ID).to_payload()
    payload.update(changes)
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
@pytest.mark.parametrize("provider_type", ["OLLAMA", "CTRANSLATE2"])
def test_loader_applies_translation_scope(
    loader_fixture: LoaderFixture,
    payload: dict[str, object],
    expected: tuple[str, ...],
    provider_type: str,
) -> None:
    if payload["scope"] in {"UNTRANSLATED_ONLY", "UNREVIEWED_ONLY"}:
        with transaction_scope(loader_fixture.factory) as session:
            first = session.get(DocumentSegment, SEGMENT_ID)
            assert first is not None
            first.machine_translation = "Terjemahan lama."
            if payload["scope"] == "UNREVIEWED_ONLY":
                first.review_status = ReviewStatus.APPROVED.value

    loaded = loader_fixture.load(loader_fixture.start(provider_type=provider_type, **payload))

    assert loaded.selected_segment_ids == expected


@pytest.mark.parametrize("state", ["LOCKED", "APPROVED", "USER_EDITED"])
@pytest.mark.parametrize("provider_type", ["OLLAMA", "CTRANSLATE2"])
def test_loader_excludes_protected_even_when_both_flags_allow_retranslation(
    loader_fixture: LoaderFixture,
    state: str,
    provider_type: str,
) -> None:
    with transaction_scope(loader_fixture.factory) as session:
        second = session.get(DocumentSegment, SEGMENT_2_ID)
        assert second is not None
        second.is_locked = int(state == "LOCKED")
        second.status = state

    skipped = loader_fixture.load(loader_fixture.start(provider_type=provider_type))
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
    assert included.selected_segment_ids == (SEGMENT_ID,)


@pytest.mark.parametrize("state", ["LOCKED", "APPROVED", "USER_EDITED", "SOURCE_CORRECTED"])
@pytest.mark.parametrize("outcome", ["success", "timeout", "cancel", "exception"])
@pytest.mark.parametrize("provider_type", ["OLLAMA", "CTRANSLATE2"])
def test_worker_preserves_changes_made_while_provider_is_running(
    loader_fixture: LoaderFixture, state: str, outcome: str, provider_type: str
) -> None:
    job_id = loader_fixture.start(provider_type=provider_type)
    expected: tuple[object, ...] | None = None

    def edit_during_translation() -> None:
        nonlocal expected
        if expected is not None:
            return
        with transaction_scope(loader_fixture.factory) as session:
            row = session.get(DocumentSegment, SEGMENT_ID)
            assert row is not None
            row.current_revision += 1
            if state == "SOURCE_CORRECTED":
                row.resolved_source_text = "Corrected source text."
            row.is_locked = int(state == "LOCKED")
            row.status = "READY_FOR_TRANSLATION" if state == "SOURCE_CORRECTED" else state
            row.review_status = (
                ReviewStatus.APPROVED.value
                if state in {"LOCKED", "APPROVED"}
                else ReviewStatus.EDITED.value
                if state == "USER_EDITED"
                else ReviewStatus.NOT_REVIEWED.value
            )
            row.reviewed_translation = "Teks dari pengguna."
            row.final_text = "Teks dari pengguna."
            expected = _protected_segment_state(row)
            if outcome == "cancel":
                job = session.get(ApplicationJob, job_id)
                assert job is not None
                job.status = JobStatus.CANCELLATION_REQUESTED.value
        if outcome == "exception":
            raise RuntimeError("Simulated provider failure")

    provider = RuntimeProvider(
        responses=[TranslationProviderError(ProviderErrorCode.TIMEOUT, "Timed out")]
        if outcome == "timeout"
        else None,
        on_translate=edit_during_translation,
    )
    runner = ProductionTranslationJobRunner(
        DatabaseTranslationOperationLoader(loader_fixture.factory, loader_fixture.storage),
        loader_fixture.factory,
        loader_fixture.data_root / "temporary",
        provider_factory=lambda _: provider,
        ctranslate2_provider_factory=lambda: provider,
    )
    if outcome == "exception":
        with pytest.raises(RuntimeError, match="Simulated provider failure"):
            runner.run(job_id)
    else:
        result = runner.run(job_id)
        if outcome == "success":
            assert SEGMENT_ID not in result.completed_segment_ids
            assert SEGMENT_2_ID in result.completed_segment_ids
            assert result.status is TranslationRunStatus.PARTIALLY_COMPLETED
            assert result.failures[0].code == "SEGMENT_REVISION_CONFLICT"
    with loader_fixture.factory() as session:
        row = session.get(DocumentSegment, SEGMENT_ID)
        assert row is not None
        assert _protected_segment_state(row) == expected
        assert (
            session.scalar(
                select(SegmentTranslation).where(
                    SegmentTranslation.segment_id == SEGMENT_ID,
                )
            )
            is None
        )


def _protected_segment_state(row: DocumentSegment) -> tuple[object, ...]:
    return (
        row.status,
        row.review_status,
        row.is_locked,
        row.current_revision,
        row.machine_translation,
        row.reviewed_translation,
        row.final_text,
        row.resolved_source_text,
    )


@pytest.mark.parametrize("provider_type", ["OLLAMA", "CTRANSLATE2"])
def test_worker_rejects_revision_changed_between_load_and_start(
    loader_fixture: LoaderFixture,
    provider_type: str,
) -> None:
    loaded = loader_fixture.load(loader_fixture.start(provider_type=provider_type))
    with transaction_scope(loader_fixture.factory) as session:
        row = session.get(DocumentSegment, SEGMENT_ID)
        assert row is not None
        row.current_revision += 1
        row.status = SegmentStatus.USER_EDITED.value
        row.review_status = ReviewStatus.EDITED.value
        expected = _protected_segment_state(row)

    def unexpected_provider(_name: str) -> object:
        raise AssertionError("Provider must not run for a stale loaded operation")

    with pytest.raises(TranslationWorkerError, match="changed before start"):
        _run_loaded_translation_job(
            loaded,
            session_factory=loader_fixture.factory,
            temporary_root=loader_fixture.data_root / "temporary",
            provider_factory=unexpected_provider,
            ctranslate2_provider_factory=lambda: unexpected_provider(CT2_MODEL_ID),
            worker_identifier="test-worker",
        )
    with loader_fixture.factory() as session:
        row = session.get(DocumentSegment, SEGMENT_ID)
        assert row is not None
        assert _protected_segment_state(row) == expected


def test_result_update_checks_revision_atomically(loader_fixture: LoaderFixture) -> None:
    job_id = loader_fixture.start()
    engine = loader_fixture.factory.kw["bind"]
    changed = False

    def change_before_update(*args: object) -> None:
        nonlocal changed
        statement = str(args[2])
        if changed or "SET heartbeat_at=application_jobs.heartbeat_at" not in statement:
            return
        changed = True
        with transaction_scope(loader_fixture.factory) as session:
            row = session.get(DocumentSegment, SEGMENT_ID)
            assert row is not None
            row.current_revision += 1
            row.resolved_source_text = "New source committed just before the result write."
            row.status = SegmentStatus.READY_FOR_TRANSLATION.value

    event.listen(engine, "before_cursor_execute", change_before_update)
    try:
        result = ProductionTranslationJobRunner(
            DatabaseTranslationOperationLoader(loader_fixture.factory, loader_fixture.storage),
            loader_fixture.factory,
            loader_fixture.data_root / "temporary",
            provider_factory=lambda _: RuntimeProvider(),
        ).run(job_id)
    finally:
        event.remove(engine, "before_cursor_execute", change_before_update)
    assert changed
    assert SEGMENT_ID in result.failed_segment_ids
    assert SEGMENT_2_ID in result.completed_segment_ids
    with loader_fixture.factory() as session:
        row = session.get(DocumentSegment, SEGMENT_ID)
        assert row is not None
        assert row.current_revision == 1
        assert row.status == SegmentStatus.READY_FOR_TRANSLATION.value
        assert row.machine_translation is None


@pytest.mark.parametrize("outcome", ["success", "exception"])
def test_late_worker_preserves_recovered_state(loader_fixture: LoaderFixture, outcome: str) -> None:
    job_id = loader_fixture.start()
    recovered: dict[str, list[object]] = {}

    def recover_while_model_runs() -> None:
        if recovered:
            return
        JobRecoveryService(
            loader_fixture.factory,
            data_root=loader_fixture.data_root,
            temporary_root=loader_fixture.data_root / "temp",
        ).recover(now=datetime.now(UTC) + timedelta(hours=1))
        with loader_fixture.factory() as session:
            for model in (ApplicationJob, JobAttempt, DocumentSegment, Project, Document):
                recovered[model.__tablename__] = list(session.execute(select(model.__table__)))
        if outcome == "exception":
            raise RuntimeError("Late provider failure")

    runner = ProductionTranslationJobRunner(
        DatabaseTranslationOperationLoader(loader_fixture.factory, loader_fixture.storage),
        loader_fixture.factory,
        loader_fixture.data_root / "temp",
        provider_factory=lambda _: RuntimeProvider(on_translate=recover_while_model_runs),
    )
    with pytest.raises((TranslationWorkerError, RuntimeError)):
        runner.run(job_id)
    with loader_fixture.factory() as session:
        for model in (ApplicationJob, JobAttempt, DocumentSegment, Project, Document):
            assert list(session.execute(select(model.__table__))) == recovered[model.__tablename__]
        assert session.scalar(select(SegmentTranslation)) is None


def test_duplicate_worker_does_not_take_running_attempt(loader_fixture: LoaderFixture) -> None:
    job_id = loader_fixture.start()
    duplicate_checked = False

    def duplicate() -> None:
        nonlocal duplicate_checked
        if duplicate_checked:
            return
        duplicate_checked = True
        with loader_fixture.factory() as session:
            before = list(session.execute(select(JobAttempt.__table__)))
        with pytest.raises(TranslationWorkerError):
            ProductionTranslationJobRunner(
                DatabaseTranslationOperationLoader(loader_fixture.factory, loader_fixture.storage),
                loader_fixture.factory,
                loader_fixture.data_root / "temp",
                provider_factory=lambda _: RuntimeProvider(),
                worker_identifier="duplicate",
            ).run(job_id)
        with loader_fixture.factory() as session:
            assert list(session.execute(select(JobAttempt.__table__))) == before
            job = session.get(ApplicationJob, job_id)
            assert job is not None and job.status == "RUNNING"

    result = ProductionTranslationJobRunner(
        DatabaseTranslationOperationLoader(loader_fixture.factory, loader_fixture.storage),
        loader_fixture.factory,
        loader_fixture.data_root / "temp",
        provider_factory=lambda _: RuntimeProvider(on_translate=duplicate),
    ).run(job_id)
    assert duplicate_checked
    assert set(result.completed_segment_ids) == {SEGMENT_ID, SEGMENT_2_ID}


def test_previous_attempt_cannot_write_after_retry_starts(loader_fixture: LoaderFixture) -> None:
    job_id = loader_fixture.start()
    expected: dict[str, list[object]] = {}

    def start_retry() -> None:
        with transaction_scope(loader_fixture.factory) as session:
            job = session.get(ApplicationJob, job_id)
            assert job is not None
            job.status = "RETRYING"
            job.retry_count += 1
            attempt = session.scalar(select(JobAttempt).where(JobAttempt.job_id == job_id))
            assert attempt is not None
            attempt.status = "STALE"
        loaded = loader_fixture.load(job_id)
        _start_translation_job(loader_fixture.factory, loaded, "replacement-worker")
        with loader_fixture.factory() as session:
            for model in (ApplicationJob, JobAttempt, DocumentSegment, Project, Document):
                expected[model.__tablename__] = list(session.execute(select(model.__table__)))

    with pytest.raises(TranslationWorkerError, match="no longer owns"):
        ProductionTranslationJobRunner(
            DatabaseTranslationOperationLoader(loader_fixture.factory, loader_fixture.storage),
            loader_fixture.factory,
            loader_fixture.data_root / "temp",
            provider_factory=lambda _: RuntimeProvider(on_translate=start_retry),
        ).run(job_id)
    with loader_fixture.factory() as session:
        for model in (ApplicationJob, JobAttempt, DocumentSegment, Project, Document):
            assert list(session.execute(select(model.__table__))) == expected[model.__tablename__]
        assert session.scalar(select(SegmentTranslation)) is None


def test_loaded_operation_from_previous_retry_generation_is_rejected(
    loader_fixture: LoaderFixture,
) -> None:
    loaded = loader_fixture.load(loader_fixture.start())
    with transaction_scope(loader_fixture.factory) as session:
        job = session.get(ApplicationJob, loaded.job_id)
        assert job is not None
        job.retry_count += 1
        job.status = "RETRYING"
    with pytest.raises(TranslationWorkerError, match="no longer executable"):
        _run_loaded_translation_job(
            loaded,
            session_factory=loader_fixture.factory,
            temporary_root=loader_fixture.data_root / "temp",
            provider_factory=lambda _: RuntimeProvider(),
            worker_identifier="old-worker",
        )
    with loader_fixture.factory() as session:
        job = session.get(ApplicationJob, loaded.job_id)
        assert job is not None and job.status == "RETRYING"
        assert session.scalar(select(JobAttempt)) is None


def test_worker_persists_real_batch_plan_before_provider_and_after_finish(
    loader_fixture: LoaderFixture,
) -> None:
    job_id = loader_fixture.start(batch_size=10)
    observed: list[dict[str, object]] = []

    def read_progress() -> None:
        with loader_fixture.factory() as session:
            job = session.get(ApplicationJob, job_id)
            assert job is not None and job.result_json is not None
            observed.append(json.loads(job.result_json))

    ProductionTranslationJobRunner(
        DatabaseTranslationOperationLoader(loader_fixture.factory, loader_fixture.storage),
        loader_fixture.factory,
        loader_fixture.data_root / "temp",
        provider_factory=lambda _: RuntimeProvider(on_translate=read_progress),
    ).run(job_id)
    # Different sections produce two batches even with a maximum batch size of ten.
    assert observed[0]["current_batch"] == 0
    assert observed[0]["total_batches"] == 2
    with loader_fixture.factory() as session:
        job = session.get(ApplicationJob, job_id)
        assert job is not None and job.result_json is not None
        final = json.loads(job.result_json)
        assert final["current_batch"] == final["total_batches"] == 2


@pytest.mark.parametrize("boundary", ["result", "finish"])
def test_recovery_wins_at_the_atomic_worker_write_boundary(
    loader_fixture: LoaderFixture,
    monkeypatch: pytest.MonkeyPatch,
    boundary: str,
) -> None:
    import transloka_worker.translation as runtime
    from transloka_translation.orchestration import SqlAlchemyTranslationRunStore

    job_id = loader_fixture.start()
    armed = False
    recovered: dict[str, list[object]] = {}
    engine = loader_fixture.factory.kw["bind"]
    owner: Any = SqlAlchemyTranslationRunStore if boundary == "result" else runtime
    name = "record_result" if boundary == "result" else "_finish_translation_job"
    original = getattr(owner, name)

    def arm_write(*args: Any, **kwargs: Any) -> Any:
        nonlocal armed
        armed = True
        return original(*args, **kwargs)

    def recover_before_guard(*args: object) -> None:
        if (
            not armed
            or recovered
            or "SET heartbeat_at=application_jobs.heartbeat_at" not in str(args[2])
        ):
            return
        JobRecoveryService(
            loader_fixture.factory,
            data_root=loader_fixture.data_root,
            temporary_root=loader_fixture.data_root / "temp",
        ).recover(now=datetime.now(UTC) + timedelta(hours=1))
        with loader_fixture.factory() as session:
            for model in (
                ApplicationJob,
                JobAttempt,
                DocumentSegment,
                SegmentTranslation,
                Project,
                Document,
            ):
                recovered[model.__tablename__] = list(session.execute(select(model.__table__)))

    monkeypatch.setattr(owner, name, arm_write)
    event.listen(engine, "before_cursor_execute", recover_before_guard)
    try:
        with pytest.raises(TranslationWorkerError, match="no longer owns"):
            ProductionTranslationJobRunner(
                DatabaseTranslationOperationLoader(loader_fixture.factory, loader_fixture.storage),
                loader_fixture.factory,
                loader_fixture.data_root / "temp",
                provider_factory=lambda _: RuntimeProvider(),
            ).run(job_id)
    finally:
        event.remove(engine, "before_cursor_execute", recover_before_guard)
    assert recovered
    with loader_fixture.factory() as session:
        for model in (
            ApplicationJob,
            JobAttempt,
            DocumentSegment,
            SegmentTranslation,
            Project,
            Document,
        ):
            assert list(session.execute(select(model.__table__))) == recovered[model.__tablename__]


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


@pytest.mark.parametrize("inject_factory", [False, True])
def test_ctranslate2_runner_uses_durable_snapshot_without_other_providers(
    loader_fixture: LoaderFixture,
    monkeypatch: pytest.MonkeyPatch,
    inject_factory: bool,
) -> None:
    monkeypatch.delenv("TRANSLOKA_CLOUD_TRANSLATION_ENABLED", raising=False)
    with transaction_scope(loader_fixture.factory) as session:
        model = session.get(LocalModelRecord, MODEL_ID)
        assert model is not None
        session.delete(model)
    job_id = loader_fixture.start(provider_type="CTRANSLATE2")
    loaded = loader_fixture.load(job_id)
    provider = RuntimeProvider()
    created: list[RuntimeProvider] = []

    def ct2_factory() -> RuntimeProvider:
        created.append(provider)
        return provider

    def unexpected_provider(*_args: object) -> object:
        pytest.fail("CTranslate2 must not construct an Ollama or cloud provider.")

    if not inject_factory:
        monkeypatch.setattr(
            "transloka_worker.translation.CTranslate2TranslationProvider", ct2_factory
        )
    result = ProductionTranslationJobRunner(
        DatabaseTranslationOperationLoader(loader_fixture.factory, loader_fixture.storage),
        loader_fixture.factory,
        loader_fixture.data_root / "temporary",
        provider_factory=unexpected_provider,
        cloud_provider_factory=unexpected_provider,
        ctranslate2_provider_factory=ct2_factory if inject_factory else None,
    ).run(job_id)

    assert loaded.provider_type == "CTRANSLATE2"
    assert loaded.ollama_model_name == CT2_MODEL_ID
    assert loaded.operation is not None
    assert loaded.operation.provider_type == "CTRANSLATE2"
    assert loaded.operation.model_id == CT2_MODEL_ID
    assert created == [provider]
    assert result.status is TranslationRunStatus.COMPLETED_WITH_WARNINGS
    assert result.completed_segment_ids == (SEGMENT_ID, SEGMENT_2_ID)
    with loader_fixture.factory() as session:
        batch = session.get(TranslationBatch, result.run_id)
        attempts = list(
            session.scalars(
                select(TranslationAttempt).where(TranslationAttempt.batch_id == result.run_id)
            )
        )
        assert batch is not None and attempts
        assert (batch.provider_type, batch.model_id) == ("CTRANSLATE2", CT2_MODEL_ID)
        assert all(
            (attempt.provider_type, attempt.model_id) == ("CTRANSLATE2", CT2_MODEL_ID)
            for attempt in attempts
        )
        assert "TRANSLOKA_CT2_MODEL_DIR" not in batch.settings_json
        assert "private-ct2-model" not in batch.settings_json
        assert json.loads(batch.settings_json)["ctranslate2_settings"] == (
            CTranslate2Settings().to_payload()
        )


def test_ctranslate2_factory_uses_saved_fallback_despite_environment_changes(
    loader_fixture: LoaderFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("TRANSLOKA_CT2_OLLAMA_FALLBACK_MODEL", "qwen2.5:3b")
    monkeypatch.setenv("TRANSLOKA_OLLAMA_URL", "http://127.0.0.1:11435")
    job_id = loader_fixture.start(provider_type="CTRANSLATE2")
    monkeypatch.setenv("TRANSLOKA_CT2_OLLAMA_FALLBACK_MODEL", "different-model:latest")
    monkeypatch.setenv("TRANSLOKA_OLLAMA_URL", "https://untrusted.example")
    loaded = loader_fixture.load(job_id)
    assert loaded.ctranslate2_settings == CTranslate2Settings(
        "qwen2.5:3b", "http://127.0.0.1:11435"
    )
    captured: list[OllamaTranslationProvider] = []

    def ct2_factory(*, fallback: OllamaTranslationProvider) -> RuntimeProvider:
        captured.append(fallback)
        return RuntimeProvider()

    def unexpected_provider(*_args: object) -> object:
        pytest.fail("The CT2 fallback must not use a generic or cloud provider factory.")

    monkeypatch.setattr("transloka_worker.translation.CTranslate2TranslationProvider", ct2_factory)
    result = ProductionTranslationJobRunner(
        DatabaseTranslationOperationLoader(loader_fixture.factory, loader_fixture.storage),
        loader_fixture.factory,
        loader_fixture.data_root / "temporary",
        provider_factory=unexpected_provider,
        cloud_provider_factory=unexpected_provider,
    ).run(job_id)
    assert result.status is TranslationRunStatus.COMPLETED_WITH_WARNINGS
    assert len(captured) == 1
    assert isinstance(captured[0], OllamaTranslationProvider)
    assert captured[0].base_url == "http://127.0.0.1:11435"
    assert captured[0]._model_name == "qwen2.5:3b"
    with loader_fixture.factory() as session:
        batch = session.get(TranslationBatch, result.run_id)
        assert batch is not None
        assert loaded.ctranslate2_settings is not None
        assert json.loads(batch.settings_json)["ctranslate2_settings"] == (
            loaded.ctranslate2_settings.to_payload()
        )


def test_ctranslate2_legacy_payload_does_not_enable_new_environment_fallback(
    loader_fixture: LoaderFixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    job_id = loader_fixture.start(provider_type="CTRANSLATE2")
    with transaction_scope(loader_fixture.factory) as session:
        job = session.get(ApplicationJob, job_id)
        assert job is not None
        payload = json.loads(job.payload_json)
        payload.pop("ctranslate2_settings")
        job.payload_json = json.dumps(payload)
    monkeypatch.setenv("TRANSLOKA_CT2_OLLAMA_FALLBACK_MODEL", "qwen2.5:3b")
    monkeypatch.setenv("TRANSLOKA_OLLAMA_URL", "https://untrusted.example")
    loaded = loader_fixture.load(job_id)
    assert loaded.ctranslate2_settings is None
    provider = RuntimeProvider()
    monkeypatch.setattr(
        "transloka_worker.translation.CTranslate2TranslationProvider", lambda: provider
    )
    assert (
        _translation_provider(
            loaded, provider_factory=lambda _model: None, cloud_provider_factory=None
        )
        is provider
    )


@pytest.mark.parametrize("languages", [("id", "en"), ("en", "fr")])
def test_ctranslate2_loader_rechecks_language_pair(
    loader_fixture: LoaderFixture, languages: tuple[str, str]
) -> None:
    job_id = loader_fixture.start(provider_type="CTRANSLATE2")
    with transaction_scope(loader_fixture.factory) as session:
        project = session.get(Project, loader_fixture.project_id)
        document = session.get(Document, DOCUMENT_ID)
        assert project is not None and document is not None
        project.source_language, project.target_language = languages
        document.source_language, document.target_language = languages
    with pytest.raises(TranslationWorkerError, match="English to Indonesian"):
        loader_fixture.load(job_id)


@pytest.mark.parametrize(("requested", "effective"), [(5, 5), (64, 64), (100, 64)])
def test_ctranslate2_batches_respect_provider_request_limit(
    loader_fixture: LoaderFixture, requested: int, effective: int
) -> None:
    loaded = loader_fixture.load(
        loader_fixture.start(provider_type="CTRANSLATE2", batch_size=requested)
    )
    assert loaded.operation is not None
    assert loaded.operation.batch_limits.max_segments == effective


def test_ctranslate2_worker_fails_closed_if_provisioning_is_removed(
    loader_fixture: LoaderFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    job_id = loader_fixture.start(provider_type="CTRANSLATE2")
    monkeypatch.delenv("TRANSLOKA_CT2_MODEL_DIR")

    def unexpected_provider(*_args: object) -> object:
        pytest.fail("Missing CTranslate2 provisioning must not fall back to another provider.")

    result = ProductionTranslationJobRunner(
        DatabaseTranslationOperationLoader(loader_fixture.factory, loader_fixture.storage),
        loader_fixture.factory,
        loader_fixture.data_root / "temporary",
        provider_factory=unexpected_provider,
        cloud_provider_factory=unexpected_provider,
    ).run(job_id)

    assert result.status is TranslationRunStatus.FAILED
    assert result.completed_segment_ids == ()
    with loader_fixture.factory() as session:
        job = session.get(ApplicationJob, job_id)
        assert job is not None
        assert job.status == JobStatus.FAILED.value
        assert list(session.scalars(select(SegmentTranslation))) == []


@pytest.mark.parametrize("initial_provider", ["OLLAMA", "CTRANSLATE2"])
def test_ctranslate2_recovery_preserves_partial_results(
    loader_fixture: LoaderFixture, initial_provider: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    if initial_provider == "CTRANSLATE2":
        monkeypatch.setenv("TRANSLOKA_CT2_OLLAMA_FALLBACK_MODEL", "qwen2.5:3b")
        monkeypatch.setenv("TRANSLOKA_OLLAMA_URL", "http://127.0.0.1:11434")
    job_id = loader_fixture.start(provider_type=initial_provider, batch_size=1)
    provider = RuntimeProvider(
        [
            _response((SEGMENT_ID, "Sumber pertama.")),
            TranslationProviderError(ProviderErrorCode.CONTENT_REJECTED, "content rejected"),
        ]
    )
    first = ProductionTranslationJobRunner(
        DatabaseTranslationOperationLoader(loader_fixture.factory, loader_fixture.storage),
        loader_fixture.factory,
        loader_fixture.data_root / "temporary",
        provider_factory=lambda _model: provider,
        ctranslate2_provider_factory=lambda: provider,
    ).run(job_id)
    assert first.status is TranslationRunStatus.PARTIALLY_COMPLETED
    assert first.completed_segment_ids == (SEGMENT_ID,)
    with loader_fixture.factory() as session:
        segment = session.get(DocumentSegment, SEGMENT_ID)
        old_job = session.get(ApplicationJob, job_id)
        assert segment is not None and old_job is not None
        saved_segment = _protected_segment_state(segment)
        saved_payload = old_job.payload_json

    if initial_provider == "OLLAMA":
        resumed_job_id = loader_fixture.start(
            idempotency_key="ct2-resume-partial-local",
            provider_type="CTRANSLATE2",
            scope="UNTRANSLATED_ONLY",
        )
        assert resumed_job_id != job_id
    else:
        monkeypatch.setenv("TRANSLOKA_CT2_OLLAMA_FALLBACK_MODEL", "different-model:latest")
        response = loader_fixture.client.post(
            f"/api/v1/projects/{loader_fixture.project_id}/translation/retry-failed",
            headers={**CLIENT_HEADERS, "Idempotency-Key": "ct2-retry-failed"},
            json={"use_smaller_batch": False},
        )
        assert response.status_code == 202, response.text
        resumed_job_id = response.json()["data"]["active_job_id"]
        assert resumed_job_id == job_id

    resumed = loader_fixture.load(resumed_job_id)
    assert resumed.provider_type == "CTRANSLATE2"
    assert resumed.selected_segment_ids == (SEGMENT_2_ID,)
    assert resumed.operation is not None
    assert resumed.operation.model_id == CT2_MODEL_ID
    if initial_provider == "CTRANSLATE2":
        assert resumed.ctranslate2_settings is not None
        assert resumed.ctranslate2_settings.fallback_model_name == "qwen2.5:3b"
    second = ProductionTranslationJobRunner(
        DatabaseTranslationOperationLoader(loader_fixture.factory, loader_fixture.storage),
        loader_fixture.factory,
        loader_fixture.data_root / "temporary",
        ctranslate2_provider_factory=RuntimeProvider,
    ).run(resumed_job_id)
    assert second.status is TranslationRunStatus.COMPLETED_WITH_WARNINGS
    with loader_fixture.factory() as session:
        segment = session.get(DocumentSegment, SEGMENT_ID)
        old_job = session.get(ApplicationJob, job_id)
        batch = session.get(TranslationBatch, first.run_id)
        assert segment is not None and old_job is not None and batch is not None
        assert _protected_segment_state(segment) == saved_segment
        assert old_job.payload_json == saved_payload
        assert batch.provider_type == initial_provider
        if initial_provider == "OLLAMA":
            assert old_job.status == JobStatus.PARTIALLY_COMPLETED.value
            assert old_job.retry_count == 0
        else:
            assert old_job.retry_count == 1
        translations = list(
            session.scalars(
                select(SegmentTranslation).where(SegmentTranslation.segment_id == SEGMENT_ID)
            )
        )
        assert len(translations) == 1


def test_cloud_runner_uses_snapshot_and_persists_actual_provider_model(
    loader_fixture: LoaderFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TRANSLOKA_CLOUD_TRANSLATION_ENABLED", "true")
    application = cast(FastAPI, loader_fixture.client.app)
    application.state.groq_provider = HealthyProvider()
    job_id = loader_fixture.start(
        provider_type="GROQ",
        model_id=None,
        cloud_model_name="qwen/qwen3.8-27b",
        cloud_consent=True,
    )
    loaded = loader_fixture.load(job_id)
    captured: list[tuple[str, bool]] = []

    def cloud_factory(model_name: str, consent: bool) -> RuntimeProvider:
        captured.append((model_name, consent))
        return RuntimeProvider()

    result = ProductionTranslationJobRunner(
        DatabaseTranslationOperationLoader(loader_fixture.factory, loader_fixture.storage),
        loader_fixture.factory,
        loader_fixture.data_root / "temporary",
        cloud_provider_factory=cloud_factory,
    ).run(job_id)

    assert loaded.provider_type == "GROQ"
    assert loaded.ollama_model_name == "qwen/qwen3.8-27b"
    assert loaded.operation is not None
    assert loaded.operation.provider_type == "GROQ"
    assert loaded.operation.model_id == "qwen/qwen3.8-27b"
    assert captured == [("qwen/qwen3.8-27b", True)]
    with loader_fixture.factory() as session:
        batch = session.get(TranslationBatch, result.run_id)
        attempt = session.scalar(
            select(TranslationAttempt).where(TranslationAttempt.batch_id == result.run_id)
        )
        assert batch is not None and attempt is not None
        assert (batch.provider_type, batch.model_id) == ("GROQ", "qwen/qwen3.8-27b")
        assert (attempt.provider_type, attempt.model_id) == ("GROQ", "qwen/qwen3.8-27b")
        assert "GROQ_API_KEY" not in batch.settings_json


def test_cloud_quota_stop_resumes_only_unfinished_segments(
    loader_fixture: LoaderFixture,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("TRANSLOKA_CLOUD_TRANSLATION_ENABLED", "true")
    application = cast(FastAPI, loader_fixture.client.app)
    application.state.groq_provider = HealthyProvider()
    job_id = loader_fixture.start(
        provider_type="GROQ",
        model_id=None,
        cloud_model_name="qwen/qwen3.8-27b",
        cloud_consent=True,
        batch_size=1,
    )
    quota_provider = RuntimeProvider(
        [
            _response((SEGMENT_ID, "Sumber pertama.")),
            *[
                TranslationProviderError(
                    ProviderErrorCode.RATE_LIMIT,
                    "quota reached",
                    retryable=True,
                    retry_after_seconds=0.0,
                )
                for _ in range(3)
            ],
        ]
    )
    first = ProductionTranslationJobRunner(
        DatabaseTranslationOperationLoader(loader_fixture.factory, loader_fixture.storage),
        loader_fixture.factory,
        loader_fixture.data_root / "temporary",
        cloud_provider_factory=lambda _model, _consent: quota_provider,
    ).run(job_id)
    assert first.status is TranslationRunStatus.FAILED
    assert first.completed_segment_ids == (SEGMENT_ID,)
    assert first.unattempted_segment_ids == (SEGMENT_2_ID,)
    status_response = loader_fixture.client.get(
        f"/api/v1/projects/{loader_fixture.project_id}/translation/status",
        headers=CLIENT_HEADERS,
    )
    assert status_response.status_code == 200
    assert status_response.json()["data"]["provider_error_code"] == "RATE_LIMIT"
    assert status_response.json()["data"]["retry_after_seconds"] == 0.0
    assert status_response.json()["data"]["unattempted_segments"] == 1

    retry_response = loader_fixture.client.post(
        f"/api/v1/projects/{loader_fixture.project_id}/translation/retry-failed",
        headers={**CLIENT_HEADERS, "Idempotency-Key": "cloud-resume-1"},
        json={"use_smaller_batch": False},
    )
    assert retry_response.status_code == 202, retry_response.text
    resumed = loader_fixture.load(job_id)
    assert resumed.selected_segment_ids == (SEGMENT_2_ID,)
    assert resumed.operation is not None
    assert resumed.operation.idempotency_key.endswith(":retry:1")

    second = ProductionTranslationJobRunner(
        DatabaseTranslationOperationLoader(loader_fixture.factory, loader_fixture.storage),
        loader_fixture.factory,
        loader_fixture.data_root / "temporary",
        cloud_provider_factory=lambda _model, _consent: RuntimeProvider(),
    ).run(job_id)

    assert second.status is TranslationRunStatus.COMPLETED
    with loader_fixture.factory() as session:
        first_segment = session.get(DocumentSegment, SEGMENT_ID)
        second_segment = session.get(DocumentSegment, SEGMENT_2_ID)
        batches = list(
            session.scalars(
                select(TranslationBatch)
                .where(TranslationBatch.document_id == DOCUMENT_ID)
                .order_by(TranslationBatch.created_at)
            )
        )
        assert first_segment is not None and second_segment is not None
        assert first_segment.machine_translation == "Sumber pertama."
        assert second_segment.machine_translation is not None
        assert len(batches) == 2
        assert all(batch.provider_type == "GROQ" for batch in batches)


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
                ProviderErrorCode.CONTENT_REJECTED,
                "provider rejected content",
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


def test_validation_failure_persists_safe_diagnostics_without_rejected_text(
    loader_fixture: LoaderFixture,
    caplog: pytest.LogCaptureFixture,
) -> None:
    source_text = "Private study grew in the 1950s and the 2000s."
    rejected_text = "Studi rahasia tumbuh pada 1950an dan masa depan."
    with transaction_scope(loader_fixture.factory) as session:
        segment = session.get(DocumentSegment, SEGMENT_ID)
        assert segment is not None
        segment.resolved_source_text = source_text
    job_id = loader_fixture.start(batch_size=1)
    provider = RuntimeProvider(
        [_response((SEGMENT_ID, rejected_text)), _response((SEGMENT_2_ID, "Sumber kedua."))]
    )
    result = ProductionTranslationJobRunner(
        DatabaseTranslationOperationLoader(loader_fixture.factory, loader_fixture.storage),
        loader_fixture.factory,
        loader_fixture.data_root / "temporary",
        provider_factory=lambda _model: provider,
    ).run(job_id)

    assert result.status is TranslationRunStatus.PARTIALLY_COMPLETED
    with loader_fixture.factory() as session:
        attempts = list(
            session.scalars(
                select(TranslationAttempt)
                .where(TranslationAttempt.batch_id == result.run_id)
                .order_by(TranslationAttempt.attempt_number)
            )
        )
        assert [attempt.status for attempt in attempts] == ["FAILED", "COMPLETED"]
        failed_attempt = attempts[0]
        assert failed_attempt.error_code == "VALIDATION_FAILED"
        assert failed_attempt.error_message == "Translation integrity validation failed."
        assert json.loads(failed_attempt.provider_metadata_json or "{}") == {
            "validation_issues": [
                {"code": "NUMBER_MISMATCH", "severity": "CRITICAL", "segment_id": SEGMENT_ID}
            ]
        }
        job = session.get(ApplicationJob, job_id)
        segment = session.get(DocumentSegment, SEGMENT_ID)
        assert job is not None and segment is not None
        payload = json.loads(job.result_json or "{}")
        assert payload["failures"] == [
            {
                "segment_id": SEGMENT_ID,
                "code": "VALIDATION_FAILED",
                "validation_codes": ["NUMBER_MISMATCH"],
            }
        ]
        assert payload["current_batch"] == payload["total_batches"] == 2
        assert segment.status == "TRANSLATION_FAILED"
        assert segment.machine_translation is None
        assert segment.resolved_source_text == source_text
        assert (
            session.scalar(
                select(SegmentTranslation).where(SegmentTranslation.segment_id == SEGMENT_ID)
            )
            is None
        )
        diagnostics = (
            (failed_attempt.provider_metadata_json or "")
            + (failed_attempt.error_message or "")
            + (job.result_json or "")
            + (job.error_message or "")
            + caplog.text
        )
        assert source_text not in diagnostics
        assert rejected_text not in diagnostics


@pytest.mark.parametrize("provider_type", ["OLLAMA", "CTRANSLATE2"])
def test_production_runner_checkpoints_cancellation(
    loader_fixture: LoaderFixture,
    provider_type: str,
) -> None:
    job_id = loader_fixture.start(provider_type=provider_type)

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
        ctranslate2_provider_factory=lambda: provider,
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
