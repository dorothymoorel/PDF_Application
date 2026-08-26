# M11-REM-09 Production Translation Worker Runtime Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the production translation-start API persist an immutable command, enqueue only its job ID in SQLite Huey, execute it through a concrete worker task, and persist truthful job and segment results.

**Architecture:** The API and worker share one task declaration from `transloka-worker` while constructing separate `SqliteHuey` instances over `<data-root>/database/tasks.db`. The application database remains the source of truth for the versioned translation command; a per-job production runner loads authoritative local state, binds the exact local model to the loopback-only Ollama provider, and drives the existing orchestrator and SQLAlchemy store.

**Tech Stack:** Python 3.12, FastAPI lifespan, SQLAlchemy 2 synchronous sessions, Huey `SqliteHuey`, SQLite WAL, Alembic test databases, pytest, Ruff, mypy, uv.

**Spec:** `docs/superpowers/specs/2026-08-27-production-translation-worker-runtime-design.md`

## Global Constraints

- Register exactly one worker task named `transloka.translation.execute`.
- Huey messages contain only one positional string argument: `job_id`.
- Use `<data-root>/database/tasks.db`; never reuse `transloka.db` as the queue database.
- Keep the default worker count at one thread.
- Construct engines, session factories, Huey instances, providers, task registries, and runners only in factories or lifespans, never at module import.
- Production Ollama configuration remains loopback-only and uses `OllamaTranslationProvider` validation.
- Preserve existing callers of `JobDispatchService.dispatch()` when no extended command is supplied.
- Do not add database migrations or schema changes.
- Do not register OCR, reconstruction, backup, export, benchmark, or maintenance tasks.
- Do not change public API response schemas or generated clients.
- Do not start M11-T18 or edit the release checklist.

## File Map

- `python/transloka-core/src/transloka_core/jobs/dispatch.py`: canonical JSON command persistence and idempotency comparison.
- `python/transloka-translation/src/transloka_translation/orchestration/service.py`: batch progress callback.
- `python/transloka-translation/src/transloka_translation/orchestration/persistence.py`: accepted translation text and review-state persistence.
- `services/api/src/transloka_api/routers/translation.py`: immutable glossary snapshot and complete translation command dispatch.
- `services/api/src/transloka_api/app.py`: producer queue ownership in FastAPI lifespan.
- `services/worker/src/transloka_worker/translation.py`: command parser, database operation loader, cancellation adapter, and production job lifecycle.
- `services/worker/src/transloka_worker/tasks/__init__.py`: task package marker.
- `services/worker/src/transloka_worker/tasks/translation.py`: stable Huey task declaration and producer/consumer registration.
- `services/worker/src/transloka_worker/queue.py`: owned queue producer and registrar-aware consumer construction.
- `services/worker/src/transloka_worker/app.py`: production translation runtime composition and shutdown.
- `services/api/pyproject.toml`, `services/worker/pyproject.toml`, `uv.lock`: explicit workspace dependencies.
- `tests/integration/worker/test_job_dispatch.py`: backward-compatible command persistence.
- `tests/integration/api/test_translation.py`: API command and glossary snapshot behavior.
- `tests/integration/translation/test_orchestration.py`: progress callback behavior.
- `tests/integration/translation/test_persistence.py`: document-segment persistence.
- `tests/integration/worker/test_translation_runtime.py`: command loading and job lifecycle.
- `tests/integration/worker/test_sqlite_huey.py`: stable task registration and resource ownership.
- `tests/e2e/runtime/test_translation_worker_runtime.py`: production app to real queue to real worker registry.

---

### Task 1: Backward-Compatible Durable Job Commands

**Files:**
- Modify: `python/transloka-core/src/transloka_core/jobs/dispatch.py`
- Test: `tests/integration/worker/test_job_dispatch.py`

**Interfaces:**
- Consumes: the existing keyword arguments of `JobDispatchService.dispatch()` and `JobQueue`.
- Produces: `command_payload: Mapping[str, object] | None = None` on `dispatch()` and canonical JSON validation through `_serialize_payload(payload: Mapping[str, object]) -> str`.

- [ ] **Step 1: Write failing tests for extended and legacy payloads**

Add imports for `json` and assertions equivalent to:

```python
def test_dispatch_persists_canonical_extended_command(job_database: JobDatabase) -> None:
    factory, queue = job_database
    command = {
        "schema": "transloka.translation.command.v1",
        "project_id": PROJECT_ID,
        "document_id": DOCUMENT_ID,
        "model_id": MODEL_ID,
        "segment_ids": [SEGMENT_ID],
    }

    result = JobDispatchService(factory, queue).dispatch(
        job_type=JobType.TRANSLATE_DOCUMENT,
        idempotency_key="translation-command-1",
        project_id=PROJECT_ID,
        document_id=DOCUMENT_ID,
        command_payload=command,
    )

    with factory() as session:
        row = session.get(ApplicationJob, result.job_id)
        assert row is not None
        assert json.loads(row.payload_json) == command
        assert row.payload_json == json.dumps(
            command, ensure_ascii=False, allow_nan=False, sort_keys=True, separators=(",", ":")
        )


def test_dispatch_rejects_non_json_command_without_creating_job(
    job_database: JobDatabase,
) -> None:
    factory, queue = job_database

    with pytest.raises(InvalidJobDispatchError, match="JSON-safe"):
        JobDispatchService(factory, queue).dispatch(
            job_type=JobType.TRANSLATE_DOCUMENT,
            idempotency_key="translation-command-invalid",
            project_id=PROJECT_ID,
            document_id=DOCUMENT_ID,
            command_payload={"schema": object()},
        )

    with factory() as session:
        assert session.scalar(select(ApplicationJob.id)) is None
```

