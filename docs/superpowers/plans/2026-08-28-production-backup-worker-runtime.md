# M11-REM-12 Production Backup Worker Runtime Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make backup creation a production background job: the production API preserves the public `POST /api/v1/backups` contract (`backup_type`, `include_original_files`, `include_exports`, `include_intermediate_files`) but maps it conservatively to a versioned internal `transloka.backup.command.v1` and enqueues only `job_id` via a new backup queue producer; a concrete worker task reuses `python/transloka-core/src/transloka_core/backup/archive.py:create_backup` to create, verify, and publish an immutable `backups/<archive_name>.zip` while updating `StoredFile(BACKUP)`, `Backup(COMPLETED)`, `ApplicationJob`, and `JobAttempt` atomically. Frontend `backup-panel.tsx` status union is widened to handle every observable `ApplicationJob` status without validation failure.

**Architecture:** The API and worker share one task declaration (`transloka.backup.execute`) from `transloka-worker` while constructing separate `SqliteHuey` instances over `<data-root>/database/tasks.db`. The application DB remains the source of truth for the versioned backup command; a per-job production runner loads that command, runs the existing archive service against `LocalDataDirectories`, and drives `StoredFile`/`Backup` + job publication in one `transaction_scope`. No archive logic is duplicated. Restore remains synchronous. OpenAPI generation updates `packages/api-client/src/generated/schema.ts` only.

**Tech Stack:** Python 3.12, FastAPI lifespan, SQLAlchemy 2 synchronous sessions, Huey `SqliteHuey`, SQLite WAL, Alembic test databases, `transloka-core` archive/manifest/verification, pytest, Ruff, mypy, uv. No new dependency. OpenAPI generation via `pnpm --filter @transloka/api-client generate`.

**Spec:** `docs/superpowers/specs/2026-08-28-production-backup-worker-runtime-design.md` — read it before implementing; it defines the public contract, conservative mapping, truthful response union, lifecycle, cancellation, cleanup, and error mapping.

## Global Constraints

- Register exactly one worker task named `transloka.backup.execute`.
- Huey messages contain only one positional string argument: `job_id`.
- Use `<data-root>/database/tasks.db`; never reuse `transloka.db` as the queue database.
- Keep the default worker count at one thread.
- Construct engines, session factories, Huey instances, task registries, and runners only in factories or lifespans, never at module import.
- Reuse `python/transloka-core/src/transloka_core/backup/archive.py:create_backup` (and `verification.py:verify_backup_archive`) — no duplicate ZipFile/manifest/sqlite-backup logic.
- Storage keys remain `backups/<archive_name>.zip` POSIX relative; never persist absolute paths.
- Preserve the public `POST /api/v1/backups` request contract (`backup_type`, `include_original_files`, `include_exports`, `include_intermediate_files`) verbatim; never expose `include_queue_database` or `include_temporary` as public API fields; reject unsupported `true` values with `422` rather than silently ignoring them.
- Return `data = {job_id, backup_id: null, status: BackupJobStatus}` plus canonical `meta.request_id`; `BackupJobStatus` is the separate creation-job union (`QUEUED`/`RUNNING`/`RETRYING`/`CANCELLATION_REQUESTED`/`COMPLETED`/`COMPLETED_WITH_WARNINGS`/`PARTIALLY_COMPLETED`/`FAILED`/`CANCELLED`/`STALE`) distinct from `BackupStatus` (`QUEUED|RUNNING|COMPLETED|FAILED` for `BackupRecord` at `backup-panel.tsx:14`); `CreateBackupResponse.data.status` at `backup-panel.tsx:42` is the only widened field; do not render job statuses as backup-list badges.
- Keep restore synchronous and untouched (`POST /api/v1/backups/{backup_id}/restore` and `RestoreWorkflow` remain as-is).
- Do cancellation checkpoint **before** `create_backup()` only; once archive creation starts, complete publication safely — never claim cancellation during `create_backup()`, never leave an untracked final archive as normal behavior.
- Clean up any newly moved archive on post-publication verification failure or DB-commit failure before marking `FAILED`; cleanup failure warnings may include only `job_id`, `backup_id` if available, and fixed `error_code` (e.g., `BACKUP_CLEANUP_FAILED`), never `storage_key` or absolute paths.
- The API router must explicitly catch and map `JobIdempotencyConflictError -> 409`, `JobQueueUnavailableError -> 503` with `job_id` (no second DB mutation — the row was already marked `FAILED/QUEUE_DISPATCH_FAILED` by `JobDispatchService`; router only maps to HTTP), `InvalidJobDispatchError`/`BackupWorkerError` -> `422`; `JobDispatchService` itself does not perform HTTP mapping.
- Keep the imported database model `BackupStatus` unchanged; name the creation-job response type `BackupJobStatus` (or use `JobStatus` directly) — never declare a module-level alias named `BackupStatus` inside `routers/backups.py`. Keep `BackupStatus` (`QUEUED|RUNNING|COMPLETED|FAILED`) for `BackupRecord`; `BackupJobStatus` is the separate union above.
- Resolve contradictions: `Backup`/`StoredFile` IDs use `uuid4`; `JobAttempt` IDs use deterministic `uuid5`; `ApplicationJob` lifecycle starts at `QUEUED` (no `CREATED` row); single response model uses `BackupJobStatus`; spec and plan share identical tests and allowed-file lists.
- Do not add database migrations, infrastructure/migrations edits, or schema changes.
- Do not add Python or Node dependencies, `uv.lock`/`pnpm-lock.yaml` edits, or `THIRD_PARTY_LICENSES.md` churn.
- Do not hand-edit `packages/api-client/src/client.ts`; only `packages/api-client/src/generated/schema.ts` is allowed as generator-owned output via `pnpm --filter @transloka/api-client generate` + `check-generated`; `apps/web/src/features/backups/backup-panel.tsx` and `apps/web/src/features/backups/backup-panel.test.tsx` are allowed only to widen the status union.
- Do not modify `docs/releases/**`, `docs/CODEX_TASKS.md`, or `M11-T18`.
- Do not stage or commit unless the implementation authorization explicitly permits it; working-tree changes must be limited to the final allowed-file list below.

