from __future__ import annotations

import asyncio
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from transloka_glossary.placeholders.restoration import (
    PlaceholderRestorer,
)
from transloka_glossary.protection import (
    ProtectedContentDetector,
    ProtectedInventoryItem,
)

from transloka_translation.batching import (
    BatchSegment,
    TranslationBatch,
    TranslationBatchBuilder,
)
from transloka_translation.parsing import ResponseParseError, parse_translation_response
from transloka_translation.prompts import VersionedPromptBuilder
from transloka_translation.providers import (
    CancellationSignal,
    TranslationProviderError,
)
from transloka_translation.schemas import (
    TranslationContext,
    TranslationPlaceholder,
    TranslationRequest,
    TranslationRequestSegment,
    TranslationResponse,
)
from transloka_translation.validation import validate_translation

from .models import (
    SegmentFailure,
    TranslationOperation,
    TranslationRunResult,
    TranslationRunStatus,
)
from .persistence import (
    IdempotencyConflictError,
    StoredAttempt,
    StoredRun,
    TranslationRunStore,
    operation_fingerprint,
)


@dataclass(frozen=True, slots=True)
class ProtectedBatch:
    batch: TranslationBatch
    request: TranslationRequest
    inventories: dict[str, tuple[ProtectedInventoryItem, ...]]


