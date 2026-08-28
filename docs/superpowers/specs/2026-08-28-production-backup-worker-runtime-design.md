# M11-REM-12 Production Backup Worker Runtime Design

## Goal

Close the backup portion of release blocker `REL-HIGH-002` by connecting the canonical backup creation path to the local `SqliteHuey` queue and a production runner that reuses the existing verified archive service. The current repository already ships a correct, verified archive creator (`python/transloka-core/src/transloka_core/backup/archive.py:create_backup`), manifest builder (`manifest.py:build_manifest`), verifier (`verification.py:verify_backup_archive`), and rollback-safe restore workflow (`restore.py:RestoreWorkflow`). The production application, however, has no `BACKUP_DATABASE` Huey task, no backup queue producer, and no worker-side loader/runner; backup creation (if exposed) would still run on the API thread against `isolation: none`. This remediation completes backup as a background job without duplicating archive logic, without a migration, and without touching restore.

Relates to `docs/releases/PERSONAL_MVP_RELEASE_CHECKLIST.md:REL-HIGH-002` (worker registry empty) and `M2-T09/M11-T03-T06` backup foundation. `M11-REM-12` is not yet registered in `docs/CODEX_TASKS.md` — that document is not modified by this design. Restore remains synchronous by explicit scope (`MAINTENANCE_MARKER`, `RestoreWorkflow`) unless a future queued-restore decision is taken.

## Authority and Existing Behavior

Canonical authority order (`docs/MASTER_CODEX_PROMPT.md:C`):

1. `docs/API_CONTRACT.md:17 Idempotency`, `19 Job Resource`, `92 Create Backup`, `93 List Backups`
2. `docs/ARCHITECTURE.md:35 Backup Data Flow`, `12 Filesystem`, `5-8 Worker`
3. `docs/DATABASE_SCHEMA.md:32 Application Jobs`, `38 Backup Tables`, `16 Stored Files`
4. `docs/SECURITY.md:AE Backup and Restore Rules`, `31-38 Filesystem Security`, `43-45 Archive Security`
5. `docs/IMPLEMENTATION_PLAN.md:20 M11 Hardening` + `docs/TECH_STACK_DECISIONS.md` (`SqliteHuey`, no Celery/Redis)

Existing backup API (`services/api/src/transloka_api/routers/backups.py:42`):

- only `POST /api/v1/backups/{backup_id}/restore` (synchronous `RestoreWorkflow.restore()` + `MaintenanceGate`);
- no `POST /api/v1/backups`, no `BACKUP_DATABASE` producer;

Existing worker (`services/worker/src/transloka_worker/app.py:133`):

- registers `transloka.translation.execute`, `transloka.ocr.execute`, `transloka.reconstruction.execute`;
- no `transloka.backup.execute`;

Existing queue (`services/worker/src/transloka_worker/queue.py:26`):

- `TranslationQueueProducer`, `OCRQueueProducer`, `ReconstructionQueueProducer` + `create_translation/ocr/reconstruction_producer()`;
- no `BackupQueueProducer`, no `create_backup_producer()`;

Frontend (`apps/web/src/features/backups/backup-panel.tsx:42`) already expects `POST /api/v1/backups` with `Idempotency-Key` returning `{job_id, backup_id: null, status}` plus canonical `meta`. That file currently declares `CreateBackupResponse.data.status: "QUEUED"` (literal) at `backup-panel.tsx:42`, while `backup-panel.tsx:14` declares `BackupStatus = "QUEUED" | "RUNNING" | "COMPLETED" | "FAILED"` for `BackupRecord` — two separate domains that must remain separate. The missing producer is therefore a contract gap, not a new product idea.

## Scope

### In scope — exactly

- `POST /api/v1/backups` as a thin, additive job-dispatch endpoint (202 + `ApplicationJob`) that enqueues **only** `job_id` via a new backup queue producer;
- a versioned durable command `transloka.backup.command.v1` persisted in `application_jobs.payload_json`;
- a new `transloka.backup.execute` Huey task and `BackupQueueProducer` constructed only in factories (no module-import side effects);
- composition of `DatabaseBackupRequestLoader` + `ProductionBackupJobRunner` in `create_queue_worker()` alongside translation/OCR/reconstruction;
- API lifespan wiring of the backup producer and exact-once shutdown of its Huey storage;
- worker-side reuse of `create_backup()` / `verify_backup_archive()` / atomic `os.replace` + `StoredFile(BACKUP, VALIDATED, is_immutable=1)` + `Backup(COMPLETED)` publication;
- `ApplicationJob`/`JobAttempt` lifecycle, progress, heartbeat, cancellation checkpoint (before archive creation only), and failure mapping;
- focused integration and runtime E2E tests proving `app -> tasks.db -> worker -> transloka.db + backups/<archive_name>` with real migrated DBs and no ephemeral `--with` dependencies;
- generator-owned `packages/api-client/src/generated/schema.ts` refreshed via `pnpm --filter @transloka/api-client generate` and verified with `check-generated`;
- adding a separate `BackupJobStatus` union for `CreateBackupResponse` in `apps/web/src/features/backups/backup-panel.tsx` and its test to handle every observable `ApplicationJob` status without validation failure, while keeping `BackupStatus` (`QUEUED | RUNNING | COMPLETED | FAILED`) unchanged for `BackupRecord`.

Payload on the wire is intentionally minimal: `job_id:str`. All inputs (backup type, conservatively mapped public flags) are re-derived from the persisted command and `LocalDataDirectories`. No PDF bytes, glossary, filesystem paths, or provider objects cross the queue.

### Out of scope — do not do

- queued restore, restore workflow redesign, or changes to `POST /{backup_id}/restore`, `RestoreWorkflow`, `FileRestoreCoordinator`, or `MAINTENANCE_MARKER_FILENAME` (`docs/ARCHITECTURE.md:36`, `SECURITY.md:46`);
- list/verify/download/delete endpoints (`GET /api/v1/backups`, `POST /{id}/verify`, `GET /{id}/download`, `DELETE /{id}`) — they remain separate work unless already implemented; this remediation asserts only `POST /backups`, `GET /jobs/{job_id}`, DB rows, and archive artifact;
- UI changes except the two files `apps/web/src/features/backups/backup-panel.tsx` and `apps/web/src/features/backups/backup-panel.test.tsx` to add a separate `BackupJobStatus` union for `CreateBackupResponse` (keeping `BackupStatus` for `BackupRecord` unchanged); all other `apps/web/**` is out of scope; hand-editing `packages/api-client/src/client.ts` is out of scope — only `packages/api-client/src/generated/schema.ts` is allowed as generator output;
- database migration or schema change (`infrastructure/migrations/**`, `0017_backups` already correct: `python/transloka-core/src/transloka_core/database/models/backups.py:28`);
- new Python or Node dependency, `uv.lock`/`pnpm-lock.yaml` edits, or `THIRD_PARTY_LICENSES.md` churn;
- WeasyPrint/ReportLab/render concerns, OCR/translation/reconstruction pipeline redesign, worker concurrency redesign (`DEFAULT_WORKER_COUNT=1`), launcher/process-manager changes;
- `docs/releases/PERSONAL_MVP_RELEASE_CHECKLIST.md` or `M11-T18` work, tag creation, or `docs/CODEX_TASKS.md` edits.

