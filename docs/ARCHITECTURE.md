# ARCHITECTURE

## TransLoka Local-First Personal MVP System Architecture

**Document Name:** `ARCHITECTURE.md`
**Document Version:** 0.2
**Status:** Draft
**Decision Date:** 2026-07-26
**Application Mode:** Local-First, Single User
**Architecture Style:** Modular Monolith with Separate Local Worker
**Primary Platform:** Windows
**Primary Input:** PDF
**Primary Output:** Translated PDF
**Primary Language Pair:** English → Bahasa Indonesia
**Primary Translation Runtime:** Ollama Local
**Primary OCR Runtime:** PaddleOCR Local
**Supersedes:** `ARCHITECTURE.md` Version 0.1

**Related Documents:**

* `PRD.md`
* `MVP_SCOPE.md`
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
* `IMPLEMENTATION_PLAN.md`
* `CODEX_TASKS.md`
* `MASTER_CODEX_PROMPT.md`

---

# 1. Revision Summary

Version 0.2 mengubah arsitektur TransLoka dari rancangan cloud-oriented menjadi arsitektur local-first untuk Personal MVP.

Perubahan utama:

1. Menghapus authentication service.
2. Menghapus user dan organization service.
3. Menghapus billing dan usage service.
4. Menghapus notification service eksternal.
5. Menghapus cloud storage.
6. Menghapus managed database.
7. Menghapus Redis.
8. Mengganti distributed queue dengan Huey `SqliteHuey`.
9. Mengganti translation provider utama dengan Ollama lokal.
10. Mengganti OCR provider utama dengan PaddleOCR lokal.
11. Menggunakan SQLite sebagai application database.
12. Menggunakan filesystem lokal untuk file dan artifact.
13. Menggunakan modular monolith dengan satu API dan satu worker lokal.
14. Membatasi network binding ke localhost.
15. Menetapkan source PDF sebagai immutable file.
16. Menetapkan hybrid reconstruction sebagai default.
17. Menetapkan security file lokal, process isolation, dan prompt-injection protection sebagai architecture concern utama.
18. Mempertahankan adapter boundary untuk kemungkinan migrasi masa depan tanpa mengimplementasikan cloud sekarang.

---

# 2. Architecture Objective

Arsitektur TransLoka harus:

* mendukung workflow import sampai export secara lokal;
* menjaga dokumen tetap privat;
* tidak membutuhkan layanan berbayar;
* tidak membutuhkan koneksi internet untuk operasi normal;
* dapat dijalankan pada satu komputer;
* dapat dipahami dan dirawat dengan bantuan Codex;
* memisahkan domain logic dari library pihak ketiga;
* mempertahankan source data;
* mendukung retry dan recovery;
* dapat berkembang tanpa overengineering;
* dapat diuji tanpa Ollama dan OCR aktual melalui fake provider.

---

# 3. Architecture Principles

## 3.1 Local-First

Seluruh data dan proses inti berada pada komputer pengguna.

## 3.2 Modular Monolith

TransLoka tidak menggunakan microservices pada Personal MVP.

Komponen tetap dipisahkan secara modular dalam repository dan codebase.

## 3.3 Separate Worker Process

Proses berat dijalankan melalui worker lokal agar API tetap responsif.

## 3.4 Source Immutability

Source PDF tidak pernah dimodifikasi.

## 3.5 Derivative Artifacts

Semua output adalah derivative:

* page render;
* OCR output;
* Document IR snapshot;
* translation;
* reconstructed page;
* export PDF;
* backup.

## 3.6 Database for State, Filesystem for Binary

SQLite menyimpan state dan metadata.

Filesystem menyimpan file besar dan binary.

## 3.7 Explicit State Machines

Status tidak disimpulkan hanya dari keberadaan file.

## 3.8 Adapters at External Boundaries

Library atau runtime yang dapat diganti dibungkus adapter.

## 3.9 Security by Default

Input, model output, path, HTML, archive, dan subprocess diperlakukan sebagai untrusted.

## 3.10 Readability over Pixel Fidelity

Reconstruction memprioritaskan kelengkapan dan keterbacaan.

## 3.11 Progressive Complexity

Implementasi dimulai dari workflow dasar, kemudian ditingkatkan secara incremental.

---

# 4. System Context

```text id="2jqlup"
┌──────────────────────────────────────────────────────────┐
│                    Local Computer                        │
│                                                          │
│  ┌──────────────┐      HTTP localhost     ┌────────────┐ │
│  │ Web Browser  │ ◄─────────────────────► │ FastAPI API│ │
│  │ Next.js UI   │                         └─────┬──────┘ │
│  └──────────────┘                               │        │
│                                                 │        │
│                         SQLite                  │        │
│                    ┌──────────────┐              │        │
│                    │transloka.db  │ ◄────────────┤        │
│                    └──────────────┘              │        │
│                                                 │        │
│                       Huey Queue                │        │
│                    ┌──────────────┐              │        │
│                    │ tasks.db     │ ◄────────────┤        │
│                    └──────┬───────┘              │        │
│                           │                      │        │
│                    ┌──────▼───────┐              │        │
│                    │ Local Worker │              │        │
│                    └───┬─────┬────┘              │        │
│                        │     │                   │        │
│                 ┌──────▼┐  ┌─▼────────┐          │        │
│                 │Ollama │  │PaddleOCR │          │        │
│                 └───────┘  └──────────┘          │        │
│                        │                         │        │
│                 ┌──────▼─────────────────────────▼─────┐ │
│                 │       Local Filesystem Storage       │ │
│                 │ PDF, images, OCR, IR, exports, backup│ │
│                 └──────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────┘
```

