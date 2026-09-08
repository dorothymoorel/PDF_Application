from __future__ import annotations

import asyncio
import json
import os
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Self, cast
from uuid import NAMESPACE_URL, UUID, uuid5

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session, sessionmaker
from transloka_core.database import transaction_scope
from transloka_core.database.models.document_ir import (
    DocumentBlock,
    DocumentSection,
    DocumentSegment,
    ReviewStatus,
    SegmentStatus,
)
from transloka_core.database.models.documents import Document, DocumentStatus
from transloka_core.database.models.jobs import (
    ApplicationJob,
    JobAttempt,
    JobAttemptStatus,
    JobStatus,
    JobType,
)
from transloka_core.database.models.models import LocalModelRecord
from transloka_core.database.models.pages import DocumentPage
from transloka_core.database.models.projects import Project, ProjectStatus
from transloka_core.storage.local import LocalFileStorage
from transloka_glossary.snapshots import (
    CompiledGlossaryRule,
    GlossarySnapshotError,
    load_glossary_snapshot,
)
from transloka_translation.batching import BatchContext, BatchLimits
from transloka_translation.orchestration import (
    SqlAlchemyTranslationRunStore,
    TranslationOperation,
    TranslationOrchestrator,
    TranslationRunResult,
    TranslationRunStatus,
    TranslationSegmentInput,
)
from transloka_translation.providers import ProviderErrorCode, TranslationProviderError
from transloka_translation.providers.groq import GROQ_MODELS, GroqTranslationProvider
from transloka_translation.providers.ollama import OllamaTranslationProvider
from transloka_translation.schemas import (
    TranslationContext,
    TranslationGlossaryEntry,
    TranslationStyle,
)

TRANSLATION_COMMAND_SCHEMA_V1 = "transloka.translation.command.v1"
TRANSLATION_COMMAND_SCHEMA = "transloka.translation.command.v2"
_TRANSLATION_SCOPES = frozenset(
    {
        "FULL_DOCUMENT",
        "UNTRANSLATED_ONLY",
        "UNREVIEWED_ONLY",
        "SECTION",
        "PAGE",
        "SELECTED_SEGMENTS",
    }
)
_TRANSLATION_STYLES = frozenset({"ACADEMIC", "PROFESSIONAL", "NATURAL", "LITERAL"})
_CONTEXT_MODES = frozenset({"NONE", "STANDARD", "EXTENDED"})
_COMMAND_FIELDS_V1 = frozenset(
    {
        "schema",
        "project_id",
        "document_id",
        "scope",
        "section_ids",
        "page_ids",
        "segment_ids",
        "model_id",
        "translation_style",
        "batch_size",
        "context_mode",
        "retranslate_existing",
        "skip_locked_segments",
        "run_semantic_validation",
        "glossary_snapshot_id",
    }
)
_COMMAND_FIELDS = _COMMAND_FIELDS_V1 | {
    "provider_type",
    "cloud_model_name",
    "cloud_consent",
    "cloud_consent_version",
}
_PROVIDER_TYPES = frozenset({"OLLAMA", "GROQ"})
_CLOUD_CONSENT_VERSION = "cloud_text_sharing_v1"


