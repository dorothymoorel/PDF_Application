# PRODUCT REQUIREMENTS DOCUMENT

## TransLoka — Local-First Personal PDF Translation Application

**Document Name:** `PRD.md`
**Document Version:** 0.2
**Status:** Draft
**Decision Date:** 2026-07-26
**Product Stage:** Personal MVP
**Primary Platform:** Windows
**Application Mode:** Local-First, Single User
**Primary Input:** PDF
**Primary Output:** Translated PDF
**Primary Language Pair:** English → Bahasa Indonesia
**Primary Translation Runtime:** Ollama Local
**Primary OCR Runtime:** Local OCR
**Monetization Status:** Deferred
**Supersedes:** `PRD.md` Version 0.1

**Related Documents:**

* `MVP_SCOPE.md`
* `TECH_STACK_DECISIONS.md`
* `ARCHITECTURE.md`
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

Version 0.2 mengubah arah produk dari rancangan aplikasi cloud atau komersial menjadi aplikasi personal yang berjalan secara lokal.

Perubahan utama:

1. Menghapus kebutuhan akun dan authentication.
2. Menghapus kebutuhan multi-user.
3. Menghapus cloud database.
4. Menghapus cloud storage.
5. Menghapus layanan translation berbayar.
6. Menghapus OCR berbayar.
7. Menghapus billing, subscription, usage credit, dan advertisement.
8. Mengganti provider translation utama menjadi Ollama lokal.
9. Mengganti penyimpanan utama menjadi SQLite dan filesystem lokal.
10. Menggunakan local background worker.
11. Menetapkan PDF sebagai satu-satunya input utama Personal MVP.
12. Menetapkan English → Bahasa Indonesia sebagai language pair utama.
13. Menetapkan Hybrid Reconstruction sebagai default.
14. Mempertahankan jalur migrasi cloud sebagai kemungkinan masa depan, bukan requirement saat ini.
15. Menetapkan keamanan localhost dan file lokal sebagai bagian requirement inti.

---

# 2. Product Overview

TransLoka adalah aplikasi penerjemah dokumen PDF berbahasa Inggris ke Bahasa Indonesia yang berjalan secara lokal pada komputer pengguna.

Aplikasi dirancang untuk menerjemahkan isi dokumen tanpa sekadar mengubah kumpulan kalimat. TransLoka harus memahami dan mempertahankan struktur dasar dokumen seperti:

* halaman;
* heading;
* paragraph;
* list;
* image;
* caption;
* table;
* code block;
* formula;
* footnote;
* header;
* footer;
* page number;
* hyperlink;
* citation;
* terminology penting.

TransLoka juga memberikan kontrol kepada pengguna atas istilah tertentu yang:

* harus tetap dalam bahasa Inggris;
* harus diterjemahkan dengan istilah tertentu;
* perlu menampilkan istilah asli dan terjemahan;
* merupakan acronym;
* tidak boleh diubah oleh model.

Setelah translation selesai, pengguna dapat meninjau hasil dalam editor, memperbaiki segment, menyetujui translation, kemudian menghasilkan PDF Bahasa Indonesia.

---

# 3. Product Vision

> Menyediakan alat penerjemah PDF lokal yang memberikan hasil Bahasa Indonesia yang natural dan dapat dikontrol, tanpa mengirim dokumen pribadi ke layanan cloud, sekaligus mempertahankan struktur dan elemen penting dokumen sumber sejauh memungkinkan.

---

# 4. Product Mission

TransLoka membantu pengguna menerjemahkan dokumen panjang dengan workflow yang:

* lebih cepat daripada translation manual penuh;
* lebih terkontrol daripada copy-paste ke chatbot;
* lebih konsisten dalam terminology;
* lebih aman untuk dokumen pribadi;
* lebih mudah direview;
* menghasilkan output PDF yang dapat digunakan.

---

# 5. Product Principles

## 5.1 Local-First

Dokumen dan proses utama tetap berada pada komputer pengguna.

## 5.2 Privacy by Default

Dokumen tidak dikirim ke server pihak ketiga secara default.

## 5.3 Source Immutability

File sumber tidak pernah dimodifikasi.

## 5.4 Human Review

Model membantu translation, tetapi pengguna tetap dapat meninjau dan mengubah hasil.

## 5.5 Terminology Control

Keputusan glossary lebih tinggi daripada preferensi model.

## 5.6 Content Completeness

Sistem tidak boleh menghapus isi agar layout terlihat rapi.

## 5.7 Readability over Pixel Perfection

Jika harus memilih, sistem memprioritaskan kelengkapan dan keterbacaan dibanding kesamaan pixel yang sempurna.

## 5.8 Explicit Failure

Kegagalan dan uncertainty harus menghasilkan warning, bukan disembunyikan.

## 5.9 Incremental Implementation

Personal MVP dibangun bertahap dan dapat diuji pada setiap milestone.

---

# 6. Problem Statement

Menerjemahkan PDF panjang secara manual memiliki beberapa masalah:

1. Teks harus diekstrak secara manual.
2. Struktur halaman mudah rusak.
3. Gambar dan caption dapat terpisah.
4. Tabel sulit dipertahankan.
5. Terminology sering tidak konsisten.
6. Istilah teknis sering diterjemahkan secara tidak tepat.
7. Copy-paste ke AI kehilangan context dokumen.
8. OCR scanned PDF dapat menghasilkan error.
9. Hasil AI masih perlu diedit.
10. Mengembalikan hasil ke format PDF memerlukan pekerjaan layout tambahan.
11. Dokumen pribadi berisiko jika dikirim ke layanan online.
12. API translation atau OCR dapat menghasilkan biaya berulang.