## Whether a New Public API Endpoint Is Necessary

**Decision: yes — `POST /api/v1/backups` is required.**

Rationale by governing documents:

- `docs/API_CONTRACT.md:92 Create Backup` normatively specifies `POST /api/v1/backups` with `Idempotency-Key`, `202 Accepted`, body including `backup_type` and response `{job_id, backup_id}`; `2.4 Explicit Jobs` requires `backup` to be a background job; `17 Idempotency` lists `create backup` as mandatory `Idempotency-Key`. The current production router violates this contract by exposing no creation endpoint. `apps/web/src/features/backups/backup-panel.tsx:34` already calls `POST /api/v1/backups`.
- `docs/ARCHITECTURE.md:35` backup flow is `Create backup job -> Collect files -> Generate manifest -> Create controlled archive -> Calculate checksum -> Verify archive -> Mark completed` — explicitly a job flow, not a synchronous API thread operation. `docs/SECURITY.md:AE` requires checksum/manifest/version/included-content and atomic publication after verification — also a job concern.
- `docs/MVP_SCOPE.md:35 MUST IMPLEMENT — Backup and Restore` and `docs/IMPLEMENTATION_PLAN.md:20` list backup creation as a hardening deliverable.

Compatibility and security implications:

- **Compatibility:** additive, no existing route is modified. `POST /{backup_id}/restore` remains untouched. Returning `202` with `{job_id, backup_id: null, status}` (see Response Contract) matches the precedent of `POST /projects/{id}/translation/start` and `POST /projects/{id}/reconstruction/start` plus `POST /documents/{id}/ocr/start` — all `202` with `job_id`. Because OpenAPI changes, `packages/api-client/src/generated/schema.ts` must be regenerated via `pnpm --filter @transloka/api-client generate` and verified with `check-generated` — never hand-edited. Frontend `backup-panel.tsx:42` keeps `BackupStatus` unchanged for `BackupRecord` and adds a separate `BackupJobStatus` union for `CreateBackupResponse` so replay of a terminal job does not fail validation.
- **Security:** the new route inherits the canonical API middleware stack already validated for translation/OCR/reconstruction: default `127.0.0.1` binding guard (`services/api/src/transloka_api/config.py`), `Origin` allowlist (`middleware/origin.py`), `X-TransLoka-Client` header preflight (`middleware/client_headers.py`), `RequestId` tracing, and normalized error envelope that never exposes absolute paths or tracebacks (`exception_handlers/`). Additional controls: `Idempotency-Key` length 1..200, content-type `application/json`, strict public `BackupType` allowlist, disk-space pre-check via `get_free_disk_bytes()` with `16 MiB` safety margin (as `backup/archive.py:37`), atomic temp-file-then-`os.replace`, no `shell=True`, no remote fetch, verification via `verify_backup_archive()` before publication. Not exposing absolute storage keys in the creation response (only `job_id` + `backup_id: null` until completion) avoids the `SECURITY.md:32 Relative Storage Keys` leakage that other endpoints already prevent.

Restore remains deliberately **out of scope** because no governing document requires queued restoration for the Local-First Personal MVP. `API_CONTRACT.md:96 Restore Backup` describes maintenance-mode behavior; the proven synchronous `RestoreWorkflow` with `create_pre_restore_backup`, temp extraction, path/checksum validation, and atomic replacement already satisfies `SECURITY.md:46 Restore Security`. Queued restore would introduce cross-process database lifecycle and maintenance-gate reentrance with no documented requirement; it is deferred.

## Public Request Contract and Internal Mapping

### Public request — preserved verbatim

`POST /api/v1/backups` must preserve the frontend contract `apps/web/src/features/backups/backup-panel.tsx:34` and `docs/API_CONTRACT.md:92`:

```json
{
  "backup_type": "DATABASE_ONLY",
  "include_original_files": false,
  "include_exports": false,
  "include_intermediate_files": false
}
```

- `backup_type` allowlist: `DATABASE_ONLY`, `METADATA`, `FULL_PROJECTS`. `FULL_APPLICATION` and `PRE_RESTORE` are rejected with `422` (see `backup/archive.py:90 UnsupportedBackupTypeError`).
- `include_original_files`, `include_exports`, `include_intermediate_files` are strict `bool` fields defaulting to `false`. Pydantic model uses `extra="forbid"` — unknown fields are rejected, not ignored.
- Internal fields `include_queue_database` and `include_temporary` are **never** exposed as public API fields and must not appear in the OpenAPI request schema or frontend payload.

### Conservative mapping to `BackupCommand` and `create_backup()`

The durable internal command (`transloka.backup.command.v1`) stores the mapped result, not the raw public flags:

```json
{
  "schema": "transloka.backup.command.v1",
  "backup_type": "METADATA",
  "include_queue_database": false,
  "include_temporary": false
}
```

Mapping rules (explicit, validated at the API boundary before `JobDispatchService`):

1. `backup_type` maps one-to-one to `create_backup(directories, backup_type, ...)` first positional arg. Values are canonicalized to upper-case and validated against `_SUPPORTED_TYPES` (`DATABASE_ONLY`, `METADATA`, `FULL_PROJECTS`).
2. Public `include_*` flags that the existing archive service **cannot honor** must be rejected explicitly rather than silently ignored. The archive service today selects content solely by `backup_type` (plus `include_queue_database`/`include_temporary` for `tasks.db`/temp). There is no per-category `original_files`/`exports`/`intermediate_files` filter. Therefore:
    - if `include_original_files == true` → `422 VALIDATION_ERROR` (`"include_original_files is not supported by the current backup service"`).
    - if `include_exports == true` → `422`.
    - if `include_intermediate_files == true` → `422`.
    - Only the all-false combination (`false, false, false`) for these three fields maps to `include_queue_database=false, include_temporary=false` and is accepted.
3. The mapping is documented as conservative to avoid a silent partial backup that the frontend would misinterpret as complete. A future archive enhancement that adds per-category selection would extend the mapper and add integration tests without changing the public field names — the depleted rejection guarantees forward compatibility.

The API constructs `BackupCommand(backup_type, include_queue_database=false, include_temporary=false)` after the mapping/validation step and persists its `to_payload()` canonical JSON in `application_jobs.payload_json`. The raw public request body is not stored.

### Validation at the API boundary

