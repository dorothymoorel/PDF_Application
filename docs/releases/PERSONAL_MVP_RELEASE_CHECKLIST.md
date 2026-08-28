# TransLoka Personal MVP Release Checklist

## Release decision

| Field | Value |
| --- | --- |
| Review task | M11-T18 — Run MVP Release Checklist |
| Review time | 2026-08-28T23:45:20+07:00 |
| Branch | `main` |
| Reviewed commit | `e26a26fbc340708743ad1a95adab349f1fc80e06` |
| Working tree at start | Clean |
| Decision | **NOT_READY** |
| Release approved | **No** |
| Rollback tag | `m11-personal-mvp-complete` — **NOT CREATED** |

The locked application, PDF, recovery, runtime-composition, security, and
dependency gates now pass. Three previous High blockers are closed: ReportLab is
declared and locked, canonical routers and four production worker flows are wired,
and the Node audits report no known vulnerabilities.

The release remains blocked for three independent reasons. The only installed
candidate model, `qwen3:1.7b`, is rejected by both the full and fresh quick
benchmarks for a critical placeholder-integrity failure. A clean first-run data
root is not migrated by the documented startup workflow and returns HTTP 500 on
the Projects screen. After a manual migration, the rendered UI can create a
project and stage a PDF, but it provides no normal project-open action and does
not continue the staged upload into validation, analysis, OCR, translation,
review, reconstruction, or export.

## Acceptance criteria

| Gate | Result | Evidence |
| --- | --- | --- |
| No Critical defect | PASS | No uncontained Critical product defect was observed. The model placeholder mismatch is detected, normalized, and rejected rather than persisted as a valid translation. |
| No blocking High defect | **FAIL** | REL-HIGH-003, REL-HIGH-005, and REL-HIGH-006 remain open: there is no accepted local model, clean first-run startup fails, and the rendered user workflow cannot progress beyond a staged PDF. |
| Digital PDF E2E | PASS | 1 passed in 5.76s in the locked environment. |
| Scanned PDF E2E | PASS | 1 passed in 13.52s in the locked environment. |
| Backup-restore E2E | PASS | 1 passed in 9.99s; backup and restoration integrity checks passed. |
| Security regression suite | PASS | 71/71 security tests passed; an additional 143 security/Ollama tests passed. |
| Original checksum invariant | PASS | 18 immutable-original and PDF-validation tests passed. |
| Final PDF validation | PASS | 7/7 final-PDF validation tests passed. |
| Local model benchmark on target hardware | **FAIL** | Full benchmark: 89/90 successful with one critical `PLACEHOLDER_MISMATCH`; fresh quick benchmark: 5/6 successful with the same critical failure. Candidate recommendation is `REJECTED`. |
| Reconstruction manual review | **NOT RUN** | No release-approved model exists from which to create the final representative translation artifact. |

## Previous release blockers

| Defect | Current status | Evidence |
| --- | --- | --- |
| REL-HIGH-001 — reconstruction dependency missing | **CLOSED** | `reportlab==5.0.1` is declared in `transloka-reconstruction`, locked, and present after `uv sync --locked`; digital, scanned, and final-PDF gates pass without ephemeral dependencies. |
| REL-HIGH-002 — production runtime not wired | **CLOSED** | Canonical routers are registered and production translation, OCR, reconstruction, and backup tasks pass 27 runtime-composition/E2E tests. |
| REL-HIGH-003 — real Ollama translation and benchmark unavailable | **PARTIALLY CLOSED / STILL BLOCKING** | Real localhost translation and quick/full runners execute. The installed model remains rejected for a critical placeholder mismatch, and human review is absent. |
| REL-HIGH-004 — High Node advisories | **CLOSED** | High, Critical, and production-only High audits all report no known vulnerabilities. |

## Commands and test results

### Environment and dependency reproducibility

| Command | Result |
| --- | --- |
| `git status --short --branch` | PASS — clean `main` at review start. |
| `uv --version` | PASS — `uv 0.11.26`. |
| `uv run python --version` | PASS — Python `3.12.10`. |
| `node --version` | PASS — Node `v24.18.0`. |
| `pnpm --version` | PASS — pnpm `11.9.0`. |
| `uv sync --locked` | PASS — 57 packages resolved; 56 installed packages checked. |
| `uv pip check` | PASS — all 56 installed packages are compatible. |
| `pnpm install --frozen-lockfile` | PASS — all five workspaces already current. |

### Static analysis, formatting, and frontend gates