TransLoka menggabungkan seluruh proses tersebut dalam satu workflow lokal.

---

# 7. Product Goals

## 7.1 Primary Goals

1. Menerjemahkan PDF English ke Bahasa Indonesia.
2. Menjaga file asli tetap tidak berubah.
3. Menjalankan translation melalui model lokal.
4. Mendukung digital PDF, scanned PDF, dan hybrid PDF.
5. Mempertahankan terminology penting.
6. Mempertahankan gambar dan struktur utama.
7. Menyediakan editor translation.
8. Menghasilkan searchable translated PDF.
9. Memberikan warning atas content atau layout issue.
10. Menyimpan seluruh project secara lokal.
11. Mendukung backup dan restore lokal.
12. Tidak membutuhkan paid service.

## 7.2 Secondary Goals

1. Menyediakan benchmark model lokal.
2. Mendukung beberapa translation styles.
3. Mengurangi pekerjaan manual pada dokumen panjang.
4. Menyediakan revision history.
5. Mendukung incremental reconstruction.
6. Menyediakan laporan quality.
7. Menyediakan storage dan maintenance tools.

---

# 8. Non-Goals

Personal MVP tidak bertujuan menjadi:

* SaaS;
* aplikasi publik;
* platform multi-user;
* editor PDF penuh;
* pengganti Adobe Acrobat;
* pengganti Adobe InDesign;
* translation marketplace;
* cloud document management platform;
* real-time collaboration platform;
* universal OCR engine;
* universal document converter;
* mobile-first application;
* translation API publik.

---

# 9. Target User

## 9.1 Primary User

Pengguna Personal MVP adalah pemilik aplikasi sendiri.

Karakteristik:

* menggunakan komputer Windows;
* memiliki PDF berbahasa Inggris;
* membutuhkan hasil Bahasa Indonesia;
* ingin mengontrol terminology;
* bersedia melakukan review;
* ingin menjaga dokumen tetap lokal;
* tidak ingin membayar API per penggunaan;
* dapat menjalankan local application dan Ollama.

## 9.2 Potential Future Users

Bukan bagian Personal MVP:

* translator professional;
* researcher;
* student;
* technical writer;
* publisher;
* enterprise reviewer;
* translation team.

---

# 10. Primary Use Cases

## UC-01 — Translate Digital PDF

Pengguna mengimpor PDF digital, memilih model lokal, menetapkan glossary, menjalankan translation, meninjau hasil, dan mengekspor translated PDF.

## UC-02 — Translate Scanned PDF

Pengguna mengimpor scanned PDF, menjalankan OCR lokal, memperbaiki source OCR yang salah, menerjemahkan, dan mengekspor searchable PDF.

## UC-03 — Preserve Technical Terms

Pengguna menetapkan istilah seperti:

```text id="um8r9d"
workflow
stakeholder
use case
machine learning
```

agar diterjemahkan sesuai aturan tertentu.

## UC-04 — Review Low-Confidence Translation

Pengguna membuka review queue dan memperbaiki segment yang memiliki warning.

## UC-05 — Retranslate Selected Segments

Pengguna mengubah glossary kemudian hanya menerjemahkan ulang segment yang terdampak.

## UC-06 — Recover Project

Pengguna membuat backup, mengalami masalah pada data, lalu melakukan restore.

---

# 11. Core User Journey

```text id="skt1ey"
Start application
        ↓
Create project
        ↓
Import PDF
        ↓
Validate file
        ↓
Analyze document
        ↓
Extract text or run OCR
        ↓
Review source structure
        ↓
Detect terminology candidates
        ↓
Create or confirm glossary
        ↓
Select local model
        ↓
Run translation
        ↓
Review warnings and translations
        ↓
Edit and approve segments
        ↓
Configure reconstruction
        ↓
Generate translated PDF
        ↓
Validate export
        ↓
Download or open local output
```

---

# 12. Personal MVP Product Boundary

Personal MVP wajib memenuhi workflow penuh dari import sampai export.

Personal MVP tidak harus:

* memiliki installer `.exe`;
* memiliki cloud sync;
* memiliki login;
* memiliki billing;
* memiliki collaboration;
* menerjemahkan format selain PDF;
* mendukung seluruh language pair;
* merekonstruksi complex table secara sempurna;
* menerjemahkan text yang menyatu di dalam image;
* menghasilkan pixel-perfect output untuk seluruh PDF.

---

# 13. Functional Requirements — Application Runtime

## FR-APP-001

Aplikasi harus berjalan secara lokal.

## FR-APP-002

Frontend dan backend hanya bind ke localhost secara default.

## FR-APP-003

Aplikasi harus dapat dijalankan melalui script Windows.

## FR-APP-004

Aplikasi harus menampilkan health status untuk:

* API;
* database;
* worker;
* filesystem;
* Ollama;
* OCR.

## FR-APP-005

Aplikasi harus dapat berjalan tanpa internet setelah dependency dan model lokal tersedia.

## FR-APP-006

Aplikasi tidak boleh bergantung pada layanan berbayar.

---

# 14. Functional Requirements — Project Management

## FR-PRJ-001

Pengguna dapat membuat project baru.

## FR-PRJ-002

Project menyimpan:

* name;
* description;
* source language;
* target language;
* document type;
* translation style;
* reconstruction mode;
* status;
* progress.

## FR-PRJ-003

Pengguna dapat membuka project lama.

## FR-PRJ-004

Pengguna dapat mengarsipkan project.

