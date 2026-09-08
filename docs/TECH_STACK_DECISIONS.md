# TECH STACK DECISIONS

## Approved cloud exception - 2026-09-07

Optional Groq text inference is approved following the owner request of 2026-09-07 and the existing Add Cloud AI Provider criteria. Use the TranslationProvider contract with stdlib HTTPS, fixed api.groq.com endpoints, environment credentials, bounded I/O and no redirects/proxies. Keep remote Ollama validation intact. Qwen 3.8 27B is a preview evaluation candidate; access, free account tier and translation quality require later validation. Existing local-only claims apply to local mode; this is the sole outbound inference exception.

Design: [Optional Groq translation](releases/CLOUD_TRANSLATION_DESIGN_2026-09-07.md).

## TransLoka Local-First Personal MVP

**Document Name:** `TECH_STACK_DECISIONS.md`  
**Document Version:** 0.2  
**Status:** Draft  
**Decision Date:** 2026-07-26  
**Deployment Target:** Personal Computer  
**Access Model:** Single User  
**Cost Objective:** Tidak menggunakan API atau layanan berbayar  
**Monetization Status:** Tidak direncanakan pada tahap awal  

**Supersedes:** `TECH_STACK_DECISIONS.md — Version 0.1`

**Related Documents:**

- `PRD.md`
- `ARCHITECTURE.md`
- `DOCUMENT_IR.md`
- `TRANSLATION_PIPELINE.md`
- `GLOSSARY_ENGINE.md`

---

# 1. Purpose

Dokumen ini menetapkan technology stack resmi untuk membangun TransLoka sebagai aplikasi lokal yang digunakan secara pribadi oleh pemilik aplikasi.

Aplikasi harus dapat:

- berjalan di komputer pengguna;
- diakses melalui browser lokal;
- menyimpan seluruh dokumen pada komputer lokal;
- menjalankan OCR secara lokal;
- menjalankan model terjemahan secara lokal;
- tidak membutuhkan API AI berbayar;
- tidak membutuhkan cloud database;
- tidak membutuhkan cloud object storage;
- tidak membutuhkan sistem subscription;
- tetap dapat dikembangkan menjadi aplikasi online pada masa depan.

Dokumen ini menjadi sumber keputusan utama untuk Codex dalam menentukan:

- runtime;
- framework;
- database;
- background task;
- penyimpanan file;
- model terjemahan;
- OCR;
- PDF processing;
- testing;
- struktur repository;
- local deployment;
- dependency.

---

# 2. Authority

Apabila terdapat konflik antara dokumen ini dan `TECH_STACK_DECISIONS.md — Version 0.1`, keputusan dalam Version 0.2 yang berlaku.

Keputusan berikut dari Version 0.1 dibatalkan untuk Personal MVP:

```text
PostgreSQL
Redis
Celery
S3-compatible cloud storage
MinIO sebagai service wajib
OpenAI API sebagai provider utama
Authentication
Email verification
Password reset
Malware scanner wajib
Organization workspace
Subscription
Billing
Credit system
Cloud deployment
Multi-user access
Tenant isolation
```

Komponen tersebut dapat dipertimbangkan kembali pada fase publik atau komersial.

---

# 3. Product Deployment Model

TransLoka dibangun sebagai:

```text
Local-first single-user web application
+ local backend
+ local background worker
+ local AI model
+ local database
+ local file storage
```

Aplikasi berjalan pada:

```text
http://127.0.0.1
```

atau:

```text
http://localhost
```

Aplikasi tidak boleh secara default membuka akses ke:

```text
0.0.0.0
```

Hal ini mencegah aplikasi dapat diakses oleh perangkat lain di jaringan tanpa konfigurasi eksplisit.

---

# 4. Primary Architecture

```text
Browser
   │
   ▼
Next.js Local Frontend
   │
   ▼
FastAPI Local Backend
   ├── SQLite Application Database
   ├── Local Project Files
   ├── Huey Local Task Queue
   ├── PDF Processing Engine
   ├── PaddleOCR
   ├── Glossary Engine
   ├── Translation Pipeline
   ├── Reconstruction Engine
   └── Ollama Local API
```

Ollama menyediakan API lokal yang dapat digunakan aplikasi untuk menjalankan model pada komputer pengguna. citeturn596603search12turn596603search25

---

# 5. Architecture Principles

## 5.1 Local by Default

Seluruh data utama disimpan pada komputer pengguna.

Tidak ada dokumen yang dikirim ke cloud secara default.

## 5.2 No Paid Service Required

Aplikasi tidak boleh membutuhkan:

- OpenAI API;
- Google Cloud Vision;
- Azure OCR;
- AWS Textract;
- cloud database;
- cloud storage;
- subscription service;
- paid authentication provider.

## 5.3 Offline-Capable

Setelah seluruh dependency dan model selesai diunduh, fungsi inti harus dapat berjalan tanpa koneksi internet.

Pengecualian:

- instalasi awal;
- download model;
- update aplikasi;
- update dependency;
- update model.

## 5.4 Single User

Aplikasi tidak perlu memiliki:

- registrasi;
- login;
- role;
- permission;
- organization;
- tenant;
- session management.

## 5.5 Future Migration Path