Tidak ada komponen yang wajib berjalan di cloud.

---

# 5. Primary Runtime Components

Personal MVP memiliki empat runtime utama:

1. Web frontend.
2. FastAPI backend.
3. Huey worker.
4. Local AI dan OCR runtimes.

---

# 6. Web Frontend

## 6.1 Technology

```text id="8vhktv"
Next.js App Router
TypeScript
Node.js 24
pnpm
Tailwind CSS
shadcn/ui
TanStack Query
Zustand
React Hook Form
Zod
PDF.js
```

## 6.2 Responsibilities

Frontend bertanggung jawab untuk:

* project dashboard;
* PDF import;
* system health;
* page preview;
* glossary editor;
* translation configuration;
* job progress;
* review editor;
* warning display;
* reconstruction settings;
* export download;
* backup and restore UI;
* storage management;
* model selection;
* benchmark display.

## 6.3 Non-Responsibilities

Frontend tidak boleh:

* membaca arbitrary local path;
* mengakses SQLite langsung;
* mengakses filesystem langsung;
* memanggil Ollama langsung;
* menjalankan OCR;
* melakukan reconstruction;
* menyimpan full document text secara permanen pada browser;
* memvalidasi security-critical path tanpa backend validation.

## 6.4 Frontend State

Gunakan:

```text id="emfrq2"
TanStack Query
```

untuk server state:

* projects;
* documents;
* pages;
* segments;
* jobs;
* warnings;
* exports.

Gunakan:

```text id="izuk97"
Zustand
```

untuk ephemeral UI state:

* selected page;
* selected segment;
* panel visibility;
* zoom;
* unsaved draft state;
* review filter.

Zustand tidak menjadi sumber kebenaran domain.

---

# 7. FastAPI Backend

## 7.1 Technology

```text id="pguyb5"
FastAPI
Python 3.12
Pydantic v2
SQLAlchemy 2
Alembic
uv
```

## 7.2 Responsibilities

Backend bertanggung jawab untuk:

* API contract;
* request validation;
* origin validation;
* project management;
* document import;
* file validation;
* job creation;
* database access;
* provider orchestration;
* Document IR queries;
* glossary management;
* translation workflow;
* review mutation;
* reconstruction orchestration;
* export metadata;
* backup and restore;
* maintenance;
* health checks.

## 7.3 Non-Responsibilities

Backend request process tidak boleh menjalankan operation berat secara langsung.

Operation berat dialihkan ke worker.

## 7.4 Application Factory

FastAPI menggunakan application factory untuk:

* test isolation;
* configuration injection;
* fake dependency injection;
* lifecycle management;
* controlled startup.

---

# 8. Local Worker

## 8.1 Technology

```text id="gwj0jo"
Huey
SqliteHuey
Python worker process
```

## 8.2 Responsibilities

Worker menjalankan:

* PDF analysis;
* page rendering;
* digital text extraction;
* OCR;
* structure detection;
* terminology candidate detection;
* translation;
* validation;
* reconstruction;
* export;
* benchmark;
* backup;
* restore;
* cleanup;
* integrity scan.

## 8.3 Worker Concurrency

Default:

```text id="dlr2cl"
1 heavy job at a time
```

Beberapa operation ringan dapat berjalan bersamaan jika aman, tetapi Personal MVP tidak mengoptimalkan concurrency tinggi.

## 8.4 Job Payload

Queue payload hanya menyimpan:

* job ID;
* project ID;
* document ID;
* page IDs;
* compact settings;
* operation ID.

Queue payload tidak menyimpan:

* PDF binary;
* entire document text;
* image binary;
* backup archive;
* raw model response.

## 8.5 Queue Database

```text id="rhybmk"
{TRANSLOKA_DATA_DIR}/database/tasks.db
```

Application state berada pada database terpisah:

```text id="cark90"
{TRANSLOKA_DATA_DIR}/database/transloka.db
```

---

# 9. Local AI Runtime

## 9.1 Translation Runtime

Primary runtime:

```text id="wb3f2r"
Ollama
```

Default endpoint:

```text id="nkhv93"
http://127.0.0.1:11434
```

## 9.2 Responsibilities

Ollama hanya bertugas:

* menerima translation request;
* menerima structured context;
* menghasilkan structured translation response.

## 9.3 Restrictions

Ollama model tidak diberikan:

* filesystem tools;
* shell tools;
* network tools;
* database tools;
* queue tools;
* deletion tools.

## 9.4 Model Selection

Model dipilih pengguna setelah:

* detection;
* health test;
* license review;
* optional benchmark.

Tidak ada model default universal yang di-hard-code.

---

# 10. Local OCR Runtime

## 10.1 Primary Runtime

```text id="zhznnd"
PaddleOCR
PP-StructureV3
```

## 10.2 Responsibilities

OCR runtime menghasilkan:

* recognized text;
* coordinates;
* confidence;
* structure candidates;
* table candidates.

## 10.3 Restrictions

OCR:

* tidak menggunakan remote URL;
* tidak mengirim data ke cloud;
* tidak mengganti raw OCR result;
* tidak menentukan final source text tanpa source-resolution rules.

---

# 11. Database Architecture

## 11.1 Application Database

```text id="j4h0zm"
SQLite
transloka.db
```

## 11.2 Queue Database

```text id="9kssff"
SQLite
tasks.db
```

## 11.3 Database Responsibilities

SQLite menyimpan:

* application settings;
* projects;
* file metadata;
* documents;
* pages;
* blocks;
* segments;
* assets;
* glossary;
* translation batches;
* revisions;
* jobs;
* warnings;
* quality reports;
* reconstruction records;
* exports;
* model metadata;
* benchmark results;
* backup metadata.

