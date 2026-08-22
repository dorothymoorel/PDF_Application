# TransLoka Personal MVP Release Checklist

## Release decision

| Field | Value |
| --- | --- |
| Review task | M11-T18 — Run MVP Release Checklist |
| Review time | 2026-08-23T02:13:52+07:00 |
| Branch | `main` |
| Reviewed commit | `24f309c1a2fc4e14127460b52aaf4f883f3a04d3` |
| Working tree at start | Clean |
| Decision | **NOT_READY** |
| Release approved | **No** |
| Rollback tag | `m11-personal-mvp-complete` — **NOT CREATED** |

The release is blocked. The locked Python environment cannot run the digital,
scanned, or final-PDF gates; critical runtime routes and worker tasks are not
wired into the application; the real Ollama benchmark cannot translate; and
the current Node dependency audit reports High vulnerabilities. M11-T18 does
not authorize changes outside this checklist, so none of these defects was
fixed during the review.

## Acceptance criteria

| Gate | Result | Evidence |
| --- | --- | --- |
| No Critical defect | PASS (none observed) | Security tests, checksum tests, backup/restore, Gitleaks, and critical-severity dependency audit found no Critical issue. |
| No blocking High defect | **FAIL** | Four unresolved High blockers are recorded below. |
| Digital PDF E2E | **FAIL** | Locked environment fails collection because `reportlab` is not installed. Diagnostic run with ephemeral `reportlab==5.0.1` passes 1/1. |
| Scanned PDF E2E | **FAIL** | Locked environment raises `OverlayDependencyError` because `reportlab` is not installed. Diagnostic run with ephemeral `reportlab==5.0.1` passes 1/1. |
| Backup-restore E2E | PASS | 1 passed; restored state and checksums match. |
| Security regression suite | PASS | 71 passed, no skips in `tests/security`; an additional 108 localhost/provider security tests passed. |
| Original checksum invariant | PASS | 18 immutable-original/PDF-validation tests passed; digital and restore diagnostics also preserved original bytes/checksums. |
| Final PDF validation | **FAIL** | Locked environment fails collection because `reportlab` is not installed. Diagnostic run with ephemeral `reportlab==5.0.1` passes 7/7. |
| Local model benchmark on target hardware | **FAIL** | Ollama is healthy and the model is installed, but the real quick benchmark fails 0/6 because `OllamaTranslationProvider` has no `translate` method. |
| Reconstruction manual review | **NOT RUN** | No releasable final-PDF artifact can be produced from the locked environment. |

## Commands and test results

### Environment and dependency reproducibility

| Command | Result |
| --- | --- |
| `uv --version` | PASS — `uv 0.11.26` |
| `uv run python --version` | PASS — Python `3.12.10` |
| `node --version` | PASS — Node `v24.18.0` |
| `pnpm --version` | PASS — pnpm `11.9.0` |
| `uv sync --locked` | PASS as a lock operation, but removed 11 undeclared packages including `reportlab==5.0.1` and `weasyprint==69.0`. |
| `pnpm install --frozen-lockfile` | PASS — lockfile unchanged and dependencies already current. |
| `uv pip check` | PASS — 55 installed packages compatible. This does not detect missing undeclared dependencies. |

### Static analysis, formatting, and frontend gates

| Command | Result |
| --- | --- |
| `uv run ruff check .` | PASS — all checks passed. |
| `uv run ruff format --check .` | **FAIL** — 2 files would be reformatted: `infrastructure/migrations/versions/0006_application_jobs.py` and `tests/integration/database/test_jobs.py`. Both have LF in Git and CRLF in the Windows working tree. |
| `uv run mypy .` | PASS — no issues in 350 source files. |
| `pnpm lint` | PASS. |
| `pnpm typecheck` | PASS. |
| `pnpm test` | PASS — API client 37 tests and web 91 tests (128 total). |
| `pnpm build` | PASS — Next.js production build completed. Generated routes: `/`, `/_not-found`, `/projects/[project_id]`, and `/settings/system`. |
| `pnpm --filter @transloka/api-client check-generated` | PASS — generated API schema is current. |
| `pnpm e2e` | **FAIL** — the canonical E2E command/script does not exist. |

### Python, E2E, integrity, and recovery gates

| Command | Result |
| --- | --- |
| `uv run pytest -m "not slow and not requires_ollama and not requires_gpu" -q` | **FAIL** during collection — 3 `ModuleNotFoundError: reportlab` errors in digital E2E, final-PDF validation, and overlay integration. |
| `uv run pytest tests/security -q` | PASS — 71 passed in 11.18s, no skips. |
| `uv run pytest tests/unit/security tests/integration/ollama -q` | PASS — 108 passed in 27.57s. |
| `uv run pytest tests/e2e/digital -q` | **FAIL** during collection — missing `reportlab`. |
| `uv run pytest tests/e2e/scanned -q` | **FAIL** — missing `reportlab` prevents overlay reconstruction. |
| `uv run pytest tests/e2e/backup_restore -q` | PASS — 1 passed in 15.50s. |
| `uv run pytest tests/integration/backup tests/security/backup tests/recovery -q` | PASS — 52 passed in 57.50s. |
| `uv run pytest tests/integration/files/test_immutable_original_storage.py tests/security/files/test_pdf_validation.py -q` | PASS — 18 passed in 4.58s. |
| `uv run pytest tests/golden -q` | PASS — 12 passed. |
| `uv run pytest tests/unit/benchmark -q` | PASS — 9 benchmark-engine tests passed. |
| `uv run alembic heads` | PASS — single head `0017_backups`. |
| `uv run alembic history` | PASS — continuous chain from `0001_baseline` through `0017_backups`. |

