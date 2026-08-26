# M11-REM-09 Production Translation Worker Runtime Design

## Goal

Close the translation portion of `REL-HIGH-002` by connecting the production
FastAPI application to the existing SQLite-backed Huey queue and by registering
one concrete worker task that executes the canonical translation pipeline.

This remediation is complete only when a request accepted by the production app
can travel through `tasks.db`, execute in the worker boundary, and persist its
result in the application database without test-only router composition.

## Existing Boundary and Gap

The repository already contains:

- `JobDispatchService`, which persists an `ApplicationJob` before queueing only
  its `job_id`;
- `SqliteHuey` configuration using `<data-root>/database/tasks.db` and one thread
  worker;
- `TranslationJobRunner`, which loads a `TranslationOperation` and invokes the
  canonical `TranslationOrchestrator`;
- `SqlAlchemyTranslationRunStore`, which persists translation batches, attempts,
  segment translations, and validation rows;
- a production translation router which deliberately returns
  `QUEUE_NOT_CONFIGURED` when no queue is attached to app state.

The production app does not create a translation queue. The worker consumer does
not register any Huey task. The current translation runner also does not own the
persisted `ApplicationJob` lifecycle, construct an operation from database state,
or update document-segment state consumed by the status API.

## Scope

This task adds exactly one executable worker path:

```text
POST /api/v1/projects/{project_id}/translation/start
  -> ApplicationJob + immutable translation command
  -> transloka.translation.execute(job_id) in tasks.db
  -> production TranslationJobRunner
  -> TranslationOrchestrator + localhost-only Ollama provider
  -> application job, attempt, batch, validation, and segment persistence
```

OCR, reconstruction, backup, benchmark, export, and maintenance worker tasks are
not registered by this task.

## Queue and Package Composition

Use one stable Huey task name: `transloka.translation.execute`.

The process-neutral Huey queue declaration and registration factory live in the
worker package. The API declares a direct workspace dependency on
`transloka-worker` and uses that factory only as an infrastructure adapter. This
keeps task serialization and naming in one place, avoids duplicate private Huey
encoding logic, and does not create a circular dependency because the worker does
not depend on the API package.

Both processes construct their own `SqliteHuey` instance against the same
`QueueConfiguration.database_path`. The API obtains a `HueyJobQueue` backed by
the task proxy; the worker registers the same task name with the real handler
before constructing its consumer. Queue creation, task registration, database
sessions, provider instances, and runners occur in application/worker factories,
never at module import.

The API lifespan stores the queue as `application.state.translation_queue`.
Shutdown closes any owned Huey storage cleanly. Database restore recreates the
SQLAlchemy session-dependent app services; the queue remains bound only to the
separate `tasks.db` and must not retain an application database session.

## Persisted Translation Command

The Huey message contains only `job_id`. All durable execution input is stored in
`ApplicationJob.payload_json` using a versioned command schema,
`transloka.translation.command.v1`.

The command records:

- project and active-document identifiers;
- `FULL_DOCUMENT`, `UNTRANSLATED_ONLY`, `UNREVIEWED_ONLY`, `SECTION`, `PAGE`, or
  `SELECTED_SEGMENTS` scope and its selected identifiers;
- the internal `mdl_...` model identifier;
- translation style, batch size, and context mode;
- retranslation, locked-segment, and semantic-validation flags;
- the immutable glossary snapshot identifier.

`JobDispatchService` gains a backward-compatible way to persist a validated,
JSON-safe task command while retaining the existing standard project, document,
page, retry, and idempotency fields. Existing callers that do not provide an
extended command keep their current payload exactly.

Before dispatch, the API freezes the active glossary into the existing immutable
snapshot format and puts its identifier in the command. Reusing an idempotency key
is accepted only when the complete canonical command matches the existing job.
No prompt text, document text, credentials, provider URL, or arbitrary callable is
placed in `tasks.db`.

## Production Operation Loader

The worker constructs `TranslationOperation` from `job_id` and authoritative
local state. The loader must:

1. require an existing `TRANSLATE_DOCUMENT` job in `QUEUED`, `RETRYING`, or the
   resumable `RUNNING` state;
2. parse only the known versioned command fields and reject malformed or unknown
   values;
3. verify that the command, `ApplicationJob`, project, and active document agree;
4. resolve the exact persisted model, require it to remain installed, and pass its
   Ollama model name only to the localhost-only provider;
5. load and integrity-check the immutable glossary snapshot, then map its compiled
   rules into translation glossary entries;
6. select eligible segments according to scope and flags, in deterministic
   document/page/block/segment order;
7. use `resolved_source_text`, persisted languages, project document type and
   style, and bounded neighbouring context;
8. bind the operation to the application job's idempotency key, command settings,
   prompt/pipeline versions, and requested batch limit.

Ignored and non-translatable segments always remain unchanged. Locked segments
remain unchanged when `skip_locked_segments` is true; when it is false they are
eligible only when the chosen scope and retranslation flag also permit them. If a
valid scope has no eligible segments, the worker records a successful no-op result
instead of constructing an invalid empty `TranslationOperation` or contacting
Ollama.

Source or metadata changes that make the persisted command internally
inconsistent fail closed. A retry continues to use the same model identifier,
glossary snapshot, scope, and idempotency key rather than silently adopting newer
settings.

## Worker Dependency Factory

Worker startup composes, in order:

1. resolved local data directories;
2. the synchronous SQLite engine and session factory;
3. `SqlAlchemyTranslationRunStore`;
4. a fresh immutable `OllamaTranslationProvider` using its default loopback
   endpoint;
5. the database operation loader and cancellation signal;
6. `TranslationOrchestrator` and `TranslationJobRunner`;
7. the registered Huey task and consumer.

