# MVP SCOPE

## TransLoka Personal MVP Scope Control Specification

**Document Name:** `MVP_SCOPE.md`
**Document Version:** 0.1
**Status:** Draft
**Decision Date:** 2026-07-26
**Application Mode:** Local-First, Single User
**Primary Platform:** Windows
**Primary Input:** PDF
**Primary Language Pair:** English → Bahasa Indonesia
**Primary Output:** Translated PDF
**Monetization Status:** Tidak termasuk Personal MVP

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

---

# 1. Purpose

Dokumen ini menetapkan batas implementasi TransLoka Personal MVP.

Tujuan utamanya adalah mencegah:

* scope creep;
* overengineering;
* penambahan fitur yang belum dibutuhkan;
* penggunaan layanan berbayar;
* ketergantungan cloud;
* arsitektur multi-user sebelum waktunya;
* pembangunan fitur kosmetik sebelum fungsi inti stabil;
* Codex mengasumsikan fitur baru sebagai requirement.

Dokumen ini menjawab empat kategori keputusan:

```text
MUST IMPLEMENT
SHOULD IMPLEMENT
DEFERRED
PROHIBITED IN PERSONAL MVP
```

---

# 2. Scope Authority

Apabila terdapat konflik antara dokumen ini dan fitur tentatif pada dokumen lain, keputusan scope dalam dokumen ini yang berlaku.

Dokumen lain tetap menjadi sumber kebenaran untuk:

* behavior;
* struktur data;
* arsitektur;
* security;
* API;
* testing;
* reconstruction;
* terminology.

Fitur yang tidak tercantum sebagai `MUST IMPLEMENT` atau `SHOULD IMPLEMENT` tidak boleh otomatis dianggap sebagai bagian Personal MVP.

---

# 3. MVP Definition

TransLoka Personal MVP adalah aplikasi lokal satu pengguna yang mampu:

```text
Import PDF
→ Analyze document
→ Extract text or OCR
→ Build Document IR
→ Detect and protect terminology
→ Translate English to Indonesian using a local model
→ Allow manual review
→ Reconstruct translated PDF
→ Validate output
→ Export translated PDF
```

MVP dianggap berhasil apabila workflow tersebut dapat dijalankan dari awal sampai akhir pada:

1. PDF digital sederhana.
2. PDF digital dengan layout menengah.
3. PDF scanned sederhana.
4. PDF hybrid.
5. PDF dengan glossary.
6. PDF dengan gambar.
7. PDF dengan tabel sederhana.

---

# 4. Primary User

Personal MVP hanya memiliki satu pengguna:

```text
Project owner
```

Tidak ada:

* user account;
* guest;
* administrator;
* reviewer terpisah;
* organization member;
* collaborator.

Seluruh data dianggap dimiliki dan dikelola oleh pengguna lokal.

---

# 5. Primary Use Case

Use case utama:

> Pengguna memilih PDF berbahasa Inggris, mengatur istilah yang harus tetap berbahasa Inggris atau diterjemahkan dengan aturan tertentu, menjalankan terjemahan lokal, meninjau hasil, lalu mengekspor PDF Bahasa Indonesia tanpa menghilangkan gambar dan struktur utama dokumen.

---

# 6. Supported Input

## 6.1 Must Support

```text
PDF digital
PDF scanned
PDF hybrid
```

## 6.2 PDF Characteristics

MVP harus mendukung secara layak:

* portrait;
* landscape;
* single-column;
* two-column;
* heading;
* paragraph;
* list;
* image;
* caption;
* simple table;
* code block;
* footnote dasar;
* external hyperlink;
* page number;
* header dan footer dasar.

## 6.3 Unsupported Input

Tidak termasuk Personal MVP:

```text
DOCX
EPUB
MOBI
AZW
PPTX
XLSX
HTML website
Image folder
CBZ
DJVU
```

Format tersebut tidak boleh diimplementasikan sebelum workflow PDF stabil.

---

# 7. Supported Language Pair

Personal MVP hanya wajib mendukung:

```text
English → Bahasa Indonesia
```

Tidak wajib mendukung:

* Bahasa Indonesia → English;
* multilingual translation;
* automatic target-language selection;
* translation chain;
* bilingual multi-target export.

Language architecture dapat tetap extensible, tetapi UI dan acceptance test berfokus pada English → Indonesian.

---

# 8. Supported Application Mode

Personal MVP wajib:

