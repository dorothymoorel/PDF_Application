import asyncio
import json
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from time import sleep

import pytest
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient
from transloka_api.app import create_app
from transloka_api.middleware import (
    CLIENT_HEADER,
    CLIENT_HEADER_VALUE,
    CLIENT_VERSION_HEADER,
    CLIENT_VERSION_VALUE,
    REQUEST_ID_HEADER,
)
from transloka_translation.benchmark import QUICK_BENCHMARK_CASES
from transloka_translation.prompts import (
    PromptMessage,
    PromptRole,
    TranslationPrompt,
    build_translation_prompt,
)
from transloka_translation.providers import (
    ProviderErrorCode,
    ProviderHealthStatus,
    TranslationProviderError,
)
from transloka_translation.providers.ollama import (
    OllamaTranslationProvider,
    RemoteOllamaEndpointError,
)

REPOSITORY_ROOT = Path(__file__).parents[3]
ALEMBIC_CONFIGURATION = REPOSITORY_ROOT / "alembic.ini"
CLIENT_HEADERS = {
    CLIENT_HEADER: CLIENT_HEADER_VALUE,
    CLIENT_VERSION_HEADER: CLIENT_VERSION_VALUE,
}


@dataclass(frozen=True, slots=True)
class StubResponse:
    payload: object
    status: int = 200
    delay_seconds: float = 0
    headers: tuple[tuple[str, str], ...] = ()
    raw_body: bytes | None = None


@dataclass(frozen=True, slots=True)
class FakeOllama:
    base_url: str
    requests: list[tuple[str, str]]
    request_bodies: list[dict[str, object]]


@dataclass(slots=True)
class Cancellation:
    is_cancelled: bool = False


def _benchmark_request() -> object:
    return QUICK_BENCHMARK_CASES[0].to_request()


