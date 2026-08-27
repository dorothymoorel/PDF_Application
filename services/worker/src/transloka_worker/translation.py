from __future__ import annotations

import asyncio
import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Self, cast
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session, sessionmaker
from transloka_core.database.models.document_ir import (
    DocumentBlock,
    DocumentSection,
    DocumentSegment,
    ReviewStatus,
    SegmentStatus,
)
from transloka_core.database.models.documents import Document
from transloka_core.database.models.jobs import ApplicationJob, JobStatus, JobType
from transloka_core.database.models.models import LocalModelRecord
from transloka_core.database.models.pages import DocumentPage
from transloka_core.database.models.projects import Project
from transloka_core.storage.local import LocalFileStorage
from transloka_glossary.snapshots import (
    CompiledGlossaryRule,
    GlossarySnapshotError,
    load_glossary_snapshot,
)
from transloka_translation.batching import BatchContext, BatchLimits
from transloka_translation.orchestration import (
    TranslationOperation,
    TranslationOrchestrator,
    TranslationRunResult,
    TranslationSegmentInput,
)
from transloka_translation.schemas import (
    TranslationContext,
    TranslationGlossaryEntry,
    TranslationStyle,
)

TRANSLATION_COMMAND_SCHEMA = "transloka.translation.command.v1"
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
_COMMAND_FIELDS = frozenset(
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
    model_id: str
    translation_style: str
    batch_size: int
    context_mode: str
    retranslate_existing: bool
    skip_locked_segments: bool
    run_semantic_validation: bool
    glossary_snapshot_id: str

    def __post_init__(self) -> None:
        _validate_identifier(self.project_id, "prj_")
        _validate_identifier(self.document_id, "doc_")
        _validate_identifiers(self.section_ids, "sec_")
        _validate_identifiers(self.page_ids, "pag_")
        _validate_identifiers(self.segment_ids, "seg_")
        _validate_identifier(self.model_id, "mdl_")
        _validate_identifier(self.glossary_snapshot_id, "gsn_")
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
        }

    @classmethod
    def from_payload_json(cls, value: str) -> Self:
        payload = _decode_translation_command(value)
        if frozenset(payload) != _COMMAND_FIELDS:
            raise TranslationWorkerError("The translation command fields are invalid.")
        if payload["schema"] != TRANSLATION_COMMAND_SCHEMA:
            raise TranslationWorkerError("The translation command schema is unsupported.")
        try:
            return cls(
                project_id=_string_value(payload, "project_id"),
                document_id=_string_value(payload, "document_id"),
                scope=_string_value(payload, "scope"),
                section_ids=_identifier_tuple(payload["section_ids"]),
                page_ids=_identifier_tuple(payload["page_ids"]),
                segment_ids=_identifier_tuple(payload["segment_ids"]),
                model_id=_string_value(payload, "model_id"),
                translation_style=_string_value(payload, "translation_style"),
                batch_size=_integer_value(payload, "batch_size"),
                context_mode=_string_value(payload, "context_mode"),
                retranslate_existing=_boolean_value(payload, "retranslate_existing"),
                skip_locked_segments=_boolean_value(payload, "skip_locked_segments"),
                run_semantic_validation=_boolean_value(payload, "run_semantic_validation"),
                glossary_snapshot_id=_string_value(payload, "glossary_snapshot_id"),
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

    model = session.get(LocalModelRecord, command.model_id)
    if model is None or not model.is_installed:
        raise TranslationWorkerError("The translation model is unavailable.")
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
        ollama_model_name=model.ollama_model_name,
        operation=operation,
        selected_segment_ids=segment_ids,
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
        provider_type="OLLAMA",
        model_id=command.model_id,
        idempotency_key=job.idempotency_key,
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
    is_locked = bool(segment.is_locked) or segment.status == SegmentStatus.LOCKED.value
    if is_locked and (command.skip_locked_segments or not command.retranslate_existing):
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