- `json.loads` via Pydantic, but internal `BackupCommand.from_payload_json()` additionally enforces duplicate-key rejection via `object_pairs_hook` — a tampered `payload_json` in the DB never reaches the runner without failing closed with `BackupWorkerError`.
- `backup_type` case-sensitive exact match; no coercion of lowercase.

## Response Contract and Idempotent Replay

### Truthful strategy — keep two status domains separate

`apps/web/src/features/backups/backup-panel.tsx:14` declares `BackupStatus = "QUEUED" | "RUNNING" | "COMPLETED" | "FAILED"` for `BackupRecord` (the `backups` table lifecycle `DATABASE_SCHEMA.md:38`). `backup-panel.tsx:42` declares `CreateBackupResponse.data.status: "QUEUED"` (single literal) for the creation job. Returning any broader backup lifecycle status as a job status would conflate two domains, and always returning `"QUEUED"` for idempotent replay would report a false persisted state when the job has already left `QUEUED` (e.g., `RUNNING`, `FAILED`, `CANCELLED`, `RETRYING`, `CANCELLATION_REQUESTED`, `COMPLETED_WITH_WARNINGS`, `PARTIALLY_COMPLETED`, `STALE`).

**Chosen truthful strategy: keep `BackupStatus` unchanged and add a separate `BackupJobStatus` union for `CreateBackupResponse`.** The implementation must:

- keep the imported database model `BackupStatus` unchanged (still `CREATED | RUNNING | COMPLETED | FAILED | CANCELLED` per `python/transloka-core/src/transloka_core/database/models/backups.py:14`) — never declare a module-level alias named `BackupStatus` inside `services/api/src/transloka_api/routers/backups.py`; name the creation-job response type `BackupJobStatus` or use `JobStatus` directly after validating the desired public members;
- keep `BackupStatus` for `BackupRecord` exactly as `QUEUED | RUNNING | COMPLETED | FAILED` (no job statuses mixed in);
- add `BackupJobStatus = "QUEUED" | "RUNNING" | "RETRYING" | "CANCELLATION_REQUESTED" | "COMPLETED" | "COMPLETED_WITH_WARNINGS" | "PARTIALLY_COMPLETED" | "FAILED" | "CANCELLED" | "STALE"` for `CreateBackupResponse.data.status`, and change **only** that field to `BackupJobStatus`.

```ts
// backup-panel.tsx:14 — unchanged
type BackupStatus = "QUEUED" | "RUNNING" | "COMPLETED" | "FAILED";
// backup-panel.tsx:42 — widened, separate domain
type BackupJobStatus = "QUEUED" | "RUNNING" | "RETRYING" | "CANCELLATION_REQUESTED" | "COMPLETED" | "COMPLETED_WITH_WARNINGS" | "PARTIALLY_COMPLETED" | "FAILED" | "CANCELLED" | "STALE";
type CreateBackupResponse = {
  data: { job_id: string; backup_id: string | null; status: BackupJobStatus };
  meta: { request_id: string };
};
```

### Response shape — compatible after adding separate union

```json
{
  "data": { "job_id": "job_...", "backup_id": null, "status": "QUEUED" },
  "meta": { "request_id": "req_..." }
}
```

- `job_id` is always present (`job_<uuid4>` 40 chars, prefixed check per `DATABASE_SCHEMA.md:32`). `backup_id` is **always `null` at `POST /backups` response time** because the `Backup` row (`bkp_<uuid4>`) is created only by the worker after the archive artifact exists — this preserves `ck_backups_completed_requirements` (`COMPLETED` requires `file_id`, `size_bytes`, `checksum_sha256`, `completed_at`).
- `status` is `BackupJobStatus` — the current persisted `ApplicationJob` status for that `Idempotency-Key`. At creation it is `QUEUED`; on idempotent replay it is the actual observed value (see table below). The Pydantic response model declares `BackupJobStatus` as above (or directly uses validated `JobStatus` members) so validation never fails merely because a valid persisted `JobStatus` is observed.
- `meta.request_id` is populated from `get_request_id()` (as translation/reconstruction do via `schemas/projects.py:ResponseMeta`).

### Idempotent replay behavior

`Idempotency-Key` (1..200 printable, `Header(alias="Idempotency-Key")`) is the operation scope per `API_CONTRACT.md:17`. Canonicalization uses `json.dumps(command.to_payload(), sort_keys=True, separators=(",",":"), allow_nan=False)` so `row.payload_json == canonical` is the idempotency comparator.

| Existing `ApplicationJob` state for the key | Replayed request `payload_json` | Behavior |
|---|---|---|
| none | — | Create `ApplicationJob(QUEUED, progress=0.0)` then `enqueue(job_id)` → `202 {job_id, backup_id:null, status:QUEUED}` |
| `QUEUED`, same canonical payload | same | Return same `job_id`, `status:QUEUED` (current row status), do not enqueue a second `tasks.db` task (`huey.pending_count` unchanged) → `202` |
| `RUNNING`, same payload | same | Return same `job_id`, `status:RUNNING` → `202` (worker already holds `RUNNING` attempt) |
| `RETRYING`, same payload | same | Return same `job_id`, `status:RETRYING` → `202` |
| `CANCELLATION_REQUESTED`, same payload | same | Return same `job_id`, `status:CANCELLATION_REQUESTED` → `202` |
| `COMPLETED`, `COMPLETED_WITH_WARNINGS`, `PARTIALLY_COMPLETED`, same payload | same | Return same `job_id`, `status:COMPLETED` (or respective completed variant) → `202`; `backup_id` still `null` at this endpoint (creation response never synthesizes `Backup` ID; completed backup discoverable via `GET /jobs/{job_id}` result or DB query); no second archive → `202` |
| `FAILED`, same payload | same | Return same `job_id`, `status:FAILED` → `202` (no auto-retry; caller must supply a new `Idempotency-Key` to retry) |
| `CANCELLED`, same payload | same | Return same `job_id`, `status:CANCELLED` → `202` |
| `STALE`, same payload | same | Return same `job_id`, `status:STALE` → `202`; `STALE` is a recovery label, not a worker-written terminal status, but replay must still succeed without scheduling a duplicate task |
| any state, **different** canonical payload (different `backup_type`) | differs | `409 IDEMPOTENCY_CONFLICT` (`JobIdempotencyConflictError`) — key belongs to a different operation |

This matches `JobDispatchService` semantics already exercised by `tests/integration/worker/test_job_dispatch.py:111` and the idempotent `POST /{backup_id}/restore` path in `routers/backups.py:202`. The frontend after widening handles each status without type error; the creation endpoint truthfully reports the persisted status rather than a hard-coded `"QUEUED"`.

## Worker Command Payload

New versioned schema: `transloka.backup.command.v1` (four keys only, as mapped above):

```json
{
  "schema": "transloka.backup.command.v1",
  "backup_type": "DATABASE_ONLY",
  "include_queue_database": false,
  "include_temporary": false
}
```

