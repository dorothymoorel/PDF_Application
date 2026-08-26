# M11-REM-04 Ollama Translation Provider Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a fail-closed, localhost-only Ollama `/api/chat` translation call and validate it against both a fake HTTP server and the installed `qwen3:1.7b` model.

**Architecture:** Keep the generic provider protocol unchanged and bind the model name, temperature, and translation timeout immutably to `OllamaTranslationProvider`. Normalize both existing canonical inputs into `TranslationPrompt`, send its messages and response schema through the standard-library HTTP transport, and return only `message.content` for the existing strict parser.

**Tech Stack:** Python 3.12, asyncio, urllib, Ollama 0.32.15, pytest 9, Ruff, mypy.

**Spec:** `docs/superpowers/specs/2026-08-26-ollama-translation-provider-design.md`

## Global Constraints

- Modify only `python/transloka-translation/src/transloka_translation/providers/ollama.py` and `tests/integration/ollama/test_ollama.py`, unless the provider contract test proves a third file is necessary.
- Add no Python dependency and make no database, migration, API-router, worker, frontend, generated-client, release-checklist, or tag change.
- Permit only validated HTTP loopback endpoints; disable proxies and reject redirects.
- Never expose prompts, source text, response bodies, credentials, or local paths in exceptions.
- Never download, remove, or mutate an Ollama model.
- Keep request and response bodies at or below 1 MiB.
- Use test-driven development: observe each new behavior fail before implementing it.

---

### Task 1: Record POST Requests in the Fake Ollama Server

**Files:**
- Modify: `tests/integration/ollama/test_ollama.py:24-95`

**Interfaces:**
- Consumes: existing `StubResponse`, `FakeOllama`, and `_fake_ollama()` test utilities.
- Produces: `FakeOllama.request_bodies: list[dict[str, object]]` and POST handling for `/api/chat`.

- [ ] **Step 1: Extend the fake server without changing production behavior**

Add an optional raw-body field, captured JSON bodies, and a shared response writer:

```python
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
```

Inside `Handler`, keep `do_GET()` behavior and add:

```python
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
```

Initialize `recorded_bodies`, return it through `FakeOllama`, and update `do_GET()` to call `_write_response()` after recording the request.

- [ ] **Step 2: Run the existing Ollama integration suite**

Run:

```powershell
uv run pytest tests/integration/ollama/test_ollama.py -q
```

Expected: all existing tests pass; no production code has changed.

---

### Task 2: Bind and Validate Immutable Translation Configuration

**Files:**
- Modify: `tests/integration/ollama/test_ollama.py`
- Modify: `python/transloka-translation/src/transloka_translation/providers/ollama.py:19-112`

**Interfaces:**
- Consumes: `TranslationRequest`, `TranslationPrompt`, and `build_translation_prompt()`.
- Produces: immutable `model_name`, `temperature`, and `translation_timeout_seconds` provider configuration plus strict input normalization.

- [ ] **Step 1: Write failing configuration and input tests**

Import `QUICK_BENCHMARK_CASES` and `build_translation_prompt`, then add:

```python
def _benchmark_request() -> object:
    return QUICK_BENCHMARK_CASES[0].to_request()


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
```

- [ ] **Step 2: Verify RED**

Run:

```powershell
uv run pytest tests/integration/ollama/test_ollama.py -q
```

Expected: failures because the constructor keywords and `translate()` do not exist.

- [ ] **Step 3: Implement minimal validated configuration and input normalization**

Add constructor parameters and read-only properties:

```python
def __init__(
    self,
    base_url: str | None = None,
    *,
    model_name: str | None = None,
    temperature: float = 0.1,
    timeout_seconds: float = DEFAULT_OLLAMA_TIMEOUT_SECONDS,
    translation_timeout_seconds: float = 120.0,
) -> None:
```

Reject blank, non-printable, or longer-than-200 model names. Reject booleans,
non-finite temperatures, and values outside `0..2`. Validate the translation
timeout as a finite real number greater than zero and at most 600 seconds.

Add:

```python
def _translation_prompt(self, request: object) -> TranslationPrompt:
    if isinstance(request, TranslationPrompt):
        return request
    if isinstance(request, TranslationRequest):
        return build_translation_prompt(request)
    raise TranslationProviderError(
        ProviderErrorCode.INVALID_REQUEST,
        "The translation request is invalid.",
    )

def _require_model_name(self) -> str:
    if self._model_name is None:
        raise TranslationProviderError(
            ProviderErrorCode.INVALID_REQUEST,
            "A local Ollama model must be selected before translation.",
        )
    return self._model_name
```

Add a temporary `translate()` that calls both helpers and then raises
`INVALID_REQUEST` with message `"Ollama translation transport is not available."`.
This is sufficient for configuration tests while keeping the transport test RED.

- [ ] **Step 4: Verify configuration tests GREEN**

Run only the four new test functions. Expected: pass.