## File Map

- `services/worker/src/transloka_worker/backup.py` — NEW: `BackupCommand` (internal four keys), strict `from_payload_json`/`to_payload`, `DatabaseBackupRequestLoader`, `ProductionBackupJobRunner` (+ `BackupWorkerError`), `BackupRunResult`.
- `services/worker/src/transloka_worker/queue.py` — add `BackupQueueProducer` and `create_backup_producer()` paralleling `create_translation/ocr/reconstruction_producer()`.
- `services/worker/src/transloka_worker/tasks/backup.py` — NEW: `BACKUP_TASK_NAME = "transloka.backup.execute"` + `register_backup_task`.
- `services/worker/src/transloka_worker/tasks/__init__.py` — export backup symbol.
- `services/worker/src/transloka_worker/app.py` — compose `DatabaseBackupRequestLoader` + `ProductionBackupJobRunner` in `create_queue_worker()`, extend `close_resources()` to close backup Huey storage.
- `services/api/src/transloka_api/routers/backups.py` — add `POST /api/v1/backups` preserving public contract, conservative mapping, persist `QUEUED` before enqueue, enqueue `job_id`, explicit `409`/`503`/`422` mapping with no second DB mutation on `503`.
- `services/api/src/transloka_api/app.py` — lifespan: create `backup_queue_owner` / `backup_queue`, expose on `application.state`, close in reverse order on shutdown.
- `packages/api-client/src/generated/schema.ts` — generator-owned output only; regenerated via `pnpm --filter @transloka/api-client generate` and verified with `check-generated`.
- `apps/web/src/features/backups/backup-panel.tsx` — add a separate `BackupJobStatus` union for `CreateBackupResponse`; keep `BackupStatus` unchanged for `BackupRecord`.
- `apps/web/src/features/backups/backup-panel.test.tsx` — update/extend to assert widened union handling.
- Tests — `tests/integration/worker/test_backup_command.py`, `tests/integration/worker/test_backup_loader.py`, `tests/integration/worker/test_backup_runtime.py`, `tests/integration/worker/test_sqlite_huey.py` (extend), `tests/integration/api/test_backups.py`, `tests/e2e/runtime/test_backup_worker_runtime.py`.

---

### Task 1: Durable Command and Conservative Public Mapping

**Files:**

- Create: `services/worker/src/transloka_worker/backup.py`
- Create: `tests/integration/worker/test_backup_command.py`

**Interfaces:**

- Consumes: `BackupType` from `transloka_core.backup.manifest`, `ApplicationJob` row.
- Produces: `BackupCommand` dataclass (internal four keys), `BackupWorkerError`, mapping function `public_to_internal(public_payload) -> BackupCommand`.

- [ ] **Step 1: Write failing tests for the versioned backup command and public mapping**

Add imports for `json`, `BackupCommand`, `BackupWorkerError`, `BACKUP_COMMAND_SCHEMA` and assertions equivalent to:

```python
def test_backup_command_round_trips_for_supported_types():
    for backup_type in ("DATABASE_ONLY","METADATA","FULL_PROJECTS"):
        cmd = BackupCommand(backup_type=backup_type)
        payload = cmd.to_payload()
        assert payload == {"schema":"transloka.backup.command.v1","backup_type":backup_type,"include_queue_database":False,"include_temporary":False}
        assert BackupCommand.from_payload_json(json.dumps(payload)).backup_type == backup_type

def test_backup_command_rejects_duplicate_keys():
    raw = '{"schema":"transloka.backup.command.v1","backup_type":"DATABASE_ONLY","include_queue_database":false,"include_temporary":false,"backup_type":"DATABASE_ONLY"}'
    with pytest.raises(BackupWorkerError): BackupCommand.from_payload_json(raw)

def test_backup_command_rejects_unknown_field():
    payload = {"schema":"transloka.backup.command.v1","backup_type":"DATABASE_ONLY","include_queue_database":False,"include_temporary":False,"extra":True}
    with pytest.raises(BackupWorkerError): BackupCommand.from_payload_json(json.dumps(payload))

def test_backup_command_rejects_full_application():
    with pytest.raises(BackupWorkerError): BackupCommand.from_payload_json(json.dumps({"schema":"transloka.backup.command.v1","backup_type":"FULL_APPLICATION","include_queue_database":False,"include_temporary":False}))

def test_public_request_with_true_include_flags_rejected():
    # API-level: include_original_files/include_exports/include_intermediate_files == true -> 422
    for field in ("include_original_files","include_exports","include_intermediate_files"):
        resp = client.post("/api/v1/backups", json={"backup_type":"DATABASE_ONLY", field: True, **{k:False for k in other_two}}, headers=idempotency)
        assert resp.status_code == 422
        assert "not supported" in resp.json()["error"]["message"].lower()

def test_public_request_all_false_maps_to_internal_false_false():
    resp = client.post("/api/v1/backups", json={"backup_type":"METADATA","include_original_files":False,"include_exports":False,"include_intermediate_files":False}, headers=idempotency)
    assert resp.status_code == 202
    assert json.loads(session.get(ApplicationJob, job_id).payload_json) == {"schema":"transloka.backup.command.v1","backup_type":"METADATA","include_queue_database":False,"include_temporary":False}
```

