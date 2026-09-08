import asyncio
import json
import threading
from datetime import UTC, datetime, timedelta
from email.message import Message
from email.utils import format_datetime
from io import BytesIO
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import ProxyHandler, Request

import pytest
from transloka_translation.prompts import build_translation_prompt
from transloka_translation.providers import (
    ProviderErrorCode,
    TranslationProvider,
    TranslationProviderError,
    groq,
)
from transloka_translation.providers.groq import GroqTranslationProvider
from transloka_translation.schemas import TranslationRequest


def request(text: str = "Read the book.") -> TranslationRequest:
    return TranslationRequest.from_dict(
        {
            "segments": [{"segment_id": "s1", "source_text": text}],
            "context": {"source_language": "en", "target_language": "id"},
            "glossary": [],
            "placeholders": [],
            "style": "PROFESSIONAL",
        }
    )


def completion(content: object = None, finish: str = "stop") -> dict[str, object]:
    if content is None:
        content = json.dumps({"segments": [{"segment_id": "s1", "translated_text": "Baca buku."}]})
    return {"choices": [{"finish_reason": finish, "message": {"content": content}}]}


def provider(**kwargs: Any) -> GroqTranslationProvider:
    return GroqTranslationProvider(
        enabled=True, cloud_consent=True, model_name=groq.GROQ_MODELS[0], **kwargs
    )


class Response(BytesIO):
    def read1(self, size: int | None = -1) -> bytes:
        return self.read(size)