Walaupun aplikasi berjalan lokal, komponen utama tetap menggunakan interface agar dapat diganti pada masa depan.

Contoh:

```text
SQLiteRepository
→ PostgreSQLRepository

LocalFileStorage
→ S3ObjectStorage

OllamaTranslationProvider
→ OpenAITranslationProvider

LocalOCRProvider
→ ManagedOCRProvider
```

## 5.6 Original Document Is Immutable

File asli tidak boleh diubah.

Semua hasil pemrosesan disimpan sebagai file turunan.

## 5.7 Resource-Aware Processing

Aplikasi harus menyesuaikan beban dengan kemampuan komputer.

Secara default:

- satu dokumen berat diproses pada satu waktu;
- concurrency OCR dibatasi;
- concurrency terjemahan dibatasi;
- model tidak dimuat berulang kali tanpa kebutuhan;
- preview menggunakan resolusi terbatas;
- intermediate file dibersihkan berdasarkan kebijakan.

---

# 6. Final Stack Summary

| Area | Decision |
|---|---|
| Application Type | Local web application |
| User Model | Single user |
| Frontend | Next.js App Router + TypeScript |
| Frontend Runtime | Node.js 24 |
| Package Manager | pnpm |
| UI | Tailwind CSS + shadcn/ui |
| Server State | TanStack Query |
| Local Editor State | Zustand |
| Form Handling | React Hook Form + Zod |
| PDF Viewer | PDF.js |
| Backend | FastAPI |
| Backend Runtime | Python 3.12 |
| Python Package Manager | uv |
| Validation | Pydantic v2 |
| ORM | SQLAlchemy 2 |
| Migration | Alembic |
| Database | SQLite |
| SQLite Mode | WAL |
| Background Queue | Huey `SqliteHuey` |
| File Storage | Local filesystem |
| Translation Runtime | Ollama |
| Translation Provider | `OllamaTranslationProvider` |
| Translation Output | JSON Schema structured output |
| OCR | PaddleOCR + PP-StructureV3 |
| Digital PDF Extraction | pdfplumber + pypdf |
| PDF Rendering | pypdfium2 |
| Overlay PDF | ReportLab + pypdf |
| Reflow PDF | HTML/CSS + WeasyPrint |
| Image Processing | Pillow + OpenCV |
| Authentication | None |
| Billing | None |
| Ads | None |
| Local Installation | Native-first |
| Optional Packaging | Docker Compose |
| Python Testing | pytest |
| Frontend Testing | Vitest + Testing Library |
| End-to-End Testing | Playwright |
| Python Quality | Ruff + mypy |
| TypeScript Quality | ESLint + TypeScript |

---

# 7. Cost Definition

Target “tanpa biaya” berarti:

```text
Tidak ada biaya API
Tidak ada biaya langganan
Tidak ada biaya server
Tidak ada biaya database cloud
Tidak ada biaya storage cloud
Tidak ada biaya authentication service
```

Namun, penggunaan tetap membutuhkan:

- komputer;
- kapasitas penyimpanan;
- RAM;
- CPU atau GPU;
- listrik;
- internet untuk download awal.

Aplikasi tidak menjamin bahwa seluruh model dapat berjalan dengan baik pada semua spesifikasi komputer.

---

# 8. Frontend Stack

## 8.1 Next.js

Gunakan:

```text
Next.js App Router
TypeScript
React
```

Next.js App Router menjadi struktur routing utama aplikasi. Dokumentasi Next.js merekomendasikan App Router untuk aplikasi baru. citeturn596603search13turn596603search14turn596603search20

Frontend bertanggung jawab untuk:

- dashboard proyek;
- pemilihan file;
- pengaturan terjemahan;
- glossary;
- progress processing;
- side-by-side editor;
- warning review;
- preview;
- export;
- local application settings.

---

## 8.2 Frontend Structure

```text
apps/web/
├── src/
│   ├── app/
│   │   ├── page.tsx
│   │   ├── projects/
│   │   ├── glossary/
│   │   ├── settings/
│   │   └── health/
│   ├── components/
│   ├── features/
│   │   ├── projects/
│   │   ├── documents/
│   │   ├── editor/
│   │   ├── glossary/
│   │   ├── translation/
│   │   └── export/
│   ├── hooks/
│   ├── lib/
│   ├── stores/
│   ├── styles/
│   └── types/
├── public/
├── tests/
└── package.json
```

---

## 8.3 TypeScript Rules

Aktifkan:

```json
{
  "compilerOptions": {
    "strict": true,
    "noUncheckedIndexedAccess": true,
    "exactOptionalPropertyTypes": true,
    "noImplicitOverride": true
  }
}
```

Dilarang:

- menggunakan `any` tanpa alasan;
- menonaktifkan TypeScript secara global;
- menulis ulang API schema secara manual;
- menggunakan `@ts-ignore` tanpa dokumentasi.

---

## 8.4 UI

Gunakan:

```text
Tailwind CSS
shadcn/ui
```

Jangan menambahkan UI framework kedua tanpa keputusan baru.

---

## 8.5 State Management

Gunakan TanStack Query untuk:

- project API;
- document status;
- processing progress;
- segment;
- glossary;
- export.

Gunakan Zustand hanya untuk state editor lokal:

- selected page;
- selected segment;
- zoom;
- panel state;
- filter;
- unsaved editor state.

---

## 8.6 PDF Viewer

Gunakan:

```text
PDF.js
```

PDF.js digunakan untuk:

- menampilkan PDF asli;
- menampilkan PDF hasil;
- navigasi halaman;
- zoom;
- page rendering;
- bounding-box overlay;
- segment selection.

---

# 9. Backend Stack

## 9.1 FastAPI

Gunakan:

```text
FastAPI
Pydantic v2
Uvicorn
```

Backend bertanggung jawab untuk:

- project management;
- local file import;
- document analysis;
- job creation;
- Document IR;
- glossary;
- translation;
- OCR;
- reconstruction;
- quality validation;
- export.

---

## 9.2 Backend Structure

```text
services/api/
├── src/transloka_api/
│   ├── main.py
│   ├── config.py
│   ├── dependencies.py
│   ├── routers/
│   ├── middleware/
│   ├── exception_handlers/
│   └── startup/
├── tests/
└── pyproject.toml
```

Route handler tidak boleh berisi business logic utama.

---

## 9.3 API Access

Backend hanya mendengarkan:

```text
127.0.0.1
```

Default port:

```text
8000
```

Frontend default:

```text
127.0.0.1:3000
```

CORS hanya mengizinkan frontend lokal yang dikonfigurasi.

---

# 10. Database

## 10.1 SQLite

Gunakan:

```text
SQLite
```

SQLite dipilih karena seluruh database dapat disimpan sebagai satu file lokal, sehingga cocok untuk aplikasi personal satu pengguna. citeturn596603search21turn596603search26turn596603search31

Lokasi default:

```text
{TRANSLoka_DATA_DIR}/database/transloka.db
```

SQLite menyimpan:

- project;
- document metadata;
- page;
- block;
- segment;
- glossary;
- term occurrence;
- translation job;
- translation attempt;
- warning;
- revision;
- export;
- application setting.

---

## 10.2 SQLite Configuration

Aktifkan:

```sql
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;
PRAGMA busy_timeout = 5000;
PRAGMA synchronous = NORMAL;
```

WAL digunakan untuk meningkatkan kemampuan reader dan writer berjalan dengan lebih baik pada aplikasi lokal, tetapi SQLite tetap memiliki batas concurrency penulisan. citeturn848434search0turn848434search8

---

## 10.3 ORM

Gunakan:

```text
SQLAlchemy 2
```

Dengan typed declarative model.

Gunakan repository abstraction agar migration ke PostgreSQL tetap memungkinkan.

Contoh:

```python
class ProjectRepository(Protocol):
    def create(self, project: Project) -> Project:
        ...

    def get(self, project_id: UUID) -> Project | None:
        ...
```

---

## 10.4 Migration

Gunakan:

```text
Alembic
```

Meskipun menggunakan SQLite, seluruh perubahan schema wajib memiliki migration.

Dilarang menghapus database pengguna hanya karena schema berubah.

---

## 10.5 SQLite Limitations

Personal MVP harus membatasi:

- satu aplikasi aktif;
- satu heavy processing job aktif secara default;
- jumlah writer process;
- transaction panjang;
- perubahan database saat AI inference berlangsung.

Database transaction harus ditutup sebelum:

- menjalankan OCR;
- memanggil Ollama;
- merender PDF;
- melakukan export panjang.

---

# 11. Background Task Queue

## 11.1 Huey

Gunakan:

```text
Huey
SqliteHuey
```

`SqliteHuey` menyediakan task queue berbasis file SQLite dan mendukung consumer terpisah tanpa membutuhkan Redis. citeturn848434search2turn848434search5turn848434search6

Ini menggantikan:

```text
Celery
Redis
```

pada Personal MVP.

---

## 11.2 Queue Storage

Queue menggunakan database terpisah:

```text
{TRANSLoka_DATA_DIR}/database/tasks.db
```

Jangan menggunakan file database aplikasi utama sebagai task queue.

Struktur:

```text
database/
├── transloka.db
└── tasks.db
```

---

## 11.3 Consumer

Background worker dijalankan sebagai proses lokal terpisah.

```text
FastAPI process
Huey consumer process
Ollama process
```

Task utama:

```text
analyze_document
render_page
extract_page
run_ocr
detect_terms
translate_batch
validate_translation
reconstruct_page
export_document
cleanup_project
```

---

## 11.4 Queue Policy

Default:

```text
Worker count: 1
Heavy task concurrency: 1
Translation batch concurrency: 1
OCR concurrency: 1
```

Pengguna dapat menaikkan concurrency melalui advanced settings.

---

## 11.5 Task Payload

Task hanya membawa identifier.

```json
{
  "job_id": "job_001",
  "project_id": "project_001",
  "document_id": "document_001",
  "page_ids": [
    "page_001",
    "page_002"
  ]
}
```

Task tidak boleh membawa:

- binary PDF;
- seluruh gambar;
- seluruh Document IR;
- prompt sangat besar;
- model file.

---

## 11.6 Idempotency

Setiap task harus:

- memiliki idempotency key;
- memeriksa output sebelumnya;
- aman dijalankan ulang;
- tidak membuat export duplikat;
- tidak menimpa approved translation;
- tidak menggandakan revision.