Include: missing field, wrong schema, non-bool internal flags, `PRE_RESTORE` rejection, canonical JSON deterministic (`sort_keys`, `separators`), case-sensitive `backup_type`.

- [ ] **Step 2: Implement `BackupCommand` with strict JSON validation and the conservative mapper**

```python
BACKUP_COMMAND_SCHEMA = "transloka.backup.command.v1"
_COMMAND_FIELDS = frozenset({"schema","backup_type","include_queue_database","include_temporary"})
_SUPPORTED = frozenset({BackupType.DATABASE_ONLY.value, BackupType.METADATA.value, BackupType.FULL_PROJECTS.value})

@dataclass(frozen=True, slots=True)
class BackupCommand:
    backup_type: str
    include_queue_database: bool = False
    include_temporary: bool = False
    def __post_init__(self):
        if type(self.include_queue_database) is not bool or type(self.include_temporary) is not bool: raise BackupWorkerError
        if self.backup_type not in _SUPPORTED: raise BackupWorkerError
    def to_payload(self) -> dict[str, object]:
        return {"schema":BACKUP_COMMAND_SCHEMA,"backup_type":self.backup_type,"include_queue_database":self.include_queue_database,"include_temporary":self.include_temporary}
    @classmethod
    def from_payload_json(cls, value: str) -> Self:
        # object_pairs_hook duplicate-key guard, exact field set, schema check
        ...

def map_public_backup_request(public: CreateBackupRequest) -> BackupCommand:
    # public has backup_type, include_original_files, include_exports, include_intermediate_files
    if public.include_original_files or public.include_exports or public.include_intermediate_files:
        # conservative: reject any true explicitly — archive service has no per-category filter
        raise BackupWorkerError("include_original_files/include_exports/include_intermediate_files is not supported by the current backup service")
    return BackupCommand(backup_type=public.backup_type, include_queue_database=False, include_temporary=False)
```

Duplicate detection mirrors `translation.py:465 _decode_translation_command`. Never expose `include_queue_database`/`include_temporary` in the OpenAPI request schema.

- [ ] **Step 3: Run focused command tests**

```powershell
uv run ruff check .
uv run mypy .
uv run pytest tests/integration/worker/test_backup_command.py -q
```

### Task 2: Loader

**Files:**

- Modify: `services/worker/src/transloka_worker/backup.py`
- Create: `tests/integration/worker/test_backup_loader.py`

- [ ] **Step 1: Write failing loader tests**

```python
def test_loader_loads_after_api_dispatch_commits():
    loaded = loader.load(job_id)
    assert loaded.job_id == job_id and loaded.command.backup_type == "METADATA"

def test_loader_rejects_wrong_job_type():  # TRANSLATE_DOCUMENT job
    with pytest.raises(BackupWorkerError): loader.load(other_job_id)

def test_loader_rejects_corrupt_payload():
    job.payload_json = "not json"
    with pytest.raises(BackupWorkerError): loader.load(job_id)

def test_loader_rejects_queue_mismatch():
    job.queue_name = "transloka-api"
    with pytest.raises(BackupWorkerError): loader.load(job_id)
```

- [ ] **Step 2: Implement `DatabaseBackupRequestLoader`**

```python
@dataclass(frozen=True, slots=True)
class LoadedBackupJob: job_id: str; idempotency_key: str; command: BackupCommand

class DatabaseBackupRequestLoader:
    def load(self, job_id: str) -> LoadedBackupJob:
        _validate_identifier(job_id,"job_")
        with session_factory() as session:
            job = session.get(ApplicationJob, job_id)
            if job is None or job.job_type != JobType.BACKUP_DATABASE.value: raise BackupWorkerError
            if job.status not in {JobStatus.QUEUED.value, JobStatus.RETRYING.value, JobStatus.RUNNING.value, JobStatus.CANCELLATION_REQUESTED.value, JobStatus.CANCELLED.value}: raise BackupWorkerError
            command = BackupCommand.from_payload_json(job.payload_json)
            return LoadedBackupJob(job.id, job.idempotency_key, command)
```

No filesystem access; directories resolved only by runner.

- [ ] **Step 3: Run focused loader tests**

```powershell
uv run ruff check .
uv run pytest tests/integration/worker/test_backup_loader.py -q
```

### Task 3: Thin Huey Task and Queue Producer

**Files:**

- Create: `services/worker/src/transloka_worker/tasks/backup.py`
- Modify: `services/worker/src/transloka_worker/tasks/__init__.py`
- Modify: `services/worker/src/transloka_worker/queue.py`

- [ ] **Step 1: Write failing tests for the task name and producer-only contract**

