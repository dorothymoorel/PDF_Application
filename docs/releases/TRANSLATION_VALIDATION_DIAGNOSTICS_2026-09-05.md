# Translation validation diagnostics and decade preservation

Date: 2026-09-05
Scope: follow-up defect repair authorized after the isolated page-213 trial.
No new milestone, model download, dependency, migration, UI contract, or cloud provider.

## Governing requirements

- `CODEX_TASKS.md`: M7-T08 deterministic integrity validators and M7-T10 orchestration
  acceptance (invalid output blocked; failed segments identifiable).
- `TRANSLATION_PIPELINE.md` sections 35–36: preserve years and numeric values while
  accepting equivalent locale separators.
- `DATABASE_SCHEMA.md` section 29.3: existing append-only translation attempts,
  error fields and optional provider metadata.
- `SECURITY.md` sections 75–76: no source, translated text, raw response or prompt
  in ordinary logs; safe identifiers and error codes only.

## Root causes and repair

1. Number matching used word boundaries that skipped `1950s`, `2000s` and `1950an`.
   A bounded decade matcher now recognizes four-digit decades with `s`, `'s`,
   curly-apostrophe `s`, `an` or `-an`. It adds their numeric value once to the
   existing inventory, avoiding overlaps with dates, versions and ordinary numbers.
   Missing, altered or duplicated values remain critical `NUMBER_MISMATCH` errors.
2. The orchestrator recorded provider attempts as completed before considering
   critical validation. Rejected batches now record `FAILED`, `VALIDATION_FAILED`
   and a fixed safe error message; accepted and warning-only statuses remain unchanged.
3. Attempt metadata now retains `validation_issues` with enum code, severity and
   segment ID (or null for batch-level mapping issues), never issue text or raw output.
   Worker result failures include the batch's distinct critical `validation_codes`.
   Existing non-validation failures retain their previous JSON shape.

Batch rejection remains atomic: a critical error rejects the whole batch, not just
the segment that caused it. The attempt's structured issues identify the actual
offending segment; repeated codes on sibling failed segments do not imply that each
sibling independently violated that rule. No rejected text is saved as accepted output.

## Changed implementation and tests in this follow-up

- `python/transloka-translation/src/transloka_translation/validation/validators.py`
- `python/transloka-translation/src/transloka_translation/orchestration/models.py`
- `python/transloka-translation/src/transloka_translation/orchestration/persistence.py`
- `python/transloka-translation/src/transloka_translation/orchestration/service.py`
- `services/worker/src/transloka_worker/translation.py`
- `tests/unit/translation/validation/test_validators.py`
- `tests/integration/translation/test_orchestration.py`
- `tests/integration/worker/test_translation_runtime.py`

Pre-existing recovery, worker-fencing, progress and user edits were preserved.

## Verification

- Regression reproduction before fix: 4 failed, 56 passed.
- Focused validators and orchestration after fix: 60 passed.
- New database worker diagnostic/privacy regression: 1 passed.
- Broader regression: **357 passed in 198.05 seconds**, using:

  ```powershell
  uv run --frozen pytest tests/unit/translation tests/integration/translation tests/integration/database/test_translation.py tests/integration/worker/test_translation_runtime.py tests/integration/api/test_translation.py tests/recovery tests/e2e/runtime/test_translation_worker_runtime.py tests/e2e/digital tests/e2e/scanned -q --tb=short
  ```

- `uv run --frozen ruff check .`: passed.
- `uv run --frozen ruff format --check .`: passed (363 files).
- `uv run --frozen mypy .`: passed (377 source files).
- `git diff --check`: passed, existing LF/CRLF warnings only.
- No Node/build rerun: no frontend or dependency changes in this follow-up.

## Real local model follow-up

Fresh isolated SQLite backup and 87 checksum-verified managed file copies; new empty
queue; the original source data root was never used by the trial services.

- Same Second Trial page 213, PAGE scope, batch size 2, installed `qwen3:1.7b`.
- Job `job_64bc191a-0f95-4565-a2c5-213a1b008fcf`: **COMPLETED**, 5/5 segments saved,
  3/3 batches processed, worker 52.109 seconds, terminal state observed at 56.3 seconds.
- Original logical database hash and all 7 original PDF hashes remained identical.
- Copy: only the 5 selected segments changed; zero changed segments outside the page.
  Source fields, reviewed/final text, locks and revisions unchanged across all 10,753 segments.
- SQLite integrity and foreign-key checks passed; zero segments left TRANSLATING.
- Trial API/worker stopped, original Ollama left running, no stage/commit.
- Evidence retained locally outside Git under
  `C:\Users\daffa\AppData\Local\TransLokaTrials\20260905-page213\postfix-copy`.

AI-assisted quality review still rejects unattended full-book readiness. The historical
Great Depression reference again became a generic Global Crisis, and the household-debt
term was narrowed to housing credit. Numeric presence does not guarantee exact chronology
or semantic fidelity. The higher completion count in this single stochastic model run
is not proof that the code changes improved generation quality. No critical error occurred
in this repeat, so the new failed-attempt diagnostics are verified by regression tests,
not by claiming an observed real-model rejection in this run.

## Boundaries

This is deterministic integrity checking, not semantic equivalence certification.
It does not validate arbitrary historical-term translations, detect every meaning
change, translate written-out numbers, or resolve abbreviated decades. A numeric
check passing does not prove that a year and a decade are semantically equivalent.
No hard-coded book-specific glossary, automatic approval, weakened critical rule,
or retry escalation was added. Previously saved book translations are not modified.
