# M11-REM-11 Production Reconstruction Worker Runtime Implementation Plan

## Constraints

- Follow the approved design and keep the queue payload to `job_id` only.
- Use test-driven changes and commit each coherent layer atomically.
- Do not add migrations, UI work, backup tasks, release edits, or remote
  rendering/network behavior.

## 1. Durable Command, Loader, and Renderer Boundary

1. Add failing worker tests for exact command fields, duplicate/unknown fields,
   invalid modes/settings/page selectors, wrong job types, inconsistent linked
   reconstruction rows, page ownership, translations, geometry, and original
   file safety.
2. Implement `ReconstructionCommand`, loaded page/block values, and
   `DatabaseReconstructionRequestLoader`.
3. Add deterministic overlay/reflow/hybrid rendering and safe PDF assembly on
   the existing reconstruction primitives.
4. Run focused reconstruction/worker tests and commit.

## 2. Persistence, Validation, and Job Lifecycle

1. Add failing tests for job attempts/progress, cancellation, page/mapping
   records, final validation, immutable file publication, export versioning,
   exact-once completion, and failure cleanup.
2. Implement `ProductionReconstructionJobRunner` with stable failure codes and
   database/file consistency handling.
3. Declare direct reconstruction/quality dependencies and refresh the lockfile.
4. Run focused tests and commit.

## 3. Stable Huey Task and Runtime Composition

1. Add failing tests for `transloka.reconstruction.execute`, producer-only
   behavior, registration alongside translation/OCR, and exact resource close.
2. Add the thin reconstruction task registry and producer.
3. Compose loader/runner in `create_queue_worker` and the producer in the API
   lifespan.
4. Run worker/app lifecycle tests and commit.

## 4. Atomic Production API Dispatch and Retry

1. Add failing API tests proving the reconstruction row exists before enqueue,
   the durable command is exact, idempotent replay does not requeue, enqueue
   failure is explicit, and page retry actually requeues durable work.
2. Refactor start dispatch to persist application/reconstruction state before
   enqueue while preserving the public response contract.
3. Wire retry dispatch and stable failure handling.
4. Regenerate the API client only if OpenAPI changes, run API tests, and commit.

## 5. Runtime E2E Evidence

1. Add a production app-to-`tasks.db`-to-worker E2E test using a temporary
   migrated data root and deterministic translated PDF fixture.
2. Verify task isolation, job/attempt lifecycle, page/mapping records, immutable
   export, final validation, status response, original preservation, and
   independent factory shutdown.
3. Run focused reconstruction, worker, API, digital/scanned/restore E2E groups
   and commit.

## 6. Final Verification and Integration

Run:

```powershell
uv run pytest -q
uv run ruff check .
uv run ruff format --check .
uv run mypy .
pnpm lint
pnpm build
pnpm typecheck
pnpm test
pnpm audit --audit-level high
pnpm --filter @transloka/api-client generate
git diff --exit-code -- packages/api-client/src/generated
git diff --check
```

Scan the repository for `.db`, `.sqlite`, and `.sqlite3` artifacts, inspect the
scope, ensure both worktrees are clean, fast-forward into `main`, and stop. Do
not start backup remediation or M11-T18.
