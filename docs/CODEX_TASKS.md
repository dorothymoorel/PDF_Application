# CODEX TASKS

## CLOUD-01 - Governance and isolated Groq adapter

Owner-authorized addition: 2026-09-07. This task is active independently of M11-T18.
Objective: introduce an explicitly enabled Groq TranslationProvider and mocked tests.
Dependencies: existing provider protocol, translation request/response schemas and
prompt builder; the cloud exception in MVP_SCOPE, TECH_STACK_DECISIONS and SECURITY.

Exact allowed files:

```text
docs/MVP_SCOPE.md
docs/TECH_STACK_DECISIONS.md
docs/SECURITY.md
docs/MASTER_CODEX_PROMPT.md
docs/API_CONTRACT.md
docs/TRANSLATION_PIPELINE.md
docs/IMPLEMENTATION_PLAN.md
docs/CODEX_TASKS.md
docs/releases/CLOUD_TRANSLATION_DESIGN_2026-09-07.md
python/transloka-translation/src/transloka_translation/providers/groq.py
python/transloka-translation/src/transloka_translation/providers/base.py
tests/unit/translation/providers/test_groq.py
tests/unit/translation/providers/test_contract.py
```

Acceptance: explicit enabled configuration; consent gate on translate; credentials
read from environment at call time; fixed HTTPS endpoints, no proxies/redirects;
1 MiB request/response bounds, logical total timeout and cancellation; strict
response schema plus local segment validation; sanitized typed errors and optional
Retry-After seconds. No automatic retries, provider switch, model downloads,
SDK/dependency changes, API/worker wiring or live user-content requests in this task.

Tests must exercise valid translation/model discovery, disabled/missing consent,
missing/invalid key, malformed/duplicate JSON, truncated or refused completion,
wrong/missing segment IDs, oversize bodies, 401/403/429/5xx, redirect refusal,
timeout and cancellation/late-result discard. Existing Ollama tests must pass.
Run Ruff check/format, mypy, provider/schema/parser tests and Ollama regression.
Do not stage or commit unless separately instructed.

CLOUD-03..04 are ordered follow-ups defined in
[the design](releases/CLOUD_TRANSLATION_DESIGN_2026-09-07.md); they are not part of
CLOUD-02 completion. Register their final scopes before starting them.

## CLOUD-02 - API/worker persistence and safe resume

Owner-authorized addition: 2026-09-07. Dependency: CLOUD-01 completed and verified.
Objective: wire the approved Groq adapter through the translation API and production
worker while preserving local v1 commands, durable provider selection, review-safe
resume and attempt fencing.

Exact allowed files:

```text
docs/CODEX_TASKS.md
docs/releases/CLOUD_TRANSLATION_DESIGN_2026-09-07.md
services/api/src/transloka_api/routers/translation.py
services/worker/src/transloka_worker/translation.py
python/transloka-translation/src/transloka_translation/orchestration/models.py
python/transloka-translation/src/transloka_translation/orchestration/service.py
python/transloka-translation/src/transloka_translation/orchestration/persistence.py
tests/integration/api/test_translation.py
tests/integration/worker/test_translation_runtime.py
tests/integration/translation/test_orchestration.py
tests/e2e/runtime/test_translation_worker_runtime.py
packages/api-client/src/generated/schema.ts
```

Acceptance: existing local requests and queued v1 commands remain compatible;
readiness is provider-aware; the v2 command durably snapshots provider, model and
consent without a credential or fabricated LocalModelRecord; persisted translation
batches and attempts identify the real provider/model. A provider-wide operational
failure stops further calls, records sanitized retry metadata and leaves remaining
segments explicitly unattempted. Explicit retry creates a new durable run, skips
completed/approved/locked segments and preserves user edits. Cancellation and stale
attempt fencing remain effective.

Transient provider transport errors receive at most three total network attempts per
batch with cancellable bounded backoff; waits beyond the budget stop immediately and
persist Retry-After metadata. Do not add a provider SDK, migration, UI selector,
credential storage, automatic provider fallback, paid upgrade, or M11-T18 work.
Generate and check the API client schema, run focused API/worker/orchestration/E2E
tests plus Ruff and mypy, and do not stage or commit unless separately instructed.

## CLOUD-03 - User setup and generated client

Owner-authorized addition: 2026-09-07. Dependency: CLOUD-02 completed and verified.
Objective: expose the approved optional Groq provider through the generated API client
and translation UI while keeping local Ollama translation as the default.

Exact allowed files:

```text
apps/web/src/features/translation/types.ts
apps/web/src/features/translation/translation-settings.tsx
apps/web/src/features/translation/translation-settings.test.tsx
apps/web/src/features/translation/translation-progress.tsx
apps/web/src/features/translation/translation-progress.test.tsx
apps/web/features/workspace/project-workspace.tsx
packages/api-client/src/client.ts
packages/api-client/src/generated/schema.ts
packages/api-client/tests/client.test.ts
```

Acceptance: Ollama remains the default provider. Groq is explicitly selected, marked
as preview, and accompanied by a clear disclosure that selected translation text is
sent to Groq. The user must explicitly consent before cloud readiness or start; the UI
and client must not request, display, transmit, or persist an API key. Provider, model,
and consent are sent through the existing readiness/start contracts. Quota and other
provider-wide stops show truthful retry guidance, retry timing when available, and
remaining unattempted work even when zero segments failed. The UI must never switch
providers automatically.

Tests must cover the local default, cloud disclosure and consent gate, absence of a key
field, provider-aware readiness/start requests, provider-wide stop and retry rendering,
and generated-client response validation. Generate and check the API schema, then run
frontend/API-client tests, lint, typecheck, build, audit, and `git diff --check`. Do not
add backend or worker changes, dependencies, migrations, live cloud requests, CLOUD-04
evaluation, or M11-T18 work. Do not stage or commit unless separately instructed.

## TransLoka Personal MVP Atomic Task Backlog

**Document Name:** `CODEX_TASKS.md`
**Document Version:** 0.1
**Status:** Draft
**Decision Date:** 2026-07-26
**Application Mode:** Local-First, Single User
**Primary Platform:** Windows
**Implementation Method:** Milestone-based atomic execution with Codex

**Related Documents:**

* `PRD.md`
* `ARCHITECTURE.md`
* `TECH_STACK_DECISIONS.md`
* `DOCUMENT_IR.md`
* `TRANSLATION_PIPELINE.md`
* `GLOSSARY_ENGINE.md`
* `LOCAL_MODEL_BENCHMARK.md`
* `RECONSTRUCTION_ENGINE.md`
* `DATABASE_SCHEMA.md`
* `API_CONTRACT.md`
* `SECURITY.md`
* `TEST_PLAN.md`
* `MVP_SCOPE.md`
* `IMPLEMENTATION_PLAN.md`

---

# 1. Purpose

Dokumen ini menerjemahkan `IMPLEMENTATION_PLAN.md` menjadi backlog task atomik yang dapat diberikan kepada Codex satu per satu.

Setiap task memiliki:

* Task ID;
* tujuan;
* dependency;
* sumber requirement;
* file scope;
* implementation requirements;
* security requirements;
* test requirements;
* verification commands;
* acceptance criteria;
* definition of done;
* out-of-scope.

Dokumen ini tidak memerintahkan Codex membangun seluruh aplikasi sekaligus.

---

# 2. Codex Execution Rule

Codex hanya boleh mengerjakan:

```text
ONE TASK PER EXECUTION
```

Kecuali Project Owner secara eksplisit menggabungkan beberapa task yang:

* sangat kecil;
* memiliki dependency sama;
* menyentuh file yang sama;
* tetap dapat direview sebagai satu unit.

Codex tidak boleh otomatis melanjutkan ke task berikutnya.

---

# 3. Task Authority

Urutan authority untuk task:

```text
1. MVP_SCOPE.md
2. TECH_STACK_DECISIONS.md
3. SECURITY.md
4. DATABASE_SCHEMA.md
5. API_CONTRACT.md
6. Component specification documents
7. IMPLEMENTATION_PLAN.md
8. CODEX_TASKS.md
9. Prompt task individual
```

Prompt task individual tidak boleh melanggar dokumen dengan authority lebih tinggi.

---

# 4. Standard Task Status

```text
NOT_STARTED
READY
IN_PROGRESS
BLOCKED
IN_REVIEW
TESTING
COMPLETED
DEFERRED
CANCELLED
```

---

# 5. Standard Task Output

Setelah menyelesaikan task, Codex harus memberikan:

```text
Task ID:
Status:
Summary:
Files Changed:
Migration Added:
Endpoints Added:
Tests Added:
Commands Run:
Command Results:
Security Checks:
Known Limitations:
Assumptions:
Follow-up Dependencies:
```

---

# 6. Standard Verification Requirements

Setiap task Python minimal menjalankan:

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy .
uv run pytest <targeted-tests>
```

Setiap task frontend minimal menjalankan:

```bash
pnpm lint
pnpm typecheck
pnpm test <targeted-tests>
```

Task linting atau bootstrap dapat menggunakan command yang relevan dengan scope saat itu.

Task integration penting juga harus menjalankan affected integration suite.

---

# 7. Standard Prohibitions

Dalam seluruh task, Codex tidak boleh:

* menambahkan paid service;
* menambahkan cloud dependency;
* menambahkan authentication;
* menambahkan billing;
* menambahkan advertisement;
* menggunakan PyMuPDF;
* bind ke `0.0.0.0`;
* menggunakan `shell=True`;
* menulis ke original PDF;
* menyimpan binary dalam SQLite;
* menampilkan absolute path melalui API;
* mencatat isi dokumen ke log;
* menghapus test yang gagal;
* menonaktifkan lint atau type checking;
* menggunakan mock pada production path;
* menambahkan task berikutnya tanpa instruksi.

---

# 8. Milestone 0 — Repository Preparation

---

## M0-T01 — Create Repository Structure

**Objective:**
Membuat struktur monorepo awal sesuai arsitektur TransLoka.

**Dependencies:**
Tidak ada.

**Requirement Sources:**

* `TECH_STACK_DECISIONS.md`
* `IMPLEMENTATION_PLAN.md` Section 9
* `MVP_SCOPE.md` Section 9

**Allowed Files:**

```text
/
apps/
services/
python/
packages/
infrastructure/
scripts/
tests/
docs/
```

**Implementation Requirements:**

Buat struktur:

```text
transloka/
├── apps/
│   └── web/
├── services/
│   ├── api/
│   └── worker/
├── python/
│   ├── transloka-core/
│   ├── transloka-document-ir/
│   ├── transloka-documents/
│   ├── transloka-glossary/
│   ├── transloka-translation/
│   ├── transloka-reconstruction/
│   └── transloka-quality/
├── packages/
│   ├── api-client/
│   ├── ui/
│   └── shared-config/
├── infrastructure/
│   ├── local/
│   ├── docker/
│   └── migrations/
├── scripts/
├── tests/
└── docs/
```

Tambahkan placeholder `.gitkeep` hanya jika folder kosong perlu dipertahankan.

**Security Requirements:**

* Jangan membuat `.env` berisi nilai nyata.
* Jangan membuat folder model di repository.
* Jangan menyalin dokumen pengguna.

**Tests Required:**

* Repository structure smoke assertion atau script sederhana.
* Tidak perlu application test.

**Verification Commands:**

```bash
git status
```

**Acceptance Criteria:**

1. Seluruh folder utama tersedia.
2. Tidak ada dependency terpasang pada task ini.
3. Tidak ada generated binary.
4. Tidak ada user document.
5. Struktur sesuai dokumen.

**Out of Scope:**

* Next.js bootstrap;
* FastAPI bootstrap;
* dependency installation;
* database.

---

## M0-T02 — Configure Node Workspace

**Objective:**
Membuat pnpm workspace dan konfigurasi Node.js root.

**Dependencies:**
M0-T01.

**Allowed Files:**

```text
package.json
pnpm-workspace.yaml
.nvmrc
.node-version
apps/web/package.json
packages/*/package.json
```

**Implementation Requirements:**

* Node.js 24.
* Package manager pnpm.
* Root scripts untuk lint, typecheck, test, dan build.
* Workspace packages dikenali.
* Jangan menginstal framework yang belum dibutuhkan.

**Tests Required:**

* pnpm workspace discovery.
* root script smoke test.

**Verification Commands:**

```bash
pnpm install
pnpm -r list --depth -1
```

**Acceptance Criteria:**

* Workspace valid.
* Node version file konsisten.
* Root scripts tersedia.
* Tidak ada npm lockfile atau yarn lockfile.

---

## M0-T03 — Configure Python Workspace

**Objective:**
Membuat uv workspace dan struktur package Python.

**Dependencies:**
M0-T01.

**Allowed Files:**

```text
pyproject.toml
.python-version
python/*/pyproject.toml
python/*/src/
services/api/pyproject.toml
services/worker/pyproject.toml
```

**Implementation Requirements:**

* Python 3.12.
* uv workspace.
* Package menggunakan `src` layout.
* Tambahkan package metadata minimum.
* Jangan menambahkan OCR atau reconstruction dependency pada task ini.

**Tests Required:**

* workspace resolution.
* import smoke test.

**Verification Commands:**

```bash
uv sync
uv run python -c "print('workspace-ok')"
```

**Acceptance Criteria:**

* uv mengenali seluruh package.
* Python version konsisten.
* Tidak ada circular dependency awal.
* Import package kosong berhasil.

---

## M0-T04 — Configure Formatting, Linting, and Type Checking

**Objective:**
Mengaktifkan Ruff, mypy, ESLint, dan TypeScript strict.

**Dependencies:**
M0-T02, M0-T03.

**Allowed Files:**

```text
pyproject.toml
package.json
tsconfig.json
eslint.config.*
apps/web/tsconfig.json
packages/*/tsconfig.json
```

**Implementation Requirements:**

Python:

* Ruff lint;
* Ruff format;
* mypy strict secara bertahap;
* type checking untuk first-party package.

TypeScript:

* `strict: true`;
* `noUncheckedIndexedAccess`;
* `exactOptionalPropertyTypes`;
* `noImplicitOverride`.

**Tests Required:**

* lint smoke;
* typecheck smoke.

**Verification Commands:**

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy .
pnpm lint
pnpm typecheck
```

**Acceptance Criteria:**