## 11.4 Files Not Stored in SQLite

Jangan menyimpan sebagai BLOB:

* PDF;
* page renders;
* images;
* OCR JSON besar;
* IR snapshots;
* export PDFs;
* backup archives.

## 11.5 Database Mode

Wajib:

```sql id="fgp2at"
PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;
PRAGMA busy_timeout = 5000;
```

## 11.6 Transaction Policy

Transaction harus pendek.

Jangan mempertahankan transaction saat:

* menunggu Ollama;
* menjalankan OCR;
* membaca PDF besar;
* merender halaman;
* menulis export;
* menunggu user review.

---

# 12. Filesystem Architecture

## 12.1 Data Root

```text id="8m9s6p"
TRANSLOKA_DATA_DIR
```

Default Windows path final masih menjadi open decision.

## 12.2 Directory Layout

```text id="8oz90f"
transloka-data/
├── database/
│   ├── transloka.db
│   └── tasks.db
│
├── projects/
│   └── {project_id}/
│       ├── original/
│       ├── pages/
│       ├── thumbnails/
│       ├── assets/
│       ├── ocr/
│       ├── intermediate/
│       │   ├── extraction/
│       │   ├── terminology/
│       │   ├── translation/
│       │   └── reconstruction/
│       ├── snapshots/
│       ├── exports/
│       └── logs/
│
├── benchmarks/
├── backups/
├── cache/
│   ├── fonts/
│   ├── renders/
│   └── models/
│
├── temp/
└── maintenance/
```

## 12.3 Storage Keys

Database hanya menyimpan relative storage key.

Contoh:

```text id="qa5h29"
projects/prj_123/original/fil_123.pdf
```

## 12.4 Path Resolution

Semua file operation melalui:

```text id="iiym6m"
FileStorage
```

Tidak ada module lain yang membangun path user-controlled secara langsung.

---

# 13. Core Domain Modules

Arsitektur domain dibagi menjadi module berikut:

```text id="66jav2"
transloka-core
transloka-document-ir
transloka-documents
transloka-glossary
transloka-translation
transloka-reconstruction
transloka-quality
```

---

# 14. `transloka-core`

Responsibilities:

* identifiers;
* shared enums;
* configuration;
* database foundation;
* repository abstractions;
* storage abstractions;
* jobs;
* backup;
* maintenance;
* common errors;
* logging;
* clock abstraction;
* checksums.

Tidak boleh memuat:

* domain translation detail;
* OCR implementation;
* reconstruction layout logic.

---

# 15. `transloka-document-ir`

Responsibilities:

* Document IR models;
* schema version;
* geometry types;
* serialization;
* snapshot;
* migration;
* invariants;
* relationships;
* source-target separation.

Module ini tidak bergantung pada:

* FastAPI;
* frontend;
* Ollama;
* PaddleOCR;
* ReportLab;
* WeasyPrint.

---

# 16. `transloka-documents`

Responsibilities:

* PDF validation;
* metadata analysis;
* native extraction;
* page rendering;
* asset extraction;
* reading order;
* block classification;
* segmentation;
* OCR adapter;
* table detection;
* scanned-page detection.

Dependencies eksternal dibungkus melalui internal adapter jika diperlukan.

---

# 17. `transloka-glossary`

Responsibilities:

* glossary entities;
* matching;
* normalization;
* priority;
* conflict detection;
* terminology candidates;
* occurrences;
* snapshots;
* placeholder generation;
* protected item restoration;
* impact analysis.

Glossary logic harus deterministik.

---

# 18. `transloka-translation`

Responsibilities:

* provider interface;
* Ollama provider;
* fake provider;
* prompt builder;
* context builder;
* batch builder;
* structured parsing;
* deterministic validation;
* retry;
* orchestration;
* benchmark.

Translation module tidak boleh melakukan direct file deletion atau arbitrary SQL.

---

# 19. `transloka-reconstruction`

Responsibilities:

* reconstruction planning;
* mode selection;
* font resolution;
* text measurement;
* overlay rendering;
* reflow rendering;
* hybrid rendering;
* image handling;
* table handling;
* overflow;
* collision;
* pagination;
* page mapping;
* PDF assembly.

Module ini menggunakan source data melalui Document IR dan approved translation snapshot.

---

# 20. `transloka-quality`

Responsibilities:

* extraction quality;
* OCR quality;
* translation integrity;
* terminology consistency;
* reconstruction quality;
* final PDF validation;
* warnings;
* reports;
* blocking policy.

Quality module tidak mengubah content secara otomatis kecuali rule deterministik yang telah ditetapkan.

---

# 21. Adapter Interfaces

Minimum adapter interfaces:

```text id="1wwzfc"
TranslationProvider
OCRProvider
FileStorage
PDFMetadataReader
PDFTextExtractor
PDFPageRenderer
AssetExtractor
ReconstructionRenderer
PDFAssembler
BackupArchive
ResourceMonitor
```

---

# 22. `TranslationProvider`

Interface minimum:

```python id="ckzst7"
class TranslationProvider(Protocol):
    def health_check(self) -> ProviderHealth:
        ...

    def list_models(self) -> list[ModelInfo]:
        ...

    def translate(
        self,
        request: TranslationRequest,
    ) -> TranslationResponse:
        ...
```

Implementations:

```text id="se90zf"
FakeTranslationProvider
OllamaTranslationProvider
```

Future provider tidak diimplementasikan pada Personal MVP.

---

# 23. `OCRProvider`

Interface minimum:

```python id="wjt45p"
class OCRProvider(Protocol):
    def health_check(self) -> ProviderHealth:
        ...

    def analyze_page(
        self,
        image: PageImageReference,
        settings: OCRSettings,
    ) -> OCRPageResult:
        ...
```

