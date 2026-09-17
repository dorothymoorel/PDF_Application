from __future__ import annotations

import asyncio
import importlib
import json
import sys
import traceback
from collections.abc import Callable
from dataclasses import dataclass, replace
from pathlib import Path
from threading import Event
from types import ModuleType, SimpleNamespace
from typing import cast
from unittest.mock import AsyncMock, Mock

import pytest
from transloka_translation.prompts import TranslationPrompt, VersionedPromptBuilder
from transloka_translation.providers import (
    ProviderErrorCode,
    ProviderHealthStatus,
    TranslationProviderError,
)
from transloka_translation.providers.ctranslate2 import CTranslate2TranslationProvider
from transloka_translation.schemas import (
    TranslationContext,
    TranslationGlossaryEntry,
    TranslationPlaceholder,
    TranslationRequest,
    TranslationRequestSegment,
    TranslationStyle,
)

_PLACEHOLDER = "__TLK_URL_0001_AB__"
_LEXICON = {
    "Read": "Baca",
    "again": "lagi",
    "and": "dan",
    "Hello": "Halo",
    "Goodbye": "Selamat",
    "savings": "tabungan",
}


class _SentencePiece:
    def __init__(self) -> None:
        self.encoded: list[str] = []

    def encode(self, text: str, *, out_type: type[str]) -> list[str]:
        assert out_type is str
        self.encoded.append(text)
        return [f"▁{word}" for word in text.split()]

    def decode(self, tokens: list[str]) -> str:
        return "".join(tokens).replace("▁", " ").strip()


@dataclass(frozen=True)
class _Call:
    inputs: tuple[tuple[str, ...], ...]
    options: dict[str, object]


def _translate_words(tokens: tuple[str, ...], beam: int) -> list[str]:
    return [f"▁{_LEXICON.get(token[1:], token[1:])}" for token in tokens if token != "</s>"]


class _Translator:
    def __init__(
        self,
        respond: Callable[[tuple[str, ...], int], list[str]] = _translate_words,
        *,
        on_call: Callable[[], None] | None = None,
    ) -> None:
        self.respond = respond
        self.on_call = on_call
        self.calls: list[_Call] = []

    def translate_batch(self, inputs: list[list[str]], **options: object) -> list[SimpleNamespace]:
        captured = tuple(tuple(tokens) for tokens in inputs)
        self.calls.append(_Call(captured, options))
        beam = options["beam_size"]
        assert isinstance(beam, int)
        results = [SimpleNamespace(hypotheses=[self.respond(tokens, beam)]) for tokens in captured]
        if self.on_call is not None:
            self.on_call()
        return results


@dataclass
class _Cancellation:
    is_cancelled: bool = False


def _provider(
    translator: _Translator | None = None, *, fallback: object = None
) -> tuple[CTranslate2TranslationProvider, _Translator, _SentencePiece]:
    provider = CTranslate2TranslationProvider(fallback=fallback)
    runtime = translator or _Translator()
    source = _SentencePiece()
    provider._runtime = (runtime, source, _SentencePiece())
    return provider, runtime, source


def _request(
    *segments: tuple[str, str],
    languages: tuple[str, str] = ("en", "id"),
    glossary: tuple[TranslationGlossaryEntry, ...] = (),
    placeholders: tuple[TranslationPlaceholder, ...] = (),
) -> TranslationPrompt:
    return VersionedPromptBuilder().build(
        TranslationRequest(
            segments=tuple(TranslationRequestSegment(*segment) for segment in segments),
            context=TranslationContext(*languages),
            glossary=glossary,
            placeholders=placeholders,
            style=TranslationStyle.NATURAL,
        )
    )


def _output(
    provider: CTranslate2TranslationProvider, prompt: TranslationPrompt
) -> list[dict[str, str]]:
    raw = asyncio.run(provider.translate(prompt))
    assert isinstance(raw, str)
    data = json.loads(raw)
    assert set(data) == {"segments"}
    return cast(list[dict[str, str]], data["segments"])