Extend the existing legacy payload test to assert its current three keys remain
`document_id`, `page_ids`, and `project_id` when `command_payload` is omitted.
Add a queue double whose `enqueue(job_id)` opens a new session and records the
stored status. Assert it observes `QUEUED`, not `CREATED`; this prevents a real
consumer from racing the post-enqueue status transaction.

- [ ] **Step 2: Run the focused tests and verify RED**

Run:

```powershell
uv run pytest tests/integration/worker/test_job_dispatch.py -q
```

Expected: the extended-command test fails because `dispatch()` does not accept
`command_payload`; all pre-existing tests still pass up to that failure.

- [ ] **Step 3: Implement canonical command serialization**

Add `Mapping` to the collections imports and change the public signature to:

```python
def dispatch(
    self,
    *,
    job_type: JobType,
    idempotency_key: str,
    project_id: str | None = None,
    document_id: str | None = None,
    page_ids: Sequence[str] = (),
    max_retries: int = 3,
    command_payload: Mapping[str, object] | None = None,
) -> JobDispatchResult:
```

Pass `command_payload` into `_validate_and_serialize_request`. Preserve the old
dictionary when it is `None`; otherwise require a non-empty mapping with string
keys and canonicalize it with:

```python
def _serialize_payload(payload: Mapping[str, object]) -> str:
    if not payload or any(not isinstance(key, str) for key in payload):
        raise InvalidJobDispatchError("The job command must be a non-empty JSON object.")
    try:
        serialized = json.dumps(
            dict(payload),
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
            sort_keys=True,
        )
        decoded = json.loads(serialized)
    except (TypeError, ValueError):
        raise InvalidJobDispatchError("The job command must be JSON-safe.") from None
    if not isinstance(decoded, dict):
        raise InvalidJobDispatchError("The job command must be a JSON object.")
    return serialized
```

Continue using the complete serialized payload in `_matches_request`, making
idempotency comparison sensitive to every command field.

Commit `ApplicationJob.status=QUEUED` and `queued_at` in the creation transaction
before calling `queue.enqueue(job_id)`. Remove the second success transaction.
When enqueue raises, `_mark_dispatch_failed()` accepts a QUEUED row, changes it to
FAILED, clears `queued_at`, and records the existing `QUEUE_DISPATCH_FAILED`
evidence. This preserves current queue-failure assertions while closing the
producer/consumer race.

- [ ] **Step 4: Run focused tests and verify GREEN**

Run:

```powershell
uv run pytest tests/integration/worker/test_job_dispatch.py -q
uv run mypy python/transloka-core/src/transloka_core/jobs/dispatch.py
```

Expected: all dispatch tests pass and mypy reports success.

- [ ] **Step 5: Commit the durable-command unit**

```powershell
git add python/transloka-core/src/transloka_core/jobs/dispatch.py tests/integration/worker/test_job_dispatch.py
git commit -m "feat(jobs): persist versioned task commands"
```

---

### Task 2: Translation Command and API Snapshot Dispatch

**Files:**
- Modify: `services/worker/src/transloka_worker/translation.py`
- Modify: `services/api/src/transloka_api/routers/translation.py`
- Modify: `services/api/pyproject.toml`
- Modify: `services/worker/pyproject.toml`
- Modify: `uv.lock`
- Test: `tests/integration/api/test_translation.py`
- Test: `tests/integration/worker/test_translation_runtime.py`

**Interfaces:**
- Consumes: `StartTranslationRequest`, `create_glossary_snapshot`, `LocalFileStorage`, and `JobDispatchService.command_payload` from Task 1.
- Produces: `TranslationCommand`, `TranslationCommand.from_payload_json(value: str)`, `TranslationCommand.to_payload() -> dict[str, object]`, and `TRANSLATION_COMMAND_SCHEMA`.

- [ ] **Step 1: Write failing strict-command parser tests**

Create `tests/integration/worker/test_translation_runtime.py` with a valid command
factory and these core assertions:

```python
def _command() -> TranslationCommand:
    return TranslationCommand(
        project_id=PROJECT_ID,
        document_id=DOCUMENT_ID,
        scope="FULL_DOCUMENT",
        section_ids=(),
        page_ids=(),
        segment_ids=(),
        model_id=MODEL_ID,
        translation_style="PROFESSIONAL",
        batch_size=5,
        context_mode="STANDARD",
        retranslate_existing=False,
        skip_locked_segments=True,
        run_semantic_validation=False,
        glossary_snapshot_id=SNAPSHOT_ID,
    )


def test_translation_command_round_trips_canonically() -> None:
    command = _command()
    payload = command.to_payload()

    assert payload["schema"] == TRANSLATION_COMMAND_SCHEMA
    assert TranslationCommand.from_payload_json(
        json.dumps(payload, sort_keys=True, separators=(",", ":"))
    ) == command


def test_translation_command_rejects_unknown_fields() -> None:
    payload = _command().to_payload()
    payload["unexpected"] = True

    with pytest.raises(TranslationWorkerError, match="fields"):
        TranslationCommand.from_payload_json(json.dumps(payload))
```

Add parameterized cases for an unknown schema, malformed prefixed identifiers,
invalid scope/selector combinations, batch sizes outside 1..100, invalid context
mode, non-boolean flags, and non-list selector fields.

- [ ] **Step 2: Extend the API test with durable snapshot assertions**

In `test_translation_start_is_idempotent_and_readiness_blocks_start`, inspect the
first job and assert:

