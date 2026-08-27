from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass

from transloka_translation.batching import BatchLimits
from transloka_translation.orchestration import (
    InMemoryTranslationRunStore,
    TranslationOperation,
    TranslationOrchestrator,
    TranslationRunStatus,
    TranslationSegmentInput,
)
from transloka_translation.providers import (
    FakeTranslationProvider,
    ProviderErrorCode,
    TranslationProviderError,
)
from transloka_translation.schemas import TranslationContext


def _operation(
    *segments: TranslationSegmentInput,
    key: str = "translation:test:one",
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
        context=TranslationContext(source_language="en", target_language="id"),
        segments=tuple(segments),
        batch_limits=limits or BatchLimits(),
    )


def _response(*pairs: tuple[str, str]) -> str:
    return json.dumps(
        {"segments": [{"segment_id": key, "translated_text": value} for key, value in pairs]}
    )


def _segment(
    identifier: str, text: str, *, order: int = 0, locked: bool = False
) -> TranslationSegmentInput:
    return TranslationSegmentInput(
        segment_id=identifier,
        source_text=text,
        segment_order=order,
        locked=locked,
    )


class _ProtectedEchoProvider:
    def __init__(self) -> None:
        self.requests: list[object] = []

    async def translate(self, request: object, *, cancellation: object = None) -> str:
        del cancellation
        self.requests.append(request)
        source_data = request.source_data["source_data"]  # type: ignore[attr-defined]
        segments = source_data["segments"]
        return _response(
            *(
                (segment["segment_id"], f"Terjemahkan {segment['source_text']}")
                for segment in segments
            )
        )


def test_fake_success_persists_restored_segment() -> None:
    provider: FakeTranslationProvider[object, str] = FakeTranslationProvider(
        response=_response(("s1", "Satu"))
    )
    store = InMemoryTranslationRunStore()
    orchestrator = TranslationOrchestrator(provider, store)

    result = asyncio.run(orchestrator.run(_operation(_segment("s1", "One"))))

    assert result.status is TranslationRunStatus.COMPLETED
    assert result.completed_segment_ids == ("s1",)
    assert store.results[0].translated_text_restored == "Satu"
    assert len(provider.requests) == 1


def test_protection_and_restoration_preserve_url() -> None:
    provider = _ProtectedEchoProvider()
    store = InMemoryTranslationRunStore()
    orchestrator = TranslationOrchestrator(provider, store)

    result = asyncio.run(
        orchestrator.run(_operation(_segment("s1", "Translate https://example.com now")))
    )

    assert result.status is TranslationRunStatus.COMPLETED
    assert (
        store.results[0].translated_text_restored == "Terjemahkan Translate https://example.com now"
    )


class _ScriptedProvider:
    def __init__(self, responses: list[str | TranslationProviderError]) -> None:
        self._responses = responses
        self.calls = 0

    async def translate(self, request: object, *, cancellation: object = None) -> str:
        del request, cancellation
        response = self._responses[self.calls]
        self.calls += 1
        if isinstance(response, TranslationProviderError):
            raise response
        return response


def test_partial_failure_identifies_only_failed_batch() -> None:
    provider = _ScriptedProvider(
        [
            _response(("s1", "Satu")),
            TranslationProviderError(
                ProviderErrorCode.TIMEOUT, "provider timed out", retryable=True
            ),
        ]
    )
    store = InMemoryTranslationRunStore()
    orchestrator = TranslationOrchestrator(provider, store)
    operation = _operation(
        _segment("s1", "One", order=0),
        _segment("s2", "Two", order=1),
        limits=BatchLimits(max_segments=1),
    )

    result = asyncio.run(orchestrator.run(operation))

    assert result.status is TranslationRunStatus.PARTIALLY_COMPLETED
    assert result.completed_segment_ids == ("s1",)
    assert result.failed_segment_ids == ("s2",)
    assert result.failures[0].code == ProviderErrorCode.TIMEOUT.value


def test_orchestrator_reports_progress_after_each_batch() -> None:
    provider = _ScriptedProvider(
        [
            _response(("s1", "Satu")),
            _response(("s2", "Dua")),
        ]
    )
    updates: list[tuple[int, int]] = []
    orchestrator = TranslationOrchestrator(
        provider,
        InMemoryTranslationRunStore(),
        batch_progress_sink=lambda completed, total: updates.append((completed, total)),
    )
    operation = _operation(
        _segment("s1", "One", order=0),
        _segment("s2", "Two", order=1),
        limits=BatchLimits(max_segments=1),
    )

    asyncio.run(orchestrator.run(operation))

    assert updates == [(1, 2), (2, 2)]


def test_provider_timeout_marks_segment_failed() -> None:
    provider: FakeTranslationProvider[object, str] = FakeTranslationProvider(
        response="unused",
        failure=TranslationProviderError(ProviderErrorCode.TIMEOUT, "timeout", retryable=True),
    )
    orchestrator = TranslationOrchestrator(provider, InMemoryTranslationRunStore())

    result = asyncio.run(orchestrator.run(_operation(_segment("s1", "One"))))

    assert result.status is TranslationRunStatus.FAILED
    assert result.failed_segment_ids == ("s1",)
    assert result.failures[0].code == "TIMEOUT"


@dataclass
class _Cancellation:
    is_cancelled: bool = True


def test_cancellation_does_not_call_provider_for_unstarted_batch() -> None:
    provider: FakeTranslationProvider[object, str] = FakeTranslationProvider(
        response=_response(("s1", "Satu"))
    )
    orchestrator = TranslationOrchestrator(provider, InMemoryTranslationRunStore())

    result = asyncio.run(
        orchestrator.run(_operation(_segment("s1", "One")), cancellation=_Cancellation())
    )

    assert result.status is TranslationRunStatus.CANCELLED
    assert result.cancelled_segment_ids == ("s1",)
    assert provider.requests == ()


def test_idempotency_returns_existing_run_without_duplicate_provider_call() -> None:
    provider: FakeTranslationProvider[object, str] = FakeTranslationProvider(
        response=_response(("s1", "Satu"))
    )
    store = InMemoryTranslationRunStore()
    orchestrator = TranslationOrchestrator(provider, store)
    operation = _operation(_segment("s1", "One"), key="translation:test:idempotent")

    first = asyncio.run(orchestrator.run(operation))
    second = asyncio.run(orchestrator.run(operation))

    assert first.run_id == second.run_id
    assert second.status is TranslationRunStatus.COMPLETED
    assert len(provider.requests) == 1
    assert len(store.attempts) == 1


def test_locked_segment_is_excluded_from_provider_and_result() -> None:
    provider: FakeTranslationProvider[object, str] = FakeTranslationProvider(
        response=_response(("s1", "Satu"))
    )
    orchestrator = TranslationOrchestrator(provider, InMemoryTranslationRunStore())
    operation = _operation(
        _segment("s1", "One", order=0),
        _segment("s2", "Already approved", order=1, locked=True),
    )

    result = asyncio.run(orchestrator.run(operation))

    assert result.status is TranslationRunStatus.COMPLETED
    assert result.completed_segment_ids == ("s1",)
    assert result.locked_segment_ids == ("s2",)
    assert len(provider.requests) == 1
