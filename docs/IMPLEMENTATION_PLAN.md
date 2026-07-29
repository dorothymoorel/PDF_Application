# IMPLEMENTATION PLAN

## TransLoka Personal MVP Technical Delivery Plan

**Document Name:** `IMPLEMENTATION_PLAN.md`
**Document Version:** 0.1
**Status:** Draft
**Decision Date:** 2026-07-26
**Application Mode:** Local-First, Single User
**Primary Platform:** Windows
**Primary Input:** PDF
**Primary Output:** Translated PDF
**Primary Language Pair:** English → Bahasa Indonesia
**Implementation Executor:** Project Owner with Codex assistance

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

---

# 1. Purpose

Dokumen ini menetapkan urutan pembangunan TransLoka Personal MVP.

Tujuan dokumen:

* memecah proyek menjadi milestone yang dapat diuji;
* menentukan dependency antarmilestone;
* membatasi ruang perubahan Codex;
* memastikan setiap milestone menghasilkan aplikasi yang tetap dapat dijalankan;
* mencegah implementasi fitur sebelum fondasinya siap;
* menyediakan quality gate;
* menyediakan rollback point;
* menetapkan bukti penyelesaian;
* menghubungkan requirement ke deliverable;
* menghindari satu perubahan besar yang sulit ditinjau.

---

# 2. Implementation Principles

## 2.1 Build Vertically

Pembangunan dilakukan melalui vertical slice yang dapat dijalankan.

Contoh:

```text
Project creation
→ database
→ API
→ frontend
→ test
```

Bukan:

```text
Membuat seluruh database
→ seluruh API
→ seluruh frontend
→ baru menguji
```

## 2.2 One Milestone at a Time

Codex tidak boleh mengerjakan milestone berikutnya sebelum quality gate milestone aktif lulus.

## 2.3 Atomic Tasks

Setiap task harus:

* memiliki satu tujuan utama;
* memiliki scope file terbatas;
* memiliki acceptance criteria;
* memiliki test;
* dapat di-review;
* dapat di-rollback.

## 2.4 Runnable at Every Stage

Repository harus tetap:

* dapat di-install;
* dapat di-lint;
* dapat di-type-check;
* dapat menjalankan test;
* dapat menjalankan komponen yang telah selesai.

## 2.5 Security by Construction

Security tidak ditambahkan pada akhir proyek.

Control keamanan diterapkan pada milestone tempat risiko muncul.

## 2.6 Tests Are Deliverables

Task tidak selesai jika implementasi tersedia tetapi test belum ada.

## 2.7 No Silent Assumption

Asumsi baru harus:

* dicatat;
* dijelaskan;
* tidak bertentangan dengan dokumen;
* tidak mengubah scope tanpa persetujuan.

## 2.8 Local-First Is Mandatory

Setiap milestone harus mempertahankan:

```text
No paid service
No required cloud
No public network exposure
No automatic data upload
```

---

# 3. Implementation Strategy

TransLoka dibangun dalam sebelas milestone utama:

```text
M0  Repository Preparation
M1  Local Application Foundation
M2  Database, Settings, and Projects
M3  File Import and Document Analysis
M4  Background Job System
M5  Document IR and Editor Foundation
M6  Glossary and Protected Content
M7  Local Translation Pipeline
M8  Review Editor
M9  OCR and Scanned Documents
M10 Reconstruction and Export
M11 Quality, Backup, Recovery, and MVP Hardening
```

---

# 4. Dependency Graph

```text
M0
│
▼
M1
│
▼
M2
├───────────────┐
▼               ▼
M3              M4
└───────┬───────┘
        ▼
        M5
        │
        ▼
        M6
        │
        ▼
        M7
        │
        ▼
        M8
        │
        ▼
        M9
        │
        ▼
        M10
        │
        ▼
        M11
```

M3 dan M4 dapat dikembangkan berurutan atau dalam branch terpisah, tetapi keduanya harus selesai sebelum M5.

---

# 5. Repository and Branch Strategy

## 5.1 Main Branch

Gunakan:

```text
main
```

`main` harus selalu:

* dapat di-install;
* dapat menjalankan fast test;
* tidak memiliki lint error;
* tidak memiliki type error;
* tidak berisi partial critical implementation.

## 5.2 Milestone Branch

Format:

```text
milestone/m01-foundation
milestone/m02-local-data
milestone/m03-pdf-import
```

## 5.3 Task Branch

Format:

```text
task/m02-t03-project-repository
task/m07-t05-placeholder-restoration
```

## 5.4 Commit Policy

Commit harus:

* memiliki satu tujuan;
* tidak mencampur refactor besar dan fitur;
* tidak memasukkan secret;
* tidak memasukkan model file;
* tidak memasukkan dokumen pengguna;
* tidak memasukkan generated cache.

Contoh:

```text
feat(projects): add project repository and migration
test(glossary): cover longest phrase matching
fix(storage): block symlink traversal
```

---

# 6. Required Repository Files

Sebelum implementasi fitur:

```text
README.md
CONTRIBUTING.md
LICENSE
THIRD_PARTY_LICENSES.md
.env.example
.gitignore
.editorconfig
.nvmrc
.node-version
.python-version
pnpm-workspace.yaml
package.json
pyproject.toml
pnpm-lock.yaml
uv.lock
```

Dokumen proyek berada pada:

```text
docs/
```

---

# 7. Global Definition of Done

Sebuah task dianggap selesai apabila:

1. Requirement telah diterapkan.
2. Tidak melanggar `MVP_SCOPE.md`.
3. Tidak menambah layanan berbayar.
4. Tidak membuka akses jaringan.
5. Code dapat dikompilasi.
6. Lint lulus.
7. Type checking lulus.
8. Test baru tersedia.
9. Test lama tetap lulus.
10. Error state ditangani.
11. Logging tidak membocorkan data.
12. Dokumentasi terkait diperbarui jika diperlukan.
13. Tidak ada `TODO` pada critical path.
14. Tidak ada mock pada production path.
15. Acceptance criteria task terpenuhi.

---

# 8. Global Quality Commands