* Seluruh command berjalan.
* Tidak ada global ignore yang melemahkan aturan inti.
* Tidak ada `skipLibCheck` tanpa alasan terdokumentasi.

---

## M0-T05 — Configure Git Ignore and Environment Template

**Objective:**
Mencegah data lokal, database, model, secret, dan build artifact masuk repository.

**Dependencies:**
M0-T01.

**Allowed Files:**

```text
.gitignore
.env.example
```

**Implementation Requirements:**

Ignore minimum:

```text
.env
.env.local
node_modules/
.venv/
.next/
dist/
coverage/
__pycache__/
.pytest_cache/
.mypy_cache/
.ruff_cache/
transloka-data/
models/
*.db
*.db-wal
*.db-shm
*.pdf
```

PDF test fixture yang memang versioned harus dikecualikan secara spesifik melalui folder fixture.

`.env.example` hanya berisi nama variable dan nilai aman.

**Security Requirements:**

* Tidak ada secret nyata.
* Tidak ada user path nyata.
* Tidak ada API key.

**Acceptance Criteria:**

* Local database tidak ter-track.
* Test fixture folder masih dapat menyimpan PDF legal.
* `.env.example` aman dibagikan.

---

## M0-T06 — Add License and Third-Party Inventory

**Objective:**
Membuat fondasi pencatatan lisensi dependency.

**Dependencies:**
M0-T02, M0-T03.

**Allowed Files:**

```text
LICENSE
THIRD_PARTY_LICENSES.md
docs/adr/
```

**Implementation Requirements:**

* Tentukan project license awal atau tandai `All Rights Reserved` jika belum diputuskan.
* Buat table dependency, fungsi, versi, lisensi, dan review status.
* Catat PyMuPDF sebagai prohibited dependency.

**Acceptance Criteria:**

* File lisensi tersedia.
* Inventory dapat diperbarui.
* Tidak ada klaim lisensi dependency yang tidak diverifikasi.

---

## M0-T07 — Add Documentation Index

**Objective:**
Membuat index authority dan urutan baca dokumen.

**Dependencies:**
M0-T01.

**Allowed Files:**

```text
docs/README.md
```

**Implementation Requirements:**

Cantumkan:

* tujuan tiap dokumen;
* authority order;
* dokumen superseded;
* dokumen yang harus dibaca Codex;
* status Draft atau active decision.

**Acceptance Criteria:**

* Codex dapat mengetahui dokumen yang berlaku.
* `TECH_STACK_DECISIONS.md v0.2` dinyatakan aktif.
* Personal MVP dinyatakan local-first dan no paid service.

---

# 9. Milestone 1 — Local Application Foundation

---

## M1-T01 — Bootstrap Next.js Application

**Objective:**
Membuat aplikasi Next.js App Router dengan TypeScript strict.

**Dependencies:**
M0-T02, M0-T04.

**Allowed Files:**

```text
apps/web/**
packages/ui/**
packages/shared-config/**
```

**Implementation Requirements:**

* Next.js App Router.
* TypeScript.
* Base layout.
* Root page.
* Tailwind CSS.
* shadcn/ui foundation jika diperlukan.
* Tidak membuat marketing homepage.
* Tidak membuat authentication.

**Tests Required:**

* root page renders;
* layout component;
* build smoke.

**Verification Commands:**

```bash
pnpm --filter web lint
pnpm --filter web typecheck
pnpm --filter web test
pnpm --filter web build
```

**Acceptance Criteria:**

* App dapat dibuild.
* Root page dapat dibuka.
* Tidak ada auth dependency.
* Tidak ada remote analytics.

---

## M1-T02 — Bootstrap FastAPI Application

**Objective:**
Membuat FastAPI application factory dan basic route.

**Dependencies:**
M0-T03, M0-T04.

**Allowed Files:**

```text
services/api/**
python/transloka-core/**
tests/unit/api/**
```

**Implementation Requirements:**

* FastAPI application factory.
* Pydantic settings.
* `/health`.
* `/api/v1/system/health` placeholder.
* Uvicorn entrypoint.
* Structured response models.

**Security Requirements:**

* Default host `127.0.0.1`.
* No debug information in response.
* No wildcard CORS.

**Tests Required:**

* app creation;
* health response;
* version response;
* no stack trace.

**Verification Commands:**

```bash
uv run pytest tests/unit/api
uv run ruff check .
uv run mypy .
```

**Acceptance Criteria:**

* API dapat start.
* `/health` mengembalikan `200`.
* Response schema valid.
* Host default loopback.

---

## M1-T03 — Implement Request ID and Error Normalization

**Objective:**
Menetapkan error envelope konsisten dan request tracing lokal.

**Dependencies:**
M1-T02.

**Allowed Files:**

```text
services/api/src/transloka_api/middleware/**
services/api/src/transloka_api/exception_handlers/**
services/api/src/transloka_api/schemas/**
tests/unit/api/**
```

**Implementation Requirements:**

* Generate request ID.
* Accept optional `X-Request-ID`.
* Add request ID to response.
* Normalize validation errors.
* Normalize not-found and internal errors.

**Security Requirements:**

* No stack trace in user response.
* No document content in logs.
* No absolute path.

**Tests Required:**

* generated request ID;
* supplied request ID;
* validation error;
* internal error sanitization.

**Acceptance Criteria:**

* Semua API error mengikuti `API_CONTRACT.md`.
* Request ID tersedia pada success dan error.

---

## M1-T04 — Implement Localhost Binding Guard

**Objective:**
Memblokir non-loopback bind secara default.

**Dependencies:**
M1-T02.

**Allowed Files:**

```text
services/api/src/transloka_api/config.py
services/api/src/transloka_api/startup/**
scripts/**
tests/unit/security/**
```

**Implementation Requirements:**

* Validasi IPv4 loopback.
* Validasi IPv6 `::1`.
* Explicit advanced override dapat ditunda.
* Startup gagal untuk `0.0.0.0`.

**Tests Required:**

* `127.0.0.1` accepted;
* `localhost` accepted;
* `::1` accepted;
* `0.0.0.0` rejected;
* LAN IP rejected.

**Acceptance Criteria:**

* Backend tidak dapat terbuka ke jaringan secara tidak sengaja.

---

## M1-T05 — Configure CORS and Origin Validation

**Objective:**
Mencegah malicious webpage memanggil API lokal.

**Dependencies:**
M1-T02.

**Allowed Files:**

```text
services/api/src/transloka_api/middleware/**
services/api/src/transloka_api/config.py
tests/unit/security/**
tests/integration/api/**
```

**Implementation Requirements:**

Allowed:

```text
http://127.0.0.1:3000
http://localhost:3000
```

* No wildcard origin.
* Mutation foreign origin rejected.
* `Origin: null` rejected untuk mutation.

**Tests Required:**

* allowed origin;
* foreign origin;
* null origin;
* preflight;
* wildcard absent.

**Acceptance Criteria:**

* Hanya frontend lokal resmi yang diterima dari browser.

---

## M1-T06 — Require TransLoka Client Headers

**Objective:**
Memaksa preflight dan membedakan request frontend resmi.

**Dependencies:**
M1-T03, M1-T05.

**Allowed Files:**

```text
services/api/src/transloka_api/middleware/**
packages/api-client/**
apps/web/src/lib/**
tests/integration/api/**
```

**Implementation Requirements:**

Wajib untuk `/api/v1` mutation:

```text
X-TransLoka-Client: web
X-TransLoka-Client-Version
```

Health endpoint dikecualikan.

**Tests Required:**

* valid headers;
* missing header;
* invalid client;
* GET policy;
* multipart upload future compatibility.

**Acceptance Criteria:**

* Mutation tanpa header ditolak.
* Frontend client otomatis mengirim header.

---

## M1-T07 — Create Worker Entrypoint and Heartbeat

**Objective:**
Membuat worker process dasar yang dapat start dan stop.

**Dependencies:**
M0-T03.

**Allowed Files:**

```text
services/worker/**
python/transloka-core/**
tests/unit/worker/**
```

**Implementation Requirements:**

* Worker entrypoint.
* Graceful shutdown.
* Heartbeat placeholder.
* Tidak menggunakan Celery atau Redis.
* Huey integration penuh ditunda ke M4.

**Tests Required:**

* worker imports;
* startup;
* shutdown;
* heartbeat state.

**Acceptance Criteria:**

* Worker process dapat dijalankan.
* Tidak ada fake completed task.

---

## M1-T08 — Create Windows Startup and Stop Scripts

**Objective:**
Memudahkan menjalankan frontend, API, dan worker secara lokal.

**Dependencies:**
M1-T01, M1-T02, M1-T07.

**Allowed Files:**

```text
scripts/setup-local.ps1
scripts/start.ps1
scripts/stop.ps1
README.md
```

**Implementation Requirements:**

* Tidak memerlukan administrator.
* Tidak membuka firewall.
* Tidak mengubah execution policy global.
* Periksa prerequisites.
* Start frontend, API, worker.
* Tampilkan process status.
* Stop process yang dimulai script.

**Security Requirements:**

* No `Invoke-Expression`.
* No arbitrary shell input.
* No remote download tanpa pemberitahuan.

**Tests Required:**

* script syntax check;
* manual smoke checklist.

**Acceptance Criteria:**

* Pengguna dapat menjalankan aplikasi melalui script.
* Stop script tidak mematikan process lain.

---

## M1-T09 — Build System Health Page

**Objective:**
Menampilkan status komponen lokal.

**Dependencies:**
M1-T01, M1-T02, M1-T07.

**Allowed Files:**

```text
apps/web/src/app/settings/system/**
apps/web/src/features/system/**
packages/api-client/**
```

**Implementation Requirements:**

Tampilkan:

* frontend;
* API;
* worker;
* database placeholder;
* filesystem placeholder;
* Ollama placeholder;
* OCR placeholder.

**Tests Required:**

* healthy;
* degraded;
* unavailable component;
* accessible status labels.

**Acceptance Criteria:**

* Status tidak hanya dibedakan dengan warna.
* Error dependency dapat dipahami.

---

## M1-T10 — Generate OpenAPI TypeScript Client

**Objective:**
Menghasilkan client frontend dari OpenAPI.

**Dependencies:**
M1-T02, M1-T03.

**Allowed Files:**

```text
packages/api-client/**
scripts/generate-api-client.*
package.json
```

**Implementation Requirements:**

* Generated types tidak diedit manual.
* Stable operation IDs.
* Script generation.
* Frontend dapat mengimpor client.

**Tests Required:**

* OpenAPI generation;
* generated client compilation;
* no duplicate schema.

**Acceptance Criteria:**

* Frontend tidak menulis ulang API type manual.

---

# 10. Milestone 2 — Database, Settings, and Projects

---

## M2-T01 — Implement Local Data Directory Resolution

**Objective:**
Menentukan dan memvalidasi data directory TransLoka.

**Dependencies:**
M1-T02.

**Allowed Files:**

```text
python/transloka-core/src/transloka_core/storage/**
services/api/src/transloka_api/config.py
tests/unit/storage/**
```

**Implementation Requirements:**

* Support `TRANSLOKA_DATA_DIR`.
* OS-aware default.
* Create required directories.
* Write permission test.
* Free disk query.
* Return internal path object only.

**Security Requirements:**

* Reject unsafe root.
* No arbitrary request path.
* No path returned through generic API.

**Tests Required:**

* explicit path;
* default path;
* no permission;
* relative path handling;
* path traversal;
* free space.

**Acceptance Criteria:**

* Semua managed file berada dalam root.
* Directory dapat dipakai setelah restart.

---

## M2-T02 — Configure SQLite Engine and Pragmas

**Objective:**
Membuat SQLAlchemy engine dengan SQLite WAL.

**Dependencies:**
M2-T01.

**Allowed Files:**

```text
python/transloka-core/src/transloka_core/database/**
tests/integration/database/**
```

**Implementation Requirements:**

Pragmas:

```sql
foreign_keys = ON
journal_mode = WAL
busy_timeout = 5000
synchronous = NORMAL
```

* Typed SQLAlchemy 2.
* Session factory.
* Transaction helper.

**Tests Required:**

* WAL enabled;
* foreign keys enabled;
* busy timeout;
* session rollback;
* reader during write.

**Acceptance Criteria:**

* Database berada pada data directory.
* SQLite error tidak membocorkan absolute path melalui API.

---

## M2-T03 — Configure Alembic

**Objective:**
Menyiapkan migration system.

**Dependencies:**
M2-T02.

**Allowed Files:**

```text
infrastructure/migrations/**
alembic.ini
python/transloka-core/**
tests/integration/database/test_migrations.py
```

**Implementation Requirements:**

* Alembic environment.
* Database URL resolved internal.
* Revision naming.
* Upgrade command.
* Current and history command.

**Tests Required:**

* empty database migration;
* current revision;
* repeated migration idempotence.

**Acceptance Criteria:**

* Schema tidak dibuat dengan production `create_all`.
* Migration dapat dijalankan melalui CLI.

---

## M2-T04 — Implement Application Metadata and Settings Tables

**Objective:**
Menyimpan metadata dan allowlisted application settings.

**Dependencies:**
M2-T03.

**Allowed Files:**

```text
python/transloka-core/src/transloka_core/database/models/application.py
python/transloka-core/src/transloka_core/repositories/settings.py
infrastructure/migrations/**
services/api/src/transloka_api/routers/settings.py
tests/**
```

**Implementation Requirements:**

* `app_metadata`;
* `app_settings`;
* JSON validation;
* setting categories;
* allowlisted keys;
* no secrets.

**Tests Required:**

* create setting;
* update allowed setting;
* reject unknown key;
* invalid JSON;
* restart persistence.

**Acceptance Criteria:**

* Frontend tidak dapat membuat arbitrary settings.
* No secret stored.

---

## M2-T05 — Implement Project Persistence

**Objective:**
Membuat project model, migration, repository, dan service.

**Dependencies:**
M2-T03.

**Allowed Files:**

```text
python/transloka-core/src/transloka_core/database/models/projects.py
python/transloka-core/src/transloka_core/repositories/projects.py
services/api/src/transloka_api/services/projects.py
infrastructure/migrations/**
tests/unit/projects/**
tests/integration/database/**
```

**Implementation Requirements:**