@pytest.fixture
def transport(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    state: dict[str, Any] = {"response": completion(), "calls": []}
    monkeypatch.setenv("GROQ_API_KEY", "test-key-never-log")

    class Opener:
        def open(self, req: Any, timeout: float) -> Response:
            state["calls"].append(req)
            assert 0 < timeout <= 120
            if "error" in state:
                raise state["error"]
            if "wait" in state:
                state["started"].set()
                state["wait"].wait(1)
            body = state.get("body", json.dumps(state["response"]).encode())
            return Response(body)

    def build(*handlers: Any) -> Opener:
        assert isinstance(handlers[0], ProxyHandler) and vars(handlers[0])["proxies"] == {}
        assert isinstance(handlers[1], groq._RejectRedirects)
        return Opener()

    monkeypatch.setattr(groq, "build_opener", build)
    return state


@pytest.mark.parametrize("prompt", [False, True])
def test_translate_uses_fixed_https_strict_schema_and_existing_contract(
    transport: dict[str, Any], prompt: bool
) -> None:
    instance = provider()
    assert isinstance(instance, TranslationProvider)
    data = request()
    result = asyncio.run(instance.translate(build_translation_prompt(data) if prompt else data))
    assert json.loads(result)["segments"][0]["translated_text"] == "Baca buku."
    sent = transport["calls"][0]
    assert len(transport["calls"]) == 1
    assert sent.full_url == "https://api.groq.com/openai/v1/chat/completions"
    assert sent.get_header("Authorization") == "Bearer test-key-never-log"
    body = json.loads(sent.data)
    assert body["stream"] is False and "tools" not in body
    assert body["reasoning_effort"] == "none"
    schema = body["response_format"]["json_schema"]
    assert schema["strict"] is True
    assert schema["schema"]["additionalProperties"] is False
    assert schema["schema"]["properties"]["segments"]["items"]["additionalProperties"] is False
    assert "test-key-never-log" not in repr(instance) + sent.data.decode() + result


@pytest.mark.parametrize("settings", [{}, {"enabled": True}, {"cloud_consent": True}])
def test_disabled_or_unconsented_translation_never_sends(
    transport: dict[str, Any], settings: dict[str, bool]
) -> None:
    instance = GroqTranslationProvider(model_name=groq.GROQ_MODELS[0], **settings)
    with pytest.raises(TranslationProviderError):
        asyncio.run(instance.translate(request()))
    assert transport["calls"] == []


def test_disabled_discovery_and_missing_key_never_send(
    transport: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    assert asyncio.run(GroqTranslationProvider().health_check()).status.value == "UNAVAILABLE"
    monkeypatch.delenv("GROQ_API_KEY")
    with pytest.raises(TranslationProviderError) as exc:
        asyncio.run(provider().translate(request()))
    assert exc.value.code == ProviderErrorCode.AUTHENTICATION_FAILED
    assert transport["calls"] == []


@pytest.mark.parametrize("key", ["", "secret\r\nHeader: injected", "white space", "ä", "x" * 513])
def test_bad_credentials_rejected_before_network(
    transport: dict[str, Any], monkeypatch: pytest.MonkeyPatch, key: str
) -> None:
    monkeypatch.setenv("GROQ_API_KEY", key)
    with pytest.raises(TranslationProviderError):
        asyncio.run(provider().list_models())
    assert not transport["calls"]


def test_discovery_filters_models_and_health_detects_missing_selection(
    transport: dict[str, Any],
) -> None:
    transport["response"] = {
        "data": [
            {"id": "unexpected"},
            {"id": groq.GROQ_MODELS[1]},
            {"id": groq.GROQ_MODELS[0], "active": False},
        ]
    }
    instance = provider()
    models = asyncio.run(instance.list_models())
    assert [(model.name, model.size_bytes) for model in models] == [(groq.GROQ_MODELS[1], None)]
    assert asyncio.run(instance.health_check()).status.value == "UNAVAILABLE"
    transport["response"] = {"data": [{"id": groq.GROQ_MODELS[0]}]}
    assert asyncio.run(instance.health_check()).status.value == "AVAILABLE"
    assert all(req.full_url.endswith("/models") and req.data is None for req in transport["calls"])


@pytest.mark.parametrize(
    "status,code,retryable",
    [
        (400, "INVALID_REQUEST", False),
        (401, "AUTHENTICATION_FAILED", False),
        (403, "AUTHENTICATION_FAILED", False),
        (404, "INVALID_REQUEST", False),
        (429, "RATE_LIMIT", True),
        (503, "PROVIDER_UNAVAILABLE", True),
        (302, "PROVIDER_UNAVAILABLE", False),
    ],
)
def test_http_errors_are_sanitized_without_automatic_retry(
    transport: dict[str, Any], status: int, code: str, retryable: bool
) -> None:
    headers = Message()
    headers["Retry-After"] = "12"
    stream = BytesIO(b"secret provider response")
    transport["error"] = HTTPError("https://secret.invalid", status, "secret text", headers, stream)
    with pytest.raises(TranslationProviderError) as exc:
        asyncio.run(provider().translate(request()))
    assert exc.value.code.value == code and exc.value.retryable is retryable
    assert exc.value.retry_after_seconds == (12 if retryable else None)
    assert "secret" not in str(exc.value)
    assert exc.value.__suppress_context__
    assert stream.closed and len(transport["calls"]) == 1


@pytest.mark.parametrize(
    "body",
    [b"invalid", b"[]", b' {"x":1,"x":2}', b'{"x":NaN}', b"\xff", b"x" * (1024 * 1024 + 1)],
    ids=["invalid", "array", "duplicate", "nan", "encoding", "oversize"],
)
def test_rejects_invalid_or_oversize_http_json(transport: dict[str, Any], body: bytes) -> None:
    transport["body"] = body
    with pytest.raises(TranslationProviderError) as exc:
        asyncio.run(provider().translate(request()))
    assert exc.value.code == ProviderErrorCode.INVALID_RESPONSE


@pytest.mark.parametrize(
    "payload",
    [
        completion(finish="length"),
        completion(content="not JSON"),
        completion(content="{}"),
        completion(content='{"segments":[{"segment_id":"wrong","translated_text":"x"}]}'),
        completion(
            content='{"segments":[{"segment_id":"s1","translated_text":"x"},{"segment_id":"s1","translated_text":"y"}]}'
        ),
        {"choices": []},
        {"choices": [None]},
    ],
)
def test_rejects_incomplete_or_wrong_segment_responses(
    transport: dict[str, Any], payload: object
) -> None:
    transport["response"] = payload
    with pytest.raises(TranslationProviderError) as exc:
        asyncio.run(provider().translate(request()))
    assert exc.value.code == ProviderErrorCode.INVALID_RESPONSE


def test_refusal_is_not_a_translation(transport: dict[str, Any]) -> None:
    transport["response"] = {
        "choices": [{"finish_reason": "stop", "message": {"refusal": "secret refusal"}}]
    }
    with pytest.raises(TranslationProviderError) as exc:
        asyncio.run(provider().translate(request()))
    assert exc.value.code == ProviderErrorCode.CONTENT_REJECTED


def test_request_size_bound_before_network(transport: dict[str, Any]) -> None:
    with pytest.raises(TranslationProviderError) as exc:
        asyncio.run(provider().translate(request("x" * (1024 * 1024))))
    assert exc.value.code == ProviderErrorCode.INVALID_REQUEST
    assert not transport["calls"]


@pytest.mark.parametrize(
    "error,code",
    [
        (TimeoutError("secret"), "TIMEOUT"),
        (URLError(TimeoutError()), "TIMEOUT"),
        (URLError("secret"), "PROVIDER_UNAVAILABLE"),
    ],
)
def test_transport_errors_normalized(
    transport: dict[str, Any], error: Exception, code: str
) -> None:
    transport["error"] = error
    with pytest.raises(TranslationProviderError) as exc:
        asyncio.run(provider().translate(request()))
    assert exc.value.code.value == code and "secret" not in str(exc.value)


@pytest.mark.parametrize("cancel", [False, True])
def test_deadline_or_cancellation_discards_late_result(
    transport: dict[str, Any], cancel: bool
) -> None:
    class Signal:
        is_cancelled = False

    signal = Signal()
    transport["wait"] = threading.Event()
    transport["started"] = threading.Event()

    async def run() -> None:
        task = asyncio.create_task(
            provider(timeout_seconds=0.2).translate(request(), cancellation=signal)
        )
        while not transport["started"].is_set():
            await asyncio.sleep(0.001)
        signal.is_cancelled = cancel
        try:
            if cancel:
                with pytest.raises(asyncio.CancelledError):
                    await asyncio.wait_for(task, 0.5)
            else:
                with pytest.raises(TranslationProviderError) as exc:
                    await asyncio.wait_for(task, 0.5)
                assert exc.value.code == ProviderErrorCode.TIMEOUT
        finally:
            transport["wait"].set()

    asyncio.run(run())
    assert len(transport["calls"]) == 1


def test_pre_cancelled_request_never_sends(transport: dict[str, Any]) -> None:
    signal = threading.Event()
    signal.is_cancelled = True  # type: ignore[attr-defined]
    with pytest.raises(asyncio.CancelledError):
        asyncio.run(provider().translate(request(), cancellation=signal))  # type: ignore[arg-type]
    assert not transport["calls"]


def test_redirect_handler_does_not_follow() -> None:
    assert (
        groq._RejectRedirects().redirect_request(
            Request("https://api.groq.com"), BytesIO(), 302, "", Message(), "https://other.invalid"
        )
        is None
    )


@pytest.mark.parametrize("value", [None, "bad", "nan", "inf", "9" * 129])
def test_invalid_retry_after_ignored(value: str | None) -> None:
    assert groq._retry_after(value) is None


def test_retry_after_seconds_and_http_date() -> None:
    assert groq._retry_after("2") == 2
    assert groq._retry_after("-2") == 0
    assert groq._retry_after("900000") == 86400
    date = format_datetime(datetime.now(UTC) + timedelta(seconds=60))
    assert 58 <= (groq._retry_after(date) or 0) <= 60


@pytest.mark.parametrize(
    "settings",
    [
        {"enabled": "true"},
        {"model_name": "unexpected"},
        {"timeout_seconds": float("nan")},
        {"timeout_seconds": True},
        {"timeout_seconds": 121},
    ],
)
def test_configuration_rejects_invalid_values(settings: dict[str, Any]) -> None:
    with pytest.raises(ValueError):
        GroqTranslationProvider(**settings)