```python
def test_backup_task_name_is_canonical():
    assert BACKUP_TASK_NAME == "transloka.backup.execute"

def test_backup_producer_only_raises():
    producer = create_backup_producer(configuration)
    with pytest.raises(RuntimeError): producer.queue.enqueue("job_test")

def test_create_queue_worker_registers_four_tasks():
    create_queue_worker(configuration, worker_identifier="test")
    assert set(registered) == {"transloka.translation.execute","transloka.ocr.execute","transloka.reconstruction.execute","transloka.backup.execute"}
```

- [ ] **Step 2: Implement the task registry**

`services/worker/src/transloka_worker/tasks/backup.py`:

```python
BACKUP_TASK_NAME = "transloka.backup.execute"
def register_backup_task(huey, handler):
    if not callable(handler): raise ValueError
    @huey.task(name=BACKUP_TASK_NAME)
    def execute_backup(job_id: str) -> object: return handler(job_id)
    return execute_backup
```

`tasks/__init__.py`: export `BACKUP_TASK_NAME`, `register_backup_task`.

`queue.py`:

```python
@dataclass(slots=True)
class BackupQueueProducer:
    queue: HueyJobQueue
    huey: Any
    def close(self): self.huey.storage.close()

def create_backup_producer(configuration=None) -> BackupQueueProducer:
    huey = create_huey(configuration)
    def producer_only(_job_id: str) -> Never: raise RuntimeError("The API backup producer cannot execute tasks.")
    task = register_backup_task(huey, producer_only)
    return BackupQueueProducer(HueyJobQueue(task), huey)
```

- [ ] **Step 3: Run focused queue tests**

```powershell
uv run ruff check .
uv run mypy .
uv run pytest tests/integration/worker/test_sqlite_huey.py -q -k backup
```

### Task 4: Production Backup Runner (reuse archive service, before-only cancellation, cleanup without path leakage)

**Files:**

- Modify: `services/worker/src/transloka_worker/backup.py` (extend)
- Create: `tests/integration/worker/test_backup_runtime.py`

- [ ] **Step 1: Write failing tests for the runner**

```python
def test_runner_creates_validated_file_and_backup_and_completes_job(tmp_path):
    result = runner.run(job_id)  # internal type DATABASE_ONLY/METADATA/FULL_PROJECTS
    assert result.status == JobStatus.COMPLETED and result.backup_id.startswith("bkp_")
    assert stored_file.status == FileStatus.VALIDATED.value and stored_file.is_immutable == 1
    assert backup.file_id == stored.id and stored.storage_key.startswith("backups/")
    assert job.progress == 1.0 and attempt.status == JobAttemptStatus.COMPLETED.value
    assert verify_backup_archive(root / stored.storage_key).manifest.backup_type.value == backup_type

def test_runner_fails_on_insufficient_disk(monkeypatch):
    monkeypatch.setattr("transloka_core.backup.archive.get_free_disk_bytes", lambda _d: 0)
    with pytest.raises(InsufficientBackupSpaceError): runner.run(job_id)
    assert job.status == JobStatus.FAILED.value

def test_runner_cancellation_before_archive_leaves_no_backup_row():
    JobCancellationService(factory, tmp_root).request(job_id)
    result = runner.run(job_id)
    assert result.status == JobStatus.CANCELLED and not backup_exists()

def test_runner_cancellation_during_archive_still_publishes_safely(fake_create_backup_slow):
    # checkpoint is before create_backup only; flag flipped after entry must still COMPLETE
    result = runner.run(job_id)  # create_backup entered before flag set
    assert result.status == JobStatus.COMPLETED

def test_runner_exact_once_on_already_completed_does_not_create_second_archive():
    runner.run(job_id); n = count_backups()
    runner.run(job_id); assert count_backups() == n

def test_runner_verification_failure_deletes_unreferenced_archive(monkeypatch, caplog):
    monkeypatch.setattr("transloka_core.backup.verification.verify_backup_archive", lambda *a, **kw: (_ for _ in ()).throw(BackupVerificationError()))
    with pytest.raises(BackupVerificationError): runner.run(job_id)
    assert not Path(root / artifact_storage_key).exists() and job.status == JobStatus.FAILED.value
    # warning log contains only job_id, backup_id, BACKUP_CLEANUP_FAILED — no storage_key
    assert "BACKUP_CLEANUP_FAILED" in caplog.text and "backups/" not in caplog.text

def test_runner_db_commit_failure_deletes_unreferenced_archive(monkeypatch, caplog):
    monkeypatch.setattr("transloka_core.database.transaction_scope", failing_scope)
    with pytest.raises(Exception): runner.run(job_id)
    assert not Path(root / artifact_storage_key).exists()
    assert "BACKUP_CLEANUP_FAILED" in caplog.text and "backups/" not in caplog.text
```

IDs: `Backup`/`StoredFile` use `uuid4` (`bkp_<uuid4>`, `fil_<uuid4>`), `JobAttempt` uses deterministic `uuid5(NAMESPACE_URL, f"transloka:backup-attempt:{job_id}:{n}")`.

- [ ] **Step 2: Implement `ProductionBackupJobRunner`**

Construction: `ProductionBackupJobRunner(loader, session_factory, temporary_root: Path, *, worker_identifier: str|None=None)`. Resolve `directories` from injected `LocalDataDirectories` (preferred) or from `session_factory`'s bound engine data-root.

`run(job_id)` (cancellation before only):

