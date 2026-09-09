from __future__ import annotations

import asyncio
import json
from dataclasses import replace

import pytest
from transloka_translation.orchestration import (
    InMemoryTranslationRunStore,
    TranslationOperation,
    TranslationOrchestrator,
    TranslationRunStatus,
    TranslationSegmentInput,
)
from transloka_translation.prompts import TranslationPrompt
from transloka_translation.providers import FakeTranslationProvider
from transloka_translation.schemas import (
    TranslationContext,
    TranslationGlossaryEntry,
    TranslationRequest,
)
from transloka_translation.validation import ValidationCode, ValidationSeverity


def _operation(
    *segments: tuple[str, str], provider_type: str = "CTRANSLATE2"
) -> TranslationOperation:
    return TranslationOperation(
        project_id="project-ct2",
        document_id="document-ct2",
        section_id=None,
        glossary_snapshot_id="glossary-ct2",
        provider_type=provider_type,
        model_id="opus-mt-en-id-ct2-int8",
        idempotency_key="ct2-unit-operation",
        context=TranslationContext("en", "id"),
        segments=tuple(
            TranslationSegmentInput(segment_id, text, segment_order=index)
            for index, (segment_id, text) in enumerate(segments)
        ),
    )


def _response(*segments: tuple[str, str]) -> str:
    return json.dumps(
        {
            "segments": [
                {"segment_id": segment_id, "translated_text": text} for segment_id, text in segments
            ]
        }
    )


def test_every_accepted_ct2_segment_persists_with_review_warning() -> None:
    store = InMemoryTranslationRunStore()
    provider = FakeTranslationProvider[TranslationPrompt, str](
        response=_response(("s1", "Halo"), ("s2", "Selamat"))
    )

    result = asyncio.run(
        TranslationOrchestrator(provider, store).run(_operation(("s1", "Hello"), ("s2", "Goodbye")))
    )

    assert result.status is TranslationRunStatus.COMPLETED_WITH_WARNINGS
    assert result.completed_segment_ids == ("s1", "s2")
    assert result.failed_segment_ids == ()
    assert result.warnings
    assert len(provider.requests) == 1
    assert [item.segment_id for item in store.results] == ["s1", "s2"]
    for persisted in store.results:
        assert persisted.validation_status == "PASSED_WITH_WARNINGS"
        assert persisted.validation_issues == (ValidationCode.NMT_REVIEW_REQUIRED.value,)
    assert {
        (issue.code, issue.severity, issue.segment_id)
        for issue in store.attempts[0].validation_issues
    } == {
        (ValidationCode.NMT_REVIEW_REQUIRED, ValidationSeverity.WARNING, "s1"),
        (ValidationCode.NMT_REVIEW_REQUIRED, ValidationSeverity.WARNING, "s2"),
    }


@pytest.mark.parametrize(
    ("invalid_text", "expected_code"),
    [
        ("Jumlah 13", ValidationCode.NUMBER_MISMATCH),
        ("", ValidationCode.EMPTY_TRANSLATION),
        (" \n\t", ValidationCode.EMPTY_TRANSLATION),
    ],
)
def test_invalid_ct2_segment_does_not_discard_healthy_segments_in_same_batch(
    invalid_text: str, expected_code: ValidationCode
) -> None:
    store = InMemoryTranslationRunStore()
    provider = FakeTranslationProvider[TranslationPrompt, str](
        response=_response(("before", "Halo"), ("invalid", invalid_text), ("after", "Selamat"))
    )
    operation = _operation(("before", "Hello"), ("invalid", "Count 12"), ("after", "Goodbye"))

    result = asyncio.run(TranslationOrchestrator(provider, store).run(operation))

    assert result.status is TranslationRunStatus.PARTIALLY_COMPLETED
    assert result.completed_segment_ids == ("before", "after")
    assert result.failed_segment_ids == ("invalid",)
    assert result.warnings
    assert [item.segment_id for item in store.results] == ["before", "after"]
    assert len(provider.requests) == 1
    assert len(store.attempts) == 1
    assert store.attempts[0].error_code == "VALIDATION_FAILED"
    assert len(result.failures) == 1
    assert result.failures[0].segment_id == "invalid"
    assert result.failures[0].code == "VALIDATION_FAILED"
    assert expected_code in result.failures[0].validation_codes
    for persisted, expected_text in zip(store.results, ("Halo", "Selamat"), strict=True):
        assert persisted.translated_text_restored == expected_text
        assert persisted.validation_status == "PASSED_WITH_WARNINGS"
        assert persisted.validation_issues == (ValidationCode.NMT_REVIEW_REQUIRED.value,)


