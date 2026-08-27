# M11-REM-10 Production OCR Worker Runtime Implementation Plan

## Constraints

- Follow the approved design and keep the queue payload to `job_id` only.
- Use test-driven changes and commit each coherent layer atomically.
- Do not add migrations, UI work, reconstruction/backup tasks, release edits,
  or a live OCR/model dependency.

## 1. Durable OCR Command and Loader

1. Add failing worker tests for exact command fields, duplicate/unknown fields,
   invalid modes/selectors/settings, wrong job types, inconsistent document/page
   ownership, unavailable originals, AUTO selection, and FORCE selection.
2. Implement `OCRCommand`, `LoadedOCRJob`, and
   `DatabaseOCRRequestLoader` in `transloka_worker.ocr`.
3. Build `OCRPageRequest` from database identifiers and a
   `LocalFileStorage.open_read` stream factory.
4. Run focused OCR/worker tests and commit.

## 2. Stable Huey Task and Production Worker

1. Add failing tests for `transloka.ocr.execute`, producer-only behavior,
   consumer registration of translation plus OCR, and resource closure.
2. Add the thin OCR task registry and OCR producer.
3. Compose the production OCR provider/orchestrator/runner in
   `create_queue_worker`, retaining provider injection for deterministic tests.
4. Declare the worker's direct `transloka-documents` dependency and refresh the
   lockfile.
5. Run focused worker tests and commit.

## 3. Production OCR API

1. Add failing API tests for canonical start/status, AUTO/FORCE validation,
   ownership validation, idempotency conflict, missing queue, and enqueue
   failure.
2. Implement the start/status endpoints and OCR response models.
3. Compose and close the OCR producer in the production app lifespan.
4. Regenerate the API client and verify no unexplained drift.
5. Run API tests and commit.

## 4. Runtime E2E Evidence

1. Add a production app-to-`tasks.db`-to-worker E2E test using a deterministic
   injected OCR provider and temporary data root.
2. Verify queued payload isolation, job/attempt lifecycle, raw OCR artifact,
   status endpoints, and independent factories.
3. Run focused OCR, worker, API, scanned/digital/restore E2E groups and commit.

## 5. Final Verification and Integration

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
not start reconstruction/backup remediation or M11-T18.
