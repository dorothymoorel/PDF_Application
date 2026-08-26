# M11-REM-05 Production Quick Benchmark Implementation Plan

## Task 1 — Production integration fixture

- Add a local fake Ollama supporting version, model listing, and structured chat responses.
- Drive refresh and quick benchmark through `create_app()` only.
- Confirm the test fails with `BENCHMARK_NOT_CONFIGURED` before implementation.

## Task 2 — Runtime adapter

- Resolve persisted model IDs with short-lived SQLAlchemy sessions.
- Reject missing or uninstalled records before constructing the provider.
- Create the bound provider with the requested temperature.
- Run the existing quick benchmark and replace only its public model ID.
- Normalize unsafe Ollama configuration without exposing configuration values.

## Task 3 — App composition and error mapping

- Construct the adapter inside the application lifespan.
- Store it as `application.state.quick_benchmark_runner`.
- Map adapter model/configuration failures to the canonical API errors.

## Task 4 — Verification

- Run benchmark API integration tests.
- Run Ollama, model, translation, and benchmark regressions.
- Run Ruff, format, mypy, full Python, Node regressions, generated-client drift, and diff checks.
- Commit only M11-REM-05 files; do not start the next remediation.