def _words(count: int) -> str:
    # Alphabetic unique tokens cannot be mistaken for numeric or code protections.
    return " ".join(
        "word" + chr(97 + index // 676) + chr(97 + index // 26 % 26) + chr(97 + index % 26)
        for index in range(count)
    )


@pytest.mark.parametrize(
    "literal",
    [
        "$1,234.50",
        "12%",
        "2024-09-03",
        "-5",
        "+7",
        "3.14",
        "²",
        "³",
        "②",
        "１２",
        "١٢",
        "https://example.test/docs?version=2",
        "/tmp/private/report.txt",
        r"C:\private\report.txt",
        "`value = 42`",
        "```python\nprint(42)\n```",
        "API",
        "[12, 13]",
        _PLACEHOLDER,
    ],
)
def test_protected_literals_never_enter_sentencepiece_or_translator(literal: str) -> None:
    provider, translator, source = _provider()
    placeholders = (
        (TranslationPlaceholder("s1", literal, "URL"),) if literal == _PLACEHOLDER else ()
    )

    assert _output(
        provider,
        _request(("s1", f"Read {literal} again."), placeholders=placeholders),
    ) == [{"segment_id": "s1", "translated_text": f"Baca {literal} lagi."}]
    assert source.encoded == ["Read", "again"]
    assert len(translator.calls) == 1
    assert translator.calls[0].inputs == (("▁Read", "</s>"), ("▁again", "</s>"))


def test_repeated_protected_literals_keep_their_inventory_and_punctuation() -> None:
    provider, translator, source = _provider()
    text = "  Read $12 and $12.\nRead https://example.test and https://example.test!  "

    assert _output(provider, _request(("s1", text))) == [
        {
            "segment_id": "s1",
            "translated_text": "  Baca $12 dan $12.\nBaca https://example.test dan https://example.test!  ",
        }
    ]
    assert not any("12" in text or "example.test" in text for text in source.encoded)
    assert len(translator.calls) == 1


@pytest.mark.parametrize(
    ("rule", "target", "replacement"),
    [
        ("KEEP_ORIGINAL", None, "savings"),
        ("PRESERVE_ABBREVIATION", None, "savings"),
        ("TRANSLATE_AS", "tabungan", "tabungan"),
        ("ORIGINAL_THEN_TRANSLATION", "tabungan", "savings (tabungan)"),
        ("TRANSLATION_THEN_ORIGINAL", "tabungan", "tabungan (savings)"),
    ],
)
def test_glossary_replacements_bypass_inference(
    rule: str, target: str | None, replacement: str
) -> None:
    provider, translator, source = _provider()
    prompt = _request(
        ("s1", "Read savings and savings again."),
        glossary=(TranslationGlossaryEntry("savings", target, rule),),
    )

    assert _output(provider, prompt) == [
        {"segment_id": "s1", "translated_text": f"Baca {replacement} dan {replacement} lagi."}
    ]
    assert source.encoded == ["Read", "and", "again"]
    assert len(translator.calls) == 1


def test_ignore_glossary_rule_allows_normal_translation() -> None:
    provider, _, source = _provider()

    assert _output(
        provider,
        _request(
            ("s1", "Read savings again."),
            glossary=(TranslationGlossaryEntry("savings", None, "IGNORE"),),
        ),
    ) == [{"segment_id": "s1", "translated_text": "Baca tabungan lagi."}]
    assert source.encoded == ["Read savings again"]


def test_output_preserves_request_order_including_literal_only_segments() -> None:
    provider, translator, _ = _provider()

    assert _output(
        provider, _request(("z-last", "Hello."), ("middle", "$12"), ("a-first", "Goodbye!"))
    ) == [
        {"segment_id": "z-last", "translated_text": "Halo."},
        {"segment_id": "middle", "translated_text": "$12"},
        {"segment_id": "a-first", "translated_text": "Selamat!"},
    ]
    assert translator.calls[0].inputs == (("▁Hello", "</s>"), ("▁Goodbye", "</s>"))


def test_literal_only_request_never_dispatches_native_translation() -> None:
    provider, translator, source = _provider()
    text = "$1,234.50 https://example.test /tmp/report.txt `value = 42`"

    assert _output(provider, _request(("literal", text))) == [
        {"segment_id": "literal", "translated_text": text}
    ]
    assert source.encoded == []
    assert translator.calls == []


@pytest.mark.parametrize("languages", [("id", "en"), ("en", "fr"), ("de", "id"), ("en-US", "id")])
def test_unsupported_language_pairs_fail_before_loading(
    languages: tuple[str, str], monkeypatch: pytest.MonkeyPatch
) -> None:
    provider = CTranslate2TranslationProvider()
    load = Mock(side_effect=AssertionError("Runtime must not load"))
    monkeypatch.setattr(provider, "_load", load)

    with pytest.raises(TranslationProviderError) as raised:
        asyncio.run(provider.translate(_request(("s1", "PRIVATE_SOURCE"), languages=languages)))

    assert raised.value.code is ProviderErrorCode.INVALID_REQUEST
    assert "PRIVATE_SOURCE" not in str(raised.value)
    load.assert_not_called()


def test_language_pair_validation_is_case_insensitive() -> None:
    provider, _, _ = _provider()
    assert (
        _output(provider, _request(("s1", "Hello"), languages=("EN", "ID")))[0]["translated_text"]
        == "Halo"
    )


@pytest.mark.parametrize("invalid", ["raw", "malformed_json", "segments", "characters"])
def test_invalid_or_oversized_requests_do_not_load_runtime(
    invalid: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    provider = CTranslate2TranslationProvider()
    load = Mock(side_effect=AssertionError("Runtime must not load"))
    monkeypatch.setattr(provider, "_load", load)
    request: object = {"source_text": "PRIVATE_SOURCE"}
    if invalid == "malformed_json":
        prompt = _request(("s1", "Hello"))
        request = replace(
            prompt,
            messages=(prompt.messages[0], replace(prompt.messages[1], content="PRIVATE_SOURCE")),
        )
    elif invalid == "segments":
        request = _request(*((f"s{index}", "Hello") for index in range(65)))
    elif invalid == "characters":
        request = _request(("s1", "x" * 100_001))

    with pytest.raises(TranslationProviderError) as raised:
        asyncio.run(provider.translate(request))

    assert raised.value.code is ProviderErrorCode.INVALID_REQUEST
    assert "PRIVATE_SOURCE" not in str(raised.value)
    load.assert_not_called()


def test_long_inputs_are_reassembled_without_truncation_across_microbatches() -> None:
    provider, translator, _ = _provider()
    text = _words(2_300)

    assert _output(provider, _request(("s1", text)))[0]["translated_text"] == text
    assert len(translator.calls) == 2
    chunks = [tokens for call in translator.calls for tokens in call.inputs]
    assert [len(tokens) - 1 for tokens in chunks] == [384, 384, 384, 384, 384, 380]
    assert [token for tokens in chunks for token in tokens[:-1]] == [
        f"▁{word}" for word in text.split()
    ]
    for call in translator.calls:
        assert sum(map(len, call.inputs)) <= 2_048
        assert all(tokens[-1] == "</s>" for tokens in call.inputs)
        assert call.options == {
            "beam_size": 1,
            "max_input_length": 0,
            "max_decoding_length": 512,
            "batch_type": "tokens",
            "max_batch_size": 2_048,
            "suppress_sequences": [],
        }


@pytest.mark.parametrize("count", [384, 385, 768, 769])
def test_chunk_boundary_lengths_preserve_every_input_token_once(count: int) -> None:
    provider, translator, _ = _provider()
    text = _words(count)

    assert _output(provider, _request(("s1", text)))[0]["translated_text"] == text
    chunks = [tokens for call in translator.calls for tokens in call.inputs]
    assert len(chunks) == (count + 383) // 384
    assert all(1 <= len(tokens) - 1 <= 384 for tokens in chunks)
    assert [token for tokens in chunks for token in tokens[:-1]] == [
        f"▁{word}" for word in text.split()
    ]


def test_chunks_split_at_sentencepiece_word_boundaries(monkeypatch: pytest.MonkeyPatch) -> None:
    tokens = ["▁word"] * 383 + ["▁joined", "tail", "▁last"]
    translator = _Translator(lambda tokens, beam: list(tokens[:-1]))
    provider, _, source = _provider(translator)
    monkeypatch.setattr(source, "encode", lambda text, out_type: tokens)
    text = " ".join(["word"] * 383 + ["joinedtail", "last"])

    assert _output(provider, _request(("s1", text)))[0]["translated_text"] == text
    assert translator.calls[0].inputs == (
        (*tokens[:383], "</s>"),
        (*tokens[383:], "</s>"),
    )


@pytest.mark.parametrize(
    "hypothesis",
    [
        [],
        ["<unk>"],
        ["▁hasil", "<unk>"],
        ["</s>", "<pad>"],
        ["▁"],
        ["▁kata"] * 512,
        ["▁kata"] * 513,
    ],
    ids=[
        "empty",
        "unknown",
        "mixed_unknown",
        "special_tokens_only",
        "blank_decode",
        "decode_cap",
        "above_decode_cap",
    ],
)
def test_invalid_decoding_fails_closed_after_one_beam_four_retry(hypothesis: list[str]) -> None:
    provider, translator, _ = _provider(_Translator(lambda tokens, beam: hypothesis))

    assert _output(provider, _request(("s1", "Hello"))) == [
        {"segment_id": "s1", "translated_text": ""}
    ]
    assert [call.options["beam_size"] for call in translator.calls] == [1, 4]
    assert provider.fallback_segment_ids == ()


def test_invalid_chunk_rejects_the_whole_segment_not_just_its_tail() -> None:
    text = _words(800)
    final_token = f"▁{text.split()[-1]}"
    provider, translator, _ = _provider(
        _Translator(lambda tokens, beam: [] if final_token in tokens else list(tokens[:-1]))
    )

    assert _output(provider, _request(("s1", text)))[0]["translated_text"] == ""
    assert [call.options["beam_size"] for call in translator.calls] == [1, 4]


def test_decoding_below_cap_is_not_rejected_or_retried() -> None:
    provider, translator, _ = _provider(_Translator(lambda tokens, beam: ["▁kata"] * 511))

    assert _output(provider, _request(("s1", "Hello")))[0]["translated_text"] == " ".join(
        ["kata"] * 511
    )
    assert [call.options["beam_size"] for call in translator.calls] == [1]


def test_retry_uses_beam_four_only_for_each_invalid_segment() -> None:
    def respond(tokens: tuple[str, ...], beam: int) -> list[str]:
        if "▁Broken" in tokens:
            return [] if beam == 1 else ["▁Pulih"]
        if "▁Hopeless" in tokens:
            return ["<unk>"]
        return _translate_words(tokens, beam)

    provider, translator, _ = _provider(_Translator(respond))

    assert _output(
        provider,
        _request(("s1", "Hello"), ("s2", "Broken"), ("s3", "Goodbye"), ("s4", "Hopeless")),
    ) == [
        {"segment_id": "s1", "translated_text": "Halo"},
        {"segment_id": "s2", "translated_text": "Pulih"},
        {"segment_id": "s3", "translated_text": "Selamat"},
        {"segment_id": "s4", "translated_text": ""},
    ]
    assert [call.options["beam_size"] for call in translator.calls] == [1, 4, 4]
    assert translator.calls[1].inputs == (("▁Broken", "</s>"),)
    assert translator.calls[2].inputs == (("▁Hopeless", "</s>"),)


def test_hallucinated_number_triggers_retry_without_retrying_healthy_peer() -> None:
    def respond(tokens: tuple[str, ...], beam: int) -> list[str]:
        if "▁Broken" in tokens and beam == 1:
            return ["▁Hasil", "▁99"]
        return ["▁Hasil"]

    provider, translator, _ = _provider(_Translator(respond))

    assert _output(provider, _request(("s1", "Hello"), ("s2", "Broken"))) == [
        {"segment_id": "s1", "translated_text": "Hasil"},
        {"segment_id": "s2", "translated_text": "Hasil"},
    ]
    assert [call.options["beam_size"] for call in translator.calls] == [1, 4]
    assert translator.calls[1].inputs == (("▁Broken", "</s>"),)


def test_runtime_exception_fails_closed_without_exposing_source_text() -> None:
    def fail(tokens: tuple[str, ...], beam: int) -> list[str]:
        raise RuntimeError("PRIVATE_SOURCE and /private/model/location")

    provider, translator, _ = _provider(_Translator(fail))

    assert _output(provider, _request(("s1", "Hello"))) == [
        {"segment_id": "s1", "translated_text": ""}
    ]
    assert [call.options["beam_size"] for call in translator.calls] == [1, 4]


def test_decoder_exception_does_not_expose_source_text(monkeypatch: pytest.MonkeyPatch) -> None:
    provider, _, _ = _provider()
    assert provider._runtime is not None
    monkeypatch.setattr(
        provider._runtime[2],
        "decode",
        Mock(side_effect=RuntimeError("PRIVATE_SOURCE and /private/model/location")),
    )

    with pytest.raises(TranslationProviderError) as raised:
        asyncio.run(provider.translate(_request(("s1", "Hello"))))

    assert raised.value.code is ProviderErrorCode.INVALID_RESPONSE
    assert raised.value.retryable is False
    formatted = "".join(traceback.format_exception(raised.value))
    assert "PRIVATE_SOURCE" not in str(raised.value)
    assert "/private/model/location" not in str(raised.value)
    assert "RuntimeError:" not in formatted


@pytest.fixture
def verified_model(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    module = ModuleType("transloka_translation.providers.nmt_model")
    module.verify_model_directory = Mock(return_value=tmp_path)  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, module.__name__, module)
    return tmp_path


def test_verified_vocabulary_digit_suppression_reaches_native_initial_and_retry_batches(
    verified_model: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    digit_tokens = ["▁12", "0", "▁$12.50", "version2", "²", "③", "１２", "١٢"]
    word_tokens = ["▁one", "▁twelve", "▁seratus", "Ⅳ", "</s>", "<unk>"]
    (verified_model / "shared_vocabulary.json").write_text(
        json.dumps(word_tokens + digit_tokens, ensure_ascii=False), encoding="utf-8"
    )

    def respond(tokens: tuple[str, ...], beam: int) -> list[str]:
        if "▁Broken" in tokens:
            return [] if beam == 1 else ["▁Pulih"]
        translated = []
        for token in _translate_words(tokens, beam):
            translated.extend(["▁dua", "▁belas"] if token == "▁twelve" else [token])
        return translated

    translator = _Translator(respond)
    source, target = _SentencePiece(), _SentencePiece()
    make_translator = Mock(return_value=translator)
    make_sentencepiece = Mock(side_effect=[source, target])
    runtimes = {
        "ctranslate2": SimpleNamespace(__version__="4.6.0", Translator=make_translator),
        "sentencepiece": SimpleNamespace(
            __version__="0.2.1", SentencePieceProcessor=make_sentencepiece
        ),
    }
    monkeypatch.setattr(importlib, "import_module", runtimes.__getitem__)
    provider = CTranslate2TranslationProvider(model_dir=verified_model / "configured")

    assert _output(
        provider, _request(("healthy", "Read twelve and 12 again."), ("retry", "Broken"))
    ) == [
        {"segment_id": "healthy", "translated_text": "Baca dua belas dan 12 lagi."},
        {"segment_id": "retry", "translated_text": "Pulih"},
    ]
    expected_suppression = [[token] for token in digit_tokens]
    assert provider._suppressed_sequences == expected_suppression
    assert [call.options["beam_size"] for call in translator.calls] == [1, 4]
    assert all(
        call.options["suppress_sequences"] == expected_suppression for call in translator.calls
    )
    assert translator.calls[1].inputs == (("▁Broken", "</s>"),)
    assert any("twelve" in text for text in source.encoded)
    assert not any(char.isdigit() for text in source.encoded for char in text)
    assert not any(
        char.isdigit()
        for call in translator.calls
        for tokens in call.inputs
        for char in "".join(tokens)
    )
    make_translator.assert_called_once_with(
        str(verified_model), device="cpu", compute_type="int8", inter_threads=1, intra_threads=4
    )
    assert [call.kwargs for call in make_sentencepiece.call_args_list] == [
        {"model_file": str(verified_model / "source.spm")},
        {"model_file": str(verified_model / "target.spm")},
    ]


@pytest.mark.parametrize("missing", ["ctranslate2", "sentencepiece"])
def test_missing_optional_runtime_is_offline_unavailable_without_content_leak(
    missing: str, verified_model: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def import_runtime(name: str) -> object:
        if name == missing:
            raise ModuleNotFoundError("PRIVATE_MODEL_PATH")
        assert name in {"ctranslate2", "sentencepiece"}
        return SimpleNamespace(__version__="4.6.0" if name == "ctranslate2" else "0.2.1")

    monkeypatch.setattr(importlib, "import_module", import_runtime)
    provider = CTranslate2TranslationProvider(model_dir=verified_model)

    assert asyncio.run(provider.health_check()).status is ProviderHealthStatus.UNAVAILABLE
    assert asyncio.run(provider.list_models()) == []
    with pytest.raises(TranslationProviderError) as raised:
        asyncio.run(provider.translate(_request(("s1", "PRIVATE_SOURCE"))))
    assert raised.value.code is ProviderErrorCode.PROVIDER_UNAVAILABLE
    assert "PRIVATE_SOURCE" not in str(raised.value)
    assert "PRIVATE_MODEL_PATH" not in str(raised.value)


def test_unconfigured_model_does_not_import_optional_runtime(
    verified_model: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("TRANSLOKA_CT2_MODEL_DIR", raising=False)
    imports = Mock(side_effect=AssertionError("No runtime may be imported"))
    monkeypatch.setattr(importlib, "import_module", imports)
    provider = CTranslate2TranslationProvider()

    assert asyncio.run(provider.health_check()).status is ProviderHealthStatus.UNAVAILABLE
    assert asyncio.run(provider.list_models()) == []
    with pytest.raises(TranslationProviderError) as raised:
        asyncio.run(provider.translate(_request(("s1", "Hello"))))
    assert raised.value.code is ProviderErrorCode.PROVIDER_UNAVAILABLE
    imports.assert_not_called()


def test_unsupported_runtime_version_fails_closed(
    verified_model: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        importlib,
        "import_module",
        lambda name: SimpleNamespace(__version__="4.5.0"),
    )
    provider = CTranslate2TranslationProvider(model_dir=verified_model)

    assert asyncio.run(provider.health_check()).status is ProviderHealthStatus.UNAVAILABLE
    with pytest.raises(TranslationProviderError) as raised:
        asyncio.run(provider.translate(_request(("s1", "Hello"))))
    assert raised.value.code is ProviderErrorCode.PROVIDER_UNAVAILABLE


def test_model_verification_failure_never_imports_runtime_or_uses_fallback(
    verified_model: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    module = sys.modules["transloka_translation.providers.nmt_model"]
    monkeypatch.setattr(
        module,
        "verify_model_directory",
        Mock(side_effect=ValueError("PRIVATE_SOURCE /private/model/location")),
    )
    imports = Mock(side_effect=AssertionError("No runtime may be imported"))
    monkeypatch.setattr(importlib, "import_module", imports)
    fallback = SimpleNamespace(translate=AsyncMock())
    provider = CTranslate2TranslationProvider(model_dir=verified_model, fallback=fallback)

    assert asyncio.run(provider.health_check()).status is ProviderHealthStatus.UNAVAILABLE
    with pytest.raises(TranslationProviderError) as raised:
        asyncio.run(provider.translate(_request(("s1", "Hello"))))

    assert raised.value.code is ProviderErrorCode.PROVIDER_UNAVAILABLE
    assert raised.value.retryable is False
    formatted = "".join(traceback.format_exception(raised.value))
    assert "PRIVATE_SOURCE" not in formatted
    assert "/private/model/location" not in formatted
    imports.assert_not_called()
    fallback.translate.assert_not_called()


def test_runtime_initialization_failure_has_no_content_bearing_exception(
    verified_model: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    runtimes = {
        "ctranslate2": SimpleNamespace(__version__="4.6.0"),
        "sentencepiece": SimpleNamespace(
            __version__="0.2.1",
            SentencePieceProcessor=Mock(
                side_effect=RuntimeError("PRIVATE_SOURCE /private/model/location")
            ),
        ),
    }
    monkeypatch.setattr(importlib, "import_module", runtimes.__getitem__)
    provider = CTranslate2TranslationProvider(model_dir=verified_model)

    with pytest.raises(TranslationProviderError) as raised:
        asyncio.run(provider.translate(_request(("s1", "Hello"))))

    assert raised.value.code is ProviderErrorCode.PROVIDER_UNAVAILABLE
    assert provider._runtime is None
    formatted = "".join(traceback.format_exception(raised.value))
    assert "PRIVATE_SOURCE" not in formatted
    assert "/private/model/location" not in formatted


def test_cloud_fallback_is_rejected_without_calling_it() -> None:
    cloud = SimpleNamespace(translate=AsyncMock(side_effect=AssertionError("Cloud must not run")))
    provider, translator, _ = _provider(_Translator(lambda tokens, beam: []), fallback=cloud)

    with pytest.raises(TranslationProviderError) as raised:
        asyncio.run(provider.translate(_request(("s1", "Hello"))))

    assert raised.value.code is ProviderErrorCode.INVALID_REQUEST
    assert [call.options["beam_size"] for call in translator.calls] == [1, 4]
    cloud.translate.assert_not_called()


def test_local_fallback_masks_protected_literals_and_restores_them(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from transloka_translation.providers.ollama import OllamaTranslationProvider

    captured: list[TranslationPrompt] = []

    async def translate(prompt: TranslationPrompt, *, cancellation: object = None) -> str:
        del cancellation
        captured.append(prompt)
        source_data = cast(dict[str, object], prompt.source_data["source_data"])
        segments = cast(list[dict[str, str]], source_data["segments"])
        placeholders = cast(list[dict[str, str]], source_data["placeholders"])
        tokens = [item["placeholder"] for item in placeholders]
        assert len(tokens) == 9
        assert segments[0]["source_text"] == (
            f"Read{tokens[0]}{tokens[1]}{tokens[2]}and{tokens[3]}{tokens[4]}"
            f"{tokens[5]}at{tokens[6]}{tokens[7]}{tokens[8]}"
        )
        assert "." not in segments[0]["source_text"]
        assert not any(char.isspace() for char in segments[0]["source_text"])
        return json.dumps(
            {
                "segments": [
                    {
                        "segment_id": segments[0]["segment_id"],
                        "translated_text": (
                            f"Baca {tokens[0]} {tokens[1]} {tokens[2]} dan {tokens[3]} "
                            f"{tokens[4]} {tokens[5]} di {tokens[6]} {tokens[7]} {tokens[8]}"
                        ),
                    }
                ]
            }
        )

    fallback = OllamaTranslationProvider()
    monkeypatch.setattr(fallback, "translate", translate)
    provider, translator, _ = _provider(_Translator(lambda tokens, beam: []), fallback=fallback)
    glossary = (TranslationGlossaryEntry("API", None, "PRESERVE_ABBREVIATION"),)
    request = TranslationRequest.from_dict(
        cast(
            dict[str, object],
            _request(
                ("s1", "Read API and 12 at https://example.test."), glossary=glossary
            ).source_data["source_data"],
        )
    )
    prompt = VersionedPromptBuilder().build(
        replace(
            request,
            context=TranslationContext(
                "en",
                "id",
                "TECHNICAL_BOOK",
                "CONTEXT_HEADING_SENTINEL",
                "CONTEXT_PREVIOUS_SENTINEL",
                "CONTEXT_NEXT_SENTINEL",
            ),
        )
    )

    output = _output(provider, prompt)

    assert output == [
        {
            "segment_id": "s1",
            "translated_text": "Baca API dan 12 di https://example.test.",
        }
    ]
    assert [call.options["beam_size"] for call in translator.calls] == [1, 4]
    assert provider.fallback_segment_ids == ("s1",)
    assert len(captured) == 1
    serialized = captured[0].messages[1].content
    assert "API" not in serialized
    assert "https://example.test" not in serialized
    assert '"12"' not in serialized
    assert "CONTEXT_HEADING_SENTINEL" not in serialized
    assert "CONTEXT_PREVIOUS_SENTINEL" not in serialized
    assert "CONTEXT_NEXT_SENTINEL" not in serialized


def test_cancellation_before_dispatch_does_not_load_or_translate(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider, translator, _ = _provider()
    load = Mock(side_effect=AssertionError("Runtime must not load"))
    monkeypatch.setattr(provider, "_load", load)

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(provider.translate(_request(("s1", "Hello")), cancellation=_Cancellation(True)))

    load.assert_not_called()
    assert translator.calls == []


def test_cancellation_while_waiting_for_lock_does_not_load_runtime(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    provider, translator, _ = _provider()
    load = Mock(side_effect=AssertionError("Runtime must not load"))
    monkeypatch.setattr(provider, "_load", load)
    cancellation = _Cancellation()

    async def cancel_waiting() -> None:
        await provider._lock.acquire()
        task = asyncio.create_task(
            provider.translate(_request(("s1", "Hello")), cancellation=cancellation)
        )
        await asyncio.sleep(0)
        cancellation.is_cancelled = True
        provider._lock.release()
        await task

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(cancel_waiting())
    load.assert_not_called()
    assert translator.calls == []


@pytest.mark.parametrize("cancel_on_call", [1, 2])
def test_cancellation_during_inference_prevents_later_microbatches_retries_and_fallback(
    cancel_on_call: int,
) -> None:
    cancellation = _Cancellation()
    fallback = SimpleNamespace(translate=AsyncMock(side_effect=AssertionError("No fallback")))

    def cancel() -> None:
        if len(translator.calls) == cancel_on_call:
            cancellation.is_cancelled = True

    translator = _Translator(lambda tokens, beam: [], on_call=cancel)
    provider, _, _ = _provider(translator, fallback=fallback)
    text = _words(2_300) if cancel_on_call == 1 else "Hello"

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(provider.translate(_request(("s1", text)), cancellation=cancellation))

    assert len(translator.calls) == cancel_on_call
    assert [call.options["beam_size"] for call in translator.calls] == (
        [1] if cancel_on_call == 1 else [1, 4]
    )
    fallback.translate.assert_not_called()


def test_task_cancellation_drains_native_work_before_releasing_provider_lock() -> None:
    started = Event()
    release = Event()

    def block_first_call() -> None:
        if len(translator.calls) == 1:
            started.set()
            assert release.wait(timeout=5), "Native translation was not released"

    translator = _Translator(on_call=block_first_call)
    provider, _, _ = _provider(translator)

    async def cancel_native_work() -> None:
        cancelled = asyncio.create_task(provider.translate(_request(("first", "Hello"))))
        try:
            assert await asyncio.to_thread(started.wait, 5)
            cancelled.cancel()
            await asyncio.sleep(0)
            assert not cancelled.done()
            assert provider._lock.locked()
            following = asyncio.create_task(provider.translate(_request(("second", "Goodbye"))))
            await asyncio.sleep(0)
            assert len(translator.calls) == 1
        finally:
            release.set()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(cancelled, timeout=5)
        result = json.loads(await asyncio.wait_for(following, timeout=5))
        assert result["segments"] == [{"segment_id": "second", "translated_text": "Selamat"}]
        assert not provider._lock.locked()

    asyncio.run(cancel_native_work())
    assert [call.options["beam_size"] for call in translator.calls] == [1, 1]