## Python

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy .
uv run pytest -m "not slow and not requires_ollama and not requires_gpu"
```

## Frontend

```bash
pnpm lint
pnpm typecheck
pnpm test
```

## End-to-End

```bash
pnpm e2e
```

## Dependency Verification

```bash
uv sync --locked
pnpm install --frozen-lockfile
```

---

# 9. Milestone 0 — Repository Preparation

## 9.1 Objective

Membuat repository yang terstruktur, reproducible, dan siap digunakan Codex.

## 9.2 Dependencies

Tidak ada.

## 9.3 Scope

* monorepo structure;
* pnpm workspace;
* uv workspace;
* base configuration;
* documentation index;
* dependency locking;
* Git configuration;
* code ownership conventions.

## 9.4 Tasks

### M0-T01 — Create Repository Structure

Buat:

```text
apps/web
services/api
services/worker
python/
packages/
infrastructure/
scripts/
tests/
docs/
```

### M0-T02 — Configure Node Workspace

* root `package.json`;
* `pnpm-workspace.yaml`;
* Node version files;
* root scripts.

### M0-T03 — Configure Python Workspace

* root `pyproject.toml`;
* uv workspace;
* Python version;
* initial package structure.

### M0-T04 — Configure Formatting and Linting

* Ruff;
* mypy;
* ESLint;
* TypeScript;
* EditorConfig.

### M0-T05 — Configure Git Ignore

Ignore:

```text
.env
node_modules
.venv
__pycache__
.pytest_cache
.mypy_cache
.next
dist
coverage
transloka-data
models
*.db
*.db-wal
*.db-shm
```

### M0-T06 — Add License Inventory

Buat:

```text
THIRD_PARTY_LICENSES.md
```

### M0-T07 — Add Documentation Index

Buat `docs/README.md` yang menjelaskan urutan authority dokumen.

## 9.5 Deliverables

* repository dapat di-clone;
* dependency dapat di-install;
* lint runner tersedia;
* test runner tersedia;
* workspace terdeteksi.

## 9.6 Quality Gate

```text
pnpm install --frozen-lockfile
uv sync --locked
pnpm lint
pnpm typecheck
uv run ruff check .
uv run mypy .
```

## 9.7 Exit Criteria

* workspace valid;
* tidak ada dependency cloud wajib;
* tidak ada secret;
* seluruh dokumen berada dalam `docs/`;
* root scripts tersedia.

---

# 10. Milestone 1 — Local Application Foundation

## 10.1 Objective

Menyediakan frontend, backend, worker placeholder nyata, local startup, dan health monitoring.

## 10.2 Dependencies

Milestone 0.

## 10.3 Scope

* Next.js;
* FastAPI;
* worker process;
* configuration;
* localhost binding;
* health endpoint;
* startup scripts;
* request ID;
* error envelope;
* CORS.

## 10.4 Tasks

### M1-T01 — Bootstrap Next.js Application

Implementasikan:

* App Router;
* TypeScript strict;
* base layout;
* application shell;
* health screen placeholder.

### M1-T02 — Bootstrap FastAPI Application

Implementasikan:

* application factory;
* configuration;
* `/health`;
* `/api/v1/system/health`;
* request ID middleware;
* normalized errors.

### M1-T03 — Configure Localhost Binding

Default:

```text
Frontend: 127.0.0.1:3000
Backend:  127.0.0.1:8000
```

Block non-loopback bind tanpa override.

### M1-T04 — Configure CORS and Origin Validation

Allowed:

```text
http://127.0.0.1:3000
http://localhost:3000
```

### M1-T05 — Require Client Headers

Implementasikan:

```text
X-TransLoka-Client
X-TransLoka-Client-Version
```

### M1-T06 — Create Worker Entrypoint

Worker belum menjalankan heavy task, tetapi harus:

* start;
* emit heartbeat;
* stop cleanly;
* memiliki health state.

### M1-T07 — Create Startup Scripts

Windows:

```text
scripts/setup-local.ps1
scripts/start.ps1
scripts/stop.ps1
```

Optional:

```text
setup-local.sh
start.sh
stop.sh
```

### M1-T08 — Build System Health UI

Tampilkan:

* API;
* worker;
* database placeholder;
* filesystem;
* Ollama;
* OCR.

### M1-T09 — Generate Initial OpenAPI Client

Buat alur:

```text
FastAPI OpenAPI
→ packages/api-client
→ frontend import
```

## 10.5 Deliverables

* frontend dapat dibuka;
* API dapat diakses;
* health screen bekerja;
* worker dapat start;
* origin asing ditolak;
* generated API client tersedia.

## 10.6 Tests

* health endpoint;
* request ID;
* normalized error;
* origin rejection;
* missing client header;
* localhost bind;
* frontend health component;
* startup smoke test.

## 10.7 Quality Gate

* full fast quality commands lulus;
* browser dapat membuka dashboard;
* backend tidak bind ke `0.0.0.0`;
* mutation tanpa client header ditolak.

## 10.8 Rollback Point

Tag:

```text
m01-foundation-complete
```

---

# 11. Milestone 2 — Database, Settings, and Projects

## 11.1 Objective

Membangun persistence lokal, migration, settings, project CRUD, dan data directory.

## 11.2 Dependencies

Milestone 1.

## 11.3 Scope

* SQLite;
* SQLAlchemy;
* Alembic;
* WAL;
* app settings;
* project models;
* repository;
* service;
* project API;
* project UI;
* integrity check.

## 11.4 Tasks

### M2-T01 — Configure Data Directory

Implementasikan:

* `TRANSLOKA_DATA_DIR`;
* OS-aware default;
* directory validation;
* write test;
* free-space check.

### M2-T02 — Configure SQLite Engine

Implementasikan pragmas:

```sql
foreign_keys = ON
journal_mode = WAL
busy_timeout = 5000
synchronous = NORMAL
```

### M2-T03 — Configure Alembic

* migration environment;
* revision naming;
* startup migration command;
* migration tests.

### M2-T04 — Implement Application Tables

* `app_metadata`;
* `app_settings`.

### M2-T05 — Implement Project Table

* SQLAlchemy model;
* Pydantic schema;
* repository;
* service;
* state enum.

### M2-T06 — Implement Project API

* create;
* list;
* get;
* update;
* archive;
* unarchive.

### M2-T07 — Implement Project Frontend

* dashboard;
* create form;
* project card;
* empty state;
* archive state.

### M2-T08 — Implement Optimistic Locking Foundation

Digunakan pada settings dan entity yang memiliki revision.

### M2-T09 — Implement Database Integrity CLI

```bash
uv run transloka db integrity-check
```

### M2-T10 — Implement Basic Backup

Database-only backup menggunakan SQLite backup mechanism.

## 11.5 Deliverables

* project tersimpan setelah restart;
* SQLite WAL aktif;
* migration berjalan;
* project CRUD lengkap;
* database backup dasar tersedia.

## 11.6 Tests

* migration empty database;
* foreign key;
* WAL;
* project CRUD;
* invalid project state;
* settings allowlist;
* backup opens;
* application restart persistence.

## 11.7 Quality Gate

* database dapat dibuat dari kosong;
* project tetap ada setelah restart;
* migration test lulus;
* backup dapat diverifikasi;
* absolute path tidak dikembalikan API.

## 11.8 Rollback Point

Tag:

```text
m02-local-data-complete
```

---

# 12. Milestone 3 — File Import and Document Analysis

## 12.1 Objective

Memungkinkan pengguna memasukkan PDF secara aman dan menghasilkan analisis dasar.

## 12.2 Dependencies

Milestone 2.

## 12.3 Scope

* stored files;
* document records;
* PDF upload;
* validation;
* checksum;
* immutable original;
* basic PDF metadata;
* page records;
* page render;
* thumbnails;
* analysis UI.

## 12.4 Tasks

### M3-T01 — Implement Stored File Model

* relative storage key;
* file role;
* checksum;
* immutable flag;
* status.

### M3-T02 — Implement LocalFileStorage

Methods:

* write temporary;
* commit original;
* open;
* delete controlled;
* calculate checksum;
* verify path.

### M3-T03 — Implement Streaming PDF Import

* multipart upload;
* size enforcement;
* temporary file;
* cleanup on failure.

### M3-T04 — Implement File Validation

* extension;
* MIME;
* magic bytes;
* corruption;
* encryption;
* page limit;
* disk estimate.

### M3-T05 — Implement Original File Immutability

* read-only policy;
* checksum;
* no overwrite;
* derivative-only output.

### M3-T06 — Implement Document Model

* metadata;
* class;
* page count;
* scanned estimate;
* status.

### M3-T07 — Implement Basic PDF Analysis

Gunakan:

* pypdf;
* pdfplumber;
* pypdfium2.

### M3-T08 — Implement Page Model

* dimensions;
* rotation;
* source page number;
* page type;
* render references.

### M3-T09 — Implement Thumbnail and Render Generation

* safe DPI;
* WebP thumbnail;
* page image cache.

### M3-T10 — Implement Import and Analysis UI

* file picker;
* validation errors;
* progress;
* document summary;
* page thumbnails.

### M3-T11 — Detect Active PDF Content

* JavaScript;
* attachment;
* unsafe link scheme;
* warning records.

## 12.5 Deliverables

* PDF dapat diimpor;
* original aman;
* metadata muncul;
* page thumbnails tersedia;
* invalid PDF ditolak.

## 12.6 Tests

* valid PDF;
* fake extension;
* wrong magic;
* corrupted;
* password protected;
* oversized;
* page limit;
* filename injection;
* path traversal;
* embedded JavaScript;
* immutable checksum.

## 12.7 Quality Gate

* original checksum sebelum dan sesudah sama;
* malformed PDF tidak mematikan API;
* thumbnails tersedia;
* active content tidak dijalankan;
* binary tidak disimpan di SQLite.

## 12.8 Rollback Point

Tag:

```text
m03-pdf-import-complete
```

---

# 13. Milestone 4 — Background Job System

## 13.1 Objective

Membangun task execution lokal yang persist, dapat dipantau, dibatalkan, dan dipulihkan.

## 13.2 Dependencies

Milestone 2. M4-T01 dapat diselesaikan sebelum atau sesudah Milestone 3, tetapi M4-T02 bergantung pada M3-T06 karena `application_jobs.document_id` mereferensikan document.

## 13.3 Scope

* Huey;
* `SqliteHuey`;
* application job records;
* job attempts;
* heartbeat;
* progress;
* cancellation;
* retry;
* stale recovery;
* idempotency.

## 13.4 Tasks

### M4-T01 — Configure Huey

Queue database:

```text
database/tasks.db
```

### M4-T02 — Implement Application Job Model

* type;
* status;
* progress;
* stage;
* error;
* timestamps.
* closed allowlist untuk job type dan attempt status mengikuti [DATABASE_SCHEMA.md](DATABASE_SCHEMA.md) dan [API_CONTRACT.md](API_CONTRACT.md).

### M4-T03 — Implement Task Dispatch Service

API tidak memanggil task implementation langsung.

### M4-T04 — Implement Job Status API

* get;
* list;
* attempts;
* poll hint.

### M4-T05 — Implement Progress Update

Worker memperbarui:

* progress;
* current stage;
* heartbeat.

### M4-T06 — Implement Cancellation

* cancellation request;
* cooperative check;
* cleanup incomplete output.

### M4-T07 — Implement Retry

* retry failed items;
* new attempt;
* bounded retries.

### M4-T08 — Implement Idempotency

* operation key;
* existing job reuse;
* no duplicate output.

### M4-T09 — Implement Stale Job Recovery

Pada startup:

* detect stale;
* inspect output;
* mark stale;
* allow retry.

### M4-T10 — Implement Job UI

* progress bar;
* stage;
* error;
* cancel;
* retry.

## 13.5 Deliverables

* long task tidak memblokir API;
* job dapat dipolling;
* worker restart dapat dipulihkan;
* duplicate action tidak membuat job ganda.

## 13.6 Tests

* state transition;
* heartbeat;
* cancellation;
* retry;
* idempotency;
* worker crash;
* stale recovery;
* duplicate dispatch;
* invalid transition.

## 13.7 Quality Gate

* semua process panjang menggunakan job;
* API tetap responsif;
* retry tidak menggandakan hasil;
* cancelled output tidak dianggap final.

## 13.8 Rollback Point

Tag:

```text
m04-jobs-complete
```

---

# 14. Milestone 5 — Document IR and Editor Foundation

## 14.1 Objective

Mengubah hasil analysis menjadi struktur dokumen yang dapat diterjemahkan dan ditampilkan di editor.

## 14.2 Dependencies

Milestone 3 dan Milestone 4.

## 14.3 Scope

* sections;
* blocks;
* segments;
* assets;
* tables;
* relationships;
* reading order;
* source geometry;
* Document IR serialization;
* page editor view.

## 14.4 Tasks

### M5-T01 — Implement Document IR Models

Pydantic dan domain models untuk:

* Document;
* Page;
* Section;
* Block;
* Segment;
* Asset;
* Table;
* Cell;
* Relationship;
* Warning.

### M5-T02 — Implement Database Tables

Migration untuk struktur Document IR.

### M5-T03 — Implement Digital Text Extraction

* characters;
* words;
* lines;
* block candidates;
* geometry.

### M5-T04 — Implement Reading Order

Minimum:

* single-column;
* two-column;
* header;
* body;
* footer.

### M5-T05 — Implement Block Classification

Minimum:

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
* page number.

### M5-T06 — Implement Segmentation

* sentence;
* paragraph;
* heading;
* list item;
* table cell;
* caption.

### M5-T07 — Implement Asset Extraction

* image;
* geometry;
* file reference;
* caption relationship.

### M5-T08 — Implement Simple Table Extraction

* row;
* column;
* cell;
* header candidate.

### M5-T09 — Implement IR Snapshot

* JSON serialization;
* version;
* checksum;
* storage file.

### M5-T10 — Implement Page Editor View API

Mengembalikan:

* page;
* blocks;
* segments;
* warnings;
* geometry.

### M5-T11 — Implement Source Page Editor UI

* PDF preview;
* block overlay;
* segment list;
* page navigation.

## 14.5 Deliverables

* PDF digital menghasilkan IR;
* segment memiliki stable ID;
* page editor dapat dibuka;
* source order dapat ditelusuri.

## 14.6 Tests

* IR invariant;
* round trip;
* geometry;
* reading order;
* segmentation;
* assets;
* table cells;
* snapshot checksum;
* multi-column fixture.

## 14.7 Quality Gate

* semua required segment dapat dilacak ke page dan block;
* source text tidak berubah;
* IR dapat di-export dan di-import;
* editor menampilkan block sesuai geometry.

## 14.8 Rollback Point

Tag:

```text
m05-document-ir-complete
```

---

# 15. Milestone 6 — Glossary and Protected Content

## 15.1 Objective

Membangun kontrol terminology sebelum translation.

## 15.2 Dependencies

Milestone 5.

## 15.3 Scope

* glossary CRUD;
* glossary terms;
* matching;
* priority;
* occurrence;
* candidates;
* conflict;
* snapshots;
* placeholders;
* impact analysis.

## 15.4 Tasks

### M6-T01 — Implement Glossary Database Models

* glossaries;
* terms;
* revisions;
* snapshots;
* occurrences;
* candidates;
* conflicts.

### M6-T02 — Implement Glossary API

* create;
* list;
* update;
* deactivate;
* terms CRUD.

### M6-T03 — Implement Matching Engine

* exact;
* phrase;
* case-insensitive;
* whole-word;
* longest-match.

### M6-T04 — Implement Priority Resolution

Minimum scope:

```text
SEGMENT
SECTION
DOCUMENT
PROJECT
```

### M6-T05 — Implement Placeholder Generator

Format:

```text
__TLK_<TYPE>_<NUMBER>_<CHECK>__
```

### M6-T06 — Implement Protected Item Detection

* term;
* URL;
* code;
* email;
* endpoint;
* path;
* citation;
* acronym.

### M6-T07 — Implement Placeholder Restoration

Strict inventory validation.

### M6-T08 — Implement Term Candidate Detection

* repeated phrase;
* named entity;
* technical identifier.

### M6-T09 — Implement Conflict Detection

Tidak memilih rule secara acak.

### M6-T10 — Implement Glossary Snapshot

Snapshot immutable dan digunakan oleh translation batch.

### M6-T11 — Implement Glossary UI

* terms;
* candidates;
* conflicts;
* occurrences;
* create/edit.

### M6-T12 — Implement Impact Analysis

* affected segments;
* approved;
* locked;
* safe replacement;
* retranslation required.

## 15.5 Deliverables

* pengguna dapat menetapkan `workflow` tetap asli;
* occurrence dapat dilihat;
* placeholders aman;
* snapshot immutable tersedia.

## 15.6 Tests

* longest match;
* priority;
* case;
* overlap;
* duplicate term;
* conflict;
* placeholder collision;
* missing placeholder;
* duplicate placeholder;
* snapshot immutability.

## 15.7 Quality Gate

* protected term tidak dapat berubah tanpa warning;
* restoration mismatch menghasilkan critical failure;
* snapshot digunakan pada batch;
* glossary revision tersedia.

## 15.8 Rollback Point

Tag:

```text
m06-glossary-complete
```

---

# 16. Milestone 7 — Local Translation Pipeline

## 16.1 Objective

Menerjemahkan segment melalui model Ollama lokal dengan validation dan retry.

## 16.2 Dependencies

Milestone 6.

## 16.3 Scope

* Ollama health;
* model detection;
* model selection;
* provider adapter;
* prompt;
* structured output;
* batching;
* context;
* validation;
* retries;
* status;
* benchmark quick test.

## 16.4 Tasks

### M7-T01 — Implement Translation Provider Interface

Implementasi:

```text
FakeTranslationProvider
OllamaTranslationProvider
```

### M7-T02 — Implement Ollama Health and Model Listing

* health;
* version;
* installed models;
* local endpoint validation.

### M7-T03 — Implement Model Selection

* translation role;
* validation role optional;
* persist selection.

### M7-T04 — Implement Translation Request Schema

* segments;
* context;
* glossary snapshot;
* placeholders;
* style;
* output schema.

### M7-T05 — Implement Prompt Builder

Prompt versioned dan source diperlakukan sebagai data.

### M7-T06 — Implement Batch Builder

* source size;
* batch size;
* context;
* order;
* locked segment exclusion.

### M7-T07 — Implement Structured Response Parser

* valid JSON;
* known segment IDs;
* no duplicate;
* no missing segment.

### M7-T08 — Implement Deterministic Validators

* placeholder;
* number;
* URL;
* code;
* citation;
* language;
* length.

### M7-T09 — Implement Retry Hierarchy

```text
same batch
→ smaller batch
→ isolated segment
→ reduced context
→ manual review
```

### M7-T10 — Implement Translation Persistence

* batch;
* attempt;
* segment translation;
* validation;
* revision.

### M7-T11 — Implement Translation Readiness

Block jika:

* no model;
* glossary conflict;
* unresolved source;
* Ollama unavailable.

### M7-T12 — Implement Translation Start, Status, Cancel

API dan frontend.

### M7-T13 — Implement Quick Model Test

* structured output;
* placeholder;
* latency snapshot.

### M7-T14 — Implement Prompt Injection Tests

Dokumen instruction tidak boleh menjadi command.

## 16.5 Deliverables

* model lokal dapat dipilih;
* translation dapat dijalankan;
* hasil tersimpan;
* validation tersedia;
* failed batch dapat di-retry.

## 16.6 Tests

* provider contract;
* fake scenarios;
* invalid JSON;
* missing segment;
* duplicate segment;
* placeholder mismatch;
* prompt injection;
* timeout;
* cancellation;
* idempotency;
* retry.

## 16.7 Quality Gate

* test standar tidak membutuhkan Ollama;
* Ollama integration test lulus pada hardware lokal;
* model output tidak dapat menjalankan action;
* protected content tetap;
* successful result tidak digandakan.

## 16.8 Rollback Point

Tag:

```text
m07-translation-complete
```

---

# 17. Milestone 8 — Review Editor

## 17.1 Objective

Memungkinkan pengguna meninjau, mengedit, menyetujui, dan mengunci translation.

## 17.2 Dependencies

Milestone 7.

## 17.3 Scope

* side-by-side editor;
* source context;
* translation edit;
* revision;
* approval;
* locking;
* warnings;
* search;
* review queue;
* bulk actions dasar.

## 17.4 Tasks

### M8-T01 — Build Side-by-Side Layout

Panel:

* source page;
* source segment;
* translation editor;
* glossary;
* warnings.

### M8-T02 — Implement Segment Editing

* local draft;
* save;
* optimistic locking;
* conflict dialog.

### M8-T03 — Implement Revisions

* list;
* inspect;
* restore;
* revision type.

### M8-T04 — Implement Approval

* approve;
* unapprove;
* approval state.

### M8-T05 — Implement Locking

* lock;
* unlock;
* prevent edit;
* prevent retranslation.

### M8-T06 — Implement Review Queue

Filters:

* warning;
* confidence;
* unreviewed;
* page;
* section.

### M8-T07 — Implement Surrounding Context

* heading;
* previous segment;
* next segment;
* section summary.

### M8-T08 — Implement Warning Resolution

* fixed;
* accepted;
* false positive.

### M8-T09 — Implement Segment Search

Source dan translation.

### M8-T10 — Implement Basic Bulk Actions

* approve;
* lock;
* retranslate selected.

### M8-T11 — Implement Unsaved Change Protection

* navigation warning;
* page change warning;
* refresh handling.

### M8-T12 — Accessibility Pass

* keyboard;
* focus;
* labels;
* non-color warning state.

## 17.5 Deliverables

* translation dapat diedit;
* revision history tersedia;
* approved segment terlindungi;
* review queue dapat digunakan.

## 17.6 Tests

* edit;
* revision;
* restore;
* approval;
* lock;
* conflict;
* unsaved state;
* bulk action;
* keyboard navigation;
* accessibility basics.

## 17.7 Quality Gate

* approved translation tidak tertimpa;
* locked segment tidak dapat diubah;
* stale edit menghasilkan conflict;
* setiap edit memiliki revision.

## 17.8 Rollback Point

Tag:

```text
m08-review-editor-complete
```

---

# 18. Milestone 9 — OCR and Scanned Documents

## 18.1 Objective

Mendukung scanned PDF dan halaman hybrid melalui OCR lokal.

## 18.2 Dependencies

Milestone 5 dan Milestone 8.

## 18.3 Scope

* PaddleOCR adapter;
* OCR health;
* page selection;
* OCR output;
* geometry;
* confidence;
* raw result;
* source correction;
* scanned E2E.

## 18.4 Tasks

### M9-T01 — Implement OCR Provider Interface

Implementasi:

```text
FakeOCRProvider
PaddleOCRProvider
```

### M9-T02 — Implement OCR Health Check

* dependency;
* model;
* CPU/GPU mode;
* cache.

### M9-T03 — Implement Scanned Page Detection

* no text layer;
* poor native extraction;
* image-dominant page.

### M9-T04 — Implement OCR Job

* page render;
* OCR;
* geometry;
* confidence;
* progress.

### M9-T05 — Implement OCR Normalization

* whitespace;
* line merge;
* hyphenation;
* reading order.

### M9-T06 — Implement OCR Source Resolution

Store separately:

* raw OCR;
* resolved source;
* manual correction.

### M9-T07 — Implement OCR Correction UI

* source comparison;
* edit;
* save;
* invalidate downstream translation by policy.

### M9-T08 — Implement Table OCR Mapping

Minimum simple table support.

### M9-T09 — Implement OCR Warnings

* low confidence;
* unrecognized block;
* possible text in image;
* reading-order uncertainty.

### M9-T10 — Implement Scanned PDF E2E

Import sampai export.

## 18.5 Deliverables

* scanned page menghasilkan segment;
* correction tersimpan;
* raw OCR tidak ditimpa;
* translated output searchable.

## 18.6 Tests

* FakeOCRProvider;
* clean scan;
* noisy scan;
* rotated;
* low resolution;
* timeout;
* low confidence;
* correction;
* source invalidation;
* OCR cancellation.

## 18.7 Quality Gate

* no remote OCR;
* raw OCR tetap;
* source correction memiliki history;
* OCR error tidak merusak project;
* scanned E2E lulus.

## 18.8 Rollback Point

Tag:

```text
m09-ocr-complete
```

---

# 19. Milestone 10 — Reconstruction and Export

## 19.1 Objective

Membangun PDF hasil translation yang lengkap, terbaca, dan tervalidasi.

## 19.2 Dependencies

Milestone 8 dan Milestone 9.

## 19.3 Scope

* reconstruction settings;
* overlay;
* reflow;
* hybrid;
* fonts;
* images;
* tables;
* overflow;
* collision;
* pages;
* metadata;
* export profiles;
* PDF validation.

## 19.4 Tasks

### M10-T01 — Implement Reconstruction Domain Models

* job;
* page;
* block;
* target mapping;
* settings.

### M10-T02 — Implement Font Resolver

* source;
* system;
* fallback;
* missing glyph warning.

### M10-T03 — Implement Text Measurement

* font;
* width;
* height;
* wrap;
* line count.

### M10-T04 — Implement Overlay Generator

Gunakan:

```text
ReportLab
pypdf
```

### M10-T05 — Implement Source Text Cover Strategy

Minimum:

* plain-background cover;
* source page raster fallback.

### M10-T06 — Implement Reflow Generator

Gunakan:

```text
HTML
CSS
Jinja2
WeasyPrint
```

Dengan restricted resource loader.

### M10-T07 — Implement Hybrid Classifier

Strategy per:

* page;
* block.

### M10-T08 — Implement Image Preservation

* aspect ratio;
* crop;
* position;
* caption relation.

### M10-T09 — Implement Simple Table Reconstruction

* wrap;
* row height;
* header;
* pagination.

### M10-T10 — Implement Complex Table Fallback

Preserve as image dan warning.

### M10-T11 — Implement Overflow Detection

* horizontal;
* vertical;
* page;
* cell.

### M10-T12 — Implement Collision Detection

* text-text;
* text-image;
* body-footer;
* table-image.

### M10-T13 — Implement Fallback Chain

```text
adjust geometry
→ reduce spacing
→ reduce font
→ reflow
→ next page
→ add page
→ manual review
```

### M10-T14 — Implement Page Mapping

* one-to-one;
* one-to-many;
* target numbering.

### M10-T15 — Implement External Hyperlink Safety

Allowed schemes only.

### M10-T16 — Implement Export Profiles

* Standard;
* High Quality;
* Compact.

### M10-T17 — Implement Final PDF Validation

* open;
* page count;
* checksum;
* text extraction;
* active content;
* missing segment;
* critical warnings.

### M10-T18 — Implement Reconstruction UI

* settings;
* preview;
* progress;
* warnings;
* retry page.

### M10-T19 — Implement Download

Safe filename dan attachment headers.

## 19.5 Deliverables

* translated PDF dapat dibuat;
* images preserved;
* text searchable;
* critical overflow diblokir;
* export dapat diunduh.

## 19.6 Tests

* overlay;
* reflow;
* hybrid;
* fonts;
* images;
* tables;
* overflow;
* collision;
* added page;
* hyperlink;
* unsafe resource;
* final PDF;
* golden documents.

## 19.7 Quality Gate

* output PDF dapat dibuka;
* missing required segment = 0;
* critical clipping = 0;
* critical collision = 0;
* original checksum tetap;
* active content tidak terbawa.

## 19.8 Rollback Point

Tag:

```text
m10-reconstruction-complete
```

---

# 20. Milestone 11 — Quality, Backup, Recovery, and MVP Hardening

## 20.1 Objective

Menyelesaikan reliability, backup, maintenance, security regression, benchmark, dan acceptance.

## 20.2 Dependencies

Seluruh milestone sebelumnya.

## 20.3 Scope

* quality reports;
* warnings;
* backup;
* restore;
* cleanup;
* integrity checks;
* model benchmark;
* recovery;
* E2E;
* performance;
* documentation;
* release checklist.

## 20.4 Tasks

### M11-T01 — Implement Quality Reports

Report:

* extraction;
* OCR;
* translation;
* terminology;
* reconstruction;
* final export.

### M11-T02 — Implement Warning Dashboard

* severity;
* filter;
* resolution;
* blocking warnings.

### M11-T03 — Complete Database Backup

* database-only;
* metadata;
* full project.

### M11-T04 — Implement Backup Manifest

* version;
* checksum;
* included files;
* schema.

### M11-T05 — Implement Backup Verification

* archive;
* manifest;
* checksum;
* database integrity.

### M11-T06 — Implement Restore

* confirmation;
* maintenance mode;
* pre-restore backup;
* temporary validation;
* atomic replacement.

### M11-T07 — Implement Maintenance

* database integrity;
* file integrity;
* orphan scan;
* temp cleanup;
* cache cleanup;
* vacuum.

### M11-T08 — Implement Storage Dashboard

* category;
* project usage;
* free disk;
* cleanup preview.

### M11-T09 — Implement Local Model Benchmark

Minimum:

* hardware profile;
* quick benchmark;
* structured output;
* placeholders;
* latency;
* RAM;
* recommendation.

### M11-T10 — Implement Recovery Flow

* stale job;
* worker crash;
* incomplete export;
* interrupted translation;
* interrupted reconstruction.

### M11-T11 — Complete Security Regression Suite

* path traversal;
* origin;
* command;
* prompt injection;
* unsafe HTML;
* zip slip;
* archive bomb;
* remote Ollama.

### M11-T12 — Complete Digital PDF E2E

Full workflow.

### M11-T13 — Complete Scanned PDF E2E

Full workflow.

### M11-T14 — Complete Backup-Restore E2E

Full restoration.

### M11-T15 — Performance Profiling

* 10;
* 50;
* 100;
* 250 pages.

### M11-T16 — Documentation Completion

* README;
* setup;
* troubleshooting;
* backup;
* restore;
* model selection;
* limitations.

### M11-T17 — License Review

Update:

```text
THIRD_PARTY_LICENSES.md
```

### M11-T18 — MVP Release Checklist

Verify exit criteria.

## 20.5 Deliverables

* application dapat dipulihkan;
* backup valid;
* E2E lulus;
* benchmark model tersedia;
* security regression lulus;
* documentation lengkap.

## 20.6 Quality Gate

* no Critical defect;
* no unresolved High defect pada critical path;
* backup-restore lulus;
* digital E2E lulus;
* scanned E2E lulus;
* security tests lulus;
* original checksum invariant lulus;
* final PDF validation lulus.

## 20.7 Rollback Point

Tag:

```text
m11-personal-mvp-complete
```

---

# 21. Post-MVP Optional Milestone — Desktop Packaging

Status:

```text
DEFERRED
```

Hanya dimulai setelah Personal MVP selesai.

Potential scope:

* desktop shell;
* installer;
* signed binary;
* automatic startup;
* packaged frontend/backend;
* update integrity.

Tidak boleh menjadi syarat Personal MVP.

---

# 22. Task Specification Template

Setiap Codex task menggunakan format:

```text
Task ID:
Milestone:
Title:
Objective:
Requirement Sources:
Dependencies:
Allowed Files:
Prohibited Files:
Implementation Requirements:
Security Requirements:
Tests Required:
Acceptance Criteria:
Definition of Done:
Out of Scope:
```

---

# 23. Example Codex Task

```text
Task ID: M2-T05
Milestone: M2 — Database, Settings, and Projects
Title: Implement Project Persistence