class TranslationWorkerError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class TranslationCommand:
    project_id: str
    document_id: str
    scope: str
    section_ids: tuple[str, ...]
    page_ids: tuple[str, ...]
    segment_ids: tuple[str, ...]
    model_id: str | None
    translation_style: str
    batch_size: int
    context_mode: str
    retranslate_existing: bool
    skip_locked_segments: bool
    run_semantic_validation: bool
    glossary_snapshot_id: str
    provider_type: str = "OLLAMA"
    cloud_model_name: str | None = None
    cloud_consent: bool = False
    cloud_consent_version: str | None = None

    def __post_init__(self) -> None:
        _validate_identifier(self.project_id, "prj_")
        _validate_identifier(self.document_id, "doc_")
        _validate_identifiers(self.section_ids, "sec_")
        _validate_identifiers(self.page_ids, "pag_")
        _validate_identifiers(self.segment_ids, "seg_")
        _validate_identifier(self.glossary_snapshot_id, "gsn_")
        if self.provider_type not in _PROVIDER_TYPES:
            raise TranslationWorkerError("The translation command provider is invalid.")
        if self.provider_type == "OLLAMA":
            _validate_identifier(self.model_id, "mdl_")
            if (
                self.cloud_model_name is not None
                or self.cloud_consent
                or self.cloud_consent_version is not None
            ):
                raise TranslationWorkerError("The translation command provider fields conflict.")
        elif (
            self.model_id is not None
            or self.cloud_model_name not in GROQ_MODELS
            or self.cloud_consent is not True
            or self.cloud_consent_version != _CLOUD_CONSENT_VERSION
        ):
            raise TranslationWorkerError("The cloud translation snapshot is invalid.")
        if self.scope not in _TRANSLATION_SCOPES:
            raise TranslationWorkerError("The translation command scope is invalid.")
        if self.translation_style not in _TRANSLATION_STYLES:
            raise TranslationWorkerError("The translation command style is invalid.")
        if type(self.batch_size) is not int or not 1 <= self.batch_size <= 100:
            raise TranslationWorkerError("The translation command batch size is invalid.")
        if self.context_mode not in _CONTEXT_MODES:
            raise TranslationWorkerError("The translation command context mode is invalid.")
        for value in (
            self.retranslate_existing,
            self.skip_locked_segments,
            self.run_semantic_validation,
        ):
            if type(value) is not bool:
                raise TranslationWorkerError("The translation command flags are invalid.")
        _validate_scope_selectors(self)

    def to_payload(self) -> dict[str, object]:
        return {
            "schema": TRANSLATION_COMMAND_SCHEMA,
            "project_id": self.project_id,
            "document_id": self.document_id,
            "scope": self.scope,
            "section_ids": list(self.section_ids),
            "page_ids": list(self.page_ids),
            "segment_ids": list(self.segment_ids),
            "model_id": self.model_id,
            "translation_style": self.translation_style,
            "batch_size": self.batch_size,
            "context_mode": self.context_mode,
            "retranslate_existing": self.retranslate_existing,
            "skip_locked_segments": self.skip_locked_segments,
            "run_semantic_validation": self.run_semantic_validation,
            "glossary_snapshot_id": self.glossary_snapshot_id,
            "provider_type": self.provider_type,
            "cloud_model_name": self.cloud_model_name,
            "cloud_consent": self.cloud_consent,
            "cloud_consent_version": self.cloud_consent_version,
        }

    @classmethod
    def from_payload_json(cls, value: str) -> Self:
        payload = _decode_translation_command(value)
        schema = payload.get("schema")
        if schema == TRANSLATION_COMMAND_SCHEMA_V1:
            if frozenset(payload) != _COMMAND_FIELDS_V1:
                raise TranslationWorkerError("The translation command fields are invalid.")
        elif schema == TRANSLATION_COMMAND_SCHEMA:
            if frozenset(payload) != _COMMAND_FIELDS:
                raise TranslationWorkerError("The translation command fields are invalid.")
        else:
            raise TranslationWorkerError("The translation command schema is unsupported.")
        try:
            return cls(
                project_id=_string_value(payload, "project_id"),
                document_id=_string_value(payload, "document_id"),
                scope=_string_value(payload, "scope"),
                section_ids=_identifier_tuple(payload["section_ids"]),
                page_ids=_identifier_tuple(payload["page_ids"]),
                segment_ids=_identifier_tuple(payload["segment_ids"]),
                model_id=_optional_string_value(payload, "model_id"),
                translation_style=_string_value(payload, "translation_style"),
                batch_size=_integer_value(payload, "batch_size"),
                context_mode=_string_value(payload, "context_mode"),
                retranslate_existing=_boolean_value(payload, "retranslate_existing"),
                skip_locked_segments=_boolean_value(payload, "skip_locked_segments"),
                run_semantic_validation=_boolean_value(payload, "run_semantic_validation"),
                glossary_snapshot_id=_string_value(payload, "glossary_snapshot_id"),
                provider_type=(
                    _string_value(payload, "provider_type")
                    if schema == TRANSLATION_COMMAND_SCHEMA
                    else "OLLAMA"
                ),
                cloud_model_name=(
                    _optional_string_value(payload, "cloud_model_name")
                    if schema == TRANSLATION_COMMAND_SCHEMA
                    else None
                ),
                cloud_consent=(
                    _boolean_value(payload, "cloud_consent")
                    if schema == TRANSLATION_COMMAND_SCHEMA
                    else False
                ),
                cloud_consent_version=(
                    _optional_string_value(payload, "cloud_consent_version")
                    if schema == TRANSLATION_COMMAND_SCHEMA
                    else None
                ),
            )
        except (TypeError, KeyError):
            raise TranslationWorkerError("The translation command values are invalid.") from None


@dataclass(frozen=True, slots=True)
class LoadedTranslationJob:
    job_id: str
    idempotency_key: str
    project_id: str
    document_id: str
    ollama_model_name: str
    operation: TranslationOperation | None
    selected_segment_ids: tuple[str, ...]
    retry_count: int
    provider_type: str = "OLLAMA"
    cloud_consent: bool = False


class DatabaseTranslationOperationLoader:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        storage: LocalFileStorage,
    ) -> None:
        self._session_factory = session_factory
        self._storage = storage

    def load(self, job_id: str) -> LoadedTranslationJob:
        _validate_identifier(job_id, "job_")
        with self._session_factory() as session:
            return _load_translation_job(session, self._storage, job_id)


type _TranslationRow = tuple[
    DocumentSegment,
    DocumentBlock,
    DocumentPage,
    DocumentSection | None,
]


def _load_translation_job(
    session: Session,
    storage: LocalFileStorage,
    job_id: str,
) -> LoadedTranslationJob:
    job = session.get(ApplicationJob, job_id)
    if job is None or job.job_type != JobType.TRANSLATE_DOCUMENT.value:
        raise TranslationWorkerError("The translation job is unavailable.")
    if job.status not in {
        JobStatus.QUEUED.value,
        JobStatus.RETRYING.value,
        JobStatus.RUNNING.value,
    }:
        raise TranslationWorkerError("The translation job is not executable.")

    command = TranslationCommand.from_payload_json(job.payload_json)
    project = session.get(Project, command.project_id)
    document = session.get(Document, command.document_id)
    if (
        project is None
        or document is None
        or project.active_document_id != command.document_id
        or document.project_id != command.project_id
        or job.project_id != command.project_id
        or job.document_id != command.document_id
        or project.source_language != document.source_language
        or project.target_language != document.target_language
        or project.document_type != document.document_type
    ):
        raise TranslationWorkerError("The translation command state is inconsistent.")

    if command.provider_type == "OLLAMA":
        model = session.get(LocalModelRecord, command.model_id)
        if model is None or not model.is_installed:
            raise TranslationWorkerError("The translation model is unavailable.")
        provider_model_name = model.ollama_model_name
    else:
        assert command.cloud_model_name is not None
        provider_model_name = command.cloud_model_name
    if command.run_semantic_validation:
        raise TranslationWorkerError("Semantic validation is unavailable.")

    try:
        snapshot = load_glossary_snapshot(
            command.glossary_snapshot_id,
            session=session,
            storage=storage,
        )
    except GlossarySnapshotError as exc:
        raise TranslationWorkerError("The translation glossary snapshot is unavailable.") from exc
    if snapshot.project_id != command.project_id or snapshot.document_id != command.document_id:
        raise TranslationWorkerError("The translation command state is inconsistent.")

    rows = cast(
        tuple[_TranslationRow, ...],
        tuple(
            session.execute(
                select(DocumentSegment, DocumentBlock, DocumentPage, DocumentSection)
                .join(DocumentBlock, DocumentBlock.id == DocumentSegment.block_id)
                .join(DocumentPage, DocumentPage.id == DocumentBlock.page_id)
                .outerjoin(DocumentSection, DocumentSection.id == DocumentSegment.section_id)
                .where(DocumentPage.document_id == command.document_id)
                .order_by(
                    func.coalesce(DocumentSection.section_order, 0),
                    DocumentPage.source_page_number,
                    DocumentBlock.page_reading_order,
                    DocumentSegment.segment_order,
                    DocumentSegment.id,
                )
            ).all()
        ),
    )
    _validate_selector_membership(rows, command)
    selected = tuple(row for row in rows if _segment_selected(row[0], row[1], row[2], command))
    segment_ids = tuple(row[0].id for row in selected)
    operation = _build_translation_operation(
        job=job,
        project=project,
        command=command,
        snapshot_rules=snapshot.compiled.rules,
        rows=rows,
        selected=selected,
    )
    return LoadedTranslationJob(
        job_id=job.id,
        idempotency_key=job.idempotency_key,
        project_id=command.project_id,
        document_id=command.document_id,
        ollama_model_name=provider_model_name,
        operation=operation,
        selected_segment_ids=segment_ids,
        retry_count=job.retry_count,
        provider_type=command.provider_type,
        cloud_consent=command.cloud_consent,
    )