---

# 12. Local File Storage

## 12.1 Storage Type

Gunakan:

```text
Local filesystem
```

Tidak menggunakan:

- S3;
- MinIO;
- Google Drive;
- Dropbox;
- cloud storage.

---

## 12.2 Default Data Directory

Gunakan environment variable:

```text
TRANSLOKA_DATA_DIR
```

Default ditentukan berdasarkan sistem operasi.

Contoh struktur:

```text
transloka-data/
├── database/
│   ├── transloka.db
│   └── tasks.db
├── projects/
│   └── {project_id}/
│       ├── original/
│       ├── pages/
│       ├── thumbnails/
│       ├── assets/
│       ├── ocr/
│       ├── intermediate/
│       ├── snapshots/
│       └── exports/
├── cache/
├── models/
├── logs/
├── backups/
└── temp/
```

---

## 12.3 Storage Adapter

Gunakan interface:

```python
class FileStorage:
    def save_original(self, project_id: str, source_path: Path) -> StoredFile:
        ...

    def save_asset(self, project_id: str, asset: bytes) -> StoredFile:
        ...

    def open_file(self, storage_key: str) -> BinaryIO:
        ...

    def delete_project(self, project_id: str) -> None:
        ...
```

Implementasi awal:

```text
LocalFileStorage
```

Implementasi masa depan:

```text
S3FileStorage
```

---

## 12.4 File Import

Browser mengirim file ke FastAPI lokal melalui multipart upload.

Backend kemudian:

1. memvalidasi extension;
2. memvalidasi magic bytes;
3. menghitung checksum;
4. membuat project directory;
5. menyalin file sebagai immutable original;
6. menyimpan metadata;
7. membuat analysis job.

---

## 12.5 Original File Policy

File asli disimpan pada:

```text
projects/{project_id}/original/
```

Setelah tersimpan:

- tidak diedit;
- tidak ditimpa;
- tidak digunakan sebagai output;
- hanya dibaca;
- memiliki checksum.

---

# 13. Translation Runtime

## 13.1 Ollama

Gunakan:

```text
Ollama
```

Ollama berjalan sebagai local model server dan menyediakan API pada komputer pengguna. citeturn596603search12turn596603search27turn848434search7

Default endpoint:

```text
http://127.0.0.1:11434
```

---

## 13.2 Provider Interface

Translation pipeline tidak memanggil Ollama secara langsung dari business logic.

Gunakan:

```python
class TranslationProvider(Protocol):
    async def health_check(self) -> ProviderHealth:
        ...

    async def list_models(self) -> list[LocalModel]:
        ...

    async def translate(
        self,
        request: TranslationRequest,
    ) -> TranslationResponse:
        ...
```

Implementasi awal:

```text
OllamaTranslationProvider
```

Implementasi test:

```text
FakeTranslationProvider
```

Implementasi masa depan:

```text
OpenAITranslationProvider
```

---

## 13.3 Structured Output

Gunakan JSON Schema structured output dari Ollama untuk memaksa model mengembalikan mapping segment yang konsisten. Ollama mendukung JSON Schema pada format output. citeturn848434search3turn848434search7

Contoh schema:

```json
{
  "type": "object",
  "properties": {
    "segments": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "segment_id": {
            "type": "string"
          },
          "translated_text": {
            "type": "string"
          }
        },
        "required": [
          "segment_id",
          "translated_text"
        ]
      }
    }
  },
  "required": [
    "segments"
  ]
}
```

---

## 13.4 Model Selection

Tidak ada model yang di-hard-code sebagai pilihan universal.

Model dipilih melalui:

```text
Settings → Local AI Model
```

Aplikasi harus:

1. memeriksa apakah Ollama aktif;
2. membaca daftar model lokal;
3. menampilkan model yang tersedia;
4. meminta pengguna memilih model;
5. menjalankan benchmark singkat;
6. menyimpan model terpilih;
7. mengizinkan perubahan model.

Configuration:

```text
OLLAMA_BASE_URL
OLLAMA_TRANSLATION_MODEL
OLLAMA_VALIDATION_MODEL
OLLAMA_CONTEXT_LENGTH
OLLAMA_TEMPERATURE
OLLAMA_KEEP_ALIVE
```

---

## 13.5 First-Run Model Check

Saat aplikasi pertama kali dijalankan:

```text
Check Ollama availability
        ↓
List installed models
        ↓
No model found
        ↓
Show setup instructions
        ↓
User installs model
        ↓
Run translation benchmark
```

Aplikasi tidak boleh mengunduh model berukuran besar secara diam-diam.

---

## 13.6 Local Model Requirements

Model terpilih harus:

- mendukung bahasa Inggris;
- menghasilkan Bahasa Indonesia yang layak;
- mengikuti instruksi;
- mendukung structured output secara memadai;
- mempertahankan placeholder;
- berjalan pada hardware pengguna;
- memiliki lisensi yang sesuai untuk penggunaan pengguna.

Lisensi model harus diperiksa secara terpisah dari lisensi Ollama.

---

## 13.7 Translation Settings

Default awal:

```text
temperature: 0.1
stream: false
structured output: enabled
context: configurable
keep_alive: configurable
```

