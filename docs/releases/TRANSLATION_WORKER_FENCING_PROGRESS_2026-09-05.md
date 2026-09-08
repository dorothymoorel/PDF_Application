# Translation worker fencing and truthful progress — 2026-09-05

## Scope

Authorized audit follow-up after historical segment recovery. This changes the
existing translation worker, persistence adapter, status endpoint, and progress
panel. No dependency, migration, public response field, or engine/model change.
Existing uncommitted review protection and recovery work is preserved.

## Worker ownership

- A worker claims its job atomically, only when no running attempt owns it.
  Duplicate deliveries cannot take over another worker's running attempt.
- The loader captures the retry generation. An operation loaded before a retry
  cannot claim or fail the newer generation.
- The running attempt ID is the write token. Every persistence transaction,
  batch-progress update, and finish/failure transition checks that token and
  the permitted job state while acquiring SQLite's writer lock. The guard is
  inside the transaction, not a pre-read check outside it.
- A terminal or replaced attempt cannot write late machine results, change
  job/project/document state, or rewrite another attempt's history. Cancellation
  checks also stop an obsolete attempt before continuing provider work.
- Existing source-revision and review/lock checks remain in force. Ownership
  fencing does not replace review protection or change the stale-heartbeat limit.

The pre-fix tests reproduced a recovered STALE job being overwritten as FAILED
by late success/error cleanup, and duplicate execution taking an active attempt.
Tests now cover late success, late exception, duplicate delivery, replacement
attempts, old loaded retry generations, and recovery immediately before the
atomic result-write/finalization guard.

## Progress semantics

- `progress` is saved document translation coverage, calculated from the same
  aggregate query as total/completed/failed/review counts. IGNORED and
  NOT_TRANSLATABLE segments remain outside the denominator. A source-only locked
  segment does not count as translated; a completed-state segment must contain
  machine, reviewed, or final translation text.
- Job status remains separate from document coverage. A failed job can leave
  useful saved results; a successful selected-page job does not imply that the
  whole document is translated.
- The orchestrator publishes the actual batch plan before the first provider
  call. The worker persists current/total batch counts in internal job metadata
  and retains them in terminal results. Section and token limits can produce
  more batches than `ceil(segment_count / requested_batch_size)`.
- The endpoint no longer invents progress batches using a fixed size of five.
  Missing/malformed historical batch data is returned as zero/unknown and the
  UI says the count is unavailable, instead of showing an invented batch total.
- Status display selects an active job, otherwise the newest terminal job for
  the active document. A newer successful job is not hidden by an older failure.
  Retry-target selection keeps its separate historical policy.
- UI labels distinguish saved document coverage from job batches processed.
  Readiness's pre-worker estimate is unchanged; it is not the actual job plan.

## Verification

```powershell
uv run --frozen pytest tests/recovery tests/integration/worker/test_translation_runtime.py tests/integration/translation tests/unit/translation tests/integration/database/test_translation.py tests/e2e/runtime/test_translation_worker_runtime.py tests/e2e/digital tests/e2e/scanned tests/integration/api/test_translation.py -q --tb=short
```

344 passed in 238.47 seconds. Two subsequently added atomic-boundary cases
passed independently. After consolidating status counts into one aggregate
query, the final API file was rerun: 34 passed in 51.52 seconds. These test
counts overlap and must not be added together as distinct tests.

Additional checks passed:

- `uv run --frozen ruff check .`
- `uv run --frozen ruff format --check .`
- `uv run --frozen mypy .` (377 source files)
- `pnpm lint`
- `pnpm test` (113 web + 45 API-client tests)
- `pnpm build`
- `pnpm typecheck` (production-generated and restored dev configurations)
- `pnpm --filter @transloka/api-client check-generated`
- `pnpm audit --audit-level high` (no known vulnerabilities)
- `git diff --check` (line-ending warnings only)

The initial dev typecheck hit the pre-existing duplicate `LayoutProps` from
`.next/dev/types` and `.next/types`. After successful production build/typecheck,
the user's original dev import in `apps/web/next-env.d.ts` was restored. The
generated build-only `.next/types` directory was moved recoverably outside the
repository to the local temporary folder named
`transloka-build-route-types-20260905-worker-progress`. Dev typecheck then passed
without changing source configuration or deleting the user's edits.

## Boundaries and remaining work

Tests used temporary databases and fake providers; no book translation, live
database repair, model download, stage, commit, or application-server startup
was performed in this pass. This is not a new full-product or real-model audit.
The earlier unrelated Ollama fixture issue, reconstruction fidelity/dependencies,
glossary enforcement, benchmark validity, warning attribution, and OCR timeout
isolation remain separate findings. Next: controlled small-scope application
trial to validate the repaired flow before restarting a full-book translation.