@contextmanager
def _fake_ollama(
    responses: Mapping[str, StubResponse],
) -> Iterator[FakeOllama]:
    recorded_requests: list[tuple[str, str]] = []
    recorded_bodies: list[dict[str, object]] = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            recorded_requests.append((self.command, self.path))
            self._write_response()

        def do_POST(self) -> None:
            recorded_requests.append((self.command, self.path))
            content_length = int(self.headers.get("Content-Length", "0"))
            body = json.loads(self.rfile.read(content_length).decode("utf-8"))
            assert isinstance(body, dict)
            recorded_bodies.append(body)
            self._write_response()

        def _write_response(self) -> None:
            response = responses.get(self.path, StubResponse({"error": "not found"}, status=404))
            if response.delay_seconds:
                sleep(response.delay_seconds)
            body = response.raw_body
            if body is None:
                body = json.dumps(response.payload).encode("utf-8")
            self.send_response(response.status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            for name, value in response.headers:
                self.send_header(name, value)
            self.end_headers()
            try:
                self.wfile.write(body)
            except OSError:
                pass

        def log_message(self, format_string: str, *arguments: object) -> None:
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield FakeOllama(
            base_url=f"http://127.0.0.1:{server.server_port}",
            requests=recorded_requests,
            request_bodies=recorded_bodies,
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


@pytest.fixture
def models_api(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path_factory: pytest.TempPathFactory,
) -> Callable[[OllamaTranslationProvider], TestClient]:
    monkeypatch.setenv("TRANSLOKA_DATA_DIR", str(tmp_path_factory.mktemp("models-api")))
    command.upgrade(Config(str(ALEMBIC_CONFIGURATION)), "head")

    def build(provider: OllamaTranslationProvider) -> TestClient:
        application = create_app()
        application.state.ollama_provider = provider
        return TestClient(application)

    return build


def test_local_endpoint_health_and_model_listing_use_read_only_requests() -> None:
    responses = {
        "/api/version": StubResponse({"version": "0.11.4"}),
        "/api/tags": StubResponse(
            {
                "models": [
                    {"name": "model-a:latest", "size": 1234},
                    {"name": "model-b:7b", "size": 5678},
                ]
            }
        ),
    }
    with _fake_ollama(responses) as fake:
        provider = OllamaTranslationProvider(fake.base_url)

        health = asyncio.run(provider.health_check())
        models = asyncio.run(provider.list_models())

    assert health.status is ProviderHealthStatus.AVAILABLE
    assert health.version == "0.11.4"
    assert [(model.name, model.size_bytes) for model in models] == [
        ("model-a:latest", 1234),
        ("model-b:7b", 5678),
    ]
    assert fake.requests == [("GET", "/api/version"), ("GET", "/api/tags")]


def test_empty_model_list_is_valid() -> None:
    with _fake_ollama({"/api/tags": StubResponse({"models": []})}) as fake:
        models = asyncio.run(OllamaTranslationProvider(fake.base_url).list_models())

    assert models == []


def test_invalid_model_response_is_normalized() -> None:
    with _fake_ollama({"/api/tags": StubResponse({"models": [{"name": "", "size": -1}]})}) as fake:
        with pytest.raises(TranslationProviderError) as raised:
            asyncio.run(OllamaTranslationProvider(fake.base_url).list_models())

    assert raised.value.code is ProviderErrorCode.INVALID_RESPONSE


@pytest.mark.parametrize(
    "base_url",
    (
        "https://127.0.0.1:11434",
        "http://example.com:11434",
        "http://192.168.1.10:11434",
        "http://user:password@127.0.0.1:11434",
        "http://127.0.0.1:11434/api",
    ),
)
def test_remote_or_unsafe_url_is_blocked_before_network_access(base_url: str) -> None:
    with pytest.raises(RemoteOllamaEndpointError, match="REMOTE_OLLAMA_BLOCKED"):
        OllamaTranslationProvider(base_url)


def test_provider_does_not_follow_redirects() -> None:
    responses = {
        "/api/tags": StubResponse(
            {},
            status=302,
            headers=(("Location", "/redirected"),),
        ),
        "/redirected": StubResponse({"models": []}),
    }
    with _fake_ollama(responses) as fake:
        with pytest.raises(TranslationProviderError) as raised:
            asyncio.run(OllamaTranslationProvider(fake.base_url).list_models())

    assert raised.value.code is ProviderErrorCode.PROVIDER_UNAVAILABLE
    assert fake.requests == [("GET", "/api/tags")]


def test_unavailable_local_endpoint_is_normalized() -> None:
    server = ThreadingHTTPServer(("127.0.0.1", 0), BaseHTTPRequestHandler)
    port = server.server_port
    server.server_close()
    provider = OllamaTranslationProvider(f"http://127.0.0.1:{port}", timeout_seconds=0.2)

    health = asyncio.run(provider.health_check())
    with pytest.raises(TranslationProviderError) as raised:
        asyncio.run(provider.list_models())

    assert health.status is ProviderHealthStatus.UNAVAILABLE
    assert health.detail in {
        ProviderErrorCode.PROVIDER_UNAVAILABLE.value,
        ProviderErrorCode.TIMEOUT.value,
    }
    assert raised.value.code in {
        ProviderErrorCode.PROVIDER_UNAVAILABLE,
        ProviderErrorCode.TIMEOUT,
    }


def test_timeout_is_normalized() -> None:
    with _fake_ollama({"/api/tags": StubResponse({"models": []}, delay_seconds=0.2)}) as fake:
        provider = OllamaTranslationProvider(fake.base_url, timeout_seconds=0.05)
        with pytest.raises(TranslationProviderError) as raised:
            asyncio.run(provider.list_models())

    assert raised.value.code is ProviderErrorCode.TIMEOUT


@pytest.mark.parametrize("model_name", ("", "   ", "bad\nmodel", "x" * 201))
def test_translation_rejects_invalid_bound_model_name(model_name: str) -> None:
    with pytest.raises(ValueError, match="model name"):
        OllamaTranslationProvider(model_name=model_name)


@pytest.mark.parametrize("temperature", (-0.01, 2.01, float("nan"), True))
def test_translation_rejects_invalid_temperature(temperature: object) -> None:
    with pytest.raises(ValueError, match="temperature"):
        OllamaTranslationProvider(temperature=temperature)  # type: ignore[arg-type]


@pytest.mark.parametrize("timeout", (0, 601, float("nan"), True))
def test_translation_rejects_invalid_translation_timeout(timeout: object) -> None:
    with pytest.raises(ValueError, match="translation timeout"):
        OllamaTranslationProvider(translation_timeout_seconds=timeout)  # type: ignore[arg-type]


def test_translation_requires_a_bound_model_before_network_access() -> None:
    with _fake_ollama({}) as fake:
        provider = OllamaTranslationProvider(fake.base_url)
        with pytest.raises(TranslationProviderError) as raised:
            asyncio.run(provider.translate(_benchmark_request()))

    assert raised.value.code is ProviderErrorCode.INVALID_REQUEST
    assert fake.requests == []


def test_translation_rejects_unknown_request_type_before_network_access() -> None:
    with _fake_ollama({}) as fake:
        provider = OllamaTranslationProvider(fake.base_url, model_name="model-a:latest")
        with pytest.raises(TranslationProviderError) as raised:
            asyncio.run(provider.translate({"source": "unsafe"}))

    assert raised.value.code is ProviderErrorCode.INVALID_REQUEST
    assert fake.requests == []


def test_translation_request_posts_structured_chat_payload() -> None:
    request = QUICK_BENCHMARK_CASES[0].to_request()
    response_text = json.dumps(
        {
            "segments": [
                {
                    "segment_id": "quick_001_general_prose",
                    "translated_text": "Aplikasi menyimpan setiap proyek secara terpisah.",
                }
            ]
        }
    )
    with _fake_ollama({"/api/chat": StubResponse({"message": {"content": response_text}})}) as fake:
        provider = OllamaTranslationProvider(
            fake.base_url,
            model_name="model-a:latest",
            temperature=0.25,
        )
        result = asyncio.run(provider.translate(request))

    assert result == response_text
    assert fake.requests == [("POST", "/api/chat")]
    assert len(fake.request_bodies) == 1
    payload = fake.request_bodies[0]
    assert payload["model"] == "model-a:latest"
    assert payload["stream"] is False
    assert payload["think"] is False
    assert payload["options"] == {"temperature": 0.25}
    messages = payload["messages"]
    assert isinstance(messages, list)
    assert len(messages) == 2
    system_message, user_message = messages
    assert isinstance(system_message, dict)
    assert isinstance(user_message, dict)
    assert [system_message["role"], user_message["role"]] == ["system", "user"]
    source_envelope = json.loads(user_message["content"])
    assert isinstance(source_envelope, dict)
    source_data = source_envelope["source_data"]
    assert isinstance(source_data, dict)
    segments = source_data["segments"]
    assert isinstance(segments, list)
    first_segment = segments[0]
    assert isinstance(first_segment, dict)
    assert first_segment["segment_id"] == "quick_001_general_prose"
    response_schema = payload["format"]
    assert isinstance(response_schema, dict)
    assert response_schema["additionalProperties"] is False
    properties = response_schema["properties"]
    assert isinstance(properties, dict)
    segments_property = properties["segments"]
    assert isinstance(segments_property, dict)
    segment_schema = segments_property["items"]
    assert isinstance(segment_schema, dict)
    assert segment_schema["additionalProperties"] is False
    item_properties = segment_schema["properties"]
    assert isinstance(item_properties, dict)
    segment_id_property = item_properties["segment_id"]
    assert isinstance(segment_id_property, dict)
    assert segment_id_property["enum"] == ["quick_001_general_prose"]


def test_translation_accepts_prebuilt_prompt() -> None:
    prompt = build_translation_prompt(QUICK_BENCHMARK_CASES[0].to_request())
    response_text = '{"segments":[]}'
    with _fake_ollama({"/api/chat": StubResponse({"message": {"content": response_text}})}) as fake:
        provider = OllamaTranslationProvider(fake.base_url, model_name="model-a:latest")
        result = asyncio.run(provider.translate(prompt))

    assert result == response_text
    assert fake.request_bodies[0]["format"] == prompt.response_schema


@pytest.mark.parametrize("response_schema_json", ("{", "[]"))
def test_translation_rejects_invalid_prebuilt_schema_before_network_access(
    response_schema_json: str,
) -> None:
    canonical = build_translation_prompt(QUICK_BENCHMARK_CASES[0].to_request())
    prompt = TranslationPrompt(
        prompt_version=canonical.prompt_version,
        messages=canonical.messages,
        response_schema_json=response_schema_json,
    )
    with _fake_ollama({}) as fake:
        provider = OllamaTranslationProvider(fake.base_url, model_name="model-a:latest")
        with pytest.raises(TranslationProviderError) as raised:
            asyncio.run(provider.translate(prompt))

    assert raised.value.code is ProviderErrorCode.INVALID_REQUEST
    assert str(raised.value) == "The translation request is invalid."
    assert fake.requests == []


@pytest.mark.parametrize(
    ("status", "expected_code", "retryable"),
    (
        (400, ProviderErrorCode.INVALID_REQUEST, False),
        (404, ProviderErrorCode.INVALID_REQUEST, False),
        (429, ProviderErrorCode.RATE_LIMIT, True),
        (500, ProviderErrorCode.PROVIDER_UNAVAILABLE, True),
        (302, ProviderErrorCode.PROVIDER_UNAVAILABLE, False),
    ),
)
def test_translation_normalizes_http_errors(
    status: int,
    expected_code: ProviderErrorCode,
    retryable: bool,
) -> None:
    secret = "source-response-secret"
    headers = (("Location", "/redirected"),) if status == 302 else ()
    responses = {
        "/api/chat": StubResponse({"error": secret}, status=status, headers=headers),
        "/redirected": StubResponse({"message": {"content": "redirect followed"}}),
    }
    with _fake_ollama(responses) as fake:
        provider = OllamaTranslationProvider(fake.base_url, model_name="model-a:latest")
        with pytest.raises(TranslationProviderError) as raised:
            asyncio.run(provider.translate(_benchmark_request()))

    assert raised.value.code is expected_code
    assert raised.value.retryable is retryable
    assert secret not in str(raised.value)
    assert raised.value.__cause__ is None
    assert fake.requests == [("POST", "/api/chat")]


@pytest.mark.parametrize(
    "response",
    (
        StubResponse({}, raw_body=b"{"),
        StubResponse([]),
        StubResponse({}),
        StubResponse({"message": None}),
        StubResponse({"message": {"content": ""}}),
        StubResponse({"message": {"content": 123}}),
    ),
)
def test_translation_rejects_invalid_outer_response(response: StubResponse) -> None:
    with _fake_ollama({"/api/chat": response}) as fake:
        provider = OllamaTranslationProvider(fake.base_url, model_name="model-a:latest")
        with pytest.raises(TranslationProviderError) as raised:
            asyncio.run(provider.translate(_benchmark_request()))

    assert raised.value.code is ProviderErrorCode.INVALID_RESPONSE


def test_translation_rejects_oversized_response() -> None:
    body = b'{"message":{"content":"' + (b"x" * (1024 * 1024)) + b'"}}'
    with _fake_ollama({"/api/chat": StubResponse({}, raw_body=body)}) as fake:
        provider = OllamaTranslationProvider(fake.base_url, model_name="model-a:latest")
        with pytest.raises(TranslationProviderError) as raised:
            asyncio.run(provider.translate(_benchmark_request()))

    assert raised.value.code is ProviderErrorCode.INVALID_RESPONSE


def test_translation_rejects_oversized_request_before_network_access() -> None:
    canonical = build_translation_prompt(QUICK_BENCHMARK_CASES[0].to_request())
    oversized = TranslationPrompt(
        prompt_version=canonical.prompt_version,
        messages=(
            canonical.messages[0],
            PromptMessage(role=PromptRole.USER, content="x" * (1024 * 1024)),
        ),
        response_schema_json=canonical.response_schema_json,
    )
    with _fake_ollama({}) as fake:
        provider = OllamaTranslationProvider(fake.base_url, model_name="model-a:latest")
        with pytest.raises(TranslationProviderError) as raised:
            asyncio.run(provider.translate(oversized))

    assert raised.value.code is ProviderErrorCode.INVALID_REQUEST
    assert fake.requests == []


def test_translation_timeout_is_retryable() -> None:
    with _fake_ollama(
        {
            "/api/chat": StubResponse(
                {"message": {"content": "{}"}},
                delay_seconds=0.2,
            )
        }
    ) as fake:
        provider = OllamaTranslationProvider(
            fake.base_url,
            model_name="model-a:latest",
            translation_timeout_seconds=0.05,
        )
        with pytest.raises(TranslationProviderError) as raised:
            asyncio.run(provider.translate(_benchmark_request()))

    assert raised.value.code is ProviderErrorCode.TIMEOUT
    assert raised.value.retryable is True


def test_translation_honors_cancellation_before_dispatch() -> None:
    with _fake_ollama({}) as fake:
        provider = OllamaTranslationProvider(fake.base_url, model_name="model-a:latest")
        with pytest.raises(asyncio.CancelledError):
            asyncio.run(
                provider.translate(
                    _benchmark_request(),
                    cancellation=Cancellation(is_cancelled=True),
                )
            )

    assert fake.requests == []


def test_translation_honors_cancellation_while_awaiting_response() -> None:
    signal = Cancellation()

    async def cancel_during_request(provider: OllamaTranslationProvider) -> float:
        loop = asyncio.get_running_loop()
        started = loop.time()
        task = asyncio.create_task(provider.translate(_benchmark_request(), cancellation=signal))
        await asyncio.sleep(0.05)
        signal.is_cancelled = True
        with pytest.raises(asyncio.CancelledError):
            await task
        return loop.time() - started

    with _fake_ollama(
        {
            "/api/chat": StubResponse(
                {"message": {"content": "{}"}},
                delay_seconds=0.5,
            )
        }
    ) as fake:
        provider = OllamaTranslationProvider(
            fake.base_url,
            model_name="model-a:latest",
            translation_timeout_seconds=1,
        )
        elapsed = asyncio.run(cancel_during_request(provider))

    assert elapsed < 0.3


def test_translation_propagates_direct_coroutine_cancellation() -> None:
    async def cancel_task(provider: OllamaTranslationProvider) -> None:
        task = asyncio.create_task(provider.translate(_benchmark_request()))
        await asyncio.sleep(0.05)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task

    with _fake_ollama(
        {
            "/api/chat": StubResponse(
                {"message": {"content": "{}"}},
                delay_seconds=0.2,
            )
        }
    ) as fake:
        provider = OllamaTranslationProvider(fake.base_url, model_name="model-a:latest")
        asyncio.run(cancel_task(provider))


def test_models_router_exposes_health_and_detected_models(
    models_api: Callable[[OllamaTranslationProvider], TestClient],
) -> None:
    responses = {
        "/api/version": StubResponse({"version": "0.11.4"}),
        "/api/tags": StubResponse({"models": [{"name": "model-a:latest", "size": 1234}]}),
    }
    with (
        _fake_ollama(responses) as fake,
        models_api(OllamaTranslationProvider(fake.base_url)) as client,
    ):
        health = client.get(
            "/api/v1/models/ollama/health",
            headers={REQUEST_ID_HEADER: "ollama-health"},
        )
        refresh = client.post(
            "/api/v1/models/refresh",
            headers={**CLIENT_HEADERS, REQUEST_ID_HEADER: "ollama-refresh"},
        )
        models = client.get(
            "/api/v1/models",
            headers={REQUEST_ID_HEADER: "ollama-models"},
        )

    assert health.status_code == 200
    assert health.json() == {
        "data": {
            "status": "AVAILABLE",
            "base_url": fake.base_url,
            "version": "0.11.4",
        },
        "meta": {"request_id": "ollama-health"},
    }
    assert refresh.status_code == 200
    assert refresh.json()["data"][0]["id"].startswith("mdl_")
    assert refresh.json()["meta"]["request_id"] == "ollama-refresh"
    assert models.status_code == 200
    assert models.json()["data"][0] == {
        "id": refresh.json()["data"][0]["id"],
        "ollama_model_name": "model-a:latest",
        "model_family": None,
        "parameter_class": None,
        "quantization": None,
        "disk_size_bytes": 1234,
        "license_status": "UNKNOWN",
        "is_installed": True,
        "is_selected_translation": False,
        "is_selected_validation": False,
    }
    assert models.json()["meta"]["request_id"] == "ollama-models"


def test_models_router_normalizes_local_service_failure(
    models_api: Callable[[OllamaTranslationProvider], TestClient],
) -> None:
    responses = {
        "/api/version": StubResponse({}, status=503),
        "/api/tags": StubResponse({}, status=503),
    }
    with (
        _fake_ollama(responses) as fake,
        models_api(OllamaTranslationProvider(fake.base_url)) as client,
    ):
        health = client.get("/api/v1/models/ollama/health")
        models = client.post("/api/v1/models/refresh", headers=CLIENT_HEADERS)

    assert health.status_code == 200
    assert health.json()["data"]["status"] == "UNAVAILABLE"
    assert health.json()["data"]["version"] == "unknown"
    assert models.status_code == 503
    assert models.json()["error"]["code"] == "OLLAMA_UNAVAILABLE"
    assert fake.requests == [("GET", "/api/version"), ("GET", "/api/tags")]


def test_refresh_preserves_ids_marks_missing_models_and_warns_for_unknown_license(
    models_api: Callable[[OllamaTranslationProvider], TestClient],
) -> None:
    responses = {
        "/api/version": StubResponse({"version": "0.11.4"}),
        "/api/tags": StubResponse(
            {
                "models": [
                    {"name": "model-a:latest", "size": 100},
                    {"name": "model-b:latest", "size": 200},
                ]
            }
        ),
    }
    with (
        _fake_ollama(responses) as fake,
        models_api(OllamaTranslationProvider(fake.base_url)) as client,
    ):
        first = client.post("/api/v1/models/refresh", headers=CLIENT_HEADERS)
        first_ids = {item["ollama_model_name"]: item["id"] for item in first.json()["data"]}
        responses["/api/tags"] = StubResponse({"models": [{"name": "model-a:latest", "size": 150}]})
        second = client.post("/api/v1/models/refresh", headers=CLIENT_HEADERS)
        installed = client.get("/api/v1/models", params={"installed": "true"})
        missing = client.get("/api/v1/models", params={"installed": "false"})

    second_by_name = {item["ollama_model_name"]: item for item in second.json()["data"]}
    assert second_by_name["model-a:latest"]["id"] == first_ids["model-a:latest"]
    assert second_by_name["model-a:latest"]["disk_size_bytes"] == 150
    assert second_by_name["model-a:latest"]["is_installed"] is True
    assert second_by_name["model-b:latest"]["id"] == first_ids["model-b:latest"]
    assert second_by_name["model-b:latest"]["is_installed"] is False
    assert {warning["code"] for warning in second.json()["meta"]["warnings"]} == {
        "MODEL_LICENSE_UNKNOWN"
    }
    assert [item["ollama_model_name"] for item in installed.json()["data"]] == ["model-a:latest"]
    assert [item["ollama_model_name"] for item in missing.json()["data"]] == ["model-b:latest"]
    assert fake.requests == [("GET", "/api/tags"), ("GET", "/api/tags")]


def test_selection_is_unique_per_role_and_unknown_license_remains_visible(
    models_api: Callable[[OllamaTranslationProvider], TestClient],
) -> None:
    responses = {
        "/api/version": StubResponse({"version": "0.11.4"}),
        "/api/tags": StubResponse(
            {
                "models": [
                    {"name": "model-a:latest", "size": 100},
                    {"name": "model-b:latest", "size": 200},
                ]
            }
        ),
    }
    with (
        _fake_ollama(responses) as fake,
        models_api(OllamaTranslationProvider(fake.base_url)) as client,
    ):
        refreshed = client.post("/api/v1/models/refresh", headers=CLIENT_HEADERS)
        ids = {item["ollama_model_name"]: item["id"] for item in refreshed.json()["data"]}
        client.post(
            f"/api/v1/models/{ids['model-a:latest']}/select",
            headers=CLIENT_HEADERS,
            json={"role": "TRANSLATION"},
        )
        translation = client.post(
            f"/api/v1/models/{ids['model-b:latest']}/select",
            headers=CLIENT_HEADERS,
            json={"role": "TRANSLATION"},
        )
        validation = client.post(
            f"/api/v1/models/{ids['model-a:latest']}/select",
            headers=CLIENT_HEADERS,
            json={"role": "VALIDATION"},
        )
        translation_models = client.get(
            "/api/v1/models",
            params={"selected_for_translation": "true"},
        )
        validation_models = client.get(
            "/api/v1/models",
            params={"selected_for_validation": "true"},
        )

    assert translation.status_code == 200
    assert translation.json()["data"]["id"] == ids["model-b:latest"]
    assert translation.json()["data"]["is_selected_translation"] is True
    assert translation.json()["meta"]["warnings"][0]["code"] == "MODEL_LICENSE_UNKNOWN"
    assert validation.status_code == 200
    assert validation.json()["data"]["id"] == ids["model-a:latest"]
    assert validation.json()["data"]["is_selected_validation"] is True
    assert [item["id"] for item in translation_models.json()["data"]] == [ids["model-b:latest"]]
    assert [item["id"] for item in validation_models.json()["data"]] == [ids["model-a:latest"]]


def test_missing_or_uninstalled_model_cannot_be_selected(
    models_api: Callable[[OllamaTranslationProvider], TestClient],
) -> None:
    responses = {
        "/api/version": StubResponse({"version": "0.11.4"}),
        "/api/tags": StubResponse({"models": [{"name": "model-a:latest", "size": 100}]}),
    }
    with (
        _fake_ollama(responses) as fake,
        models_api(OllamaTranslationProvider(fake.base_url)) as client,
    ):
        refreshed = client.post("/api/v1/models/refresh", headers=CLIENT_HEADERS)
        model_id = refreshed.json()["data"][0]["id"]
        client.post(
            f"/api/v1/models/{model_id}/select",
            headers=CLIENT_HEADERS,
            json={"role": "TRANSLATION"},
        )
        missing = client.post(
            "/api/v1/models/mdl_550e8400-e29b-41d4-a716-446655440000/select",
            headers=CLIENT_HEADERS,
            json={"role": "TRANSLATION"},
        )
        responses["/api/tags"] = StubResponse({"models": []})
        client.post("/api/v1/models/refresh", headers=CLIENT_HEADERS)
        persisted = client.get("/api/v1/models", params={"installed": "false"})
        uninstalled = client.post(
            f"/api/v1/models/{model_id}/select",
            headers=CLIENT_HEADERS,
            json={"role": "TRANSLATION"},
        )

    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "MODEL_NOT_FOUND"
    assert uninstalled.status_code == 409
    assert uninstalled.json()["error"]["code"] == "OLLAMA_MODEL_NOT_INSTALLED"
    assert persisted.json()["data"][0]["is_selected_translation"] is False
    assert persisted.json()["data"][0]["is_selected_validation"] is False


def test_selection_requires_available_ollama_health(
    models_api: Callable[[OllamaTranslationProvider], TestClient],
) -> None:
    responses = {
        "/api/version": StubResponse({"version": "0.11.4"}),
        "/api/tags": StubResponse({"models": [{"name": "model-a:latest", "size": 100}]}),
    }
    with (
        _fake_ollama(responses) as fake,
        models_api(OllamaTranslationProvider(fake.base_url)) as client,
    ):
        refreshed = client.post("/api/v1/models/refresh", headers=CLIENT_HEADERS)
        model_id = refreshed.json()["data"][0]["id"]
        responses["/api/version"] = StubResponse({}, status=503)
        selected = client.post(
            f"/api/v1/models/{model_id}/select",
            headers=CLIENT_HEADERS,
            json={"role": "TRANSLATION"},
        )

    assert selected.status_code == 503
    assert selected.json()["error"]["code"] == "OLLAMA_UNAVAILABLE"


def test_models_router_blocks_remote_configuration(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    monkeypatch.setenv("TRANSLOKA_DATA_DIR", str(tmp_path_factory.mktemp("blocked-models-api")))
    monkeypatch.setenv("TRANSLOKA_OLLAMA_URL", "http://example.com:11434")
    application = create_app()

    with TestClient(application) as client:
        blocked = client.get("/api/v1/models/ollama/health")

    assert blocked.status_code == 403
    assert blocked.json()["error"]["code"] == "REMOTE_OLLAMA_BLOCKED"