| Command | Result |
| --- | --- |
| `uv run ruff check .` | PASS — all checks passed. |
| `uv run ruff format --check .` | PASS — 356 files already formatted. |
| `uv run mypy .` | PASS — no issues in 370 source files. |
| `pnpm lint` | PASS. |
| `pnpm typecheck` | PASS. |
| `pnpm test` | PASS — API client 37 and web 93 tests, 130 total. |
| `pnpm build` | PASS — Next.js production build completed. |
| `pnpm --filter @transloka/api-client check-generated` | PASS — generated schema is current. |
| `pnpm e2e` | **FAIL (non-blocking tooling gap)** — no root/workspace `e2e` command exists. The canonical Python E2E suites were run directly and passed. |

### Python, E2E, integrity, and recovery gates

| Command | Result |
| --- | --- |
| `uv run pytest -m "not slow and not requires_ollama and not requires_gpu" -q` | PASS — 1,349 passed and 7 skipped in 1,122.74s. |
| `uv run pytest tests/e2e/digital -q` | PASS — 1 passed. |
| `uv run pytest tests/e2e/scanned -q` | PASS — 1 passed. |
| `uv run pytest tests/e2e/backup_restore -q` | PASS — 1 passed. |
| `uv run pytest tests/integration/reconstruction/test_final_pdf_validation.py -q` | PASS — 7 passed. |
| `uv run pytest tests/security -q` | PASS — 71 passed. |
| `uv run pytest tests/unit/security tests/integration/ollama -q` | PASS — 143 passed. |
| `uv run pytest tests/integration/backup tests/security/backup tests/recovery -q` | PASS — 52 passed. |
| `uv run pytest tests/integration/files/test_immutable_original_storage.py tests/security/files/test_pdf_validation.py -q` | PASS — 18 passed. |
| `uv run pytest tests/golden -q` | PASS — 12 passed. |
| `uv run pytest tests/unit/benchmark -q` | PASS — 9 passed. |
| Production app/worker runtime suite | PASS — 27 passed for canonical router registration, SqliteHuey, and translation/OCR/reconstruction/backup worker flows. |
| `uv run pytest tests/integration/reconstruction/test_reflow_generator.py -q -rs` | 2 passed, 5 skipped because the optional WeasyPrint runtime is not installed. |
| `uv run alembic heads` | PASS — single head `0017_backups`. |
| `uv run alembic history` | PASS — continuous chain from `0001_baseline` through `0017_backups`. |

### Security, secrets, repository artifacts, and dependencies

| Command/check | Result |
| --- | --- |
| `gitleaks git --redact --no-banner` | PASS — 188 commits and approximately 5.15 MB scanned; no leaks found. |
| Prohibited dependency scan | PASS — no PyMuPDF, `pymupdf`, `pymupdf4llm`, or `fitz` in manifests, lockfiles, or implementation packages. |
| Tracked runtime artifact scan | PASS — no tracked database, model weight, or PDF artifact found. |
| `pnpm audit --audit-level critical` | PASS — no known vulnerabilities. |
| `pnpm audit --audit-level high` | PASS — no known vulnerabilities. |
| `pnpm audit --prod --audit-level high` | PASS — no known vulnerabilities. |

## Runtime integration checks

| Check | Result |
| --- | --- |
| Canonical router registration | PASS — production `create_app()` exposes all expected router groups. |
| Translation worker runtime | PASS — production API dispatch, persisted command, SqliteHuey task, worker lifecycle, and output persistence are exercised by runtime E2E. |
| OCR worker runtime | PASS — production queue/worker lifecycle E2E passed. |
| Reconstruction worker runtime | PASS — production queue/worker lifecycle E2E passed. |
| Backup worker runtime | PASS — production queue/worker lifecycle, archive publication, and persistence E2E passed. |
| Queue isolation | PASS — `tasks.db` remains separate from `transloka.db`; factories own and close their resources. |

## Manual local UI trial

The release audit was extended with a rendered-browser trial on the target
machine. The stack used `C:\Users\daffa\TransLokaTrialData`, outside the Git
repository, with web and API bound to loopback and Ollama `0.33.1` running on
loopback. The trial used a generated non-sensitive one-page PDF.