```python
with factory() as session:
    row = session.get(ApplicationJob, first.json()["data"]["job_id"])
    assert row is not None
    command = TranslationCommand.from_payload_json(row.payload_json)
    assert command.project_id == project_id
    assert command.document_id == DOCUMENT_ID
    assert command.model_id == MODEL_ID
    assert command.glossary_snapshot_id.startswith("gsn_")
    snapshot = session.get(GlossarySnapshot, command.glossary_snapshot_id)
    assert snapshot is not None
```

Add a second POST using the same idempotency key but a different `batch_size` and
assert `409 IDEMPOTENCY_CONFLICT`.

Extend `RecordingQueue` to retain enqueued IDs. In the cancel/retry test, make the
job retryable, POST one retry key twice, and assert the original job ID is enqueued
exactly one additional time. Add an unavailable-queue case asserting `503
QUEUE_UNAVAILABLE`, terminal FAILED job state, a finalized failed retry attempt,
and no false `RETRYING` status.

- [ ] **Step 3: Run parser and API tests and verify RED**

```powershell
uv run pytest tests/integration/worker/test_translation_runtime.py tests/integration/api/test_translation.py -q
```

Expected: import/attribute failures for `TranslationCommand`, followed by missing
snapshot/command assertions once the parser exists.

- [ ] **Step 4: Implement the immutable command value object**

Add these public definitions to `transloka_worker.translation`:

```python
TRANSLATION_COMMAND_SCHEMA = "transloka.translation.command.v1"
_TRANSLATION_SCOPES = frozenset(
    {
        "FULL_DOCUMENT",
        "UNTRANSLATED_ONLY",
        "UNREVIEWED_ONLY",
        "SECTION",
        "PAGE",
        "SELECTED_SEGMENTS",
    }
)


@dataclass(frozen=True, slots=True)
class TranslationCommand:
    project_id: str
    document_id: str
    scope: str
    section_ids: tuple[str, ...]
    page_ids: tuple[str, ...]
    segment_ids: tuple[str, ...]
    model_id: str
    translation_style: str
    batch_size: int
    context_mode: str
    retranslate_existing: bool
    skip_locked_segments: bool
    run_semantic_validation: bool
    glossary_snapshot_id: str

    def to_payload(self) -> dict[str, object]:
        return {
            "schema": TRANSLATION_COMMAND_SCHEMA,
            "project_id": self.project_id,
            "document_id": self.document_id,
            "scope": self.scope,
            "section_ids": list(self.section_ids),
            "page_ids": list(self.page_ids),
            "segment_ids": list(self.segment_ids),
            "model_id": self.model_id,
            "translation_style": self.translation_style,
            "batch_size": self.batch_size,
            "context_mode": self.context_mode,
            "retranslate_existing": self.retranslate_existing,
            "skip_locked_segments": self.skip_locked_segments,
            "run_semantic_validation": self.run_semantic_validation,
            "glossary_snapshot_id": self.glossary_snapshot_id,
        }

    @classmethod
    def from_payload_json(cls, value: str) -> Self:
        payload = _decode_translation_command(value)
        return _translation_command_from_payload(payload)
```

Implement every validation exercised above. `to_payload()` emits every field and
the schema. `from_payload_json()` accepts exactly that key set, converts selector
lists to tuples, and raises `TranslationWorkerError` with stable generic messages.
Define the parser helpers in the same module with these exact signatures:

```python
def _decode_translation_command(value: str) -> dict[str, object]:
    """Decode one JSON object and reject invalid JSON, duplicate keys, and non-objects."""


def _translation_command_from_payload(
    payload: dict[str, object],
) -> TranslationCommand:
    """Validate the exact key set, identifiers, selectors, choices, integers, and flags."""
```

Use the repository's strict type convention (`type(value) is ...`) so booleans
cannot pass integer validation. Identifier checks require canonical UUID text with
the prefixes `prj_`, `doc_`, `sec_`, `pag_`, `seg_`, `mdl_`, and `gsn_`. SECTION,
PAGE, and SELECTED_SEGMENTS require only their matching non-empty selector; the
three broad scopes require all selector tuples to be empty.

- [ ] **Step 5: Persist a glossary snapshot and full command before queueing**

In the start route, resolve `_translation_queue(request)` before creating snapshot
state. Then use a separate committed transaction:

```python
with transaction_scope(_session_factory(request)) as snapshot_session:
    snapshot = create_glossary_snapshot(
        session=snapshot_session,
        storage=LocalFileStorage(request.app.state.settings.data_directories),
        project_id=project_id,
        document_id=document_id,
    )

command = TranslationCommand(
    project_id=project_id,
    document_id=document_id,
    scope=payload.scope,
    section_ids=tuple(payload.section_ids or ()),
    page_ids=tuple(payload.page_ids or ()),
    segment_ids=tuple(payload.segment_ids or ()),
    model_id=payload.model_id,
    translation_style=(payload.translation_style or readiness.project.translation_style),
    batch_size=payload.batch_size,
    context_mode=payload.context_mode,
    retranslate_existing=payload.retranslate_existing,
    skip_locked_segments=payload.skip_locked_segments,
    run_semantic_validation=payload.run_semantic_validation,
    glossary_snapshot_id=snapshot.id,
)
```

Pass `command_payload=command.to_payload()` to `dispatch()`. Map command/snapshot
validation failures to the existing `VALIDATION_ERROR` or a stable 409 readiness
error without exposing local paths.

After `JobRetryService.request(...)`, enqueue the existing job ID only when
`result.created` is true. If enqueue raises, call a router-local helper with this
signature before returning the existing normalized 503 response:

```python
def _mark_retry_queue_failure(
    session_factory: sessionmaker[Session],
    job_id: str,
    attempt_id: str,
) -> None:
    """Atomically fail the retrying job and its active attempt after enqueue failure."""
```