* Prefixed UUID.
* Project status enum.
* Source and target language.
* Translation style.
* Reconstruction mode.
* Progress.
* Timestamps.
* Archive state.
* Soft deletion field.

**Tests Required:**

* create;
* get;
* list;
* update;
* archive;
* invalid progress;
* invalid enum;
* persistence.

**Acceptance Criteria:**

* Project tetap ada setelah restart.
* No billing or user foreign key.

---

## M2-T06 — Implement Project API

**Objective:**
Menyediakan project CRUD sesuai contract.

**Dependencies:**
M2-T05, M1-T10.

**Allowed Files:**

```text
services/api/src/transloka_api/routers/projects.py
services/api/src/transloka_api/schemas/projects.py
services/api/src/transloka_api/app.py
packages/api-client/**
tests/integration/api/test_projects.py
```

**Implementation Requirements:**

* create;
* list;
* get;
* patch;
* archive;
* unarchive;
* router registration;
* normalized errors.

**Tests Required:**

* valid flow;
* missing project;
* archived project;
* validation;
* request envelope;
* client headers.

**Acceptance Criteria:**

* API sesuai `API_CONTRACT.md`.
* Absolute path tidak muncul.

---

## M2-T07 — Build Project Dashboard and Create Form

**Objective:**
Membuat UI project list dan project creation.

**Dependencies:**
M2-T06.

**Allowed Files:**

```text
apps/web/app/**
apps/web/features/projects/**
apps/web/package.json
packages/api-client/**
pnpm-lock.yaml
```

**Implementation Requirements:**

* project cards;
* create project form;
* loading;
* empty state;
* error state;
* archive view;
* client-side schema aligned with generated types.

**Tests Required:**

* render list;
* create project;
* validation error;
* API failure;
* archive indicator.

**Acceptance Criteria:**

* Project dapat dibuat dari UI.
* Page refresh mempertahankan project.

---

## M2-T08 — Implement Basic Database Integrity CLI

**Objective:**
Menambahkan command untuk memeriksa integritas SQLite.

**Dependencies:**
M2-T02, M2-T03.

**Allowed Files:**

```text
python/transloka-core/src/transloka_core/cli/**
tests/integration/database/**
```

**Implementation Requirements:**

Command:

```bash
uv run transloka db integrity-check
```

Check:

* SQLite integrity;
* foreign keys;
* schema revision;
* data directory.

**Tests Required:**

* healthy DB;
* invalid foreign key fixture;
* corrupted copy behavior.

**Acceptance Criteria:**

* Command tidak memperbaiki otomatis.
* Corruption menghasilkan exit code non-zero.

---

## M2-T09 — Implement Database-Only Backup

**Objective:**
Membuat backup SQLite yang aman.

**Dependencies:**
M2-T02.

**Allowed Files:**

```text
python/transloka-core/src/transloka_core/backup/**
tests/integration/backup/**
```

**Implementation Requirements:**

* SQLite backup API.
* Temporary file.
* Integrity verification.
* Checksum.
* Atomic rename.
* No raw copy during active WAL.

**Tests Required:**

* backup valid;
* restore into temporary database;
* checksum;
* interrupted backup;
* insufficient disk.

**Acceptance Criteria:**

* Backup dapat dibuka.
* Original DB tidak berubah.
* Incomplete backup tidak dianggap valid.

---

# 11. Milestone 3 — File Import and Document Analysis

---

## M3-T01 — Implement Stored File Model

**Objective:**
Menyimpan metadata file tanpa BLOB.

**Dependencies:**
M2-T03, M2-T05.

**Allowed Files:**

```text
python/transloka-core/src/transloka_core/database/models/files.py
python/transloka-core/src/transloka_core/repositories/files.py
infrastructure/migrations/**
tests/**
```

**Implementation Requirements:**

* relative storage key;
* file role;
* MIME;
* size;
* checksum;
* immutable flag;
* status;
* metadata JSON.

**Tests Required:**

* unique storage key;
* nonnegative size;
* immutable flag;
* no absolute path.

**Acceptance Criteria:**

* Binary tidak disimpan di DB.
* Path disimpan relatif.

---

## M3-T02 — Implement LocalFileStorage

**Objective:**
Membuat adapter filesystem lokal aman.

**Dependencies:**
M2-T01, M3-T01.

**Allowed Files:**

```text
python/transloka-core/src/transloka_core/storage/local.py
tests/unit/storage/**
tests/security/**
```

**Implementation Requirements:**

* write temporary;
* atomic commit;
* read;
* checksum;
* delete controlled;
* safe filename;
* root containment;
* symlink protection.

**Tests Required:**

* traversal;
* symlink escape;
* reserved filename;
* atomic write;
* duplicate filename;
* delete only managed file.

**Acceptance Criteria:**

* Tidak ada operation di luar data root.
* Original dapat ditandai immutable.

---

## M3-T03 — Implement Streaming PDF Upload

**Objective:**
Menerima upload tanpa membaca seluruh file ke RAM.

**Dependencies:**
M3-T02, M2-T06.

**Allowed Files:**

```text
services/api/src/transloka_api/routers/documents.py
services/api/src/transloka_api/services/imports.py
tests/integration/api/**
```

**Implementation Requirements:**

* multipart streaming;
* size limit while streaming;
* temporary file;
* cleanup on error;
* idempotency key foundation.

**Tests Required:**

* valid upload;
* empty upload;
* interrupted upload;
* oversized stream;
* Unicode filename.

**Acceptance Criteria:**

* Temporary file dibersihkan saat gagal.
* No arbitrary path request.

---

## M3-T04 — Implement PDF File Validation

**Objective:**
Memvalidasi PDF sebelum analysis.

**Dependencies:**
M3-T03.

**Allowed Files:**

```text
python/transloka-documents/src/transloka_documents/validation/**
tests/security/files/**
tests/fixtures/pdf/**
```

**Implementation Requirements:**

* extension;
* MIME signal;
* `%PDF-` magic;
* parser open;
* password protection;
* page count limit;
* basic complexity;
* checksum;
* disk estimate.

**Tests Required:**

* wrong extension;
* wrong magic;
* corrupted;
* password protected;
* page limit;
* malformed;
* oversized.

**Acceptance Criteria:**

* Invalid file ditolak dengan error code tepat.
* Parser failure tidak mematikan API.

---

## M3-T05 — Implement Immutable Original Storage

**Objective:**
Menyimpan PDF asli sebagai immutable source.

**Dependencies:**
M3-T02, M3-T04.

**Allowed Files:**

```text
services/api/src/transloka_api/services/imports.py
python/transloka-core/src/transloka_core/storage/**
tests/integration/files/**
```

**Implementation Requirements:**

* copy from validated temp;
* calculate SHA-256;
* assign original role;
* no overwrite;
* database record;
* readonly application policy.

**Tests Required:**

* checksum;
* retry import;
* overwrite attempt;
* original mutation check.

**Acceptance Criteria:**

* Source checksum tetap.
* Output tidak pernah menggunakan source path sebagai target.

---

## M3-T06 — Implement Document Model and Migration

**Objective:**
Menyimpan document metadata.

**Dependencies:**
M3-T01, M3-T05.

**Allowed Files:**

```text
python/transloka-core/src/transloka_core/database/models/documents.py
infrastructure/migrations/**
tests/integration/database/**
```

**Implementation Requirements:**

* project link;
* original file;
* class;
* language;
* page count;
* status;
* metadata;
* scanned count;
* image and table count.

**Tests Required:**

* valid document;
* unique project/original;
* invalid counts;
* foreign key.

**Acceptance Criteria:**

* Document dapat direferensikan project.
* Tidak ada binary field.

---

## M3-T07 — Implement Basic PDF Metadata Analysis

**Objective:**
Mengekstrak metadata dan page information.

**Dependencies:**
M3-T06, M4 job system dapat menggunakan synchronous development path sementara hanya jika diberi label prototype.

**Allowed Files:**

```text
python/transloka-documents/src/transloka_documents/analysis/**
tests/integration/pdf/**
```

**Implementation Requirements:**

Gunakan:

* pypdf untuk metadata;
* pdfplumber untuk text presence;
* pypdfium2 untuk rendering support.

Output:

* title;
* author;
* page count;
* dimensions;
* rotation;
* text-layer estimate.

**Tests Required:**

* portrait;
* landscape;
* rotation;
* missing metadata;
* malformed page.

**Acceptance Criteria:**

* Analysis tidak menggunakan PyMuPDF.
* Metadata failure tidak membatalkan seluruh import jika PDF masih valid.

---

## M3-T08 — Implement Document Page Model

**Objective:**
Menyimpan halaman sumber.

**Dependencies:**
M3-T06, M3-T07.

**Allowed Files:**

```text
python/transloka-core/src/transloka_core/database/models/pages.py
infrastructure/migrations/**
tests/integration/database/**
```

**Implementation Requirements:**

* source page number;
* logical number;
* dimensions;
* rotation;
* page type;
* classification;
* confidence;
* render references.

**Tests Required:**

* unique page number;
* valid geometry;
* rotation;
* invalid confidence.

**Acceptance Criteria:**

* Setiap page terhubung ke document.
* Page numbering stabil.

---

## M3-T09 — Implement Page Rendering and Thumbnail Generation

**Objective:**
Menghasilkan preview halaman menggunakan pypdfium2.

**Dependencies:**
M3-T08, M3-T02.

**Allowed Files:**

```text
python/transloka-documents/src/transloka_documents/rendering/**
tests/integration/pdf/**
```

**Implementation Requirements:**

* full render;
* WebP thumbnail;
* DPI allowlist;
* cache key;
* file records;
* memory safety.

**Tests Required:**

* render portrait;
* landscape;
* rotated;
* excessive DPI;
* checksum;
* repeated cache hit.

**Acceptance Criteria:**

* Thumbnail dapat dibuka.
* Render tidak keluar data directory.
* Excessive DPI ditolak.

---

## M3-T10 — Implement Active Content Detection

**Objective:**
Mendeteksi JavaScript, attachment, dan unsafe action.

**Dependencies:**
M3-T07.

**Allowed Files:**

```text
python/transloka-documents/src/transloka_documents/security/**
tests/security/pdf/**
```

**Implementation Requirements:**

* detect embedded JavaScript;
* detect attachment;
* detect launch action;
* detect unsafe URL schemes;
* create warnings.

**Tests Required:**

* JavaScript fixture;
* attachment fixture;
* safe link;
* unsafe link.

**Acceptance Criteria:**

* Active content tidak dijalankan.
* Warning tersedia.

---

## M3-T11 — Build Document Import and Analysis UI

**Objective:**
Membuat file picker, validation feedback, dan document overview.

**Dependencies:**
M3-T03, M3-T07, M3-T09.

**Allowed Files:**

```text
apps/web/src/features/documents/**
apps/web/src/app/projects/[project_id]/**
```

**Implementation Requirements:**

* file selection;
* upload progress;
* error display;
* document summary;
* thumbnails;
* analysis status.

**Tests Required:**

* valid selection;
* wrong file;
* upload error;
* progress;
* thumbnail list.

**Acceptance Criteria:**

* User dapat memahami alasan file ditolak.
* No filesystem path exposed.

---

# 12. Milestone 4 — Background Job System

---

## M4-T01 — Configure SqliteHuey

**Objective:**
Menyiapkan queue lokal tanpa Redis.

**Dependencies:**
M2-T01, M1-T07.

**Allowed Files:**

```text
services/worker/**
python/transloka-core/src/transloka_core/jobs/**
tests/integration/worker/**
```

**Implementation Requirements:**

* `SqliteHuey`;
* queue DB `tasks.db`;
* worker count 1 default;
* configuration;
* graceful shutdown.

**Tests Required:**

* enqueue;
* execute;
* restart;
* queue DB separate.

**Acceptance Criteria:**

* Redis tidak digunakan.
* Queue tidak memakai application DB.

---

## M4-T02 — Implement Application Job Models

**Objective:**
Menyimpan business job dan attempts.

**Dependencies:**
M2-T03, M3-T06.

**Allowed Files:**

```text
python/transloka-core/src/transloka_core/database/models/jobs.py
infrastructure/migrations/**
tests/integration/database/**
```

**Implementation Requirements:**

* application jobs;
* attempts;
* dependencies;
* status;
* progress;
* heartbeat;
* error;
* idempotency.

`job_type` menggunakan closed allowlist:

```text
IMPORT_DOCUMENT
ANALYZE_DOCUMENT
OCR_DOCUMENT
DETECT_TERMS
TRANSLATE_DOCUMENT
RECONSTRUCT_DOCUMENT
EXPORT_DOCUMENT
BENCHMARK_MODEL
BACKUP_DATABASE
RESTORE_DATABASE
MAINTENANCE
```

Status attempt menggunakan closed allowlist:

```text
RUNNING
COMPLETED
COMPLETED_WITH_WARNINGS
PARTIALLY_COMPLETED
FAILED
CANCELLED
STALE
```

**Tests Required:**

* constraints;
* status;
* unique idempotency;
* attempt numbering.

**Acceptance Criteria:**

* Job state tidak bergantung hanya pada Huey.

---

## M4-T03 — Implement Job Dispatch Service

**Objective:**
Menghubungkan business job dengan queue.

**Dependencies:**
M4-T01, M4-T02.

**Allowed Files:**

```text
python/transloka-core/src/transloka_core/jobs/dispatch.py
services/worker/**
tests/integration/worker/**
```

**Implementation Requirements:**

* create DB job;
* dispatch queue task;
* safe failure if dispatch fails;
* payload only contains IDs;
* outbox-like consistency atau documented fallback.

**Tests Required:**

* successful dispatch;
* queue unavailable;
* duplicate key;
* payload does not contain binary.

**Acceptance Criteria:**

* Queue failure tidak meninggalkan job palsu `QUEUED`.

---

## M4-T04 — Implement Job Progress and Heartbeat

**Objective:**
Menyimpan progress dan mendeteksi worker aktif.

**Dependencies:**
M4-T03.

**Allowed Files:**

```text
python/transloka-core/src/transloka_core/jobs/progress.py
services/worker/**
tests/integration/worker/**
```

**Implementation Requirements:**

* progress 0–1;
* current stage;
* heartbeat;
* safe update;
* transaction short.

**Tests Required:**

* valid update;
* invalid progress;
* heartbeat;
* job completed.