## FR-PRJ-005

Pengguna dapat menghapus project dengan confirmation.

## FR-PRJ-006

Project tetap tersedia setelah aplikasi restart.

## FR-PRJ-007

Dashboard menampilkan progress dan warning summary.

---

# 15. Functional Requirements — PDF Import

## FR-IMP-001

Pengguna dapat memilih satu PDF dari komputer.

## FR-IMP-002

Upload browser dikirim ke backend lokal.

## FR-IMP-003

File harus divalidasi berdasarkan:

* extension;
* MIME signal;
* magic bytes;
* ukuran;
* page count;
* parser readability;
* password protection;
* disk availability.

## FR-IMP-004

Invalid PDF harus menghasilkan error yang dapat ditindaklanjuti.

## FR-IMP-005

Original PDF harus disimpan sebagai immutable file.

## FR-IMP-006

SHA-256 checksum harus dicatat.

## FR-IMP-007

File asli tidak boleh digunakan sebagai output destination.

## FR-IMP-008

Temporary upload harus dibersihkan jika import gagal.

---

# 16. Functional Requirements — Document Analysis

## FR-ANA-001

Sistem harus mendeteksi jumlah halaman.

## FR-ANA-002

Sistem harus mendeteksi page dimensions dan rotation.

## FR-ANA-003

Sistem harus menentukan apakah halaman:

* digital;
* scanned;
* hybrid.

## FR-ANA-004

Sistem harus mendeteksi text layer.

## FR-ANA-005

Sistem harus menghasilkan thumbnail.

## FR-ANA-006

Sistem harus menghasilkan page render untuk editor.

## FR-ANA-007

Sistem harus mendeteksi image dan table candidates.

## FR-ANA-008

Sistem harus mendeteksi embedded JavaScript dan attachment.

## FR-ANA-009

Active content tidak boleh dijalankan.

---

# 17. Functional Requirements — Document IR

## FR-IR-001

Sistem harus membuat Document IR yang versioned.

## FR-IR-002

Document IR harus memuat:

* document;
* page;
* section;
* block;
* segment;
* asset;
* table;
* cell;
* annotation;
* relationship;
* warning.

## FR-IR-003

Setiap entity harus memiliki stable identifier.

## FR-IR-004

Source dan target data harus disimpan terpisah.

## FR-IR-005

Geometry harus menggunakan canonical coordinate system.

## FR-IR-006

Reading order harus tersimpan.

## FR-IR-007

Document IR harus dapat diserialisasi ke JSON.

## FR-IR-008

Document IR harus dapat dibuat snapshot.

## FR-IR-009

Snapshot tidak boleh ditimpa.

---

# 18. Functional Requirements — Text Extraction

## FR-EXT-001

Digital PDF harus menggunakan native extraction bila tersedia.

## FR-EXT-002

Sistem harus mempertahankan source text asli hasil extraction.

## FR-EXT-003

Sistem harus mendeteksi:

* heading;
* paragraph;
* list;
* caption;
* header;
* footer;
* page number;
* code;
* table cell.

## FR-EXT-004

Sistem harus menghubungkan text dengan geometry.

## FR-EXT-005

Sistem harus menghasilkan reading order.

## FR-EXT-006

Uncertain reading order harus menghasilkan warning.

---

# 19. Functional Requirements — OCR

## FR-OCR-001

Sistem harus menyediakan local OCR.

## FR-OCR-002

OCR dapat dijalankan otomatis pada scanned page.

## FR-OCR-003

OCR dapat dijalankan manual pada selected page.

## FR-OCR-004

OCR menghasilkan:

* text;
* geometry;
* confidence;
* page relation.

## FR-OCR-005

Raw OCR output harus dipertahankan.

## FR-OCR-006

Pengguna dapat memperbaiki resolved source text.

## FR-OCR-007

Correction tidak boleh menimpa raw OCR text.

## FR-OCR-008

Low-confidence OCR harus masuk review queue.

## FR-OCR-009

OCR tidak boleh menggunakan cloud service.

---

# 20. Functional Requirements — Segmentation

## FR-SEG-001

Sistem harus membagi source menjadi translation segments.

## FR-SEG-002

Segment harus menyimpan hubungan dengan:

* document;
* section;
* page;
* block;
* reading order.

## FR-SEG-003

Segment tidak boleh memotong:

* URL;
* code identifier;
* placeholder;
* citation identifier.

## FR-SEG-004

Segment harus memiliki status translation dan review.

## FR-SEG-005

Segment ID tidak berubah hanya karena translation berubah.

---

# 21. Functional Requirements — Glossary

## FR-GLS-001

Pengguna dapat membuat glossary project.

## FR-GLS-002

Pengguna dapat menambah, mengubah, menonaktifkan, dan mencari term.

## FR-GLS-003

Rule minimum:

```text id="pkn71y"
KEEP_ORIGINAL
TRANSLATE_AS
ORIGINAL_THEN_TRANSLATION
TRANSLATION_THEN_ORIGINAL
PRESERVE_ABBREVIATION
IGNORE
```

## FR-GLS-004

Matching harus mendukung:

* exact;
* phrase;
* case-insensitive;
* whole word;
* longest match first.

## FR-GLS-005

Glossary scope minimum:

```text id="wlq7iy"
PROJECT
DOCUMENT
SECTION
SEGMENT
```

## FR-GLS-006

Term occurrence harus dapat dilihat.

## FR-GLS-007

Sistem harus mendeteksi terminology candidates.

## FR-GLS-008

Candidate tidak otomatis menjadi glossary term.

