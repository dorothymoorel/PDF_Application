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

This checklist is the M11-T18 snapshot from 2026-08-28. Later remediation must
be validated by a new complete M11-T18 run before the release decision changes.

Post-review evidence on 2026-09-04 resolves the automated portion of
REL-HIGH-003: the current `qwen3:1.7b` candidate passed a fresh 6/6 quick
benchmark and two independent 90/90 full runs with no critical failure. The
production run returned `RECOMMENDED_DEFAULT`; its local registry record now
contains `Apache-2.0` and `APPROVED_FOR_PERSONAL_USE`. See
`LOCAL_MODEL_BENCHMARK_2026-09-04.md`. Human blind quality review remains open,
so the release decision stays **NOT_READY** until that review and a clean
M11-T18 rerun are complete.

## Acceptance criteria

| Gate | Result | Evidence |
| --- | --- | --- |
| No Critical defect | PASS | No uncontained Critical product defect was observed in the original review. The later automated model rerun completed without a critical failure. |
| No blocking High defect | **FAIL** | The original review found REL-HIGH-003, REL-HIGH-005, and REL-HIGH-006. The automated model gate now passes, but human blind review and a complete M11-T18 rerun remain required before the current blocking-defect count can be recertified. |
| Digital PDF E2E | PASS | 1 passed in 5.76s in the locked environment. |
| Scanned PDF E2E | PASS | 1 passed in 13.52s in the locked environment. |
| Backup-restore E2E | PASS | 1 passed in 9.99s; backup and restoration integrity checks passed. |
| Security regression suite | PASS | 71/71 security tests passed; an additional 143 security/Ollama tests passed. |
| Original checksum invariant | PASS | 18 immutable-original and PDF-validation tests passed. |
| Final PDF validation | PASS | 7/7 final-PDF validation tests passed. |
| Local model benchmark on target hardware | **PASS (AUTOMATED)** | Post-review evidence: production full benchmark 90/90, zero critical failures, quality score 1.0, recommendation `RECOMMENDED_DEFAULT`; fresh quick benchmark 6/6. Human blind quality review is still pending. |
| Reconstruction manual review | **NOT RUN** | The automated model gate now passes, but representative human review has not yet been recorded. |

## Previous release blockers

| Defect | Current status | Evidence |
| --- | --- | --- |
| REL-HIGH-001 — reconstruction dependency missing | **CLOSED** | `reportlab==5.0.1` is declared in `transloka-reconstruction`, locked, and present after `uv sync --locked`; digital, scanned, and final-PDF gates pass without ephemeral dependencies. |
| REL-HIGH-002 — production runtime not wired | **CLOSED** | Canonical routers are registered and production translation, OCR, reconstruction, and backup tasks pass 27 runtime-composition/E2E tests. |
| REL-HIGH-003 — real Ollama translation and benchmark unavailable | **AUTOMATED GATE CLOSED / HUMAN REVIEW OPEN** | `LOCAL_MODEL_BENCHMARK_2026-09-04.md` records quick 6/6 and production full 90/90 with zero critical failures. Registry license status is `APPROVED_FOR_PERSONAL_USE`; human blind review remains required. |
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

The current production full benchmark evidence is
`docs/releases/LOCAL_MODEL_BENCHMARK_2026-09-04.md`. It supersedes the rejected
2026-08-27 automated result for the current runtime while preserving the older
report as historical evidence.

| Metric | Result |
| --- | --- |
| Attempts | 90 / 90 completed |
| Successful | 90 |
| Failed | 0 |
| Critical failures | 0 |
| Success rate / quality score | 100% / 1.0 |
| Average latency | 3.95 seconds |
| Recommendation | `RECOMMENDED_DEFAULT` |

### Fresh quick benchmark

A fresh real benchmark against Ollama 0.33.2 confirmed the full-run result:

