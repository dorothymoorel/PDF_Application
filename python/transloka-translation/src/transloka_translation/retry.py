from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from enum import StrEnum
from hashlib import sha256
from typing import Any

from transloka_translation.batching import BatchContext, BatchLimits
from transloka_translation.orchestration import (
    TranslationOperation,
    TranslationOrchestrator,
    TranslationRunResult,
    TranslationRunStatus,
)
from transloka_translation.providers import CancellationSignal
from transloka_translation.schemas import TranslationContext

_COMPLETED_BY_IDEMPOTENCY: dict[tuple[int, str], set[str]] = {}


class RetryLevel(StrEnum):
    SAME_BATCH = "SAME_BATCH"
    SMALLER_BATCH = "SMALLER_BATCH"
    SINGLE_SEGMENT = "SINGLE_SEGMENT"
    REDUCED_CONTEXT = "REDUCED_CONTEXT"
    MANUAL_REVIEW = "MANUAL_REVIEW"


class RetryOutcomeStatus(StrEnum):
    COMPLETED = "COMPLETED"
    COMPLETED_WITH_WARNINGS = "COMPLETED_WITH_WARNINGS"
    MANUAL_REVIEW = "MANUAL_REVIEW"
    CANCELLED = "CANCELLED"


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    same_batch_max: int = 2
    smaller_batch_max: int = 2
    single_segment_max: int = 1
    reduced_context_max: int = 1

    def __post_init__(self) -> None:
        values = (
            self.same_batch_max,
            self.smaller_batch_max,
            self.single_segment_max,
            self.reduced_context_max,
        )
        if any(type(value) is not int or value < 0 for value in values):
            raise ValueError("Retry limits must be non-negative integers.")


@dataclass(frozen=True, slots=True)
class RetryAttempt:
    level: RetryLevel
    attempt_number: int
    operation_key: str
    pending_segment_ids: tuple[str, ...]
    result: TranslationRunResult


@dataclass(frozen=True, slots=True)
class RetryResult:
    status: RetryOutcomeStatus
    completed_segment_ids: tuple[str, ...]
    manual_review_segment_ids: tuple[str, ...]
    attempts: tuple[RetryAttempt, ...]
    warnings: tuple[str, ...] = ()

    @property
    def attempt_count(self) -> int:
        return len(self.attempts)

    @property
    def preserved_segment_ids(self) -> tuple[str, ...]:
        return self.completed_segment_ids