Temperature rendah digunakan untuk meningkatkan konsistensi.

---

## 13.8 Translation Validation

Model lokal tetap wajib melalui:

- placeholder validation;
- segment mapping validation;
- numerical validation;
- URL validation;
- code validation;
- language detection;
- terminology consistency check.

Local model tidak boleh dianggap benar hanya karena seluruh data diproses secara lokal.

---

# 14. OCR

## 14.1 Primary OCR

Gunakan:

```text
PaddleOCR
PP-StructureV3
```

PP-StructureV3 mendukung parsing dokumen seperti layout, tabel, formula, dan elemen visual. Paket instalasi `doc-parser` tersedia untuk kebutuhan document parsing. citeturn596603search0turn596603search1turn596603search7

---

## 14.2 OCR Installation

Dependency group:

```text
paddleocr[doc-parser]
```

PaddlePaddle harus dipasang sesuai CPU atau GPU yang tersedia.

---

## 14.3 OCR Model Download

Model OCR dapat membutuhkan download saat pertama kali digunakan.

Aplikasi harus:

- memberi tahu pengguna;
- menampilkan ukuran jika tersedia;
- menampilkan progress;
- tidak memulai download tanpa tindakan pengguna;
- menyimpan model pada cache lokal.

---

## 14.4 CPU Mode

CPU mode wajib didukung.

Default Personal MVP:

```text
CPU-compatible OCR
one page at a time
limited concurrency
```

GPU menjadi optional acceleration.

---

## 14.5 OCR Provider Interface

```python
class OCRProvider(Protocol):
    def health_check(self) -> OCRHealth:
        ...

    def analyze_page(
        self,
        image_path: Path,
        settings: OCRSettings,
    ) -> OCRPageResult:
        ...
```

Implementasi:

```text
PaddleOCRProvider
```

---

# 15. PDF Processing

## 15.1 Digital PDF Extraction

Gunakan:

```text
pdfplumber
pypdf
```

`pdfplumber` digunakan untuk:

- text;
- word;
- character;
- geometry;
- line;
- rectangle;
- table candidate.

`pypdf` digunakan untuk:

- metadata;
- page manipulation;
- page merge;
- annotation;
- bookmark;
- final assembly.

---

## 15.2 PDF Rendering

Gunakan:

```text
pypdfium2
```

Untuk:

- thumbnail;
- page image;
- OCR input;
- preview;
- visual comparison.

---

## 15.3 Overlay Reconstruction

Gunakan:

```text
ReportLab
pypdf
```

ReportLab menghasilkan translated text overlay.

`pypdf` menggabungkan overlay dengan halaman sumber atau reconstructed background.

---

## 15.4 Reflow Reconstruction

Gunakan:

```text
HTML
CSS
Jinja2
WeasyPrint
```

Reflow digunakan untuk:

- paragraf terlalu panjang;
- halaman buku;
- layout yang tidak dapat dipertahankan melalui overlay;
- dokumen yang lebih mengutamakan keterbacaan.

---

## 15.5 Hybrid Reconstruction

Default:

```text
HYBRID
```

Strategi:

```text
Images               → preserve
Headers and footers   → overlay
Short text blocks     → overlay
Long paragraphs       → reflow
Simple tables         → reconstruct
Complex tables        → preserve image + warning
Overflow              → reflow or add page
```

---

# 16. PyMuPDF Decision

Status:

```text
NOT USED
```

Walaupun aplikasi saat ini hanya untuk penggunaan pribadi, PyMuPDF tidak dijadikan dependency utama agar tidak menimbulkan hambatan lisensi apabila aplikasi nantinya dibagikan atau dikembangkan menjadi produk.

Codex tidak boleh menambahkan:

```text
pymupdf
fitz
pymupdf4llm
```

tanpa keputusan baru.

---

# 17. Authentication

Status:

```text
NOT REQUIRED
```

Personal MVP tidak memiliki:

- register;
- login;
- logout;
- password;
- email verification;
- password reset;
- user table;
- session;
- CSRF token untuk autentikasi.

Aplikasi tetap hanya boleh bind ke localhost.

---

# 18. Security Scope

Walaupun lokal, aplikasi tetap harus:

- memvalidasi file;
- membatasi akses path;
- mencegah path traversal;
- menghindari arbitrary command execution;
- menyaring HTML untuk reconstruction;
- tidak memuat remote asset tanpa izin;
- tidak menulis di luar data directory;
- tidak mencatat isi dokumen lengkap ke log;
- tidak mengekspos Ollama ke jaringan melalui aplikasi.

---

# 19. File Validation

Sebelum PDF diproses:

- periksa extension;
- periksa MIME;
- periksa magic bytes;
- periksa file size;
- periksa corruption;
- periksa password protection;
- periksa page count;
- periksa embedded JavaScript;
- periksa attachment;
- hitung checksum.

Malware scanning dengan ClamAV tidak wajib pada Personal MVP karena pengguna memproses file sendiri.

Adapter dapat ditambahkan pada fase publik.

---

# 20. Monetization

Status:

```text
REMOVED FROM PERSONAL MVP
```

Tidak dibuat:

- subscription;
- payment;
- credit;
- invoice;
- advertisement;
- watermark paket;
- usage billing;
- pricing page;
- upgrade prompt.

