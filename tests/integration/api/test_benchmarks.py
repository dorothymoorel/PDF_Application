import asyncio
import json
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from typing import cast

import pytest
from alembic import command
from alembic.config import Config
from fastapi import FastAPI
from fastapi.testclient import TestClient
from transloka_api.app import create_app
from transloka_api.middleware import (
    CLIENT_HEADER,
    CLIENT_HEADER_VALUE,
    CLIENT_VERSION_HEADER,
    CLIENT_VERSION_VALUE,
)

REPOSITORY_ROOT = Path(__file__).parents[3]
ALEMBIC_CONFIGURATION = REPOSITORY_ROOT / "alembic.ini"
CLIENT_HEADERS = {
    CLIENT_HEADER: CLIENT_HEADER_VALUE,
    CLIENT_VERSION_HEADER: CLIENT_VERSION_VALUE,
}


@dataclass(frozen=True, slots=True)
class FakeBenchmarkOllama:
    base_url: str
    requests: list[tuple[str, str]]
    chat_bodies: list[dict[str, object]]
    installed_models: list[str]


@contextmanager
def _fake_benchmark_ollama() -> Iterator[FakeBenchmarkOllama]:
    requests: list[tuple[str, str]] = []
    chat_bodies: list[dict[str, object]] = []
    installed_models = ["model-a:latest"]

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            requests.append((self.command, self.path))
            if self.path == "/api/version":
                self._write_json({"version": "test"})
                return
            if self.path == "/api/tags":
                self._write_json(
                    {
                        "models": [
                            {"name": model_name, "size": 100} for model_name in installed_models
                        ]
                    }
                )
                return
            self._write_json({"error": "not found"}, status=404)

        def do_POST(self) -> None:
            requests.append((self.command, self.path))
            if self.path != "/api/chat":
                self._write_json({"error": "not found"}, status=404)
                return
            content_length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(content_length).decode("utf-8"))
            assert isinstance(payload, dict)
            chat_bodies.append(payload)
            messages = payload["messages"]
            assert isinstance(messages, list)
            user_message = messages[1]
            assert isinstance(user_message, dict)
            source_envelope = json.loads(user_message["content"])
            source_data = source_envelope["source_data"]
            source_segment = source_data["segments"][0]
            response = {
                "segments": [
                    {
                        "segment_id": source_segment["segment_id"],
                        "translated_text": source_segment["source_text"],
                    }
                ]
            }
            self._write_json({"message": {"content": json.dumps(response)}})

        def _write_json(self, payload: object, *, status: int = 200) -> None:
            body = json.dumps(payload).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format_string: str, *arguments: object) -> None:
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield FakeBenchmarkOllama(
            base_url=f"http://127.0.0.1:{server.server_port}",
            requests=requests,
            chat_bodies=chat_bodies,
            installed_models=installed_models,
        )
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


