# M11-REM-04 Ollama Translation Provider Design

## Goal

Implement the missing production translation call in `OllamaTranslationProvider` so an
authorized localhost Ollama model can execute TransLoka's canonical structured prompts. The
implementation must preserve the existing provider protocol, fail closed, and support a real
quick benchmark without adding cloud or model-download behavior.

## Current Gap

`OllamaTranslationProvider` currently supports health checks and model discovery only. Two
existing callers use different input representations:

- translation orchestration passes a `TranslationPrompt`;
- quick and full benchmark runners pass a `TranslationRequest`.

Ollama also requires a concrete model name for every generation request, while the generic
provider protocol intentionally exposes only `translate(request, cancellation=...)`.

## Design Decision

Bind generation configuration immutably to each provider instance:

```python
OllamaTranslationProvider(
    base_url="http://127.0.0.1:11434",
    model_name="qwen3:1.7b",
    temperature=0.1,
    timeout_seconds=2.0,
    translation_timeout_seconds=120.0,
)
```

`model_name` remains optional so the existing health and model-listing adapter can be created
without selecting a model. Calling `translate()` on an unbound instance fails with normalized
`INVALID_REQUEST`. A bound instance cannot change model or temperature after construction.

This avoids a breaking change to `TranslationProvider`, avoids mutable shared model selection,
and lets the future worker composition root create one provider for the selected Ollama model.

## Accepted Inputs

`translate()` accepts only:

- `TranslationPrompt`, used directly; or
- `TranslationRequest`, converted using `build_translation_prompt()`.

All other input types fail with `INVALID_REQUEST`. Supporting both existing canonical types
keeps orchestration and benchmark callers provider-independent without duplicating prompt
construction logic inside benchmark runners.

## Ollama Request

The provider sends one `POST /api/chat` request with:

```json
{
  "model": "qwen3:1.7b",
  "messages": [
    {"role": "system", "content": "..."},
    {"role": "user", "content": "..."}
  ],
  "stream": false,
  "format": {"type": "object"},
  "options": {"temperature": 0.1}
}
```

`format` contains the complete response schema from `TranslationPrompt`, not the abbreviated
example above. JSON serialization is deterministic, UTF-8, and rejects non-finite numbers.
Serialized requests larger than 1 MiB fail before network access.

The returned outer Ollama object must contain `message.content` as a non-empty string. The
provider returns that string unchanged. Existing strict response parsing remains responsible
for validating segment IDs, duplicate or missing segments, unknown fields, and translated
text.

## Network and Security Controls

All existing localhost URL validation remains mandatory. Translation uses the same transport
policy as health and model listing:

- HTTP loopback endpoint only;
- proxies disabled;
- redirects rejected;
- no cloud fallback;
- no authentication or credential forwarding;
- no model pull or mutation endpoint;
- response body limited to 1 MiB;
- separate bounded translation timeout, from greater than zero through 600 seconds;
- error messages contain no prompt, source text, response body, or local path.

The cancellation signal is checked before prompt construction, before dispatch, while awaiting
the blocking standard-library HTTP operation, and after response receipt. Cancellation returns
`asyncio.CancelledError` promptly. The underlying helper thread remains bounded by the socket
timeout because Python's standard-library HTTP client cannot forcibly stop an active thread.
Direct coroutine cancellation also propagates unchanged.

## Error Normalization

Transport and response failures map to existing provider codes:

- timeout: `TIMEOUT`, retryable;
- HTTP 429: `RATE_LIMIT`, retryable;
- HTTP 400 or 404: `INVALID_REQUEST`, not retryable;
- redirect, other HTTP failure, connection failure, or OS failure:
  `PROVIDER_UNAVAILABLE`, retryable only for transient failures;
- invalid input, missing model binding, or oversized request: `INVALID_REQUEST`;
- malformed UTF-8/JSON, oversized response, missing `message.content`, or empty content:
  `INVALID_RESPONSE`.

No raw Ollama error body is included in the normalized exception.

## Validation Strategy

Implementation follows test-driven development. Fake local HTTP-server integration tests cover:

1. exact `/api/chat` method, path, messages, model, schema, temperature, and `stream=false`;
2. both accepted input types;
3. missing or invalid model configuration;
4. remote URL, proxy, and redirect rejection;
5. timeout and cancellation before and during a request;
6. request and response size limits;
7. malformed outer JSON and invalid `message.content`;
8. normalized HTTP and connection errors;
9. absence of source text and response bodies from exceptions.

After deterministic tests pass, run the real quick benchmark against the installed local
`qwen3:1.7b` model. Record its actual completion status, structured-output validity,
placeholder integrity, latency, and recommendation. A model quality rejection is reported as a
benchmark result, not hidden or converted into a passing result.

## Expected Implementation Scope

Primary files:

```text
python/transloka-translation/src/transloka_translation/providers/ollama.py
tests/integration/ollama/test_ollama.py
```

Only if required by the accepted tests:

```text
tests/unit/translation/providers/test_contract.py
```

No dependency, database, migration, API-router, worker-registry, generated-client, frontend,
release-checklist, or tag changes belong to M11-REM-04.

## Non-Goals

- Registering Huey worker tasks.
- Building the worker composition root.
- Resolving database model IDs to Ollama model names.
- Wiring a production benchmark runner into `create_app()`.
- Downloading, deleting, or changing Ollama models.
- Updating release status or creating the Personal MVP tag.

Those remain separately reviewable remediation work.