* berjalan secara lokal;
* menggunakan browser lokal;
* hanya bind ke localhost;
* menyimpan data di komputer;
* menggunakan model lokal;
* bekerja tanpa internet setelah dependency dan model tersedia.

Tidak wajib:

* memiliki desktop installer;
* berjalan sebagai Windows service;
* berjalan saat startup sistem;
* dapat diakses perangkat lain.

---

# 9. MUST IMPLEMENT — Application Foundation

## 9.1 Repository

Wajib tersedia:

```text
pnpm workspace
uv workspace
locked dependencies
environment configuration
startup scripts
test scripts
```

## 9.2 Local Runtime

Wajib:

* Next.js frontend;
* FastAPI backend;
* Huey worker;
* SQLite;
* local filesystem;
* Ollama adapter;
* OCR adapter.

## 9.3 Local Startup

Pengguna harus dapat menjalankan aplikasi melalui script lokal.

Minimum:

```text
start.ps1
stop.ps1
```

Linux/macOS script dapat tersedia, tetapi Windows menjadi prioritas.

## 9.4 Health Checks

Wajib tersedia health check untuk:

* frontend;
* API;
* worker;
* database;
* filesystem;
* Ollama;
* OCR.

---

# 10. MUST IMPLEMENT — Project Management

Pengguna harus dapat:

* membuat proyek;
* memberi nama proyek;
* memilih source language;
* memilih target language;
* memilih translation style;
* memilih reconstruction mode;
* membuka proyek;
* melihat status proyek;
* mengarsipkan proyek;
* menghapus proyek dengan confirmation.

Project list harus menampilkan:

* name;
* status;
* progress;
* updated time;
* page count jika tersedia;
* warning count.

---

# 11. MUST IMPLEMENT — PDF Import

Pengguna harus dapat:

* memilih satu PDF;
* mengunggahnya ke backend lokal;
* melihat progress import;
* menerima validation error yang jelas.

Validasi wajib:

* extension;
* MIME;
* magic bytes;
* file size;
* page count;
* corruption;
* password protection;
* checksum;
* available disk space.

File asli harus:

* disalin ke project directory;
* bersifat immutable;
* memiliki checksum;
* tidak ditimpa hasil.

---

# 12. MUST IMPLEMENT — Document Analysis

Analysis wajib mendeteksi:

* page count;
* page dimensions;
* rotation;
* digital text layer;
* scanned pages;
* hybrid pages;
* images;
* table candidates;
* header;
* footer;
* page number;
* reading order dasar;
* page classification.

Output wajib menghasilkan Document IR.

---

# 13. MUST IMPLEMENT — Page Preview

Pengguna harus dapat:

* melihat thumbnail;
* membuka page preview;
* berpindah halaman;
* zoom;
* melihat segment bounding box;
* memilih segment pada halaman.

PDF.js digunakan untuk source PDF preview.

---

# 14. MUST IMPLEMENT — OCR

OCR wajib tersedia untuk:

* scanned page;
* hybrid page yang membutuhkan OCR;
* manual selected page.

OCR wajib menghasilkan:

* text;
* geometry;
* confidence;
* page association;
* block association.

Pengguna harus dapat:

* melihat hasil OCR;
* memperbaiki source text;
* menyimpan correction;
* mempertahankan raw OCR result.

OCR tidak wajib menghasilkan hasil sempurna tanpa review.

---

# 15. MUST IMPLEMENT — Document IR

Document IR wajib menyimpan:

* document;
* page;
* section dasar;
* block;
* segment;
* asset;
* table;
* table cell;
* annotation dasar;
* relationship;
* source geometry;
* target geometry;
* source text;
* target text;
* reading order;
* confidence;
* warning.

Document IR harus:

* versioned;
* serializable;
* dapat dibuat snapshot;
* tidak mencampur source dan target text.

---

# 16. MUST IMPLEMENT — Segmentation

Sistem wajib membuat segment untuk:

* heading;
* paragraph;
* list item;
* caption;
* table cell;
* header;
* footer;
* footnote;
* code block classification.

Segmentation harus menjaga:

* source order;
* block relation;
* section relation;
* page relation;
* stable ID.

---

# 17. MUST IMPLEMENT — Glossary

Pengguna harus dapat:

* membuat glossary proyek;
* menambah term;
* mengubah term;
* menonaktifkan term;
* mencari term;
* melihat occurrence;
* menerima terminology candidate;
* menolak terminology candidate.