## FR-GLS-009

Conflicting rules harus menghasilkan warning.

## FR-GLS-010

Translation batch harus menggunakan immutable glossary snapshot.

---

# 22. Functional Requirements — Protected Content

## FR-PRO-001

Sistem harus melindungi:

* glossary terms;
* URL;
* email;
* code;
* API endpoint;
* file path;
* citation;
* acronym terpilih.

## FR-PRO-002

Protected content harus diganti dengan placeholder sebelum model menerima source.

## FR-PRO-003

Placeholder harus unik.

## FR-PRO-004

Sistem harus mendeteksi:

* missing placeholder;
* changed placeholder;
* duplicate placeholder;
* unknown placeholder.

## FR-PRO-005

Placeholder mismatch merupakan critical failure.

## FR-PRO-006

Model tidak boleh dianggap berhasil jika placeholder inventory tidak valid.

---

# 23. Functional Requirements — Local Model Management

## FR-MDL-001

Aplikasi harus mendeteksi Ollama lokal.

## FR-MDL-002

Aplikasi harus menampilkan model yang telah terpasang.

## FR-MDL-003

Pengguna dapat memilih model translation.

## FR-MDL-004

Aplikasi tidak boleh mengunduh model tanpa tindakan pengguna.

## FR-MDL-005

Model tidak boleh di-hard-code sebagai default universal.

## FR-MDL-006

Aplikasi harus menyediakan quick model test.

## FR-MDL-007

Remote model endpoint harus ditolak secara default.

## FR-MDL-008

Model output harus diperlakukan sebagai untrusted data.

---

# 24. Functional Requirements — Translation

## FR-TRN-001

Translation menggunakan local Ollama provider.

## FR-TRN-002

Translation harus menggunakan structured output.

## FR-TRN-003

Setiap output harus memuat segment ID yang dikenal.

## FR-TRN-004

Sistem harus mendeteksi:

* missing segment;
* duplicate segment;
* unknown segment;
* invalid JSON;
* empty translation.

## FR-TRN-005

Translation harus menggunakan context secukupnya.

## FR-TRN-006

Translation harus menggunakan glossary snapshot.

## FR-TRN-007

Translation harus mendukung style:

```text id="1qw3ik"
LITERAL
PROFESSIONAL
ACADEMIC
NATURAL
```

## FR-TRN-008

`LITERARY` berstatus optional untuk Personal MVP.

## FR-TRN-009

Pengguna dapat memulai, membatalkan, dan retry translation.

## FR-TRN-010

Successful result tidak boleh digandakan saat retry.

## FR-TRN-011

Locked segment tidak boleh diterjemahkan ulang.

## FR-TRN-012

Model tidak memiliki akses ke filesystem, database, shell, atau network tool.

---

# 25. Functional Requirements — Translation Validation

## FR-VAL-001

Sistem harus memvalidasi placeholder.

## FR-VAL-002

Sistem harus memvalidasi segment mapping.

## FR-VAL-003

Sistem harus memvalidasi angka.

## FR-VAL-004

Sistem harus memvalidasi URL.

## FR-VAL-005

Sistem harus memvalidasi email.

## FR-VAL-006

Sistem harus memvalidasi code.

## FR-VAL-007

Sistem harus memvalidasi citation identifier.

## FR-VAL-008

Sistem harus memeriksa target language.

## FR-VAL-009

Sistem harus memeriksa suspicious length ratio.

## FR-VAL-010

Failed validation menghasilkan warning atau translation failure berdasarkan severity.

## FR-VAL-011

Semantic second-model validation tidak wajib.

---

# 26. Functional Requirements — Review Editor

## FR-REV-001

Pengguna dapat melihat source dan translation berdampingan.

## FR-REV-002

Pengguna dapat melihat surrounding context.

## FR-REV-003

Pengguna dapat mengedit translation.

## FR-REV-004

Setiap edit membuat revision.

## FR-REV-005

Pengguna dapat approve dan unapprove segment.

## FR-REV-006

Pengguna dapat lock dan unlock segment.

## FR-REV-007

Locked segment tidak dapat diedit.

## FR-REV-008

Pengguna dapat melihat revision history.

## FR-REV-009

Pengguna dapat memulihkan revision lama.

## FR-REV-010

Restore revision menghasilkan revision baru.

## FR-REV-011

Unsaved change tidak boleh hilang tanpa warning.

## FR-REV-012

Revision conflict harus menghasilkan `409 Conflict`.

---

# 27. Functional Requirements — Review Queue

## FR-RQU-001

Review queue harus menampilkan segment yang:

* gagal validation;
* low confidence;
* memiliki terminology warning;
* belum direview;
* translation failed;
* memiliki source OCR uncertainty.

## FR-RQU-002

Pengguna dapat memfilter berdasarkan:

* page;
* section;
* severity;
* warning type;
* review status.

## FR-RQU-003

Pengguna dapat berpindah langsung ke segment terkait.

## FR-RQU-004

Warning resolution harus tercatat.

---

# 28. Functional Requirements — Reconstruction

## FR-REC-001

Reconstruction mode minimum:

```text id="qyvydn"
OVERLAY
REFLOW
HYBRID
```

## FR-REC-002

Hybrid menjadi default.

## FR-REC-003

Sistem harus mempertahankan page dimensions bila memungkinkan.

## FR-REC-004

Sistem harus mempertahankan image.

## FR-REC-005

Sistem harus mempertahankan formula.

## FR-REC-006

Sistem harus mempertahankan code content.

## FR-REC-007

Sistem harus merekonstruksi simple table.

