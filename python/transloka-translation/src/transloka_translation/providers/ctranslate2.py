from __future__ import annotations

import asyncio
import importlib
import json
import os
import re
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from transloka_glossary.protection import ProtectedContentDetector

from transloka_translation.prompts import TranslationPrompt, VersionedPromptBuilder
from transloka_translation.schemas import (
    TranslatedSegment,
    TranslationRequest,
    TranslationResponse,
)
from transloka_translation.validation import validate_translation

from .base import (
    CancellationSignal,
    LocalModel,
    ProviderErrorCode,
    ProviderHealth,
    ProviderHealthStatus,
    TranslationProviderError,
)

MODEL_ID = "opus-mt-en-id-ct2-int8"
MODEL_REVISION = "6e4c52d61a6b16fe3509b0267cbfec65011b860b"
_MAX_SOURCE_TOKENS = 384
_MAX_TARGET_TOKENS = 512
_TOKEN_BUDGET = 2048
_PLACEHOLDER = re.compile(r"__TLK_[A-Z_]+_[0-9]{4,}_[0-9A-F]{2}__")
_NUMBER = re.compile(r"(?:[$€£¥]\s*)?[+−-]?\d[\d.,:/%–−-]*(?:[A-Za-z]+)?")
_EDGES = re.compile(r"^(\W*)(.*?)(\W*)$", re.DOTALL)


@dataclass(frozen=True)
class _Piece:
    text: str
    literal: bool


