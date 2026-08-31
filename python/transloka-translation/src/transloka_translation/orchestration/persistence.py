from __future__ import annotations

import hashlib
import json
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Protocol, cast
from uuid import uuid4

from transloka_translation.batching import TranslationBatch
from transloka_translation.validation import (
    ValidationCode,
    ValidationIssue,
    ValidationReport,
    ValidationSeverity,
)

from .models import TranslationOperation, TranslationRunStatus

_VALIDATOR_TYPE_BY_VALIDATION_CODE: dict[ValidationCode, str] = {
    ValidationCode.SEGMENT_MAPPING_MISMATCH: "SEGMENT_MAPPING",
    ValidationCode.PLACEHOLDER_MISMATCH: "PLACEHOLDER_INTEGRITY",
    ValidationCode.NUMBER_MISMATCH: "NUMERICAL_INTEGRITY",
    ValidationCode.URL_MISMATCH: "URL_INTEGRITY",
    ValidationCode.CODE_MISMATCH: "CODE_INTEGRITY",
    ValidationCode.CITATION_MISMATCH: "CITATION_INTEGRITY",
    ValidationCode.TARGET_LANGUAGE_MISMATCH: "LANGUAGE",
    ValidationCode.EMPTY_TRANSLATION: "SEMANTIC",
    ValidationCode.SUSPICIOUS_LENGTH: "LENGTH_RATIO",
    ValidationCode.NEGATION_MISMATCH: "SEMANTIC",
}