Factories accept narrow dependency overrides for tests. Production construction
does not accept a remote provider URL and does not shell out. The worker disposes
the SQLAlchemy engine and Huey resources during graceful shutdown.

## Application Job and Segment Lifecycle

Translation execution follows the existing persisted OCR lifecycle semantics
without introducing a generic task framework:

- validate the job's executable state;
- create or resume one `JobAttempt` and record the worker identifier;
- transition `QUEUED` or `RETRYING` to `RUNNING` before provider work;
- heartbeat and persist bounded progress after each translation batch;
- expose cancellation through a database-backed `CancellationSignal`, checked
  before batches and by the provider;
- map the final translation result to `COMPLETED`,
  `COMPLETED_WITH_WARNINGS`, `PARTIALLY_COMPLETED`, `FAILED`, or `CANCELLED`;
- write a versioned, JSON-safe summary to `ApplicationJob.result_json`;
- finalize the active `JobAttempt`, timestamps, stage, progress, and sanitized
  error fields;
- re-raise unexpected worker errors after best-effort failure persistence so Huey
  and recovery logic retain truthful failure evidence.

The orchestrator receives a backward-compatible batch progress callback. The
SQLAlchemy persistence path also updates each affected `DocumentSegment`:

- accepted output stores the restored machine translation and transitions to
  `MACHINE_TRANSLATED` or `NEEDS_REVIEW` according to validation warnings;
- rejected/provider-failed output transitions to `TRANSLATION_FAILED` without
  discarding prior source content;
- cancellation leaves unprocessed segment content untouched;
- locked/excluded segments remain unchanged.

Project status and progress are updated consistently with the final job outcome so
the existing translation status endpoint reflects persisted worker results rather
than only translation-batch rows.

## Concurrency, Restore, and Failure Rules

- The application database and `tasks.db` remain separate SQLite files.
- One worker thread remains the Personal MVP default.
- The existing maintenance gate runs before every registered task, so restore
  cannot overlap new translation work.
- No SQLAlchemy session crosses a process boundary or survives outside its
  transaction/session context.
- Queue failure leaves the already-created application job in the canonical
  `QUEUE_DISPATCH_FAILED` state.
- Missing jobs, wrong job types, corrupt commands, missing snapshots, unavailable
  models, and non-loopback provider configuration fail closed with stable,
  non-sensitive error codes.
- Document text, prompts, model responses, filesystem paths, and raw exception
  internals are not written to logs.

## Verification

Add focused unit/integration coverage for command validation, operation loading,
scope selection, no-op execution, cancellation, progress, result mapping, segment
updates, task-name stability, factory isolation, and worker shutdown.

The acceptance E2E uses a temporary data root and the production `create_app`
lifespan. It must:

1. seed a migrated application database with a project, document, translatable
   segments, glossary data, and an installed selected model;
2. inject a deterministic fake translation provider into the worker dependency
   factory, without contacting Ollama;
3. call the production translation-start route;
4. prove the application job is `QUEUED` and the named task is present in the real
   temporary `tasks.db`;
5. execute that queued task through the real worker registry;
6. verify the final job and attempt lifecycle, translation batch/results,
   document-segment text/status, and production status endpoint;
7. verify the queue message contains only the job identifier;
8. verify a second app/worker factory does not reuse engines, sessions, task
   registries, or provider state from the first.

No automated test requires a real model download, network access, or a running
Ollama service. Final verification includes the full Python suite, Ruff check and
format check, mypy, Node regression suite/build/audit, generated-client drift check,
`git diff --check`, and a repository runtime-database artifact scan.

## Expected Implementation Files

Implementation is constrained to the smallest necessary set under:

- `python/transloka-core/src/transloka_core/jobs/dispatch.py`;
- `python/transloka-translation/src/transloka_translation/orchestration/**`;
- `services/api/src/transloka_api/app.py`;
- `services/api/src/transloka_api/routers/translation.py`;
- `services/api/pyproject.toml`;
- `services/worker/src/transloka_worker/app.py`;
- `services/worker/src/transloka_worker/queue.py`;
- `services/worker/src/transloka_worker/translation.py`;
- a thin `services/worker/src/transloka_worker/tasks/translation.py` registry
  module;
- `services/worker/pyproject.toml`;
- focused tests under `tests/integration/api`, `tests/integration/translation`,
  `tests/integration/worker`, and `tests/e2e`;
- `uv.lock` only when workspace dependency declarations require regeneration.

No migration or schema change is expected. If implementation proves that a schema
change or a file outside this boundary is required, stop and revise this design
before editing that file.

## Out of Scope

- OCR, reconstruction, backup, export, benchmark, or maintenance task
  registration;
- worker health reporting or launcher/process-manager changes;
- UI changes or generated API-client changes unless the public OpenAPI contract
  unexpectedly changes;
- retry-policy redesign, distributed workers, multiple worker threads, or remote
  queues;
- prompt redesign, translation-quality tuning, model selection/download changes,
  or rerunning the model benchmark;
- release-checklist edits, release tagging, or starting M11-T18.

## Alternatives Rejected

Registering all missing worker tasks together is rejected because it crosses
independent OCR, reconstruction, backup, and translation lifecycles and cannot be
reviewed atomically.

Running translation inline in FastAPI is rejected because the canonical
architecture requires heavy work in the separate worker process.

Duplicating Huey's private task serialization in the API is rejected because task
name or payload drift would only appear at runtime. A single shared registration
factory is smaller and testable.

Passing a serialized `TranslationOperation` through Huey is rejected because it
duplicates durable application state, can become stale, and would place document
text in `tasks.db`.