## FR-REC-008

Complex table dapat dipertahankan sebagai image.

## FR-REC-009

Sistem harus mendeteksi text overflow.

## FR-REC-010

Sistem harus mendeteksi collision.

## FR-REC-011

Teks tidak boleh dipotong diam-diam.

## FR-REC-012

Sistem dapat menambah halaman.

## FR-REC-013

Sistem harus menyimpan source-target page mapping.

## FR-REC-014

Sistem harus menggunakan font fallback jika font asli tidak tersedia.

## FR-REC-015

Source file tetap read-only.

---

# 29. Functional Requirements — Reconstruction Fallback

Fallback minimum:

```text id="2cniqo"
Wrap text
→ expand text box
→ reduce spacing
→ reduce font within safe limit
→ move following block
→ reflow block
→ continue next page
→ add page
→ require manual review
```

Critical unresolved overflow harus memblokir final export.

---

# 30. Functional Requirements — Images

## FR-IMG-001

Image harus mempertahankan aspect ratio.

## FR-IMG-002

Image harus mempertahankan relation dengan caption.

## FR-IMG-003

Image tidak boleh dikompresi agresif tanpa setting pengguna.

## FR-IMG-004

Text yang menyatu dalam image tidak wajib diterjemahkan.

## FR-IMG-005

Text di dalam image yang tidak diterjemahkan harus menghasilkan warning jika terdeteksi.

---

# 31. Functional Requirements — Tables

## FR-TBL-001

Sistem harus mendeteksi simple table.

## FR-TBL-002

Sistem harus menyimpan row, column, dan cell.

## FR-TBL-003

Translation table harus mempertahankan angka.

## FR-TBL-004

Cell text dapat di-wrap.

## FR-TBL-005

Row height dapat diperbesar.

## FR-TBL-006

Header dapat diulang pada page continuation.

## FR-TBL-007

Complex table dapat menggunakan fallback image.

## FR-TBL-008

Table tidak boleh silently corrupted.

---

# 32. Functional Requirements — Code and Formula

## FR-COD-001

Code content tidak boleh diterjemahkan secara default.

## FR-COD-002

Code indentation harus dipertahankan.

## FR-COD-003

Code menggunakan monospace font.

## FR-FRM-001

Formula dipertahankan sebagai source asset atau representation.

## FR-FRM-002

Formula symbol tidak boleh diubah model.

## FR-FRM-003

Equation number harus dipertahankan.

---

# 33. Functional Requirements — Links and Citations

## FR-LNK-001

External link dengan scheme aman dapat dipertahankan.

## FR-LNK-002

Allowed scheme:

```text id="a77eey"
http
https
mailto
```

## FR-LNK-003

Unsafe scheme harus dinonaktifkan.

## FR-LNK-004

Link tidak boleh di-fetch selama reconstruction.

## FR-CIT-001

Citation identifier harus dipertahankan.

## FR-CIT-002

Citation tidak boleh diciptakan baru oleh model.

---

# 34. Functional Requirements — Export

## FR-EXP-001

Pengguna dapat membuat translated PDF.

## FR-EXP-002

Export harus versioned.

## FR-EXP-003

Export lama tidak boleh ditimpa.

## FR-EXP-004

Output harus dapat dibuka oleh PDF reader umum.

## FR-EXP-005

Output harus memiliki selectable text.

## FR-EXP-006

Output harus searchable.

## FR-EXP-007

Output harus memiliki checksum.

## FR-EXP-008

Output harus divalidasi sebelum status `COMPLETED`.

## FR-EXP-009

Output tidak boleh membawa embedded JavaScript atau unsafe active content.

## FR-EXP-010

Export profiles minimum:

```text id="r6rfy8"
STANDARD
HIGH_QUALITY
COMPACT
```

---

# 35. Functional Requirements — Background Jobs

## FR-JOB-001

Proses panjang harus berjalan melalui background job.

## FR-JOB-002

Job digunakan untuk:

* analysis;
* OCR;
* terminology detection;
* translation;
* reconstruction;
* export;
* benchmark;
* backup;
* restore;
* maintenance berat.

## FR-JOB-003

Job harus memiliki:

* status;
* progress;
* current stage;
* heartbeat;
* attempts;
* retry;
* cancellation;
* error.

## FR-JOB-004

Job harus idempotent jika operation dapat dikirim ulang.

## FR-JOB-005

Stale job harus dapat dideteksi.

## FR-JOB-006

Incomplete artifact tidak boleh dianggap final.

## FR-JOB-007

Application database dan queue database harus terpisah.

---

# 36. Functional Requirements — Storage

## FR-STO-001

Semua data berada dalam managed local data directory.

## FR-STO-002

Database hanya menyimpan relative storage keys.

## FR-STO-003

Binary file disimpan di filesystem.

## FR-STO-004

Aplikasi harus menampilkan storage usage.

## FR-STO-005

Aplikasi harus memiliki temporary file cleanup.

## FR-STO-006

Cleanup harus mendukung dry-run.

## FR-STO-007

Cleanup tidak boleh menghapus original secara otomatis.

---

# 37. Functional Requirements — Backup and Restore

## FR-BKP-001

Pengguna dapat membuat database-only backup.

## FR-BKP-002

Pengguna dapat membuat metadata backup.

## FR-BKP-003

Full project backup berstatus recommended.

## FR-BKP-004

Backup harus memiliki:

* manifest;
* checksum;
* application version;
* database schema version;
* content inventory.

## FR-BKP-005

Backup harus diverifikasi.

## FR-BKP-006