def operation_fingerprint(operation: TranslationOperation) -> str:
    payload = {
        "project_id": operation.project_id,
        "document_id": operation.document_id,
        "section_id": operation.section_id,
        "glossary_snapshot_id": operation.glossary_snapshot_id,
        "provider_type": operation.provider_type,
        "model_id": operation.model_id,
        "idempotency_key": operation.idempotency_key,
        "context": operation.context.to_dict(),
        "segments": [
            {
                "segment_id": segment.segment_id,
                "source_text": segment.source_text,
                "section_id": segment.section_id,
                "section_order": segment.section_order,
                "page_order": segment.page_order,
                "block_order": segment.block_order,
                "segment_order": segment.segment_order,
                "locked": segment.locked,
            }
            for segment in operation.segments
        ],
        "glossary": [entry.to_dict() for entry in operation.glossary],
        "style": operation.style.value,
        "prompt_version": operation.prompt_version,
        "pipeline_version": operation.pipeline_version,
        "settings_json": operation.settings_json,
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class StoredRun:
    run_id: str
    idempotency_key: str
    fingerprint: str
    status: TranslationRunStatus


@dataclass(frozen=True, slots=True)
class StoredAttempt:
    attempt_id: str
    attempt_number: int
    status: str
    segment_ids: tuple[str, ...]
    error_code: str | None = None
    error_message: str | None = None


@dataclass(frozen=True, slots=True)
class StoredSegmentResult:
    segment_id: str
    translated_text_raw: str
    translated_text_restored: str
    validation_status: str
    validation_issues: tuple[str, ...]


class TranslationRunStore(Protocol):
    def find_by_idempotency_key(self, key: str) -> StoredRun | None: ...

    def create_run(
        self,
        operation: TranslationOperation,
        fingerprint: str,
        eligible_segment_ids: Iterable[str],
    ) -> StoredRun: ...

    def record_attempt(
        self,
        run: StoredRun,
        attempt_number: int,
        batch: TranslationBatch,
        *,
        status: str,
        error_code: str | None = None,
        error_message: str | None = None,
    ) -> StoredAttempt: ...

    def record_result(
        self,
        attempt: StoredAttempt,
        segment_id: str,
        translated_text_raw: str,
        translated_text_restored: str,
        report: ValidationReport,
    ) -> StoredSegmentResult: ...

    def finish_run(self, run: StoredRun, status: TranslationRunStatus) -> StoredRun: ...


@dataclass(slots=True)
class InMemoryTranslationRunStore:
    runs: dict[str, StoredRun] = field(default_factory=dict)
    runs_by_key: dict[str, StoredRun] = field(default_factory=dict)
    attempts: list[StoredAttempt] = field(default_factory=list)
    results: list[StoredSegmentResult] = field(default_factory=list)

    def find_by_idempotency_key(self, key: str) -> StoredRun | None:
        return self.runs_by_key.get(key)

    def create_run(
        self,
        operation: TranslationOperation,
        fingerprint: str,
        eligible_segment_ids: Iterable[str],
    ) -> StoredRun:
        del eligible_segment_ids
        existing = self.find_by_idempotency_key(operation.idempotency_key)
        if existing is not None:
            return existing
        run = StoredRun(
            run_id=f"tbt_{uuid4()}",
            idempotency_key=operation.idempotency_key,
            fingerprint=fingerprint,
            status=TranslationRunStatus.CREATED,
        )
        self.runs[run.run_id] = run
        self.runs_by_key[run.idempotency_key] = run
        return run

    def record_attempt(
        self,
        run: StoredRun,
        attempt_number: int,
        batch: TranslationBatch,
        *,
        status: str,
        error_code: str | None = None,
        error_message: str | None = None,
    ) -> StoredAttempt:
        attempt = StoredAttempt(
            attempt_id=f"tat_{uuid4()}",
            attempt_number=attempt_number,
            status=status,
            segment_ids=batch.segment_ids,
            error_code=error_code,
            error_message=error_message,
        )
        self.attempts.append(attempt)
        return attempt

    def record_result(
        self,
        attempt: StoredAttempt,
        segment_id: str,
        translated_text_raw: str,
        translated_text_restored: str,
        report: ValidationReport,
    ) -> StoredSegmentResult:
        del attempt
        result = StoredSegmentResult(
            segment_id=segment_id,
            translated_text_raw=translated_text_raw,
            translated_text_restored=translated_text_restored,
            validation_status=("PASSED_WITH_WARNINGS" if report.warnings else "PASSED"),
            validation_issues=tuple(issue.code.value for issue in report.issues),
        )
        self.results.append(result)
        return result

    def finish_run(self, run: StoredRun, status: TranslationRunStatus) -> StoredRun:
        updated = StoredRun(run.run_id, run.idempotency_key, run.fingerprint, status)
        self.runs[run.run_id] = updated
        self.runs_by_key[run.idempotency_key] = updated
        return updated


class IdempotencyConflictError(RuntimeError):
    """Raised when an idempotency key is reused for different source data."""


class SqlAlchemyTranslationRunStore:
    """SQLAlchemy persistence adapter for the M7 translation tables."""

    def __init__(self, session_factory: Any) -> None:
        self._session_factory = session_factory
        self._run_metadata: dict[str, tuple[str, str]] = {}

    def find_by_idempotency_key(self, key: str) -> StoredRun | None:
        from sqlalchemy import select
        from transloka_core.database.models.translation import (
            TranslationBatch,
        )

        with self._session_factory() as session:
            row = session.scalar(
                select(TranslationBatch).where(TranslationBatch.idempotency_key == key)
            )
            if row is None:
                return None
            fingerprint = ""
            try:
                settings = json.loads(row.settings_json)
                if isinstance(settings, dict):
                    fingerprint = str(settings.get("_operation_fingerprint", ""))
            except (TypeError, ValueError):
                pass
            return StoredRun(
                row.id, row.idempotency_key, fingerprint, TranslationRunStatus(row.status)
            )

    def create_run(
        self,
        operation: TranslationOperation,
        fingerprint: str,
        eligible_segment_ids: Iterable[str],
    ) -> StoredRun:
        from transloka_core.database import transaction_scope
        from transloka_core.database.models.translation import (
            TranslationBatch,
            TranslationBatchSegment,
            TranslationBatchStatus,
        )

        existing = self.find_by_idempotency_key(operation.idempotency_key)
        if existing is not None:
            return existing
        segment_ids = tuple(eligible_segment_ids)
        now = _now()
        run = StoredRun(
            run_id=f"tbt_{uuid4()}",
            idempotency_key=operation.idempotency_key,
            fingerprint=fingerprint,
            status=TranslationRunStatus.CREATED,
        )
        with transaction_scope(self._session_factory) as session:
            settings = _settings_with_fingerprint(operation.settings_json, fingerprint)
            session.add(
                TranslationBatch(
                    id=run.run_id,
                    project_id=operation.project_id,
                    document_id=operation.document_id,
                    section_id=operation.section_id,
                    glossary_snapshot_id=operation.glossary_snapshot_id,
                    provider_type=operation.provider_type,
                    model_id=operation.model_id,
                    prompt_version=operation.prompt_version,
                    pipeline_version=operation.pipeline_version,
                    status=TranslationBatchStatus.CREATED.value,
                    segment_count=len(segment_ids),
                    source_character_count=sum(
                        len(segment.source_text)
                        for segment in operation.segments
                        if not segment.locked
                    ),
                    estimated_input_tokens=None,
                    actual_input_tokens=None,
                    actual_output_tokens=None,
                    batch_order=operation.batch_order,
                    idempotency_key=operation.idempotency_key,
                    settings_json=settings,
                    created_at=now,
                )
            )
            for order, segment_id in enumerate(segment_ids):
                session.add(
                    TranslationBatchSegment(
                        batch_id=run.run_id,
                        segment_id=segment_id,
                        segment_order=order,
                    )
                )
        self._run_metadata[run.run_id] = (operation.provider_type, operation.model_id)
        return run

    def record_attempt(
        self,
        run: StoredRun,
        attempt_number: int,
        batch: TranslationBatch,
        *,
        status: str,
        error_code: str | None = None,
        error_message: str | None = None,
    ) -> StoredAttempt:
        from transloka_core.database import transaction_scope
        from transloka_core.database.models.translation import TranslationAttempt

        attempt = StoredAttempt(
            attempt_id=f"tat_{uuid4()}",
            attempt_number=attempt_number,
            status=status,
            segment_ids=batch.segment_ids,
            error_code=error_code,
            error_message=error_message,
        )
        with transaction_scope(self._session_factory) as session:
            provider_type, model_id = self._run_metadata.get(
                run.run_id, ("translation", "translation")
            )
            session.add(
                TranslationAttempt(
                    id=attempt.attempt_id,
                    batch_id=run.run_id,
                    attempt_number=attempt_number,
                    provider_type=provider_type,
                    model_id=model_id,
                    status=status,
                    request_hash=hashlib.sha256(",".join(batch.segment_ids).encode()).hexdigest(),
                    response_hash=None,
                    latency_ms=None,
                    input_tokens=None,
                    output_tokens=None,
                    retry_reason=None,
                    error_code=error_code,
                    error_message=error_message,
                    provider_metadata_json=None,
                    created_at=_now(),
                    completed_at=_now(),
                )
            )
        return attempt

    def record_result(
        self,
        attempt: StoredAttempt,
        segment_id: str,
        translated_text_raw: str,
        translated_text_restored: str,
        report: ValidationReport,
    ) -> StoredSegmentResult:
        from transloka_core.database import transaction_scope
        from transloka_core.database.models.document_ir import (
            DocumentSegment,
            ReviewStatus,
            SegmentStatus,
        )
        from transloka_core.database.models.translation import (
            SegmentTranslation,
            SegmentTranslationStatus,
            TranslationValidation,
            TranslationValidationStatus,
        )

        result_id = str(uuid4())
        validation_status = (
            TranslationValidationStatus.PASSED_WITH_WARNINGS.value
            if report.warnings
            else TranslationValidationStatus.PASSED.value
        )
        with transaction_scope(self._session_factory) as session:
            segment = session.get(DocumentSegment, segment_id)
            if segment is None:
                raise LookupError(f"Document segment not found: {segment_id}")
            session.add(
                SegmentTranslation(
                    id=result_id,
                    segment_id=segment_id,
                    batch_id=_batch_id_from_attempt(self._session_factory, attempt.attempt_id),
                    attempt_id=attempt.attempt_id,
                    translated_text_raw=translated_text_raw,
                    translated_text_restored=translated_text_restored,
                    status=SegmentTranslationStatus.MACHINE_TRANSLATED.value,
                    confidence_overall=None,
                    confidence_json=None,
                    validation_status=validation_status,
                    created_at=_now(),
                )
            )
            segment.machine_translation = translated_text_restored
            segment.status = (
                SegmentStatus.NEEDS_REVIEW.value
                if report.warnings
                else SegmentStatus.MACHINE_TRANSLATED.value
            )
            segment.review_status = (
                ReviewStatus.REVIEW_REQUIRED.value
                if report.warnings
                else ReviewStatus.NOT_REVIEWED.value
            )
            segment.updated_at = _now()
            for validator_type, status, details_json in _group_validation_issues(report.issues):
                session.add(
                    TranslationValidation(
                        id=str(uuid4()),
                        segment_translation_id=result_id,
                        validator_type=validator_type,
                        status=status,
                        score=None,
                        details_json=details_json,
                        created_at=_now(),
                    )
                )
        return StoredSegmentResult(
            segment_id,
            translated_text_raw,
            translated_text_restored,
            validation_status,
            tuple(issue.code.value for issue in report.issues),
        )

    def finish_run(self, run: StoredRun, status: TranslationRunStatus) -> StoredRun:
        from transloka_core.database import transaction_scope
        from transloka_core.database.models.translation import TranslationBatch

        with transaction_scope(self._session_factory) as session:
            row = session.get(TranslationBatch, run.run_id)
            if row is not None:
                row.status = status.value
                row.completed_at = _now()
        return StoredRun(run.run_id, run.idempotency_key, run.fingerprint, status)


def _batch_id_from_attempt(session_factory: Any, attempt_id: str) -> str:
    from sqlalchemy import select
    from transloka_core.database.models.translation import TranslationAttempt

    with session_factory() as session:
        row = session.scalar(select(TranslationAttempt).where(TranslationAttempt.id == attempt_id))
        if row is None:
            raise LookupError(f"Translation attempt not found: {attempt_id}")
        return cast(str, row.batch_id)


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _settings_with_fingerprint(settings_json: str, fingerprint: str) -> str:
    try:
        value = json.loads(settings_json)
    except (TypeError, ValueError):
        value = {}
    if not isinstance(value, dict):
        value = {"value": value}
    value["_operation_fingerprint"] = fingerprint
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _group_validation_issues(
    issues: Iterable[ValidationIssue],
) -> tuple[tuple[str, str, str], ...]:
    grouped: dict[str, list[ValidationIssue]] = {}
    for issue in issues:
        validator_type = _VALIDATOR_TYPE_BY_VALIDATION_CODE.get(issue.code, "SEMANTIC")
        grouped.setdefault(validator_type, []).append(issue)

    return tuple(
        (
            validator_type,
            _highest_validation_severity(group).value,
            json.dumps(
                {
                    "issues": [
                        {
                            "code": issue.code.value,
                            "severity": issue.severity.value,
                            "message": issue.message,
                        }
                        for issue in group
                    ]
                },
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ),
        )
        for validator_type, group in grouped.items()
    )


def _highest_validation_severity(issues: Iterable[ValidationIssue]) -> ValidationSeverity:
    return (
        ValidationSeverity.CRITICAL
        if any(issue.severity is ValidationSeverity.CRITICAL for issue in issues)
        else ValidationSeverity.WARNING
    )