### Diagnostic runs outside the locked release environment

These commands were diagnostic only. They do not satisfy the release gate
because the required packages are absent from the manifests and `uv.lock`.

| Command | Result |
| --- | --- |
| `uv run --with reportlab==5.0.1 pytest tests/e2e/digital tests/e2e/scanned tests/integration/reconstruction/test_final_pdf_validation.py -q` | PASS — 9/9 (digital 1, scanned 1, final-PDF 7). Confirms the locked dependency declaration is the immediate failure cause. |
| Full suite with ephemeral `reportlab==5.0.1` | 1193 passed, 7 skipped, 1 failed. The skips were 5 unavailable WeasyPrint-native-runtime cases and 2 unavailable Windows symlink cases. The single failure was caused by the ephemeral `VIRTUAL_ENV` value; its isolated locked-environment rerun passed 1/1. |
| Reflow test with ephemeral `weasyprint==69.0` | 2 passed, 5 skipped because Windows could not load `libgobject-2.0-0`. |

### Security, secrets, repository artifacts, and dependencies

| Command/check | Result |
| --- | --- |
| `gitleaks git --redact --no-banner` | PASS — 157 commits scanned; no leaks found. |
| Prohibited dependency scan | PASS — no `PyMuPDF`, `pymupdf`, `pymupdf4llm`, or `fitz` in manifests or lockfiles. |
| Tracked local-data/model scan | PASS — no runtime database, model weight, or user PDF is tracked; `.env.example` contains loopback-only example values. |
| `pnpm audit --audit-level critical` | PASS for Critical severity — 0 Critical; it still reports 3 High vulnerabilities. |
| `pnpm audit --audit-level high` | **FAIL** — 3 High vulnerabilities: `brace-expansion@5.0.8`, `js-yaml@4.3.0`, and `nanoid@3.3.16`. |
| `pnpm audit --prod --audit-level high` | **FAIL** — 1 production High: `nanoid@3.3.16` through `next > postcss`. |

## Runtime integration checks

The application source and runtime OpenAPI contract were inspected because the
service-level E2E tests manually add routers and use fake providers.

| Check | Result |
| --- | --- |
| API liveness `/health` | PASS — HTTP 200, version `0.1.0`. |
| System health `/api/v1/system/health` | **DEGRADED** — database, filesystem, worker, Ollama, and OCR all report `UNAVAILABLE`. |
| Core OpenAPI routes in `create_app()` | **FAIL** — model, benchmark, OCR, review, reconstruction, and warning routes are absent. |
| Worker Huey registry | **FAIL** — `create_huey()` has zero registered tasks. |
| Real quick benchmark using `qwen3:1.7b` | **FAIL** — 0 successful, 6 failed, code `PROVIDER_ERROR`; provider has no `translate` method. |

## Hardware and benchmark record

### Target hardware

| Component | Value |
| --- | --- |
| Operating system | Microsoft Windows 11 Home Single Language, 64-bit, build 26200 |
| CPU | AMD Ryzen 5 3550H, 4 physical / 8 logical cores |
| RAM | 15.44 GB total; approximately 5.2–5.6 GB available during review |
| Discrete GPU | NVIDIA GeForce GTX 1050, 3 GB reported adapter RAM |
| Integrated GPU | AMD Radeon Vega 8, 0.5 GB reported adapter RAM |
| Repository drive | `F:`; approximately 71.19 GB free |
| Ollama | `0.32.15`, healthy on `http://127.0.0.1:11434` |
| Installed model | `qwen3:1.7b`, Q4_K_M, approximately 1.4 GB, digest `8f68893c685c...` |

### Deterministic pipeline benchmark