Restore membutuhkan explicit confirmation.

## FR-BKP-007

Restore harus membuat pre-restore backup secara default.

## FR-BKP-008

Restore dilakukan ke temporary location terlebih dahulu.

## FR-BKP-009

Database replacement dilakukan setelah integrity check berhasil.

## FR-BKP-010

Unsafe archive harus ditolak.

---

# 38. Functional Requirements — Maintenance

## FR-MNT-001

Aplikasi harus menyediakan database integrity check.

## FR-MNT-002

Aplikasi harus menyediakan file integrity check.

## FR-MNT-003

Aplikasi harus menyediakan orphan file scan.

## FR-MNT-004

Aplikasi harus menyediakan temp cleanup.

## FR-MNT-005

Aplikasi harus menyediakan cache cleanup.

## FR-MNT-006

Database vacuum hanya berjalan saat aman.

## FR-MNT-007

Maintenance result harus tersimpan.

---

# 39. Functional Requirements — Local Model Benchmark

## FR-BEN-001

Aplikasi harus dapat menyimpan hardware profile.

## FR-BEN-002

Aplikasi harus dapat menjalankan quick benchmark.

## FR-BEN-003

Benchmark harus memeriksa:

* structured output;
* terminology;
* placeholders;
* numbers;
* translation quality dasar;
* latency;
* memory.

## FR-BEN-004

Full benchmark berstatus recommended.

## FR-BEN-005

Model recommendation tidak boleh berdasarkan nama saja.

## FR-BEN-006

Model yang gagal critical test tidak boleh direkomendasikan.

---

# 40. Non-Functional Requirements — Privacy

## NFR-PRV-001

Dokumen tidak dikirim ke cloud secara default.

## NFR-PRV-002

Aplikasi tidak menggunakan telemetry.

## NFR-PRV-003

Aplikasi tidak menggunakan remote analytics.

## NFR-PRV-004

Normal log tidak menyimpan document text.

## NFR-PRV-005

Normal log tidak menyimpan raw prompts.

## NFR-PRV-006

Normal log tidak menyimpan absolute user path.

## NFR-PRV-007

Remote model provider tidak termasuk Personal MVP.

---

# 41. Non-Functional Requirements — Security

## NFR-SEC-001

API hanya bind ke loopback.

## NFR-SEC-002

Foreign origin harus ditolak.

## NFR-SEC-003

Mutation membutuhkan custom client header.

## NFR-SEC-004

Path traversal harus diblokir.

## NFR-SEC-005

Unsafe symlink harus diblokir.

## NFR-SEC-006

Command execution tidak menggunakan `shell=True`.

## NFR-SEC-007

User-controlled filename tidak digunakan sebagai command string.

## NFR-SEC-008

Source text harus di-escape sebelum digunakan dalam HTML.

## NFR-SEC-009

WeasyPrint tidak boleh mengambil remote resource.

## NFR-SEC-010

Backup extraction harus mencegah zip slip.

## NFR-SEC-011

Model output tidak dapat menentukan action aplikasi.

## NFR-SEC-012

Unsafe PDF active content tidak diteruskan ke export.

---

# 42. Non-Functional Requirements — Reliability

## NFR-REL-001

Original PDF tidak boleh berubah.

## NFR-REL-002

Important file menggunakan atomic write.

## NFR-REL-003

SQLite menggunakan WAL.

## NFR-REL-004

Database foreign key aktif.

## NFR-REL-005

Transaction harus pendek.

## NFR-REL-006

Worker crash tidak boleh merusak database.

## NFR-REL-007

Stale job dapat dipulihkan.

## NFR-REL-008

Backup harus dapat diverifikasi.

## NFR-REL-009

Valid output lama tidak dihapus saat operation baru gagal.

---

# 43. Non-Functional Requirements — Performance

Performance target bergantung pada hardware dan model.

Aplikasi harus:

* menggunakan concurrency rendah secara default;
* memproses page secara bertahap;
* tidak memuat seluruh PDF besar ke RAM;
* menggunakan cache untuk page render;
* menggunakan batch translation;
* membatasi OCR concurrency;
* menyediakan cancellation;
* menampilkan progress;
* memeriksa disk space.

Target universal waktu translation tidak ditetapkan sebelum benchmark hardware.

---

# 44. Non-Functional Requirements — Usability

## NFR-UX-001

UI desktop harus dapat digunakan tanpa command line untuk workflow utama.

## NFR-UX-002

Loading, empty, success, dan error states harus tersedia.

## NFR-UX-003

Error harus menjelaskan tindakan yang dapat dilakukan.

## NFR-UX-004

Warning tidak hanya ditampilkan melalui warna.

## NFR-UX-005

Keyboard navigation dasar harus tersedia pada editor.

## NFR-UX-006

Unsaved changes harus dilindungi.

## NFR-UX-007

Technical terminology yang sulit harus disederhanakan pada UI.

---

# 45. Non-Functional Requirements — Accessibility

Personal MVP minimum:

* semantic form labels;
* visible focus;
* keyboard-accessible control;
* warning text;
* heading structure;
* zoom support;
* modal focus handling.

Tagged PDF dan PDF accessibility tree berstatus deferred.

---

# 46. Non-Functional Requirements — Maintainability

Aplikasi menggunakan modular monolith.

Module boundary minimum:

```text id="tm1rvh"
Web frontend
FastAPI API
Application services
Domain packages
Repositories
SQLite
Filesystem storage
Worker
Translation adapters
OCR adapters
Reconstruction adapters
Quality services
```

External dependency harus menggunakan adapter jika replaceability dibutuhkan.