def _validate_selector_membership(
    rows: tuple[_TranslationRow, ...],
    command: TranslationCommand,
) -> None:
    requested: frozenset[str]
    available: frozenset[str]
    if command.scope == "SECTION":
        requested = frozenset(command.section_ids)
        available = frozenset(row[0].section_id for row in rows if row[0].section_id is not None)
    elif command.scope == "PAGE":
        requested = frozenset(command.page_ids)
        available = frozenset(row[2].id for row in rows)
    elif command.scope == "SELECTED_SEGMENTS":
        requested = frozenset(command.segment_ids)
        available = frozenset(row[0].id for row in rows)
    else:
        return
    if not requested.issubset(available):
        raise TranslationWorkerError("The translation command selector is unavailable.")


def _build_translation_operation(
    *,
    job: ApplicationJob,
    project: Project,
    command: TranslationCommand,
    snapshot_rules: tuple[CompiledGlossaryRule, ...],
    rows: tuple[_TranslationRow, ...],
    selected: tuple[_TranslationRow, ...],
) -> TranslationOperation | None:
    if not selected:
        return None
    title_text = {
        row[0].id: row[0].resolved_source_text.strip()
        for row in rows
        if row[0].resolved_source_text.strip()
    }
    segments = tuple(
        TranslationSegmentInput(
            segment_id=segment.id,
            source_text=segment.resolved_source_text,
            section_id=segment.section_id,
            section_order=section.section_order if section is not None else 0,
            page_order=page.source_page_number,
            block_order=block.page_reading_order,
            segment_order=segment.segment_order,
            context=_batch_context(index, selected, title_text, command.context_mode),
            locked=False,
            expected_revision=segment.current_revision,
        )
        for index, (segment, block, page, section) in enumerate(selected)
    )
    glossary = tuple(
        TranslationGlossaryEntry(
            source_term=rule.source_term,
            target_term=rule.target_term,
            rule_type=rule.rule_type.value,
        )
        for rule in snapshot_rules
    )
    return TranslationOperation(
        project_id=command.project_id,
        document_id=command.document_id,
        section_id=command.section_ids[0] if len(command.section_ids) == 1 else None,
        glossary_snapshot_id=command.glossary_snapshot_id,
        provider_type=command.provider_type,
        model_id=(command.model_id or command.cloud_model_name or ""),
        idempotency_key=(
            job.idempotency_key
            if job.retry_count == 0
            else f"{job.idempotency_key}:retry:{job.retry_count}"
        ),
        context=TranslationContext(
            source_language=project.source_language,
            target_language=project.target_language,
            document_type=project.document_type,
        ),
        segments=segments,
        glossary=glossary,
        style=TranslationStyle(command.translation_style),
        settings_json=json.dumps(
            command.to_payload(),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ),
        batch_limits=BatchLimits(max_segments=command.batch_size),
    )


def _batch_context(
    index: int,
    rows: tuple[_TranslationRow, ...],
    title_text: dict[str, str],
    context_mode: str,
) -> BatchContext:
    if context_mode == "NONE":
        return BatchContext()
    section = rows[index][3]
    heading = None
    if section is not None and section.title_segment_id is not None:
        heading = title_text.get(section.title_segment_id)
        if heading is not None:
            heading = heading[:500]
    radius = 1 if context_mode == "STANDARD" else 2
    previous = _joined_context(rows[max(0, index - radius) : index], from_end=True)
    following = _joined_context(rows[index + 1 : index + radius + 1], from_end=False)
    return BatchContext(heading=heading, previous_text=previous, next_text=following)


def _joined_context(rows: tuple[_TranslationRow, ...], *, from_end: bool) -> str | None:
    if not rows:
        return None
    value = "\n".join(row[0].resolved_source_text for row in rows).strip()
    if not value:
        return None
    return value[-2000:] if from_end else value[:2000]


