# DOCUMENT INTERMEDIATE REPRESENTATION

## TransLoka Document IR Specification

**Document Name:** `DOCUMENT_IR.md`  
**Document Version:** 0.1  
**Status:** Draft  
**Related Documents:**

- `PRD.md`
- `ARCHITECTURE.md`

**Primary Purpose:** Menetapkan representasi internal dokumen yang konsisten untuk ekstraksi, OCR, penerjemahan, editing, quality assurance, rekonstruksi, dan ekspor.

---

# 1. Purpose

Document Intermediate Representation, selanjutnya disebut `Document IR`, adalah representasi terstruktur dari dokumen sumber beserta seluruh hasil pemrosesannya.

Document IR menjadi sumber data utama yang digunakan oleh:

- PDF parser;
- OCR engine;
- layout detection engine;
- terminology engine;
- translation engine;
- translation memory;
- side-by-side editor;
- quality assurance engine;
- reconstruction engine;
- export service.

Document IR harus mampu menyimpan:

- urutan halaman;
- ukuran dan orientasi halaman;
- teks asli;
- teks hasil OCR;
- struktur dokumen;
- posisi setiap elemen;
- style;
- gambar;
- tabel;
- hyperlink;
- footnote;
- formula;
- kode;
- glossary matches;
- hasil terjemahan;
- hasil review;
- confidence score;
- warning;
- version history.

Document IR tidak hanya menyimpan teks, tetapi juga hubungan antara konten dan struktur visual dokumen.

---

# 2. Design Goals

Document IR harus memenuhi sasaran berikut.

## 2.1 Lossless Representation

Sebisa mungkin, seluruh informasi penting dari dokumen sumber harus dapat direpresentasikan tanpa kehilangan:

- teks;
- struktur;
- urutan baca;
- posisi;
- style;
- gambar;
- tabel;
- metadata;
- relasi antarbagian.

## 2.2 Provider Neutral

Document IR tidak boleh bergantung pada format respons satu penyedia:

- OCR;
- AI translation;
- PDF parser;
- document analysis;
- cloud provider.

Respons provider harus dinormalisasi ke dalam struktur Document IR.

## 2.3 Translation Safe

Struktur harus memungkinkan sistem menerjemahkan teks tanpa mengubah:

- angka;
- URL;
- kode;
- citation;
- nama produk;
- nama fungsi;
- formula;
- istilah yang dilindungi.

## 2.4 Reconstruction Ready

Document IR harus menyediakan informasi yang cukup untuk:

- overlay reconstruction;
- reflow reconstruction;
- hybrid reconstruction;
- bilingual export;
- visual comparison.

## 2.5 Editable

Setiap unit terjemahan harus dapat:

- diedit;
- dikunci;
- disetujui;
- diterjemahkan ulang;
- dikembalikan ke versi sebelumnya;
- diberi komentar;
- ditandai untuk review.

## 2.6 Versioned

Document IR harus mendukung perubahan struktur data tanpa merusak proyek lama.

## 2.7 Partial Processing

Sistem harus dapat menyimpan hasil parsial.

Contoh:

- halaman 1–20 selesai;
- halaman 21 gagal OCR;
- halaman 22–30 belum diproses.

---

# 3. Core Principles

## 3.1 Source Content Is Immutable

Konten sumber yang telah diekstrak tidak boleh ditimpa oleh hasil terjemahan atau hasil review.

Field berikut harus dipisahkan:

- `source_text`
- `ocr_text`
- `normalized_source_text`
- `protected_source_text`
- `machine_translation`
- `reviewed_translation`
- `final_text`

## 3.2 Stable Identifier

Setiap entity harus memiliki identifier yang stabil.

Identifier tidak boleh berubah hanya karena:

- segmen diterjemahkan ulang;
- glossary diperbarui;
- posisi elemen direkonstruksi;
- pengguna mengedit hasil.

## 3.3 Geometry Is Explicit

Setiap elemen visual harus menyimpan geometry dalam sistem koordinat yang didefinisikan.

## 3.4 Reading Order Is Separate from Position

Posisi visual tidak selalu sama dengan urutan baca.

Document IR harus menyimpan:

- posisi visual;
- reading order;
- semantic order.

Hal ini penting untuk dokumen:

- dua kolom;
- tiga kolom;
- sidebar;
- footnote;
- textbox;
- tabel;
- caption.

## 3.5 Original and Reconstructed Geometry Are Separate

Geometry sumber tidak boleh ditimpa oleh geometry hasil rekonstruksi.

Gunakan:

- `source_geometry`
- `target_geometry`

## 3.6 Machine and Human Decisions Are Separate

Sistem harus dapat membedakan:

- hasil deteksi otomatis;
- hasil model;
- perubahan pengguna;
- keputusan final.

---

# 4. Entity Hierarchy

Struktur utama Document IR:

```text
Document
├── Metadata
├── Processing Configuration
├── Sections
│   └── Chapters
├── Pages
│   ├── Layers
│   ├── Blocks
│   │   ├── Lines
│   │   │   └── Spans
│   │   │       └── Tokens
│   │   ├── Segments
│   │   └── Cells
│   ├── Assets
│   ├── Annotations
│   └── Warnings
├── Glossary Snapshot
├── Translation Memory References
├── Quality Report
└── Revision History
```

Entity utama:

1. Document.
2. Section.
3. Chapter.
4. Page.
5. Layer.
6. Block.
7. Line.
8. Span.
9. Token.
10. Segment.
11. Table.
12. Table Cell.
13. Asset.
14. Annotation.
15. Glossary Match.
16. Translation Revision.
17. Warning.
18. Quality Check.
19. Relationship.
20. Export Layout.

---

# 5. Document Root Object

Contoh:

```json
{
  "ir_version": "0.1",
  "document_id": "doc_01JABC123",
  "project_id": "prj_01JABC123",
  "source_file_id": "file_01JABC123",
  "source_language": "en",
  "target_language": "id",
  "document_type": "TECHNICAL_BOOK",
  "title": "Example Technical Book",
  "page_count": 240,
  "status": "STRUCTURED",
  "metadata": {},
  "processing_config": {},
  "sections": [],
  "pages": [],
  "glossary_snapshot": {},
  "quality_report": {},
  "revision": 1,
  "created_at": "2026-07-26T08:00:00Z",
  "updated_at": "2026-07-26T08:30:00Z"
}
```

---

# 6. Document Fields

## 6.1 Required Fields

| Field | Type | Description |
|---|---|---|
| `ir_version` | string | Versi schema Document IR |
| `document_id` | string | ID unik dokumen |
| `project_id` | string | ID proyek |
| `source_file_id` | string | Referensi file sumber |
| `source_language` | string | Bahasa sumber |
| `target_language` | string | Bahasa target |
| `document_type` | enum | Jenis dokumen |
| `page_count` | integer | Jumlah halaman sumber |
| `status` | enum | Status Document IR |
| `revision` | integer | Revisi Document IR |
| `created_at` | datetime | Waktu pembuatan |
| `updated_at` | datetime | Waktu perubahan terakhir |

## 6.2 Optional Fields