Implementations:

```text id="svvyms"
FakeOCRProvider
PaddleOCRProvider
```

---

# 24. `FileStorage`

Interface minimum:

```python id="3xjgpr"
class FileStorage(Protocol):
    def write_temporary(self, stream: BinaryIO) -> TemporaryFile:
        ...

    def commit(self, temp: TemporaryFile, storage_key: str) -> StoredFile:
        ...

    def open_read(self, storage_key: str) -> BinaryIO:
        ...

    def delete(self, storage_key: str) -> None:
        ...

    def checksum(self, storage_key: str) -> str:
        ...
```

Personal MVP implementation:

```text id="jof9yz"
LocalFileStorage
```

---

# 25. API Layer Architecture

API structure:

```text id="ngk8wn"
routers
schemas
services
dependency injection
middleware
exception handlers
```

Router tidak boleh memuat business logic kompleks.

Flow:

```text id="1uhqtc"
HTTP request
→ Pydantic validation
→ application service
→ domain service
→ repository/provider
→ response schema
```

---

# 26. Repository Layer

Repository interface minimum:

```text id="x17c57"
ProjectRepository
StoredFileRepository
DocumentRepository
PageRepository
BlockRepository
SegmentRepository
GlossaryRepository
TranslationRepository
JobRepository
WarningRepository
ReconstructionRepository
ExportRepository
BackupRepository
```

Repository:

* menggunakan SQLAlchemy;
* menerima session;
* tidak melakukan network request;
* tidak merender file;
* tidak membangun prompt;
* tidak mengelola UI state.

---

# 27. Application Services

Application services mengoordinasikan use cases.

Contoh:

```text id="na6bhh"
CreateProjectService
ImportDocumentService
AnalyzeDocumentService
RunOCRService
DetectTerminologyService
StartTranslationService
EditSegmentService
ApproveSegmentService
StartReconstructionService
CreateExportService
CreateBackupService
RestoreBackupService
```

Application service boleh memanggil:

* repository;
* domain service;
* adapter;
* job dispatcher.

Application service tidak boleh menyimpan business state di memory sebagai sumber kebenaran.

---

# 28. Document Import Data Flow

```text id="997ci8"
Browser selects PDF
        ↓
Multipart upload to FastAPI
        ↓
Stream to controlled temporary file
        ↓
Validate size, magic, MIME, parser, pages, password
        ↓
Calculate checksum
        ↓
Commit immutable source file
        ↓
Create stored file record
        ↓
Create document record
        ↓
Create analysis job
        ↓
Return document + job
```

---

# 29. Document Analysis Data Flow

```text id="6x7ssn"
Worker receives document ID
        ↓
Load immutable source reference
        ↓
Read metadata
        ↓
Create page records
        ↓
Detect digital/scanned/hybrid pages
        ↓
Render thumbnails
        ↓
Extract native text
        ↓
Detect assets and tables
        ↓
Build preliminary Document IR
        ↓
Persist analysis
        ↓
Create IR snapshot
        ↓
Update job and project status
```

---

# 30. OCR Data Flow

```text id="uow5y9"
Select OCR pages
        ↓
Create OCR job
        ↓
Render page image
        ↓
Run PaddleOCR
        ↓
Store raw OCR result
        ↓
Normalize lines and geometry
        ↓
Create or update source blocks and segments
        ↓
Calculate confidence
        ↓
Generate warnings
        ↓
Allow manual source correction
```

Raw OCR tidak ditimpa.

---

# 31. Glossary Data Flow

```text id="fzupb6"
Extracted segments
        ↓
Normalize terms
        ↓
Detect terminology candidates
        ↓
User accepts/rejects candidates
        ↓
Compile glossary rules
        ↓
Resolve priority and conflicts
        ↓
Create immutable glossary snapshot
        ↓
Detect occurrences
        ↓
Generate protected items
```

---

# 32. Translation Data Flow

```text id="e7js7f"
Select translation scope
        ↓
Translation readiness check
        ↓
Load source segments
        ↓
Load glossary snapshot
        ↓
Detect protected content
        ↓
Replace protected content with placeholders
        ↓
Build context and batches
        ↓
Send structured request to Ollama
        ↓
Parse structured response
        ↓
Validate segment mapping
        ↓
Restore placeholders
        ↓
Run deterministic QA
        ↓
Persist attempt and result
        ↓
Update segment status
        ↓
Create warnings or review queue entries
```

---

# 33. Review Data Flow

```text id="ngpbyu"
User selects segment
        ↓
Load source, translation, context, warnings
        ↓
User edits translated text
        ↓
Send expected revision
        ↓
Backend validates optimistic lock
        ↓
Create append-only revision
        ↓
Update current reviewed translation
        ↓
Invalidate related reconstruction cache
        ↓
Optional approve and lock
```

---

# 34. Reconstruction Data Flow

```text id="90in9p"
Reconstruction readiness check
        ↓
Resolve approved/final translation snapshot
        ↓
Create reconstruction plan
        ↓
Select strategy per page/block
        ↓
Resolve fonts
        ↓
Measure translated text
        ↓
Detect overflow and collision
        ↓
Apply fallback chain
        ↓
Render overlay/reflow/hybrid pages
        ↓
Preserve assets
        ↓
Assemble PDF
        ↓
Remove unsafe active content
        ↓
Validate final PDF
        ↓
Create export record
```

---

# 35. Backup Data Flow

```text id="iw52lv"
User requests backup
        ↓
Create backup job
        ↓
Check disk space
        ↓
Create SQLite backup
        ↓
Collect selected files
        ↓
Generate manifest
        ↓
Create controlled archive
        ↓
Calculate checksum
        ↓
Verify archive
        ↓
Mark backup completed
```