The helper sets job and attempt to FAILED, uses `QUEUE_DISPATCH_FAILED`, clears
stale queue/start timestamps, sets `completed_at`, and preserves the original
versioned translation command. A repeated retry idempotency key returns
`created=False` and must not enqueue a duplicate task.

- [ ] **Step 6: Declare workspace dependencies and refresh the lock**

Add `transloka-worker` to API dependencies. Add `transloka-core`,
`transloka-glossary`, and `transloka-translation` to worker dependencies while
retaining `huey>=3.3.2,<4`. Then run:

```powershell
uv lock
uv sync --locked
```

Expected: workspace packages resolve locally and SQLAlchemy/Huey versions do not
move outside their existing locked constraints.

- [ ] **Step 7: Run focused tests and commit**

```powershell
uv run pytest tests/integration/worker/test_translation_runtime.py tests/integration/api/test_translation.py -q
uv run ruff check services/api/src/transloka_api/routers/translation.py services/worker/src/transloka_worker/translation.py
uv run mypy services/api/src/transloka_api/routers/translation.py services/worker/src/transloka_worker/translation.py
git add services/api/src/transloka_api/routers/translation.py services/worker/src/transloka_worker/translation.py services/api/pyproject.toml services/worker/pyproject.toml uv.lock tests/integration/api/test_translation.py tests/integration/worker/test_translation_runtime.py
git commit -m "feat(translation): persist executable commands"
```

---

### Task 3: Batch Progress and Accepted Segment Persistence

**Files:**
- Modify: `python/transloka-translation/src/transloka_translation/orchestration/service.py`
- Modify: `python/transloka-translation/src/transloka_translation/orchestration/persistence.py`
- Test: `tests/integration/translation/test_orchestration.py`
- Create: `tests/integration/translation/test_persistence.py`

**Interfaces:**
- Consumes: `TranslationOrchestrator`, `SqlAlchemyTranslationRunStore`, `DocumentSegment`, `ReviewStatus`, and `SegmentStatus`.
- Produces: optional `batch_progress_sink: Callable[[int, int], None]` and persisted accepted translation state.

- [ ] **Step 1: Write a failing progress-callback test**

```python
def test_orchestrator_reports_progress_after_each_batch() -> None:
    provider = _ScriptedProvider([_response(("s1", "Satu")), _response(("s2", "Dua"))])
    updates: list[tuple[int, int]] = []
    orchestrator = TranslationOrchestrator(
        provider,
        InMemoryTranslationRunStore(),
        batch_progress_sink=lambda completed, total: updates.append((completed, total)),
    )
    operation = _operation(
        _segment("s1", "One", order=0),
        _segment("s2", "Two", order=1),
        limits=BatchLimits(max_segments=1),
    )

    asyncio.run(orchestrator.run(operation))

    assert updates == [(1, 2), (2, 2)]
```

Add one cancellation case asserting the callback still reaches `(2, 2)` as each
planned batch becomes terminal without provider calls.

- [ ] **Step 2: Write a failing SQLAlchemy segment persistence test**

Create a migrated temporary database fixture, seed one translation batch context,
invoke `record_result()`, and assert:

```python
with factory() as session:
    segment = session.get(DocumentSegment, SEGMENT_ID)
    assert segment is not None
    assert segment.machine_translation == "Alur kerja dimulai."
    assert segment.status == SegmentStatus.MACHINE_TRANSLATED.value
    assert segment.review_status == ReviewStatus.NOT_REVIEWED.value
```

Add a warning report case expecting `SegmentStatus.NEEDS_REVIEW` and
`ReviewStatus.REVIEW_REQUIRED`.

- [ ] **Step 3: Run focused tests and verify RED**

```powershell
uv run pytest tests/integration/translation/test_orchestration.py tests/integration/translation/test_persistence.py -q
```

Expected: constructor failure for `batch_progress_sink` and unchanged
`DocumentSegment` fields.

- [ ] **Step 4: Add the backward-compatible progress callback**

Extend the constructor with:

```python
batch_progress_sink: Callable[[int, int], None] | None = None,
```

Store it as `_batch_progress_sink`. Iterate with `enumerate(plan.batches, start=1)`
and invoke it in a `finally` block for each batch:

```python
finally:
    if self._batch_progress_sink is not None:
        self._batch_progress_sink(batch_number, len(plan.batches))
```

The callback must not replace the existing final `status_sink`.

- [ ] **Step 5: Update accepted segment state in the same transaction**

Inside `SqlAlchemyTranslationRunStore.record_result()`, load the segment and fail
if it disappeared. After adding `SegmentTranslation`, set:

```python
segment.machine_translation = translated_text_restored
segment.status = (
    SegmentStatus.NEEDS_REVIEW.value
    if report.warnings
    else SegmentStatus.MACHINE_TRANSLATED.value
)
segment.review_status = (
    ReviewStatus.REVIEW_REQUIRED.value
    if report.warnings
    else ReviewStatus.NOT_REVIEWED.value
)
segment.updated_at = _now()
```

Do not modify `reviewed_translation`, `final_text`, locked state, or source fields.

- [ ] **Step 6: Verify and commit**

```powershell
uv run pytest tests/integration/translation/test_orchestration.py tests/integration/translation/test_persistence.py -q
uv run ruff check python/transloka-translation/src/transloka_translation/orchestration tests/integration/translation
uv run mypy python/transloka-translation/src/transloka_translation/orchestration
git add python/transloka-translation/src/transloka_translation/orchestration/service.py python/transloka-translation/src/transloka_translation/orchestration/persistence.py tests/integration/translation/test_orchestration.py tests/integration/translation/test_persistence.py
git commit -m "feat(translation): persist batch progress and segment output"
```

---

### Task 4: Database Translation Operation Loader