def test_invalid_url_is_segment_local_and_other_segment_preserves_original_url() -> None:
    class ProtectedResponseProvider:
        async def translate(
            self, request: TranslationPrompt, *, cancellation: object = None
        ) -> str:
            data = TranslationRequest.from_dict(request.source_data["source_data"])
            valid = data.segments[1].source_text.replace("Read", "Baca")
            return _response(("invalid", "Baca"), ("valid", valid))

    store = InMemoryTranslationRunStore()
    provider = ProtectedResponseProvider()

    result = asyncio.run(
        TranslationOrchestrator(provider, store).run(
            _operation(
                ("invalid", "Read https://invalid.example.test"),
                ("valid", "Read https://valid.example.test"),
            )
        )
    )

    assert result.status is TranslationRunStatus.PARTIALLY_COMPLETED
    assert result.failed_segment_ids == ("invalid",)
    assert result.completed_segment_ids == ("valid",)
    assert result.failures[0].validation_codes == (
        ValidationCode.CODE_MISMATCH,
        ValidationCode.URL_MISMATCH,
    )
    assert [item.segment_id for item in store.results] == ["valid"]
    assert store.results[0].translated_text_restored == "Baca https://valid.example.test"


@pytest.mark.parametrize("provider_type", ["CTRANSLATE2", "OLLAMA"])
def test_ct2_glossary_acronym_stays_visible_while_ollama_still_receives_placeholder(
    provider_type: str,
) -> None:
    glossary = TranslationGlossaryEntry("API", "antarmuka", "TRANSLATE_AS")

    class GlossaryResponseProvider:
        async def translate(self, prompt: TranslationPrompt, *, cancellation: object = None) -> str:
            request = TranslationRequest.from_dict(prompt.source_data["source_data"])
            assert request.glossary == (glossary,)
            source = request.segments[0].source_text
            if provider_type == "CTRANSLATE2":
                assert source == "API"
                assert request.placeholders == ()
                return _response(("s1", "antarmuka"))
            assert source.startswith("__TLK_")
            assert len(request.placeholders) == 1
            assert request.placeholders[0].placeholder == source
            return _response(("s1", source))

    store = InMemoryTranslationRunStore()
    operation = replace(
        _operation(("s1", "API"), provider_type=provider_type), glossary=(glossary,)
    )

    result = asyncio.run(TranslationOrchestrator(GlossaryResponseProvider(), store).run(operation))

    assert result.completed_segment_ids == ("s1",)
    assert result.failed_segment_ids == ()
    assert store.results[0].translated_text_restored == (
        "antarmuka" if provider_type == "CTRANSLATE2" else "API"
    )
    if provider_type == "CTRANSLATE2":
        assert ValidationCode.NMT_REVIEW_REQUIRED.value in store.results[0].validation_issues


def test_all_invalid_ct2_segments_fail_without_persisting_results() -> None:
    store = InMemoryTranslationRunStore()
    provider = FakeTranslationProvider[TranslationPrompt, str](
        response=_response(("s1", ""), ("s2", ""))
    )

    result = asyncio.run(
        TranslationOrchestrator(provider, store).run(_operation(("s1", "Hello"), ("s2", "Goodbye")))
    )

    assert result.status is TranslationRunStatus.FAILED
    assert result.failed_segment_ids == ("s1", "s2")
    assert result.completed_segment_ids == ()
    assert store.results == []
    assert len(store.attempts) == 1
    assert store.attempts[0].status == "FAILED"
    assert store.attempts[0].error_code == "VALIDATION_FAILED"
    assert len(result.failures) == 2
    assert all(
        failure.validation_codes == (ValidationCode.EMPTY_TRANSLATION,)
        for failure in result.failures
    )