class CTranslate2TranslationProvider:
    """Opt-in, offline EN→ID inference; protected spans never enter the model."""

    def __init__(
        self,
        *,
        model_dir: Path | None = None,
        fallback: Any = None,
    ) -> None:
        configured = os.environ.get("TRANSLOKA_CT2_MODEL_DIR")
        self._model_dir = model_dir or (Path(configured) if configured else None)
        self._fallback = fallback
        self._runtime: tuple[Any, Any, Any] | None = None
        self._lock = asyncio.Lock()
        self.fallback_segment_ids: tuple[str, ...] = ()
        self._suppressed_sequences: list[list[str]] = []

    async def health_check(self) -> ProviderHealth:
        try:
            await asyncio.to_thread(self._check_installation)
        except TranslationProviderError:
            return ProviderHealth(
                ProviderHealthStatus.UNAVAILABLE,
                detail="Provision the pinned local CTranslate2 model and optional runtime.",
            )
        return ProviderHealth(ProviderHealthStatus.AVAILABLE, version="4.6.0")

    async def list_models(self) -> list[LocalModel]:
        if (await self.health_check()).status is not ProviderHealthStatus.AVAILABLE:
            return []
        return [LocalModel(MODEL_ID)]

    def _check_installation(self) -> Path:
        # The manifest verifier checks the private path, revision, and every model byte.
        from .nmt_model import verify_model_directory

        try:
            if self._model_dir is None:
                raise ValueError("Local model is not configured.")
            directory = verify_model_directory(self._model_dir)
            ct2 = importlib.import_module("ctranslate2")
            sp = importlib.import_module("sentencepiece")
            if ct2.__version__ != "4.6.0" or sp.__version__ != "0.2.1":
                raise ValueError("Unsupported local NMT runtime.")
            return directory
        except Exception:
            raise _error(ProviderErrorCode.PROVIDER_UNAVAILABLE) from None

    def _load(self) -> tuple[Any, Any, Any]:
        if self._runtime is None:
            directory = self._check_installation()
            try:
                ct2 = importlib.import_module("ctranslate2")
                sp = importlib.import_module("sentencepiece")
                source = sp.SentencePieceProcessor(model_file=str(directory / "source.spm"))
                target = sp.SentencePieceProcessor(model_file=str(directory / "target.spm"))
                vocabulary = json.loads((directory / "shared_vocabulary.json").read_text())
                # Source digits are reassembled verbatim; decoding must not invent new ones.
                self._suppressed_sequences = [
                    [token] for token in vocabulary if any(char.isdigit() for char in token)
                ]
                translator = ct2.Translator(
                    str(directory),
                    device="cpu",
                    compute_type="int8",
                    inter_threads=1,
                    intra_threads=4,
                )
                self._runtime = (translator, source, target)
            except Exception:
                raise _error(ProviderErrorCode.PROVIDER_UNAVAILABLE) from None
        return self._runtime

    async def translate(
        self, request: object, *, cancellation: CancellationSignal | None = None
    ) -> str:
        _check_cancelled(cancellation)
        try:
            if not isinstance(request, TranslationPrompt):
                raise ValueError("A translation prompt is required.")
            data = TranslationRequest.from_dict(request.source_data["source_data"])
            if (data.context.source_language.lower(), data.context.target_language.lower()) != (
                "en",
                "id",
            ):
                raise ValueError("Unsupported language pair.")
            if len(data.segments) > 64 or sum(len(s.source_text) for s in data.segments) > 100_000:
                raise ValueError("Request is outside bounded inference limits.")
        except Exception:
            raise _error(ProviderErrorCode.INVALID_REQUEST) from None

        async with self._lock:
            _check_cancelled(cancellation)
            self.fallback_segment_ids = ()
            await _offload(self._load)
            try:
                outputs = await self._infer(data, beam_size=1, cancellation=cancellation)
                for index in range(len(data.segments)):
                    _check_cancelled(cancellation)
                    single = _single_request(data, index)
                    if _accepted(single, outputs[index]):
                        continue
                    # Retry only the failed segment, without discarding its healthy neighbors.
                    retry = await self._infer(single, beam_size=4, cancellation=cancellation)
                    outputs[index] = retry[0]
                    if not _accepted(single, outputs[index]) and self._fallback is not None:
                        outputs[index] = await self._local_fallback(single, cancellation)
                        if _accepted(single, outputs[index]):
                            self.fallback_segment_ids += single.segment_ids
                    if not _accepted(single, outputs[index]):
                        outputs[index] = ""
                _check_cancelled(cancellation)
                return json.dumps(
                    TranslationResponse(
                        tuple(
                            TranslatedSegment(segment.segment_id, text)
                            for segment, text in zip(data.segments, outputs, strict=True)
                        )
                    ).to_dict(),
                    ensure_ascii=False,
                )
            except (asyncio.CancelledError, TranslationProviderError):
                raise
            except Exception:
                raise _error(ProviderErrorCode.INVALID_RESPONSE) from None

    async def _local_fallback(
        self, request: TranslationRequest, cancellation: CancellationSignal | None
    ) -> str:
        # Only a local Ollama provider is permitted; never route failed book text to cloud.
        from .ollama import OllamaTranslationProvider

        if not isinstance(self._fallback, OllamaTranslationProvider):
            raise _error(ProviderErrorCode.INVALID_REQUEST)
        try:
            raw = await self._fallback.translate(
                VersionedPromptBuilder().build(request), cancellation=cancellation
            )
            response = TranslationResponse.from_dict(
                json.loads(raw), known_segment_ids=request.segment_ids
            )
            output = response.segments[0].translated_text
            return output if _accepted(request, output) else ""
        except asyncio.CancelledError:
            raise
        except Exception:
            return ""

    async def _infer(
        self,
        request: TranslationRequest,
        *,
        beam_size: int,
        cancellation: CancellationSignal | None,
    ) -> list[str]:
        translator, source, target = self._load()
        parts = [_protect(s.source_text, request) for s in request.segments]
        work: list[tuple[int, int, list[str]]] = []
        for owner, pieces in enumerate(parts):
            for position, piece in enumerate(pieces):
                if piece.literal:
                    continue
                tokens = list(source.encode(piece.text, out_type=str))
                offset = 0
                while offset < len(tokens):
                    end = min(offset + _MAX_SOURCE_TOKENS, len(tokens))
                    if end < len(tokens):
                        boundary = end
                        while boundary > offset and not tokens[boundary].startswith("▁"):
                            boundary -= 1
                        if boundary > offset:
                            end = boundary
                    work.append((owner, position, tokens[offset:end] + ["</s>"]))
                    offset = end
        translated: dict[tuple[int, int], list[str]] = {}
        invalid: set[int] = set()
        cursor = 0
        while cursor < len(work):
            _check_cancelled(cancellation)
            batch = []
            budget = 0
            while cursor < len(work) and budget + len(work[cursor][2]) <= _TOKEN_BUDGET:
                batch.append(work[cursor])
                budget += len(work[cursor][2])
                cursor += 1
            try:
                results = await _offload(
                    translator.translate_batch,
                    [item[2] for item in batch],
                    beam_size=beam_size,
                    max_input_length=0,
                    max_decoding_length=_MAX_TARGET_TOKENS,
                    batch_type="tokens",
                    max_batch_size=_TOKEN_BUDGET,
                    suppress_sequences=self._suppressed_sequences,
                )
                if len(results) != len(batch):
                    raise ValueError("Unexpected inference cardinality.")
            except Exception:
                invalid.update(owner for owner, _, _ in batch)
                continue
            _check_cancelled(cancellation)
            for (owner, position, _), result in zip(batch, results, strict=True):
                hypothesis = result.hypotheses[0]
                if not hypothesis or len(hypothesis) >= _MAX_TARGET_TOKENS or "<unk>" in hypothesis:
                    invalid.add(owner)
                    continue
                text = str(target.decode([t for t in hypothesis if t not in {"</s>", "<pad>"}]))
                # Fragment edges are restored separately; do not invent sentence breaks there.
                text = text.strip().rstrip(".,;:!?。")
                if not text:
                    invalid.add(owner)
                translated.setdefault((owner, position), []).append(text)
        outputs = []
        for owner, pieces in enumerate(parts):
            output = "".join(
                piece.text if piece.literal else " ".join(translated.get((owner, position), []))
                for position, piece in enumerate(pieces)
            )
            outputs.append("" if owner in invalid else output)
        return outputs