```python
def run(self, job_id: str):
    existing = _completed_result(session_factory, job_id)
    if existing is not None: return existing  # idempotent, no second archive
    loaded = self._loader.load(job_id)
    if JobCancellationService(session_factory, self._temporary_root).checkpoint(job_id):
        return _finish_cancelled(factory, loaded, identifier)  # CANCELLED, no Backup row
    try:
        _start_attempt(factory, job_id, identifier)
        JobProgressService(factory).update(job_id, progress=0.05, current_stage="BACKUP_PREPARING")
        directories = self._directories or resolve_local_data_directories(data_root)
        # single non-interruptible call; no checkpoint during it
        artifact = create_backup(directories, loaded.command.backup_type,
                                 include_queue_database=loaded.command.include_queue_database,
                                 include_temporary=loaded.command.include_temporary)
        # verify before DB publish; on failure delete the just-moved archive (restricted warning)
        try:
            verify_backup_archive(directories.root / artifact.storage_key, data_root=directories.root)
        except Exception as verr:
            try: Path(directories.root / artifact.storage_key).unlink(missing_ok=True)
            except OSError: pass
            else:
                # warning with only job_id, backup_id if allocated, fixed code — no storage_key
                logger.warning("BACKUP_CLEANUP_FAILED", extra={"job_id": job_id, "error_code": "BACKUP_CLEANUP_FAILED"})
            _fail_job(factory, job_id, verr, identifier); raise
        # publish atomically; on DB failure delete the unreferenced archive with same restricted warning
        try:
            return _publish(factory, loaded, artifact, identifier)
        except Exception as pub_err:
            try: Path(directories.root / artifact.storage_key).unlink(missing_ok=True)
            except OSError: pass
            else:
                logger.warning("BACKUP_CLEANUP_FAILED", extra={"job_id": job_id, "backup_id": getattr(artifact, "backup_id", None), "error_code": "BACKUP_CLEANUP_FAILED"})
            _fail_job(factory, job_id, pub_err, identifier); raise
    except Exception as exc:
        # _fail_job already called for verify/publish branches; for other branches call it here
        if not _is_already_failed(session_factory, job_id):
            _fail_job(factory, job_id, exc, identifier)
        raise
```

`_publish` (`transaction_scope`): `fil_<uuid4>`, `bkp_<uuid4>`, `StoredFile(BACKUP, backups/..., VALIDATED, is_immutable=1)`, `Backup(COMPLETED, file_id, ...)`, `ApplicationJob(COMPLETED, progress=1.0, result_json=transloka.backup.job.v1 {backup_id, storage_key})`, `JobAttempt(COMPLETED)`. If `ApplicationJob` already `COMPLETED` with a `Backup`, return early (exact-once).

- [ ] **Step 3: Run focused runner tests**

```powershell
uv run ruff check .
uv run ruff format --check .
uv run mypy .
uv run pytest tests/integration/worker/test_backup_runtime.py -q
```

### Task 5: Atomic Production API Dispatch (preserve public contract, explicit error mapping, no second mutation on 503)

**Files:**

- Modify: `services/api/src/transloka_api/routers/backups.py`
- Modify: `services/api/src/transloka_api/app.py`
- Modify: `apps/web/src/features/backups/backup-panel.tsx`
- Modify: `apps/web/src/features/backups/backup-panel.test.tsx`
- Create: `tests/integration/api/test_backups.py`

- [ ] **Step 1: Write failing API tests proving no shadowing and exact-status replay via single dispatch**