Rule wajib:

```text
KEEP_ORIGINAL
TRANSLATE_AS
ORIGINAL_THEN_TRANSLATION
TRANSLATION_THEN_ORIGINAL
PRESERVE_ABBREVIATION
IGNORE
```

Rule lain dapat tersedia jika sudah dibutuhkan pipeline, tetapi tidak wajib memiliki UI lengkap pada versi pertama.

---

# 18. MUST IMPLEMENT — Glossary Matching

Matching wajib mendukung:

* exact match;
* phrase match;
* case-insensitive;
* whole word;
* longest match first;
* priority;
* basic scope;
* overlapping term resolution.

Scope minimum:

```text
PROJECT
DOCUMENT
SECTION
SEGMENT
```

System dan domain glossary dapat tersedia sebagai seed, tetapi UI manajemen penuh tidak wajib.

---

# 19. MUST IMPLEMENT — Placeholder Protection

Sistem wajib melindungi:

* glossary terms;
* code;
* URL;
* email;
* API endpoint;
* file path;
* citation identifier;
* numerical unit tertentu;
* acronym yang ditetapkan.

Placeholder wajib:

* unik;
* stabil dalam satu request;
* tidak bertabrakan dengan source;
* divalidasi;
* dipulihkan;
* menghasilkan critical error jika rusak.

---

# 20. MUST IMPLEMENT — Local Translation

Translation wajib menggunakan:

```text
OllamaTranslationProvider
```

Pengguna harus dapat:

* memeriksa status Ollama;
* melihat model terpasang;
* memilih model;
* menjalankan quick test;
* memulai translation;
* melihat progress;
* membatalkan translation;
* retry failed segment.

Translation wajib menggunakan:

* structured output;
* segment ID mapping;
* context;
* glossary snapshot;
* placeholder protection;
* deterministic validation.

---

# 21. MUST IMPLEMENT — Translation Styles

Minimum style:

```text
LITERAL
PROFESSIONAL
ACADEMIC
NATURAL
```

`LITERARY` dapat masuk sebagai `SHOULD IMPLEMENT`.

Style harus memengaruhi prompt, tetapi tidak boleh mengubah glossary dan protected content.

---

# 22. MUST IMPLEMENT — Translation Validation

Wajib memvalidasi:

* JSON schema;
* segment ID;
* missing segment;
* duplicate segment;
* placeholder;
* number;
* URL;
* code;
* citation;
* target language;
* empty output;
* suspicious length ratio.

Semantic validation menggunakan model kedua tidak wajib.

---

# 23. MUST IMPLEMENT — Translation Status

Setiap segment harus memiliki status.

Minimum:

```text
READY_FOR_TRANSLATION
TRANSLATING
MACHINE_TRANSLATED
TRANSLATION_FAILED
NEEDS_REVIEW
USER_EDITED
APPROVED
LOCKED
```

Project harus menampilkan:

* total segment;
* translated;
* failed;
* review required;
* approved;
* locked.

---

# 24. MUST IMPLEMENT — Review Editor

Pengguna harus dapat:

* melihat source text;
* melihat machine translation;
* melihat surrounding context;
* mengedit translation;
* menyimpan edit;
* approve;
* unapprove;
* lock;
* unlock;
* melihat warning;
* melihat revision history;
* restore revision.

Editor wajib mencegah:

* overwrite revision lama;
* edit locked segment;
* silent conflict;
* hilangnya unsaved text tanpa warning.

---

# 25. MUST IMPLEMENT — Review Queue

Review queue wajib dapat memfilter:

* low confidence;
* failed validation;
* terminology warning;
* placeholder warning;
* untranslated segment;
* unreviewed;
* page;
* section.

Tidak wajib memiliki workflow reviewer terpisah.

---

# 26. MUST IMPLEMENT — Reconstruction

Wajib tersedia:

```text
OVERLAY
REFLOW
HYBRID
```

Hybrid menjadi default.

Reconstruction wajib menangani:

* heading;
* paragraph;
* image;
* caption;
* simple table;
* code block;
* header;
* footer;
* page number;
* overflow;
* collision;
* font fallback;
* page addition.

---

# 27. MUST IMPLEMENT — Image Preservation

Sistem wajib:

* mempertahankan image;
* mempertahankan aspect ratio;
* mempertahankan crop secara wajar;
* mempertahankan relation dengan caption;
* tidak menerjemahkan text di dalam image;
* menghasilkan warning jika text dalam image terdeteksi.

