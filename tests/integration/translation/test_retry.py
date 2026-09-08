from __future__ import annotations

import asyncio
import json
from typing import Any

from transloka_translation.batching import BatchLimits
from transloka_translation.orchestration import (
    InMemoryTranslationRunStore,
    TranslationOperation,
    TranslationOrchestrator,
    TranslationSegmentInput,
)
from transloka_translation.providers import ProviderErrorCode, TranslationProviderError
from transloka_translation.retry import (
    RetryLevel,
    RetryOutcomeStatus,
    RetryPolicy,
    TranslationRetryCoordinator,
)
from transloka_translation.schemas import TranslationContext


def _operation(
    *segments: TranslationSegmentInput,
    key: str = "translation:retry:test",
    limits: BatchLimits | None = None,
) -> TranslationOperation:
    return TranslationOperation(
        project_id="prj_test",
        document_id="doc_test",
        section_id="section_test",
        glossary_snapshot_id="gls_test",
        provider_type="fake",
        model_id="fake-model",
        idempotency_key=key,
        context=TranslationContext(
            source_language="en",
            target_language="id",
            previous_text="previous context",
            next_text="next context",
        ),
        segments=tuple(segments),
        batch_limits=limits or BatchLimits(),
    )


def _segment(identifier: str, order: int) -> TranslationSegmentInput:
    return TranslationSegmentInput(
        segment_id=identifier,
        source_text=f"Source sentence {order}.",
        segment_order=order,
    )


class _ScriptedProvider:
    def __init__(self, outcomes: list[str | TranslationProviderError]) -> None:
        self._outcomes = outcomes
        self.requests: list[Any] = []
        self._call_count = 0

    async def translate(self, request: Any, *, cancellation: Any = None) -> str:
        del cancellation
        self.requests.append(request)
        outcome = self._outcomes[min(self._call_count, len(self._outcomes) - 1)]
        self._call_count += 1
        if isinstance(outcome, TranslationProviderError):
            raise outcome
        source_data = request.source_data["source_data"]
        return json.dumps(
            {
                "segments": [
                    {
                        "segment_id": segment["segment_id"],
                        "translated_text": f"Translated {segment['source_text']}",
                    }
                    for segment in source_data["segments"]
                ]
            }
        )


def _coordinator(
    provider: _ScriptedProvider,
    store: InMemoryTranslationRunStore,
    *,
    policy: RetryPolicy | None = None,
) -> TranslationRetryCoordinator:
    return TranslationRetryCoordinator(
        TranslationOrchestrator(provider, store),
        policy=policy,
    )


def test_retry_splits_failed_batch_and_completes_smaller_batches() -> None:
    provider = _ScriptedProvider(
        [
            TranslationProviderError(ProviderErrorCode.INVALID_RESPONSE, "truncated"),
            "echo",
            "echo",
        ]
    )
    coordinator = _coordinator(
        provider,
        InMemoryTranslationRunStore(),
        policy=RetryPolicy(same_batch_max=0),
    )
    operation = _operation(
        *(_segment(f"s{index}", index) for index in range(4)),
        limits=BatchLimits(max_segments=4),
    )

    result = asyncio.run(coordinator.run(operation))

    assert result.status is RetryOutcomeStatus.COMPLETED
    assert result.manual_review_segment_ids == ()
    assert any(attempt.level is RetryLevel.SMALLER_BATCH for attempt in result.attempts)
    assert result.completed_segment_ids == ("s0", "s1", "s2", "s3")


def test_successful_prior_segment_is_preserved_during_retry() -> None:
    provider = _ScriptedProvider(
        [
            "echo",
            TranslationProviderError(ProviderErrorCode.INVALID_RESPONSE, "invalid response"),
            "echo",
        ]
    )
    store = InMemoryTranslationRunStore()
    coordinator = _coordinator(provider, store)
    operation = _operation(
        _segment("s1", 1),
        _segment("s2", 2),
        limits=BatchLimits(max_segments=1),
    )

    result = asyncio.run(coordinator.run(operation))

    assert result.status is RetryOutcomeStatus.COMPLETED
    assert result.preserved_segment_ids == ("s1", "s2")
    assert [stored.segment_id for stored in store.results] == ["s1", "s2"]
    assert result.attempts[-1].pending_segment_ids == ("s2",)


def test_retry_stops_at_max_attempt_and_marks_manual_review() -> None:
    provider = _ScriptedProvider(
        [TranslationProviderError(ProviderErrorCode.INVALID_RESPONSE, "invalid response")]
    )
    coordinator = _coordinator(
        provider,
        InMemoryTranslationRunStore(),
        policy=RetryPolicy(
            same_batch_max=0,
            smaller_batch_max=0,
            single_segment_max=0,
            reduced_context_max=0,
        ),
    )

    result = asyncio.run(coordinator.run(_operation(_segment("s1", 1))))

    assert result.status is RetryOutcomeStatus.MANUAL_REVIEW
    assert result.attempt_count == 1
    assert result.manual_review_segment_ids == ("s1",)


def test_retry_idempotency_does_not_duplicate_valid_revision() -> None:
    provider = _ScriptedProvider(["echo"])
    store = InMemoryTranslationRunStore()
    coordinator = _coordinator(provider, store)
    operation = _operation(_segment("s1", 1), key="translation:retry:idempotent")

    first = asyncio.run(coordinator.run(operation))
    second = asyncio.run(coordinator.run(operation))

    assert first.status is RetryOutcomeStatus.COMPLETED
    assert second.status is RetryOutcomeStatus.COMPLETED
    assert second.attempts == ()
    assert len(provider.requests) == 1
    assert len(store.results) == 1
