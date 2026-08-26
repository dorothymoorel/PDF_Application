# M11-REM-05 Production Quick Benchmark Composition Design

## Goal

Make the existing quick-benchmark API operational in the production `create_app()` factory by
binding each persisted local-model record to the localhost-only Ollama provider implemented by
M11-REM-04.

## Runtime Flow

1. `POST /api/v1/models/{model_id}/benchmarks/quick` receives the persisted `mdl_...` ID.
2. A production adapter resolves that record through the lifespan-owned SQLAlchemy session
   factory.
3. Missing or uninstalled records fail before Ollama network access.
4. The adapter creates an immutable `OllamaTranslationProvider` for the record's
   `ollama_model_name` and the requested temperature.
5. `QuickBenchmarkRunner` performs its existing health, installed-model, structured-output,
   placeholder, latency, and recommendation checks.
6. The public result retains the persisted `model_id`; the Ollama name is transport detail.

The adapter is created inside the application lifespan, after the database session factory is
available. This keeps import side effects absent and ensures production and tests share the same
composition root.

## Error Policy

- unknown persisted model: `MODEL_NOT_FOUND`, HTTP 404;
- persisted but uninstalled model: `OLLAMA_MODEL_NOT_INSTALLED`, HTTP 409;
- remote or otherwise unsafe Ollama configuration: `REMOTE_OLLAMA_BLOCKED`, HTTP 403;
- Ollama health, model discovery, translation, schema, placeholder, and cancellation outcomes:
  existing benchmark/provider normalization remains authoritative;
- no prompt, response body, credential, or local filesystem path is exposed.

## Validation

A real local fake-Ollama integration test must use only the production app factory. It refreshes
model discovery, obtains the generated persisted ID, runs the quick endpoint, and proves:

- six canonical cases complete;
- the internal model ID is preserved in the response;
- the correct Ollama model and request temperature are used;
- missing and uninstalled records fail before chat dispatch;
- no manual router or benchmark-runner injection is needed.

## Scope

Allowed implementation files:

```text
services/api/src/transloka_api/app.py
services/api/src/transloka_api/routers/benchmarks.py
services/api/src/transloka_api/services/benchmarks.py
tests/integration/api/test_benchmarks.py
```

This task does not add full-benchmark endpoints or persistence, Huey tasks, translation worker
composition, model downloads, dependencies, frontend work, release-checklist changes, or tags.