---

# 28. MUST IMPLEMENT — Table Handling

Wajib:

* merekonstruksi simple table;
* memvalidasi row dan column;
* mempertahankan angka;
* wrap cell text;
* menambah row height;
* preserve complex table sebagai image jika reconstruction tidak aman;
* menghasilkan warning.

Tidak wajib merekonstruksi seluruh complex table secara editable.

---

# 29. MUST IMPLEMENT — Overflow Handling

Urutan minimum:

```text
wrap text
→ expand box
→ reduce spacing
→ reduce font within limit
→ move next block
→ reflow
→ continue next page
→ add page
→ manual review
```

Teks tidak boleh dipotong diam-diam.

---

# 30. MUST IMPLEMENT — Export

Pengguna harus dapat membuat:

```text
Translated PDF
```

Output wajib:

* dapat dibuka;
* memiliki selectable text;
* searchable;
* memiliki checksum;
* memiliki page count;
* mempertahankan major image;
* tidak memiliki critical warning;
* tidak memiliki embedded active content berbahaya.

---

# 31. MUST IMPLEMENT — Export Profiles

Minimum:

```text
STANDARD
HIGH_QUALITY
COMPACT
```

Bilingual PDF tidak wajib.

---

# 32. MUST IMPLEMENT — Jobs

Background job wajib digunakan untuk:

* analysis;
* OCR;
* terminology detection;
* translation;
* reconstruction;
* export;
* benchmark;
* backup;
* restore.

Job wajib mendukung:

* progress;
* stage;
* retry;
* cancellation;
* stale detection;
* idempotency;
* attempt history.

---

# 33. MUST IMPLEMENT — Local Storage

Wajib:

* configurable data directory;
* project directories;
* separate original;
* page render;
* OCR;
* intermediate;
* export;
* backup;
* temp.

Pengguna harus dapat melihat storage usage.

---

# 34. MUST IMPLEMENT — Database

SQLite wajib menyimpan:

* projects;
* files;
* documents;
* pages;
* blocks;
* segments;
* glossary;
* translation;
* revision;
* jobs;
* warnings;
* reconstruction;
* exports;
* models;
* benchmark;
* backup.

Wajib:

* Alembic;
* WAL;
* foreign keys;
* optimistic locking;
* backup;
* restore;
* integrity check.

---

# 35. MUST IMPLEMENT — Backup and Restore

Pengguna harus dapat:

* membuat database backup;
* membuat metadata backup;
* memverifikasi backup;
* restore backup;
* membuat pre-restore backup;
* melihat backup history.

Full project backup adalah `SHOULD IMPLEMENT`.

---

# 36. MUST IMPLEMENT — Security

Wajib:

* bind localhost;
* origin validation;
* custom client header;
* path traversal protection;
* file validation;
* command injection protection;
* `shell=False`;
* HTML escaping;
* remote resource blocking;
* prompt injection resistance;
* safe archive extraction;
* atomic file write;
* sanitized log;
* no document content in normal log.

---

# 37. MUST IMPLEMENT — Testing

Wajib tersedia:

* unit tests;
* database tests;
* API contract tests;
* security tests;
* glossary tests;
* placeholder tests;
* fake translation provider;
* fake OCR provider;
* golden PDF tests;
* digital PDF E2E;
* scanned PDF E2E;
* backup-restore test;
* final PDF validation.

---

# 38. SHOULD IMPLEMENT — Local Model Benchmark

Sebaiknya tersedia:

* hardware detection;
* quick benchmark;
* model comparison;
* structured output test;
* terminology test;
* placeholder test;
* latency;
* RAM;
* VRAM jika tersedia;
* recommendation status.

Full manual blind review dapat disederhanakan pada Personal MVP awal.

---

# 39. SHOULD IMPLEMENT — Translation Mode Literary

`LITERARY` sebaiknya tersedia karena aplikasi dapat digunakan untuk ebook atau novel.

Namun, fitur ini tidak boleh menunda:

* technical translation;
* academic translation;
* reconstruction;
* export.

---

# 40. SHOULD IMPLEMENT — Search

Sebaiknya tersedia pencarian untuk:

* source text;
* translated text;
* glossary term;
* warning;
* segment ID.

FTS5 digunakan jika tersedia.

---

# 41. SHOULD IMPLEMENT — Bulk Review