| Step | Result |
| --- | --- |
| `scripts\start.ps1 -CheckOnly` | PASS — development prerequisites were ready. |
| Start web, API, and worker | PASS — web `127.0.0.1:3000`, API `127.0.0.1:8000`, and all four Huey task families started. |
| Open Projects with a clean data root | **FAIL** — the database file existed with no tables; project listing returned normalized HTTP 500. `uv run alembic current` produced no current revision. |
| Manually run `uv run alembic upgrade head` | PASS as a diagnostic/manual remediation — schema reached `0017_backups`; `transloka db integrity-check` passed integrity, foreign-key, and schema checks. This command is absent from the documented normal first-run path. |
| Create project | PASS — `Trial TransLoka` was persisted and rendered at 0% progress. |
| Open project from its card | **FAIL** — the card exposes Archive only and has no project link or open action. Direct navigation to the existing project route was required. |
| Upload generated PDF | PARTIAL — upload reached 100% and returned `STAGED`. |
| Continue analysis and workflow | **FAIL** — status remained `STAGED`; no page count, thumbnails, analysis job, OCR, translation, review, reconstruction, or export action became available. The production upload route stages a temporary file only, and `ImportService.store_original()` has no production caller outside tests. |
| System health page | **FAIL** — development rendering remained indefinitely at `Checking`; Worker, Database, Filesystem, Ollama, and OCR were hard-coded as `Not implemented`. The backend system-health contract is still described as a placeholder and returned all components `UNAVAILABLE` despite the running stack. |
| Repository cleanliness | PASS after cleanup — the Next.js-generated `next-env.d.ts` change was reverted; runtime database, queue database, and PDF remain outside the repository. |

## Hardware and benchmark record

### Current target hardware

| Component | Observed value |
| --- | --- |
| Operating system | Microsoft Windows 11 Home Single Language, 64-bit, build 26200 |
| CPU | AMD Ryzen 5 3550H, 4 physical / 8 logical cores |
| RAM | 15.44 GiB total; approximately 3.07 GiB free at evidence capture |
| Discrete GPU | NVIDIA GeForce GTX 1050, 3 GiB, driver 32.0.15.8180 |
| Integrated GPU | AMD Radeon Vega 8, 0.5 GiB reported, driver 31.0.21923.1000 |
| Repository drive | `F:`; approximately 71.87 GiB free |
| Ollama | `0.33.1`, healthy at `http://127.0.0.1:11434` |
| Installed candidate | `qwen3:1.7b`, digest `8f68893c685c`, approximately 1.4 GB |

### Full benchmark evidence

The canonical production full benchmark evidence remains
`docs/releases/LOCAL_MODEL_BENCHMARK_2026-08-27.md`. No model, prompt, dataset,
or hardware change justified repeating the approximately 62-minute, 90-attempt
run.

| Metric | Result |
| --- | --- |
| Attempts | 90 / 90 completed |
| Successful | 89 |
| Failed | 1 |
| Critical failures | 1 — `PLACEHOLDER_MISMATCH` |
| Success rate / quality score | 98.89% / 0.9889 |
| Average latency | 41.06 seconds |
| Recommendation | **REJECTED** |

### Fresh quick benchmark

A fresh real benchmark against Ollama 0.33.1 confirmed the full-run result:

| Metric | Result |
| --- | --- |
| Status / recommendation | `FAILED` / `REJECTED` |
| Cases | 6 total; 5 successful; 1 failed |
| Failed case | `quick_003_placeholders` |
| Failure | Critical `PLACEHOLDER_MISMATCH` |
| Average latency | 37.12 seconds |
| Temperature | 0.1 |

The provider is operational and five cases complete, but the candidate model
cannot be accepted because placeholder preservation is a critical invariant.

### License evidence

- `ollama show qwen3:1.7b --license` is recorded in the full benchmark as Apache
  License 2.0 with Alibaba Cloud copyright.
- The candidate is rejected and is not selected or pinned as the application
  default.
- `THIRD_PARTY_LICENSES.md` keeps model weights separate from application
  dependencies and requires exact license review when a model is selected.
- The application model registry still reports the candidate license status as
  unknown; selection must not occur until this is reconciled.

## Backup and rollback verification

- Backup-restore E2E passed.
- Backup, verification, security, and recovery suites passed 52 tests.
- Production backup dispatch/worker/archive persistence is included in the
  27-test runtime suite.
- The migration chain has one head, `0017_backups`.
- The rollback tag `m11-personal-mvp-complete` does not exist and was not
  created because the release gate failed.

## Open defects

### REL-HIGH-003 — No accepted local translation model

**Severity:** High, release blocking

The production Ollama provider and benchmark runners now execute correctly, but
`qwen3:1.7b` fails both full and quick benchmarks on placeholder integrity. The
failure is critical at the model-output level and correctly fails closed in the
application. No alternative licensed candidate has an accepted full benchmark,
and no human blind quality review has been completed.

Required remediation:

1. Evaluate a better-suited locally installed, license-reviewed model or make a
   separately scoped prompt/model-compatibility correction without weakening
   placeholder validation.
2. Require an accepted full benchmark with zero critical failures.
3. Complete human blind translation-quality review.
4. Record the selected model ID, license, attribution, and application registry
   license status.
5. Rerun M11-T18 from a clean locked environment.

### REL-HIGH-005 — Clean first-run startup does not initialize the schema

**Severity:** High, release blocking

Following `docs/SETUP.md` with a new external data root starts the API and
creates an empty SQLite file, but neither the setup nor start script upgrades it
to the current Alembic head. The first Projects request then fails with HTTP 500.
Manual `alembic upgrade head` repairs the trial database, but this undocumented
intervention is not an acceptable Personal MVP first-run experience.

Required remediation:

1. Define a safe, idempotent first-run migration policy with backup and
   downgrade protections for existing databases.
2. Integrate the policy into the supported setup/start workflow or fail startup
   with an explicit actionable schema error before serving the UI.
3. Add a clean-data-root runtime test that starts the supported stack and loads
   the Projects page without manual database commands.

### REL-HIGH-006 — Rendered workflow cannot progress beyond staged upload

**Severity:** High, release blocking

The Projects UI can create a database row but its project card has no link or
open action. Direct navigation reveals only the upload component. The production
upload endpoint writes a temporary staged file and returns `STAGED`; no
production path calls `ImportService.store_original()` or dispatches document
validation/analysis. Consequently the user cannot reach the implemented OCR,
translation, review, reconstruction, export, benchmark, backup, or maintenance
features through a complete application journey.

Required remediation:

1. Add an accessible project-open action and a canonical project workspace
   navigation flow.
2. Complete the immutable import transition from staged upload through PDF
   validation, original-file persistence, document/page creation, and analysis
   dispatch with idempotency and cleanup on failure.
3. Connect the existing feature panels to the persisted project/document/job
   state instead of exposing them only through isolated component tests.
4. Add a browser E2E covering create project, import, analysis, OCR/translation,
   review, reconstruction, export, checksum, backup, and restore.

### REL-MEDIUM-002 — Canonical frontend E2E command is absent

**Severity:** Medium, non-blocking for this review

`pnpm e2e` is still not defined. The Python digital, scanned, backup/restore,
and production runtime E2E suites were run directly and passed, but the documented
single frontend E2E entrypoint remains unavailable.

### REL-MEDIUM-003 — Optional reflow native runtime is unavailable

**Severity:** Medium, known limitation

The locked environment does not install WeasyPrint; five reflow-generator
integration cases skip. Overlay-based digital/scanned E2E and final-PDF
validation pass. Reflow/hybrid behavior requiring WeasyPrint remains unavailable
until a separately approved Python/native-runtime installation and validation
task is completed.

### REL-MEDIUM-004 — System health UI is stale and hangs in development

**Severity:** Medium

The page checks only the simple API liveness endpoint and hard-codes the other
components as `Not implemented`. In the supported development start mode,
React's effect cleanup aborts the first request while the second effect observes
the still-active controller and returns, leaving the page at `Checking`. The
production system-health endpoint also reports placeholder component state
rather than the actual running database, filesystem, worker, Ollama, and OCR
readiness.

## Known product limitations

- Single-user and localhost-only; the Windows account is the trust boundary.
- No authentication, multi-user collaboration, cloud storage, remote inference,
  billing, public deployment, or desktop installer.
- Personal MVP scope is PDF and English-to-Indonesian only.
- OCR and reconstruction require human review for poor scans, complex tables,
  formulas, unusual fonts, and dense layouts.
- Reflow scenarios needing WeasyPrint are unavailable in the current locked
  environment; validated overlay paths remain available.
- No local model is release-approved. The installed candidate must not be
  silently selected.
- RAM headroom was very low during the full benchmark, and NVIDIA VRAM was not
  used according to the available telemetry.

## Required next action

Do not declare the Personal MVP complete and do not create the rollback tag.
Resolve REL-HIGH-005 and REL-HIGH-006 first through separately scoped first-run
and end-to-end UI/runtime remediation tasks. Then resolve REL-HIGH-003 through a
model-selection or prompt/model-compatibility task that preserves strict
placeholder validation. After a complete browser UAT, an accepted full
benchmark, and human blind review, rerun M11-T18. Address the stale health UI,
missing `pnpm e2e` command, and optional WeasyPrint runtime in explicit scopes;
they must not be bundled into this checklist-only task.