@pytest.fixture
def benchmark_api(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> Iterator[tuple[TestClient, FakeBenchmarkOllama]]:
    root = tmp_path / "benchmark api"
    monkeypatch.setenv("TRANSLOKA_DATA_DIR", str(root))
    with _fake_benchmark_ollama() as fake:
        monkeypatch.setenv("TRANSLOKA_OLLAMA_URL", fake.base_url)
        command.upgrade(Config(str(ALEMBIC_CONFIGURATION)), "head")
        with TestClient(create_app()) as client:
            yield client, fake


def _refresh_model(client: TestClient) -> str:
    response = client.post("/api/v1/models/refresh", headers=CLIENT_HEADERS)
    assert response.status_code == 200
    model_id = response.json()["data"][0]["id"]
    assert isinstance(model_id, str)
    return model_id


def test_production_app_runs_quick_benchmark_for_persisted_model(
    benchmark_api: tuple[TestClient, FakeBenchmarkOllama],
) -> None:
    client, fake = benchmark_api
    model_id = _refresh_model(client)

    response = client.post(
        f"/api/v1/models/{model_id}/benchmarks/quick",
        headers={**CLIENT_HEADERS, "Idempotency-Key": "production-quick-1"},
        json={
            "dataset_version": "translation_benchmark_en_id_0.1",
            "temperature": 0.25,
            "batch_sizes": [1, 5],
        },
    )

    assert response.status_code == 202
    result = response.json()["data"]
    assert result["model_id"] == model_id
    assert result["benchmark_id"] == f"{model_id}:production-quick-1"
    assert result["status"] == "COMPLETED"
    assert result["recommendation"] == "RECOMMENDED_DEFAULT"
    assert result["successful_cases"] == 6
    assert result["failed_cases"] == 0
    assert len(fake.chat_bodies) == 6
    assert all(body["model"] == "model-a:latest" for body in fake.chat_bodies)
    assert all(body["options"] == {"temperature": 0.25} for body in fake.chat_bodies)


def test_production_app_exposes_full_benchmark_for_persisted_model(
    benchmark_api: tuple[TestClient, FakeBenchmarkOllama],
) -> None:
    client, fake = benchmark_api
    model_id = _refresh_model(client)
    application = cast(FastAPI, client.app)

    result = asyncio.run(
        application.state.full_benchmark_runner.run(
            model_id,
            dataset_version="translation_benchmark_en_id_0.1",
            temperature=0.0,
            batch_sizes=[1, 5],
            context_lengths=["SHORT", "MEDIUM", "LONG"],
            benchmark_id=f"{model_id}:production-full-1",
        )
    )

    assert result.model_id == model_id
    assert result.benchmark_id == f"{model_id}:production-full-1"
    assert result.status.value == "COMPLETED"
    assert result.recommendation.value == "RECOMMENDED_DEFAULT"
    assert result.completed_runs == result.successful_runs == result.total_runs == 90
    assert result.failed_runs == 0
    assert result.hardware_profile.ollama_version == "test"
    assert len(fake.chat_bodies) == 90
    assert all(body["model"] == "model-a:latest" for body in fake.chat_bodies)
    assert all(body["options"] == {"temperature": 0.0} for body in fake.chat_bodies)


def test_production_benchmark_rejects_missing_and_uninstalled_models_before_chat(
    benchmark_api: tuple[TestClient, FakeBenchmarkOllama],
) -> None:
    client, fake = benchmark_api
    missing = client.post(
        "/api/v1/models/mdl_550e8400-e29b-41d4-a716-446655440000/benchmarks/quick",
        headers={**CLIENT_HEADERS, "Idempotency-Key": "missing-model"},
        json={},
    )
    model_id = _refresh_model(client)
    fake.installed_models.clear()
    refreshed = client.post("/api/v1/models/refresh", headers=CLIENT_HEADERS)
    assert refreshed.status_code == 200
    request_count = len(fake.requests)
    uninstalled = client.post(
        f"/api/v1/models/{model_id}/benchmarks/quick",
        headers={**CLIENT_HEADERS, "Idempotency-Key": "uninstalled-model"},
        json={},
    )

    assert missing.status_code == 404
    assert missing.json()["error"]["code"] == "MODEL_NOT_FOUND"
    assert uninstalled.status_code == 409
    assert uninstalled.json()["error"]["code"] == "OLLAMA_MODEL_NOT_INSTALLED"
    assert fake.requests[request_count:] == []
    assert fake.chat_bodies == []


def test_production_benchmark_blocks_remote_ollama_configuration(
    benchmark_api: tuple[TestClient, FakeBenchmarkOllama],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client, fake = benchmark_api
    model_id = _refresh_model(client)
    request_count = len(fake.requests)
    monkeypatch.setenv("TRANSLOKA_OLLAMA_URL", "http://example.com:11434")

    response = client.post(
        f"/api/v1/models/{model_id}/benchmarks/quick",
        headers={**CLIENT_HEADERS, "Idempotency-Key": "remote-provider"},
        json={},
    )

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "REMOTE_OLLAMA_BLOCKED"
    assert fake.requests[request_count:] == []
    assert fake.chat_bodies == []