```python
def test_database_BackupStatus_not_shadowed():
    # imported BackupStatus is the persisted Backup ORM lifecycle enum, not the TypeScript BackupRecord type
    assert BackupStatus.__name__ == "BackupStatus" and set(BackupStatus) == {"CREATED","RUNNING","COMPLETED","FAILED","CANCELLED"}
    assert "BackupStatus =" not in open("services/api/src/transloka_api/routers/backups.py").read().split("class CreateBackup")[0]

def test_CreateBackupResponse_uses_BackupJobStatus():
    # BackupJobStatus is the separate creation-job union for CreateBackupResponse.data.status
    from typing import get_args

    assert set(get_args(BackupJobStatus)) == {"QUEUED","RUNNING","RETRYING","CANCELLATION_REQUESTED","COMPLETED","COMPLETED_WITH_WARNINGS","PARTIALLY_COMPLETED","FAILED","CANCELLED","STALE"}

def test_create_backup_persists_queued_job_and_enqueues_only_job_id(client_factory, tmp_path):
    resp = client.post("/api/v1/backups", json={"backup_type":"METADATA","include_original_files":False,"include_exports":False,"include_intermediate_files":False},
                       headers={"Idempotency-Key":"backup-1","X-TransLoka-Client":"web","X-TransLoka-Client-Version":"0.1.0"})
    assert resp.status_code == 202 and resp.json()["data"]["backup_id"] is None and resp.json()["data"]["status"] == "QUEUED"
    assert huey.dequeue().args == (job_id,)

def test_create_backup_idempotent_dispatch_returns_exact_persisted_status(monkeypatch):
    # seed via JobDispatchService.dispatch() that returns RUNNING/FAILED/STALE — API must return that exact status, not hard-coded QUEUED
    for persisted in ("RUNNING","FAILED","STALE","RETRYING","CANCELLATION_REQUESTED","COMPLETED_WITH_WARNINGS","PARTIALLY_COMPLETED"):
        dispatch_result = type("R", (), {"job_id": job_id, "status": JobStatus(persisted)})()
        monkeypatch.setattr(JobDispatchService, "dispatch", lambda *a, **kw: dispatch_result)
        resp = client.post("/api/v1/backups", json={"backup_type":"METADATA","include_original_files":False,"include_exports":False,"include_intermediate_files":False}, headers={"Idempotency-Key": f"replay-{persisted}"})
        assert resp.json()["data"]["status"] == persisted and resp.json()["data"]["job_id"] == job_id

def test_concurrent_existing_dispatch_does_not_enqueue_twice(monkeypatch):
    # JobDispatchService returns existing job with result.created == False — huey.pending_count unchanged
    assert huey.pending_count() == 1

def test_create_backup_never_fails_validation_for_valid_persisted_status():
    for status in ("QUEUED","RUNNING","RETRYING","CANCELLATION_REQUESTED","COMPLETED","COMPLETED_WITH_WARNINGS","PARTIALLY_COMPLETED","FAILED","CANCELLED","STALE"):
        assert client.post(..., headers={"Idempotency-Key": f"replay-{status}"}).status_code == 202

def test_create_backup_queue_unavailable_returns_503_with_job_id_and_no_second_mutation(monkeypatch):
    resp = client.post(..., headers={"Idempotency-Key":"fail"})
    assert resp.status_code == 503 and resp.json()["error"]["code"] == "QUEUE_UNAVAILABLE" and resp.json()["error"]["details"]["job_id"] == job_id
    # JobDispatchService already marked FAILED/QUEUE_DISPATCH_FAILED — router did no second mutation
    assert session.get(ApplicationJob, job_id).error_code == "QUEUE_DISPATCH_FAILED"

def test_create_backup_idempotency_conflict_409_on_different_payload():
    client.post(..., json={"backup_type":"DATABASE_ONLY", ...}, headers={"Idempotency-Key":"conflict"})
    resp = client.post(..., json={"backup_type":"METADATA", ...}, headers={"Idempotency-Key":"conflict"})
    assert resp.status_code == 409

def test_create_backup_maps_invalid_dispatch_and_worker_errors_to_422():
    assert client.post(..., json={"backup_type":"FULL_APPLICATION", ...}).status_code == 422
    assert client.post(..., json={"backup_type":"DATABASE_ONLY","include_original_files":True, ...}).status_code == 422
```

```ts
// backup-panel.test.tsx — TypeScript status domains (separate file, not Python BackupStatus)
test("BackupRecord retains only backup lifecycle statuses", () => {
  // backup-panel.tsx:14 BackupStatus stays QUEUED|RUNNING|COMPLETED|FAILED for BackupRecord
  expectTypeOf<BackupStatus>().toEqualTypeOf<"QUEUED" | "RUNNING" | "COMPLETED" | "FAILED">();
});
test("backup-panel separate domains", () => {
  // backup-panel.tsx:14 BackupStatus unchanged and backup-panel.tsx:42 BackupJobStatus are two separate unions
  expectTypeOf<BackupJobStatus>().not.toEqualTypeOf<BackupStatus>();
});
test("create-result message is truthful for every BackupJobStatus", () => {
  // exercises CreateBackupResponse variants via the create action, not a backup-list badge
  for (const status of ["QUEUED","RUNNING","RETRYING","CANCELLATION_REQUESTED","COMPLETED","COMPLETED_WITH_WARNINGS","PARTIALLY_COMPLETED","FAILED","CANCELLED","STALE"] as const) {
    const response: CreateBackupResponse = { data: { job_id: "job_...", backup_id: null, status }, meta: { request_id: "req_..." } };
    expect(`Backup job ${response.data.status}: ${response.data.job_id}`).toBe(`Backup job ${status}: ${response.data.job_id}`);
  }
});
```

Include: reject unknown `backup_type`, missing `Idempotency-Key` → `422`. Do not assert job statuses as backup-list badges — domains are separate; only `BackupRecord` badges use `BackupStatus`. No `GET /api/v1/backups` assertion (separate work).

- [ ] **Step 2: Implement the route (conservative mapper, widened union, explicit mapping with no second mutation)**

`services/api/src/transloka_api/routers/backups.py` — add above the existing restore route, without modifying it; keep imported `BackupStatus` (persisted `Backup` ORM lifecycle enum `CREATED|RUNNING|COMPLETED|FAILED|CANCELLED` used by existing backup routes) unchanged, add separate `BackupJobStatus`:

```python
from transloka_core.database.models.backups import BackupStatus  # persisted Backup ORM lifecycle enum — unchanged
from transloka_core.database.models.jobs import JobStatus

BackupJobStatus = Literal["QUEUED","RUNNING","RETRYING","CANCELLATION_REQUESTED","COMPLETED","COMPLETED_WITH_WARNINGS","PARTIALLY_COMPLETED","FAILED","CANCELLED","STALE"]

class CreateBackupRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    backup_type: Literal["DATABASE_ONLY","METADATA","FULL_PROJECTS"]
    include_original_files: bool = False
    include_exports: bool = False
    include_intermediate_files: bool = False

class CreateBackupData(BaseModel):
    job_id: str
    backup_id: None = None
    status: BackupJobStatus

class CreateBackupResponse(BaseModel):
    data: CreateBackupData
    meta: ResponseMeta

@router.post("", operation_id="create_backup", response_model=CreateBackupResponse, status_code=202)
def create_backup(payload: CreateBackupRequest, request: Request,
                  idempotency_key: Annotated[str, Header(alias="Idempotency-Key", min_length=1, max_length=200)]):
    # 1. conservative public->internal mapping; reject unsupported true values
    if payload.include_original_files or payload.include_exports or payload.include_intermediate_files:
        raise TransLokaError(code="VALIDATION_ERROR", message="include_original_files/include_exports/include_intermediate_files is not supported by the current backup service", status_code=422)
    command = BackupCommand(backup_type=payload.backup_type, include_queue_database=False, include_temporary=False)
    # 2. single dispatch — rely on JobDispatchService idempotency comparison, no manual pre-read
    try:
        result = JobDispatchService(_session_factory(request), _backup_queue(request)).dispatch(
            job_type=JobType.BACKUP_DATABASE, idempotency_key=idempotency_key, command_payload=command.to_payload())
    except JobIdempotencyConflictError as exc:
        raise TransLokaError(code="IDEMPOTENCY_CONFLICT", status_code=409, ...) from exc
    except JobQueueUnavailableError as exc:
        # JobDispatchService already marked FAILED/QUEUE_DISPATCH_FAILED — only map to HTTP, no second mutation
        raise TransLokaError(code="QUEUE_UNAVAILABLE", status_code=503, details={"job_id": exc.job_id}) from exc
    except (InvalidJobDispatchError, BackupWorkerError) as exc:
        raise TransLokaError(code="VALIDATION_ERROR", status_code=422, ...) from exc
    # return actual persisted status from dispatch result, not hard-coded QUEUED
    return CreateBackupResponse(data=CreateBackupData(job_id=result.job_id, backup_id=None, status=result.status.value), meta=ResponseMeta(request_id=_request_id()))
```

`_backup_queue(request)` reads `request.app.state.backup_queue`; if absent, raise `503 QUEUE_NOT_CONFIGURED` (fail closed). Validation via Pydantic ensures missing `Idempotency-Key` → `422`. Never declare `BackupStatus =` alias in this module — `BackupStatus` remains the persisted `Backup` ORM lifecycle enum (`CREATED|RUNNING|COMPLETED|FAILED|CANCELLED`) used by existing backup routes; `BackupRecord` is a separate TypeScript frontend type.

Update `apps/web/src/features/backups/backup-panel.tsx`:

```ts
// :14 — unchanged BackupRecord domain
type BackupStatus = "QUEUED" | "RUNNING" | "COMPLETED" | "FAILED";
// :42 — separate domain for creation job
type BackupJobStatus = "QUEUED" | "RUNNING" | "RETRYING" | "CANCELLATION_REQUESTED" | "COMPLETED" | "COMPLETED_WITH_WARNINGS" | "PARTIALLY_COMPLETED" | "FAILED" | "CANCELLED" | "STALE";
type CreateBackupResponse = { data: { job_id: string; backup_id: string | null; status: BackupJobStatus } };
```

Create-result message: `Backup job ${status}: ${job_id}` — truthful, not a backup-list badge. `backup-panel.test.tsx` exercises `CreateBackupResponse` variants via the create action; do not render job statuses as backup-list badges (different domains).

- [ ] **Step 3: Wire lifespan and generated client**

`services/api/src/transloka_api/app.py:lifespan()` — nest a fourth producer alongside translation/ocr/reconstruction (same reverse-close order):

```python
try:
    translation_queue_owner = create_translation_producer(...)
    try:
        ocr_queue_owner = create_ocr_producer(...)
        try:
            reconstruction_queue_owner = create_reconstruction_producer(...)
            try:
                backup_queue_owner = create_backup_producer(resolve_queue_configuration(data_directories.root))
            except Exception:
                reconstruction_queue_owner.close(); raise
        except Exception: ocr_queue_owner.close(); raise
    except Exception: translation_queue_owner.close(); raise
except Exception: engine.dispose(); raise
application.state.backup_queue_owner = backup_queue_owner
application.state.backup_queue = backup_queue_owner.queue
...
finally:
    backup_queue_owner.close()
    reconstruction_queue_owner.close()
    ocr_queue_owner.close()
    translation_queue_owner.close()
    engine.dispose()
```

After adding the route, regenerate and verify the generator-owned client (no clean-diff assertion):

```powershell
pnpm --filter @transloka/api-client generate
pnpm --filter @transloka/api-client check-generated
```

Never hand-edit `schema.ts`, never modify `client.ts` (except the two panel files above).

- [ ] **Step 4: Run API tests**

```powershell
uv run ruff check .
uv run mypy .
uv run pytest tests/integration/api/test_backups.py -q
```

### Task 6: Runtime E2E Evidence (production app -> tasks.db -> worker)

**Files:**

- Create: `tests/e2e/runtime/test_backup_worker_runtime.py`

- [ ] **Step 1: Write the runtime E2E (no GET /backups list assertion; correct StoredFile ownership)**