---

# 36. Restore Data Flow

```text id="t7hkyo"
User confirms restore
        ↓
Enter maintenance mode
        ↓
Pause new mutation jobs
        ↓
Create pre-restore backup
        ↓
Validate archive
        ↓
Extract to controlled temp directory
        ↓
Validate paths, checksums, schema
        ↓
Run database integrity check
        ↓
Replace database atomically
        ↓
Restore referenced files
        ↓
Run application integrity check
        ↓
Exit maintenance mode
```

---

# 37. State Management

## 37.1 Project State

Project status disimpan di database.

## 37.2 Job State

Business job status disimpan di `transloka.db`.

Huey queue state berada di `tasks.db`.

## 37.3 Segment State

Current state disimpan pada segment.

History disimpan pada append-only revisions.

## 37.4 Reconstruction State

Setiap run memiliki immutable settings snapshot dan versioned output.

---

# 38. Job State Machine

```text id="tj54y3"
CREATED
→ QUEUED
→ RUNNING
→ COMPLETED
```

Alternatives:

```text id="0jauje"
RUNNING → COMPLETED_WITH_WARNINGS
RUNNING → PARTIALLY_COMPLETED
RUNNING → RETRYING
RUNNING → FAILED
RUNNING → CANCELLATION_REQUESTED → CANCELLED
```

Worker crash:

```text id="v8l5cn"
RUNNING → STALE
```

---

# 39. Project State Machine

```text id="17ilp0"
CREATED
→ IMPORTING
→ ANALYZING
→ EXTRACTING
→ TERMS_DETECTED
→ WAITING_FOR_GLOSSARY
→ TRANSLATING
→ READY_FOR_REVIEW
→ REVIEWING
→ RECONSTRUCTING
→ READY_FOR_EXPORT
→ COMPLETED
```

Alternative state:

```text id="3nrizp"
OCR_PROCESSING
PARTIALLY_COMPLETED
FAILED
CANCELLED
ARCHIVED
DELETION_QUEUED
```

---

# 40. Segment State Machine

```text id="950a1s"
CREATED
→ EXTRACTED
→ NORMALIZED
→ TERMS_DETECTED
→ PROTECTED
→ READY_FOR_TRANSLATION
→ TRANSLATING
→ MACHINE_TRANSLATED
→ NEEDS_REVIEW
→ USER_EDITED
→ APPROVED
→ LOCKED
```

Alternative:

```text id="t6sdl1"
OCR_REQUIRED
OCR_COMPLETED
TRANSLATION_FAILED
IGNORED
NOT_TRANSLATABLE
```

---

# 41. Caching Strategy

Personal MVP menggunakan cache lokal terbatas.

Cache candidates:

* thumbnails;
* page renders;
* model metadata;
* compiled glossary;
* translation request hashes;
* reconstruction page output;
* text measurements.

Cache tidak menjadi sumber kebenaran.

Cache dapat dibangun ulang.

---

# 42. Cache Keys

Cache harus mempertimbangkan:

```text id="sd0br6"
source checksum
document revision
page ID
segment revision
glossary snapshot
translation settings
model ID
prompt version
reconstruction settings
engine version
font mapping
```

---

# 43. Translation Cache

Exact translation reuse dapat digunakan jika seluruh hash sama:

```text id="kr7ac4"
source text
context fingerprint
glossary snapshot
model
prompt version
settings
```

Translation cache tidak digunakan untuk:

* approved text replacement;
* cross-project semantic memory;
* fuzzy translation memory.

---

# 44. Reconstruction Cache

Page reconstruction cache key:

```text id="h317vj"
document version
page ID
segment revision set
glossary snapshot
reconstruction profile
font resolver version
engine version
```

Jika satu segment berubah, hanya page terkait sebaiknya invalidated.

Incremental reconstruction berstatus recommended.

---

# 45. Security Boundaries

Architecture trust boundaries:

```text id="z8a72p"
Browser input
PDF file
Filesystem path
OCR output
Model output
HTML/CSS renderer
Backup archive
Subprocess output
Third-party dependency
```

Seluruh boundary membutuhkan validation.

---

# 46. Browser Boundary

Control:

* localhost origin allowlist;
* custom client header;
* content-type validation;
* no wildcard CORS;
* GET read-only;
* no arbitrary path API.

---

# 47. PDF Boundary

Control:

* streaming upload;
* magic validation;
* size limit;
* page limit;
* parser handling;
* active content detection;
* image-size limit;
* source immutability.

---

# 48. Filesystem Boundary

Control:

* relative storage keys;
* canonical path resolution;
* root containment;
* symlink checks;
* atomic writes;
* safe filename;
* controlled deletion.

---

# 49. Model Boundary

Control:

* source as data;
* structured response;
* schema validation;
* no tools;
* placeholder inventory;
* deterministic validation;
* remote endpoint blocked.

---

# 50. OCR Boundary

Control:

* raster input generated internally;
* geometry validation;
* confidence validation;
* output escaping;
* raw result retained.

---

# 51. HTML and WeasyPrint Boundary

Control:

* internal templates only;
* escaped source;
* CSS allowlist;
* custom resource loader;
* no remote assets;
* no arbitrary `file://`;
* no script or iframe.

---

# 52. Archive Boundary

Control:

* manifest;
* checksums;
* path validation;
* decompressed-size limit;
* compression-ratio limit;
* symlink rejection;
* temporary extraction.

---

# 53. Subprocess Boundary

Control:

* `shell=False`;
* argument list;
* timeout;
* exit-code validation;
* environment allowlist;
* controlled work directory;
* sanitized logs.