- `schema` is the exact string `transloka.backup.command.v1`.
- `backup_type` enumerates the **existing** `BackupType` values supported by `backup/archive.py:40 _SUPPORTED_TYPES`: `DATABASE_ONLY`, `METADATA`, `FULL_PROJECTS`. `FULL_APPLICATION` and `PRE_RESTORE` are rejected by the command.
- `include_queue_database` and `include_temporary` are strict `bool` fields defaulting to `false`, supplied only by the API mapper — never by the frontend. The API mapper today always writes `false/false` (see mapping table); the internal command retains these flags for future archive extension without migration.

Validation (mirrors `translation.py:113` and `ocr.py:77` strict JSON):

- decode via `json.loads(..., object_pairs_hook=rejectDuplicateKeys)` — duplicate JSON keys fail closed with `BackupWorkerError`;
- reject unknown, missing, extra, or wrong-typed fields (exact `_COMMAND_FIELDS` match);
- reject unsupported `schema` strings;
- reject non-`bool` flags, wrong `backup_type` case/value, `FULL_APPLICATION`/`PRE_RESTORE` requests;
- `to_payload()` and `from_payload_json()` are inverses; `from_payload_json()` also validates against the same field set so a tampered `payload_json` never reaches the runner.

The command is the **only** durable execution input besides `job_id`. No directory path, model file, or user display name crosses `tasks.db`.

## Reuse of Existing Archive Services

Implementation must **call, not duplicate** `python/transloka-core/src/transloka_core/backup/archive.py`. Required reuse:

- `create_backup(directories, backup_type, include_queue_database, include_temporary) -> BackupArchiveArtifact` for `DATABASE_ONLY`/`METADATA`/`FULL_PROJECTS`;
- the archive's internal `ensure_local_data_directories()`, `get_free_disk_bytes()` + `_SAFETY_MARGIN_BYTES`, `_copy_sqlite_database()` via `sqlite3 backup API`, `_build_manifest()`/`verify_manifest()`, `_write_archive()` with `ZIP_DEFLATED`+`compresslevel=9`, `_verify_archive()` with manifest/namelist/`testzip()`/checksum checks, and atomic `os.replace()` to `directories.backups / archive_name`.

Specifically, no new `ZipFile` loop, no new `manifest.json` construction, no new `sqlite3 backup` copy is introduced in the worker package. `storage_key` remains `backups/<archive_name>` as `archive.py:158` (`backups` POSIX relative key, verified by `tests/integration/backup/test_database_backup.py:62`). The runner is responsible only for loading the command, invoking the service, translating its artifact into `StoredFile`+`Backup` rows, and updating the job.

Verification before publication must also reuse `verify_backup_archive(archive_path, data_root=root)` from `backup/verification.py:114` — at minimum the archive is re-opened and `MANIFEST_MAX_BYTES`, path safety, checksum, and SQLite integrity are re-checked before the database commit is considered successful.

## Backup and ApplicationJob Lifecycle Transitions

### ApplicationJob (`python/transloka-core/src/transloka_core/database/models/jobs.py:22`, `DATABASE_SCHEMA.md:32`)

Job type is always `BACKUP_DATABASE`. Queue name is `transloka` (`services/worker/src/transloka_worker/queue.py:22 QUEUE_NAME`); do **not** reuse `transloka-api` (that value is specific to the synchronous restore pseudo-job `routers/backups.py:40`). Lifecycle for this remediation (no `CREATED` row — API writes `QUEUED` directly, matching the existing `JobDispatchService` precedent used by translation/OCR/reconstruction):

```
QUEUED -> RUNNING        -> COMPLETED
                   -> COMPLETED_WITH_WARNINGS
                   -> PARTIALLY_COMPLETED
                   -> FAILED
                   -> CANCELLED
        -> RETRYING -> RUNNING (via generic retry, not used within this remediation directly)
        -> CANCELLATION_REQUESTED -> CANCELLED
STALE is a recovery label applied by stale-recovery, not by the runner.
```

- `QUEUED` is written **before** enqueue (API). `RUNNING` is set by the worker on first successful `load()` before archiving begins, with `progress=0.0`, `current_stage="BACKUP_RUNNING"`, `heartbeat_at=now`. A cancellation checkpoint before archiving transitions directly to `CANCELLED` without invoking `create_backup()`.
- `COMPLETED` (`progress=1.0`, `current_stage=COMPLETED`, `completed_at=now`, `heartbeat_at=now`, `result_json` set) only after the archive artifact, `StoredFile`, `Backup`, and `JobAttempt` have all committed in one `transaction_scope`. `COMPLETED_WITH_WARNINGS`/`PARTIALLY_COMPLETED` are valid terminal states that the response model must accept without validation failure, even though the backup worker itself currently maps all successes to `COMPLETED`.
- `FAILED` (`current_stage=FAILED`, `error_code`, `error_message` truncated to 500 printable chars, `completed_at`, `heartbeat_at`) on any `BackupArchiveError` / `InsufficientBackupSpaceError` / verification error / unexpected exception after `RUNNING`.
- `CANCELLED` when `JobCancellationService.checkpoint(job_id)` returns true **before** `create_backup()`; no artifact is published and the attempt is closed as `CANCELLED` without creating a `Backup` row. No cancellation is attempted during `create_backup()` itself.
- Enqueue failure after `QUEUED` commit: API mapping handles it via `JobQueueUnavailableError -> 503` (see Error Mapping); `JobDispatchService` has already marked the row `FAILED/QUEUE_DISPATCH_FAILED` — the router must not perform a second DB mutation.

`payload_json` stores the canonical command JSON (`sort_keys=True`, `separators=(",",":")`, `allow_nan=False`), immutable for idempotency comparison (`JobDispatchService` `row.payload_json == payload_json`).

### Backup (`python/transloka-core/src/transloka_core/database/models/backups.py:14`, `infrastructure/migrations/versions/0017_backups.py:17`)

```
(no row at QUEUED/RUNNING) -> COMPLETED
                            -> FAILED (optional, with error_code)
(no row on CANCELLED — worker leaves no orphan Backup)
```

- For the async `BACKUP_DATABASE` path, **no `Backup` row is created in the API**. The worker creates the row exactly once, inside the same transaction that creates the `StoredFile` and completes the job. This avoids the `ck_backups_completed_requirements` (`status NOT IN ('COMPLETED') OR (file_id IS NOT NULL ...)`) violation that would occur if the API inserted a `COMPLETED` placeholder before the artifact exists.
- `COMPLETED` row requires `file_id IS NOT NULL`, `size_bytes NOT NULL`, `checksum_sha256` lowercase 64-hex, `completed_at NOT NULL`, `included_content_json` valid JSON array. Source of truth for `id` is `bkp_<uuid4>` (40 chars, prefixed check with `uuid4`), `application_version` from `importlib.metadata.version("transloka-core")` via `archive.py`, `database_schema_version` from `verify_database()`'s `alembic_version`, `included_content` from `artifact.manifest.included_content` (includes `backup-warning.txt` per `archive.py:133`).
- `FAILED` rows are optional and should carry `error_code` (uppercased exception type, 100 chars) and truncated message; they are not required for idempotent replay.
- `PRE_RESTORE` type is never used by this queue (reserved for `restore.py`).