Sebaiknya pengguna dapat:

* approve beberapa segment;
* lock beberapa segment;
* retranslate selected segment;
* mark review required.

Bulk action harus menjaga revision dan locking.

---

# 42. SHOULD IMPLEMENT — Glossary Import and Export

Sebaiknya mendukung:

```text
CSV
TSV
JSON
```

Minimum viable:

```text
CSV import
CSV export
```

---

# 43. SHOULD IMPLEMENT — Full Project Backup

Sebaiknya backup dapat menyertakan:

* database;
* original PDF;
* IR snapshot;
* export;
* glossary.

Backup model Ollama tidak perlu disertakan.

---

# 44. SHOULD IMPLEMENT — Cleanup Tools

Sebaiknya pengguna dapat menghapus:

* page render cache;
* OCR cache;
* old temporary files;
* old reconstruction cache;
* old exports.

Cleanup wajib memiliki dry-run.

---

# 45. SHOULD IMPLEMENT — Debug Layout View

Sebaiknya tersedia development-only view untuk:

* block ID;
* source bounding box;
* target bounding box;
* reading order;
* collision;
* overflow;
* strategy.

Tidak harus tersedia dalam polished end-user UI.

---

# 46. SHOULD IMPLEMENT — Incremental Reconstruction

Sebaiknya hanya page yang berubah yang direkonstruksi ulang.

Namun, full-document reconstruction dapat diterima pada versi sangat awal apabila:

* hasil benar;
* page count kecil;
* cache architecture tetap dipersiapkan.

---

# 47. SHOULD IMPLEMENT — Internal Links and Bookmarks

Sebaiknya:

* external hyperlink dipertahankan;
* source bookmark dipetakan;
* internal page link diperbarui jika memungkinkan.

Kegagalan tidak boleh merusak PDF.

---

# 48. SHOULD IMPLEMENT — Table of Contents Warning

Jika pagination berubah, sistem sebaiknya:

* mendeteksi TOC;
* menampilkan warning;
* menandai nomor halaman mungkin tidak akurat.

Regenerasi otomatis TOC tidak wajib.

---

# 49. SHOULD IMPLEMENT — Accessibility Basics

Frontend sebaiknya mendukung:

* keyboard;
* visible focus;
* labels;
* semantic controls;
* warning tidak hanya menggunakan warna;
* browser zoom.

Tagged PDF accessibility tidak wajib pada Personal MVP.

---

# 50. DEFERRED — Desktop Installer

Ditunda:

* `.exe` installer;
* auto-launch;
* system tray;
* packaged desktop shell;
* automatic updater.

Personal MVP dapat dijalankan melalui local scripts.

Desktop packaging dapat dipertimbangkan setelah workflow stabil.

---

# 51. DEFERRED — Multi-User

Ditunda:

* registration;
* login;
* password;
* session;
* role;
* permission;
* invitation;
* organization;
* collaboration;
* reviewer account.

---

# 52. DEFERRED — Cloud Services

Ditunda:

* cloud database;
* S3;
* cloud backup;
* cloud OCR;
* hosted AI;
* remote deployment;
* public URL;
* remote worker.

---

# 53. DEFERRED — Monetization

Ditunda:

* subscription;
* pricing;
* credit;
* payment;
* invoice;
* advertisement;
* affiliate;
* paywall;
* usage billing.

Database tidak perlu memiliki billing table.

---

# 54. DEFERRED — Additional Formats

Ditunda:

```text
DOCX
EPUB
MOBI
AZW
PPTX
XLSX
HTML
Markdown
```

PDF tetap menjadi satu-satunya format input dan output utama Personal MVP.

---

# 55. DEFERRED — Text Inside Image Translation

Ditunda:

* OCR text inside diagrams;
* image text replacement;
* automatic redraw;
* translated chart labels;
* translated screenshots.

Personal MVP hanya memberikan warning.

---

# 56. DEFERRED — Complex Table Reconstruction

Ditunda:

* nested tables;
* irregular financial tables;
* diagram-like tables;
* complex merged-cell reconstruction;
* table redesign.

Fallback:

```text
PRESERVE_AS_IMAGE
```

---

# 57. DEFERRED — Formula Translation and Recomposition

Ditunda:

* formula OCR correction;
* LaTeX regeneration;
* formula translation;
* symbolic validation;
* equation editing.

Formula dipertahankan.

---

# 58. DEFERRED — Advanced Collaboration Editor

