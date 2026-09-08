# Translation review protection — 2026-09-05

## Scope

Audit follow-up for the production translation worker and M7-T10 orchestration,
enforcing the review/locking invariants of M8-T04 and MASTER_CODEX_PROMPT section R.
This is not a release approval or completion of the remaining audit findings.

## Behavior

- Locked, approved, and user-edited segments are excluded from automatic worker
  selection even when the retranslation flags are enabled. Flags do not unlock
  a segment or revoke review protection.
- The production loader captures each selected segment's revision. A change
  between loading and worker startup rejects the stale operation.
- Model-result writes check revision and protection state atomically in SQLite.
  A conflicting result is not persisted as a successful segment translation;
  the run records SEGMENT_REVISION_CONFLICT and continues other segments.
- Success, failure, cancellation, and unexpected-exception cleanup preserve
  newer user edits, approvals, locks, and source corrections. Status cleanup
  applies only to still-running segments at the revision owned by that operation.
- Source text, reviewed/final text, and revision history are not rewritten by
  these guards. No API schema, migration, dependency, or model change is needed.

## Verification

The pre-fix regression run reproduced 15 failures. After the fix:

```powershell
uv run --frozen pytest tests/integration/worker/test_translation_runtime.py tests/integration/translation tests/integration/database/test_translation.py tests/e2e/runtime/test_translation_worker_runtime.py tests/e2e/digital tests/e2e/scanned tests/integration/api/test_translation.py -q --tb=short
```

104 passed in 126.49 seconds. One subsequently added atomic-write interleaving
test also passed independently:

```powershell
uv run --frozen pytest tests/integration/worker/test_translation_runtime.py::test_result_update_checks_revision_atomically -q --tb=short
uv run --frozen ruff check .
uv run --frozen ruff format --check .
uv run --frozen mypy .
git diff --check
```

All checks above passed. These are scoped regression checks, not a new full-suite
or real-model acceptance run. The earlier audit's unrelated Ollama test-fixture
failure and missing WeasyPrint dependency remain unresolved.

## Follow-up: orphan translation segment recovery

The M4-T08 startup recovery service now reconciles historical and newly stale
translation segments after its existing job recovery pass. Changes are limited
to `python/transloka-core/src/transloka_core/jobs/recovery.py` and
`tests/recovery/test_stale_job_recovery.py`, plus this audit note.

- Require a terminal `TRANSLATE_DOCUMENT` job for the segment's document and
  no nonterminal translation job for that document. A queued, created, running,
  retrying, or cancellation-requested job blocks reconciliation.
- Only `TRANSLATING` segments with usable source text are eligible. Locked
  segments, human review states, reviewed translations, and final text are skipped.
- Without machine output, restore `READY_FOR_TRANSLATION`. Preserve existing
  review flags. With machine output, preserve it and use `NEEDS_REVIEW` /
  `REVIEW_REQUIRED`; recovery does not claim successful validation.
- All eligibility checks are inside one SQL UPDATE, including the active-job
  and review guards. Interleaving tests cover enqueue and review before the write.
- Source text, machine text, revisions, translation history, and files are not
  rewritten. Repeated recovery is idempotent. Existing job results and retry
  behavior retain their public contract.

The regression first reproduced a segment remaining `TRANSLATING` after a
terminal job. The updated recovery test file passes 53 tests, including blank
machine output, every terminal job status, all active states, unrelated documents,
protected content, missing job evidence, restart, and concurrent changes.

The broader regression completed with 171 passed in 168.91 seconds:

```powershell
uv run --frozen pytest tests/recovery tests/integration/worker/test_translation_runtime.py tests/integration/translation tests/integration/database/test_translation.py tests/e2e/runtime/test_translation_worker_runtime.py tests/e2e/digital tests/e2e/scanned tests/integration/api/test_translation.py -q --tb=short
```

The final recovery-only run (53 passed in 32.44 seconds) includes the extra
empty/whitespace machine-output cases added after broad-suite collection. These
counts overlap; they are not 224 distinct tests. Ruff, format check, mypy, and
`git diff --check` also pass. Node checks and real-model translation were not
rerun for this backend-only follow-up.

This was tested on migrated temporary databases only. No API/worker was started
against the user's data root. The new reconciliation runs on the next controlled
API startup; take a database backup and ensure old workers are stopped before
applying it to a real project. This change is not a worker lease/late-result
fencing fix, nor a progress-counter or translation-quality fix.

## Remaining work

Worker late-result fencing and UI progress consistency were subsequently
addressed in `TRANSLATION_WORKER_FENCING_PROGRESS_2026-09-05.md` with scoped tests.
Reconstruction fidelity/dependencies, glossary enforcement, benchmark validity,
warning attribution, and OCR timeout isolation remain separate audit findings.
The implementation/test pass above did not change the user's database. The
separately authorized live maintenance pass is recorded below. No schema was
migrated, no model was downloaded, and no changes were staged or committed.

## Authorized live maintenance — 2026-09-05

The owner authorized continuing with backup, quiescence checks, and controlled
recovery. No TransLoka API or worker process was running; application ports were
not listening and all 40 persisted jobs were terminal. Unrelated processes and
Ollama were left alone.

- Created a DATABASE_ONLY archive through the existing SQLite-backup service:
  `backups/transloka-backup-database_only-20260905T045251364.zip`.
- Archive SHA-256:
  `e5e454315446c164a1003ee8b4f885a994143f2d45de138078582b49a112be55`.
- Verified its manifest, archive checksums, SQLite integrity, foreign keys,
  application version `0.0.0`, and schema revision `0017_backups`. This is a
  private database snapshot, not a full-project/PDF backup or a new Backup job.
- Rehearsed on the fixed database member extracted from the verified archive
  into a separate maintenance directory; the live database remained unchanged.
- Applied at `2026-09-05T04:54:12.573Z` using an outer SQLite write transaction.
  The live tables had to match the backup baseline before execution. Only the
  independently predicted segment status/review-status/timestamp transitions
  were accepted before commit; any unexpected mutation would roll back.
- Recovered 4,026 segments: 3,936 to READY_FOR_TRANSLATION and 90 with existing
  machine text to NEEDS_REVIEW / REVIEW_REQUIRED. Remaining TRANSLATING: 0.
- Total resulting segment states: APPROVED 10, MACHINE_TRANSLATED 1,776,
  NEEDS_REVIEW 1,386, READY_FOR_TRANSLATION 7,581.
- Every segment's other columns, including source, machine/reviewed/final text
  and revision, were unchanged. All 41 other tables were unchanged, including
  job/attempt history, translations, projects, documents, and file registry.
- A second recovery pass made no changes. Integrity check: ok; foreign-key
  violations: 0. Post-commit checks matched the validated transaction state.
- All 87 nondeleted registered files matched size and SHA-256 before and after:
  7 originals, 3 IR snapshots, 4 exports, 1 prior backup, and 72 OCR outputs.

Local maintenance script and count-only verification reports are retained under
`backups/maintenance-20260905-segment-recovery/` in the application data root,
outside Git. The rehearsal database and backup contain private document data.
No restore was performed, no translation was queued, and no server was started.
This resolves the historical segment-state inconsistency, not the remaining
job-history, progress UI, model-quality, or reconstruction findings.