def _protect(text: str, request: TranslationRequest) -> list[_Piece]:
    candidates: list[tuple[int, int, str]] = []
    for pattern in (_PLACEHOLDER, _NUMBER):
        candidates.extend((m.start(), m.end(), m.group()) for m in pattern.finditer(text))
    candidates.extend((index, index + 1, char) for index, char in enumerate(text) if char.isdigit())
    candidates.extend(
        (item.start_offset, item.end_offset, item.source_value)
        for item in ProtectedContentDetector().detect(text)
    )
    glossary_candidates: list[tuple[int, int, str]] = []
    for entry in request.glossary:
        replacement = _glossary_value(entry.source_term, entry.target_term, entry.rule_type)
        if replacement is None:
            continue
        for match in re.finditer(r"(?<!\w)" + re.escape(entry.source_term) + r"(?!\w)", text):
            glossary_candidates.append((match.start(), match.end(), replacement))
    candidates = glossary_candidates + candidates
    selected: list[tuple[int, int, str]] = []
    for candidate in sorted(candidates, key=lambda item: (-(item[1] - item[0]), item[0])):
        if not any(candidate[0] < end and start < candidate[1] for start, end, _ in selected):
            selected.append(candidate)
    pieces: list[_Piece] = []
    offset = 0
    for start, end, value in sorted(selected):
        pieces.extend(_plain_pieces(text[offset:start]))
        pieces.append(_Piece(value, True))
        offset = end
    pieces.extend(_plain_pieces(text[offset:]))
    return pieces


def _plain_pieces(text: str) -> list[_Piece]:
    pieces = []
    # Keep sentence punctuation and whitespace outside decoding, including chunk boundaries.
    for sentence in re.split(r"(?<=[.!?])(?=\s)", text):
        match = _EDGES.fullmatch(sentence)
        if not match or not match.group(2):
            if sentence:
                pieces.append(_Piece(sentence, True))
        else:
            pieces.extend(
                _Piece(value, index != 1) for index, value in enumerate(match.groups()) if value
            )
    return pieces


def _glossary_value(source: str, target: str | None, rule: str) -> str | None:
    if rule in {"KEEP_ORIGINAL", "PRESERVE_ABBREVIATION"}:
        return source
    if rule == "IGNORE":
        return None
    if not target:
        raise _error(ProviderErrorCode.INVALID_REQUEST)
    if rule == "TRANSLATE_AS":
        return target
    if rule == "ORIGINAL_THEN_TRANSLATION":
        return f"{source} ({target})"
    if rule == "TRANSLATION_THEN_ORIGINAL":
        return f"{target} ({source})"
    raise _error(ProviderErrorCode.INVALID_REQUEST)


def _single_request(request: TranslationRequest, index: int) -> TranslationRequest:
    segment = request.segments[index]
    return TranslationRequest(
        segments=(segment,),
        context=request.context,
        glossary=request.glossary,
        placeholders=tuple(p for p in request.placeholders if p.segment_id == segment.segment_id),
        style=request.style,
    )


def _accepted(request: TranslationRequest, output: str) -> bool:
    response = TranslationResponse((TranslatedSegment(request.segments[0].segment_id, output),))
    if not validate_translation(request, response).accepted:
        return False
    source = request.segments[0].source_text
    if Counter(_NUMBER.findall(_PLACEHOLDER.sub("", source))) != Counter(
        _NUMBER.findall(_PLACEHOLDER.sub("", output))
    ):
        return False
    protected_inventory = Counter(
        piece.text
        for piece in _protect(source, request)
        if piece.literal and piece.text.strip() and any(c.isalnum() for c in piece.text)
    )
    for literal, count in protected_inventory.items():
        if output.count(literal) < count:
            return False
    return True


def _check_cancelled(signal: CancellationSignal | None) -> None:
    if signal is not None and signal.is_cancelled:
        raise asyncio.CancelledError


async def _offload(function: Callable[..., Any], *args: Any, **kwargs: Any) -> Any:
    task = asyncio.create_task(asyncio.to_thread(function, *args, **kwargs))
    try:
        return await asyncio.shield(task)
    except asyncio.CancelledError:
        # Native decoding is bounded but not interruptible; keep the lock until it drains.
        try:
            await task
        except Exception:
            pass
        raise


def _error(code: ProviderErrorCode) -> TranslationProviderError:
    return TranslationProviderError(
        code, "Local NMT operation could not be completed.", retryable=False
    )