**Acceptance Criteria:**

* Frontend dapat membaca status terbaru.

---

## M4-T05 — Implement Job API

**Objective:**
Menyediakan get, list, dan attempts.

**Dependencies:**
M4-T02, M4-T04.

**Allowed Files:**

```text
services/api/src/transloka_api/app.py
services/api/src/transloka_api/routers/jobs.py
services/api/src/transloka_api/schemas/jobs.py
packages/api-client/**
tests/integration/api/**
```

**Tests Required:**

* get;
* list;
* filters;
* missing;
* response schema;
* attempts.

**Acceptance Criteria:**

* API sesuai contract.
* Job ID internal Huey tidak diekspos.

---

## M4-T06 — Implement Cooperative Cancellation

**Objective:**
Membatalkan job tanpa merusak data.

**Dependencies:**
M4-T04, M4-T05.

**Allowed Files:**

```text
python/transloka-core/src/transloka_core/jobs/cancellation.py
services/worker/**
services/api/src/transloka_api/routers/jobs.py
services/api/src/transloka_api/schemas/jobs.py
packages/api-client/**
tests/integration/api/**
tests/recovery/**
```

**Implementation Requirements:**

* request flag;
* checkpoint;
* atomic operation completion;
* cleanup incomplete output;
* preserve valid prior result.

**Tests Required:**

* cancel queued;
* cancel running;
* repeated cancel;
* completed job cannot cancel;
* incomplete file cleanup.

**Acceptance Criteria:**

* Cancelled output tidak dianggap final.

---

## M4-T07 — Implement Retry and Attempt History

**Objective:**
Memungkinkan retry aman.

**Dependencies:**
M4-T03, M4-T06.

**Allowed Files:**

```text
python/transloka-core/src/transloka_core/jobs/retry.py
services/api/src/transloka_api/routers/jobs.py
services/api/src/transloka_api/schemas/jobs.py
packages/api-client/**
tests/integration/api/**
tests/integration/worker/**
```

**Implementation Requirements:**

* bounded retries;
* new attempt;
* retry reason;
* failed-items-only option foundation;
* no duplicate result.

**Tests Required:**

* first retry;
* max retries;
* repeated retry;
* completed job rejection;
* idempotency.

**Acceptance Criteria:**

* Attempt history lengkap.
* Retry tidak menghapus error lama.

---

## M4-T08 — Implement Stale Job Recovery

**Objective:**
Menangani worker crash dan application restart.

**Dependencies:**
M4-T04, M4-T07.

**Allowed Files:**

```text
python/transloka-core/src/transloka_core/jobs/recovery.py
services/api/src/transloka_api/startup/**
tests/recovery/**
```

**Implementation Requirements:**

* stale threshold;
* heartbeat inspection;
* mark `STALE`;
* inspect final artifact;
* retry option;
* no auto-complete based only on file existence.

**Tests Required:**

* stale running;
* healthy running;
* incomplete output;
* valid atomic output;
* restart.

**Acceptance Criteria:**

* Duplicate work tidak terjadi tanpa reason.
* Stale state terlihat oleh user.

---

## M4-T09 — Build Job Progress UI

**Objective:**
Menampilkan job progress, stage, cancel, dan retry.

**Dependencies:**
M4-T08.

**Allowed Files:**

```text
apps/web/src/features/jobs/**
```

**Implementation Requirements:**

* polling;
* `Retry-After`;
* terminal status stop;
* cancel button;
* retry button;
* failure details.

**Tests Required:**

* queued;
* running;
* completed;
* failed;
* cancelled;
* polling cleanup.

**Acceptance Criteria:**

* UI tidak polling setelah terminal state.

---

# 13. Milestone 5 — Document IR and Editor Foundation

---

## M5-T01 — Implement Document IR Domain Models

**Objective:**
Membuat model Pydantic/domain sesuai `DOCUMENT_IR.md`.

**Dependencies:**
M3-T08.

**Allowed Files:**

```text
python/transloka-document-ir/**
tests/unit/document_ir/**
```

**Implementation Requirements:**

* Document;
* Page;
* Section;
* Block;
* Segment;
* Asset;
* Table;
* Cell;
* Annotation;
* Relationship;
* Warning;
* schema version.

**Tests Required:**

* required fields;
* invalid geometry;
* serialization;
* round trip;
* stable ID.

**Acceptance Criteria:**

* Source dan target data terpisah.
* Unknown incompatible schema ditolak.

---

## M5-T02 — Implement Document Structure Database Tables

**Objective:**
Membuat section, block, segment, asset, table, dan relationship tables.

**Dependencies:**
M5-T01, M2-T03.

**Allowed Files:**

```text
python/transloka-core/src/transloka_core/database/models/document_ir.py
infrastructure/migrations/**
tests/integration/database/**
```

**Implementation Requirements:**

Sesuai `DATABASE_SCHEMA.md`.

**Tests Required:**

* foreign keys;
* unique reading order;
* segment order;
* table cell position;
* cascade behavior.

**Acceptance Criteria:**

* Struktur Document IR dapat dipersist.

---

## M5-T03 — Implement Digital Text Extraction

**Objective:**
Mengekstrak text dan geometry dari PDF digital.

**Dependencies:**
M3-T07, M5-T01.

**Allowed Files:**

```text
python/transloka-documents/src/transloka_documents/extraction/**
tests/golden/**
```

**Implementation Requirements:**

* pdfplumber;
* words;
* lines;
* character geometry jika tersedia;
* text blocks;
* normalization boundaries.

**Tests Required:**

* single column;
* two column;
* heading;
* list;
* ligature;
* hyphenation.

**Acceptance Criteria:**

* No PyMuPDF.
* Source text dapat dilacak ke geometry.

---

## M5-T04 — Implement Reading Order Resolver

**Objective:**
Menentukan urutan baca halaman.

**Dependencies:**
M5-T03.

**Allowed Files:**

```text
python/transloka-documents/src/transloka_documents/structure/reading_order.py
tests/unit/documents/**
tests/golden/**
```

**Implementation Requirements:**

* single-column;
* two-column;
* header;
* body;
* footer;
* stable order;
* uncertainty warning.

**Tests Required:**

* normal;
* two-column;
* sidebar;
* ambiguous layout.

**Acceptance Criteria:**

* Tidak menggabungkan kolom secara zigzag salah pada fixture dasar.

---

## M5-T05 — Implement Block Classification

**Objective:**
Mengklasifikasikan block dasar.

**Dependencies:**
M5-T03, M5-T04.

**Allowed Files:**

```text
python/transloka-documents/src/transloka_documents/structure/classifier.py
tests/unit/documents/**
```

**Implementation Requirements:**

Types minimum:

* title;
* heading;
* paragraph;
* list;
* caption;
* image;
* table;
* code;
* header;
* footer;
* page number;
* unknown.

**Tests Required:**

* each type;
* low confidence;
* unknown fallback.

**Acceptance Criteria:**

* Unknown tidak dipaksakan ke type salah tanpa warning.

---

## M5-T06 — Implement Segmentation Engine

**Objective:**
Membuat unit translation.

**Dependencies:**
M5-T05.

**Allowed Files:**

```text
python/transloka-documents/src/transloka_documents/segmentation/**
tests/unit/segmentation/**
```

**Implementation Requirements:**

* paragraph;
* sentence;
* heading;
* list item;
* caption;
* table cell;
* code not translated;
* URL intact.

**Tests Required:**

* abbreviation;
* decimal;
* citation;
* URL;
* long sentence;
* mixed language.

**Acceptance Criteria:**

* Segment stable dan ordered.
* URL/code tidak terpotong.

---

## M5-T07 — Implement Asset Extraction

**Objective:**
Menyimpan image dan geometry.

**Dependencies:**
M5-T02, M5-T03.

**Allowed Files:**

```text
python/transloka-documents/src/transloka_documents/assets/**
tests/integration/pdf/**
```

**Implementation Requirements:**

* image reference;
* geometry;
* page;
* asset type;
* checksum;
* caption relationship.

**Tests Required:**

* JPEG;
* PNG;
* repeated image;
* missing image;
* rotation.

**Acceptance Criteria:**

* Asset disimpan di filesystem.
* Aspect ratio metadata tersedia.

---

## M5-T08 — Implement Simple Table Extraction

**Objective:**
Membuat table dan cell untuk table sederhana.

**Dependencies:**
M5-T02, M5-T03.

**Allowed Files:**

```text
python/transloka-documents/src/transloka_documents/tables/**
tests/golden/**
```

**Implementation Requirements:**

* row and column;
* header candidate;
* geometry;
* simple complexity classification;
* fallback unknown.

**Tests Required:**

* grid table;
* no border table;
* merged cell limited;
* complex fallback.

**Acceptance Criteria:**

* Complex table tidak direkonstruksi paksa pada tahap extraction.

---

## M5-T09 — Implement IR Snapshot Service

**Objective:**
Menyimpan snapshot JSON immutable.

**Dependencies:**
M5-T01, M5-T02, M3-T02.

**Allowed Files:**

```text
python/transloka-document-ir/src/transloka_document_ir/snapshots.py
tests/integration/document_ir/**
```

**Implementation Requirements:**

* version;
* checksum;
* file record;
* revision number;
* immutable;
* canonical JSON.

**Tests Required:**

* create;
* checksum;
* repeated version;
* round trip;
* tampered snapshot.

**Acceptance Criteria:**

* Snapshot lama tidak ditimpa.

---

## M5-T10 — Implement Page Editor View API

**Objective:**
Mengembalikan page, block, segment, dan warning dalam satu request.

**Dependencies:**
M5-T02, M3-T09.

**Allowed Files:**

```text
services/api/src/transloka_api/routers/pages.py
services/api/src/transloka_api/schemas/pages.py
tests/integration/api/**
```

**Implementation Requirements:**

* page metadata;
* blocks;
* segments;
* warnings;
* preview URLs;
* stable ordering.

**Tests Required:**

* page found;
* page missing;
* ordering;
* no path exposure;
* pagination if needed.

**Acceptance Criteria:**

* Frontend tidak perlu query per block.

---

## M5-T11 — Build Source Page Viewer

**Objective:**
Menampilkan PDF page dan bounding boxes.

**Dependencies:**
M5-T10.

**Allowed Files:**

```text
apps/web/src/features/editor/**
apps/web/src/features/pdf-viewer/**
```

**Implementation Requirements:**

* PDF.js;
* zoom;
* page navigation;
* block overlay;
* segment selection;
* reading-order indicator development-only.

**Tests Required:**

* render;
* zoom;
* select;
* page change;
* keyboard navigation basic.

**Acceptance Criteria:**

* Bounding box aligned pada fixture dasar.

---

# 14. Milestone 6 — Glossary and Protected Content

---

## M6-T01 — Implement Glossary Database Models

**Objective:**
Membuat glossary-related schema.

**Dependencies:**
M5-T02.

**Allowed Files:**

```text
python/transloka-core/src/transloka_core/database/models/glossary.py
infrastructure/migrations/**
tests/integration/database/**
```

**Implementation Requirements:**

* glossaries;
* terms;
* revisions;
* snapshots;
* candidates;
* occurrences;
* conflicts;
* protected items.

**Tests Required:**

* constraints;
* revision uniqueness;
* snapshot immutability;
* target required rule.

**Acceptance Criteria:**

* Tidak ada user-account dependency.

---

## M6-T02 — Implement Glossary CRUD Service and API

**Objective:**
Menyediakan glossary dan term management.

**Dependencies:**
M6-T01.

**Allowed Files:**

```text
python/transloka-glossary/**
services/api/src/transloka_api/routers/glossaries.py
tests/**
```

**Implementation Requirements:**

* create;
* list;
* update;
* activate;
* deactivate;
* term CRUD;
* revision.

**Tests Required:**

* CRUD;
* duplicate;
* version conflict;
* deactivate;
* archived term.

**Acceptance Criteria:**

* Semua perubahan term memiliki revision.

---

## M6-T03 — Implement Glossary Matching Engine

**Objective:**
Mencocokkan terminology secara deterministik.

**Dependencies:**
M6-T02.

**Allowed Files:**

```text
python/transloka-glossary/src/transloka_glossary/matching/**
tests/unit/glossary/**
```

**Implementation Requirements:**

* exact;
* phrase;
* case-insensitive;
* whole-word;
* longest-match-first;
* punctuation;
* overlap resolution.

**Tests Required:**

* phrase overlap;
* nested term;
* case;
* punctuation;
* repeated term.

**Acceptance Criteria:**

* Hasil deterministik.
* Tidak memilih secara acak.

---

## M6-T04 — Implement Glossary Scope Priority

**Objective:**
Menerapkan scope hierarchy.

**Dependencies:**
M6-T03.

**Allowed Files:**

```text
python/transloka-glossary/src/transloka_glossary/resolution/**
tests/unit/glossary/**
```

**Implementation Requirements:**

Minimum priority:

```text
SEGMENT
SECTION
DOCUMENT
PROJECT
USER
DOMAIN
SYSTEM
```

Personal MVP dapat hanya memiliki UI untuk empat scope pertama.

**Tests Required:**

* project overrides system;
* segment overrides document;
* equal-priority conflict.

**Acceptance Criteria:**

* Conflict tanpa winner menghasilkan warning.

---

## M6-T05 — Implement Placeholder Generator

**Objective:**
Menghasilkan placeholder aman.

**Dependencies:**
M6-T03.

**Allowed Files:**

```text
python/transloka-glossary/src/transloka_glossary/placeholders/generator.py
tests/unit/placeholders/**
```

**Implementation Requirements:**

Format:

```text
__TLK_<TYPE>_<NUMBER>_<CHECK>__
```

* collision detection;
* stable inventory per request;
* type allowlist.

**Tests Required:**

* uniqueness;
* collision;
* repeated source;
* invalid type;
* long document.

**Acceptance Criteria:**

* Placeholder tidak muncul alami dalam source tanpa collision handling.

---

## M6-T06 — Implement Protected Content Detector

**Objective:**
Melindungi term dan non-translatable item.

**Dependencies:**
M6-T05.

**Allowed Files:**

```text
python/transloka-glossary/src/transloka_glossary/protection/**
tests/unit/protection/**
```

**Implementation Requirements:**

Protect:

* glossary term;
* URL;
* email;
* code;
* endpoint;
* file path;
* citation;
* acronym.