class TranslationRetryCoordinator:
    """Apply bounded retry levels without replaying successful segments."""

    def __init__(
        self,
        orchestrator: TranslationOrchestrator,
        *,
        policy: RetryPolicy | None = None,
        orchestrator_factory: Callable[[TranslationOperation], TranslationOrchestrator]
        | None = None,
    ) -> None:
        if not isinstance(orchestrator, TranslationOrchestrator):
            raise TypeError("orchestrator must be TranslationOrchestrator.")
        self._orchestrator = orchestrator
        self._store = getattr(orchestrator, "_store", None)
        self._policy = policy or RetryPolicy()
        self._orchestrator_factory = orchestrator_factory

    async def run(
        self,
        operation: TranslationOperation,
        *,
        cancellation: CancellationSignal | None = None,
    ) -> RetryResult:
        if not isinstance(operation, TranslationOperation):
            raise TypeError("operation must be TranslationOperation.")

        eligible_ids = tuple(
            segment.segment_id for segment in operation.segments if not segment.locked
        )
        existing = self._find_existing(operation.idempotency_key)
        cache_key = (id(self._store), operation.idempotency_key)
        preserved = set(_COMPLETED_BY_IDEMPOTENCY.get(cache_key, set()))
        if existing is not None and existing.status in {
            TranslationRunStatus.COMPLETED,
            TranslationRunStatus.COMPLETED_WITH_WARNINGS,
        }:
            preserved.update(eligible_ids)
            return RetryResult(
                status=(
                    RetryOutcomeStatus.COMPLETED_WITH_WARNINGS
                    if existing.status is TranslationRunStatus.COMPLETED_WITH_WARNINGS
                    else RetryOutcomeStatus.COMPLETED
                ),
                completed_segment_ids=_ordered_ids(operation, preserved),
                manual_review_segment_ids=(),
                attempts=(),
            )

        pending = [segment_id for segment_id in eligible_ids if segment_id not in preserved]
        attempts: list[RetryAttempt] = []
        warnings: list[str] = []
        attempt_number = 0
        was_cancelled = False

        async def execute(
            level: RetryLevel,
            candidate: TranslationOperation,
            pending_ids: tuple[str, ...],
        ) -> None:
            nonlocal pending, attempt_number, was_cancelled
            if not pending_ids or _cancelled(cancellation):
                return
            attempt_number += 1
            result = await self._runner(candidate).run(candidate, cancellation=cancellation)
            attempts.append(
                RetryAttempt(
                    level=level,
                    attempt_number=attempt_number,
                    operation_key=candidate.idempotency_key,
                    pending_segment_ids=pending_ids,
                    result=result,
                )
            )
            preserved.update(result.completed_segment_ids)
            _COMPLETED_BY_IDEMPOTENCY.setdefault(cache_key, set()).update(
                result.completed_segment_ids
            )
            warnings.extend(result.warnings)
            remaining = [
                segment_id
                for segment_id in pending
                if segment_id not in result.completed_segment_ids
            ]
            if result.cancelled_segment_ids:
                was_cancelled = True
            pending = [
                segment_id
                for segment_id in remaining
                if segment_id in result.failed_segment_ids
                or segment_id in result.cancelled_segment_ids
            ]

        initial_key = operation.idempotency_key
        if existing is not None:
            initial_key = _retry_key(operation.idempotency_key, RetryLevel.SAME_BATCH, 0, pending)
        await execute(
            RetryLevel.SAME_BATCH,
            replace(
                operation, segments=_segments_for(operation, pending), idempotency_key=initial_key
            ),
            tuple(pending),
        )

        for retry_number in range(1, self._policy.same_batch_max + 1):
            if not pending or _cancelled(cancellation):
                break
            key = _retry_key(
                operation.idempotency_key, RetryLevel.SAME_BATCH, retry_number, pending
            )
            await execute(
                RetryLevel.SAME_BATCH,
                replace(operation, segments=_segments_for(operation, pending), idempotency_key=key),
                tuple(pending),
            )

        for retry_number in range(1, self._policy.smaller_batch_max + 1):
            if not pending or _cancelled(cancellation):
                break
            limits = _reduced_batch_limits(operation.batch_limits, retry_number)
            key = _retry_key(
                operation.idempotency_key, RetryLevel.SMALLER_BATCH, retry_number, pending
            )
            await execute(
                RetryLevel.SMALLER_BATCH,
                replace(
                    operation,
                    segments=_segments_for(operation, pending),
                    batch_limits=limits,
                    idempotency_key=key,
                ),
                tuple(pending),
            )

        for retry_number in range(1, self._policy.single_segment_max + 1):
            if not pending or _cancelled(cancellation):
                break
            for segment_id in tuple(pending):
                key = _retry_key(
                    operation.idempotency_key,
                    RetryLevel.SINGLE_SEGMENT,
                    retry_number,
                    (segment_id,),
                )
                await execute(
                    RetryLevel.SINGLE_SEGMENT,
                    replace(
                        operation,
                        segments=_segments_for(operation, (segment_id,)),
                        batch_limits=BatchLimits(
                            max_segments=1,
                            max_input_tokens=operation.batch_limits.max_input_tokens,
                            max_context_tokens=operation.batch_limits.max_context_tokens,
                        ),
                        idempotency_key=key,
                    ),
                    (segment_id,),
                )

        for retry_number in range(1, self._policy.reduced_context_max + 1):
            if not pending or _cancelled(cancellation):
                break
            reduced_context_segments = tuple(
                replace(
                    segment,
                    context=BatchContext(heading=segment.context.heading),
                )
                for segment in _segments_for(operation, pending)
            )
            key = _retry_key(
                operation.idempotency_key,
                RetryLevel.REDUCED_CONTEXT,
                retry_number,
                pending,
            )
            await execute(
                RetryLevel.REDUCED_CONTEXT,
                replace(
                    operation,
                    segments=reduced_context_segments,
                    context=_reduced_context(operation.context),
                    batch_limits=BatchLimits(
                        max_segments=1,
                        max_input_tokens=operation.batch_limits.max_input_tokens,
                        max_context_tokens=operation.batch_limits.max_context_tokens,
                    ),
                    idempotency_key=key,
                ),
                tuple(pending),
            )

        if _cancelled(cancellation) or was_cancelled:
            status = RetryOutcomeStatus.CANCELLED
        elif pending:
            status = RetryOutcomeStatus.MANUAL_REVIEW
        elif any(
            attempt.result.status is TranslationRunStatus.COMPLETED_WITH_WARNINGS
            for attempt in attempts
        ):
            status = RetryOutcomeStatus.COMPLETED_WITH_WARNINGS
        else:
            status = RetryOutcomeStatus.COMPLETED
        return RetryResult(
            status=status,
            completed_segment_ids=_ordered_ids(operation, preserved),
            manual_review_segment_ids=tuple(
                segment_id for segment_id in eligible_ids if segment_id in pending
            ),
            attempts=tuple(attempts),
            warnings=tuple(warnings),
        )

    def _runner(self, operation: TranslationOperation) -> TranslationOrchestrator:
        if self._orchestrator_factory is not None:
            return self._orchestrator_factory(operation)
        return self._orchestrator

    def _find_existing(self, key: str) -> Any:
        store = getattr(self._orchestrator, "_store", None)
        if store is None or not hasattr(store, "find_by_idempotency_key"):
            return None
        return store.find_by_idempotency_key(key)