- title;
- subtitle;
- author;
- publisher;
- publication year;
- ISBN;
- source application;
- PDF version;
- document subject;
- keywords;
- detected domain;
- translation style;
- copyright notice.

---

# 7. Document Type

Nilai awal:

```text
ACADEMIC_PAPER
ACADEMIC_BOOK
TECHNICAL_BOOK
USER_MANUAL
BUSINESS_REPORT
LEGAL_DOCUMENT
FICTION_BOOK
NONFICTION_BOOK
PRESENTATION_EXPORT
BROCHURE
FORM
COMIC_OR_GRAPHIC_BOOK
GENERAL_DOCUMENT
UNKNOWN
```

Document type digunakan untuk menentukan:

- segmentation;
- translation style;
- terminology recommendation;
- reconstruction strategy;
- quality rules.

---

# 8. Document Status

```text
CREATED
ANALYZED
EXTRACTED
OCR_PARTIAL
OCR_COMPLETE
STRUCTURED
TERMS_DETECTED
READY_FOR_TRANSLATION
TRANSLATING
TRANSLATED
PARTIALLY_TRANSLATED
REVIEWING
REVIEWED
RECONSTRUCTING
RECONSTRUCTED
QUALITY_CHECKED
READY_FOR_EXPORT
EXPORTED
FAILED
ARCHIVED
```

Status harus mengikuti state transition yang valid.

Contoh:

```text
EXTRACTED → STRUCTURED
```

Valid.

```text
CREATED → EXPORTED
```

Tidak valid.

---

# 9. Metadata Object

```json
{
  "filename": "book.pdf",
  "mime_type": "application/pdf",
  "file_size_bytes": 18392810,
  "checksum_sha256": "example",
  "pdf_version": "1.7",
  "is_encrypted": false,
  "is_password_protected": false,
  "has_embedded_fonts": true,
  "has_text_layer": true,
  "has_forms": false,
  "has_javascript": false,
  "has_attachments": false,
  "creator": "Adobe InDesign",
  "producer": "Adobe PDF Library",
  "creation_date": null,
  "modification_date": null
}
```

---

# 10. Processing Configuration

Processing configuration menyimpan pengaturan yang digunakan ketika membangun Document IR.

```json
{
  "source_language": "en",
  "target_language": "id",
  "translation_style": "PROFESSIONAL",
  "reconstruction_mode": "HYBRID",
  "ocr_mode": "AUTO",
  "translate_headers": true,
  "translate_footers": false,
  "translate_captions": true,
  "translate_tables": true,
  "translate_bibliography": false,
  "preserve_code": true,
  "preserve_formulas": true,
  "preserve_urls": true,
  "preserve_product_names": true,
  "selected_page_ranges": [
    {
      "start": 1,
      "end": 240
    }
  ]
}
```

Processing configuration harus disimpan sebagai snapshot.

Perubahan konfigurasi tidak boleh mengubah riwayat proses sebelumnya secara diam-diam.

---

# 11. Coordinate System

## 11.1 Source Coordinate Space

Gunakan coordinate space berbasis unit PDF point.

```text
1 point = 1/72 inch
```

Origin default:

```text
bottom-left
```

Namun, untuk kemudahan frontend, sistem dapat menyediakan normalized geometry dengan origin:

```text
top-left
```

Kedua sistem harus dibedakan secara eksplisit.

## 11.2 Geometry Object

```json
{
  "coordinate_system": "PDF_POINT_TOP_LEFT",
  "x": 72.0,
  "y": 120.0,
  "width": 451.0,
  "height": 80.0,
  "rotation": 0.0
}
```

## 11.3 Normalized Geometry

Untuk frontend:

```json
{
  "x": 0.121,
  "y": 0.143,
  "width": 0.758,
  "height": 0.095
}
```

Nilai berada pada rentang:

```text
0.0–1.0
```

## 11.4 Polygon Geometry

Untuk teks miring atau area tidak berbentuk persegi:

```json
{
  "points": [
    {"x": 100, "y": 100},
    {"x": 300, "y": 90},
    {"x": 310, "y": 150},
    {"x": 110, "y": 160}
  ]
}
```

---

# 12. Page Object

```json
{
  "page_id": "page_0001",
  "document_id": "doc_01JABC123",
  "source_page_number": 1,
  "logical_page_number": "i",
  "target_page_number": 1,
  "width": 595.28,
  "height": 841.89,
  "rotation": 0,
  "page_type": "DIGITAL",
  "status": "STRUCTURED",
  "source_storage_key": null,
  "rendered_image_key": "pages/page_0001.png",
  "thumbnail_key": "thumbnails/page_0001.webp",
  "reading_direction": "LTR",
  "column_count": 1,
  "blocks": [],
  "assets": [],
  "annotations": [],
  "warnings": [],
  "confidence": {}
}
```

---

# 13. Page Fields

## 13.1 Page Number Fields

### `source_page_number`

Nomor urutan fisik halaman dalam file.

Selalu integer mulai dari 1.

### `logical_page_number`

Nomor yang terlihat pada dokumen.

Contoh:

```text
i
ii
iii
1
2
A-1
```

### `target_page_number`

Nomor fisik pada dokumen hasil rekonstruksi.

Dapat berbeda jika hasil terjemahan membutuhkan halaman tambahan.

---

# 14. Page Type

```text
DIGITAL
SCANNED
HYBRID
IMAGE_ONLY
FORM
COVER
TABLE_OF_CONTENTS
INDEX
BIBLIOGRAPHY
BLANK
UNKNOWN
```

Page type dapat memiliki lebih dari satu tag tambahan.

Contoh:

```json
{
  "page_type": "DIGITAL",
  "page_tags": [
    "MULTI_COLUMN",
    "HAS_TABLE",
    "HAS_FOOTNOTE"
  ]
}
```

---

# 15. Layer Model

Setiap halaman dapat memiliki layer:

```text
BACKGROUND
RASTER_IMAGE
VECTOR_GRAPHICS
SOURCE_TEXT
OCR_TEXT
ANNOTATION
TRANSLATED_TEXT
REVIEW_OVERLAY
```

Layer digunakan agar sistem dapat:

- mempertahankan background;
- menyembunyikan teks sumber saat overlay;
- menampilkan highlight;
- membandingkan source dan target;
- membangun hasil ekspor.

Contoh:

```json
{
  "layer_id": "layer_001",
  "layer_type": "SOURCE_TEXT",
  "z_index": 10,
  "visible": true,
  "locked": true
}
```

---

# 16. Block Object

Block adalah unit struktural visual dan semantik pada halaman.

```json
{
  "block_id": "block_0001",
  "page_id": "page_0001",
  "block_type": "PARAGRAPH",
  "semantic_role": "BODY_TEXT",
  "source_geometry": {},
  "target_geometry": null,
  "reading_order": 7,
  "parent_block_id": null,
  "child_block_ids": [],
  "style": {},
  "source_text": "Example paragraph.",
  "normalized_source_text": "Example paragraph.",
  "segments": [],
  "lines": [],
  "confidence": {},
  "status": "READY_FOR_TRANSLATION",
  "warnings": []
}
```

---

# 17. Block Types