### JobAttempt (`DATABASE_SCHEMA.md:32.2`)

- `attempt_number` starts at 1, deterministic `id = uuid5(NAMESPACE_URL, f"transloka:backup-attempt:{job_id}:{n}")` for attempts only — `Backup` and `StoredFile` IDs use `uuid4` per `DATABASE_SCHEMA.md:8 Identifier Convention` and existing `infrastructure/migrations/versions/0017_backups.py:22`. The two ID families are intentionally different (attempts deterministic for exact-once retry, backup artifacts random for uniqueness);
- `RUNNING` on worker start, `COMPLETED`/`FAILED`/`CANCELLED` on terminal, `worker_identifier` from `COMPUTERNAME/HOSTNAME/transloka-worker` fallback, truncated to 200 printable chars;
- at most one `RUNNING` attempt per `job_id`; re-invocation of an already `COMPLETED` job must not create a new attempt (idempotent early return).

## Transaction and Enqueue Ordering

API (`POST /api/v1/backups`) must follow the proven **persist-then-enqueue** pattern that translation (`routers/translation.py:243`), OCR (`routers/ocr.py:120`), and reconstruction (`routers/reconstruction.py:180`) already established, but without a manual pre-read — rely on `JobDispatchService.dispatch()` idempotency:

1. Validate request body (`backup_type` allowlist, `extra="forbid"`), reject `include_* == true` per mapping table with `422`, validate `Idempotency-Key` (1..200 printable). Do **not** perform a manual `select ApplicationJob where idempotency_key == key` before dispatch; `JobDispatchService.dispatch()` already implements the exact idempotency comparison (`row.job_type == job_type and row.payload_json == canonical`) and returns the existing progressed job without enqueuing a second task.
2. Call `result = JobDispatchService(session_factory, backup_queue).dispatch(job_type=BACKUP_DATABASE, idempotency_key=idempotency_key, command_payload=command.to_payload())` **once**; do not hard-code `"QUEUED"` — return `status = result.status.value` (the actual persisted value, validated by `BackupJobStatus`). This avoids the race where `dispatch()` returns an existing `RUNNING`/`FAILED`/`STALE` job while the route hard-codes `QUEUED`. On success, return `202 {job_id: result.job_id, backup_id: null, status: result.status.value}` with `meta.request_id`. `result.created` indicates whether a new `tasks.db` entry was enqueued.
3. On `Huey` enqueue exception, `JobDispatchService` has already marked the row `FAILED` with `QUEUE_DISPATCH_FAILED` (as `python/transloka-core/src/transloka_core/jobs/dispatch.py:146 _mark_dispatch_failed`). The router must only catch `JobQueueUnavailableError` and raise `TransLokaError(code="QUEUE_UNAVAILABLE", status_code=503, details={"job_id": job_id})`; it must not attempt a second database status mutation.
4. Worker `load()` validates the job is `QUEUED/RETRYING/RUNNING` (and `CANCELLATION_REQUESTED/CANCELLED` for checkpoint) and that `payload_json` decodes to a legal command. Worker transitions `QUEUED->RUNNING` only inside its own `transaction_scope` after `load()` succeeds, creating `JobAttempt(RUNNING)` atomically.
5. Artifact publication is a **single** `transaction_scope`: create `StoredFile` (`BACKUP`, `storage_key=backups/...`, `is_immutable=1`, `status=VALIDATED`), create `Backup(COMPLETED, ...)` with `file_id` foreign key, update `ApplicationJob(COMPLETED)`, complete `JobAttempt(COMPLETED)`. `completion` of the file on the filesystem (`os.replace` to `backups/`) occurs **before** this transaction; verification (`verify_backup_archive`) occurs after the file move but still before the DB commit. See Cleanup section for commit-failure handling.

This ordering removes the reconstruction race (where a consumer observed an `ApplicationJob` before its `ReconstructionJob`) because the backup type has no secondary linked table besides `Backup` itself — the artifact rows are created by the worker, not the API.

## StoredFile and Backup Persistence Requirements (existing schema only)

No migration. All columns are exactly those in `infrastructure/migrations/versions/0017_backups.py:22` and `python/transloka-core/src/transloka_core/storage/local.py`.

**StoredFile** (`DATABASE_SCHEMA.md:16.1`):

- `id = fil_<uuid4>`, `project_id=None`, `document_id=None` (backup is global, not project-scoped);
- `file_role = BACKUP`, `storage_key = backups/<archive_name>.zip` (POSIX, unique), `original_filename = safe_filename = Path(storage_key).name`, `mime_type = application/zip`, `size_bytes = artifact.size_bytes`, `checksum_sha256 = artifact.checksum_sha256` (lowercase 64-hex), `is_immutable = 1`, `status = VALIDATED` (validated by `verify_backup_archive` before DB commit), `metadata_json = null`;
- `created_at = artifact.created_at` (from `archive.py:133 _timestamp()`), `deleted_at=None`.

**Backup**:

- `id = bkp_<uuid4>` (40 chars, `uuid4`, prefixed check), `backup_type = command.backup_type`, `file_id = StoredFile.id`, `application_version = artifact.manifest.application_version`, `database_schema_version = artifact.manifest.database_schema_version`, `status = COMPLETED`, `size_bytes`, `checksum_sha256`, `included_content_json = json.dumps(list(artifact.included_content), sort_keys=True, separators=(",",":"))`, `created_at = artifact.created_at`, `completed_at = now`, `error_code = None`.

Both rows must be inserted with `session.flush()` ordering `StoredFile` then `Backup` to satisfy the foreign key, and the unique `storage_key` constraint ensures no duplicate archive after idempotent replay.

## Runtime Registration and Producer Requirements