**Tests Required:**

* each type;
* overlap;
* URL punctuation;
* code identifier;
* path separators.

**Acceptance Criteria:**

* Protected inventory lengkap.

---

## M6-T07 — Implement Placeholder Restoration and Validation

**Objective:**
Memulihkan protected content secara strict.

**Dependencies:**
M6-T06.

**Allowed Files:**

```text
python/transloka-glossary/src/transloka_glossary/placeholders/restoration.py
tests/unit/placeholders/**
```

**Implementation Requirements:**

Detect:

* missing;
* altered;
* duplicated;
* unknown;
* reordered where order matters.

**Tests Required:**

* successful restore;
* missing;
* duplicate;
* unknown;
* malformed;
* punctuation.

**Acceptance Criteria:**

* Mismatch menghasilkan critical failure.
* Partial silent restore tidak diperbolehkan.

---

## M6-T08 — Implement Term Candidate Detection

**Objective:**
Menghasilkan calon terminology.

**Dependencies:**
M5-T06, M6-T01.

**Allowed Files:**

```text
python/transloka-glossary/src/transloka_glossary/candidates/**
tests/unit/glossary/**
```

**Implementation Requirements:**

* repeated phrase;
* named entity signal;
* technical identifier;
* occurrence count;
* confidence;
* common-word filtering dasar.

**Tests Required:**

* repeated phrase;
* common word;
* code;
* capitalization;
* minimum occurrence.

**Acceptance Criteria:**

* Candidate tidak otomatis menjadi glossary.

---

## M6-T09 — Implement Glossary Conflict Detection

**Objective:**
Mendeteksi rule yang tidak konsisten.

**Dependencies:**
M6-T04.

**Allowed Files:**

```text
python/transloka-glossary/src/transloka_glossary/conflicts/**
tests/unit/glossary/**
```

**Implementation Requirements:**

* target conflict;
* rule conflict;
* scope conflict;
* context conflict;
* resolution status.

**Tests Required:**

* auto-resolved;
* manual conflict;
* inactive rule ignored.

**Acceptance Criteria:**

* Translation readiness diblokir untuk unresolved blocking conflict.

---

## M6-T10 — Implement Glossary Snapshot Service

**Objective:**
Membekukan term set untuk translation batch.

**Dependencies:**
M6-T01, M6-T04.

**Allowed Files:**

```text
python/transloka-glossary/src/transloka_glossary/snapshots.py
tests/integration/glossary/**
```

**Implementation Requirements:**

* compile active rules;
* canonical order;
* checksum;
* immutable file;
* source version list.

**Tests Required:**

* repeated snapshot same content;
* changed term new version;
* tamper;
* immutability.

**Acceptance Criteria:**

* Batch selalu menunjuk snapshot ID.

---

## M6-T11 — Implement Glossary UI

**Objective:**
Menyediakan terms, candidates, conflicts, dan occurrences.

**Dependencies:**
M6-T02, M6-T08, M6-T09.

**Allowed Files:**

```text
apps/web/src/features/glossary/**
```

**Implementation Requirements:**

* term list;
* create/edit;
* rule type;
* candidate accept/reject;
* conflict view;
* occurrence list.

**Tests Required:**

* CRUD;
* candidate;
* conflict;
* form validation;
* empty state.

**Acceptance Criteria:**

* User dapat menetapkan `workflow` sebagai `KEEP_ORIGINAL`.

---

## M6-T12 — Implement Glossary Impact Analysis

**Objective:**
Menghitung dampak perubahan term.

**Dependencies:**
M6-T03, M6-T10.

**Allowed Files:**

```text
python/transloka-glossary/src/transloka_glossary/impact.py
services/api/src/transloka_api/routers/glossaries.py
tests/**
```

**Implementation Requirements:**

Return:

* affected segments;
* approved;
* locked;
* safe replacement;
* retranslation recommended;
* conflicts.

**Tests Required:**

* unreviewed;
* approved;
* locked;
* no occurrence;
* multiple terms.

**Acceptance Criteria:**

* Tidak mengubah segment saat hanya melakukan analysis.

---

# 15. Milestone 7 — Local Translation Pipeline

---

## M7-T01 — Implement Translation Provider Protocol

**Objective:**
Membuat adapter contract.

**Dependencies:**
M6-T10.

**Allowed Files:**

```text
python/transloka-translation/src/transloka_translation/providers/**
tests/unit/translation/providers/**
```

**Implementation Requirements:**

Methods:

* health check;
* list models;
* translate;
* cancellation support where possible.

Implement:

* FakeTranslationProvider;
* protocol only for Ollama initially.

**Tests Required:**

* provider contract;
* fake success;
* fake failure.

**Acceptance Criteria:**

* Business logic tidak bergantung langsung pada Ollama client.

---

## M7-T02 — Implement Ollama Health and Model Listing

**Objective:**
Mendeteksi local Ollama.

**Dependencies:**
M7-T01.

**Allowed Files:**

```text
python/transloka-translation/src/transloka_translation/providers/ollama.py
services/api/src/transloka_api/routers/models.py
tests/integration/ollama/**
```

**Implementation Requirements:**

* local URL only;
* health;
* model list;
* timeout;
* normalized errors;
* no model download.

**Tests Required:**

* unavailable;
* local endpoint;
* remote URL blocked;
* empty model list;
* fake HTTP server.

**Acceptance Criteria:**

* Remote endpoint ditolak default.
* No cloud fallback.

---

## M7-T03 — Implement Local Model Persistence and Selection

**Objective:**
Menyimpan model yang terdeteksi dan pilihan user.

**Dependencies:**
M7-T02, M2-T03.

**Allowed Files:**

```text
python/transloka-core/src/transloka_core/database/models/models.py
infrastructure/migrations/**
services/api/src/transloka_api/routers/models.py
tests/**
```

**Implementation Requirements:**

* local model record;
* install state;
* license status;
* selected translation;
* selected validation;
* only one selected per role.

**Tests Required:**

* refresh;
* select;
* unavailable model;
* license unknown warning.

**Acceptance Criteria:**

* Model ID tidak di-hard-code.

---

## M7-T04 — Implement Translation Request and Response Schemas

**Objective:**
Menetapkan structured translation contract.

**Dependencies:**
M7-T01, M6-T07.

**Allowed Files:**

```text
python/transloka-translation/src/transloka_translation/schemas/**
tests/unit/translation/**
```

**Implementation Requirements:**

Request:

* segments;
* context;
* glossary;
* placeholders;
* style.

Response:

* known segment IDs;
* translated text only.

**Tests Required:**

* valid;
* missing;
* unknown field;
* duplicate ID;
* wrong type.

**Acceptance Criteria:**

* Tidak ada field action, command, URL fetch, atau file operation.

---

## M7-T05 — Implement Versioned Prompt Builder

**Objective:**
Membangun prompt yang memisahkan instruction dan source data.

**Dependencies:**
M7-T04.

**Allowed Files:**

```text
python/transloka-translation/src/transloka_translation/prompts/**
tests/unit/translation/prompts/**
```

**Implementation Requirements:**

* prompt version;
* translation style;
* source as structured data;
* glossary;
* no system prompt leakage;
* source instructions treated as data.

**Tests Required:**

* prompt injection source;
* style;
* glossary;
* deterministic structure;
* no raw shell fields.

**Acceptance Criteria:**

* Fake system message dalam source tidak menjadi instruction.

---

## M7-T06 — Implement Translation Batch Builder

**Objective:**
Membentuk batch berdasarkan segment dan context.

**Dependencies:**
M7-T05.

**Allowed Files:**

```text
python/transloka-translation/src/transloka_translation/batching/**
tests/unit/translation/**
```

**Implementation Requirements:**

* batch size;
* context length;
* segment order;
* locked exclusion;
* token estimate;
* section grouping;
* no duplicate segment.

**Tests Required:**

* 1, 5, 10, 20;
* long segment;
* locked;
* mixed section;
* overflow estimate.

**Acceptance Criteria:**

* Batch order deterministic.

---

## M7-T07 — Implement Structured Response Parser

**Objective:**
Memvalidasi response model.

**Dependencies:**
M7-T04.

**Allowed Files:**

```text
python/transloka-translation/src/transloka_translation/parsing/**
tests/unit/translation/**
```

**Implementation Requirements:**

Reject:

* invalid JSON;
* markdown wrapper if strict parser cannot safely normalize;
* missing segment;
* duplicate;
* unknown ID;
* empty text.

**Tests Required:**

Semua failure scenario dari `TEST_PLAN.md`.

**Acceptance Criteria:**

* Response invalid tidak masuk sebagai machine translation valid.

---

## M7-T08 — Implement Deterministic Translation Validators

**Objective:**
Memeriksa correctness invariant.

**Dependencies:**
M7-T07, M6-T07.

**Allowed Files:**

```text
python/transloka-translation/src/transloka_translation/validation/**
tests/unit/translation/validation/**
```

**Implementation Requirements:**

Validators:

* placeholder;
* mapping;
* number;
* URL;
* code;
* citation;
* language;
* empty;
* suspicious length.

**Tests Required:**

* valid and invalid per validator;
* negation fixture as benchmark warning;
* added number;
* altered URL.

**Acceptance Criteria:**

* Critical integrity error memblokir acceptance.

---

## M7-T09 — Implement Translation Persistence Models

**Objective:**
Menyimpan batches, attempts, results, dan validations.

**Dependencies:**
M7-T08, M2-T03.

**Allowed Files:**

```text
python/transloka-core/src/transloka_core/database/models/translation.py
infrastructure/migrations/**
tests/integration/database/**
```

**Implementation Requirements:**

Sesuai `DATABASE_SCHEMA.md`.

**Tests Required:**

* batch;
* segment join;
* attempt;
* validation unique;
* append-only result.

**Acceptance Criteria:**

* Previous attempt tidak ditimpa.

---

## M7-T10 — Implement Translation Orchestration Service

**Objective:**
Menjalankan pipeline end-to-end.

**Dependencies:**
M7-T06, M7-T07, M7-T08, M7-T09, M4-T03.

**Allowed Files:**

```text
python/transloka-translation/src/transloka_translation/orchestration/**
services/worker/**
tests/integration/translation/**
```

**Implementation Requirements:**

Pipeline:

```text
load
protect
context
batch
provider
parse
restore
validate
persist
status
```

**Tests Required:**

* fake success;
* partial failure;
* provider timeout;
* cancellation;
* idempotency;
* locked segment.

**Acceptance Criteria:**

* Completed valid segment tersimpan.
* Failed segment dapat diidentifikasi.

---

## M7-T11 — Implement Translation Retry Hierarchy

**Objective:**
Mencoba ulang dengan strategi aman.

**Dependencies:**
M7-T10.

**Allowed Files:**

```text
python/transloka-translation/src/transloka_translation/retry.py
tests/integration/translation/**
```

**Implementation Requirements:**

```text
same batch
smaller batch
single segment
reduced context
manual review
```

**Tests Required:**

* batch split;
* successful prior segment preserved;
* max attempt;
* idempotency.

**Acceptance Criteria:**

* Retry tidak menggandakan revision valid.

---

## M7-T12 — Implement Translation Readiness and API

**Objective:**
Menyediakan readiness, start, status, cancel, retry.

**Dependencies:**
M7-T10, M4-T05.

**Allowed Files:**

```text
services/api/src/transloka_api/routers/translation.py
packages/api-client/**
tests/integration/api/**
```

**Implementation Requirements:**

Readiness blockers:

* no model;
* Ollama down;
* unresolved source;
* glossary conflict;
* no segments.

**Tests Required:**

* ready;
* each blocker;
* start;
* duplicate start;
* cancel;
* retry.

**Acceptance Criteria:**

* Translation tidak dimulai jika readiness gagal.

---

## M7-T13 — Build Translation Settings and Progress UI

**Objective:**
Memilih model, style, batch size, dan menjalankan translation.

**Dependencies:**
M7-T03, M7-T12.

**Allowed Files:**

```text
apps/web/src/features/translation/**
apps/web/src/features/models/**
```

**Implementation Requirements:**

* model selection;
* health;
* style;
* batch;
* start;
* progress;
* cancel;
* retry failures.

**Tests Required:**

* no model;
* Ollama down;
* running;
* failed;
* completed.

**Acceptance Criteria:**

* UI tidak menawarkan cloud provider.

---

## M7-T14 — Implement Quick Model Benchmark

**Objective:**
Menguji model secara singkat.

**Dependencies:**
M7-T02, M7-T08.

**Allowed Files:**

```text
python/transloka-translation/src/transloka_translation/benchmark/**
services/api/src/transloka_api/routers/benchmarks.py
tests/unit/benchmark/**
```

**Implementation Requirements:**

* 5–8 cases;
* structured output;
* placeholder;
* latency;
* basic recommendation;
* no silent model download.

**Tests Required:**

* completed;
* schema failure;
* placeholder failure;
* interrupted.

**Acceptance Criteria:**

* Model yang gagal critical test tidak direkomendasikan.

---

# 16. Milestone 8 — Review Editor

---

## M8-T01 — Implement Segment Revision Model

**Objective:**
Mencatat setiap perubahan translation.

**Dependencies:**
M7-T09.

**Allowed Files:**

```text
python/transloka-core/src/transloka_core/database/models/revisions.py
infrastructure/migrations/**
tests/integration/database/**
```

**Implementation Requirements:**

* append-only;
* revision number;
* type;
* previous;
* new;
* reason;
* source translation reference.

**Tests Required:**

* sequential revision;
* duplicate number;
* restore creates new revision.

**Acceptance Criteria:**

* Revision lama tidak diubah.

---

## M8-T02 — Implement Segment Edit API

**Objective:**
Mengedit translation dengan optimistic locking.

**Dependencies:**
M8-T01.

**Allowed Files:**

```text
services/api/src/transloka_api/routers/segments.py
services/api/src/transloka_api/services/segments.py
tests/integration/api/**
```

**Implementation Requirements:**

* expected revision;
* reviewed translation;
* reason;
* update final text;
* invalidate reconstruction cache.

**Tests Required:**

* edit;
* conflict;
* locked;
* empty;
* revision created.

**Acceptance Criteria:**

* Stale edit menghasilkan `409`.

---

## M8-T03 — Implement Approve and Unapprove