```text
DOCUMENT_TITLE
SUBTITLE
HEADING_1
HEADING_2
HEADING_3
HEADING_4
HEADING_5
HEADING_6
PARAGRAPH
BLOCKQUOTE
LIST
LIST_ITEM
TABLE
TABLE_ROW
TABLE_CELL
IMAGE
FIGURE
CAPTION
HEADER
FOOTER
PAGE_NUMBER
FOOTNOTE
ENDNOTE
CODE_BLOCK
INLINE_CODE_CONTAINER
FORMULA
EQUATION_LABEL
BIBLIOGRAPHY_ENTRY
INDEX_ENTRY
TABLE_OF_CONTENTS_ENTRY
SIDEBAR
CALLOUT
TEXTBOX
FORM_FIELD
SIGNATURE_FIELD
DECORATIVE_TEXT
UNKNOWN
```

---

# 18. Semantic Role

Block type menjelaskan bentuk.

Semantic role menjelaskan fungsi.

Contoh:

```text
TITLE
CHAPTER_TITLE
SECTION_TITLE
BODY_TEXT
DEFINITION
EXAMPLE
WARNING
NOTE
TIP
QUOTE
CAPTION
REFERENCE
CODE
FORMULA
NAVIGATION
DECORATION
```

Satu block dapat memiliki:

```json
{
  "block_type": "PARAGRAPH",
  "semantic_role": "WARNING"
}
```

---

# 19. Reading Order

Setiap block harus memiliki `reading_order`.

Contoh:

```text
1, 2, 3, 4, 5
```

Reading order bersifat unik dalam satu halaman.

Untuk dokumen kompleks, gunakan:

- page reading order;
- section reading order;
- global reading order.

Contoh:

```json
{
  "page_reading_order": 4,
  "section_reading_order": 18,
  "global_reading_order": 245
}
```

---

# 20. Parent and Child Relationships

Hubungan parent-child digunakan untuk:

- list dan list item;
- table dan cell;
- figure dan caption;
- section dan paragraph;
- sidebar dan content;
- footnote dan footnote text.

Contoh:

```text
TABLE
├── TABLE_ROW
│   ├── TABLE_CELL
│   └── TABLE_CELL
```

---

# 21. Line Object

Line adalah satu baris visual.

```json
{
  "line_id": "line_001",
  "block_id": "block_001",
  "source_geometry": {},
  "baseline": {
    "x1": 80,
    "y1": 120,
    "x2": 500,
    "y2": 120
  },
  "reading_order": 1,
  "spans": []
}
```

Line digunakan untuk:

- preserving line layout;
- font analysis;
- OCR correction;
- overlay reconstruction;
- text fitting.

---

# 22. Span Object

Span adalah bagian teks dengan style yang sama.

```json
{
  "span_id": "span_001",
  "line_id": "line_001",
  "text": "Important workflow",
  "source_geometry": {},
  "style": {
    "font_family": "Helvetica",
    "font_size": 11,
    "font_weight": 700,
    "italic": false
  },
  "tokens": []
}
```

Contoh satu baris dapat terdiri atas:

- teks normal;
- bold;
- italic;
- hyperlink;
- inline code.

---

# 23. Token Object

Token adalah unit teks terkecil yang perlu dilacak.

```json
{
  "token_id": "token_001",
  "span_id": "span_001",
  "text": "workflow",
  "normalized_text": "workflow",
  "token_type": "TERM",
  "start_offset": 10,
  "end_offset": 18,
  "source_geometry": {},
  "confidence": 0.99
}
```

Token type:

```text
WORD
PUNCTUATION
NUMBER
DATE
TIME
UNIT
CURRENCY
URL
EMAIL
CITATION
TERM
NAME
PRODUCT
ORGANIZATION
CODE
VARIABLE
FUNCTION
FILE_PATH
COMMAND
FORMULA
PLACEHOLDER
WHITESPACE
UNKNOWN
```

---

# 24. Style Object

```json
{
  "font_family": "Times New Roman",
  "font_postscript_name": "TimesNewRomanPSMT",
  "font_size": 11.0,
  "font_weight": 400,
  "bold": false,
  "italic": false,
  "underline": false,
  "strikethrough": false,
  "text_color": "#000000",
  "background_color": null,
  "letter_spacing": 0,
  "word_spacing": 0,
  "line_height": 14,
  "text_align": "JUSTIFY",
  "vertical_align": "BASELINE",
  "writing_mode": "HORIZONTAL",
  "indent_left": 0,
  "indent_right": 0,
  "first_line_indent": 24,
  "space_before": 0,
  "space_after": 6
}
```

---

# 25. Segment Object

Segment adalah unit utama penerjemahan.

Satu block dapat memiliki satu atau beberapa segment.

```json
{
  "segment_id": "segment_0001",
  "block_id": "block_0001",
  "segment_order": 1,
  "source_text": "The workflow begins after authentication.",
  "ocr_text": null,
  "normalized_source_text": "The workflow begins after authentication.",
  "protected_source_text": "The __TERM_001__ begins after __TERM_002__.",
  "machine_translation": "Workflow dimulai setelah autentikasi.",
  "reviewed_translation": null,
  "final_text": "Workflow dimulai setelah autentikasi.",
  "status": "MACHINE_TRANSLATED",
  "translation_style": "PROFESSIONAL",
  "glossary_matches": [],
  "protected_items": [],
  "confidence": {},
  "warnings": [],
  "revision_history": []
}
```

---

# 26. Segment Boundaries

Segment harus mengikuti batas semantik.

Segment tidak boleh memotong:

- kalimat;
- istilah multiword;
- hyperlink;
- citation;
- inline code;
- formula;
- quotation;
- list item;
- table cell.

Batas segment yang direkomendasikan:

1. Satu atau beberapa kalimat dalam satu paragraf.
2. Satu list item.
3. Satu heading.
4. Satu caption.
5. Satu table cell.
6. Satu footnote.
7. Satu bibliography entry.

---

# 27. Segment Status

```text
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

# 28. Final Text Resolution

Field `final_text` tidak boleh ditulis sembarangan.

Resolution rule:

```text
Jika status APPROVED atau USER_EDITED:
    final_text = reviewed_translation

Jika reviewed_translation tersedia:
    final_text = reviewed_translation

Jika machine_translation tersedia:
    final_text = machine_translation

Jika segment NOT_TRANSLATABLE:
    final_text = source_text