---

# 54. Error Architecture

Errors dibagi menjadi:

```text id="t266q0"
DomainError
ValidationError
SecurityError
ProviderError
StorageError
DatabaseError
JobError
ReconstructionError
BackupError
```

API layer mengubah error menjadi normalized API error.

Internal stack trace tidak dikirim ke frontend.

---

# 55. Error Propagation

```text id="zq2zrq"
Library exception
→ adapter normalization
→ domain/application error
→ API error code
→ user-actionable frontend message
```

Library exception tidak boleh bocor langsung ke API.

---

# 56. Warning Architecture

Warning berbeda dari error.

Warning:

* dapat tidak memblokir;
* memiliki severity;
* dapat diselesaikan;
* dapat diterima oleh pengguna;
* tersimpan dalam history.

Critical warning tertentu bersifat non-overridable.

---

# 57. Observability

Personal MVP menggunakan local observability.

Minimum:

* structured logs;
* request IDs;
* job IDs;
* durations;
* resource metrics;
* warning counts;
* application health;
* operation event history.

Tidak menggunakan remote telemetry.

---

# 58. Logging Architecture

Safe log fields:

```text id="1ucwyv"
timestamp
level
request_id
job_id
project_id
document_id
page_id
segment_id
operation
status
duration_ms
error_code
```

Jangan log:

* full source text;
* full translation;
* prompt;
* raw model response;
* absolute path;
* PDF content.

---

# 59. Resource Monitoring

Monitor:

* free disk;
* process RAM;
* optional GPU VRAM;
* page render duration;
* OCR duration;
* model latency;
* reconstruction duration.

Resource monitor digunakan untuk warning dan benchmark, bukan cloud analytics.

---

# 60. Failure Recovery

## 60.1 API Crash

API restart membaca state dari SQLite.

## 60.2 Worker Crash

Heartbeat menjadi stale.

Job dapat di-retry.

## 60.3 Ollama Failure

Attempt gagal.

Batch dapat di-retry.

## 60.4 OCR Failure

Page ditandai failed.

Page lain tetap valid.

## 60.5 Reconstruction Failure

Output sementara tidak dianggap final.

Valid output lama tetap tersedia.

## 60.6 Database Failure

Mutation diblokir jika integrity check gagal.

## 60.7 Disk Full

Operation dihentikan sebelum final artifact commit.

---

# 61. Idempotency Architecture

Idempotency diperlukan untuk:

* import;
* analysis;
* translation start;
* reconstruction;
* export;
* backup;
* restore;
* retry.

Idempotency key mengacu pada operation dan scope.

Duplicate request mengembalikan existing job atau result.

---

# 62. Versioning Architecture

Versioned artifacts:

* database schema;
* Document IR schema;
* glossary snapshot;
* prompt;
* translation pipeline;
* translation result;
* segment revision;
* reconstruction engine;
* reconstruction settings;
* export;
* benchmark dataset;
* backup manifest.

---

# 63. Configuration Architecture

Configuration sources:

```text id="5u5je3"
Environment variables
App settings database
Task-specific settings snapshot
Internal defaults
```

Priority:

```text id="d40k0d"
Explicit task setting
→ application setting
→ environment
→ safe default
```

Security-critical defaults tidak boleh dilemahkan oleh project document.

---

# 64. Environment Variables

Minimum candidates:

```text id="cgpi9k"
TRANSLOKA_DATA_DIR
TRANSLOKA_API_HOST
TRANSLOKA_API_PORT
TRANSLOKA_WEB_ORIGINS
TRANSLOKA_OLLAMA_URL
TRANSLOKA_LOG_LEVEL
TRANSLOKA_DEBUG
```

Sensitive values tidak diperlukan untuk Personal MVP.

---

# 65. Deployment Model

Personal MVP menggunakan native local deployment.

Processes:

```text id="0yspsr"
Next.js
FastAPI
Huey worker
Ollama
```

OCR dapat berjalan dalam worker process atau subprocess sesuai hasil implementasi.

---

# 66. Windows Process Layout

```text id="cpeq0n"
start.ps1
├── starts Next.js
├── starts FastAPI
├── starts Huey worker
└── checks Ollama and OCR status
```

`stop.ps1` hanya menghentikan process yang dikelola TransLoka.

---

# 67. Docker Position

Docker bersifat optional.

Docker dapat digunakan untuk:

* development consistency;
* CI;
* troubleshooting.

Docker tidak menjadi requirement Personal MVP.

Ollama GPU passthrough dan Windows filesystem complexity menjadi alasan native-first.

---

# 68. Repository Architecture

```text id="2i4rvs"
transloka/
├── apps/
│   └── web/
│
├── services/
│   ├── api/
│   └── worker/
│
├── python/
│   ├── transloka-core/
│   ├── transloka-document-ir/
│   ├── transloka-documents/
│   ├── transloka-glossary/
│   ├── transloka-translation/
│   ├── transloka-reconstruction/
│   └── transloka-quality/
│
├── packages/
│   ├── api-client/
│   ├── ui/
│   └── shared-config/
│
├── infrastructure/
│   ├── migrations/
│   ├── local/
│   └── docker/
│
├── scripts/
├── tests/
└── docs/
```

---

# 69. Dependency Direction

Allowed dependency direction:

```text id="z7fhkg"
API
→ Application services
→ Domain modules
→ Interfaces
→ Infrastructure adapters
```

Domain modules tidak boleh mengimpor FastAPI.

Frontend tidak boleh mengimpor backend implementation.

Repository tidak boleh mengimpor frontend atau API router.

---

# 70. Python Package Dependency Guidance