Usage tetap dapat dicatat secara lokal untuk:

- jumlah halaman;
- waktu pemrosesan;
- penggunaan token lokal;
- estimasi beban;
- troubleshooting.

Usage record tidak memiliki nilai uang.

---

# 21. Local Data Privacy

Karena seluruh pemrosesan lokal:

- dokumen tetap berada pada komputer;
- teks tidak dikirim ke AI cloud;
- glossary tetap lokal;
- hasil OCR tetap lokal;
- export tetap lokal.

Aplikasi harus menampilkan status:

```text
Local processing active
```

Jika pada masa depan provider cloud diaktifkan, aplikasi wajib menampilkan warning sebelum dokumen dikirim.

---

# 22. Repository Structure

```text
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
│   ├── local/
│   ├── docker/
│   └── migrations/
│
├── scripts/
│   ├── setup-local.ps1
│   ├── setup-local.sh
│   ├── start.ps1
│   ├── start.sh
│   ├── stop.ps1
│   ├── stop.sh
│   ├── backup.ps1
│   └── backup.sh
│
├── tests/
│   ├── fixtures/
│   ├── golden-documents/
│   ├── integration/
│   ├── visual/
│   └── security/
│
├── docs/
├── pnpm-workspace.yaml
├── package.json
├── pyproject.toml
├── uv.lock
├── pnpm-lock.yaml
├── .python-version
├── .nvmrc
├── .env.example
└── README.md
```

---

# 23. Native-First Installation

Personal MVP menggunakan native-first installation.

Komponen yang berjalan:

```text
Ollama
Next.js
FastAPI
Huey consumer
SQLite
```

Alasan:

- akses GPU Ollama lebih mudah;
- penggunaan resource lebih ringan;
- debugging lebih sederhana;
- folder lokal lebih mudah diakses;
- tidak membutuhkan Docker Desktop.

---

# 24. Optional Docker

Docker bersifat:

```text
OPTIONAL
```

Docker dapat digunakan untuk:

- development consistency;
- integration testing;
- CI;
- future deployment testing.

Ollama disarankan tetap berjalan native pada komputer host.

---

# 25. Startup Script

Sediakan:

```text
scripts/start.ps1
scripts/start.sh
```

Script menjalankan:

1. environment check;
2. database migration;
3. FastAPI;
4. Huey consumer;
5. Next.js;
6. Ollama health check;
7. membuka browser.

Script tidak boleh menginstal dependency tanpa pemberitahuan.

---

# 26. First-Run Setup

First-run flow:

```text
Check Python
Check Node.js
Check dependency
Check data directory
Create SQLite database
Run migration
Check Ollama
List local models
Check OCR dependency
Create application settings
Run health checks
Open application
```

---

# 27. Application Health Page

Route:

```text
/settings/system
```

Menampilkan:

- frontend status;
- backend status;
- worker status;
- database status;
- data directory;
- free disk space;
- Ollama status;
- selected model;
- OCR status;
- model cache;
- active job;
- application version.

---

# 28. Local Settings

Settings minimum:

```text
Data directory
Ollama endpoint
Translation model
Validation model
OCR mode
Maximum active jobs
OCR concurrency
Translation batch size
Page render DPI
Temporary file retention
Automatic backup
Log level
```

---

# 29. Backup

Aplikasi menyediakan backup lokal.

Backup mencakup:

```text
transloka.db
glossary
project metadata
translation revisions
settings
```

Optional full backup mencakup:

```text
original PDFs
intermediate files
exports
```

Format:

```text
transloka-backup-{timestamp}.zip
```

Backup tidak boleh dibuat ketika database transaction sedang aktif tanpa mekanisme snapshot yang aman.

---

# 30. Restore

Restore harus:

1. memvalidasi format backup;
2. memvalidasi version;
3. membuat backup keadaan saat ini;
4. menghentikan worker;
5. memulihkan database;
6. memulihkan file;
7. menjalankan migration jika diperlukan;
8. menjalankan integrity check.

---

# 31. Resource Profiles

## 31.1 Low-Resource Profile

```text
CPU processing
small local model
one OCR page at a time
small translation batches
lower preview resolution
```

## 31.2 Standard Profile

```text
CPU or supported GPU
medium local model
limited parallel rendering
standard translation batches
```

## 31.3 High-Resource Profile

```text
GPU acceleration
larger local model
higher context
parallel page rendering
higher OCR concurrency
```

Aplikasi harus dapat memilih profile berdasarkan konfigurasi, bukan asumsi.

---

# 32. Disk Space Management

Sistem harus mencatat ukuran:

- original;
- page render;
- OCR cache;
- model output;
- reconstructed page;
- export;
- backup.

Pengguna dapat menghapus:

```text
temporary files
page render cache
OCR cache
old export
old snapshot
```

File original dan approved translation tidak boleh ikut terhapus tanpa konfirmasi.

---

# 33. Environment Variables