**Objective:**
Mengelola review state.

**Dependencies:**
M8-T02.

**Allowed Files:**

```text
services/api/src/transloka_api/routers/segments.py
tests/integration/api/**
```

**Implementation Requirements:**

* approve;
* unapprove;
* revision;
* optional lock after approval.

**Tests Required:**

* approve;
* unapprove;
* invalid state;
* revision conflict.

**Acceptance Criteria:**

* Approved text menjadi final text.

---

## M8-T04 — Implement Segment Locking

**Objective:**
Melindungi approved segment.

**Dependencies:**
M8-T03.

**Allowed Files:**

```text
services/api/src/transloka_api/services/segments.py
tests/integration/api/**
```

**Implementation Requirements:**

* lock;
* unlock;
* reason for unlock;
* block edit and retranslation.

**Tests Required:**

* lock;
* edit locked;
* translate locked;
* unlock;
* revision.

**Acceptance Criteria:**

* Locked segment tidak dapat diubah diam-diam.

---

## M8-T05 — Implement Segment Revision API

**Objective:**
Melihat dan memulihkan revision.

**Dependencies:**
M8-T01.

**Allowed Files:**

```text
services/api/src/transloka_api/routers/revisions.py
tests/integration/api/**
```

**Implementation Requirements:**

* list;
* get;
* restore;
* pagination;
* restore creates new revision.

**Tests Required:**

* list order;
* restore;
* invalid revision;
* conflict.

**Acceptance Criteria:**

* Restore tidak menghapus revision setelahnya.

---

## M8-T06 — Build Side-by-Side Review Editor

**Objective:**
Menggabungkan page preview, source, translation, dan context.

**Dependencies:**
M5-T11, M8-T02.

**Allowed Files:**

```text
apps/web/src/features/editor/**
```

**Implementation Requirements:**

Panels:

* source PDF;
* source segment;
* translation editor;
* context;
* glossary;
* warnings.

**Tests Required:**

* select segment;
* edit;
* save;
* API failure;
* loading;
* locked state.

**Acceptance Criteria:**

* User dapat review satu segment tanpa pindah halaman penuh.

---

## M8-T07 — Implement Unsaved Change Protection

**Objective:**
Mencegah edit hilang.

**Dependencies:**
M8-T06.

**Allowed Files:**

```text
apps/web/src/features/editor/state/**
apps/web/src/features/editor/hooks/**
tests/frontend/**
```

**Implementation Requirements:**

* dirty state;
* page navigation warning;
* segment navigation warning;
* browser unload warning where supported.

**Tests Required:**

* no change;
* dirty navigation;
* successful save;
* failed save.

**Acceptance Criteria:**

* Unsaved edit tidak hilang diam-diam.

---

## M8-T08 — Implement Review Queue API and UI

**Objective:**
Menampilkan segment yang memerlukan review.

**Dependencies:**
M7-T12, M8-T02.

**Allowed Files:**

```text
services/api/src/transloka_api/routers/review.py
apps/web/src/features/review-queue/**
tests/**
```

**Implementation Requirements:**

Filters:

* warning;
* confidence;
* status;
* page;
* section.

**Tests Required:**

* filters;
* ordering;
* empty state;
* navigation to segment.

**Acceptance Criteria:**

* User dapat berpindah antarsegmen review.

---

## M8-T09 — Implement Warning Resolution

**Objective:**
Mencatat penyelesaian warning.

**Dependencies:**
M8-T02.

**Allowed Files:**

```text
services/api/src/transloka_api/routers/warnings.py
apps/web/src/features/warnings/**
tests/**
```

**Implementation Requirements:**

* resolve;
* accept;
* false positive;
* non-overridable critical policy.

**Tests Required:**

* resolve;
* accept;
* critical block;
* history.

**Acceptance Criteria:**

* Warning tidak dihapus dari history.

---

## M8-T10 — Implement Basic Bulk Segment Actions

**Objective:**
Menyediakan approve, lock, dan retranslate selected.

**Dependencies:**
M8-T03, M8-T04, M7-T12.

**Allowed Files:**

```text
services/api/src/transloka_api/routers/segments.py
apps/web/src/features/editor/bulk/**
tests/**
```

**Implementation Requirements:**

* selected IDs;
* action allowlist;
* partial failure;
* locked policy;
* job for heavy retranslation.

**Tests Required:**

* approve multiple;
* mixed state;
* locked;
* invalid ID;
* retry.

**Acceptance Criteria:**

* Bulk action tidak mengabaikan revision conflict.

---

## M8-T11 — Implement Editor Accessibility Basics

**Objective:**
Meningkatkan keyboard dan screen-reader usability.

**Dependencies:**
M8-T06.

**Allowed Files:**

```text
apps/web/src/features/editor/**
tests/accessibility/**
```

**Implementation Requirements:**

* labels;
* keyboard navigation;
* focus;
* warning text;
* modal focus trap;
* semantic buttons.

**Tests Required:**

* keyboard;
* labels;
* focus;
* automated accessibility smoke.

**Acceptance Criteria:**

* Warning tidak hanya ditunjukkan oleh warna.

---

# 17. Milestone 9 — OCR and Scanned Documents

---

## M9-T01 — Implement OCR Provider Protocol

**Objective:**
Membuat contract OCR.

**Dependencies:**
M5-T01.

**Allowed Files:**

```text
python/transloka-documents/src/transloka_documents/ocr/**
tests/unit/ocr/**
```

**Implementation Requirements:**

* health;
* analyze page;
* settings;
* result geometry;
* confidence.

Implement:

* FakeOCRProvider;
* protocol for PaddleOCR.

**Tests Required:**

* fake success;
* empty;
* low confidence;
* timeout.

**Acceptance Criteria:**

* Pipeline tidak bergantung langsung pada Paddle class.

---

## M9-T02 — Implement PaddleOCR Provider

**Objective:**
Menjalankan OCR lokal.

**Dependencies:**
M9-T01.

**Allowed Files:**

```text
python/transloka-documents/src/transloka_documents/ocr/paddle.py
tests/integration/ocr/**
```

**Implementation Requirements:**

* local model;
* CPU mode;
* geometry;
* confidence;
* no remote URL;
* controlled model cache;
* one-page processing.

**Tests Required:**

* clean scan;
* rotated;
* provider unavailable;
* model missing;
* timeout.

**Acceptance Criteria:**

* OCR berjalan lokal.
* No cloud fallback.

---

## M9-T03 — Implement Scanned Page Detection

**Objective:**
Menentukan halaman yang memerlukan OCR.

**Dependencies:**
M3-T07, M9-T01.

**Allowed Files:**

```text
python/transloka-documents/src/transloka_documents/ocr/detection.py
tests/unit/ocr/**
```

**Implementation Requirements:**

Signals:

* no text;
* low text coverage;
* image dominance;
* poor native extraction.

**Tests Required:**

* digital;
* scanned;
* hybrid;
* image page with no text;
* threshold.

**Acceptance Criteria:**

* Image-only illustration tidak selalu dianggap perlu OCR tanpa text signal.

---

## M9-T04 — Implement OCR Job Orchestration

**Objective:**
Menjalankan OCR per page melalui worker.

**Dependencies:**
M9-T02, M9-T03, M4-T03.

**Allowed Files:**

```text
services/worker/src/**
python/transloka-documents/src/transloka_documents/ocr/orchestration.py
tests/integration/ocr/**
```

**Implementation Requirements:**

* page render;
* OCR;
* persistence;
* progress;
* retry;
* cancellation;
* raw output file.

**Tests Required:**

* selected pages;
* auto pages;
* partial failure;
* cancel;
* retry.

**Acceptance Criteria:**

* Page valid lain tetap tersimpan jika satu page gagal.

---

## M9-T05 — Implement OCR Normalization and Reading Order

**Objective:**
Mengubah output OCR menjadi block dan segment source.

**Dependencies:**
M9-T04, M5-T04.

**Allowed Files:**

```text
python/transloka-documents/src/transloka_documents/ocr/normalization.py
tests/unit/ocr/**
```

**Implementation Requirements:**

* whitespace;
* line merge;
* hyphenation;
* geometry;
* reading order;
* confidence propagation.

**Tests Required:**

* multiline;
* hyphen;
* two columns;
* low confidence.

**Acceptance Criteria:**

* Raw OCR tetap tersedia.

---

## M9-T06 — Implement Source Resolution and OCR Correction API

**Objective:**
Memisahkan raw OCR dan corrected source.

**Dependencies:**
M9-T05, M8-T01.

**Allowed Files:**

```text
services/api/src/transloka_api/routers/ocr.py
services/api/src/transloka_api/services/source_resolution.py
tests/integration/api/**
```

**Implementation Requirements:**

* resolved source text;
* expected revision;
* source correction event/revision;
* downstream invalidation policy.

**Tests Required:**

* correction;
* conflict;
* raw preserved;
* translation invalidation.

**Acceptance Criteria:**

* Correction tidak menimpa raw OCR.

---

## M9-T07 — Build OCR Review UI

**Objective:**
Memungkinkan correction source text.

**Dependencies:**
M9-T06.

**Allowed Files:**

```text
apps/web/src/features/ocr/**
```

**Implementation Requirements:**

* page image;
* raw OCR;
* resolved source;
* confidence;
* save;
* warning.

**Tests Required:**

* low confidence;
* edit;
* save;
* conflict;
* navigation.

**Acceptance Criteria:**

* User memahami bahwa perubahan source dapat memerlukan retranslation.

---

## M9-T08 — Implement Basic OCR Table Mapping

**Objective:**
Memetakan simple OCR table.

**Dependencies:**
M9-T05, M5-T08.

**Allowed Files:**

```text
python/transloka-documents/src/transloka_documents/ocr/tables.py
tests/integration/ocr/**
```

**Implementation Requirements:**

* simple grid;
* cell text;
* geometry;
* confidence;
* fallback complex.

**Tests Required:**

* simple;
* missing border;
* complex fallback.

**Acceptance Criteria:**

* Complex table tidak dipaksa menjadi struktur salah.

---

## M9-T09 — Implement OCR Warnings

**Objective:**
Mencatat low confidence dan uncertainty.

**Dependencies:**
M9-T04, M8-T09.

**Allowed Files:**

```text
python/transloka-quality/src/transloka_quality/ocr/**
tests/unit/quality/**
```

**Implementation Requirements:**

Warnings:

* low confidence;
* unresolved block;
* reading-order uncertainty;
* possible text in image;
* table uncertainty.

**Tests Required:**

* threshold;
* page scope;
* warning resolution.

**Acceptance Criteria:**

* Critical low-quality source dapat memblokir translation sesuai policy.

---

## M9-T10 — Implement Scanned PDF End-to-End Test

**Objective:**
Membuktikan scanned workflow.

**Dependencies:**
M9-T07, M7-T12, M10 belum tersedia sehingga test dapat berhenti pada reviewed translation dulu; final full E2E diperluas pada M11.

**Allowed Files:**

```text
tests/e2e/scanned/**
```

**Implementation Requirements:**

* import;
* detect;
* OCR;
* correct;
* glossary;
* translate;
* review.

**Acceptance Criteria:**

* Source correction dan translation tersimpan.
* Original unchanged.

---

# 18. Milestone 10 — Reconstruction and Export

---

## M10-T01 — Implement Reconstruction Models and Migration

**Objective:**
Menyimpan reconstruction jobs, pages, blocks, dan mappings.

**Dependencies:**
M8-T01, M2-T03.

**Allowed Files:**

```text
python/transloka-core/src/transloka_core/database/models/reconstruction.py
infrastructure/migrations/**
tests/integration/database/**
```

**Implementation Requirements:**

Sesuai `DATABASE_SCHEMA.md`.

**Tests Required:**

* job;
* page;
* block;
* mapping;
* hash uniqueness.

**Acceptance Criteria:**

* Multiple export versions dapat menunjuk reconstruction berbeda.

---

## M10-T02 — Implement Reconstruction Settings Schema

**Objective:**
Memvalidasi mode dan profile reconstruction.

**Dependencies:**
M10-T01.

**Allowed Files:**

```text
python/transloka-reconstruction/src/transloka_reconstruction/settings.py
tests/unit/reconstruction/**
```

**Implementation Requirements:**

Modes:

* OVERLAY;
* REFLOW;
* HYBRID.

Profiles:

* PRESERVE_LAYOUT;
* BALANCED;
* READABILITY_FIRST.

Settings sesuai `RECONSTRUCTION_ENGINE.md`.

**Tests Required:**

* defaults;
* invalid minimum font;
* invalid profile;
* unsafe setting.

**Acceptance Criteria:**

* Hybrid default.
* Profile tidak silently mengubah protected content.

---

## M10-T03 — Implement Font Resolver

**Objective:**
Memetakan font sumber ke output.

**Dependencies:**
M10-T02.

**Allowed Files:**

```text
python/transloka-reconstruction/src/transloka_reconstruction/fonts/**
tests/unit/reconstruction/fonts/**
```

**Implementation Requirements:**

Order:

* embedded legal and usable;
* system same font;
* metric compatible;
* configured fallback;
* universal fallback.

**Tests Required:**

* available;
* unavailable;
* serif;
* sans;
* monospace;
* missing glyph.

**Acceptance Criteria:**

* Font proprietary tidak diekstrak atau didistribusikan tanpa review.

---

## M10-T04 — Implement Text Measurement

**Objective:**
Mengukur target text dengan font output.

**Dependencies:**
M10-T03.

**Allowed Files:**

```text
python/transloka-reconstruction/src/transloka_reconstruction/layout/measurement.py
tests/unit/reconstruction/**
```

**Implementation Requirements:**

* width;
* height;
* wrap;
* line count;
* line height;
* style;
* deterministic result.

**Tests Required:**

* short;
* long;
* bold;
* italic;
* font fallback;
* line break.

**Acceptance Criteria:**

* Pengukuran menggunakan font aktual.

---

## M10-T05 — Implement Overflow and Collision Detection

**Objective:**
Mendeteksi layout failure.

**Dependencies:**
M10-T04.

**Allowed Files:**

```text
python/transloka-reconstruction/src/transloka_reconstruction/layout/overflow.py
python/transloka-reconstruction/src/transloka_reconstruction/layout/collision.py
tests/unit/reconstruction/**
```