| Component | Requirement |
|---|---|
| Huey task name | exactly `transloka.backup.execute` (`services/worker/src/transloka_worker/tasks/backup.py:4`), paralleling `transloka.translation.execute`, `transloka.ocr.execute`, `transloka.reconstruction.execute` — single char-for-char string, no variant |
| Task signature | `def execute_backup(job_id: str) -> object` — one positional `str`, no kwargs, no `project_id`/`payload` |
| Registration | `register_backup_task(huey, handler) -> task` via `@huey.task(name=BACKUP_TASK_NAME)` (`tasks/backup.py:7`) |
| Queue name | `QUEUE_NAME = "transloka"` (`queue.py:22`) for all producers; backup uses the same name |
| Queue DB | `<data-root>/database/tasks.db` (`QueueConfiguration.database_path`), never `transloka.db` |
| Worker thread | exactly `DEFAULT_WORKER_COUNT = 1` (`queue.py:20`) |
| Producer class | `BackupQueueProducer(queue: HueyJobQueue, huey: Any)` with `close()` -> `huey.storage.close()` (`queue.py:57`) |
| Producer factory | `create_backup_producer(configuration) -> BackupQueueProducer` that calls `create_huey()` then `register_backup_task(huey, producer_only)` where `producer_only(_job_id: str) -> Never: raise RuntimeError("The API backup producer cannot execute tasks.")` — matches `create_translation/ocr/reconstruction_producer()` `Never` contract |
| API lifespan | `services/api/src/transloka_api/app.py:lifespan()` must create `backup_queue_owner = create_backup_producer(resolve_queue_configuration(data_directories.root))` inside the same nested `try/except` that already creates translation/ocr/reconstruction owners, store `application.state.backup_queue_owner` + `application.state.backup_queue`, and close it exactly once on shutdown (reverse order: backup, reconstruction, ocr, translation) plus the synchronous `restore_workflow` and engine disposal — parallel to the existing three-producer wiring |
| Worker consumer | `services/worker/src/transloka_worker/app.py:create_queue_worker()` must create one engine, one `LocalFileStorage`, one `DatabaseBackupRequestLoader`, one `ProductionBackupJobRunner`, register `register_backup_task(huey, runner.run)` alongside the three existing tasks inside the same `register_tasks(huey)` closure passed to `create_consumer(effective_configuration, register_tasks=...)`, and extend `close_resources()` to close backup `huey.storage` before engine disposal — single `SqliteHuey` instance per process, constructed only in factories, never at import |
| Generated client | `packages/api-client/src/generated/schema.ts` is the only generator-owned file allowed. After adding the route, run `pnpm --filter @transloka/api-client generate` and `pnpm --filter @transloka/api-client check-generated`; never hand-edit `schema.ts` and do not modify `packages/api-client/src/client.ts` or `apps/web/**` except adding the separate `BackupJobStatus` union in the two panel files |

## Security Boundaries

Arises from `docs/SECURITY.md:31-38 Filesystem`, `43-45 Backup`, `59 Ollama Base URL`, `75 Logging`, `80 Lockfile`, plus proven patterns in `translation.py:60`/`ocr.py:39`/`reconstruction.py:54`:

- Network: API and worker bind remains `127.0.0.1` / `::1` loopback only; no new `0.0.0.0` exposure; CORS stays allowlisted (`http://127.0.0.1:3000`, `http://localhost:3000`), no wildcard.
- Filesystem: all storage keys are POSIX relative (`backups/...`), canonicalized via `Path(*relative.split("/")).resolve(strict=False)` and verified `is_relative_to(root.resolve())`; absolute paths, `..`, `\`, `:`, NUL, symlinks, and reserved Windows names rejected per `verification.py:243 _safe_entry_name` and `archive.py:282 _safe_stage_path`; original PDF sourced through `LocalFileStorage` paths, never from command payload.
- Archive: reuse `verify_backup_archive()` with `BackupVerificationLimits(max_entries=10_000, max_file_uncompressed_bytes=1 GiB, max_total_uncompressed_bytes=4 GiB, max_compression_ratio=200.0)` — zip-slip, symlink entry, encrypted flag, decompression bomb, excessive entries, and invalid manifest all fail closed before any DB mutation.
- Subprocess/command injection: no `shell=True`, no `os.system`, no interpolation of user input into command lines; only allowlisted Python archive calls.
- Logging: cleanup failure warnings may include only `job_id`, `backup_id` if available, and a fixed `error_code` (e.g., `BACKUP_CLEANUP_FAILED`) but must not log `storage_key` or absolute filesystem paths; never log `payload_json`, manifest JSON, or archive bytes; safe fields only per `SECURITY.md:75-76` (`job_id`, `backup_id`, `backup_type`, `status`, `error_code`).
- Idempotency / DoS: `Idempotency-Key` bounded 1..200 printable, payload canonical `sort_keys+separators` for stable comparison, disk-space check `source_size*2 + 16 MiB` before staging, maintenance gate (`MaintenanceGate` pre/post signals in `queue.py:102-116`) prevents restore overlapping backup tasks; cancellation is cooperative via `JobCancellationService.checkpoint(job_id)`.

## Cancellation Semantics

`create_backup()` is **non-interruptible** — it stages to a temporary directory then atomically `os.replace()`s the final archive into `backups/` before returning. The runner therefore **must not claim cancellation occurs during `create_backup()`**.

**Chosen policy: cancellation checkpoint before archive creation only; once creation starts, complete publication safely.**

- Before invoking `create_backup()`, the runner calls `JobCancellationService.checkpoint(job_id)` (which transitions `CANCELLATION_REQUESTED -> CANCELLED` if requested). If true, transition the job to `CANCELLED`, close the attempt as `CANCELLED`, create no `StoredFile`/`Backup`, and return immediately.
- Once `create_backup()` has been entered, the runner does **not** poll for cancellation until after `verify_backup_archive()` and the DB `transaction_scope` have either committed or failed. If a cancellation request arrives mid-archive, the archive is still verified and published atomically as `COMPLETED` — the cancellation request is treated as satisfied by the completed backup (the caller can delete the backup if desired, but no orphan archive is left). No `Untracked final archive as normal behavior` is permitted.
- No deletion of the newly owned archive on cancellation is performed under this policy, so there is no after-create deletion-failure path to handle. This matches the existing OCR/reconstruction `checkpoint before render, then complete` pattern and avoids the race where an archive could be deleted while `verify_backup_archive()` is still reading it.

## Cleanup After Publication Failure

To prevent newly created unreferenced archives from accumulating:

- If `verify_backup_archive()` fails after `create_backup()` has already moved the archive to `backups/`, the runner must delete the file at `directories.root / artifact.storage_key` before marking the job `FAILED`. Deletion is best-effort via `Path.unlink(missing_ok=True)` inside `try/except OSError: pass`; if deletion fails, the runner logs at `warning` level with only `job_id`, `backup_id` (if allocated), and fixed `error_code=BACKUP_CLEANUP_FAILED` — **no `storage_key` or absolute path** — and still marks the job `FAILED` with `BACKUP_FAILED`; the file remains discoverable via the next orphan-scan (`maintenance` separate work) but is not considered the normal untracked-archive case.
- If the DB `transaction_scope` that creates `StoredFile`/`Backup` + `ApplicationJob(COMPLETED)` raises (e.g., constraint violation, foreign-key race), the runner must also delete the just-moved archive in a `except` block before `_fail_job`, using the same best-effort `unlink` and the same restricted warning fields (`job_id`, `backup_id`, `BACKUP_CLEANUP_FAILED`). If the deletion itself raises, the same warning-log path is taken and the job is still marked `FAILED`; no success response is returned while the file remains.

## Error Mapping

The API router — not `JobDispatchService` — owns HTTP mapping. `JobDispatchService` raises domain errors; the router catches and converts, without a second DB mutation on `503`:

| Domain error | HTTP | `error.code` | Details |
|---|---|---|---|
| `JobIdempotencyConflictError` | `409` | `IDEMPOTENCY_CONFLICT` | `{ "message": "The idempotency key belongs to a different backup request." }` |
| `JobQueueUnavailableError` | `503` | `QUEUE_UNAVAILABLE` | `{ "job_id": job_id }` from the exception's `job_id`; `JobDispatchService` has already marked the row `FAILED/QUEUE_DISPATCH_FAILED` via `_mark_dispatch_failed` — router only maps to HTTP, no second `FAILED` mutation |
| `InvalidJobDispatchError` | `422` | `VALIDATION_ERROR` | message from the exception or `"The backup request contains invalid values."` |
| `BackupWorkerError` (unknown `backup_type`, duplicate keys, wrong schema, unsupported type) | `422` | `VALIDATION_ERROR` | same as above; keep the imported database model `BackupStatus` unchanged — name the job response type `BackupJobStatus` or validated `JobStatus` members, never declare `BackupStatus` alias inside `routers/backups.py` |
| Public `include_* == true` rejection (conservative mapping) | `422` | `VALIDATION_ERROR` | `"include_original_files is not supported by the current backup service"` (per field) |

`JobDispatchService` must not import `TransLokaError` or return HTTP responses itself; tests assert the domain exception types directly.

## Exact Tests

All new tests must belong to the existing pytest layout and run under `uv run pytest -q` with the locked environment (no ephemeral `reportlab`/`weasyprint`). Spec and plan tests are identical — keep them in sync.

### A. Unit — command payload (`tests/integration/worker/test_backup_command.py`)

- `test_backup_command_round_trips_valid_payload_for_each_supported_type` (`DATABASE_ONLY`, `METADATA`, `FULL_PROJECTS`);
- `test_backup_command_rejects_duplicate_json_keys`;
- `test_backup_command_rejects_unknown_field`;
- `test_backup_command_rejects_missing_field`;
- `test_backup_command_rejects_wrong_schema`;
- `test_backup_command_rejects_full_application_type`;
- `test_backup_command_rejects_pre_restore_type`;
- `test_backup_command_rejects_non_bool_flag`;
- `test_backup_command_canonical_json_is_deterministic` (`json.dumps(..., sort_keys, separators)`);
- `test_backup_command_public_mapping_rejects_true_include_flags` (each of `include_original_files`, `include_exports`, `include_intermediate_files` true → `422` via API; also `BackupCommand` direct construction with `include_queue_database/include_temporary` true is not exposed publicly but internal direct use is tested).

### B. Unit — DB loader (`tests/integration/worker/test_backup_loader.py`)

- `test_loader_loads_backup_command_after_api_dispatch_commits`;
- `test_loader_rejects_wrong_job_type` (`TRANSLATE_DOCUMENT` job);
- `test_loader_rejects_missing_job`;
- `test_loader_rejects_corrupt_payload_json`;
- `test_loader_rejects_unsupported_backup_type_in_payload`;
- `test_loader_rejects_queue_mismatch` (job has `queue_name != transloka`);

### C. Integration — API dispatch (`tests/integration/api/test_backups.py`)

- `test_create_backup_persists_queued_job_and_enqueues_only_job_id` (assert `ApplicationJob.status==QUEUED`, `payload_json == canonical`, `task.args == (job_id,)` from `huey.dequeue()`, response `data == {job_id, backup_id: None, status: result.status.value}` + `meta.request_id`; do not assert a hard-coded `QUEUED` when the result may be `RUNNING`/`FAILED`/etc.);
- `test_database_BackupStatus_not_shadowed_in_backups_router` (assert imported `BackupStatus` from `python/transloka-core/src/transloka_core/database/models/backups.py` is still the persisted `Backup` ORM lifecycle enum `CREATED|RUNNING|COMPLETED|FAILED|CANCELLED` and `services/api/src/transloka_api/routers/backups.py` contains no `BackupStatus =` alias; `BackupRecord` is a separate TypeScript frontend type, not this Python enum);
- `test_CreateBackupResponse_uses_BackupJobStatus` (assert `BackupJobStatus` is the distinct creation-job union `QUEUED|RUNNING|RETRYING|CANCELLATION_REQUESTED|COMPLETED|COMPLETED_WITH_WARNINGS|PARTIALLY_COMPLETED|FAILED|CANCELLED|STALE` used only for `CreateBackupResponse.data.status`);
- `test_create_backup_rejects_invalid_backup_type_422` (`FULL_APPLICATION`, empty, lowercase);
- `test_create_backup_rejects_true_include_flags_422` (each `include_*` true → `422`);
- `test_create_backup_idempotent_dispatch_returns_exact_persisted_status` (for an idempotent `JobDispatchService.dispatch()` result with `status=RUNNING`/`FAILED`/`STALE`, the API returns that exact `status` rather than hard-coded `QUEUED`; covers `QUEUED`, `RUNNING`, `RETRYING`, `CANCELLATION_REQUESTED`, `COMPLETED`, `COMPLETED_WITH_WARNINGS`, `PARTIALLY_COMPLETED`, `FAILED`, `CANCELLED`, `STALE`);
- `test_concurrent_existing_dispatch_does_not_enqueue_twice` (`result.created == False` → `huey.pending_count` unchanged, same `job_id`);
- `test_create_backup_idempotency_conflict_409_on_different_payload` (same key, different `backup_type` → `409 IDEMPOTENCY_CONFLICT`);
- `test_create_backup_queue_unavailable_maps_to_503_with_job_id_and_no_second_mutation` (inject failing queue, assert `503 QUEUE_UNAVAILABLE` with `details.job_id` == already-failed row's `job_id`, router did no second `FAILED` mutation);
- `test_create_backup_maps_invalid_dispatch_and_worker_errors_to_422` (`InvalidJobDispatchError` / `BackupWorkerError` → `422`);
- `test_create_backup_never_fails_validation_for_valid_persisted_status` (for each `BackupJobStatus` value, replay via `dispatch()` returns that `status` without `422`);
- `test_create_backup_preserves_restore_route_untouched` (snapshot test; `POST /{id}/restore` still synchronous);

### C2. Frontend — backup-panel status domains (`apps/web/src/features/backups/backup-panel.test.tsx`)

- `test_BackupRecord_retains_only_backup_lifecycle_statuses` (in `backup-panel.test.tsx`: assert `BackupStatus` at `backup-panel.tsx:14` for `BackupRecord` remains exactly `QUEUED|RUNNING|COMPLETED|FAILED`; no job statuses mixed in);
- `test_backup_panel_ts_separate_domains` (in `backup-panel.test.tsx`: assert `backup-panel.tsx:14` `BackupStatus` unchanged and `backup-panel.tsx:42` `BackupJobStatus` for `CreateBackupResponse` are two separate unions, not merged; create-result message is `"Backup job <BackupJobStatus>: <job_id>"` via the create action, not a backup-list badge);

### D. Integration — worker lifecycle (`tests/integration/worker/test_backup_runtime.py`)

- `test_backup_runner_creates_validated_stored_file_and_backup_and_completes_job` (assert `StoredFile(BACKUP, VALIDATED, is_immutable=1)`, `Backup(COMPLETED, file_id == stored.id)`, `stored.storage_key.startswith("backups/")`, `ApplicationJob(COMPLETED, progress=1.0)`, `JobAttempt(COMPLETED)`);
- `test_backup_runner_rejects_backup_type_not_supported_without_retry`;
- `test_backup_runner_fails_gracefully_on_insufficient_disk` (`mock get_free_disk_bytes -> 0`, assert `FAILED/INSUFFICIENT_DISK`, no `backups/*.zip` left);
- `test_backup_runner_cancellation_before_archive_leaves_no_backup_row_and_is_cancelled` (`JobCancellationService.request` then `runner.run` → `CANCELLED`);
- `test_backup_runner_cancellation_during_archive_still_publishes_safely` (flag becomes true after `create_backup` entry — runner still returns `COMPLETED`, no untracked file);
- `test_backup_runner_exact_once_on_already_completed_job_does_not_create_second_backup` (second `runner.run(job_id)` returns same `result_json`, `backups` count stays 1);
- `test_backup_runner_verification_failure_deletes_unreferenced_archive` (mock `verify_backup_archive` to raise, assert archive deleted, `FAILED`);
- `test_backup_runner_db_commit_failure_deletes_unreferenced_archive` (mock commit to raise, assert archive deleted, `FAILED`);

### E. Queue / registry (`tests/integration/worker/test_sqlite_huey.py`)

- `test_huey_registers_transloka_backup_execute_exactly_once`;
- `test_backup_producer_only_raises_runtime_error`;
- `test_create_queue_worker_registers_translation_ocr_reconstruction_and_backup_together`;
- `test_backup_producer_and_consumer_close_storage_exactly_once`;

### F. Runtime E2E (`tests/e2e/runtime/test_backup_worker_runtime.py`)

Uses `tmp_path` with `resolve_local_data_directories`, `alembic upgrade head`, real `SqliteHuey`, `create_app()` lifespan, **no fake archive**:

1. seed a migrated `transloka.db` (no project needed; backup is global) with at least one `stored_files(ORIGINAL)` to prove non-empty DB;
2. `POST /api/v1/backups` with `{"backup_type":"METADATA","include_original_files":false,"include_exports":false,"include_intermediate_files":false}`, `Idempotency-Key` → assert `202 {data:{job_id, backup_id:null, status:"QUEUED"}, meta:{request_id}}` and `Backup` not yet present;
3. prove `tasks.db` contains the single task `transloka.backup.execute` with `args == (job_id,)` and no other args/kwargs;
4. construct `create_queue_worker(configuration)` with real `DatabaseBackupRequestLoader`/`ProductionBackupJobRunner` and execute the dequeued task via the worker registry;
5. assert `ApplicationJob(COMPLETED, progress=1.0, result_json schema transloka.backup.job.v1)`, `JobAttempt(COMPLETED)`, `Backup(COMPLETED, backup_type==METADATA)`, `StoredFile(BACKUP, VALIDATED, storage_key=backups/... .zip)` with `backup.file_id == stored.id` and `stored.storage_key.startswith("backups/")`, file on disk, `verify_backup_archive` succeeds, `manifest.json` inside matches `included_content`;
6. assert idempotent replay via `POST /backups` with same key after completion returns `status:COMPLETED` (and `GET /api/v1/jobs/{job_id}` reflects `COMPLETED`), re-execution via runner is idempotent;
7. assert independent shutdown: `app.state.backup_queue_owner.close()` + `worker.close_resources()` + `engine.dispose()` do not interfere cross-factory, and no `.db`/`.zip` artifact is committed to the repository.

This E2E asserts **only** `POST /backups`, `GET /jobs/{job_id}`, DB rows (`Backup.file_id == StoredFile.id` + `StoredFile.storage_key`), and archive artifact. No assertion on `GET /api/v1/backups` list.

No test contacts Ollama, WeasyPrint, or the network; reflow/reconstruction native library is not required.

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

Explicitly **not** allowed:

```
python/transloka-core/src/transloka_core/backup/__init__.py  # transloka-core must not import/re-export worker types
infrastructure/migrations/**
pyproject.toml / uv.lock / pnpm-lock.yaml
THIRD_PARTY_LICENSES.md / docs/adr/**
packages/api-client/src/client.ts
docs/releases/PERSONAL_MVP_RELEASE_CHECKLIST.md
docs/CODEX_TASKS.md
*.db / *.db-wal / *.db-shm / backups/*.zip
```

If implementation discovers a need outside this exact list, stop and revise this design before editing that file.

## Design Alternatives Considered

- **Synchronous backup in the API thread:** rejected; violates `API_CONTRACT.md:2.4` (backup must be a job), blocks the event loop on large `FULL_PROJECTS` archives, and bypasses `Stale/Cancel/Heartbeat` guarantees that translation/OCR/reconstruction already provide.
- **Serializing the full command or filesystem paths through Huey:** rejected; duplicates durable `payload_json`, can go stale, and risks placing document data in `tasks.db` (prohibited by `MASTER_CODEX_PROMPT:J Data Privacy Rules`).
- **Bundling queued restore into the same remediation:** rejected; the proven `RestoreWorkflow` already provides maintenance-mode, temp extraction, path/checksum, and atomic replacement with explicit `RESTORE` confirmation. Queued restore would add engine-disposal races and `MaintenanceGate` reentrance without a documented requirement.
- **Exposing `include_queue_database`/`include_temporary` publicly:** rejected; leaks implementation detail (`tasks.db` exclusion) and has no consumer — `backup-panel.tsx` already uses the four public fields with the conservative all-false mapping.

## Open Issues

- The deferred `FULL_APPLICATION` type (documented as not yet implemented in `backup/archive.py:90`) remains deferred; `POST /api/v1/backups` must reject it with `422` and the E2E covers only `DATABASE_ONLY`→`FULL_PROJECTS`.
- Reflow-native-code presence (`WeasyPrint` + `libgobject`) does not affect the backup worker; verification succeeds with the same `verify_backup_archive` path used by `M11-T04` backups, so no native-runtime gate is added.