Objective:
Implement the project SQLAlchemy model, repository, service, migration,
and tests.

Requirement Sources:
- DATABASE_SCHEMA.md Section 15
- API_CONTRACT.md Sections 25–27
- SECURITY.md Sections 40–42
- MVP_SCOPE.md Section 10

Dependencies:
- SQLite engine exists
- Alembic configured

Allowed Files:
- python/transloka-core/transloka_core/database/models/projects.py
- python/transloka-core/transloka_core/repositories/projects.py
- services/api/src/transloka_api/services/projects.py
- infrastructure/migrations/*
- tests/unit/projects/*
- tests/integration/database/*

Prohibited Files:
- translation modules
- reconstruction modules
- frontend editor
- authentication

Implementation Requirements:
- prefixed UUID
- project status enum
- timestamps
- archive support
- no hard delete in this task

Security Requirements:
- parameterized queries
- no absolute path
- validate enum

Tests Required:
- create
- get
- list
- update
- archive
- invalid state
- migration

Acceptance Criteria:
- project persists after restart
- migration succeeds on empty database
- all tests pass
```

---

# 24. Codex Execution Sequence

Untuk setiap task:

1. Baca dokumen requirement terkait.
2. Periksa repository saat ini.
3. Identifikasi dependency yang sudah tersedia.
4. Buat perubahan terbatas.
5. Tambahkan test.
6. Jalankan lint.
7. Jalankan type check.
8. Jalankan targeted test.
9. Jalankan affected integration test.
10. Tampilkan ringkasan perubahan.
11. Tampilkan command test dan hasilnya.
12. Catat assumption atau limitation.
13. Jangan melanjutkan task berikutnya otomatis.

---

# 25. Codex Stop Conditions

Codex harus berhenti dan melaporkan jika:

* requirement bertentangan;
* dependency belum tersedia;
* scope membutuhkan fitur deferred;
* dependency license bermasalah;
* migration dapat menghapus data;
* security control tidak dapat diterapkan;
* test gagal karena bug lama;
* hardware requirement tidak diketahui;
* task membutuhkan paid service;
* perubahan menyentuh area di luar allowed files.

Berhenti berarti tidak mengarang solusi diam-diam.

---

# 26. Codex Prohibited Behavior

Codex tidak boleh:

* mengimplementasikan seluruh aplikasi sekaligus;
* mengganti stack;
* menambahkan cloud;
* menambahkan auth;
* menambahkan billing;
* menambahkan PyMuPDF;
* menggunakan `shell=True`;
* menghapus failing test;
* menonaktifkan type checking;
* membuat hard-coded success;
* menggunakan fake provider di production;
* mengubah original PDF;
* menghapus revision;
* melewati migration;
* menambahkan dependency tanpa alasan;
* mengerjakan task berikutnya tanpa review.

---

# 27. Code Review Checklist

Setiap task ditinjau untuk:

## Correctness

* requirement terpenuhi;
* edge case ditangani;
* state transition valid;
* error code benar.

## Scope

* tidak ada fitur tambahan;
* tidak ada refactor tidak terkait;
* file change terbatas.

## Security

* input divalidasi;
* path aman;
* no secret;
* no raw document log;
* no remote access.

## Data Integrity

* transaction tepat;
* source immutable;
* revision tersimpan;
* idempotency tersedia bila diperlukan.

## Testing

* test relevan;
* test gagal sebelum fix bila regression;
* tidak flaky;
* tidak bergantung pada paid service.

## Maintainability

* interface jelas;
* module boundary dipertahankan;
* tidak ada duplicated logic;
* dependency justified.

---

# 28. Migration Review Checklist

Setiap database migration diperiksa:

1. Revision ID unik.
2. Parent benar.
3. Upgrade tersedia.
4. Downgrade tersedia jika aman.
5. Data lama tidak hilang.
6. Source text tidak berubah.
7. ID tidak berubah.
8. Index baru diperlukan.
9. Constraint tidak merusak data fixture.
10. Migration test lulus.
11. Backup recommendation tersedia untuk perubahan berisiko.

---

# 29. Dependency Addition Checklist

Sebelum menambah dependency:

1. Fungsi belum tersedia.
2. Package dipelihara.
3. License diperiksa.
4. Ukuran dependency wajar.
5. Tidak menambah cloud requirement.
6. Tidak menambah binary tidak terpercaya.
7. Dapat berjalan Windows.
8. Versi dikunci.
9. License inventory diperbarui.
10. Test ditambahkan.

---

# 30. Security Gate per Milestone

| Milestone | Security Gate                             |
| --------- | ----------------------------------------- |
| M1        | Localhost, CORS, client header            |
| M2        | SQL safety, path-free API                 |
| M3        | File validation, immutable original       |
| M4        | Safe cancellation, idempotency            |
| M5        | Untrusted extracted text handling         |
| M6        | Placeholder integrity                     |
| M7        | Prompt isolation, model output validation |
| M8        | XSS prevention, revision conflict         |
| M9        | OCR isolation, raw output safety          |
| M10       | Restricted HTML, safe PDF export          |
| M11       | Backup extraction, restore integrity      |

---

# 31. Test Gate per Milestone

| Milestone | Minimum Required Test           |
| --------- | ------------------------------- |
| M0        | Workspace smoke                 |
| M1        | Health and origin               |
| M2        | Migration and project CRUD      |
| M3        | Import and malformed PDF        |
| M4        | Job retry and cancellation      |
| M5        | IR round trip                   |
| M6        | Glossary and placeholder        |
| M7        | Provider contract and injection |
| M8        | Revision and locking            |
| M9        | Scanned OCR fixture             |
| M10       | Golden reconstruction           |
| M11       | Full E2E and restore            |

---

# 32. Documentation Gate per Milestone

Setiap milestone memperbarui minimal:

* README setup jika command berubah;
* `.env.example` jika configuration berubah;
* API docs jika endpoint berubah;
* migration history jika schema berubah;
* license inventory jika dependency berubah;
* troubleshooting jika error baru penting.

---

# 33. Progress Tracking

Gunakan status:

```text
NOT_STARTED
READY
IN_PROGRESS
BLOCKED
IN_REVIEW
TESTING
COMPLETED
DEFERRED
```

Untuk setiap task catat:

```text
Task ID
Status
Owner
Dependencies
Branch
Commit
Tests
Known Issues
Completed Date
```

---

# 34. Milestone Completion Report

Setiap milestone menghasilkan report:

```text
Milestone:
Status:
Completed Tasks:
Deferred Tasks:
Files Added:
Migrations:
Endpoints:
Tests Added:
Tests Passed:
Security Checks:
Known Limitations:
Rollback Tag:
Next Milestone Readiness:
```

---

# 35. Risk Register

## Risk 1 — Local Model Quality Insufficient

Mitigation:

* benchmark;
* glossary;
* review editor;
* multiple candidate models;
* small batch;
* deterministic validation.

## Risk 2 — Hardware Insufficient

Mitigation:

* low-resource profile;
* concurrency 1;
* smaller model;
* reduced context;
* lower render DPI.

## Risk 3 — Layout Preservation Too Complex

Mitigation:

* hybrid mode;
* readability priority;
* complex table image fallback;
* manual review;
* page addition.

## Risk 4 — OCR Quality Low

Mitigation:

* confidence;
* manual source correction;
* page-level retry;
* preserve raw OCR.

## Risk 5 — SQLite Write Contention

Mitigation:

* WAL;
* short transactions;
* one heavy writer;
* busy timeout;
* separate Huey database.

## Risk 6 — Dependency Installation Difficult on Windows

Mitigation:

* native-first scripts;
* documented prerequisites;
* optional Docker;
* dependency groups;
* health checks.

## Risk 7 — Disk Usage Excessive

Mitigation:

* storage dashboard;
* cleanup;
* cache categories;
* disk estimate;
* configurable retention.

## Risk 8 — Project Scope Expansion

Mitigation:

* `MVP_SCOPE.md`;
* task boundaries;
* no deferred features;
* milestone gates.

---

# 36. Rollback Strategy

## 36.1 Code Rollback

Setiap milestone memiliki tag.

## 36.2 Database Rollback

* migration downgrade jika aman;
* pre-migration backup untuk risky migration;
* no destructive migration without backup.

## 36.3 File Rollback

Original tidak berubah.

Derived output dapat dihapus dan dibangun ulang.

## 36.4 Translation Rollback

Gunakan segment revision.

## 36.5 Glossary Rollback

Gunakan glossary revision dan snapshot.

## 36.6 Reconstruction Rollback

Gunakan reconstruction job version dan export version.

---

# 37. Partial Failure Policy

Aplikasi harus mendukung partial completion.

Contoh:

* 98 halaman berhasil, 2 gagal;
* 500 segment berhasil, 4 gagal;
* 20 tabel berhasil, 1 dipertahankan sebagai image.

Status:

```text
PARTIALLY_COMPLETED
```

Partial result tidak boleh diberi status final tanpa warning.

---

# 38. Performance Checkpoints

## After M3

Ukur:

* import;
* page render;
* storage size.

## After M5

Ukur:

* IR size;
* segment query;
* page editor load.

## After M7

Ukur:

* model load;
* batch latency;
* RAM;
* token speed.

## After M9

Ukur:

* OCR page time;
* OCR memory;
* model cache.

## After M10

Ukur:

* reconstruction page time;
* export size;
* visual validation time.

## After M11

Ukur full workflow.

---

# 39. Manual Review Checkpoints

Manual review dilakukan setelah:

* M3: PDF analysis;
* M5: reading order;
* M6: glossary matching;
* M7: translation quality;
* M8: editor usability;
* M9: OCR correction;
* M10: PDF layout;
* M11: full workflow.

---

# 40. Hardware Benchmark Checkpoint

Sebelum memilih default model:

1. Catat hardware.
2. Pastikan Ollama tersedia.
3. Jalankan quick benchmark kandidat.
4. Uji placeholder.
5. Uji Bahasa Indonesia.
6. Catat RAM dan latency.
7. Pilih model.
8. Simpan configuration.

Model default tidak ditetapkan pada code.

---

# 41. MVP Release Candidate Process

## RC1

Fokus:

* digital PDF;
* glossary;
* translation;
* review;
* basic hybrid export.

## RC2

Fokus:

* scanned PDF;
* OCR correction;
* table handling;
* backup.

## RC3

Fokus:

* recovery;
* performance;
* security;
* documentation.

Personal MVP selesai setelah RC3 memenuhi exit criteria.

---

# 42. MVP Release Checklist

## Installation

* Node tersedia.
* Python tersedia.
* pnpm tersedia.
* uv tersedia.
* Ollama tersedia.
* dependency locked.
* startup script bekerja.

## Local Security

* localhost only.
* foreign origin rejected.
* path traversal blocked.
* no remote provider.
* no document log leakage.

## Data

* SQLite valid.
* migration current.
* backup valid.
* restore tested.
* original immutable.

## Translation

* model selected.
* glossary works.
* placeholders valid.
* retry works.
* review works.

## PDF

* digital analysis works.
* OCR works.
* reconstruction works.
* output searchable.
* export valid.

## Tests

* static checks pass.
* unit pass.
* integration pass.
* security pass.
* digital E2E pass.
* scanned E2E pass.
* restore E2E pass.

---

# 43. MVP Exit Criteria

Personal MVP selesai apabila:

1. Seluruh `MUST IMPLEMENT` pada `MVP_SCOPE.md` terpenuhi.
2. Milestone M0–M11 selesai.
3. Tidak ada Critical defect.
4. Tidak ada unresolved High defect pada critical path.
5. Aplikasi berjalan lokal.
6. Tidak membutuhkan paid service.
7. Original PDF tetap.
8. Digital PDF E2E lulus.
9. Scanned PDF E2E lulus.
10. Glossary dan placeholder lulus.
11. Local translation berjalan.
12. Review dan revision berjalan.
13. Hybrid reconstruction berjalan.
14. Export PDF valid.
15. Backup dan restore lulus.
16. Security regression lulus.
17. Dokumentasi setup lengkap.
18. Model lokal telah diuji pada hardware pengguna.

---

# 44. Deferred Implementation Tracks

Tidak dimulai selama Personal MVP:

```text
Desktop installer
Authentication
Multi-user
Cloud storage
Cloud database
Remote AI provider
Payment
Ads
EPUB
DOCX
Real-time collaboration
Advanced semantic QA
Complex table recreation
Text-in-image translation
```

---

# 45. Recommended First Codex Sequence

Urutan task awal:

```text
M0-T01 Create repository structure
M0-T02 Configure Node workspace
M0-T03 Configure Python workspace
M0-T04 Configure lint and type checking
M0-T05 Configure Git ignore
M0-T06 Add license inventory
M0-T07 Add documentation index
M1-T01 Bootstrap Next.js
M1-T02 Bootstrap FastAPI
M1-T03 Configure localhost binding
M1-T04 Configure CORS
M1-T05 Require client headers
```

Codex tidak boleh langsung membuat translation pipeline sebelum foundation selesai.

---

# 46. Initial Repository Validation

Setelah M0, repository harus dapat menjalankan:

```bash
pnpm install --frozen-lockfile
uv sync --locked
pnpm lint
pnpm typecheck
uv run ruff check .
uv run mypy .
```

Belum diperlukan fungsi aplikasi pada tahap tersebut.

---

# 47. Initial Vertical Slice

Vertical slice pertama setelah foundation:

```text
Create project in frontend
→ POST project API
→ project service
→ SQLite repository
→ return project
→ display project dashboard
→ restart application
→ project still exists
```

Slice ini menjadi bukti arsitektur frontend, API, database, dan testing terhubung.

---

# 48. Second Vertical Slice

```text
Create project
→ import small digital PDF
→ validate
→ save immutable original
→ create document
→ render first page
→ display thumbnail
```

---

# 49. Third Vertical Slice

```text
Extract one paragraph
→ create one segment
→ add glossary term
→ protect term
→ translate using FakeTranslationProvider
→ review segment
→ export one-page PDF
```

Slice ini dapat dibuat sebelum seluruh fitur lengkap untuk membuktikan pipeline end-to-end.

---

# 50. Scope of Early Prototype

Early prototype boleh:

* hanya menggunakan PDF fixture;
* hanya satu page;
* menggunakan fake provider;
* menggunakan simple overlay;
* belum memiliki polished UI.

Namun, prototype harus diberi label:

```text
DEVELOPMENT PROTOTYPE
```

Tidak boleh dianggap Personal MVP selesai.

---

# 51. Production-Path Transition

Sebelum milestone dinyatakan selesai:

* fake provider dipindahkan ke test atau development config;
* production path menggunakan real local adapter;
* placeholder implementation dihapus;
* error handling lengkap;
* test integration tersedia.

---

# 52. Documentation Authority for Codex

Urutan authority:

```text
1. MVP_SCOPE.md
2. TECH_STACK_DECISIONS.md
3. SECURITY.md
4. DATABASE_SCHEMA.md
5. API_CONTRACT.md
6. Component specification documents
7. IMPLEMENTATION_PLAN.md
8. Task-specific instructions
```

Task-specific instruction tidak boleh melanggar dokumen di atas.

---

# 53. Conflict Resolution

Jika dua dokumen bertentangan:

1. Jangan memilih sendiri.
2. Identifikasi section yang bertentangan.
3. Gunakan authority order.
4. Catat conflict.
5. Terapkan keputusan dokumen yang lebih tinggi.
6. Jika authority sama, minta keputusan Project Owner sebelum mengubah requirement.

---

# 54. Assumption Register

Asumsi implementasi dicatat pada:

```text
docs/ASSUMPTIONS.md
```

Format:

```text
ASSUMPTION-ID:
Date:
Related Task:
Assumption:
Reason:
Impact:
Validation Needed:
Status:
```

Asumsi tidak menjadi requirement permanen tanpa approval.

---

# 55. Decision Register

Keputusan teknis baru dicatat sebagai ADR:

```text
docs/adr/
```

Format filename:

```text
ADR-0001-title.md
```

ADR dibutuhkan untuk:

* mengganti dependency utama;
* mengganti database;
* mengganti queue;
* mengganti PDF library;
* menambahkan remote service;
* menambah desktop shell;
* mengubah security model.

---

# 56. Issue Classification

Issue development diklasifikasikan:

```text
BUG
SECURITY
DATA_INTEGRITY
PERFORMANCE
UX
DOCUMENTATION
TECH_DEBT
SCOPE_REQUEST
```

`SCOPE_REQUEST` tidak langsung diimplementasikan.

---

# 57. Technical Debt Policy

Technical debt dapat diterima jika:

* tidak berada pada security path;
* tidak menyebabkan kehilangan data;
* tidak merusak source;
* terdokumentasi;
* memiliki issue;
* tidak digunakan untuk menunda test critical.

Dilarang membuat debt berupa:

* disabled validation;
* hard-coded model;
* missing migration;
* skipped backup;
* fake production result.

---

# 58. Definition of Ready for a Task

Task siap dikerjakan jika:

1. Requirement tersedia.
2. Dependency selesai.
3. Allowed files diketahui.
4. Acceptance criteria jelas.
5. Test requirement jelas.
6. Security requirement jelas.
7. Tidak membutuhkan fitur deferred.
8. Tidak ada conflict yang belum diselesaikan.

---

# 59. Definition of Ready for a Milestone

Milestone siap dimulai jika:

* previous required milestone selesai;
* branch dibuat;
* task list tersedia;
* test environment siap;
* migration backup point tersedia jika diperlukan;
* hardware dependency tersedia;
* open blocking decision diselesaikan.

---

# 60. Definition of Done for a Milestone

Milestone selesai jika:

1. Semua Must task selesai.
2. Quality gate lulus.
3. Security gate lulus.
4. Documentation diperbarui.
5. Known limitation dicatat.
6. No Critical defect.
7. Rollback tag dibuat.
8. Completion report dibuat.
9. Next milestone dependency tersedia.

---

# 61. Open Implementation Decisions

1. Nama final Python package.
2. Nama final CLI command.
3. Default Windows data directory.
4. Apakah Huey consumer menggunakan thread atau process.
5. Nilai stale job timeout.
6. Nilai default PDF size limit.
7. Nilai default page limit.
8. Nilai default render DPI.
9. Default fallback font.
10. Apakah WeasyPrint dipasang pada setup awal atau reconstruction group.
11. Apakah OCR dependency dipasang saat setup awal.
12. Apakah PaddleOCR model diunduh melalui setup terpisah.
13. Apakah FTS5 wajib.
14. Apakah full project backup masuk M11 Must.
15. Apakah compact export masuk release pertama.
16. Apakah `LITERARY` translation style masuk M7.
17. Apakah debug layout UI tetap development-only.
18. Apakah app menggunakan polling saja atau SSE setelah MVP.
19. Apakah local API menggunakan startup token pada packaged version.
20. Apakah desktop packaging menjadi milestone langsung setelah MVP.

---

# 62. Definition of Done

`IMPLEMENTATION_PLAN.md` dianggap selesai apabila:

* milestone implementasi telah ditetapkan;
* dependency graph tersedia;
* task utama telah dipecah;
* deliverable setiap milestone jelas;
* quality gate setiap milestone tersedia;
* security gate tersedia;
* rollback point tersedia;
* Codex execution rules tersedia;
* task template tersedia;
* MVP exit criteria tersedia;
* deferred tracks telah dipisahkan;
* pembangunan dapat dimulai tanpa memerintahkan Codex membuat seluruh aplikasi sekaligus.
