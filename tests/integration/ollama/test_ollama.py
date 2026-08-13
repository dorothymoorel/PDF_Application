import asyncio
import json
from collections.abc import Callable, Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from threading import Thread
from time import sleep

import pytest
from fastapi.testclient import TestClient
from transloka_api.app import create_app
from transloka_api.middleware import REQUEST_ID_HEADER
from transloka_api.routers.models import router
from transloka_translation.providers import (
    ProviderErrorCode,
    ProviderHealthStatus,
    TranslationProviderError,
)
from transloka_translation.providers.ollama import (
    OllamaTranslationProvider,
    RemoteOllamaEndpointError,
)


@dataclass(frozen=True, slots=True)
class StubResponse:
    payload: object
    status: int = 200
    delay_seconds: float = 0
    headers: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True, slots=True)
class FakeOllama:
    base_url: str
    requests: list[tuple[str, str]]


@contextmanager
def _fake_ollama(
    responses: Mapping[str, StubResponse],
) -> Iterator[FakeOllama]:
    recorded_requests: list[tuple[str, str]] = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            recorded_requests.append((self.command, self.path))
            response = responses.get(self.path, StubResponse({"error": "not found"}, status=404))
            if response.delay_seconds:
                sleep(response.delay_seconds)
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

    def build(provider: OllamaTranslationProvider) -> TestClient:
        application = create_app()
        application.state.ollama_provider = provider
        application.include_router(router)
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
    assert models.status_code == 200
    assert models.json() == {
        "data": [{"ollama_model_name": "model-a:latest", "disk_size_bytes": 1234}],
        "meta": {"request_id": "ollama-models"},
    }


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
        models = client.get("/api/v1/models")

    assert health.status_code == 200
    assert health.json()["data"]["status"] == "UNAVAILABLE"
    assert health.json()["data"]["version"] == "unknown"
    assert models.status_code == 503
    assert models.json()["error"]["code"] == "OLLAMA_UNAVAILABLE"
    assert fake.requests == [("GET", "/api/version"), ("GET", "/api/tags")]


def test_models_router_blocks_remote_configuration(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path_factory: pytest.TempPathFactory,
) -> None:
    monkeypatch.setenv("TRANSLOKA_DATA_DIR", str(tmp_path_factory.mktemp("blocked-models-api")))
    monkeypatch.setenv("TRANSLOKA_OLLAMA_URL", "http://example.com:11434")
    application = create_app()
    application.include_router(router)

    with TestClient(application) as client:
        blocked = client.get("/api/v1/models")

    assert blocked.status_code == 403
    assert blocked.json()["error"]["code"] == "REMOTE_OLLAMA_BLOCKED"