def _segment_selected(
    segment: DocumentSegment,
    block: DocumentBlock,
    page: DocumentPage,
    command: TranslationCommand,
) -> bool:
    if segment.status in {
        SegmentStatus.IGNORED.value,
        SegmentStatus.NOT_TRANSLATABLE.value,
    }:
        return False
    if _segment_is_protected(segment):
        return False

    if command.scope == "SECTION" and segment.section_id not in command.section_ids:
        return False
    if command.scope == "PAGE" and page.id not in command.page_ids:
        return False
    if command.scope == "SELECTED_SEGMENTS" and segment.id not in command.segment_ids:
        return False
    if command.scope == "UNTRANSLATED_ONLY" and _has_existing_translation(segment):
        return False
    if command.scope == "UNREVIEWED_ONLY" and segment.review_status in {
        ReviewStatus.EDITED.value,
        ReviewStatus.APPROVED.value,
    }:
        return False

    return command.retranslate_existing or not _has_existing_translation(segment)


def _has_existing_translation(segment: DocumentSegment) -> bool:
    return any(
        value is not None and value.strip()
        for value in (
            segment.machine_translation,
            segment.reviewed_translation,
            segment.final_text,
        )
    )


def _segment_is_protected(segment: DocumentSegment) -> bool:
    return (
        bool(segment.is_locked)
        or segment.status
        in {
            SegmentStatus.LOCKED.value,
            SegmentStatus.APPROVED.value,
            SegmentStatus.USER_EDITED.value,
        }
        or segment.review_status in {ReviewStatus.APPROVED.value, ReviewStatus.EDITED.value}
    )


def _loaded_revisions(loaded: LoadedTranslationJob) -> dict[str, int | None]:
    return (
        {item.segment_id: item.expected_revision for item in loaded.operation.segments}
        if loaded.operation is not None
        else {}
    )


def _write_segment_status(
    session: Session,
    segment_id: str,
    revision: int | None,
    status: str,
    now: str,
    *,
    only_running: bool = True,
) -> bool:
    if revision is None:
        return False
    statement = update(DocumentSegment).where(
        DocumentSegment.id == segment_id,
        DocumentSegment.current_revision == revision,
        DocumentSegment.is_locked == 0,
        DocumentSegment.status.not_in(("LOCKED", "APPROVED", "USER_EDITED")),
        DocumentSegment.review_status.not_in(("APPROVED", "EDITED")),
    )
    if only_running:
        statement = statement.where(DocumentSegment.status == SegmentStatus.TRANSLATING.value)
    return (
        session.scalar(
            statement.values(status=status, updated_at=now).returning(DocumentSegment.id)
        )
        is not None
    )


def _decode_translation_command(value: str) -> dict[str, object]:
    if type(value) is not str or not value:
        raise TranslationWorkerError("The translation command JSON is invalid.")

    def decode_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, item in pairs:
            if key in result:
                raise TranslationWorkerError("The translation command fields are duplicated.")
            result[key] = item
        return result

    try:
        payload = json.loads(value, object_pairs_hook=decode_pairs)
    except (json.JSONDecodeError, TranslationWorkerError):
        raise TranslationWorkerError("The translation command JSON is invalid.") from None
    if not isinstance(payload, dict):
        raise TranslationWorkerError("The translation command must be a JSON object.")
    return payload


def _identifier_tuple(value: object) -> tuple[str, ...]:
    if type(value) is not list or any(type(item) is not str for item in value):
        raise TranslationWorkerError("The translation command selector values are invalid.")
    return tuple(value)


def _string_value(payload: dict[str, object], key: str) -> str:
    value = payload[key]
    if type(value) is not str:
        raise TranslationWorkerError("The translation command values are invalid.")
    return value


def _optional_string_value(payload: dict[str, object], key: str) -> str | None:
    value = payload[key]
    if value is not None and type(value) is not str:
        raise TranslationWorkerError("The translation command values are invalid.")
    return value


def _integer_value(payload: dict[str, object], key: str) -> int:
    value = payload[key]
    if type(value) is not int:
        raise TranslationWorkerError("The translation command values are invalid.")
    return value


def _boolean_value(payload: dict[str, object], key: str) -> bool:
    value = payload[key]
    if type(value) is not bool:
        raise TranslationWorkerError("The translation command values are invalid.")
    return value


def _validate_identifier(value: object, prefix: str) -> None:
    if type(value) is not str or not value.startswith(prefix):
        raise TranslationWorkerError("A translation command identifier is invalid.")
    try:
        identifier = UUID(value[len(prefix) :])
    except (ValueError, AttributeError):
        raise TranslationWorkerError("A translation command identifier is invalid.") from None
    if value != f"{prefix}{identifier}":
        raise TranslationWorkerError("A translation command identifier is invalid.")


def _validate_identifiers(values: object, prefix: str) -> None:
    if type(values) is not tuple or len(values) != len(set(values)):
        raise TranslationWorkerError("The translation command selectors are invalid.")
    for value in values:
        _validate_identifier(value, prefix)


def _validate_scope_selectors(command: TranslationCommand) -> None:
    populated = {
        "SECTION": bool(command.section_ids),
        "PAGE": bool(command.page_ids),
        "SELECTED_SEGMENTS": bool(command.segment_ids),
    }
    if command.scope in populated:
        if not populated[command.scope] or sum(populated.values()) != 1:
            raise TranslationWorkerError("The translation command selector is invalid.")
        return
    if any(populated.values()):
        raise TranslationWorkerError("The translation command selector is invalid.")


class DatabaseCancellationSignal:
    def __init__(
        self, session_factory: sessionmaker[Session], job_id: str, attempt_id: str | None = None
    ) -> None:
        self._session_factory = session_factory
        self._job_id = job_id
        self._attempt_id = attempt_id

    @property
    def is_cancelled(self) -> bool:
        with self._session_factory() as session:
            row = session.get(ApplicationJob, self._job_id)
            if row is None:
                raise TranslationWorkerError("The translation job was not found.")
            if self._attempt_id is not None:
                attempt = session.get(JobAttempt, self._attempt_id)
                if (
                    attempt is None
                    or attempt.status != JobAttemptStatus.RUNNING.value
                    or row.status not in {"RUNNING", "CANCELLATION_REQUESTED", "CANCELLED"}
                ):
                    raise TranslationWorkerError("The translation attempt no longer owns the job.")
            return row.status in {
                JobStatus.CANCELLATION_REQUESTED.value,
                JobStatus.CANCELLED.value,
            }