| Metric | Result |
| --- | --- |
| Status / recommendation | `COMPLETED` / `RECOMMENDED_DEFAULT` |
| Cases | 6 total; 6 successful; 0 failed |
| Failed case | None |
| Failure | None |
| Average latency | 7.58 seconds |
| Temperature | 0.1 |

The placeholder case now passes without weakening the critical integrity
validator.

### License evidence

- `ollama show qwen3:1.7b --license` is recorded in the full benchmark as Apache
  License 2.0 with Alibaba Cloud copyright.
- The candidate passed the automated gate and remains the user's persisted
  translation selection; it is not hard-coded as a universal default.
- `THIRD_PARTY_LICENSES.md` keeps model weights separate from application
  dependencies and requires exact license review when a model is selected.
- The local application model registry records `license_name=Apache-2.0` and
  `license_status=APPROVED_FOR_PERSONAL_USE`.

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

The production Ollama provider and benchmark runners execute correctly.
`qwen3:1.7b` now passes both quick and full benchmarks with zero critical
failures, and its local registry license record is reconciled. No human blind
quality review has been completed, so final model acceptance remains open.

Required remediation:

1. Complete human blind translation-quality review.
2. Rerun M11-T18 from a clean locked environment.

### REL-HIGH-005 — Clean first-run startup does not initialize the schema

**Status:** Remediated after this checklist snapshot; pending M11-T18 recertification

Commit `885332d` adds safe startup migration behavior, setup/troubleshooting
guidance, and Windows-script coverage. The complete M11-T18 rerun must verify it
again from a fresh external data root.

### REL-HIGH-006 — Rendered workflow cannot progress beyond staged upload

**Status:** Remediated after this checklist snapshot; pending M11-T18 recertification

Commit `aecde17` and the subsequent import/runtime fixes connect the persisted
workspace journey and add the canonical Playwright workflow. The complete
M11-T18 rerun must recertify this path against the current runtime.

### REL-MEDIUM-002 — Canonical frontend E2E command is absent

**Status:** Remediated after this checklist snapshot

The root package now defines `pnpm e2e` as `playwright test`. Its current result
belongs in the complete M11-T18 rerun.

### REL-MEDIUM-003 — Optional reflow native runtime is unavailable

**Severity:** Medium, known limitation

The locked environment does not install WeasyPrint; five reflow-generator
integration cases skip. Overlay-based digital/scanned E2E and final-PDF
validation pass. Reflow/hybrid behavior requiring WeasyPrint remains unavailable
until a separately approved Python/native-runtime installation and validation
task is completed.

### REL-MEDIUM-004 — System health UI is stale and hangs in development

**Status:** Remediated after this checklist snapshot; pending M11-T18 recertification

Commits `ad0873e` and `4bb975e` fix Strict Mode request recovery and report real
database, filesystem, worker, Ollama, and OCR readiness. The complete M11-T18
rerun must recertify the rendered page.

## Known product limitations

- Single-user and localhost-only; the Windows account is the trust boundary.
- No authentication, multi-user collaboration, cloud storage, remote inference,
  billing, public deployment, or desktop installer.
- Personal MVP scope is PDF and English-to-Indonesian only.
- OCR and reconstruction require human review for poor scans, complex tables,
  formulas, unusual fonts, and dense layouts.
- Reflow scenarios needing WeasyPrint are unavailable in the current locked
  environment; validated overlay paths remain available.
- `qwen3:1.7b` passes the automated model gate and is the user's persisted
  translation selection, but human blind quality review remains required.
- The current hardware detector does not populate GPU telemetry. During the
  accepted rerun, `ollama ps` reported 100% GPU placement; formal peak RAM/VRAM
  sampling was not captured.

## Required next action

Do not declare the Personal MVP complete and do not create the rollback tag.
Complete and record a human blind translation-quality review, then rerun the
entire M11-T18 checklist from a clean locked environment. The rerun must include
fresh-data-root startup, browser UAT, real system health, `pnpm e2e`, automated
quality gates, repository cleanliness, and rollback readiness. Optional
WeasyPrint support remains a separately scoped non-blocking decision.