**Files:**
- Modify: `services/worker/src/transloka_worker/translation.py`
- Test: `tests/integration/worker/test_translation_runtime.py`

**Interfaces:**
- Consumes: `TranslationCommand`, application models, `load_glossary_snapshot`, `LocalFileStorage`, and `BatchLimits`.
- Produces: `LoadedTranslationJob` and `DatabaseTranslationOperationLoader.load(job_id: str) -> LoadedTranslationJob`.

- [ ] **Step 1: Write failing loader tests for authoritative binding**

Seed a migrated database with one queued translation job, project, document, two
ordered segments, snapshot, and model. Assert:

```python
loaded = DatabaseTranslationOperationLoader(factory, storage).load(JOB_ID)

assert loaded.job_id == JOB_ID
assert loaded.ollama_model_name == "translation-test:latest"
assert loaded.operation is not None
assert loaded.operation.model_id == MODEL_ID
assert loaded.operation.idempotency_key == "translation-runtime-1"
assert loaded.operation.glossary_snapshot_id == SNAPSHOT_ID
assert [segment.segment_id for segment in loaded.operation.segments] == [SEGMENT_1, SEGMENT_2]
assert loaded.operation.batch_limits == BatchLimits(max_segments=5)
```

Parameterize selector tests for all six scopes. Add cases for locked exclusion,
locked inclusion when both flags permit it, untranslated-only filtering,
unreviewed-only filtering, deterministic ordering, and a valid empty selection
returning `operation is None`.

Add fail-closed tests for wrong job type, non-executable status, mismatched active
document, missing/corrupt snapshot, missing/uninstalled model, and malformed
command JSON. A selected segment identifier that does not belong to the bound
document also fails closed. Until a separate semantic-model runner exists,
`run_semantic_validation=True` raises `TranslationWorkerError` with the stable
message "Semantic validation is unavailable." instead of silently ignoring the
requested pass.

- [ ] **Step 2: Run loader tests and verify RED**

```powershell
uv run pytest tests/integration/worker/test_translation_runtime.py -k "loader or scope" -q
```

Expected: `DatabaseTranslationOperationLoader` and `LoadedTranslationJob` are not
defined.

- [ ] **Step 3: Define the loaded job boundary**

```python
@dataclass(frozen=True, slots=True)
class LoadedTranslationJob:
    job_id: str
    idempotency_key: str
    project_id: str
    document_id: str
    ollama_model_name: str
    operation: TranslationOperation | None
    selected_segment_ids: tuple[str, ...]
```

`selected_segment_ids` includes only rows whose worker state may change. An empty
tuple is the successful no-op signal.

- [ ] **Step 4: Implement strict state loading and scope selection**

Implement:

```python
class DatabaseTranslationOperationLoader:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        storage: LocalFileStorage,
    ) -> None:
        self._session_factory = session_factory
        self._storage = storage

    def load(self, job_id: str) -> LoadedTranslationJob:
        _validate_job_id(job_id)
        with self._session_factory() as session:
            return _load_translation_job(session, self._storage, job_id)
```

The query joins `DocumentSegment -> DocumentBlock -> DocumentPage`, outer-joins
`DocumentSection`, filters the job document, and orders by section order (null as
zero), source page number, block page reading order, segment order, then segment
ID. Apply the command scope before status flags. Never include `IGNORED` or
`NOT_TRANSLATABLE`. For `skip_locked_segments=False`, pass `locked=False` into the
domain segment so the canonical batch builder may execute it.

Define the called helpers with these signatures:

```python
def _validate_job_id(job_id: str) -> None:
    """Require canonical job_<uuid> text."""


def _load_translation_job(
    session: Session,
    storage: LocalFileStorage,
    job_id: str,
) -> LoadedTranslationJob:
    """Validate job/command state and build the deterministic loaded boundary."""
```

Map the snapshot rules exactly as:

```python
glossary = tuple(
    TranslationGlossaryEntry(
        source_term=rule.source_term,
        target_term=rule.target_term,
        rule_type=rule.rule_type.value,
    )
    for rule in snapshot.compiled.rules
)
```

Build the operation with the internal model ID, `provider_type="OLLAMA"`, the
application job idempotency key, canonical command JSON in `settings_json`, and
`BatchLimits(max_segments=command.batch_size)`. Map project style into the
translation package enum and context mode into bounded neighbouring
`BatchContext` values. NONE supplies no neighbours. STANDARD supplies the
immediately preceding and following eligible segment. EXTENDED supplies at most
two segments on each side, joined with `"\n"`; truncate each side to 2,000 Unicode
code points. Heading context uses the persisted section title when available and
never exceeds 500 code points.

- [ ] **Step 5: Verify and commit**

```powershell
uv run pytest tests/integration/worker/test_translation_runtime.py -k "command or loader or scope" -q
uv run ruff check services/worker/src/transloka_worker/translation.py tests/integration/worker/test_translation_runtime.py
uv run mypy services/worker/src/transloka_worker/translation.py
git add services/worker/src/transloka_worker/translation.py tests/integration/worker/test_translation_runtime.py
git commit -m "feat(worker): load translation operations from local state"
```

---

### Task 5: Persisted Translation Job Lifecycle

**Files:**
- Modify: `services/worker/src/transloka_worker/translation.py`
- Test: `tests/integration/worker/test_translation_runtime.py`

**Interfaces:**
- Consumes: `LoadedTranslationJob`, `SqlAlchemyTranslationRunStore`, `OllamaTranslationProvider`, `JobProgressService`, and application job models.
- Produces: `DatabaseCancellationSignal` and `ProductionTranslationJobRunner.run(job_id: str) -> TranslationRunResult`.