class ProductionTranslationJobRunner:
    def __init__(
        self,
        loader: DatabaseTranslationOperationLoader,
        session_factory: sessionmaker[Session],
        temporary_root: Path,
        *,
        provider_factory: Callable[[str], object] | None = None,
        cloud_provider_factory: Callable[[str, bool], object] | None = None,
        worker_identifier: str | None = None,
    ) -> None:
        if not isinstance(loader, DatabaseTranslationOperationLoader):
            raise ValueError("A database translation loader is required.")
        if not isinstance(temporary_root, Path) or not temporary_root.is_absolute():
            raise ValueError("The worker temporary root must be absolute.")
        self._loader = loader
        self._session_factory = session_factory
        self._temporary_root = temporary_root.resolve(strict=False)
        self._provider_factory = provider_factory or (
            lambda model_name: OllamaTranslationProvider(model_name=model_name)
        )
        self._cloud_provider_factory = cloud_provider_factory or (
            lambda model_name, consent: GroqTranslationProvider(
                enabled=True,
                cloud_consent=consent,
                model_name=model_name,
            )
        )
        self._worker_identifier = _worker_identifier(worker_identifier)

    def run(self, job_id: str) -> TranslationRunResult:
        loaded = self._loader.load(job_id)
        return _run_loaded_translation_job(
            loaded,
            session_factory=self._session_factory,
            temporary_root=self._temporary_root,
            provider_factory=self._provider_factory,
            cloud_provider_factory=self._cloud_provider_factory,
            worker_identifier=self._worker_identifier,
        )


def _run_loaded_translation_job(
    loaded: LoadedTranslationJob,
    *,
    session_factory: sessionmaker[Session],
    temporary_root: Path,
    provider_factory: Callable[[str], object],
    cloud_provider_factory: Callable[[str, bool], object] | None = None,
    worker_identifier: str,
) -> TranslationRunResult:
    attempt_id: str | None = None
    try:
        attempt_id = _start_translation_job(session_factory, loaded, worker_identifier)
        if loaded.operation is None:
            result = TranslationRunResult(
                run_id=str(uuid5(NAMESPACE_URL, f"transloka:translation-noop:{loaded.job_id}")),
                idempotency_key=loaded.idempotency_key,
                status=TranslationRunStatus.COMPLETED,
                completed_segment_ids=(),
                failed_segment_ids=(),
                locked_segment_ids=(),
                cancelled_segment_ids=(),
            )
        else:

            def guard(session: Session) -> None:
                _lock_translation_attempt(session, loaded.job_id, attempt_id)

            def report_progress(completed_batches: int, total_batches: int) -> None:
                ratio = completed_batches / total_batches if total_batches else 0.0
                with transaction_scope(session_factory) as session:
                    guard(session)
                    job = session.get(ApplicationJob, loaded.job_id)
                    assert job is not None
                    job.progress = min(0.99, max(0.0, ratio * 0.99))
                    job.current_stage = f"TRANSLATING_{completed_batches}_OF_{total_batches}"
                    job.result_json = json.dumps(
                        {
                            "schema": "transloka.translation.job-progress.v1",
                            "current_batch": completed_batches,
                            "total_batches": total_batches,
                        }
                    )
                    job.heartbeat_at = _translation_timestamp()

            orchestrator = TranslationOrchestrator(
                _translation_provider(
                    loaded,
                    provider_factory=provider_factory,
                    cloud_provider_factory=cloud_provider_factory,
                ),
                SqlAlchemyTranslationRunStore(session_factory, write_guard=guard),
                batch_progress_sink=report_progress,
            )
            result = asyncio.run(
                orchestrator.run(
                    loaded.operation,
                    cancellation=DatabaseCancellationSignal(
                        session_factory, loaded.job_id, attempt_id
                    ),
                )
            )
        _finish_translation_job(session_factory, loaded, result, worker_identifier, attempt_id)
        return result
    except Exception as exc:
        _fail_translation_job(session_factory, loaded, exc, worker_identifier, attempt_id)
        raise


class _CloudEnabledProvider:
    def __init__(self, provider: Any) -> None:
        self._provider = provider

    async def translate(self, request: object, *, cancellation: object = None) -> object:
        if not _cloud_translation_enabled():
            raise TranslationProviderError(
                ProviderErrorCode.INVALID_REQUEST,
                "Cloud translation was disabled before the request.",
            )
        return await self._provider.translate(request, cancellation=cancellation)


def _translation_provider(
    loaded: LoadedTranslationJob,
    *,
    provider_factory: Callable[[str], object],
    cloud_provider_factory: Callable[[str, bool], object] | None,
) -> object:
    if loaded.provider_type == "OLLAMA":
        return provider_factory(loaded.ollama_model_name)
    factory = cloud_provider_factory or (
        lambda model_name, consent: GroqTranslationProvider(
            enabled=True,
            cloud_consent=consent,
            model_name=model_name,
        )
    )
    return _CloudEnabledProvider(factory(loaded.ollama_model_name, loaded.cloud_consent))