---

# 47. Non-Functional Requirements — Testability

Sistem harus mendukung:

* FakeTranslationProvider;
* FakeOCRProvider;
* temporary SQLite database;
* temporary data directory;
* golden PDF fixtures;
* deterministic glossary tests;
* security tests;
* end-to-end tests.

Standard automated test tidak bergantung pada paid service atau internet.

---

# 48. UI Information Architecture

Minimum pages:

```text id="cp7vbn"
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
Review Queue
Warnings
Reconstruction Settings
Reconstruction Progress
Exports
Models
Benchmarks
Backups
Storage
System Health
Application Settings
```

---

# 49. Dashboard Requirements

Dashboard menampilkan:

* active projects;
* archived projects;
* project status;
* progress;
* last updated;
* page count;
* translation progress;
* warning count;
* export availability;
* create project action.

---

# 50. Project Overview Requirements

Project overview menampilkan:

* document summary;
* analysis status;
* glossary status;
* translation status;
* review status;
* reconstruction status;
* export status;
* storage usage;
* current active job;
* critical warnings.

---

# 51. Editor Requirements

Editor minimum terdiri dari:

* page preview;
* source segment;
* translation field;
* previous and next context;
* glossary matches;
* warnings;
* revision access;
* approve;
* lock;
* save;
* retranslate.

---

# 52. Project Status Model

```text id="z91yxd"
CREATED
IMPORTING
ANALYZING
WAITING_FOR_SETTINGS
EXTRACTING
OCR_PROCESSING
TERMS_DETECTED
WAITING_FOR_GLOSSARY
TRANSLATING
READY_FOR_REVIEW
REVIEWING
RECONSTRUCTING
READY_FOR_EXPORT
COMPLETED
PARTIALLY_COMPLETED
FAILED
CANCELLED
ARCHIVED
DELETION_QUEUED
```

Status transition harus divalidasi backend.

---

# 53. Segment Status Model

```text id="wdp4si"
CREATED
EXTRACTED
OCR_REQUIRED
OCR_COMPLETED
NORMALIZED
TERMS_DETECTED
PROTECTED
READY_FOR_TRANSLATION
TRANSLATING
MACHINE_TRANSLATED
TRANSLATION_FAILED
NEEDS_REVIEW
USER_EDITED
APPROVED
LOCKED
IGNORED
NOT_TRANSLATABLE
```

---

# 54. Warning Severity

```text id="yvq4ox"
INFO
LOW
MEDIUM
HIGH
CRITICAL
```

Critical warning dapat memblokir operation.

---

# 55. Critical Blocking Conditions

Operation final harus diblokir jika terdapat:

```text id="wkcj6u"
MISSING_TRANSLATED_SEGMENT
PLACEHOLDER_RESTORATION_FAILED
ORIGINAL_FILE_CHECKSUM_MISMATCH
OUTPUT_PDF_CORRUPTED
PATH_TRAVERSAL_DETECTED
CRITICAL_TEXT_CLIPPING
CRITICAL_LAYOUT_COLLISION
TABLE_STRUCTURE_CORRUPTED_CRITICAL
```

---

# 56. Success Metrics

Karena Personal MVP digunakan sendiri, metrics tidak dikirim ke analytics.

Metrics lokal:

## 56.1 Completion

* persentase project yang mencapai export;
* jumlah failed segment;
* jumlah review-required segment.

## 56.2 Translation Quality

* placeholder pass rate;
* numerical integrity pass rate;
* terminology consistency;
* manual edit rate;
* approval rate.

## 56.3 Reconstruction Quality

* missing segment count;
* clipping count;
* collision count;
* major image preservation;
* table fallback count.

## 56.4 Reliability

* job retry success;
* stale job recovery;
* backup verification;
* restore success;
* source checksum pass.

## 56.5 Performance

* page analysis time;
* OCR time per page;
* translation latency;
* reconstruction time per page;
* peak RAM;
* disk usage.

---

# 57. Personal MVP Target Metrics

Initial targets:

```text id="hmhhi3"
Original checksum integrity             100%
Required segment completeness          100%
Placeholder integrity                  100%
Critical clipping in final export        0
Critical collision in final export       0
Final PDF open success                 100%
Backup verification success            100%
Digital E2E completion                 100%
Scanned E2E completion                 100%
```

Translation quality score ditentukan berdasarkan selected local model benchmark.

---

# 58. Acceptance Scenarios

## AS-01 — Digital PDF

Given:

* valid English digital PDF;
* local model selected;
* glossary configured.

When:

* user starts full workflow.

Then:

* source remains unchanged;
* segments are translated;
* terms follow glossary;
* user can review;
* PDF export is searchable and valid.

## AS-02 — Scanned PDF

Given:

* scanned PDF;
* OCR available.

When:

* user runs OCR and corrects source.

Then:

* raw OCR remains;
* corrected source is used;
* translation can run;
* final output contains searchable translated text.

## AS-03 — Placeholder Failure

Given:

* model alters protected placeholder.

When:

* validation runs.

Then:

* translation is rejected;
* warning is critical;
* result is not stored as successful.

## AS-04 — Worker Crash

Given:

* translation job running.

When:

* worker terminates unexpectedly.

Then:

* job becomes stale;
* completed batches remain;
* incomplete batches can retry;
* duplicates are not created.

## AS-05 — Backup Restore

Given:

* project with reviewed translation and export.

When:

* backup is created, verified, and restored.

Then:

* project, revisions, glossary, and files return consistently.

---

# 59. Product Risks