Suggested direction:

```text id="g23jp6"
transloka-core
        ↑
transloka-document-ir
        ↑
transloka-documents
transloka-glossary
transloka-translation
transloka-reconstruction
transloka-quality
```

Circular dependency harus dihindari.

Shared types yang terlalu umum berada di `transloka-core`.

Document-specific models tetap berada di `transloka-document-ir`.

---

# 71. Frontend Architecture

Feature-based organization:

```text id="q5twuj"
apps/web/src/
├── app/
├── features/
│   ├── projects/
│   ├── documents/
│   ├── pdf-viewer/
│   ├── glossary/
│   ├── translation/
│   ├── editor/
│   ├── ocr/
│   ├── reconstruction/
│   ├── exports/
│   ├── models/
│   ├── benchmarks/
│   ├── backups/
│   ├── storage/
│   └── system/
├── components/
├── hooks/
├── lib/
└── state/
```

Business feature state tidak ditempatkan seluruhnya di global store.

---

# 72. API Structure

```text id="bp5s9e"
services/api/src/transloka_api/
├── app.py
├── config.py
├── middleware/
├── exception_handlers/
├── routers/
├── schemas/
├── services/
├── dependencies/
└── startup/
```

---

# 73. Worker Structure

```text id="hwtdhr"
services/worker/src/transloka_worker/
├── app.py
├── config.py
├── tasks/
│   ├── analysis.py
│   ├── ocr.py
│   ├── terminology.py
│   ├── translation.py
│   ├── reconstruction.py
│   ├── export.py
│   ├── backup.py
│   └── maintenance.py
└── lifecycle/
```

Task function harus tipis.

Business operation berada pada domain/application service.

---

# 74. OpenAPI Architecture

FastAPI menghasilkan OpenAPI.

TypeScript API client dihasilkan dari OpenAPI.

Flow:

```text id="a6vfui"
FastAPI schemas
→ OpenAPI
→ generated TypeScript client
→ frontend
```

Generated client tidak diedit manual.

---

# 75. Testing Architecture

Test layers:

```text id="8v5tfa"
Unit
Integration
Contract
Security
Golden document
Visual regression
Recovery
End-to-end
Performance
```

Standard CI menggunakan fake providers.

Local full validation menggunakan Ollama dan PaddleOCR aktual.

---

# 76. Fake Providers

Required:

```text id="lw0c7g"
FakeTranslationProvider
FakeOCRProvider
FakeFileStorage where useful
FakeResourceMonitor
FakeClock
```

Fake hanya digunakan pada test atau development mode yang jelas.

---

# 77. Golden Documents

Golden fixtures mencakup:

* digital single-column;
* digital two-column;
* scanned;
* hybrid;
* image-heavy;
* table;
* code;
* footnote;
* rotated;
* malformed;
* active content.

---

# 78. Performance Architecture

## 78.1 Streaming

Gunakan streaming untuk:

* upload;
* file copy;
* checksum;
* PDF assembly jika memungkinkan;
* backup archive.

## 78.2 Page-Oriented Processing

PDF diproses page-by-page.

## 78.3 Batch Translation

Translation menggunakan small configurable batches.

## 78.4 Low Concurrency

Default concurrency rendah untuk mencegah resource exhaustion.

## 78.5 Checkpointing

Long jobs menyimpan checkpoint setelah unit kerja valid selesai.

---

# 79. Resource Profiles

## 79.1 Low

* small model;
* concurrency 1;
* reduced context;
* lower DPI;
* smaller batches.

## 79.2 Standard

* 7B–14B candidate;
* standard DPI;
* small batch;
* hybrid reconstruction.

## 79.3 High

* larger model;
* larger context;
* higher DPI;
* more expensive reconstruction.

Model size final ditentukan benchmark.

---

# 80. Architecture Decision: No Authentication

Personal MVP tidak menggunakan authentication karena:

* single user;
* localhost-only;
* no public deployment;
* no organization data sharing.

Konsekuensi:

* OS account security menjadi trust boundary;
* remote deployment dilarang;
* authentication wajib ditambahkan sebelum LAN/public use.

---

# 81. Architecture Decision: SQLite

SQLite dipilih karena:

* local;
* no service management;
* reliable;
* transaction support;
* Alembic compatible;
* sufficient for one user;
* easy backup.

PostgreSQL ditunda hingga ada kebutuhan multi-user atau remote deployment.

---

# 82. Architecture Decision: Huey

Huey dipilih karena:

* ringan;
* mendukung SQLite;
* mudah dijalankan lokal;
* tidak membutuhkan Redis;
* cukup untuk single-user queue.

Celery tidak dipilih karena kompleksitas tambahan.

---

# 83. Architecture Decision: Local Filesystem

Filesystem lokal dipilih karena:

* no cloud;
* simple binary handling;
* efficient for PDF and images;
* compatible with backup;
* no external service.

Object storage abstraction dipertahankan hanya pada interface level jika diperlukan.

---

# 84. Architecture Decision: Ollama

Ollama dipilih karena:

* local inference;
* no paid request;
* model choice;
* API sederhana;
* privacy.

Model quality tetap diverifikasi melalui benchmark.

---

# 85. Architecture Decision: Hybrid Reconstruction

Hybrid dipilih sebagai default karena:

* overlay cocok untuk fixed layout;
* reflow cocok untuk long text expansion;
* preserve mode cocok untuk image/formula;
* tidak semua page memerlukan strategy yang sama.

---

# 86. Architecture Decision: No PyMuPDF

PyMuPDF, `fitz`, dan `pymupdf4llm` tidak digunakan tanpa keputusan lisensi baru.

Approved PDF libraries:

```text id="u7op8h"
pdfplumber
pypdf
pypdfium2
ReportLab
WeasyPrint
```

---

# 87. Future Migration Path

Arsitektur mempertahankan kemungkinan migrasi melalui adapter.

Future possibilities:

* PostgreSQL;
* S3-compatible storage;
* remote model provider;
* distributed queue;
* authentication;
* multi-user;
* desktop shell;
* cloud deployment.

Tidak satu pun diimplementasikan pada Personal MVP.

---

# 88. Migration Preconditions

Sebelum berpindah ke cloud atau multi-user:

1. PRD direvisi.
2. Security model direvisi.
3. Authentication ditambahkan.
4. Authorization ditambahkan.
5. Database migration plan dibuat.
6. Storage migration plan dibuat.
7. Remote TLS ditambahkan.
8. Secrets management ditambahkan.
9. Privacy policy dibuat.
10. Threat model diperbarui.
11. Operational monitoring ditambahkan.
12. Monetization diputuskan secara terpisah.

---

# 89. Architecture Constraints for Codex

Codex wajib:

* mengikuti modular monolith;
* menggunakan approved stack;
* menggunakan adapters;
* mempertahankan data boundaries;
* menggunakan migrations;
* menambahkan tests;
* tidak menambah cloud;
* tidak menambah auth;
* tidak menambah billing;
* tidak menambah PyMuPDF;
* tidak mengerjakan future migration tanpa task eksplisit.

---

# 90. Architecture Smells to Avoid

Hindari:

* router dengan business logic;
* service yang langsung menulis arbitrary file;
* domain yang mengimpor FastAPI;
* global mutable state;
* model output dipakai tanpa validation;
* BLOB besar dalam SQLite;
* path string tersebar;
* direct subprocess dari router;
* queue task berisi PDF binary;
* revision overwrite;
* cache sebagai source of truth;
* shared module yang menampung seluruh logic;
* circular package dependency.

---

# 91. Architecture Validation Checklist

## Runtime

* frontend start;
* API start;
* worker start;
* Ollama health;
* OCR health.

## Network

* localhost only;
* foreign origin rejected;
* no remote provider.

## Data

* SQLite WAL;
* queue DB separate;
* files under root;
* original immutable.

## Processing

* heavy work in worker;
* provider adapter;
* job state persisted;
* retry idempotent.

## Security

* path containment;
* no shell;
* escaped HTML;
* archive safety;
* prompt injection tests.

## Output

* versioned export;
* final validation;
* checksum;
* no active content.

---

# 92. Architecture Acceptance Criteria

Architecture Version 0.2 dianggap siap apabila:

1. Seluruh core runtime bersifat lokal.
2. Tidak ada cloud dependency wajib.
3. Tidak ada authentication service.
4. Tidak ada billing service.
5. Modular monolith telah ditetapkan.
6. Separate worker telah ditetapkan.
7. SQLite application database telah ditetapkan.
8. Queue database terpisah telah ditetapkan.
9. Filesystem storage telah ditetapkan.
10. Ollama adapter telah ditetapkan.
11. PaddleOCR adapter telah ditetapkan.
12. Document IR boundary telah ditetapkan.
13. Glossary boundary telah ditetapkan.
14. Translation boundary telah ditetapkan.
15. Reconstruction boundary telah ditetapkan.
16. Security boundaries telah ditetapkan.
17. Data flow import sampai export telah ditetapkan.
18. Backup dan restore flow telah ditetapkan.
19. Job lifecycle telah ditetapkan.
20. Package dependency direction telah ditetapkan.
21. Repository structure telah ditetapkan.
22. Testing architecture telah ditetapkan.
23. Recovery strategy telah ditetapkan.
24. Performance strategy telah ditetapkan.
25. Future migration tetap deferred.

---

# 93. Open Architecture Decisions

1. Default Windows data directory.
2. Apakah OCR berjalan di worker process atau isolated child process.
3. Apakah PDF parser tertentu membutuhkan child-process isolation.
4. Default stale-job threshold.
5. Exact worker process count.
6. Apakah OCR dependency dipasang pada base setup.
7. Apakah WeasyPrint dependency dipasang pada base setup.
8. Apakah FTS5 mandatory.
9. Exact backup archive format.
10. Apakah queue database masuk backup.
11. Apakah browser UI memakai polling saja.
12. Apakah SSE ditambahkan post-MVP.
13. Exact resource monitoring implementation.
14. Default fallback font bundle.
15. Apakah source embedded font dapat digunakan.
16. Apakah page render cache memiliki LRU cleanup.
17. Apakah full project backup mandatory.
18. Apakah OCR formula detection digunakan.
19. Apakah external annotations dipertahankan.
20. Apakah desktop packaging menjadi post-MVP milestone pertama.

---

# 94. Definition of Done

`ARCHITECTURE.md` Version 0.2 dinyatakan selesai apabila:

* seluruh architecture selaras dengan `PRD.md` Version 0.2;
* local-first menjadi deployment model utama;
* modular monolith menjadi architecture style;
* separate local worker telah ditetapkan;
* SQLite dan filesystem menjadi persistence utama;
* Ollama dan PaddleOCR menjadi local runtime;
* authentication, billing, cloud storage, dan managed services dihapus;
* source immutability telah ditetapkan;
* Document IR menjadi canonical document model;
* glossary, translation, reconstruction, quality, dan backup boundaries telah ditetapkan;
* data flow lengkap tersedia;
* security boundaries tersedia;
* failure recovery tersedia;
* repository layout tersedia;
* Codex dapat mengimplementasikan system tanpa menebak component responsibilities;
* future cloud migration tetap hanya berupa adapter path dan bukan implementation requirement.