async def retry_translation(
    operation: TranslationOperation,
    orchestrator: TranslationOrchestrator,
    *,
    policy: RetryPolicy | None = None,
    cancellation: CancellationSignal | None = None,
) -> RetryResult:
    return await TranslationRetryCoordinator(orchestrator, policy=policy).run(
        operation,
        cancellation=cancellation,
    )


def _segments_for(
    operation: TranslationOperation, segment_ids: list[str] | tuple[str, ...]
) -> tuple[Any, ...]:
    wanted = set(segment_ids)
    return tuple(segment for segment in operation.segments if segment.segment_id in wanted)


def _ordered_ids(operation: TranslationOperation, identifiers: set[str]) -> tuple[str, ...]:
    return tuple(
        segment.segment_id for segment in operation.segments if segment.segment_id in identifiers
    )


def _reduced_batch_limits(limits: BatchLimits, retry_number: int) -> BatchLimits:
    divisor = 2**retry_number
    return BatchLimits(
        max_segments=max(1, (limits.max_segments + divisor - 1) // divisor),
        max_input_tokens=max(1, limits.max_input_tokens // divisor),
        max_context_tokens=(
            None
            if limits.max_context_tokens is None
            else max(0, limits.max_context_tokens // divisor)
        ),
    )


def _reduced_context(context: TranslationContext) -> TranslationContext:
    return TranslationContext(
        source_language=context.source_language,
        target_language=context.target_language,
        document_type=context.document_type,
        heading=context.heading,
        previous_text=None,
        next_text=None,
    )


def _retry_key(
    base: str, level: RetryLevel, retry_number: int, segment_ids: list[str] | tuple[str, ...]
) -> str:
    digest = sha256("|".join(segment_ids).encode("utf-8")).hexdigest()[:12]
    return f"{base}:retry:{level.value.lower()}:{retry_number}:{digest}"


def _cancelled(signal: CancellationSignal | None) -> bool:
    return signal is not None and signal.is_cancelled


__all__ = [
    "RetryAttempt",
    "RetryLevel",
    "RetryOutcomeStatus",
    "RetryPolicy",
    "RetryResult",
    "TranslationRetryCoordinator",
    "retry_translation",
]