```

Resolved final text dapat dihitung secara dinamis atau disimpan sebagai cache.

---

# 29. Source Text Fields

## `source_text`

Teks sumber hasil ekstraksi native.

## `ocr_text`

Teks hasil OCR.

## `normalized_source_text`

Teks yang telah dinormalisasi tanpa mengubah makna.

Normalisasi dapat mencakup:

- menggabungkan hyphenation antarbaris;
- menghapus whitespace berlebihan;
- memperbaiki karakter Unicode;
- menyatukan baris paragraf;
- memperbaiki ligature.

## `protected_source_text`

Teks yang telah mengandung placeholder glossary dan protected item.

---

# 30. Normalization Rules

Normalisasi diperbolehkan untuk:

- mengubah ligature `ﬁ` menjadi `fi`;
- menghapus line break visual di tengah kalimat;
- memperbaiki spasi ganda;
- menyatukan kata yang terpotong karena line wrap;
- menormalisasi quote;
- menormalisasi dash;
- menormalisasi Unicode.

Normalisasi tidak boleh:

- mengubah angka;
- mengubah istilah;
- mengubah punctuation bermakna;
- menghapus citation;
- mengubah kapitalisasi nama khusus;
- menyimpulkan kata yang tidak jelas tanpa warning.

Setiap perubahan normalisasi harus dapat dilacak.

---

# 31. OCR Data

```json
{
  "ocr": {
    "required": true,
    "provider": "ocr_provider",
    "model": "ocr_model",
    "language": "en",
    "confidence": 0.94,
    "rotation_detected": 0,
    "deskew_applied": true,
    "denoise_applied": true,
    "source_image_key": "ocr/page_001.png",
    "raw_response_reference": "ocr_raw_001"
  }
}
```

Raw provider response tidak harus disimpan permanen.

Namun, field penting harus dinormalisasi ke Document IR.

---

# 32. OCR Conflict Resolution

Pada hybrid PDF, source text dan OCR text dapat berbeda.

Gunakan keputusan:

```text
NATIVE_TEXT
OCR_TEXT
MERGED
MANUAL
```

Contoh:

```json
{
  "text_resolution": {
    "selected_source": "NATIVE_TEXT",
    "native_confidence": 0.98,
    "ocr_confidence": 0.92,
    "difference_score": 0.08,
    "resolved_by": "SYSTEM"
  }
}
```

Jika perbedaan melebihi threshold, segment harus diberi warning.

---

# 33. Protected Item Object

```json
{
  "protected_item_id": "protected_001",
  "segment_id": "segment_001",
  "placeholder": "__TERM_001__",
  "original_text": "workflow",
  "normalized_text": "workflow",
  "item_type": "GLOSSARY_TERM",
  "rule": "KEEP_ORIGINAL",
  "replacement_text": "workflow",
  "start_offset": 4,
  "end_offset": 12,
  "case_sensitive": false,
  "status": "RESTORED"
}
```

---

# 34. Protected Item Types

```text
GLOSSARY_TERM
URL
EMAIL
PHONE_NUMBER
CITATION
REFERENCE_NUMBER
PRODUCT_NAME
PERSON_NAME
ORGANIZATION_NAME
LOCATION_NAME
CODE
INLINE_CODE
VARIABLE
FUNCTION
CLASS_NAME
FILE_PATH
COMMAND
FORMULA
EQUATION
VERSION
IDENTIFIER
USER_DEFINED
```

---

# 35. Placeholder Requirements

Placeholder harus:

- unik dalam satu request;
- sulit muncul secara alami;
- dapat divalidasi;
- tidak berubah saat diterjemahkan;
- memiliki mapping yang tersimpan;
- dapat direstorasi secara deterministik.

Format awal:

```text
__TLK_TERM_0001__
__TLK_URL_0001__
__TLK_CODE_0001__
```

Dilarang menggunakan placeholder sederhana seperti:

```text
TERM1
URL1
```

karena lebih mudah diubah oleh model.

---

# 36. Glossary Match Object

```json
{
  "match_id": "match_001",
  "segment_id": "segment_001",
  "glossary_term_id": "term_001",
  "source_term": "workflow",
  "matched_text": "workflow",
  "rule_type": "KEEP_ORIGINAL",
  "target_term": null,
  "start_offset": 4,
  "end_offset": 12,
  "priority": 100,
  "match_method": "EXACT",
  "confidence": 1.0
}
```

Match method:

```text
EXACT
CASE_INSENSITIVE
LEMMA
PHRASE
REGEX
SEMANTIC
USER_CONFIRMED
```

---

# 37. Glossary Snapshot

Document IR harus menyimpan snapshot glossary yang digunakan.

```json
{
  "glossary_snapshot": {
    "snapshot_id": "gls_snapshot_001",
    "created_at": "2026-07-26T08:00:00Z",
    "terms": [
      {
        "source_term": "workflow",
        "rule_type": "KEEP_ORIGINAL",
        "target_term": null
      }
    ]
  }
}
```

Tujuan:

- reproducibility;
- audit;
- comparison;
- translation ulang;
- version tracking.

Perubahan glossary global tidak boleh diam-diam mengubah terjemahan lama.

---

# 38. Translation Result Object

```json
{
  "translation_result": {
    "provider": "provider_name",
    "model": "model_name",
    "request_id": "provider_request_001",
    "prompt_version": "translation_prompt_0.1",
    "translated_at": "2026-07-26T08:15:00Z",
    "input_units": 245,
    "output_units": 190,
    "latency_ms": 1430,
    "retry_count": 0,
    "machine_translation": "Workflow dimulai setelah autentikasi.",
    "detected_target_language": "id",
    "validation_status": "PASSED"
  }
}
```

Prompt lengkap tidak harus disimpan dalam Document IR.

Yang disimpan:

- prompt version;
- provider;
- model;
- request reference;
- parameter penting.

---

# 39. Translation Revision Object

```json
{
  "revision_id": "rev_001",
  "segment_id": "segment_001",
  "revision_number": 2,
  "revision_type": "USER_EDIT",
  "previous_text": "Workflow dimulai setelah proses autentikasi.",
  "new_text": "Workflow dimulai setelah autentikasi.",
  "actor_type": "USER",
  "actor_id": "user_001",
  "reason": "Terminology correction",
  "created_at": "2026-07-26T08:30:00Z"
}
```

Revision type:

```text
MACHINE_TRANSLATION
AUTOMATIC_RETRY
GLOSSARY_REAPPLICATION
USER_EDIT
ADMIN_CORRECTION
TRANSLATION_MEMORY_REUSE
RESTORE_VERSION
```

---

# 40. Confidence Object

Confidence harus memiliki komponen.

```json
{
  "confidence": {
    "overall": 0.92,
    "extraction": 0.99,
    "ocr": null,
    "structure": 0.95,
    "translation": 0.91,
    "terminology": 1.0,
    "numerical_integrity": 1.0,
    "layout": 0.86,
    "calculated_at": "2026-07-26T08:20:00Z",
    "scoring_version": "confidence_0.1"
  }
}
```

Confidence tidak boleh direpresentasikan hanya sebagai label subjektif.

---

# 41. Warning Object

```json
{
  "warning_id": "warning_001",
  "scope_type": "SEGMENT",
  "scope_id": "segment_001",
  "warning_type": "LOW_TRANSLATION_CONFIDENCE",
  "severity": "MEDIUM",
  "message": "Translation confidence is below configured threshold.",
  "details": {},
  "status": "OPEN",
  "created_by": "SYSTEM",
  "created_at": "2026-07-26T08:20:00Z",
  "resolved_at": null,
  "resolved_by": null
}
```

---

# 42. Warning Severity

```text
INFO
LOW
MEDIUM
HIGH
CRITICAL
```

Critical warning mencegah ekspor final, kecuali pengguna dengan permission khusus melakukan override.

---

# 43. Warning Types

## Extraction

```text
TEXT_EXTRACTION_FAILED
READING_ORDER_UNCERTAIN
UNKNOWN_CHARACTER
FONT_MAPPING_FAILED
```

## OCR

```text
LOW_OCR_CONFIDENCE
OCR_TEXT_CONFLICT
UNREADABLE_REGION
ROTATION_UNCERTAIN
```

## Translation

```text
TRANSLATION_FAILED
LOW_TRANSLATION_CONFIDENCE
UNTRANSLATED_TEXT
TARGET_LANGUAGE_MISMATCH
POSSIBLE_HALLUCINATION
SOURCE_MEANING_DRIFT
```

## Terminology

```text
GLOSSARY_NOT_APPLIED
TERM_INCONSISTENT
PLACEHOLDER_MISSING
PLACEHOLDER_DUPLICATED
CASE_MISMATCH
```

## Integrity

```text
NUMBER_CHANGED
DATE_CHANGED
UNIT_CHANGED
URL_CHANGED
CITATION_CHANGED
CODE_CHANGED
```

## Layout

```text
TEXT_OVERFLOW
TEXT_CLIPPED
TEXT_OVERLAP
IMAGE_OVERLAP
MISSING_IMAGE
TABLE_OVERFLOW
FONT_TOO_SMALL
PAGE_ADDED
LAYOUT_SHIFT
```

## Structure

```text
HEADING_LEVEL_CHANGED
LIST_NUMBERING_CHANGED
TABLE_STRUCTURE_CHANGED
FOOTNOTE_LINK_BROKEN
READING_ORDER_CHANGED
```

---

# 44. Warning Resolution

```json
{
  "resolution": {
    "resolution_type": "USER_ACCEPTED",
    "note": "Term intentionally left untranslated.",
    "actor_id": "user_001",
    "resolved_at": "2026-07-26T09:00:00Z"
  }
}
```

Resolution type:

```text
AUTO_FIXED
USER_FIXED
USER_ACCEPTED
IGNORED_BY_POLICY
FALSE_POSITIVE
REQUIRES_REPROCESSING
```

---

# 45. Table Object

```json
{
  "table_id": "table_001",
  "block_id": "block_table_001",
  "source_geometry": {},
  "target_geometry": null,
  "row_count": 4,
  "column_count": 3,
  "has_header_row": true,
  "has_header_column": false,
  "border_style": "VISIBLE",
  "cells": [],
  "continuation": {
    "is_continued_from_previous_page": false,
    "continues_to_next_page": true,
    "related_table_id": "table_002"
  },
  "status": "EXTRACTED",
  "confidence": 0.91
}
```

---

# 46. Table Cell Object

```json
{
  "cell_id": "cell_001",
  "table_id": "table_001",
  "row_index": 0,
  "column_index": 0,
  "row_span": 1,
  "column_span": 1,
  "source_geometry": {},
  "target_geometry": null,
  "cell_role": "HEADER",
  "source_text": "Workflow",
  "segments": [],
  "style": {},
  "horizontal_align": "LEFT",
  "vertical_align": "MIDDLE"
}
```

---

# 47. Table Translation Rules

1. Table cell diterjemahkan sebagai unit terpisah.
2. Context tabel harus menyertakan:
   - judul tabel;
   - header row;
   - header column;
   - caption;
   - cell terkait.
3. Angka tidak boleh berubah.
4. Formula tidak boleh diterjemahkan.
5. Unit tidak boleh diubah tanpa aturan eksplisit.
6. Merged cell harus dipertahankan.
7. Urutan row dan column tidak boleh berubah.

---

# 48. Asset Object

```json
{
  "asset_id": "asset_001",
  "page_id": "page_001",
  "asset_type": "RASTER_IMAGE",
  "source_geometry": {},
  "target_geometry": null,
  "storage_key": "assets/image_001.png",
  "mime_type": "image/png",
  "checksum_sha256": "example",
  "width_px": 1200,
  "height_px": 800,
  "dpi": 300,
  "rotation": 0,
  "opacity": 1,
  "z_index": 3,
  "alt_text": null,
  "caption_block_id": "block_caption_001",
  "preservation_policy": "KEEP_UNCHANGED"
}
```

---

# 49. Asset Types

```text
RASTER_IMAGE
VECTOR_IMAGE
CHART
DIAGRAM
LOGO
ICON
BACKGROUND
DECORATIVE_ELEMENT
EMBEDDED_FILE
FONT
AUDIO
VIDEO
UNKNOWN
```

Untuk MVP, audio dan video hanya dicatat sebagai metadata.

---

# 50. Asset Preservation Policy

```text
KEEP_UNCHANGED
RECOMPRESS_LOSSLESS
RECOMPRESS_STANDARD
RENDER_AS_IMAGE
REPLACE_WITH_TRANSLATED_VERSION
REMOVE
```

MVP default:

```text
KEEP_UNCHANGED
```

`REMOVE` hanya boleh digunakan berdasarkan tindakan pengguna atau aturan keamanan.

---

# 51. Annotation Object

```json
{
  "annotation_id": "annotation_001",
  "page_id": "page_001",
  "annotation_type": "HYPERLINK",
  "source_geometry": {},
  "target_geometry": null,
  "target": "https://example.com",
  "content": null,
  "preserve": true
}
```

Annotation type:

```text
HYPERLINK
INTERNAL_LINK
COMMENT
HIGHLIGHT
UNDERLINE
STRIKEOUT
STAMP
FORM_FIELD
BOOKMARK
```

---

# 52. Hyperlink Handling

Hyperlink harus dipisahkan antara:

- visible text;
- target URL.

Contoh:

```json
{
  "visible_text": "OpenAI documentation",
  "target_url": "https://example.com",
  "translate_visible_text": true,
  "preserve_target_url": true
}
```

Target URL tidak boleh dikirim untuk diterjemahkan.

---

# 53. Footnote Object

```json
{
  "footnote_id": "footnote_001",
  "reference_segment_id": "segment_012",
  "note_block_id": "block_footnote_001",
  "marker": "1",
  "source_page_id": "page_001",
  "target_page_id": null,
  "relationship_status": "LINKED"
}
```

Footnote marker tidak boleh berubah tanpa alasan.

Footnote text dapat diterjemahkan.

---

# 54. Formula Object

```json
{
  "formula_id": "formula_001",
  "block_id": "block_formula_001",
  "source_geometry": {},
  "representation": {
    "type": "LATEX",
    "value": "E = mc^2"
  },
  "rendered_asset_id": null,
  "translation_policy": "PRESERVE"
}
```

Formula tidak diterjemahkan.

Teks penjelasan di sekitar formula tetap diterjemahkan.

---

# 55. Code Object

```json
{
  "code_id": "code_001",
  "block_id": "block_code_001",
  "language": "python",
  "source_code": "print('Hello')",
  "translation_policy": "PRESERVE_CODE",
  "comment_policy": "TRANSLATE_COMMENTS_OPTIONAL",
  "line_numbers": true
}
```

Default MVP:

- kode tidak diterjemahkan;
- nama variable tidak diterjemahkan;
- string literal tidak diterjemahkan;
- comment hanya diterjemahkan jika pengguna mengaktifkan opsi.

---

# 56. Relationship Object

Relationship menyimpan hubungan semantik.

```json
{
  "relationship_id": "rel_001",
  "relationship_type": "CAPTION_OF",
  "source_entity_id": "block_caption_001",
  "target_entity_id": "asset_001",
  "confidence": 0.98
}
```

Relationship type:

```text
CAPTION_OF
FOOTNOTE_OF
CONTINUATION_OF
CHILD_OF
REFERENCES
LINKS_TO
LABEL_OF
HEADER_FOR
BELONGS_TO_SECTION
PRECEDES
FOLLOWS
```

---

# 57. Section Object

```json
{
  "section_id": "section_001",
  "document_id": "doc_001",
  "section_type": "CHAPTER",
  "title_segment_id": "segment_title_001",
  "level": 1,
  "order": 1,
  "parent_section_id": null,
  "start_page_id": "page_010",
  "end_page_id": "page_035",
  "block_ids": [],
  "summary": null
}
```

Section type:

```text
FRONT_MATTER
PREFACE
TABLE_OF_CONTENTS
PART
CHAPTER
SECTION
SUBSECTION
APPENDIX
BIBLIOGRAPHY
INDEX
BACK_MATTER
```

---

# 58. Section Context

Section dapat menyimpan context summary untuk membantu translation engine.

```json
{
  "context_summary": {
    "source_summary": "This chapter explains authentication workflows.",
    "generated_by": "SYSTEM",
    "model": "model_name",
    "version": "0.1"
  }
}
```

Context summary tidak boleh masuk ke dokumen hasil.

Summary hanya digunakan untuk menjaga konsistensi terjemahan.

---

# 59. Chapter Terminology Context

Setiap section dapat memiliki terminology context.

```json
{
  "active_terms": [
    {
      "source_term": "workflow",
      "rule": "KEEP_ORIGINAL"
    },
    {
      "source_term": "access token",
      "rule": "TRANSLATE_AS",
      "target_term": "token akses"
    }
  ]
}
```

---

# 60. Reconstruction Object

Setiap block dapat memiliki reconstruction state.

```json
{
  "reconstruction": {
    "mode": "HYBRID",
    "source_geometry": {},
    "target_geometry": {},
    "font_mapping": {
      "source_font": "Helvetica",
      "target_font": "Arial"
    },
    "font_size_source": 11,
    "font_size_target": 10.5,
    "line_height_target": 13,
    "fit_strategy": "EXPAND_TEXTBOX",
    "overflow": false,
    "page_break_inserted": false
  }
}
```

---

# 61. Reconstruction Fit Strategy

```text
ORIGINAL_BOX
REWRAP
EXPAND_TEXTBOX
REDUCE_PARAGRAPH_SPACING
REDUCE_LINE_SPACING
REDUCE_FONT_SIZE
MOVE_FOLLOWING_BLOCKS
REFLOW_TO_NEXT_PAGE
ADD_PAGE
PRESERVE_AS_IMAGE
MANUAL
```

Semua perubahan signifikan harus dicatat.

---

# 62. Source and Target Page Mapping

Karena terjemahan dapat menambah halaman:

```json
{
  "page_mapping": {
    "source_page_id": "page_010",
    "target_page_ids": [
      "target_page_010",
      "target_page_011"
    ],
    "mapping_type": "ONE_TO_MANY"
  }
}
```

Mapping type:

```text
ONE_TO_ONE
ONE_TO_MANY
MANY_TO_ONE
UNMAPPED
```

---

# 63. Quality Report

```json
{
  "quality_report": {
    "report_id": "quality_001",
    "version": "qa_0.1",
    "overall_score": 0.91,
    "status": "PASSED_WITH_WARNINGS",
    "checks": [],
    "critical_warning_count": 0,
    "high_warning_count": 2,
    "medium_warning_count": 11,
    "low_warning_count": 24,
    "generated_at": "2026-07-26T09:30:00Z"
  }
}
```

---

# 64. Quality Check Object

```json
{
  "check_id": "check_001",
  "check_type": "NUMERICAL_INTEGRITY",
  "scope_type": "DOCUMENT",
  "scope_id": "doc_001",
  "status": "PASSED",
  "score": 1.0,
  "details": {
    "source_numbers": 294,
    "matched_numbers": 294,
    "changed_numbers": 0
  }
}
```

Status:

```text
NOT_RUN
RUNNING
PASSED
PASSED_WITH_WARNINGS
FAILED
SKIPPED
```

---

# 65. Comment Object

Editor dapat menyimpan komentar.

```json
{
  "comment_id": "comment_001",
  "scope_type": "SEGMENT",
  "scope_id": "segment_001",
  "author_id": "user_001",
  "content": "Check whether this term should remain in English.",
  "status": "OPEN",
  "created_at": "2026-07-26T09:00:00Z",
  "resolved_at": null
}
```

---

# 66. Locking Object

```json
{
  "lock": {
    "is_locked": true,
    "lock_type": "USER_APPROVED",
    "locked_by": "user_001",
    "locked_at": "2026-07-26T09:15:00Z"
  }
}
```

Lock type:

```text
SYSTEM_PROTECTED
USER_APPROVED
ORGANIZATION_APPROVED
LEGAL_HOLD
EXPORT_LOCK
```

Segmen terkunci tidak boleh diterjemahkan ulang secara otomatis.

---

# 67. Edit Conflict Handling

Untuk mencegah perubahan bersamaan:

```json
{
  "revision": 5,
  "updated_at": "2026-07-26T09:15:00Z"
}
```

Update harus menyertakan expected revision.

Jika revision berbeda:

```text
409 CONFLICT
```

Frontend harus meminta pengguna memilih:

- reload;
- merge;
- overwrite dengan izin;
- simpan sebagai alternatif.

---

# 68. Provenance

Setiap field hasil pemrosesan penting harus dapat ditelusuri.

```json
{
  "provenance": {
    "source": "OCR_PROVIDER",
    "provider": "provider_name",
    "model": "model_name",
    "job_id": "job_001",
    "created_at": "2026-07-26T08:00:00Z"
  }
}
```

Source:

```text
PDF_NATIVE
OCR_PROVIDER
LAYOUT_MODEL
TRANSLATION_MODEL
SYSTEM_RULE
USER
ADMIN
IMPORT
```

---

# 69. Audit Requirements

Perubahan berikut wajib dicatat:

- source text resolution;
- OCR correction;
- glossary application;
- translation result;
- user edit;
- approval;
- lock;
- warning override;
- reconstruction override;
- export generation.

Audit log tidak wajib menyimpan seluruh isi teks jika dapat menimbulkan risiko privasi.

Dapat menyimpan:

- hash;
- changed field;
- actor;
- timestamp;
- revision reference.

---

# 70. Storage Strategy

Document IR dapat disimpan menggunakan kombinasi:

## Relational Database

Untuk:

- document;
- page;
- block;
- segment;
- glossary matches;
- warnings;
- status;
- revision metadata.

## JSONB

Untuk:

- style;
- geometry;
- provider metadata;
- reconstruction metadata;
- confidence components.

## Object Storage

Untuk:

- raw provider response;
- large Document IR snapshot;
- page render;
- source asset;
- exported IR archive.

---

# 71. Canonical Source of Truth

Untuk MVP:

- PostgreSQL menjadi sumber kebenaran entity aktif.
- Object storage menyimpan snapshot besar dan artifact.
- Redis tidak boleh menjadi sumber kebenaran permanen.

Redis hanya digunakan untuk:

- cache;
- queue;
- lock;
- progress sementara.

---

# 72. Snapshot Strategy

Snapshot Document IR dibuat pada:

1. Setelah extraction selesai.
2. Setelah OCR selesai.
3. Setelah structure detection selesai.
4. Setelah translation selesai.
5. Setelah user review selesai.
6. Sebelum reconstruction.
7. Setelah reconstruction.
8. Saat export.

Contoh nama:

```text
document_ir/
├── extracted-v1.json
├── structured-v1.json
├── translated-v1.json
├── reviewed-v1.json
└── reconstructed-v1.json
```

---

# 73. Schema Versioning

Versi menggunakan format:

```text
MAJOR.MINOR
```

Contoh:

```text
0.1
0.2
1.0
```

## Major Version

Naik jika:

- ada breaking change;
- field penting berubah arti;
- hierarchy berubah;
- migrasi wajib dilakukan.

## Minor Version

Naik jika:

- field opsional ditambahkan;
- enum ditambahkan;
- metadata baru ditambahkan;
- perubahan backward-compatible.

---

# 74. Migration Strategy

Setiap perubahan schema harus menyediakan:

- source version;
- target version;
- migration script;
- rollback strategy;
- migration test;
- sample document.

Contoh:

```text
Document IR 0.1 → 0.2
```

Migrasi tidak boleh menghapus source text atau revision history.

---

# 75. Validation Rules

Document IR harus lolos validasi berikut.

## Document

- `page_count` sesuai jumlah page object.
- `source_language` tersedia.
- `target_language` tersedia.
- `document_id` unik.

## Page

- `source_page_number` unik.
- width dan height lebih besar dari nol.
- block harus merujuk ke page yang benar.

## Block

- geometry berada dalam batas halaman.
- reading order valid.
- block type dikenali.

## Segment

- source text tidak boleh null untuk segment translatable.
- segment order harus konsisten.
- final text mengikuti resolution rule.
- protected placeholder harus dapat direstorasi.

## Table

- row index dan column index valid.
- merged cell tidak overlap secara tidak sah.
- jumlah row dan column sesuai.

## Asset

- storage key tersedia.
- checksum tersedia.
- geometry valid.

---

# 76. Invariants

Invariant berikut tidak boleh dilanggar.

1. File sumber tidak dimodifikasi.
2. `source_text` tidak ditimpa oleh hasil terjemahan.
3. Setiap segment harus merujuk ke satu block.
4. Setiap block harus merujuk ke satu page.
5. Setiap page harus merujuk ke satu document.
6. Setiap placeholder harus memiliki protected item.
7. Setiap protected item harus direstorasi atau diberi warning.
8. Nomor sumber tidak boleh berubah tanpa warning.
9. URL sumber tidak boleh berubah tanpa warning.
10. Code tidak boleh berubah tanpa policy eksplisit.
11. Revision tidak boleh berkurang.
12. Entity ID tidak boleh digunakan ulang.
13. Deletion harus mengikuti retention policy.
14. Geometry sumber dan target harus dipisahkan.
15. User-approved segment tidak boleh ditimpa otomatis.

---

# 77. Example Complete Segment

```json
{
  "segment_id": "segment_0042",
  "block_id": "block_0018",
  "segment_order": 2,
  "source_text": "Each use case belongs to a specific workflow.",
  "ocr_text": null,
  "normalized_source_text": "Each use case belongs to a specific workflow.",
  "protected_source_text": "Each __TLK_TERM_0001__ belongs to a specific __TLK_TERM_0002__.",
  "machine_translation": "Setiap use case termasuk dalam workflow tertentu.",
  "reviewed_translation": "Setiap use case merupakan bagian dari workflow tertentu.",
  "final_text": "Setiap use case merupakan bagian dari workflow tertentu.",
  "status": "APPROVED",
  "translation_style": "PROFESSIONAL",
  "glossary_matches": [
    {
      "source_term": "use case",
      "rule_type": "KEEP_ORIGINAL"
    },
    {
      "source_term": "workflow",
      "rule_type": "KEEP_ORIGINAL"
    }
  ],
  "protected_items": [
    {
      "placeholder": "__TLK_TERM_0001__",
      "original_text": "use case",
      "replacement_text": "use case",
      "status": "RESTORED"
    },
    {
      "placeholder": "__TLK_TERM_0002__",
      "original_text": "workflow",
      "replacement_text": "workflow",
      "status": "RESTORED"
    }
  ],
  "confidence": {
    "overall": 0.97,
    "extraction": 1.0,
    "translation": 0.95,
    "terminology": 1.0,
    "numerical_integrity": 1.0
  },
  "warnings": [],
  "revision_history": [
    {
      "revision_number": 1,
      "revision_type": "MACHINE_TRANSLATION"
    },
    {
      "revision_number": 2,
      "revision_type": "USER_EDIT"
    }
  ]
}
```

---

# 78. Example Page Structure

```json
{
  "page_id": "page_0010",
  "source_page_number": 10,
  "logical_page_number": "3",
  "width": 595.28,
  "height": 841.89,
  "rotation": 0,
  "page_type": "DIGITAL",
  "column_count": 2,
  "blocks": [
    {
      "block_id": "block_heading_001",
      "block_type": "HEADING_1",
      "reading_order": 1
    },
    {
      "block_id": "block_paragraph_001",
      "block_type": "PARAGRAPH",
      "reading_order": 2
    },
    {
      "block_id": "block_image_001",
      "block_type": "FIGURE",
      "reading_order": 3
    },
    {
      "block_id": "block_caption_001",
      "block_type": "CAPTION",
      "reading_order": 4
    }
  ],
  "assets": [
    {
      "asset_id": "asset_001",
      "asset_type": "RASTER_IMAGE"
    }
  ]
}
```

---

# 79. Editor View Model

Frontend tidak harus menggunakan seluruh Document IR secara langsung.

Backend dapat menghasilkan Editor View Model.

```json
{
  "page": {
    "page_id": "page_001",
    "preview_url": "signed-url",
    "width": 595,
    "height": 842
  },
  "segments": [
    {
      "segment_id": "segment_001",
      "source_text": "Example text",
      "final_text": "Contoh teks",
      "geometry": {},
      "status": "MACHINE_TRANSLATED",
      "confidence": 0.92,
      "warnings": []
    }
  ]
}
```

Tujuan:

- payload lebih kecil;
- rendering lebih cepat;
- data sensitif dibatasi;
- authorization lebih mudah.

---

# 80. API Serialization Rules

1. Gunakan `snake_case`.
2. Gunakan ISO 8601 untuk datetime.
3. Gunakan UTF-8.
4. Nilai enum menggunakan uppercase.
5. ID diperlakukan sebagai string.
6. Field null hanya digunakan jika nilainya belum tersedia.
7. Field kosong dan field tidak tersedia harus dibedakan.
8. Geometry menggunakan angka desimal.
9. Urutan array harus stabil jika memiliki arti.
10. Response besar harus mendukung pagination atau chunking.

---

# 81. Partial Loading

Document IR dokumen besar tidak boleh selalu dikirim dalam satu response.

API harus mendukung:

- page range;
- block range;
- segment pagination;
- warning filter;
- status filter;
- section filter.

Contoh:

```text
GET /documents/{documentId}/pages/10
GET /pages/{pageId}/segments
GET /segments?status=NEEDS_REVIEW
```

---

# 82. Search Index

Search index dapat menyimpan:

- source text;
- translated text;
- reviewed text;
- glossary terms;
- heading;
- section title.

Search harus dapat membedakan:

```text
SOURCE
TRANSLATION
BOTH
```

---

# 83. Privacy Classification

Field dapat diklasifikasikan sebagai:

```text
PUBLIC_METADATA
USER_PRIVATE
DOCUMENT_CONFIDENTIAL
SYSTEM_INTERNAL
SECURITY_SENSITIVE
```

Contoh:

- filename: `USER_PRIVATE`
- source text: `DOCUMENT_CONFIDENTIAL`
- API key: tidak boleh masuk Document IR
- model name: `SYSTEM_INTERNAL`

---

# 84. Data Minimization

Document IR tidak boleh menyimpan:

- provider API key;
- password pengguna;
- payment card;
- session token;
- signed URL jangka panjang;
- secret internal;
- full system prompt;
- data provider yang tidak dibutuhkan.

---

# 85. Deletion Semantics

Deletion status:

```text
ACTIVE
SOFT_DELETED
DELETION_QUEUED
DELETING
DELETED
LEGAL_HOLD
```

Penghapusan document harus mencakup:

- pages;
- blocks;
- segments;
- assets;
- warnings;
- revisions;
- snapshots;
- exports;
- cache;
- search index.

Audit minimal dapat dipertahankan sesuai kebijakan hukum dan privasi tanpa menyimpan isi dokumen.

---

# 86. Import and Export of Document IR

Document IR dapat diekspor sebagai paket internal:

```text
document-ir-package/
├── manifest.json
├── document.json
├── pages/
│   ├── page-0001.json
│   └── page-0002.json
├── assets/
├── revisions/
├── quality-report.json
└── checksums.json
```

Paket harus memiliki checksum.

Import harus memvalidasi:

- schema version;
- checksum;
- referential integrity;
- file safety;
- ID conflicts.

---

# 87. Performance Considerations

Untuk dokumen besar:

- page object disimpan terpisah;
- segment dimuat per halaman;
- asset tidak di-inline;
- raw OCR response tidak dimuat default;
- snapshot dikompresi;
- style object dapat menggunakan deduplicated style reference;
- font metadata dapat disimpan sebagai shared object.

Contoh:

```json
{
  "style_ref": "style_body_01"
}
```

---

# 88. Deduplication

Entity yang dapat dideduplicasi:

- style;
- font;
- image berdasarkan checksum;
- glossary term;
- translation memory;
- identical segment source.

Deduplication tidak boleh menghapus hubungan ke lokasi asli.

---

# 89. Testing Requirements

## Schema Tests

- required field validation;
- enum validation;
- type validation;
- geometry validation;
- referential integrity.

## Round-Trip Tests

```text
PDF → Document IR → PDF
```

Periksa:

- jumlah halaman;
- teks;
- gambar;
- reading order;
- table;
- hyperlink.

## Translation Tests

Periksa:

- protected term;
- placeholder restoration;
- number preservation;
- code preservation;
- citation preservation.

## Migration Tests

Periksa:

- schema lama dapat dimigrasi;
- source text tidak hilang;
- revision history tetap tersedia.

## Large Document Tests

Minimal:

- 500 halaman;
- 10.000 segment;
- 1.000 gambar;
- 200 tabel.

---

# 90. Acceptance Criteria

Document IR dinyatakan siap digunakan pada MVP apabila:

1. Dapat merepresentasikan dokumen PDF digital.
2. Dapat merepresentasikan scanned PDF.
3. Dapat menyimpan geometry setiap block.
4. Dapat menyimpan reading order secara terpisah.
5. Dapat menyimpan hasil OCR dan native extraction.
6. Dapat menyimpan source text tanpa dimodifikasi.
7. Dapat menyimpan hasil terjemahan mesin.
8. Dapat menyimpan hasil edit pengguna.
9. Dapat menyimpan glossary match.
10. Dapat melindungi istilah dengan placeholder.
11. Dapat menyimpan table dan cell.
12. Dapat menyimpan gambar tanpa memodifikasinya.
13. Dapat menyimpan hyperlink dan footnote.
14. Dapat menyimpan warning dan confidence.
15. Dapat menyimpan source dan target geometry.
16. Dapat menyimpan revision history.
17. Dapat diproses per halaman.
18. Dapat divalidasi secara otomatis.
19. Dapat dimigrasikan ke versi schema berikutnya.
20. Dapat digunakan oleh parser, translation engine, editor, QA, reconstruction, dan export service.

---

# 91. Recommended Implementation Order

1. Document root.
2. Page schema.
3. Block schema.
4. Segment schema.
5. Geometry schema.
6. Style schema.
7. Asset schema.
8. Glossary match schema.
9. Protected item schema.
10. Translation result schema.
11. Warning schema.
12. Table schema.
13. Revision schema.
14. Reconstruction schema.
15. Quality report schema.
16. Schema validator.
17. Database mapping.
18. API serialization.
19. Snapshot exporter.
20. Migration framework.

---

# 92. Open Questions

1. Apakah token-level geometry perlu disimpan untuk semua PDF atau hanya OCR?
2. Apakah line dan span disimpan permanen atau dibangun ulang saat dibutuhkan?
3. Apakah style disimpan inline atau menggunakan style reference?
4. Apakah raw OCR response perlu disimpan setelah proyek selesai?
5. Apakah machine translation lama dipertahankan setelah translation ulang?
6. Berapa jumlah revision maksimum per segment?
7. Apakah komentar ikut masuk dalam export package?
8. Apakah translation memory menjadi bagian dari Document IR atau hanya referensi eksternal?
9. Bagaimana menyimpan tabel sangat kompleks dengan nested table?
10. Bagaimana menyimpan diagram dengan teks yang tidak diterjemahkan?
11. Apakah visual difference result disimpan per page atau hanya warning?
12. Bagaimana menangani dokumen dengan vertical writing?
13. Apakah document section ditentukan sebelum atau setelah OCR?
14. Apakah bibliography entry diproses sebagai satu segment atau beberapa field?
15. Bagaimana menangani satu paragraf yang berlanjut ke halaman berikutnya?

---

# 93. Definition of Done

Implementasi Document IR dianggap selesai apabila:

- schema utama tersedia;
- schema memiliki validator;
- entity memiliki stable ID;
- referential integrity dapat diperiksa;
- source content bersifat immutable;
- page dapat diproses secara independen;
- glossary placeholder dapat dipetakan;
- translation revision dapat dicatat;
- geometry sumber dan target terpisah;
- warning dapat ditambahkan dan diselesaikan;
- snapshot dapat dibuat;
- schema dapat diserialisasi ke JSON;
- schema dapat disimpan ke database;
- schema dapat digunakan untuk membuat preview editor;
- schema dapat digunakan untuk reconstruction;
- automated tests lulus.