**Implementation Requirements:**

Overflow:

* horizontal;
* vertical;
* page;
* cell.

Collision:

* text-text;
* text-image;
* text-table;
* header/footer.

**Tests Required:**

Semua type dan severity.

**Acceptance Criteria:**

* Critical collision memblokir final export.

---

## M10-T06 — Implement Overlay Page Generator

**Objective:**
Membuat overlay transparent dengan ReportLab dan merge dengan pypdf.

**Dependencies:**
M10-T04, M10-T05.

**Allowed Files:**

```text
python/transloka-reconstruction/src/transloka_reconstruction/overlay/**
tests/integration/reconstruction/**
```

**Implementation Requirements:**

* source page copy;
* source text cover;
* transparent overlay;
* translated selectable text;
* merge;
* page dimensions;
* no duplicate searchable source text where source is covered.

**Security Requirements:**

* Original read-only.
* No PyMuPDF.
* No active content propagation.

**Tests Required:**

* plain page;
* header;
* caption;
* text box;
* output text extraction;
* source residue.

**Acceptance Criteria:**

* Output valid.
* Translated text searchable.
* Source text tidak terlihat ganda.

---

## M10-T07 — Implement Overlay Source Text Cover Strategies

**Objective:**
Menangani source text region.

**Dependencies:**
M10-T06.

**Allowed Files:**

```text
python/transloka-reconstruction/src/transloka_reconstruction/overlay/cover.py
tests/integration/reconstruction/**
```

**Implementation Requirements:**

Minimum:

* solid-background cover;
* raster-background fallback.

**Tests Required:**

* white;
* colored;
* image background fallback;
* uncovered source warning.

**Acceptance Criteria:**

* Tidak meninggalkan visible source text tanpa warning.

---

## M10-T08 — Implement Sanitized Reflow HTML Builder

**Objective:**
Mengubah Document IR ke internal HTML/CSS.

**Dependencies:**
M10-T02, M10-T03.

**Allowed Files:**

```text
python/transloka-reconstruction/src/transloka_reconstruction/reflow/**
tests/unit/reconstruction/reflow/**
```

**Implementation Requirements:**

* escaped text;
* allowlisted elements;
* internal CSS;
* local asset IDs;
* no arbitrary HTML;
* no script.

**Tests Required:**

* source `<script>`;
* unsafe URL;
* code;
* heading;
* table;
* image.

**Acceptance Criteria:**

* Source text selalu escaped.

---

## M10-T09 — Implement Restricted WeasyPrint Resource Loader

**Objective:**
Mencegah remote dan filesystem access.

**Dependencies:**
M10-T08.

**Allowed Files:**

```text
python/transloka-reconstruction/src/transloka_reconstruction/reflow/resources.py
tests/security/reconstruction/**
```

**Implementation Requirements:**

Allow:

* approved local asset;
* approved local font.

Reject:

* HTTP;
* HTTPS;
* FTP;
* arbitrary file;
* UNC;
* localhost fetch.

**Tests Required:**

* local approved;
* outside root;
* remote;
* data URI oversized;
* symlink.

**Acceptance Criteria:**

* WeasyPrint tidak dapat membaca arbitrary local file.

---

## M10-T10 — Implement Reflow PDF Generator

**Objective:**
Membuat PDF dari sanitized HTML.

**Dependencies:**
M10-T08, M10-T09.

**Allowed Files:**

```text
python/transloka-reconstruction/src/transloka_reconstruction/reflow/generator.py
tests/integration/reconstruction/**
```

**Implementation Requirements:**

* page size;
* margin;
* heading;
* paragraph;
* list;
* image;
* table;
* page break;
* widow/orphan basic.

**Tests Required:**

* long paragraph;
* heading;
* image;
* table;
* added page;
* unsafe resource.

**Acceptance Criteria:**

* Output searchable dan valid.

---

## M10-T11 — Implement Hybrid Strategy Classifier

**Objective:**
Memilih overlay, reflow, preserve, atau reconstruct per page/block.

**Dependencies:**
M10-T06, M10-T10.

**Allowed Files:**

```text
python/transloka-reconstruction/src/transloka_reconstruction/hybrid/**
tests/unit/reconstruction/**
```

**Implementation Requirements:**

Defaults:

* header/footer/caption/fixed text → overlay;
* body paragraph expansion → reflow;
* image → preserve;
* simple table → reconstruct;
* complex → image/manual review.

**Tests Required:**

* fixed page;
* body page;
* mixed;
* table-heavy;
* unsupported.

**Acceptance Criteria:**

* Decision tersimpan dan deterministik.

---

## M10-T12 — Implement Image Preservation

**Objective:**
Menempatkan image tanpa merusak aspect ratio.

**Dependencies:**
M10-T06, M10-T10.

**Allowed Files:**

```text
python/transloka-reconstruction/src/transloka_reconstruction/assets/**
tests/integration/reconstruction/**
```

**Implementation Requirements:**

* preserve;
* aspect ratio;
* crop;
* rotation;
* caption relation;
* missing asset warning.

**Tests Required:**

* PNG;
* JPEG;
* transparent;
* rotation;
* missing.

**Acceptance Criteria:**

* Major image preservation metric tersedia.

---

## M10-T13 — Implement Simple Table Reconstruction

**Objective:**
Membangun ulang table sederhana.

**Dependencies:**
M10-T04, M5-T08.

**Allowed Files:**

```text
python/transloka-reconstruction/src/transloka_reconstruction/tables/**
tests/integration/reconstruction/**
```

**Implementation Requirements:**

* rows;
* columns;
* header;
* cell wrapping;
* row expansion;
* numeric integrity;
* continuation.

**Tests Required:**

* simple;
* multiline;
* repeated header;
* split page;
* numbers.

**Acceptance Criteria:**

* Missing cell = 0 untuk fixture simple.

---

## M10-T14 — Implement Complex Table Fallback

**Objective:**
Menjaga table kompleks secara aman.

**Dependencies:**
M10-T13.

**Allowed Files:**

```text
python/transloka-reconstruction/src/transloka_reconstruction/tables/fallback.py
tests/integration/reconstruction/**
```

**Implementation Requirements:**

* preserve as image;
* translated caption;
* warning;
* no false claim reconstructed.

**Tests Required:**

* nested;
* irregular;
* image fallback;
* warning.

**Acceptance Criteria:**

* Table tidak rusak diam-diam.

---

## M10-T15 — Implement Layout Fallback Chain

**Objective:**
Menangani text expansion.

**Dependencies:**
M10-T05, M10-T11.

**Allowed Files:**

```text
python/transloka-reconstruction/src/transloka_reconstruction/layout/fallback.py
tests/unit/reconstruction/**
```

**Implementation Requirements:**

```text
wrap
expand box
reduce spacing
reduce font
move block
reflow
next page
add page
manual review
```

**Tests Required:**

* each step;
* minimum font;
* critical unresolved;
* page addition.

**Acceptance Criteria:**

* Teks tidak dipotong.

---

## M10-T16 — Implement Target Page Mapping

**Objective:**
Memetakan source page ke output page.

**Dependencies:**
M10-T10, M10-T15.

**Allowed Files:**

```text
python/transloka-reconstruction/src/transloka_reconstruction/pagination/**
tests/unit/reconstruction/**
```

**Implementation Requirements:**

* one-to-one;
* one-to-many;
* target numbering;
* added page;
* page count changes.

**Tests Required:**

* no change;
* added page;
* split paragraph;
* multiple source to one target if supported.

**Acceptance Criteria:**

* Mapping tersedia untuk export dan link update.

---

## M10-T17 — Implement External Hyperlink Safety

**Objective:**
Mempertahankan link aman.

**Dependencies:**
M10-T06, M10-T10.

**Allowed Files:**

```text
python/transloka-reconstruction/src/transloka_reconstruction/links/**
tests/security/reconstruction/**
```

**Implementation Requirements:**

Allow:

* HTTP;
* HTTPS;
* mailto.

Reject:

* JavaScript;
* file;
* shell;
* data by default.

**Tests Required:**

* each scheme;
* translated label;
* broken link.

**Acceptance Criteria:**

* Link tidak di-fetch selama reconstruction.

---

## M10-T18 — Implement Export Models and Versioning

**Objective:**
Menyimpan export metadata.

**Dependencies:**
M10-T01.

**Allowed Files:**

```text
python/transloka-core/src/transloka_core/database/models/exports.py
infrastructure/migrations/**
tests/integration/database/**
```

**Implementation Requirements:**

* type;
* profile;
* version;
* file;
* checksum;
* status;
* validation report.

**Tests Required:**

* version unique;
* missing file;
* completed requirements.

**Acceptance Criteria:**

* Export lama tidak ditimpa.

---

## M10-T19 — Implement Final PDF Validation

**Objective:**
Memastikan output layak final.

**Dependencies:**
M10-T06, M10-T10, M10-T18.

**Allowed Files:**

```text
python/transloka-quality/src/transloka_quality/pdf/**
tests/integration/reconstruction/**
```

**Implementation Requirements:**

Check:

* can open;
* page count;
* checksum;
* text extraction;
* missing segments;
* active content;
* major images;
* critical warnings;
* source residue.

**Tests Required:**

* valid;
* corrupted;
* missing segment;
* active content;
* blank output.

**Acceptance Criteria:**

* Invalid output tidak menjadi `COMPLETED`.

---

## M10-T20 — Implement Reconstruction API

**Objective:**
Menyediakan readiness, preview, start, status, retry, cancel.

**Dependencies:**
M10-T11, M10-T19, M4-T05.

**Allowed Files:**

```text
services/api/src/transloka_api/routers/reconstruction.py
packages/api-client/**
tests/integration/api/**
```

**Tests Required:**

* readiness;
* start;
* duplicate;
* preview;
* cancel;
* retry page;
* blocking warning.

**Acceptance Criteria:**

* Critical warning dapat memblokir export.

---

## M10-T21 — Build Reconstruction and Export UI

**Objective:**
Mengatur mode, profile, progress, warnings, dan download.

**Dependencies:**
M10-T20.

**Allowed Files:**

```text
apps/web/src/features/reconstruction/**
apps/web/src/features/exports/**
```

**Implementation Requirements:**

* profile;
* settings;
* preview;
* progress;
* warning;
* retry page;
* create export;
* download.

**Tests Required:**

* mode;
* running;
* failed;
* warning;
* download.

**Acceptance Criteria:**

* User dapat memilih `BALANCED` default.

---

# 19. Milestone 11 — Quality, Backup, Recovery, and Hardening

---

## M11-T01 — Implement Unified Warning and Quality Models

**Objective:**
Menyatukan warning dan reports.

**Dependencies:**
M8-T09, M10-T19.

**Allowed Files:**

```text
python/transloka-core/src/transloka_core/database/models/quality.py
python/transloka-quality/**
infrastructure/migrations/**
tests/**
```

**Implementation Requirements:**

* reports;
* checks;
* warnings;
* severity;
* resolution;
* non-overridable critical.

**Tests Required:**

* report;
* warning;
* severity counts;
* resolution;
* critical block.

**Acceptance Criteria:**

* Warning history preserved.

---

## M11-T02 — Build Warning and Quality Dashboard

**Objective:**
Menampilkan quality status proyek.

**Dependencies:**
M11-T01.

**Allowed Files:**

```text
apps/web/src/features/quality/**
```

**Implementation Requirements:**

* filters;
* counts;
* report details;
* navigation to page/segment;
* blocking state.

**Tests Required:**

* severity;
* empty;
* resolved;
* navigation.

**Acceptance Criteria:**

* Critical issue jelas terlihat.

---

## M11-T03 — Implement Backup Models and Manifest

**Objective:**
Mencatat backup dan membuat manifest.

**Dependencies:**
M2-T09.

**Allowed Files:**

```text
python/transloka-core/src/transloka_core/database/models/backups.py
python/transloka-core/src/transloka_core/backup/manifest.py
infrastructure/migrations/**
tests/**
```

**Implementation Requirements:**

* backup type;
* file;
* checksum;
* schema version;
* application version;
* included content.

**Tests Required:**

* manifest;
* invalid checksum;
* missing file;
* version.

**Acceptance Criteria:**

* Backup tidak valid sebelum verification.

---

## M11-T04 — Implement Metadata and Full Project Backup

**Objective:**
Membuat backup lebih lengkap.

**Dependencies:**
M11-T03.

**Allowed Files:**

```text
python/transloka-core/src/transloka_core/backup/**
tests/integration/backup/**
```

**Implementation Requirements:**

Types:

* database only;
* metadata;
* full projects.

Exclude:

* model files;
* temp by default;
* queue DB by default unless documented.

**Tests Required:**

* inclusion;
* exclusion;
* large file list;
* interrupted;
* disk check.

**Acceptance Criteria:**

* Backup contains warning about private data.

---

## M11-T05 — Implement Safe Backup Verification

**Objective:**
Memvalidasi archive tanpa mengekstrak tidak aman.

**Dependencies:**
M11-T04.

**Allowed Files:**

```text
python/transloka-core/src/transloka_core/backup/verification.py
tests/security/backup/**
```

**Implementation Requirements:**

* checksum;
* manifest;
* schema;
* path;
* symlink;
* archive bomb;
* decompressed size;
* DB integrity.

**Tests Required:**

* zip slip;
* symlink;
* bomb;
* corruption;
* missing manifest.

**Acceptance Criteria:**

* Unsafe backup tidak dapat direstore.

---

## M11-T06 — Implement Restore Workflow

**Objective:**
Memulihkan state secara aman.

**Dependencies:**
M11-T05, M4-T06.

**Allowed Files:**

```text
python/transloka-core/src/transloka_core/backup/restore.py
services/api/src/transloka_api/routers/backups.py
tests/recovery/**
```

**Implementation Requirements:**

* confirmation;
* maintenance mode;
* pause worker;
* pre-restore backup;
* temp restore;
* integrity;
* atomic replacement;
* restart checks.

**Tests Required:**

* success;
* invalid archive;
* interrupted;
* pre-backup;
* rollback.

**Acceptance Criteria:**

* Active database tidak diganti sebelum validation lulus.

---

## M11-T07 — Implement Maintenance Services

**Objective:**
Menyediakan integrity, cleanup, orphan scan, dan vacuum.

**Dependencies:**
M11-T01, M3-T02.