class TranslationOrchestrator:
    """Executes one deterministic translation operation from load through persist."""

    def __init__(
        self,
        provider: Any,
        store: TranslationRunStore,
        *,
        batch_builder: TranslationBatchBuilder | None = None,
        prompt_builder: VersionedPromptBuilder | None = None,
        detector: ProtectedContentDetector | None = None,
        restorer: PlaceholderRestorer | None = None,
        status_sink: Callable[[TranslationRunStatus], None] | None = None,
        batch_progress_sink: Callable[[int, int], None] | None = None,
    ) -> None:
        self._provider = provider
        self._store = store
        self._batch_builder = batch_builder
        self._prompt_builder = prompt_builder
        self._detector = detector or ProtectedContentDetector()
        self._restorer = restorer or PlaceholderRestorer()
        self._status_sink = status_sink
        self._batch_progress_sink = batch_progress_sink

    async def run(
        self,
        operation: TranslationOperation,
        *,
        cancellation: CancellationSignal | None = None,
    ) -> TranslationRunResult:
        fingerprint = operation_fingerprint(operation)
        existing = self._store.find_by_idempotency_key(operation.idempotency_key)
        if existing is not None:
            if existing.fingerprint and existing.fingerprint != fingerprint:
                raise IdempotencyConflictError(
                    f"Idempotency key is already used: {operation.idempotency_key}."
                )
            return self._result_for_existing(existing)

        builder = self._batch_builder or TranslationBatchBuilder(operation.batch_limits)
        batch_segments = tuple(
            BatchSegment(
                segment_id=segment.segment_id,
                section_id=segment.section_id,
                section_order=segment.section_order,
                page_order=segment.page_order,
                block_order=segment.block_order,
                segment_order=segment.segment_order,
                source_text=segment.source_text,
                context=segment.context,
                locked=segment.locked,
            )
            for segment in operation.segments
        )
        plan = builder.build(batch_segments)
        run = self._store.create_run(operation, fingerprint, plan.segment_ids)
        self._emit(TranslationRunStatus.RUNNING)

        completed: list[str] = []
        failed: list[str] = []
        cancelled: list[str] = []
        failures: list[SegmentFailure] = []
        warnings: list[str] = []
        attempt_count = 0

        total_batches = len(plan.batches)
        for batch_number, batch in enumerate(plan.batches, start=1):
            if _is_cancelled(cancellation):
                cancelled.extend(batch.segment_ids)
                self._emit_batch_progress(batch_number, total_batches)
                continue
            protected = self._prepare_batch(operation, batch)
            attempt_count += 1
            attempt_number = attempt_count
            attempt: StoredAttempt | None = None
            try:
                prompt = (
                    self._prompt_builder or VersionedPromptBuilder(operation.prompt_version)
                ).build(protected.request)
                raw_response = await self._provider.translate(prompt, cancellation=cancellation)
                if _is_cancelled(cancellation):
                    cancelled.extend(batch.segment_ids)
                    self._emit_batch_progress(batch_number, total_batches)
                    continue
                response = _coerce_response(raw_response, protected.request.segment_ids)
                report = validate_translation(protected.request, response)
                attempt_status = "COMPLETED_WITH_WARNINGS" if report.warnings else "COMPLETED"
                attempt = self._store.record_attempt(
                    run,
                    attempt_number,
                    batch,
                    status=attempt_status,
                )
                if not report.accepted:
                    issue_text = "; ".join(issue.message for issue in report.critical_issues)
                    failed.extend(batch.segment_ids)
                    failures.extend(
                        SegmentFailure(segment_id, "VALIDATION_FAILED", issue_text)
                        for segment_id in batch.segment_ids
                    )
                    continue
                for segment in batch.segments:
                    translated = next(
                        item for item in response.segments if item.segment_id == segment.segment_id
                    )
                    inventory = protected.inventories.get(segment.segment_id, ())
                    restored = (
                        self._restorer.restore(translated.translated_text, inventory)
                        if inventory
                        else translated.translated_text
                    )
                    self._store.record_result(
                        attempt,
                        segment.segment_id,
                        translated.translated_text,
                        restored,
                        report,
                    )
                    completed.append(segment.segment_id)
                warnings.extend(issue.message for issue in report.warnings)
            except asyncio.CancelledError:
                cancelled.extend(batch.segment_ids)
                if attempt is None:
                    self._store.record_attempt(run, attempt_number, batch, status="CANCELLED")
            except TranslationProviderError as error:
                failed.extend(batch.segment_ids)
                failures.extend(
                    SegmentFailure(segment_id, error.code.value, str(error))
                    for segment_id in batch.segment_ids
                )
                self._store.record_attempt(
                    run,
                    attempt_number,
                    batch,
                    status="FAILED",
                    error_code=error.code.value,
                    error_message=str(error),
                )
            except (ResponseParseError, ValueError) as error:
                failed.extend(batch.segment_ids)
                failures.extend(
                    SegmentFailure(segment_id, "INVALID_RESPONSE", str(error))
                    for segment_id in batch.segment_ids
                )
                self._store.record_attempt(
                    run,
                    attempt_number,
                    batch,
                    status="FAILED",
                    error_code="INVALID_RESPONSE",
                    error_message=str(error),
                )
            self._emit_batch_progress(batch_number, total_batches)

        locked = list(plan.excluded_locked_segment_ids)
        final_status = _final_status(completed, failed, cancelled, warnings, len(locked))
        self._store.finish_run(run, final_status)
        self._emit(final_status)
        return TranslationRunResult(
            run_id=run.run_id,
            idempotency_key=run.idempotency_key,
            status=final_status,
            completed_segment_ids=tuple(completed),
            failed_segment_ids=tuple(failed),
            locked_segment_ids=tuple(locked),
            cancelled_segment_ids=tuple(cancelled),
            failures=tuple(failures),
            warnings=tuple(warnings),
            attempt_count=attempt_count,
        )

    def _prepare_batch(
        self, operation: TranslationOperation, batch: TranslationBatch
    ) -> ProtectedBatch:
        requests: list[TranslationRequestSegment] = []
        placeholders: list[TranslationPlaceholder] = []
        inventories: dict[str, tuple[ProtectedInventoryItem, ...]] = {}
        for segment in batch.segments:
            protected = self._detector.protect(segment.source_text)
            inventories[segment.segment_id] = protected.inventory
            requests.append(TranslationRequestSegment(segment.segment_id, protected.text))
            placeholders.extend(
                TranslationPlaceholder(
                    segment_id=segment.segment_id,
                    placeholder=item.placeholder,
                    item_type=item.item_type.value,
                )
                for item in protected.inventory
            )
        context = operation.context
        if batch.segments[0].context.heading is not None:
            context = TranslationContext(
                source_language=context.source_language,
                target_language=context.target_language,
                document_type=context.document_type,
                heading=batch.segments[0].context.heading,
                previous_text=batch.segments[0].context.previous_text,
                next_text=batch.segments[-1].context.next_text,
            )
        request = TranslationRequest(
            segments=tuple(requests),
            context=context,
            glossary=operation.glossary,
            placeholders=tuple(placeholders),
            style=operation.style,
        )
        return ProtectedBatch(batch, request, inventories)

    def _emit(self, status: TranslationRunStatus) -> None:
        if self._status_sink is not None:
            self._status_sink(status)

    def _emit_batch_progress(self, completed_batches: int, total_batches: int) -> None:
        if self._batch_progress_sink is not None:
            self._batch_progress_sink(completed_batches, total_batches)

    @staticmethod
    def _result_for_existing(run: StoredRun) -> TranslationRunResult:
        return TranslationRunResult(
            run_id=run.run_id,
            idempotency_key=run.idempotency_key,
            status=run.status,
            completed_segment_ids=(),
            failed_segment_ids=(),
            locked_segment_ids=(),
            cancelled_segment_ids=(),
        )


def _coerce_response(
    raw_response: object, known_segment_ids: tuple[str, ...]
) -> TranslationResponse:
    if isinstance(raw_response, TranslationResponse):
        return raw_response
    if not isinstance(raw_response, str):
        raise ValueError("Provider response must be JSON text or TranslationResponse.")
    return parse_translation_response(raw_response, known_segment_ids=known_segment_ids)


def _is_cancelled(signal: CancellationSignal | None) -> bool:
    return signal is not None and signal.is_cancelled


def _final_status(
    completed: list[str],
    failed: list[str],
    cancelled: list[str],
    warnings: list[str],
    locked_count: int,
) -> TranslationRunStatus:
    if not completed and cancelled and not failed:
        return TranslationRunStatus.CANCELLED
    if not completed and failed:
        return TranslationRunStatus.FAILED
    if failed or cancelled:
        return TranslationRunStatus.PARTIALLY_COMPLETED
    if warnings:
        return TranslationRunStatus.COMPLETED_WITH_WARNINGS
    if not completed and locked_count:
        return TranslationRunStatus.COMPLETED
    return TranslationRunStatus.COMPLETED