- [ ] **Step 1: Write failing lifecycle success and no-op tests**

Use a provider factory that records the model name and returns deterministic JSON.
For a successful job assert:

```python
result = runner.run(JOB_ID)

assert result.status is TranslationRunStatus.COMPLETED
assert provider_models == ["translation-test:latest"]
with factory() as session:
    job = session.get(ApplicationJob, JOB_ID)
    assert job is not None
    assert job.status == JobStatus.COMPLETED.value
    assert job.progress == 1.0
    assert json.loads(job.result_json or "")["schema"] == "transloka.translation.job-result.v1"
    attempt = session.scalar(select(JobAttempt).where(JobAttempt.job_id == JOB_ID))
    assert attempt is not None
    assert attempt.status == JobAttemptStatus.COMPLETED.value
```

For an empty loaded job, assert no provider is constructed, the job completes at
progress 1.0, and result lists are empty.

- [ ] **Step 2: Write failing partial, failure, and cancellation tests**

Cover these exact mappings:

```text
TranslationRunStatus.COMPLETED_WITH_WARNINGS -> JobStatus.COMPLETED_WITH_WARNINGS
TranslationRunStatus.PARTIALLY_COMPLETED     -> JobStatus.PARTIALLY_COMPLETED
TranslationRunStatus.FAILED                  -> JobStatus.FAILED
TranslationRunStatus.CANCELLED               -> JobStatus.CANCELLED
```

Assert failed segment IDs become `TRANSLATION_FAILED`; cancelled unprocessed
segments retain their prior text/status; unexpected exceptions persist a sanitized
error code and message, finalize the running attempt as failed, then re-raise.

- [ ] **Step 3: Run lifecycle tests and verify RED**

```powershell
uv run pytest tests/integration/worker/test_translation_runtime.py -k "runner or lifecycle or cancellation" -q
```

Expected: production runner/cancellation imports fail.

- [ ] **Step 4: Implement the database-backed cancellation signal**

```python
class DatabaseCancellationSignal:
    def __init__(self, session_factory: sessionmaker[Session], job_id: str) -> None:
        self._session_factory = session_factory
        self._job_id = job_id

    @property
    def is_cancelled(self) -> bool:
        with self._session_factory() as session:
            row = session.get(ApplicationJob, self._job_id)
            if row is None:
                raise TranslationWorkerError("The translation job was not found.")
            return row.status in {
                JobStatus.CANCELLATION_REQUESTED.value,
                JobStatus.CANCELLED.value,
            }
```

- [ ] **Step 5: Implement the production runner and lifecycle helpers**

Use this public constructor:

```python
class ProductionTranslationJobRunner:
    def __init__(
        self,
        loader: DatabaseTranslationOperationLoader,
        session_factory: sessionmaker[Session],
        temporary_root: Path,
        *,
        provider_factory: Callable[[str], object] | None = None,
        worker_identifier: str | None = None,
    ) -> None:
        self._loader = loader
        self._session_factory = session_factory
        self._temporary_root = temporary_root.resolve(strict=False)
        self._provider_factory = provider_factory or (
            lambda model_name: OllamaTranslationProvider(model_name=model_name)
        )
        self._worker_identifier = _worker_identifier(worker_identifier)

    def run(self, job_id: str) -> TranslationRunResult:
        loaded = self._loader.load(job_id)
        return _run_loaded_translation_job(
            loaded,
            session_factory=self._session_factory,
            temporary_root=self._temporary_root,
            provider_factory=self._provider_factory,
            worker_identifier=self._worker_identifier,
        )
```

The default provider factory is:

```python
lambda model_name: OllamaTranslationProvider(model_name=model_name)
```

Start/resume one `JobAttempt`, set project/document/selected segments to their
translating states, and construct a fresh `SqlAlchemyTranslationRunStore` and
orchestrator per job. Convert `(completed_batches, total_batches)` to progress in
`[0.0, 0.99]`; reserve `1.0` for terminal success. Call
`JobCancellationService.checkpoint(job_id)` after a cancelled result. Finish job,
attempt, document, project, failed-segment, and result JSON fields in one
transaction. Use deterministic UUID5 attempt IDs and the OCR runner's timestamp
format.

The result JSON contains only schema, run ID, status, segment ID lists, warning
count, failure code/segment pairs, and attempt count. It must not contain source
text, prompt text, provider output, local paths, or exception representations.

Define the lifecycle helpers with these exact signatures so their transactions
are independently testable:

```python
def _run_loaded_translation_job(
    loaded: LoadedTranslationJob,
    *,
    session_factory: sessionmaker[Session],
    temporary_root: Path,
    provider_factory: Callable[[str], object],
    worker_identifier: str,
) -> TranslationRunResult:
    """Execute or no-op one loaded job and always persist a terminal lifecycle."""


def _worker_identifier(value: str | None) -> str:
    """Return a validated explicit value or a process-specific local identifier."""


def _start_translation_job(
    session_factory: sessionmaker[Session],
    loaded: LoadedTranslationJob,
    worker_identifier: str,
) -> None:
    """Create/resume the attempt and mark job/document/project/segments running."""


def _finish_translation_job(
    session_factory: sessionmaker[Session],
    loaded: LoadedTranslationJob,
    result: TranslationRunResult,
    worker_identifier: str,
) -> None:
    """Persist terminal job, attempt, document, project, and failed-segment state."""


def _fail_translation_job(
    session_factory: sessionmaker[Session],
    loaded: LoadedTranslationJob,
    error: Exception,
    worker_identifier: str,
) -> None:
    """Persist sanitized failure evidence without masking the original exception."""
```

- [ ] **Step 6: Run lifecycle regressions and commit**