**Allowed Files:**

```text
python/transloka-core/src/transloka_core/maintenance/**
services/api/src/transloka_api/routers/maintenance.py
tests/**
```

**Implementation Requirements:**

* DB check;
* file check;
* orphan scan;
* temp cleanup;
* cache cleanup;
* vacuum;
* dry-run.

**Tests Required:**

* protected files;
* orphan;
* missing record;
* active job block;
* dry-run.

**Acceptance Criteria:**

* Cleanup tidak menghapus original atau latest valid export otomatis.

---

## M11-T08 — Build Storage and Backup UI

**Objective:**
Menampilkan storage, backup, restore, dan cleanup.

**Dependencies:**
M11-T04, M11-T06, M11-T07.

**Allowed Files:**

```text
apps/web/src/features/storage/**
apps/web/src/features/backups/**
```

**Implementation Requirements:**

* storage categories;
* backup list;
* create;
* verify;
* restore confirmation;
* cleanup dry-run.

**Tests Required:**

* create;
* verify;
* restore warning;
* cleanup preview.

**Acceptance Criteria:**

* Restore tidak dapat dijalankan tanpa confirmation.

---

## M11-T09 — Complete Full Local Model Benchmark

**Objective:**
Menyediakan benchmark sesuai hardware.

**Dependencies:**
M7-T14.

**Allowed Files:**

```text
python/transloka-translation/src/transloka_translation/benchmark/**
apps/web/src/features/benchmarks/**
tests/**
```

**Implementation Requirements:**

* hardware profile;
* repeated runs;
* batch sizes;
* context;
* RAM;
* VRAM optional;
* quality scoring;
* recommendation;
* human review optional.

**Tests Required:**

* run;
* cancel;
* resume;
* critical failure;
* recommendation.

**Acceptance Criteria:**

* No default model hard-coded.

---

## M11-T10 — Implement Stale Artifact Recovery

**Objective:**
Menangani incomplete page, export, snapshot, dan backup.

**Dependencies:**
M4-T08, M10-T19, M11-T05.

**Allowed Files:**

```text
python/transloka-core/src/transloka_core/recovery/**
tests/recovery/**
```

**Implementation Requirements:**

* temp artifact scan;
* checksum;
* DB state;
* preserve valid prior result;
* remove incomplete;
* report recovery.

**Tests Required:**

* incomplete export;
* stale page;
* incomplete backup;
* valid atomic file.

**Acceptance Criteria:**

* File existence alone tidak berarti complete.

---

## M11-T11 — Complete Security Regression Suite

**Objective:**
Memastikan seluruh critical controls memiliki test.

**Dependencies:**
Seluruh security-related tasks.

**Allowed Files:**

```text
tests/security/**
```

**Implementation Requirements:**

Cover:

* path traversal;
* symlink;
* origin;
* custom header;
* command injection;
* malformed PDF;
* active content;
* prompt injection;
* raw HTML;
* remote WeasyPrint;
* remote Ollama;
* zip slip;
* archive bomb;
* log sanitization.

**Acceptance Criteria:**

* Seluruh critical security test lulus.
* Tidak ada test critical yang skipped.

---

## M11-T12 — Implement Digital PDF End-to-End Test

**Objective:**
Menguji full digital workflow.

**Dependencies:**
M10-T21, M11-T01.

**Allowed Files:**

```text
tests/e2e/digital/**
```

**Implementation Requirements:**

Flow lengkap dari project sampai download export.

Use FakeTranslationProvider untuk CI.

Optional local Ollama variant.

**Acceptance Criteria:**

* Original unchanged.
* Term protected.
* Revision exists.
* Export valid.

---

## M11-T13 — Implement Scanned PDF End-to-End Test

**Objective:**
Menguji full scanned workflow.

**Dependencies:**
M9-T10, M10-T21.

**Allowed Files:**

```text
tests/e2e/scanned/**
```

**Implementation Requirements:**

* import;
* OCR;
* correction;
* glossary;
* translation;
* review;
* reconstruction;
* export.

**Acceptance Criteria:**

* Searchable translated output.
* Raw OCR preserved.
* Original unchanged.

---

## M11-T14 — Implement Backup-Restore End-to-End Test

**Objective:**
Membuktikan state dapat dipulihkan.

**Dependencies:**
M11-T06.

**Allowed Files:**

```text
tests/e2e/backup_restore/**
```

**Implementation Requirements:**

* create complete project;
* backup;
* mutate/delete;
* restore;
* compare state and checksums.

**Acceptance Criteria:**

* Project, revisions, glossary, and export restored.

---

## M11-T15 — Implement Performance Benchmark Suite

**Objective:**
Mengukur resource tanpa menetapkan target universal.

**Dependencies:**
M10-T21.

**Allowed Files:**

```text
tests/performance/**
scripts/benchmark.*
```

**Implementation Requirements:**

Documents:

* 10;
* 50;
* 100;
* 250 pages.

Metrics:

* import;
* extraction;
* OCR;
* translation;
* reconstruction;
* RAM;
* disk;
* query performance.

**Acceptance Criteria:**

* Report mencatat hardware dan settings.
* Tidak membandingkan hardware berbeda secara langsung.

---

## M11-T16 — Complete User Documentation

**Objective:**
Membuat panduan penggunaan Personal MVP.

**Dependencies:**
Seluruh milestone.

**Allowed Files:**

```text
README.md
docs/SETUP.md
docs/USER_GUIDE.md
docs/TROUBLESHOOTING.md
docs/BACKUP_AND_RESTORE.md
docs/MODEL_SELECTION.md
docs/LIMITATIONS.md
```

**Implementation Requirements:**

* prerequisites;
* setup;
* start/stop;
* Ollama;
* OCR;
* workflow;
* backup;
* restore;
* known limitations;
* privacy.

**Acceptance Criteria:**

* Pengguna dapat menjalankan aplikasi tanpa membaca source code.

---

## M11-T17 — Complete Third-Party License Review

**Objective:**
Memperbarui inventory dependency aktual.

**Dependencies:**
Seluruh dependency telah stabil.

**Allowed Files:**

```text
THIRD_PARTY_LICENSES.md
docs/adr/**
```

**Implementation Requirements:**

* package;
* version;
* function;
* license;
* review status;
* distribution implication.

**Acceptance Criteria:**

* PyMuPDF tidak ada.
* Model license dicatat terpisah.

---

## M11-T18 — Run MVP Release Checklist

**Objective:**
Memverifikasi exit criteria.

**Dependencies:**
M11-T01 sampai M11-T17.

**Allowed Files:**

```text
docs/releases/PERSONAL_MVP_RELEASE_CHECKLIST.md
```

**Implementation Requirements:**

Record:

* commands;
* test results;
* defects;
* model benchmark;
* hardware;
* known limitations;
* backup verification;
* rollback tag.

**Acceptance Criteria:**

* No Critical defect.
* No blocking High defect.
* Digital, scanned, and restore E2E pass.
* Security suite pass.
* Original checksum invariant pass.

---

# 20. Task Dependency Summary

```text
M0-T01
├── M0-T02
├── M0-T03
├── M0-T05
└── M0-T07

M0-T02 + M0-T03
└── M0-T04
└── M0-T06

M1 Foundation
└── M2 Database
    ├── M3 Import
    └── M4 Jobs

M3 + M4
└── M5 Document IR
    └── M6 Glossary
        └── M7 Translation
            └── M8 Review
                ├── M9 OCR
                └── M10 Reconstruction
                    └── M11 Hardening
```

---

# 21. Recommended Initial Codex Task Order

Urutan pertama yang harus diberikan kepada Codex:

```text
1. M0-T01 — Create Repository Structure
2. M0-T02 — Configure Node Workspace
3. M0-T03 — Configure Python Workspace
4. M0-T04 — Configure Formatting, Linting, and Type Checking
5. M0-T05 — Configure Git Ignore and Environment Template
6. M0-T06 — Add License and Third-Party Inventory
7. M0-T07 — Add Documentation Index
8. M1-T01 — Bootstrap Next.js Application
9. M1-T02 — Bootstrap FastAPI Application
10. M1-T03 — Implement Request ID and Error Normalization
11. M1-T04 — Implement Localhost Binding Guard
12. M1-T05 — Configure CORS and Origin Validation
13. M1-T06 — Require TransLoka Client Headers
14. M1-T07 — Create Worker Entrypoint and Heartbeat
15. M1-T08 — Create Windows Startup and Stop Scripts
16. M1-T09 — Build System Health Page
17. M1-T10 — Generate OpenAPI TypeScript Client
```

---

# 22. Task Merge Rules

Task dapat digabung hanya jika:

1. Dependency sama.
2. File scope sangat beririsan.
3. Total perubahan tetap kecil.
4. Acceptance criteria tetap terpisah.
5. Test tiap requirement tetap tersedia.

Contoh yang mungkin digabung:

```text
M0-T05 + M0-T06
```

Contoh yang tidak boleh digabung:

```text
M3-T03 Streaming Upload
+
M7-T10 Translation Orchestration
```

---

# 23. Task Split Rules

Task wajib dipecah jika:

* menyentuh lebih dari satu subsystem besar;
* memerlukan migration dan UI kompleks sekaligus;
* memiliki lebih dari satu business objective;
* sulit direview;
* test menjadi sangat luas;
* dapat menyebabkan perubahan lebih dari satu milestone.

Codex harus mengusulkan split, bukan memperluas task sendiri.

---

# 24. File Scope Rules

`Allowed Files` berarti Codex boleh mengubah file tersebut dan file pendukung yang benar-benar diperlukan.

Jika perlu mengubah file di luar scope:

1. Jelaskan kebutuhan.
2. Jangan mengubah sebelum approval.
3. Kecuali perubahan mekanis wajib seperti lockfile akibat dependency yang telah disetujui.

Dilarang menggunakan alasan “cleanup” untuk refactor area yang tidak terkait.

---

# 25. Migration Task Rules

Task yang menambah schema wajib:

* membuat Alembic migration;
* memperbarui SQLAlchemy model;
* menambah migration test;
* menguji empty database;
* menguji upgrade fixture;
* tidak menghapus data tanpa backup.

---

# 26. API Task Rules

Task API wajib:

* menggunakan generated schema;
* menambahkan operation ID;
* menambahkan response type;
* menambahkan normalized errors;
* menambahkan contract test;
* memperbarui generated TypeScript client.

---

# 27. Frontend Task Rules

Task frontend wajib:

* menggunakan generated API client;
* memiliki loading state;
* memiliki empty state jika relevan;
* memiliki error state;
* tidak menggunakan raw HTML;
* menjaga accessibility dasar;
* tidak menyimpan document content ke browser persistent storage tanpa requirement.

---

# 28. AI Task Rules

Task AI wajib:

* menggunakan provider adapter;
* menggunakan local Ollama;
* source dianggap data;
* structured output;
* deterministic validation;
* no tool access;
* no shell;
* no filesystem action;
* no automatic remote fallback.

---

# 29. PDF Task Rules

Task PDF wajib:

* tidak menggunakan PyMuPDF;
* original read-only;
* artifact derivative;
* checksum source;
* controlled temporary file;
* parser error handling;
* golden fixture test.

---

# 30. Security Task Rules

Security task tidak boleh dianggap selesai hanya dengan komentar atau validation di frontend.

Control harus diterapkan pada backend atau core layer.

Contoh:

```text
Safe filename di frontend saja = tidak cukup.
Path containment pada storage service = wajib.
```

---

# 31. Test Failure Rule

Jika targeted test menemukan bug lama:

1. Catat test dan bug.
2. Tentukan apakah bug memblokir task.
3. Jangan menghapus test.
4. Jangan menandai task complete.
5. Perbaiki hanya jika masih dalam scope atau minta task baru.

---

# 32. Deferred Task Register

Task berikut tidak boleh dibuat dalam Personal MVP backlog aktif:

```text
Desktop installer
Authentication
User accounts
Cloud deployment
Cloud storage
OpenAI provider
Payment
Advertisement
EPUB
DOCX
Text-in-image replacement
Advanced complex-table recreation
Real-time collaboration
```

---

# 33. MVP Completion Mapping

| MVP Capability     | Primary Tasks   |
| ------------------ | --------------- |
| Local startup      | M1-T01–M1-T09   |
| Project management | M2-T05–M2-T07   |
| PDF import         | M3-T01–M3-T05   |
| PDF analysis       | M3-T06–M3-T11   |
| Background jobs    | M4-T01–M4-T09   |
| Document IR        | M5-T01–M5-T11   |
| Glossary           | M6-T01–M6-T12   |
| Local translation  | M7-T01–M7-T14   |
| Review editor      | M8-T01–M8-T11   |
| OCR                | M9-T01–M9-T10   |
| Reconstruction     | M10-T01–M10-T17 |
| Export             | M10-T18–M10-T21 |
| Backup and restore | M11-T03–M11-T08 |
| Full validation    | M11-T11–M11-T18 |

---

# 34. Definition of Ready for Codex

Sebuah task siap diberikan kepada Codex jika:

1. Semua dependency berstatus `COMPLETED`.
2. Repository state bersih atau perubahan aktif diketahui.
3. Requirement sources tersedia.
4. Allowed files jelas.
5. Acceptance criteria jelas.
6. Test requirements jelas.
7. Hardware dependency tersedia jika diperlukan.
8. Tidak ada unresolved conflict.

---

# 35. Definition of Done for Codex Task

Task berstatus `COMPLETED` hanya jika:

* implementation lengkap;
* test ditambahkan;
* targeted test lulus;
* lint lulus;
* type checking lulus;
* migration lulus jika ada;
* security requirement terpenuhi;
* no out-of-scope change;
* no hidden assumption;
* completion report diberikan.

---

# 36. Definition of Done

`CODEX_TASKS.md` dianggap selesai apabila:

* seluruh milestone telah dipecah menjadi task atomik;
* setiap task memiliki dependency;
* setiap task memiliki file scope;
* setiap task memiliki implementation requirement;
* setiap task memiliki security requirement yang relevan;
* setiap task memiliki test requirement;
* setiap task memiliki acceptance criteria;
* urutan awal Codex tersedia;
* task merge dan split rules tersedia;
* deferred features tidak masuk backlog aktif;
* Codex dapat mulai dari `M0-T01` tanpa menebak scope proyek.