```python
def test_backup_app_to_tasksdb_to_worker_completes_and_publishes(tmp_path):
    root = tmp_path / "backup-runtime-e2e"
    command.upgrade(Config(str(REPOSITORY_ROOT / "alembic.ini")), "head")
    directories = resolve_local_data_directories(root)
    app = create_app(Settings(data_directories=directories))
    with TestClient(app) as client:
        resp = client.post("/api/v1/backups",
            json={"backup_type":"METADATA","include_original_files":False,"include_exports":False,"include_intermediate_files":False},
            headers={"Idempotency-Key":"e2e-backup-1","X-TransLoka-Client":"web","X-TransLoka-Client-Version":"0.1.0"})
        assert resp.status_code == 202 and resp.json()["data"]["backup_id"] is None and resp.json()["data"]["status"] == "QUEUED"
        job_id = resp.json()["data"]["job_id"]
        huey = create_huey(resolve_queue_configuration(root))
        task = huey.dequeue()
        assert task is not None and task.name == "transloka.backup.execute" and task.args == (job_id,)
        factory = create_session_factory(create_sqlite_engine(directories))
        storage = LocalFileStorage(directories)
        runner = ProductionBackupJobRunner(DatabaseBackupRequestLoader(factory, storage), factory, directories.temporary)
        result = runner.run(job_id)
        assert result.status == JobStatus.COMPLETED
    with factory() as session:
        job = session.get(ApplicationJob, job_id)
        assert job.status == JobStatus.COMPLETED.value and job.progress == 1.0
        attempt = session.scalars(select(JobAttempt).where(JobAttempt.job_id==job_id)).one()
        assert attempt.status == JobAttemptStatus.COMPLETED.value
        stored = session.scalar(select(StoredFile).where(StoredFile.file_role==FileRole.BACKUP.value))
        backup = session.get(Backup, stored.file_id and session.scalar(select(Backup.id).where(Backup.file_id==stored.id)) or None)  # simplified: assert backup.file_id == stored.id
        # correct ownership assertion:
        assert backup.file_id == stored.id and stored.storage_key.startswith("backups/")
        assert Path(directories.root / stored.storage_key).is_file()
    v = verify_backup_archive(directories.root / stored.storage_key, data_root=directories.root)
    assert v.manifest.backup_type.value == "METADATA"
    # idempotent replay via POST with same key after completion
    resp2 = client.post("/api/v1/backups", json={"backup_type":"METADATA","include_original_files":False,"include_exports":False,"include_intermediate_files":False}, headers={"Idempotency-Key":"e2e-backup-1","X-TransLoka-Client":"web","X-TransLoka-Client-Version":"0.1.0"})
    assert resp2.json()["data"]["status"] == "COMPLETED" and resp2.json()["data"]["job_id"] == job_id
    # GET /jobs/{job_id} reflects COMPLETED; no assertion on GET /backups list
    assert client.get(f"/api/v1/jobs/{job_id}").json()["data"]["status"] == "COMPLETED"
    # re-execution idempotent, no second archive
    assert runner.run(job_id).status == JobStatus.COMPLETED
```

Explicitly assert `backup.file_id == stored.id` and `stored.storage_key.startswith("backups/")` (`Backup` has no `storage_key`). Assert progress/heartbeat, immutable `StoredFile(BACKUP, VALIDATED, is_immutable=1)`, independent `app.state.backup_queue_owner.close()` + `worker.close_resources()` + `engine.dispose()`.

- [ ] **Step 2: Run focused suites**

```powershell
uv run pytest tests/e2e/runtime/test_backup_worker_runtime.py tests/integration/worker/test_backup_*.py tests/integration/api/test_backups.py tests/integration/worker/test_sqlite_huey.py -q
```

## Final Verification and Integration

Run (working-tree changes must be limited to the exact allowed-file list below; do not stage or commit unless the implementation authorization explicitly permits it):

```powershell
uv run ruff check .
uv run ruff format --check .
uv run mypy .
uv run pytest tests/integration/backup -q
uv run pytest tests/security/backup -q
uv run pytest tests/e2e/backup_restore -q
uv run pytest tests/integration/worker/test_job_dispatch.py -q
uv run pytest -m "not slow and not requires_ollama and not requires_gpu" -q
pnpm lint
pnpm typecheck
pnpm test
pnpm build
pnpm audit --audit-level high
pnpm --filter @transloka/api-client generate
pnpm --filter @transloka/api-client check-generated
git diff --check
git status --porcelain
```

Do not run `git diff --exit-code -- packages/api-client/src/generated/schema.ts` — the generated schema is an expected implementation change; clean-diff is valid only after it has been committed. Scan for stray runtime artifacts (`*.db`/`*.zip` only in `tmp_path` fixtures). When green, hold — do not fast-forward into `main`, do not create a tag, and do not start `M11-T18`. Report the verification matrix in the completion report.

## Exact Allowed-File List for Implementation

Implementation PR for `M11-REM-12` may touch **only** these exact paths:

```
services/worker/src/transloka_worker/backup.py
services/worker/src/transloka_worker/queue.py
services/worker/src/transloka_worker/tasks/backup.py
services/worker/src/transloka_worker/tasks/__init__.py
services/worker/src/transloka_worker/app.py
services/api/src/transloka_api/routers/backups.py
services/api/src/transloka_api/app.py
packages/api-client/src/generated/schema.ts
apps/web/src/features/backups/backup-panel.tsx
apps/web/src/features/backups/backup-panel.test.tsx
tests/integration/api/test_backups.py
tests/integration/worker/test_backup_command.py
tests/integration/worker/test_backup_loader.py
tests/integration/worker/test_backup_runtime.py
tests/integration/worker/test_sqlite_huey.py
tests/e2e/runtime/test_backup_worker_runtime.py
```

Do not add any public endpoint beyond `POST /api/v1/backups`; do not queue restore; do not add UI beyond the two panel files; do not add a migration; do not add a dependency; do not hand-edit the generated client.