def test_only_local_fallback_segment_receives_fallback_warning() -> None:
    class LocalFallbackProvider(FakeTranslationProvider[object, str]):
        fallback_segment_ids = ("fallback",)

    store = InMemoryTranslationRunStore()
    provider = LocalFallbackProvider(
        response=_response(("normal", "Halo"), ("fallback", "Selamat"))
    )

    result = asyncio.run(
        TranslationOrchestrator(provider, store).run(
            _operation(("normal", "Hello"), ("fallback", "Goodbye"))
        )
    )

    assert result.status is TranslationRunStatus.COMPLETED_WITH_WARNINGS
    assert store.results[0].segment_id == "normal"
    assert store.results[0].validation_issues == (ValidationCode.NMT_REVIEW_REQUIRED.value,)
    assert store.results[1].segment_id == "fallback"
    assert set(store.results[1].validation_issues) == {
        ValidationCode.NMT_REVIEW_REQUIRED.value,
        ValidationCode.NMT_LOCAL_FALLBACK_USED.value,
    }


def test_other_providers_retain_atomic_batch_rejection() -> None:
    store = InMemoryTranslationRunStore()
    provider = FakeTranslationProvider[TranslationPrompt, str](
        response=_response(("s1", "Jumlah 13"), ("s2", "Halo"))
    )

    result = asyncio.run(
        TranslationOrchestrator(provider, store).run(
            _operation(("s1", "Count 12"), ("s2", "Hello"), provider_type="FAKE")
        )
    )

    assert result.status is TranslationRunStatus.FAILED
    assert result.failed_segment_ids == ("s1", "s2")
    assert store.results == []
    assert all(
        issue.code is not ValidationCode.NMT_REVIEW_REQUIRED
        for attempt in store.attempts
        for issue in attempt.validation_issues
    )


def test_other_provider_success_is_not_marked_as_nmt() -> None:
    store = InMemoryTranslationRunStore()
    provider = FakeTranslationProvider[TranslationPrompt, str](response=_response(("s1", "Halo")))

    result = asyncio.run(
        TranslationOrchestrator(provider, store).run(
            _operation(("s1", "Hello"), provider_type="FAKE")
        )
    )

    assert result.status is TranslationRunStatus.COMPLETED
    assert result.warnings == ()
    assert store.results[0].validation_issues == ()


@pytest.mark.parametrize(
    "raw_response",
    [
        '{"segments":[',
        _response(("s1", "Halo")),
        _response(("s1", "Halo"), ("s1", "Selamat")),
        _response(("s1", "Halo"), ("unknown", "Selamat")),
        _response(("s1", "Halo"), ("", "Selamat")),
        '{"segments":[{"segment_id":"s1","translated_text":"Halo"},'
        '{"segment_id":2,"translated_text":"Selamat"}]}',
        '{"segments":[{"segment_id":"s1","translated_text":"Halo"},'
        '{"segment_id":"s2","translated_text":null}]}',
        '{"segments":[],"segments":[{"segment_id":"s1","translated_text":"Halo"},'
        '{"segment_id":"s2","translated_text":"Selamat"}]}',
        f"```json\n{_response(('s1', 'Halo'), ('s2', 'Selamat'))}\n```",
    ],
    ids=[
        "malformed_json",
        "missing_id",
        "duplicate_id",
        "unknown_id",
        "empty_id",
        "numeric_id",
        "invalid_type",
        "duplicate_key",
        "markdown",
    ],
)
def test_ct2_per_segment_validation_keeps_structural_json_errors_batch_fatal(
    raw_response: str,
) -> None:
    store = InMemoryTranslationRunStore()
    provider = FakeTranslationProvider[TranslationPrompt, str](response=raw_response)

    result = asyncio.run(
        TranslationOrchestrator(provider, store).run(_operation(("s1", "Hello"), ("s2", "Goodbye")))
    )

    assert result.status is TranslationRunStatus.FAILED
    assert result.failed_segment_ids == ("s1", "s2")
    assert result.completed_segment_ids == ()
    assert store.results == []
    assert len(provider.requests) == 1
    assert len(result.failures) == 2
    assert all(failure.code == "INVALID_RESPONSE" for failure in result.failures)
    assert len(store.attempts) == 1
    assert store.attempts[0].error_code == "INVALID_RESPONSE"


def test_non_ct2_empty_translation_still_rejects_entire_batch() -> None:
    store = InMemoryTranslationRunStore()
    provider = FakeTranslationProvider[TranslationPrompt, str](
        response=_response(("invalid", ""), ("valid", "Halo"))
    )

    result = asyncio.run(
        TranslationOrchestrator(provider, store).run(
            _operation(("invalid", "Goodbye"), ("valid", "Hello"), provider_type="FAKE")
        )
    )

    assert result.status is TranslationRunStatus.FAILED
    assert result.failed_segment_ids == ("invalid", "valid")
    assert store.results == []
    assert result.warnings == ()