Command:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/benchmark.ps1
```

The benchmark passed, but uses fake OCR/translation providers and the pypdf
blank-page fallback when ReportLab is absent. It measures pipeline overhead,
not model translation quality.

| Pages | Import s | Extraction s | OCR s | Translation s | Reconstruction s | Query s | Peak traced RAM MB | Disk bytes |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 10 | 0.0146 | 0.0299 | 0.0002 | 0.0067 | 0.1011 | 0.0034 | 0.0547 | 3,046 |
| 50 | 0.0911 | 0.1522 | 0.0017 | 0.0141 | 0.5005 | 0.0052 | 0.2410 | 12,806 |
| 100 | 0.1126 | 0.2384 | 0.0041 | 0.0196 | 1.1531 | 0.0039 | 0.4130 | 25,030 |
| 250 | 0.2964 | 0.7135 | 0.0048 | 0.0452 | 2.8932 | 0.0289 | 0.9221 | 62,230 |

### Local model benchmark

The benchmark engine tests pass and Ollama/model discovery works, but the real
provider cannot execute translation. No full benchmark report, quality score,
or model recommendation was produced. The installed model must not be selected
as a release default from this failed run.

## Backup and rollback verification

- Backup-restore E2E passed and restored project state, revisions, glossary,
  original file, and export with matching checksums.
- The broader backup, verification, security, and recovery set passed 52 tests.
- The migration chain has one head (`0017_backups`).
- The requested rollback tag is `m11-personal-mvp-complete`.
- The tag was not created because release gates failed. Tagging a known-bad
  release would incorrectly mark it as complete.

## Open defects

### REL-HIGH-001 — Reconstruction dependencies are not declared or locked

**Severity:** High, release blocking

Production overlay code imports ReportLab, but neither `reportlab` nor
`weasyprint` is declared in a Python manifest or `uv.lock`. A clean
`uv sync --locked` removes both. Digital E2E, scanned E2E, overlay integration,
and final-PDF validation therefore fail in the reproducible environment.

Required remediation:

1. Add the required reconstruction dependency or a canonical optional extra to
   the appropriate Python package and lock it.
2. Update the third-party license inventory.
3. Rerun the locked full suite, both E2E flows, and final-PDF validation.

### REL-HIGH-002 — Core runtime workflow is not wired into the application

**Severity:** High, release blocking

`create_app()` omits core model, benchmark, OCR, review, reconstruction,
warning, glossary, revision, segment, and settings routers. The E2E tests add
several routers manually. The worker's Huey registry is empty, while the API's
fallback translation queue is a no-op. The implemented service-level workflow
is therefore not available as an operational Personal MVP runtime.

Required remediation:

1. Register the canonical routers and their dependencies in the app factory.
2. Register concrete OCR/translation/reconstruction/backup worker tasks.
3. Replace no-op fallback queue behavior with explicit configuration failure.
4. Add runtime/API E2E tests that use the production app factory and worker.

### REL-HIGH-003 — Real Ollama translation and model benchmark cannot execute

**Severity:** High, release blocking

Ollama `0.32.15` and `qwen3:1.7b` are available locally, but
`OllamaTranslationProvider` implements health/model discovery only. The real
quick benchmark failed all six cases because the provider has no `translate`
method. The benchmark router is also absent from the production app factory.

Required remediation:

1. Implement the authorized localhost-only Ollama translation call with strict
   response parsing, timeout, size, cancellation, and redirect controls.
2. Wire quick/full benchmark runners into the application.
3. Run the full hardware/model benchmark and record license, settings, quality,
   latency, RAM/VRAM, and recommendation.

### REL-HIGH-004 — High-severity Node advisories remain unresolved

**Severity:** High, release blocking

The current audit reports three High advisories. One is in the production
dependency graph (`nanoid@3.3.16` through Next.js/PostCSS); two are development
paths (`brace-expansion@5.0.8` and `js-yaml@4.3.0`). No Critical advisory was
reported.

Required remediation:

1. Update/override dependencies to patched versions using a dedicated
   dependency task.
2. Regenerate and review `pnpm-lock.yaml`.
3. Rerun high- and critical-level audits plus frontend regression gates.

### REL-MEDIUM-001 — Ruff format check fails on Windows line endings

**Severity:** Medium, release-gate failure

Two tracked Python files are LF in the Git index but CRLF in the working tree,
and `ruff format --check .` reports both as unformatted. Normalize the checkout
policy (for example through an approved `.gitattributes` decision) and rerun the
format gate.

### REL-MEDIUM-002 — Canonical frontend E2E command is absent

**Severity:** Medium

`pnpm e2e` is specified by the implementation plan but no root/workspace E2E
script exists. There is also no Playwright configuration in the repository.

### REL-MEDIUM-003 — Reflow native runtime is unavailable

**Severity:** Medium

Five reflow integration scenarios skip because Windows cannot load
`libgobject-2.0-0`, even when WeasyPrint is supplied ephemerally. Reflow/hybrid
output requires an explicit native-runtime installation and validation plan.

## Known product limitations

- Single-user and localhost-only; the Windows OS account is the trust boundary.
- No authentication, multi-user support, cloud storage, remote inference,
  billing, or desktop installer.
- Personal MVP scope is PDF and English-to-Indonesian only.
- OCR and reconstruction quality require human review, especially for poor
  scans, complex tables, formulas, unusual fonts, and dense layouts.
- No model is universally recommended; model license and target-hardware
  benchmark must be reviewed separately.
- Several feature panels exist in source but are not connected to the main web
  navigation or production API runtime.

## Required next action

Do not declare the Personal MVP complete and do not create the rollback tag.
Create separately scoped remediation tasks for REL-HIGH-001 through
REL-HIGH-004, then rerun M11-T18 from a clean locked environment. After all
release-blocking gates pass, perform reconstruction manual review and create
the annotated rollback tag `m11-personal-mvp-complete` on the verified release
commit.