## Risk 1 — Translation Quality Varies by Model

Mitigation:

* benchmark;
* glossary;
* review;
* retry;
* multiple candidate models.

## Risk 2 — Hardware Cannot Run Large Model

Mitigation:

* low-resource profile;
* smaller quantized model;
* smaller batch;
* concurrency 1.

## Risk 3 — Layout Preservation Is Inconsistent

Mitigation:

* hybrid reconstruction;
* overflow detection;
* page addition;
* warnings;
* manual review.

## Risk 4 — OCR Errors Affect Translation

Mitigation:

* confidence;
* source correction;
* raw OCR preservation;
* review queue.

## Risk 5 — Disk Usage Becomes Large

Mitigation:

* storage dashboard;
* cleanup;
* cache categories;
* disk-space check.

## Risk 6 — Malicious PDF

Mitigation:

* validation;
* parser isolation;
* active content detection;
* limits;
* safe output.

## Risk 7 — Scope Creep

Mitigation:

* `MVP_SCOPE.md`;
* atomic Codex tasks;
* milestone gates;
* deferred list.

---

# 60. Dependencies

## Required Local Dependencies

* Node.js 24;
* pnpm;
* Python 3.12;
* uv;
* Ollama;
* selected model;
* OCR dependencies;
* WeasyPrint runtime requirements;
* supported PDF libraries.

## No Required External Services

Personal MVP tidak memerlukan:

* cloud account;
* API key;
* payment account;
* hosted database;
* hosted storage.

---

# 61. Deferred Features

Deferred:

```text id="55ph78"
Desktop installer
Automatic updater
Authentication
Multi-user
Cloud sync
Cloud backup
Remote provider
Payment
Subscription
Advertisement
DOCX
EPUB
MOBI
PPTX
XLSX
Text-in-image replacement
Complex table recreation
Translation memory across projects
Semantic second-model validation
Real-time collaboration
Public API
```

---

# 62. Prohibited Features in Personal MVP

Dilarang:

* paid API dependency;
* automatic cloud upload;
* public network exposure;
* hidden telemetry;
* user account system;
* billing system;
* advertisement system;
* PyMuPDF dependency;
* source PDF mutation;
* arbitrary shell execution;
* arbitrary filesystem access;
* fake production translation;
* silent content deletion;
* raw document logging.

---

# 63. Implementation Milestones

```text id="a5yktw"
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
M11 Quality, Backup, Recovery, and Hardening
```

Detail implementation mengikuti `IMPLEMENTATION_PLAN.md` dan `CODEX_TASKS.md`.

---

# 64. Release Criteria

Personal MVP siap digunakan apabila:

1. Dapat dijalankan lokal.
2. Tidak membutuhkan paid service.
3. Project dapat dibuat.
4. PDF dapat diimpor.
5. Source checksum tetap.
6. Digital PDF dapat dianalisis.
7. Scanned PDF dapat di-OCR.
8. Document IR dapat dibuat.
9. Glossary dapat dikontrol.
10. Placeholder validation bekerja.
11. Local model dapat dipilih.
12. Translation dapat berjalan.
13. Failed segment dapat retry.
14. Review editor dapat digunakan.
15. Revision history tersedia.
16. Approved segment terlindungi.
17. Hybrid reconstruction bekerja.
18. Image dapat dipertahankan.
19. Simple table dapat direkonstruksi.
20. Searchable PDF dapat diekspor.
21. Critical warning memblokir export.
22. Backup dapat dibuat dan diverifikasi.
23. Restore berhasil.
24. Digital E2E test lulus.
25. Scanned E2E test lulus.
26. Security regression test lulus.
27. Tidak ada Critical defect.

---

# 65. Open Product Decisions

1. Apakah `LITERARY` menjadi mandatory.
2. Maximum default PDF size.
3. Maximum default page count.
4. Default render DPI.
5. Default fallback font.
6. Default model setelah benchmark hardware.
7. Apakah FTS5 wajib.
8. Apakah full project backup menjadi mandatory.
9. Apakah Compact export masuk first release.
10. Apakah internal bookmark restoration masuk MVP.
11. Apakah TOC regeneration masuk MVP.
12. Apakah bilingual export masuk setelah MVP.
13. Apakah annotations dipertahankan atau di-flatten.
14. Apakah PDF form dipertahankan.
15. Apakah desktop installer menjadi post-MVP milestone pertama.
16. Apakah database encryption diperlukan.
17. Apakah backup encryption diperlukan.
18. Apakah startup local token diperlukan pada packaged release.
19. Apakah Windows menjadi satu-satunya supported platform awal.
20. Berapa retention default untuk intermediate files.

---

# 66. Definition of Done

`PRD.md` Version 0.2 dinyatakan selesai apabila:

* product vision selaras dengan local-first;
* target user adalah single local user;
* PDF menjadi primary input;
* English → Bahasa Indonesia menjadi primary language pair;
* Ollama menjadi primary translation runtime;
* local OCR menjadi primary OCR runtime;
* SQLite dan filesystem lokal menjadi storage;
* authentication, billing, advertisement, dan cloud dihapus dari Personal MVP;
* core workflow import sampai export telah ditetapkan;
* glossary dan protected content telah ditetapkan;
* review dan revision telah ditetapkan;
* reconstruction dan export telah ditetapkan;
* backup dan restore telah ditetapkan;
* security requirements telah ditetapkan;
* success metrics telah ditetapkan;
* release criteria telah ditetapkan;
* deferred dan prohibited features telah dipisahkan;
* dokumen dapat digunakan Codex sebagai requirement produk utama.