```powershell
uv run pytest tests/integration/worker/test_translation_runtime.py tests/integration/translation -q
uv run ruff check services/worker/src/transloka_worker/translation.py
uv run mypy services/worker/src/transloka_worker/translation.py
git add services/worker/src/transloka_worker/translation.py tests/integration/worker/test_translation_runtime.py
git commit -m "feat(worker): persist translation job lifecycle"
```

---

### Task 6: Stable Huey Task and Worker Composition

**Files:**
- Create: `services/worker/src/transloka_worker/tasks/__init__.py`
- Create: `services/worker/src/transloka_worker/tasks/translation.py`
- Modify: `services/worker/src/transloka_worker/queue.py`
- Modify: `services/worker/src/transloka_worker/app.py`
- Test: `tests/integration/worker/test_sqlite_huey.py`
- Test: `tests/integration/worker/test_translation_runtime.py`

**Interfaces:**
- Consumes: `ProductionTranslationJobRunner`, `create_huey`, and `QueueConfiguration`.
- Produces: `TRANSLATION_TASK_NAME`, `register_translation_task(huey, handler)`, `create_translation_producer(configuration)`, and a production `create_queue_worker()` that registers the handler before consumer creation.

- [ ] **Step 1: Write failing task-name and restart compatibility tests**

```python
def test_translation_task_survives_producer_consumer_restart(tmp_path: Path) -> None:
    configuration = resolve_queue_configuration(tmp_path / "data")
    producer = create_translation_producer(configuration)
    try:
        producer.queue.enqueue(JOB_ID)
        assert producer.huey.pending_count() == 1
    finally:
        producer.close()

    received: list[str] = []
    consumer_huey = create_huey(configuration)
    try:
        register_translation_task(consumer_huey, lambda job_id: received.append(job_id))
        task = consumer_huey.dequeue()
        assert task is not None
        assert task.name == TRANSLATION_TASK_NAME == "transloka.translation.execute"
        assert tuple(task.data) == (JOB_ID,)
        consumer_huey.execute(task)
        assert received == [JOB_ID]
    finally:
        consumer_huey.storage.close()
```

Add a test that two producers have different Huey objects and that both close
their own storage.

- [ ] **Step 2: Run queue tests and verify RED**

```powershell
uv run pytest tests/integration/worker/test_sqlite_huey.py -q
```

Expected: task module and producer factory imports fail.

- [ ] **Step 3: Implement the thin task registry**

In `tasks/translation.py`:

```python
TRANSLATION_TASK_NAME = "transloka.translation.execute"


def register_translation_task(huey: Any, handler: Callable[[str], object]) -> Any:
    if not callable(handler):
        raise ValueError("The translation task handler must be callable.")

    @huey.task(name=TRANSLATION_TASK_NAME)  # type: ignore[untyped-decorator]
    def execute_translation(job_id: str) -> object:
        return handler(job_id)

    return execute_translation
```

The module contains no Huey instance, engine, provider, session, or registered
task at import.

- [ ] **Step 4: Add owned producer resources and registrar-aware consumer creation**

Define:

```python
@dataclass(slots=True)
class TranslationQueueProducer:
    queue: HueyJobQueue
    huey: Any

    def close(self) -> None:
        self.huey.storage.close()


def create_translation_producer(
    configuration: QueueConfiguration | None = None,
) -> TranslationQueueProducer:
    huey = create_huey(configuration)

    def producer_only(_job_id: str) -> Never:
        raise RuntimeError("The API translation producer cannot execute tasks.")

    task = register_translation_task(huey, producer_only)
    return TranslationQueueProducer(HueyJobQueue(task), huey)
```

Extend `create_consumer` with an optional `register_tasks: Callable[[Any], None]`
called after `create_huey()` and before `create_consumer()`.

- [ ] **Step 5: Compose production worker dependencies**

Change `create_queue_worker` to resolve directories, create a synchronous SQLite
engine/session factory, create `LocalFileStorage`, build
`DatabaseTranslationOperationLoader` and `ProductionTranslationJobRunner`, and
register `runner.run` before consumer construction. Keep injectable
`provider_factory` and `worker_identifier` keyword arguments for tests.

Update `QueueWorker.run()` to close the engine and Huey storage in `finally`, once
the consumer exits. `QueueWorker.stop()` remains graceful and idempotent.

- [ ] **Step 6: Verify worker composition and commit**

```powershell
uv run pytest tests/integration/worker/test_sqlite_huey.py tests/integration/worker/test_translation_runtime.py -q
uv run ruff check services/worker/src/transloka_worker
uv run mypy services/worker/src/transloka_worker
git add services/worker/src/transloka_worker/tasks services/worker/src/transloka_worker/queue.py services/worker/src/transloka_worker/app.py tests/integration/worker/test_sqlite_huey.py tests/integration/worker/test_translation_runtime.py
git commit -m "feat(worker): register production translation task"
```

---

### Task 7: FastAPI Producer Lifespan Wiring

**Files:**
- Modify: `services/api/src/transloka_api/app.py`
- Test: `tests/integration/api/test_translation.py`
- Test: `tests/integration/worker/test_sqlite_huey.py`

**Interfaces:**
- Consumes: `create_translation_producer()` from Task 6.
- Produces: production `application.state.translation_queue` and owned queue shutdown.

- [ ] **Step 1: Write failing production lifespan tests**

Add a fixture that does not replace `application.state.translation_queue` and
assert within `TestClient`:

```python
producer = application.state.translation_queue_owner
assert application.state.translation_queue is producer.queue
assert producer.huey.pending_count() == 0
assert producer.huey.storage.filename == str(
    application.state.settings.data_directories.database / "tasks.db"
)
```