---

### Task 3: Implement Strict `/api/chat` Translation Transport

**Files:**
- Modify: `tests/integration/ollama/test_ollama.py`
- Modify: `python/transloka-translation/src/transloka_translation/providers/ollama.py:113-end`

**Interfaces:**
- Consumes: a bound model and normalized `TranslationPrompt`.
- Produces: `async translate(request: object, *, cancellation: CancellationSignal | None = None) -> str`.

- [ ] **Step 1: Write the failing success-path tests**

Add one test using `TranslationRequest` and one using `TranslationPrompt`:

```python
def test_translation_posts_canonical_structured_chat_request() -> None:
    request = QUICK_BENCHMARK_CASES[0].to_request()
    expected_prompt = build_translation_prompt(request)
    response_text = json.dumps(
        {"segments": [{"segment_id": request.segment_ids[0], "translated_text": "Hasil"}]}
    )
    with _fake_ollama(
        {"/api/chat": StubResponse({"message": {"role": "assistant", "content": response_text}})}
    ) as fake:
        provider = OllamaTranslationProvider(
            fake.base_url,
            model_name="model-a:latest",
            temperature=0.25,
        )
        result = asyncio.run(provider.translate(request))

    assert result == response_text
    assert fake.requests == [("POST", "/api/chat")]
    assert fake.request_bodies == [
        {
            "format": expected_prompt.response_schema,
            "messages": [message.to_dict() for message in expected_prompt.messages],
            "model": "model-a:latest",
            "options": {"temperature": 0.25},
            "stream": False,
        }
    ]


def test_translation_accepts_an_existing_translation_prompt() -> None:
    request = QUICK_BENCHMARK_CASES[0].to_request()
    prompt = build_translation_prompt(request)
    response_text = json.dumps(
        {"segments": [{"segment_id": request.segment_ids[0], "translated_text": "Hasil"}]}
    )
    with _fake_ollama(
        {"/api/chat": StubResponse({"message": {"content": response_text}})}
    ) as fake:
        result = asyncio.run(
            OllamaTranslationProvider(
                fake.base_url,
                model_name="model-a:latest",
            ).translate(prompt)
        )

    assert result == response_text
```

- [ ] **Step 2: Verify RED**

Run the two success-path tests. Expected: fail with the temporary transport error.

- [ ] **Step 3: Implement POST serialization and response extraction**

Create a deterministic request object with `model`, `messages`, `stream`, `format`, and
`options.temperature`. Serialize using:

```python
body = json.dumps(
    payload,
    ensure_ascii=False,
    allow_nan=False,
    sort_keys=True,
    separators=(",", ":"),
).encode("utf-8")
```

Reject bodies over `_MAX_RESPONSE_BYTES`. Send through a new `_post_json_sync()` using:

```python
request = Request(
    f"{self._base_url}/api/chat",
    data=body,
    headers={"Accept": "application/json", "Content-Type": "application/json"},
    method="POST",
)
```

Use `build_opener(ProxyHandler({}), _RejectRedirects())`, the translation timeout, and
the existing response-size/JSON-object validation. Require `payload["message"]` to be a
mapping and `message["content"]` to be a non-empty string, then return it unchanged.

- [ ] **Step 4: Verify success paths GREEN**

Run the two tests. Expected: pass with exactly one local POST each.

---

### Task 4: Normalize Failures, Enforce Size Limits, and Honor Cancellation

**Files:**
- Modify: `tests/integration/ollama/test_ollama.py`
- Modify: `python/transloka-translation/src/transloka_translation/providers/ollama.py`

**Interfaces:**
- Consumes: `CancellationSignal` and existing `ProviderErrorCode` values.
- Produces: bounded cancellation polling and sanitized normalized failures.

- [ ] **Step 1: Write failing response, HTTP, size, and cancellation tests**

Add parameterized invalid-response cases for raw invalid JSON, missing `message`, non-string
`content`, empty `content`, and a response over 1 MiB. Assert `INVALID_RESPONSE` and assert the
secret sentinel from each body is absent from `str(raised.value)`.

Add HTTP mapping tests with responses `400`, `404`, `429`, `500`, and `302`; assert respectively
`INVALID_REQUEST`, `INVALID_REQUEST`, `RATE_LIMIT`, `PROVIDER_UNAVAILABLE`, and
`PROVIDER_UNAVAILABLE`. For the redirect case, configure `/redirected` and assert the fake
server records only `POST /api/chat`.

Add this cancellation test:

```python
@dataclass(slots=True)
class MutableCancellation:
    is_cancelled: bool = False


def test_translation_honors_cancellation_while_waiting_for_ollama() -> None:
    signal = MutableCancellation()
    response_text = json.dumps({"segments": []})

    async def run() -> None:
        with _fake_ollama(
            {
                "/api/chat": StubResponse(
                    {"message": {"content": response_text}},
                    delay_seconds=0.25,
                )
            }
        ) as fake:
            provider = OllamaTranslationProvider(
                fake.base_url,
                model_name="model-a:latest",
                translation_timeout_seconds=1,
            )
            task = asyncio.create_task(provider.translate(_benchmark_request(), cancellation=signal))
            await asyncio.sleep(0.03)
            signal.is_cancelled = True
            with pytest.raises(asyncio.CancelledError):
                await asyncio.wait_for(task, timeout=0.15)

    asyncio.run(run())
```

Also test already-cancelled input produces no request, direct `asyncio.Task.cancel()` propagates
`CancelledError`, timeout maps to retryable `TIMEOUT`, and a source string larger than 1 MiB maps
to `INVALID_REQUEST` before network access.

- [ ] **Step 2: Verify RED**

Run the newly added failure tests. Expected: at least invalid outer responses, HTTP mapping,
request-size enforcement, and in-flight cancellation fail.

- [ ] **Step 3: Implement failure mapping and cancellation polling**

Factor HTTP errors through one helper:

```python
def _http_error(self, status_code: int) -> TranslationProviderError:
    if status_code == 429:
        return TranslationProviderError(
            ProviderErrorCode.RATE_LIMIT,
            "The local Ollama service is temporarily rate limited.",
            retryable=True,
        )
    if status_code in {400, 404}:
        return TranslationProviderError(
            ProviderErrorCode.INVALID_REQUEST,
            "The local Ollama service rejected the translation request.",
        )
    return TranslationProviderError(
        ProviderErrorCode.PROVIDER_UNAVAILABLE,
        "The local Ollama service returned an unsuccessful response.",
        retryable=status_code >= 500,
    )
```

Await the blocking POST task with a 10 ms cancellation polling interval:

```python
task = asyncio.create_task(asyncio.to_thread(self._post_json_sync, body))
try:
    while not task.done():
        self._raise_if_cancelled(cancellation)
        await asyncio.wait({task}, timeout=0.01)
    payload = await task
finally:
    if not task.done():
        task.cancel()
self._raise_if_cancelled(cancellation)
```

`_raise_if_cancelled()` raises `asyncio.CancelledError`. Do not catch that exception in transport
normalization. Reuse sanitized `_timeout_error()` and `_invalid_response()` factories.

- [ ] **Step 4: Verify all Ollama integration tests GREEN**

Run:

```powershell
uv run pytest tests/integration/ollama/test_ollama.py -q
```

Expected: all tests pass, including existing health/model/router tests.

---

### Task 5: Verify the Provider and Run the Real Quick Benchmark

**Files:**
- Modify only if a verified defect is found: the two implementation files above.

**Interfaces:**
- Consumes: completed `OllamaTranslationProvider` and `QuickBenchmarkRunner`.
- Produces: fresh deterministic verification plus an actual local model benchmark result.

- [ ] **Step 1: Run focused static and regression checks**

```powershell
uv run pytest tests/unit/translation tests/unit/benchmark tests/integration/ollama tests/integration/translation -q
uv run ruff check python/transloka-translation/src/transloka_translation/providers/ollama.py tests/integration/ollama/test_ollama.py
uv run ruff format --check python/transloka-translation/src/transloka_translation/providers/ollama.py tests/integration/ollama/test_ollama.py
uv run mypy python/transloka-translation services/api services/worker tests/integration/ollama
```

Expected: every command exits zero.

- [ ] **Step 2: Run the real localhost quick benchmark**

```powershell
uv run python -c "import asyncio,json; from transloka_translation.benchmark import QuickBenchmarkRunner; from transloka_translation.providers.ollama import OllamaTranslationProvider; provider=OllamaTranslationProvider(model_name='qwen3:1.7b', translation_timeout_seconds=180); result=asyncio.run(QuickBenchmarkRunner(provider).run('qwen3:1.7b')); print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))"
```

Expected: the command completes without `PROVIDER_ERROR`. Record the actual benchmark status,
case counts, structured-output validity, placeholder integrity, latency, and recommendation.
Do not change a rejected model-quality result into a pass.

- [ ] **Step 3: Run full repository verification**

```powershell
uv run pytest -q
uv run ruff check .
uv run mypy .
pnpm lint
pnpm typecheck
pnpm test
pnpm build
pnpm --filter @transloka/api-client check-generated
git diff --check
```

Run `uv run ruff format --check .` separately and report the two pre-existing Windows CRLF
failures if they remain. Do not reformat those out-of-scope files.

- [ ] **Step 4: Review and commit only the implementation scope**

```powershell
git diff --name-status
git diff --check
git add -- python/transloka-translation/src/transloka_translation/providers/ollama.py tests/integration/ollama/test_ollama.py
git diff --cached --check
git commit -m "feat(translation): implement local Ollama generation"
git status --short
```

Expected: the commit contains only the provider and its integration tests, and the final working
tree is clean.