Ditunda:

* real-time cursor;
* comments by multiple users;
* live presence;
* concurrent editing;
* merge conflict UI multi-user;
* shared review assignments.

---

# 59. DEFERRED — Translation Memory Across Projects

Ditunda:

* fuzzy translation memory;
* organization-wide TM;
* cross-user memory;
* semantic retrieval;
* automatic sentence reuse.

Exact local cache dapat digunakan internal, tetapi tidak menjadi fitur produk awal.

---

# 60. DEFERRED — Remote Model Provider

Ditunda:

* OpenAI;
* Anthropic;
* Google Gemini;
* Azure;
* hosted inference;
* managed translation API.

Provider interface tetap disiapkan.

---

# 61. DEFERRED — Model Download from UI

Ditunda:

* browsing remote models;
* automatic download;
* progress install;
* model removal;
* model marketplace.

Pengguna mengelola Ollama melalui mekanisme Ollama sendiri.

Aplikasi hanya mendeteksi model terpasang.

---

# 62. DEFERRED — Automatic Model Selection

Ditunda:

* automatic hardware-based download;
* automatic model replacement;
* automatic quality routing;
* multiple models loaded concurrently.

Aplikasi dapat memberi recommendation, tetapi pengguna memilih.

---

# 63. DEFERRED — Advanced Semantic QA

Ditunda:

* second-model critic;
* automatic back-translation;
* entailment model;
* factual consistency model;
* learned quality estimator.

Deterministic QA tetap wajib.

---

# 64. DEFERRED — PDF/A and Accessibility Export

Ditunda:

* PDF/A validation;
* tagged PDF;
* screen-reader structure;
* accessibility tree;
* alt-text generation.

---

# 65. DEFERRED — Advanced Annotation and Form Support

Ditunda:

* interactive forms;
* signature fields;
* embedded multimedia;
* complex annotation;
* comment collaboration;
* form submission.

Personal MVP dapat preserve atau flatten jika aman.

---

# 66. PROHIBITED — Paid API Dependency

Codex tidak boleh membuat fungsi inti bergantung pada:

* OpenAI API;
* paid OCR;
* cloud storage;
* paid auth;
* paid database;
* payment API;
* commercial translation API.

---

# 67. PROHIBITED — Public Network Exposure

Codex tidak boleh:

* bind ke `0.0.0.0`;
* membuka firewall;
* membuat public tunnel;
* menggunakan ngrok;
* membuat public deployment;
* mengekspos Ollama;
* menyediakan remote API.

---

# 68. PROHIBITED — Automatic Cloud Upload

Tidak boleh:

* mengirim PDF;
* mengirim text;
* mengirim OCR;
* mengirim glossary;
* mengirim translation;
* mengirim backup;

ke layanan luar tanpa keputusan baru dan explicit user consent.

---

# 69. PROHIBITED — Authentication Overengineering

Codex tidak boleh menambahkan:

* user table;
* password;
* JWT;
* Auth.js;
* Clerk;
* Supabase Auth;
* Firebase Auth;
* role;
* permission.

---

# 70. PROHIBITED — Microservices

Personal MVP tidak boleh dipecah menjadi microservice independen.

Tetap gunakan:

```text
modular monolith
+ separate local worker
```

---

# 71. PROHIBITED — Kubernetes

Dilarang menambahkan:

* Kubernetes;
* Helm;
* service mesh;
* autoscaling;
* cluster deployment.

---

# 72. PROHIBITED — Unapproved PDF Library

Codex tidak boleh menambahkan:

```text
PyMuPDF
fitz
pymupdf4llm
```

tanpa keputusan lisensi baru.

---

# 73. PROHIBITED — Original File Mutation

Tidak boleh:

* menulis ke source PDF;
* menghapus source page;
* menggunakan source sebagai output;
* mengganti checksum;
* menyimpan translation dalam original.

---

# 74. PROHIBITED — Silent Data Loss

Dilarang:

* menghapus segment agar layout muat;
* memotong translation;
* menghapus warning;
* menimpa approved translation;
* menghapus revision;
* menghapus glossary snapshot;
* menganggap partial output sebagai final tanpa warning.

---

# 75. PROHIBITED — Fake Production Implementation

Dilarang menyelesaikan fitur dengan:

* hard-coded success;
* fake job progress;
* placeholder file;
* mock translation;
* mock OCR;
* empty PDF;
* generated static screenshot;
* TODO pada critical path.