Construct two app instances against two temporary data roots and assert their
producer Huey objects and queue database paths differ. After each `TestClient`
closes, assert its storage connection is closed by performing the Huey-supported
closed-resource check used in `test_sqlite_huey.py`.

- [ ] **Step 2: Run focused tests and verify RED**

```powershell
uv run pytest tests/integration/api/test_translation.py tests/integration/worker/test_sqlite_huey.py -k "production_queue or producer" -q
```

Expected: `translation_queue_owner` is absent.

- [ ] **Step 3: Own the producer in the application lifespan**

At lifespan startup:

```python
translation_queue_owner = create_translation_producer(
    resolve_queue_configuration(effective_settings.data_directories.root)
)
application.state.translation_queue_owner = translation_queue_owner
application.state.translation_queue = translation_queue_owner.queue
```

Close it in `finally` before disposing the application engine. Do not recreate it
inside `reopen_database()` because it owns only the separate queue database and no
application session. If producer construction fails, app startup fails rather than
silently installing a null queue.

- [ ] **Step 4: Run API and restore regressions, then commit**

```powershell
uv run pytest tests/integration/api/test_translation.py tests/e2e/backup_restore/test_backup_restore.py tests/integration/worker/test_sqlite_huey.py -q
uv run ruff check services/api/src/transloka_api/app.py
uv run mypy services/api/src/transloka_api/app.py
git add services/api/src/transloka_api/app.py tests/integration/api/test_translation.py tests/integration/worker/test_sqlite_huey.py
git commit -m "feat(api): wire production translation queue"
```

---

### Task 8: Production API-to-Worker E2E and Final Verification

**Files:**
- Create: `tests/e2e/runtime/test_translation_worker_runtime.py`
- A reproduced test failure may modify only files already listed in Tasks 1-7.

**Interfaces:**
- Consumes: production `create_app`, real `tasks.db`, `register_translation_task`, `DatabaseTranslationOperationLoader`, and `ProductionTranslationJobRunner`.
- Produces: executable release evidence for the translation portion of `REL-HIGH-002`.

- [ ] **Step 1: Write the production E2E test**

Use a temporary migrated data root, production `create_app()`, the existing client
headers, and seeded project/document/segment/model data. Set only the health-check
provider on app state so readiness remains deterministic. POST the start route and
exit that API lifespan cleanly. Then open a worker Huey over the same configuration
and register a production runner with an injected deterministic provider:

```python
class DeterministicProvider:
    async def translate(self, request: object, *, cancellation: object = None) -> str:
        del cancellation
        source_data = request.source_data["source_data"]  # type: ignore[attr-defined]
        return json.dumps(
            {
                "segments": [
                    {
                        "segment_id": item["segment_id"],
                        "translated_text": "Alur kerja dimulai.",
                    }
                    for item in source_data["segments"]
                ]
            }
        )
```

Before execution assert the dequeued task name and `tuple(task.data) == (job_id,)`.
Execute through `huey.execute(task)`. Open a fresh API lifespan for the final status
read, then assert:

```python
assert status_body["data"]["status"] == "COMPLETED"
assert status_body["data"]["completed_segments"] == 1
assert status_body["data"]["progress"] == 1.0

with factory() as session:
    job = session.get(ApplicationJob, job_id)
    segment = session.get(DocumentSegment, SEGMENT_ID)
    assert job is not None and job.status == JobStatus.COMPLETED.value
    assert segment is not None and segment.machine_translation == "Alur kerja dimulai."
    assert session.scalar(
        select(func.count()).select_from(TranslationBatch)
    ) == 1
    assert session.scalar(
        select(func.count()).select_from(SegmentTranslation)
    ) == 1
```

Also assert no files ending in `.db`, `.sqlite`, or `.sqlite3` were created beneath
the repository root.

- [ ] **Step 2: Run the E2E test and fix only reproduced failures**

```powershell
uv run pytest tests/e2e/runtime/test_translation_worker_runtime.py -q
```

Expected: PASS through the real production app factory, real temporary SQLite Huey
database, real task registry, and production worker runner without contacting a
real Ollama server.

- [ ] **Step 3: Run focused Python regression groups**

```powershell
uv run pytest tests/integration/api/test_translation.py tests/integration/translation tests/integration/worker tests/e2e/runtime/test_translation_worker_runtime.py -q
uv run pytest tests/e2e/digital/test_digital_pdf.py tests/e2e/scanned/test_scanned_pdf.py tests/e2e/backup_restore/test_backup_restore.py -q
```

Expected: all selected tests pass.

- [ ] **Step 4: Run full repository verification**

```powershell
uv run pytest -q
uv run ruff check .
uv run ruff format --check .
uv run mypy .
pnpm lint
pnpm typecheck
pnpm test
pnpm build
pnpm audit --audit-level high
pnpm --filter @transloka/api-client generate
git diff --exit-code -- packages/api-client/src/generated
git diff --check
```

Expected: every command exits zero; generated client has no drift.

- [ ] **Step 5: Scan runtime database artifacts and inspect scope**

```powershell
Get-ChildItem . -Recurse -Force -File |
    Where-Object { $_.Extension -in ".db", ".sqlite", ".sqlite3" } |
    Select-Object FullName

git status --short
git diff --name-status HEAD~7
```

Expected: no runtime database file inside tracked repository paths; changes remain
inside the spec's implementation and test boundaries.

- [ ] **Step 6: Commit the E2E evidence**

```powershell
git add tests/e2e/runtime/test_translation_worker_runtime.py
git diff --cached --check
git commit -m "test(e2e): verify production translation worker runtime"
git status --short
```

Expected: final working tree is clean. Stop after reporting M11-REM-09; do not
register another task or begin M11-T18.
