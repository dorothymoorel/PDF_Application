# M11-REM-08 Production Full Benchmark Design

## Goal

Close the executable full-benchmark portion of `REL-HIGH-003` by composing the
existing canonical `FullBenchmarkRunner` with persisted local-model records and the
localhost-only Ollama provider.

## Existing Boundary

The domain runner already implements the M11-T09 matrix:

- 30 cases;
- three repetitions per case;
- batch-size and context-length variation;
- cancellation and resume;
- structured-output and placeholder validation;
- hardware profile, latency, quality score, and recommendation.

It currently accepts an Ollama model name directly and is not available from the
production app composition.

## Production Adapter

Add `ProductionFullBenchmarkRunner` beside the quick-benchmark adapter. It must:

1. resolve the persisted internal `mdl_...` identifier in a short database session;
2. reject missing or no-longer-installed records before model generation;
3. construct a fresh immutable localhost-only Ollama provider per run;
4. detect the host hardware profile and record the Ollama version reported locally;
5. run the canonical 90-attempt matrix;
6. return the result with the internal model identifier restored.

The app lifespan owns the adapter and recreates it when the database is reopened.

## API and Worker Boundary

Do not add an inline `POST /benchmarks/full` implementation in this task. A full run
is a heavy, long-running operation and the API contract requires a concurrency limit.
HTTP dispatch, persistence, cancellation checkpoints, and resume orchestration belong
to the separately blocked production-worker remediation. The app-state adapter created
here is the concrete runner that that worker will invoke.

## Evidence

Integration tests must exercise the real production app lifespan and persisted model
registry against a local fake Ollama server. They must verify all 90 generation calls,
internal-ID retention, model binding, hardware/Ollama metadata, and fail-closed remote
configuration.

After automated verification, run the adapter through the production app lifespan
against the installed target model and record the complete result and environment in a
release evidence report. A model may be rejected; truthful benchmark evidence is the
acceptance criterion, not a favorable recommendation.

## Out of Scope

- full-benchmark HTTP dispatch and worker persistence;
- benchmark history/comparison UI;
- human blind-review UI;
- worker runtime composition;
- model downloads or selection changes;
- release checklist edits or release tagging.