Fake provider hanya untuk test atau explicit development mode.

---

# 76. PROHIBITED — Arbitrary Shell Execution

Codex tidak boleh:

* menggunakan `shell=True`;
* membuat command dari filename;
* menjalankan raw user input;
* mengeksekusi PDF attachment;
* menjalankan macro;
* menjalankan embedded JavaScript.

---

# 77. PROHIBITED — Raw HTML Injection

Tidak boleh menggunakan raw document text sebagai HTML.

Dilarang:

```text
dangerouslySetInnerHTML
```

untuk source, OCR, translation, glossary, atau model output.

---

# 78. PROHIBITED — Arbitrary Filesystem Access

Frontend dan API tidak boleh menerima arbitrary path untuk:

* read;
* write;
* delete;
* export;
* restore.

Semua file harus direferensikan melalui resource ID dan validated storage key.

---

# 79. PROHIBITED — Automatic Destructive Action

Tidak boleh otomatis:

* menghapus original;
* menghapus project;
* overwrite backup;
* restore database;
* vacuum saat job aktif;
* cleanup protected file;
* replace selected model.

Destructive action membutuhkan confirmation.

---

# 80. MVP User Interface Scope

Minimum screens:

```text
Dashboard
Create Project
Project Overview
Document Import
Analysis Status
Page Viewer
Glossary
Term Candidates
Translation Settings
Translation Progress
Review Editor
Warnings
Reconstruction Settings
Reconstruction Progress
Exports
Models
System Health
Backups
Settings
```

---

# 81. UI Not Required to Be Perfect

Personal MVP tidak membutuhkan:

* custom visual identity kompleks;
* animation berlebihan;
* marketing homepage;
* onboarding tour kompleks;
* dark mode;
* mobile-first layout;
* multi-theme;
* drag-and-drop dashboard customization.

UI harus:

* jelas;
* konsisten;
* dapat digunakan;
* responsif pada desktop;
* memiliki loading dan error state.

---

# 82. Mobile Scope

Mobile browser bukan target utama.

Minimum:

* halaman tidak rusak total;
* dashboard dapat dibuka;
* status dapat dilihat.

Editor PDF tidak wajib nyaman di layar kecil.

---

# 83. Project Size Limits

Nilai final ditentukan melalui benchmark, tetapi aplikasi wajib memiliki configurable limit untuk:

```text
upload size
page count
render DPI
active jobs
translation batch size
OCR concurrency
```

UI harus menjelaskan jika limit tercapai.

---

# 84. Scope Change Process

Fitur baru hanya boleh masuk jika:

1. kebutuhan jelas;
2. masuk prioritas Personal MVP;
3. dependency diperiksa;
4. security impact diperiksa;
5. database impact diperiksa;
6. API impact diperiksa;
7. test requirement dibuat;
8. dokumen scope diperbarui.

Codex tidak boleh memutuskan scope change sendiri.

---

# 85. Codex Scope Rules

Untuk setiap task, Codex wajib:

1. Membaca `MVP_SCOPE.md`.
2. Menyebut requirement yang diimplementasikan.
3. Tidak menambahkan fitur deferred.
4. Tidak menambahkan prohibited feature.
5. Tidak mengubah stack.
6. Tidak memperluas file yang diubah tanpa kebutuhan.
7. Menambahkan test.
8. Melaporkan assumption.
9. Menandai dependency task.
10. Berhenti jika requirement bertentangan.

---

# 86. Codex Task Completion Rules

Sebuah task tidak dianggap selesai jika:

* hanya ada UI tanpa backend;
* hanya ada backend tanpa integration;
* hanya ada schema tanpa migration;
* hanya ada endpoint tanpa test;
* hanya ada mock;
* error state belum ditangani;
* critical security control belum ada;
* acceptance criteria belum lulus.

---

# 87. Personal MVP Milestones

## Milestone 1 — Foundation

Scope:

* repository;
* runtime;
* startup;
* health;
* lint;
* test.

## Milestone 2 — Local Data

Scope:

* SQLite;
* migration;
* data directory;
* projects;
* settings;
* files.

## Milestone 3 — PDF Import and Analysis

Scope:

* upload;
* validation;
* checksum;
* rendering;
* extraction;
* Document IR.

## Milestone 4 — Local Jobs

Scope:

* Huey;
* job status;
* progress;
* retry;
* cancellation;
* recovery.