def _cloud_translation_enabled() -> bool:
    return os.environ.get("TRANSLOKA_CLOUD_TRANSLATION_ENABLED", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _lock_translation_attempt(
    session: Session, job_id: str, attempt_id: str | None, *, allow_cancelled: bool = False
) -> None:
    statuses = [JobStatus.RUNNING.value, JobStatus.CANCELLATION_REQUESTED.value]
    if allow_cancelled:
        statuses.append(JobStatus.CANCELLED.value)
    # The no-op UPDATE acquires SQLite's writer lock before any dependent write.
    # Checking the attempt token also fences a stale worker after a job is retried.
    owned = session.scalar(
        update(ApplicationJob)
        .where(
            ApplicationJob.id == job_id,
            ApplicationJob.status.in_(statuses),
            select(JobAttempt.id)
            .where(
                JobAttempt.id == attempt_id,
                JobAttempt.job_id == job_id,
                JobAttempt.status == JobAttemptStatus.RUNNING.value,
            )
            .exists(),
        )
        .values(heartbeat_at=ApplicationJob.heartbeat_at)
        .returning(ApplicationJob.id)
    )
    if owned is None:
        raise TranslationWorkerError("The translation attempt no longer owns the job.")


def _worker_identifier(value: str | None) -> str:
    candidate = (
        value or os.environ.get("COMPUTERNAME") or os.environ.get("HOSTNAME") or "transloka-worker"
    )
    normalized = candidate.strip()
    if not normalized or not normalized.isprintable() or len(normalized) > 200:
        return "transloka-worker"
    return normalized


def _start_translation_job(
    session_factory: sessionmaker[Session],
    loaded: LoadedTranslationJob,
    worker_identifier: str,
) -> str:
    now = _translation_timestamp()
    revisions = _loaded_revisions(loaded)
    with transaction_scope(session_factory) as session:
        job = session.get(ApplicationJob, loaded.job_id)
        project = session.get(Project, loaded.project_id)
        document = session.get(Document, loaded.document_id)
        if job is None or project is None or document is None:
            raise TranslationWorkerError("The translation lifecycle state is unavailable.")
        attempts = list(
            session.scalars(
                select(JobAttempt)
                .where(JobAttempt.job_id == loaded.job_id)
                .order_by(JobAttempt.attempt_number)
            )
        )
        retry_attempt = (
            attempts[-1]
            if job.status == JobStatus.RETRYING.value
            and attempts
            and attempts[-1].status == JobAttemptStatus.RUNNING.value
            and attempts[-1].worker_identifier is None
            else None
        )
        ownership_predicate = (
            select(JobAttempt.id)
            .where(
                JobAttempt.id == retry_attempt.id,
                JobAttempt.job_id == loaded.job_id,
                JobAttempt.status == JobAttemptStatus.RUNNING.value,
                JobAttempt.worker_identifier.is_(None),
            )
            .exists()
            if retry_attempt is not None
            else ~select(JobAttempt.id)
            .where(
                JobAttempt.job_id == loaded.job_id,
                JobAttempt.status == JobAttemptStatus.RUNNING.value,
            )
            .exists()
        )
        claimed = session.scalar(
            update(ApplicationJob)
            .where(
                ApplicationJob.id == loaded.job_id,
                ApplicationJob.retry_count == loaded.retry_count,
                ApplicationJob.status.in_(("QUEUED", "RETRYING", "RUNNING")),
                ownership_predicate,
            )
            .values(status=JobStatus.RUNNING.value)
            .returning(ApplicationJob.id)
        )
        if claimed is None:
            raise TranslationWorkerError(
                "The translation job is already owned or no longer executable."
            )
        statuses: dict[str, str] = {}
        for segment_id in loaded.selected_segment_ids:
            segment = session.get(DocumentSegment, segment_id)
            if segment is None:
                raise TranslationWorkerError("A selected translation segment disappeared.")
            statuses[segment_id] = segment.status
        details_value: dict[str, object] = {
            "schema": "transloka.translation.attempt-state.v1",
            "document_status": document.status,
            "project_status": project.status,
            "segment_statuses": statuses,
        }
        if retry_attempt is not None and retry_attempt.details_json:
            try:
                retry_details = json.loads(retry_attempt.details_json)
            except (TypeError, ValueError):
                retry_details = None
            if isinstance(retry_details, dict) and isinstance(retry_details.get("retry"), dict):
                details_value["retry"] = retry_details["retry"]
        details = json.dumps(
            details_value,
            sort_keys=True,
            separators=(",", ":"),
        )
        if retry_attempt is not None:
            attempt = retry_attempt
            attempt.worker_identifier = worker_identifier
            attempt.started_at = now
            attempt.details_json = details
        else:
            attempt_number = len(attempts) + 1
            attempt = JobAttempt(
                id=str(
                    uuid5(
                        NAMESPACE_URL,
                        f"transloka:translation-attempt:{loaded.job_id}:{attempt_number}",
                    )
                ),
                job_id=loaded.job_id,
                attempt_number=attempt_number,
                status=JobAttemptStatus.RUNNING.value,
                worker_identifier=worker_identifier,
                started_at=now,
                completed_at=None,
                duration_ms=None,
                error_code=None,
                error_message=None,
                details_json=details,
            )
            session.add(attempt)
        job.status = JobStatus.RUNNING.value
        job.progress = 0.0
        job.result_json = None
        job.current_stage = "TRANSLATING"
        job.started_at = job.started_at or now
        job.heartbeat_at = now
        project.status = ProjectStatus.TRANSLATING.value
        project.progress = 0.0
        project.updated_at = now
        document.status = DocumentStatus.TRANSLATING.value
        document.updated_at = now
        for segment_id in loaded.selected_segment_ids:
            if not _write_segment_status(
                session,
                segment_id,
                revisions.get(segment_id),
                SegmentStatus.TRANSLATING.value,
                now,
                only_running=False,
            ):
                raise TranslationWorkerError("A selected translation segment changed before start.")
        session.flush()
        return attempt.id


def _finish_translation_job(
    session_factory: sessionmaker[Session],
    loaded: LoadedTranslationJob,
    result: TranslationRunResult,
    worker_identifier: str,
    attempt_id: str,
) -> None:
    now = _translation_timestamp()
    revisions = _loaded_revisions(loaded)
    job_status = _translation_job_status(result.status)
    result_json = _translation_result_json(result)
    with transaction_scope(session_factory) as session:
        _lock_translation_attempt(session, loaded.job_id, attempt_id, allow_cancelled=True)
        job = session.get(ApplicationJob, loaded.job_id)
        project = session.get(Project, loaded.project_id)
        document = session.get(Document, loaded.document_id)
        if job is None or project is None or document is None:
            raise TranslationWorkerError("The translation lifecycle state disappeared.")
        attempt = session.get(JobAttempt, attempt_id)
        assert attempt is not None
        previous = _attempt_state(attempt)
        progress = _terminal_progress(result, len(loaded.selected_segment_ids))
        job.status = job_status.value
        job.progress = progress
        job.current_stage = job_status.value
        terminal_result = json.loads(result_json)
        batch_progress = json.loads(job.result_json) if job.result_json else {}
        if isinstance(batch_progress, dict):
            for key in ("current_batch", "total_batches"):
                if key in batch_progress:
                    terminal_result[key] = batch_progress[key]
        job.result_json = json.dumps(terminal_result, sort_keys=True, separators=(",", ":"))
        job.completed_at = now
        job.heartbeat_at = now
        if job_status is JobStatus.CANCELLED:
            job.cancelled_at = job.cancelled_at or now
        error_code, error_message = _translation_result_error(result)
        job.error_code = error_code
        job.error_message = error_message
        project.status = _translation_project_status(job_status).value
        project.progress = progress
        project.updated_at = now
        document.status = _translation_document_status(
            job_status,
            previous.get("document_status"),
        ).value
        document.updated_at = now
        failed_ids = set(result.failed_segment_ids)
        cancelled_ids = set(result.cancelled_segment_ids)
        unattempted_ids = set(result.unattempted_segment_ids)
        previous_segments = previous.get("segment_statuses", {})
        for segment_id in failed_ids:
            _write_segment_status(
                session,
                segment_id,
                revisions.get(segment_id),
                SegmentStatus.TRANSLATION_FAILED.value,
                now,
            )
        if isinstance(previous_segments, dict):
            for segment_id in cancelled_ids | unattempted_ids:
                old_status = previous_segments.get(segment_id)
                if isinstance(old_status, str):
                    _write_segment_status(
                        session,
                        segment_id,
                        revisions.get(segment_id),
                        old_status,
                        now,
                    )
        _complete_translation_attempt(
            attempt,
            job_status,
            now,
            worker_identifier,
            error_code,
            error_message,
        )
        session.flush()


def _fail_translation_job(
    session_factory: sessionmaker[Session],
    loaded: LoadedTranslationJob,
    error: Exception,
    worker_identifier: str,
    attempt_id: str | None,
) -> None:
    now = _translation_timestamp()
    revisions = _loaded_revisions(loaded)
    error_code = type(error).__name__.upper()[:100] or "TRANSLATIONWORKERERROR"
    raw_message = str(error).strip()
    error_message = (
        raw_message[:500]
        if raw_message and raw_message.isprintable()
        else "Translation job failed."
    )
    try:
        with transaction_scope(session_factory) as session:
            if attempt_id is None:
                unclaimed = session.scalar(
                    update(ApplicationJob)
                    .where(
                        ApplicationJob.id == loaded.job_id,
                        ApplicationJob.retry_count == loaded.retry_count,
                        ApplicationJob.status.in_(("QUEUED", "RETRYING")),
                        ~select(JobAttempt.id)
                        .where(
                            JobAttempt.job_id == loaded.job_id,
                            JobAttempt.status == "RUNNING",
                        )
                        .exists(),
                    )
                    .values(status=JobStatus.FAILED.value)
                    .returning(ApplicationJob.id)
                )
                if unclaimed is None:
                    return
            else:
                _lock_translation_attempt(session, loaded.job_id, attempt_id)
            job = session.get(ApplicationJob, loaded.job_id)
            if job is None:
                return
            attempt = session.get(JobAttempt, attempt_id) if attempt_id is not None else None
            previous = _attempt_state(attempt) if attempt is not None else {}
            job.status = JobStatus.FAILED.value
            job.current_stage = JobStatus.FAILED.value
            job.error_code = error_code
            job.error_message = error_message
            job.completed_at = now
            job.heartbeat_at = now
            project = session.get(Project, loaded.project_id)
            if project is not None:
                project.status = ProjectStatus.FAILED.value
                project.updated_at = now
            document = session.get(Document, loaded.document_id)
            if document is not None:
                document.status = DocumentStatus.FAILED.value
                document.updated_at = now
            previous_segments = previous.get("segment_statuses", {})
            if isinstance(previous_segments, dict):
                for segment_id, old_status in previous_segments.items():
                    if isinstance(old_status, str):
                        _write_segment_status(
                            session,
                            segment_id,
                            revisions.get(segment_id),
                            old_status,
                            now,
                        )
            if attempt is not None:
                _complete_translation_attempt(
                    attempt,
                    JobStatus.FAILED,
                    now,
                    worker_identifier,
                    error_code,
                    error_message,
                )
            session.flush()
    except Exception:
        return


def _attempt_state(attempt: JobAttempt | None) -> dict[str, object]:
    if attempt is None or attempt.details_json is None:
        return {}
    try:
        payload = json.loads(attempt.details_json)
    except (TypeError, ValueError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _complete_translation_attempt(
    attempt: JobAttempt,
    status: JobStatus,
    completed_at: str,
    worker_identifier: str,
    error_code: str | None,
    error_message: str | None,
) -> None:
    attempt.status = _translation_attempt_status(status).value
    attempt.completed_at = completed_at
    attempt.worker_identifier = worker_identifier
    attempt.error_code = error_code
    attempt.error_message = error_message


def _translation_job_status(status: TranslationRunStatus) -> JobStatus:
    return {
        TranslationRunStatus.COMPLETED: JobStatus.COMPLETED,
        TranslationRunStatus.COMPLETED_WITH_WARNINGS: JobStatus.COMPLETED_WITH_WARNINGS,
        TranslationRunStatus.PARTIALLY_COMPLETED: JobStatus.PARTIALLY_COMPLETED,
        TranslationRunStatus.FAILED: JobStatus.FAILED,
        TranslationRunStatus.CANCELLED: JobStatus.CANCELLED,
    }[status]


def _translation_attempt_status(status: JobStatus) -> JobAttemptStatus:
    return {
        JobStatus.COMPLETED: JobAttemptStatus.COMPLETED,
        JobStatus.COMPLETED_WITH_WARNINGS: JobAttemptStatus.COMPLETED_WITH_WARNINGS,
        JobStatus.PARTIALLY_COMPLETED: JobAttemptStatus.PARTIALLY_COMPLETED,
        JobStatus.FAILED: JobAttemptStatus.FAILED,
        JobStatus.CANCELLED: JobAttemptStatus.CANCELLED,
    }[status]


def _translation_project_status(status: JobStatus) -> ProjectStatus:
    return {
        JobStatus.COMPLETED: ProjectStatus.READY_FOR_REVIEW,
        JobStatus.COMPLETED_WITH_WARNINGS: ProjectStatus.READY_FOR_REVIEW,
        JobStatus.PARTIALLY_COMPLETED: ProjectStatus.PARTIALLY_COMPLETED,
        JobStatus.FAILED: ProjectStatus.FAILED,
        JobStatus.CANCELLED: ProjectStatus.CANCELLED,
    }[status]


def _translation_document_status(
    status: JobStatus,
    previous_status: object,
) -> DocumentStatus:
    if status in {JobStatus.COMPLETED, JobStatus.COMPLETED_WITH_WARNINGS}:
        return DocumentStatus.TRANSLATED
    if status is JobStatus.PARTIALLY_COMPLETED:
        return DocumentStatus.PARTIALLY_TRANSLATED
    if status is JobStatus.FAILED:
        return DocumentStatus.FAILED
    if not isinstance(previous_status, str):
        return DocumentStatus.READY_FOR_TRANSLATION
    try:
        return DocumentStatus(previous_status)
    except ValueError:
        return DocumentStatus.READY_FOR_TRANSLATION


def _terminal_progress(result: TranslationRunResult, selected_count: int) -> float:
    if result.status in {
        TranslationRunStatus.COMPLETED,
        TranslationRunStatus.COMPLETED_WITH_WARNINGS,
    }:
        return 1.0
    return len(result.completed_segment_ids) / selected_count if selected_count else 1.0


def _translation_result_error(
    result: TranslationRunResult,
) -> tuple[str | None, str | None]:
    if result.provider_error_code is not None:
        return (
            result.provider_error_code,
            "Translation stopped because the configured provider is unavailable.",
        )
    if not result.failures:
        return None, None
    return (
        "TRANSLATION_SEGMENT_FAILED",
        f"{len(result.failed_segment_ids)} translation segment(s) failed.",
    )


def _translation_result_json(result: TranslationRunResult) -> str:
    return json.dumps(
        {
            "schema": "transloka.translation.job-result.v1",
            "run_id": result.run_id,
            "status": result.status.value,
            "completed_segment_ids": list(result.completed_segment_ids),
            "failed_segment_ids": list(result.failed_segment_ids),
            "locked_segment_ids": list(result.locked_segment_ids),
            "cancelled_segment_ids": list(result.cancelled_segment_ids),
            "unattempted_segment_ids": list(result.unattempted_segment_ids),
            "warning_count": len(result.warnings),
            "failures": [
                {
                    "segment_id": failure.segment_id,
                    "code": failure.code,
                    **(
                        {"validation_codes": [code.value for code in failure.validation_codes]}
                        if failure.validation_codes
                        else {}
                    ),
                }
                for failure in result.failures
            ],
            "attempt_count": result.attempt_count,
            **(
                {"provider_error_code": result.provider_error_code}
                if result.provider_error_code is not None
                else {}
            ),
            **(
                {"retry_after_seconds": result.retry_after_seconds}
                if result.retry_after_seconds is not None
                else {}
            ),
        },
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    )


def _translation_timestamp() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


class TranslationJobRunner:
    """Small worker boundary that keeps queue concerns separate from the pipeline."""

    def __init__(
        self,
        orchestrator: TranslationOrchestrator,
        operation_loader: Callable[[str], TranslationOperation],
    ) -> None:
        self._orchestrator = orchestrator
        self._operation_loader = operation_loader

    def run(self, job_id: str) -> TranslationRunResult:
        if type(job_id) is not str or not job_id.strip():
            raise ValueError("job_id must be a non-empty string.")
        operation = self._operation_loader(job_id)
        if not isinstance(operation, TranslationOperation):
            raise TypeError("operation_loader must return TranslationOperation.")
        return asyncio.run(self._orchestrator.run(operation))


def run_translation_job(
    job_id: str,
    *,
    orchestrator: TranslationOrchestrator,
    operation_loader: Callable[[str], TranslationOperation],
) -> TranslationRunResult:
    return TranslationJobRunner(orchestrator, operation_loader).run(job_id)


def create_translation_task(
    *,
    orchestrator: TranslationOrchestrator,
    operation_loader: Callable[[str], TranslationOperation],
) -> Callable[[str], TranslationRunResult]:
    runner = TranslationJobRunner(orchestrator, operation_loader)
    return runner.run