```text
APP_ENV=local
APP_HOST=127.0.0.1
APP_PORT=8000
WEB_PORT=3000

TRANSLOKA_DATA_DIR=
DATABASE_URL=sqlite:///...

HUEY_DATABASE_PATH=
HUEY_WORKERS=1

OLLAMA_BASE_URL=http://127.0.0.1:11434
OLLAMA_TRANSLATION_MODEL=
OLLAMA_VALIDATION_MODEL=
OLLAMA_CONTEXT_LENGTH=
OLLAMA_TEMPERATURE=0.1
OLLAMA_KEEP_ALIVE=

OCR_DEVICE=cpu
OCR_LANGUAGE=en
OCR_CONCURRENCY=1

MAX_UPLOAD_BYTES=
MAX_PDF_PAGES=
PAGE_RENDER_DPI=
TEMP_RETENTION_DAYS=
```

Tidak ada:

```text
OPENAI_API_KEY
S3_ACCESS_KEY
DATABASE_PASSWORD
REDIS_URL
PAYMENT_SECRET
```

pada Personal MVP.

---

# 34. Python Dependency Management

Gunakan:

```text
uv
pyproject.toml
uv.lock
```

Dependency dibagi menjadi optional groups:

```text
api
worker
ocr
reconstruction
development
testing
```

Contoh:

```toml
[project.optional-dependencies]
ocr = [
  "paddleocr[doc-parser]"
]

reconstruction = [
  "reportlab",
  "weasyprint",
  "pypdf"
]
```

---

# 35. Testing Stack

## Python

```text
pytest
pytest-asyncio
httpx
```

## Frontend

```text
Vitest
Testing Library
```

## End-to-End

```text
Playwright
```

## Database Integration

Gunakan SQLite file sementara.

Tests harus mencakup:

- WAL configuration;
- migration;
- concurrent reader;
- controlled writer;
- queue recovery;
- backup;
- restore.

---

# 36. Fake Provider

Test tidak boleh membutuhkan model AI aktif.

Gunakan:

```text
FakeTranslationProvider
FakeOCRProvider
```

Fake provider menghasilkan output deterministik.

Integration test Ollama ditandai:

```text
requires_local_model
```

dan dapat dilewati pada CI standar.

---

# 37. Golden Document Tests

Sediakan fixture:

```text
digital-single-column.pdf
digital-two-column.pdf
scanned-basic.pdf
hybrid.pdf
table-heavy.pdf
image-heavy.pdf
code-heavy.pdf
footnote-heavy.pdf
```

Fixture harus:

- boleh digunakan secara hukum;
- berukuran kecil;
- tidak berisi data pribadi;
- disimpan dalam repository jika lisensinya mengizinkan.

---

# 38. Code Quality