## Milestone 5 — Glossary

Scope:

* glossary CRUD;
* matching;
* candidate;
* placeholder;
* snapshot.

## Milestone 6 — Translation

Scope:

* Ollama;
* model selection;
* structured output;
* batching;
* validation;
* retry.

## Milestone 7 — Editor

Scope:

* source and translation;
* edit;
* revision;
* approve;
* lock;
* review queue.

## Milestone 8 — OCR

Scope:

* PaddleOCR;
* scanned page;
* OCR correction;
* confidence.

## Milestone 9 — Reconstruction

Scope:

* overlay;
* reflow;
* hybrid;
* images;
* simple table;
* overflow;
* PDF output.

## Milestone 10 — Quality, Export, and Backup

Scope:

* warning;
* quality report;
* export;
* integrity;
* backup;
* restore;
* cleanup.

---

# 88. MVP Exit Criteria

Personal MVP dinyatakan selesai apabila:

1. Aplikasi dapat dijalankan secara lokal.
2. Tidak membutuhkan paid service.
3. Project dapat dibuat.
4. PDF dapat diimpor.
5. Original checksum tidak berubah.
6. Digital PDF dapat dianalisis.
7. Scanned PDF dapat melalui OCR.
8. Document IR dapat dibuat.
9. Glossary dapat dibuat.
10. Protected term dapat dipertahankan.
11. Ollama model dapat dipilih.
12. Translation dapat dijalankan.
13. Structured output dapat divalidasi.
14. Failed segment dapat di-retry.
15. Translation dapat diedit.
16. Revision dapat disimpan.
17. Segment dapat di-approve.
18. Segment dapat di-lock.
19. Overlay reconstruction bekerja.
20. Reflow reconstruction bekerja.
21. Hybrid reconstruction bekerja.
22. Gambar dapat dipertahankan.
23. Simple table dapat direkonstruksi.
24. Critical overflow dapat dideteksi.
25. PDF hasil dapat diekspor.
26. Output PDF dapat dibuka.
27. Output text dapat dicari.
28. Backup dapat dibuat.
29. Backup dapat di-restore.
30. Digital dan scanned E2E test lulus.
31. Security test utama lulus.
32. Tidak ada critical defect.

---

# 89. MVP Non-Goals Summary

TransLoka Personal MVP bukan:

* SaaS;
* aplikasi publik;
* platform multi-user;
* layanan translation berbayar;
* editor desktop penuh;
* pengganti Adobe Acrobat;
* pengganti InDesign;
* OCR universal sempurna;
* penerjemah semua format;
* tool collaboration;
* marketplace model;
* cloud document platform.

---

# 90. Open Scope Decisions

1. Apakah `LITERARY` masuk Must atau Should.
2. Apakah full project backup masuk Must.
3. Apakah CSV glossary import wajib pada versi pertama.
4. Apakah manual block geometry editor masuk MVP.
5. Apakah bilingual PDF masuk setelah translated PDF stabil.
6. Apakah TOC regeneration masuk MVP.
7. Apakah internal bookmark restoration masuk MVP.
8. Apakah multi-document project masuk MVP.
9. Apakah section editor manual dibutuhkan.
10. Apakah FTS5 menjadi mandatory.
11. Apakah auto-detection text inside image diperlukan.
12. Apakah desktop installer menjadi milestone setelah MVP.
13. Apakah Windows menjadi platform satu-satunya.
14. Apakah full benchmark wajib sebelum pertama kali translate.
15. Apakah model validator kedua digunakan.
16. Apakah complex table warning cukup tanpa preview fallback.
17. Apakah annotations dipertahankan.
18. Apakah external link dipertahankan secara default.
19. Apakah output profile Compact wajib.
20. Apakah project duplication dibutuhkan.

---

# 91. Definition of Done

`MVP_SCOPE.md` dianggap selesai apabila:

* workflow utama telah ditetapkan;
* seluruh fitur wajib telah didaftarkan;
* fitur opsional telah dipisahkan;
* fitur deferred telah dinyatakan;
* fitur terlarang telah dinyatakan;
* batas format telah ditetapkan;
* batas bahasa telah ditetapkan;
* batas user model telah ditetapkan;
* milestone telah dipetakan;
* exit criteria telah ditetapkan;
* Codex memiliki aturan scope yang tidak ambigu;
* Personal MVP dapat dibangun tanpa cloud dan tanpa biaya layanan.