Required commands:

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy .
uv run pytest
```

```bash
pnpm lint
pnpm typecheck
pnpm test
```

Codex tidak boleh menyelesaikan task jika:

- test gagal;
- lint gagal;
- type checking gagal;
- migration gagal;
- health check gagal.

---

# 39. Deferred Components

Komponen berikut ditunda:

```text
Authentication
Multi-user support
PostgreSQL
Redis
Celery
S3
Cloud hosting
OpenAI provider
Payment
Subscription
Advertisement
Public API
Organization workspace
Real-time collaboration
Email delivery
ClamAV
Kubernetes
EPUB
MOBI
AZW
Desktop installer
Automatic updater
```

---

# 40. Future Migration Triggers

## Move SQLite to PostgreSQL

Dipertimbangkan jika:

- aplikasi menjadi multi-user;
- diakses melalui internet;
- banyak concurrent writer;
- server deployment;
- collaborative editing.

## Move Huey to Celery

Dipertimbangkan jika:

- beberapa worker machine;
- distributed queue;
- task volume tinggi;
- independent OCR server;
- cloud deployment.

## Move Local Files to S3

Dipertimbangkan jika:

- file harus diakses dari beberapa server;
- aplikasi online;
- user account;
- remote backup;
- multi-device access.

## Add Cloud AI Provider

Dipertimbangkan jika:

- model lokal tidak memenuhi kualitas;
- pengguna mengaktifkan secara eksplisit;
- dokumen yang dikirim telah disetujui;
- estimasi biaya ditampilkan.

---

# 41. Prohibited Technical Choices

Codex tidak boleh menambahkan tanpa keputusan baru:

```text
PostgreSQL
Redis
Celery
S3
MinIO sebagai service wajib
OpenAI API
Firebase
Supabase
Clerk
Auth0
payment gateway
advertising SDK
analytics cloud
Kubernetes
PyMuPDF
```

Codex juga tidak boleh:

- membuka backend ke seluruh jaringan;
- mengirim dokumen ke internet;
- melakukan telemetry tanpa izin;
- mengunduh model besar diam-diam;
- menyimpan file di luar data directory;
- menghapus original PDF;
- menggunakan fake provider pada production path;
- membuat autentikasi yang belum dibutuhkan;
- membuat billing table;
- membuat subscription logic.

---

# 42. Codex Implementation Rules

Codex harus:

1. Membaca seluruh folder `docs/`.
2. Menggunakan Version 0.2 sebagai keputusan stack aktif.
3. Tidak mengikuti keputusan cloud pada Version 0.1.
4. Mengerjakan satu task terbatas.
5. Menambahkan test.
6. Menjalankan test.
7. Menjaga local-only networking.
8. Menjaga original file immutable.
9. Menyimpan seluruh data dalam data directory.
10. Menggunakan provider adapter.
11. Tidak mengirim data ke cloud.
12. Tidak memilih model secara hard-coded.
13. Menampilkan error jika Ollama tidak tersedia.
14. Menampilkan error jika OCR dependency tidak tersedia.
15. Tidak menganggap placeholder implementation sebagai fitur selesai.
16. Tidak menambahkan monetisasi.
17. Tidak mengubah dokumen requirement diam-diam.

---

# 43. Revised Implementation Milestones

## Milestone 1 — Local Repository Foundation

- pnpm workspace;
- uv workspace;
- local configuration;
- lint;
- type checking;
- testing;
- startup scripts.

## Milestone 2 — Local Database and Project Management

- SQLite;
- WAL mode;
- Alembic;
- project CRUD;
- local settings;
- data directory.

## Milestone 3 — Local File Import

- PDF selection;
- multipart local upload;
- file validation;
- checksum;
- immutable original;
- project folder.

## Milestone 4 — Background Worker

- Huey;
- `SqliteHuey`;
- task database;
- task status;
- retry;
- cancellation;
- progress.

## Milestone 5 — Digital PDF Analysis

- pypdf metadata;
- pdfplumber extraction;
- pypdfium2 rendering;
- Document IR;
- page preview.

## Milestone 6 — Glossary Engine

- glossary CRUD;
- term matching;
- priority;
- snapshot;
- placeholder protection;
- consistency validation.

## Milestone 7 — Ollama Translation

- Ollama health check;
- model listing;
- model selection;
- structured output;
- translation batch;
- placeholder restoration;
- retry;
- validation.

## Milestone 8 — Review Editor

- PDF.js;
- source preview;
- translated segment;
- editing;
- approval;
- warning;
- revision.

## Milestone 9 — OCR

- PaddleOCR;
- PP-StructureV3;
- scanned page detection;
- OCR confidence;
- OCR correction;
- table detection.

## Milestone 10 — Reconstruction and Export

- overlay;
- reflow;
- hybrid mode;
- image preservation;
- overflow handling;
- PDF export.

## Milestone 11 — Quality and Local Backup

- integrity validation;
- terminology validation;
- quality report;
- backup;
- restore;
- cleanup.

---

# 44. Personal MVP Acceptance Criteria

Personal MVP dianggap berhasil apabila:

1. Dapat berjalan di komputer lokal.
2. Tidak membutuhkan koneksi internet setelah setup.
3. Tidak membutuhkan API berbayar.
4. Tidak membutuhkan cloud database.
5. Tidak membutuhkan cloud storage.
6. Tidak memiliki login.
7. Data disimpan di folder lokal.
8. SQLite digunakan.
9. Huey menggunakan SQLite.
10. Ollama digunakan sebagai translation provider.
11. Model dapat dipilih pengguna.
12. Structured output digunakan.
13. PaddleOCR berjalan secara lokal.
14. PDF digital dapat diekstrak.
15. Scanned PDF dapat diproses.
16. Glossary dapat mempertahankan istilah.
17. Placeholder dapat divalidasi.
18. Gambar asli dapat dipertahankan.
19. Hasil dapat diedit.
20. Hasil dapat diekspor sebagai PDF.
21. Progress tetap tersedia saat proses panjang.
22. Job gagal dapat diulang.
23. Aplikasi hanya bind ke localhost.
24. Original file tidak berubah.
25. Tidak ada data yang dikirim ke cloud.
26. Backup lokal dapat dibuat.
27. Test utama lulus.
28. Tidak ada fitur billing.
29. Tidak ada advertisement.
30. Tidak ada dependency cloud wajib.

---

# 45. Open Decisions

Keputusan berikut belum ditetapkan:

1. Model Ollama terbaik untuk spesifikasi komputer pengguna.
2. Batas minimum RAM.
3. Batas minimum VRAM.
4. Default context length.
5. Default translation batch size.
6. Ukuran maksimum PDF.
7. Jumlah maksimum halaman.
8. Resolusi render default.
9. Apakah aplikasi akan dikemas menjadi desktop installer.
10. Apakah automatic update dibutuhkan.
11. Apakah GPU NVIDIA tersedia.
12. Apakah pengguna memerlukan dukungan AMD atau Intel GPU.
13. Lokasi default data directory pada Windows.
14. Apakah full project backup menyertakan model.
15. Berapa lama intermediate files disimpan.

Keputusan model lokal harus dibuat melalui benchmark pada hardware pengguna, bukan melalui asumsi.

---

# 46. Definition of Done

`TECH_STACK_DECISIONS.md — Version 0.2` dianggap selesai apabila:

- arsitektur local-first telah ditetapkan;
- seluruh layanan berbayar telah dihapus;
- monetisasi telah dihapus;
- multi-user telah dihapus;
- SQLite telah ditetapkan;
- local filesystem telah ditetapkan;
- Huey telah ditetapkan;
- Ollama telah ditetapkan;
- PaddleOCR tetap digunakan;
- PDF stack tetap ditetapkan;
- local networking telah dibatasi;
- backup lokal telah ditentukan;
- migration path masa depan tetap tersedia;
- Codex memiliki batas implementasi yang jelas;
- Version 0.1 secara eksplisit dinyatakan tidak berlaku untuk Personal MVP.
