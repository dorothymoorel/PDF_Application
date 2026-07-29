# DATABASE SCHEMA

## TransLoka Local SQLite Data Model Specification

**Document Name:** `DATABASE_SCHEMA.md`  
**Document Version:** 0.1  
**Status:** Draft  
**Decision Date:** 2026-07-26  
**Database Engine:** SQLite  
**ORM:** SQLAlchemy 2  
**Migration Tool:** Alembic  
**Application Mode:** Local-First, Single User  

**Related Documents:**

- `PRD.md`
- `ARCHITECTURE.md`
- `TECH_STACK_DECISIONS.md`
- `DOCUMENT_IR.md`
- `TRANSLATION_PIPELINE.md`
- `GLOSSARY_ENGINE.md`
- `LOCAL_MODEL_BENCHMARK.md`
- `RECONSTRUCTION_ENGINE.md`

---

# 1. Purpose

Dokumen ini menetapkan schema database utama TransLoka untuk Personal MVP.

Schema digunakan untuk menyimpan:

- konfigurasi aplikasi;
- proyek;
- dokumen sumber;
- metadata file;
- Document IR;
- halaman;
- block;
- segment;
- gambar dan aset;
- glossary;
- terminology occurrence;
- translation job;
- hasil terjemahan;
- revision;
- quality report;
- reconstruction;
- export;
- benchmark model;
- backup;
- event operasional.

Database utama disimpan sebagai:

```text
{TRANSLOKA_DATA_DIR}/database/transloka.db
```

Queue Huey menggunakan database berbeda:

```text
{TRANSLOKA_DATA_DIR}/database/tasks.db
```

`tasks.db` dikelola oleh Huey dan bukan bagian dari Alembic migration aplikasi.

---

# 2. Database Authority

Database merupakan sumber kebenaran utama untuk:

- status proyek;
- metadata dokumen;
- struktur aktif Document IR;
- final translation;
- revision history;
- glossary;
- warning;
- job status;
- reconstruction status;
- export metadata.

Filesystem merupakan sumber kebenaran untuk binary dan artifact besar:

- PDF asli;
- page rendering;
- thumbnail;
- gambar;
- raw OCR result;
- Document IR snapshot;
- reconstructed page;
- final PDF;
- backup.

Redis, PostgreSQL, dan cloud database tidak digunakan pada Personal MVP.

---

# 3. Database Principles

## 3.1 Original Content Is Immutable

Field sumber berikut tidak boleh ditimpa oleh hasil terjemahan:

- `source_text`;
- `native_text`;
- `ocr_text`;
- `source_geometry_json`;
- original file record;
- source checksum.

Perubahan hasil OCR oleh pengguna disimpan sebagai correction atau resolved text, bukan menimpa raw OCR result.

## 3.2 Relational Core, JSON for Variable Data

Data yang sering dicari, difilter, atau diperbarui disimpan sebagai column relasional.

Contoh:

- project status;
- page number;
- segment status;
- glossary source term;
- job status;
- warning severity.

Data fleksibel disimpan sebagai JSON text.

Contoh:

- geometry;
- style;
- provider metadata;
- confidence components;
- reconstruction settings;
- validation details.

## 3.3 Files Are Referenced, Not Embedded

Binary file tidak disimpan sebagai BLOB dalam SQLite.

Database hanya menyimpan:

- storage key;
- path relatif;
- MIME type;
- ukuran;
- checksum;
- metadata.

## 3.4 Stable Identifiers

Identifier tidak berubah setelah entity dibuat.

ID tidak boleh bergantung pada:

- urutan row;
- page number;
- filename;
- path;
- translated text.

## 3.5 Explicit Status

Proses panjang harus memiliki status eksplisit.

Jangan menyimpulkan status hanya berdasarkan keberadaan file.

## 3.6 Migration-Only Schema Changes

Perubahan schema hanya dilakukan melalui Alembic migration.

Aplikasi production tidak menggunakan `metadata.create_all()` untuk memperbarui schema.

---

# 4. SQLite Configuration

Setiap koneksi utama harus menjalankan:

```sql
PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;
PRAGMA synchronous = NORMAL;
PRAGMA busy_timeout = 5000;
PRAGMA temp_store = MEMORY;
```

Optional setelah benchmark:

```sql
PRAGMA cache_size = -20000;
PRAGMA mmap_size = 268435456;
```

Nilai optional tidak boleh diasumsikan optimal untuk seluruh komputer.

---

# 5. SQLite File Structure

```text
transloka-data/
└── database/
    ├── transloka.db
    ├── transloka.db-wal
    ├── transloka.db-shm
    └── tasks.db
```

File `-wal` dan `-shm` tidak boleh dihapus saat aplikasi aktif.

Backup tidak boleh dilakukan hanya dengan menyalin `transloka.db` ketika WAL masih aktif tanpa menggunakan SQLite backup mechanism.

---

# 6. Table Mode

Gunakan SQLite `STRICT` tables jika kompatibel dengan migration dan test environment.

Contoh:

```sql
CREATE TABLE projects (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL
) STRICT;
```

Jika `STRICT` menimbulkan masalah compatibility, keputusan perubahan harus dicatat dalam Architecture Decision Record.

---

# 7. Data Type Conventions

| Logical Type | SQLite Type |
|---|---|
| Identifier | `TEXT` |
| String | `TEXT` |
| Long Text | `TEXT` |
| Enum | `TEXT` + `CHECK` |
| Boolean | `INTEGER` + `CHECK (value IN (0,1))` |
| Integer | `INTEGER` |
| Decimal | `REAL` |
| Money | Tidak digunakan |
| DateTime | `TEXT` ISO 8601 UTC |
| JSON | `TEXT` |
| File Size | `INTEGER` |
| Checksum | `TEXT` |
| Binary | Disimpan di filesystem |

---

# 8. Identifier Convention

Gunakan prefixed UUID string.

Contoh:

```text
prj_550e8400-e29b-41d4-a716-446655440000
doc_550e8400-e29b-41d4-a716-446655440000
pag_550e8400-e29b-41d4-a716-446655440000
seg_550e8400-e29b-41d4-a716-446655440000
```

Prefix:

| Entity | Prefix |
|---|---|
| Project | `prj_` |
| Document | `doc_` |
| File | `fil_` |
| Section | `sec_` |
| Page | `pag_` |
| Block | `blk_` |
| Segment | `seg_` |
| Asset | `ast_` |
| Table | `tbl_` |
| Cell | `cel_` |
| Glossary | `gls_` |
| Glossary Term | `trm_` |
| Job | `job_` |
| Translation Batch | `tbt_` |
| Translation Attempt | `tat_` |
| Revision | `rev_` |
| Warning | `wrn_` |
| Export | `exp_` |

UUID dibuat pada application layer.

Database tidak membuat ID otomatis.

---

# 9. Timestamp Convention

Semua timestamp menggunakan UTC ISO 8601.

Contoh:

```text
2026-07-26T08:30:00.123Z
```

Column umum:

```text
created_at TEXT NOT NULL
updated_at TEXT NOT NULL
deleted_at TEXT
```

Database tidak menyimpan local timezone.

Frontend mengubah timestamp untuk tampilan lokal.

---

# 10. Boolean Convention

Boolean disimpan sebagai:

```text
0 = false
1 = true
```

Contoh constraint:

```sql
is_locked INTEGER NOT NULL DEFAULT 0
    CHECK (is_locked IN (0, 1))
```

---

# 11. JSON Convention

JSON disimpan sebagai canonical UTF-8 text.

Column JSON harus diberi suffix:

```text
_json
```

Contoh:

```text
geometry_json
style_json
settings_json
metadata_json
```

Jika SQLite JSON functions tersedia, gunakan validation:

```sql
CHECK (
    geometry_json IS NULL
    OR json_valid(geometry_json)
)
```

Application layer tetap wajib memvalidasi JSON menggunakan Pydantic.

---

# 12. Naming Convention

## Tables

Gunakan plural snake case:

```text
projects
documents
document_pages
translation_batches
```

## Columns

Gunakan snake case:

```text
project_id
created_at
source_language
```

## Foreign Keys

Gunakan:

```text
<entity>_id
```

## Index

Format:

```text
ix_<table>_<columns>
```

## Unique Constraint

Format:

```text
uq_<table>_<columns>
```

## Check Constraint

Format:

```text
ck_<table>_<description>
```

---

# 13. Schema Groups

Schema dibagi menjadi:

1. Application.
2. Projects and Files.
3. Document Structure.
4. Tables and Relationships.
5. Glossary.
6. Translation.
7. Revision and Review.
8. Jobs.
9. Quality.
10. Reconstruction.
11. Export.
12. Model Benchmark.
13. Backup and Maintenance.
14. Operational Events.

---

# 14. Application Tables

## 14.1 `app_metadata`

Menyimpan informasi database dan aplikasi.

| Column | Type | Constraint |
|---|---|---|
| `key` | TEXT | Primary key |
| `value` | TEXT | Not null |
| `updated_at` | TEXT | Not null |

Contoh key:

```text
database_initialized_at
application_version
data_format_version
last_integrity_check_at
```

SQL:

```sql
CREATE TABLE app_metadata (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL
) STRICT;
```

---

## 14.2 `app_settings`

Menyimpan pengaturan lokal.

| Column | Type | Constraint |
|---|---|---|
| `key` | TEXT | Primary key |
| `value_json` | TEXT | Not null, valid JSON |
| `category` | TEXT | Not null |
| `updated_at` | TEXT | Not null |

Category:

```text
GENERAL
STORAGE
TRANSLATION
OCR
RECONSTRUCTION
BACKUP
ADVANCED
```

Secret tidak boleh disimpan di table ini.

Jika suatu secret diperlukan pada fase berikutnya, gunakan environment variable atau OS secret storage.

---

# 15. Project Tables

## 15.1 `projects`

Menyimpan satu proyek terjemahan.

| Column | Type | Constraint |
|---|---|---|
| `id` | TEXT | Primary key |
| `name` | TEXT | Not null |
| `description` | TEXT | Nullable |
| `status` | TEXT | Not null |
| `source_language` | TEXT | Not null |
| `target_language` | TEXT | Not null |
| `document_type` | TEXT | Not null |
| `translation_style` | TEXT | Not null |
| `reconstruction_mode` | TEXT | Not null |
| `progress` | REAL | Not null, 0–1 |
| `active_document_id` | TEXT | Nullable |
| `settings_json` | TEXT | Not null |
| `created_at` | TEXT | Not null |
| `updated_at` | TEXT | Not null |
| `archived_at` | TEXT | Nullable |
| `deleted_at` | TEXT | Nullable |

Status:

```text
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

Constraints:

```sql
CHECK (progress >= 0.0 AND progress <= 1.0)
CHECK (source_language <> '')
CHECK (target_language <> '')
```

Index:

```sql
CREATE INDEX ix_projects_status
ON projects(status);

CREATE INDEX ix_projects_updated_at
ON projects(updated_at DESC);
```

---

# 16. File Tables

## 16.1 `stored_files`

Menyimpan metadata semua file yang dikelola aplikasi.

| Column | Type | Constraint |
|---|---|---|
| `id` | TEXT | Primary key |
| `project_id` | TEXT | Nullable, foreign key |
| `document_id` | TEXT | Nullable, foreign key |
| `file_role` | TEXT | Not null |
| `storage_key` | TEXT | Not null, unique |
| `original_filename` | TEXT | Nullable |
| `safe_filename` | TEXT | Not null |
| `mime_type` | TEXT | Not null |
| `size_bytes` | INTEGER | Not null |
| `checksum_sha256` | TEXT | Not null |
| `is_immutable` | INTEGER | Not null |
| `status` | TEXT | Not null |
| `metadata_json` | TEXT | Nullable |
| `created_at` | TEXT | Not null |
| `deleted_at` | TEXT | Nullable |

File role:

```text
ORIGINAL
PAGE_RENDER
THUMBNAIL
EXTRACTED_ASSET
OCR_INPUT
OCR_OUTPUT
IR_SNAPSHOT
RECONSTRUCTED_PAGE
EXPORT
BACKUP
TEMPORARY
BENCHMARK_REPORT
```

Status:

```text
CREATED
AVAILABLE
VALIDATED
MISSING
CORRUPTED
DELETION_QUEUED
DELETED
```

Constraint:

```sql
CHECK (size_bytes >= 0)
CHECK (is_immutable IN (0,1))
```

Indexes:

```sql
CREATE UNIQUE INDEX uq_stored_files_storage_key
ON stored_files(storage_key);

CREATE INDEX ix_stored_files_project_role
ON stored_files(project_id, file_role);

CREATE INDEX ix_stored_files_checksum
ON stored_files(checksum_sha256);
```

`storage_key` selalu berupa path relatif terhadap `TRANSLOKA_DATA_DIR`.

Absolute path tidak disimpan.

---

# 17. Document Tables

## 17.1 `documents`

Satu project dapat memiliki satu atau beberapa document version, walaupun Personal MVP biasanya menggunakan satu source document.

| Column | Type | Constraint |
|---|---|---|
| `id` | TEXT | Primary key |
| `project_id` | TEXT | Not null, foreign key |
| `original_file_id` | TEXT | Not null, foreign key |
| `ir_version` | TEXT | Not null |
| `title` | TEXT | Nullable |
| `author` | TEXT | Nullable |
| `document_type` | TEXT | Not null |
| `document_class` | TEXT | Not null |
| `source_language` | TEXT | Not null |
| `target_language` | TEXT | Not null |
| `page_count` | INTEGER | Not null |
| `word_count_estimate` | INTEGER | Nullable |
| `has_text_layer` | INTEGER | Not null |
| `scanned_page_count` | INTEGER | Not null |
| `image_count` | INTEGER | Not null |
| `table_count` | INTEGER | Not null |
| `status` | TEXT | Not null |
| `metadata_json` | TEXT | Nullable |
| `analysis_json` | TEXT | Nullable |
| `created_at` | TEXT | Not null |
| `updated_at` | TEXT | Not null |

Document class:

```text
DIGITAL_PDF
SCANNED_PDF
HYBRID_PDF
UNSUPPORTED
CORRUPTED
PASSWORD_PROTECTED
```

Constraints:

```sql
CHECK (page_count >= 0)
CHECK (scanned_page_count >= 0)
CHECK (image_count >= 0)
CHECK (table_count >= 0)
CHECK (has_text_layer IN (0,1))
```

Unique:

```sql
CREATE UNIQUE INDEX uq_documents_project_original_file
ON documents(project_id, original_file_id);
```

---

# 18. Document Section Tables

## 18.1 `document_sections`

| Column | Type | Constraint |
|---|---|---|
| `id` | TEXT | Primary key |
| `document_id` | TEXT | Not null, foreign key |
| `parent_section_id` | TEXT | Nullable, self foreign key |
| `section_type` | TEXT | Not null |
| `level` | INTEGER | Not null |
| `section_order` | INTEGER | Not null |
| `title_segment_id` | TEXT | Nullable |
| `start_page_id` | TEXT | Nullable |
| `end_page_id` | TEXT | Nullable |
| `source_summary` | TEXT | Nullable |
| `context_json` | TEXT | Nullable |
| `created_at` | TEXT | Not null |
| `updated_at` | TEXT | Not null |

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
UNKNOWN
```

Constraints:

```sql
CHECK (level >= 0)
CHECK (section_order >= 0)
```

Unique:

```sql
CREATE UNIQUE INDEX uq_document_sections_order
ON document_sections(document_id, section_order);
```

---

# 19. Page Tables

## 19.1 `document_pages`

| Column | Type | Constraint |
|---|---|---|
| `id` | TEXT | Primary key |
| `document_id` | TEXT | Not null, foreign key |
| `source_page_number` | INTEGER | Not null |
| `logical_page_number` | TEXT | Nullable |
| `width_points` | REAL | Not null |
| `height_points` | REAL | Not null |
| `rotation_degrees` | REAL | Not null |
| `page_type` | TEXT | Not null |
| `page_classification` | TEXT | Nullable |
| `column_count` | INTEGER | Not null |
| `reading_direction` | TEXT | Not null |
| `status` | TEXT | Not null |
| `render_file_id` | TEXT | Nullable |
| `thumbnail_file_id` | TEXT | Nullable |
| `native_extraction_confidence` | REAL | Nullable |
| `ocr_confidence` | REAL | Nullable |
| `structure_confidence` | REAL | Nullable |
| `metadata_json` | TEXT | Nullable |
| `created_at` | TEXT | Not null |
| `updated_at` | TEXT | Not null |

Constraints:

```sql
CHECK (source_page_number >= 1)
CHECK (width_points > 0)
CHECK (height_points > 0)
CHECK (column_count >= 0)
CHECK (
    native_extraction_confidence IS NULL
    OR native_extraction_confidence BETWEEN 0 AND 1
)
CHECK (
    ocr_confidence IS NULL
    OR ocr_confidence BETWEEN 0 AND 1
)
```

Unique:

```sql
CREATE UNIQUE INDEX uq_document_pages_number
ON document_pages(document_id, source_page_number);
```

Indexes:

```sql
CREATE INDEX ix_document_pages_status
ON document_pages(document_id, status);

CREATE INDEX ix_document_pages_type
ON document_pages(document_id, page_type);
```

---

# 20. Block Tables

## 20.1 `document_blocks`

| Column | Type | Constraint |
|---|---|---|
| `id` | TEXT | Primary key |
| `page_id` | TEXT | Not null, foreign key |
| `section_id` | TEXT | Nullable, foreign key |
| `parent_block_id` | TEXT | Nullable, self foreign key |
| `block_type` | TEXT | Not null |
| `semantic_role` | TEXT | Nullable |
| `page_reading_order` | INTEGER | Not null |
| `global_reading_order` | INTEGER | Nullable |
| `source_text` | TEXT | Nullable |
| `normalized_source_text` | TEXT | Nullable |
| `source_geometry_json` | TEXT | Not null |
| `target_geometry_json` | TEXT | Nullable |
| `style_json` | TEXT | Nullable |
| `detail_json` | TEXT | Nullable |
| `status` | TEXT | Not null |
| `confidence` | REAL | Nullable |
| `created_at` | TEXT | Not null |
| `updated_at` | TEXT | Not null |

`detail_json` dapat menyimpan:

- line;
- span;
- token;
- baseline;
- polygon;
- native extraction metadata.

Pada Personal MVP, line, span, dan token tidak disimpan sebagai table terpisah kecuali benchmark menunjukkan kebutuhan query yang kuat.

Constraints:

```sql
CHECK (page_reading_order >= 0)
CHECK (
    confidence IS NULL
    OR confidence BETWEEN 0 AND 1
)
```

Unique:

```sql
CREATE UNIQUE INDEX uq_document_blocks_page_order
ON document_blocks(page_id, page_reading_order);
```

Indexes:

```sql
CREATE INDEX ix_document_blocks_page_type
ON document_blocks(page_id, block_type);

CREATE INDEX ix_document_blocks_section
ON document_blocks(section_id, global_reading_order);
```

---

# 21. Segment Tables

## 21.1 `document_segments`

Segment adalah unit utama terjemahan.

| Column | Type | Constraint |
|---|---|---|
| `id` | TEXT | Primary key |
| `block_id` | TEXT | Not null, foreign key |
| `section_id` | TEXT | Nullable, foreign key |
| `segment_order` | INTEGER | Not null |
| `global_order` | INTEGER | Nullable |
| `source_text` | TEXT | Not null |
| `native_text` | TEXT | Nullable |
| `ocr_text` | TEXT | Nullable |
| `resolved_source_text` | TEXT | Not null |
| `normalized_source_text` | TEXT | Not null |
| `protected_source_text` | TEXT | Nullable |
| `machine_translation` | TEXT | Nullable |
| `reviewed_translation` | TEXT | Nullable |
| `final_text` | TEXT | Nullable |
| `source_language` | TEXT | Not null |
| `target_language` | TEXT | Not null |
| `status` | TEXT | Not null |
| `review_status` | TEXT | Not null |
| `is_locked` | INTEGER | Not null |
| `current_revision` | INTEGER | Not null |
| `confidence_overall` | REAL | Nullable |
| `confidence_json` | TEXT | Nullable |
| `translation_settings_hash` | TEXT | Nullable |
| `created_at` | TEXT | Not null |
| `updated_at` | TEXT | Not null |

Segment status:

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

Review status:

```text
NOT_REVIEWED
REVIEW_REQUIRED
IN_REVIEW
EDITED
APPROVED
REJECTED
```

Constraints:

```sql
CHECK (segment_order >= 0)
CHECK (current_revision >= 0)
CHECK (is_locked IN (0,1))
CHECK (
    confidence_overall IS NULL
    OR confidence_overall BETWEEN 0 AND 1
)
```

Unique:

```sql
CREATE UNIQUE INDEX uq_document_segments_block_order
ON document_segments(block_id, segment_order);
```

Indexes:

```sql
CREATE INDEX ix_document_segments_status
ON document_segments(status);

CREATE INDEX ix_document_segments_review_status
ON document_segments(review_status);

CREATE INDEX ix_document_segments_section_order
ON document_segments(section_id, global_order);

CREATE INDEX ix_document_segments_block
ON document_segments(block_id);
```

---

# 22. Source Fragment Mapping

## 22.1 `segment_fragments`

Digunakan ketika satu segment berasal dari lebih dari satu region atau halaman.

| Column | Type | Constraint |
|---|---|---|
| `id` | TEXT | Primary key |
| `segment_id` | TEXT | Not null, foreign key |
| `page_id` | TEXT | Not null, foreign key |
| `block_id` | TEXT | Nullable, foreign key |
| `fragment_order` | INTEGER | Not null |
| `source_geometry_json` | TEXT | Not null |
| `source_text` | TEXT | Nullable |
| `created_at` | TEXT | Not null |

Unique:

```sql
CREATE UNIQUE INDEX uq_segment_fragments_order
ON segment_fragments(segment_id, fragment_order);
```

---

# 23. Asset Tables

## 23.1 `document_assets`

| Column | Type | Constraint |
|---|---|---|
| `id` | TEXT | Primary key |
| `document_id` | TEXT | Not null, foreign key |
| `page_id` | TEXT | Nullable, foreign key |
| `file_id` | TEXT | Not null, foreign key |
| `asset_type` | TEXT | Not null |
| `source_geometry_json` | TEXT | Nullable |
| `target_geometry_json` | TEXT | Nullable |
| `width_pixels` | INTEGER | Nullable |
| `height_pixels` | INTEGER | Nullable |
| `dpi` | REAL | Nullable |
| `rotation_degrees` | REAL | Not null |
| `z_index` | INTEGER | Not null |
| `caption_block_id` | TEXT | Nullable |
| `preservation_policy` | TEXT | Not null |
| `metadata_json` | TEXT | Nullable |
| `created_at` | TEXT | Not null |
| `updated_at` | TEXT | Not null |

Asset type:

```text
RASTER_IMAGE
VECTOR_IMAGE
CHART
DIAGRAM
LOGO
ICON
BACKGROUND
DECORATIVE_ELEMENT
FONT
EMBEDDED_FILE
UNKNOWN
```

Constraint:

```sql
CHECK (width_pixels IS NULL OR width_pixels >= 0)
CHECK (height_pixels IS NULL OR height_pixels >= 0)
```

Indexes:

```sql
CREATE INDEX ix_document_assets_page
ON document_assets(page_id);

CREATE INDEX ix_document_assets_type
ON document_assets(document_id, asset_type);
```

---

# 24. Table Structure Tables

## 24.1 `document_tables`

| Column | Type | Constraint |
|---|---|---|
| `id` | TEXT | Primary key |
| `block_id` | TEXT | Not null, unique, foreign key |
| `row_count` | INTEGER | Not null |
| `column_count` | INTEGER | Not null |
| `complexity` | TEXT | Not null |
| `has_header_row` | INTEGER | Not null |
| `has_header_column` | INTEGER | Not null |
| `source_geometry_json` | TEXT | Not null |
| `target_geometry_json` | TEXT | Nullable |
| `continuation_of_table_id` | TEXT | Nullable |
| `status` | TEXT | Not null |
| `confidence` | REAL | Nullable |
| `metadata_json` | TEXT | Nullable |
| `created_at` | TEXT | Not null |
| `updated_at` | TEXT | Not null |

Complexity:

```text
SIMPLE
MODERATE
COMPLEX
UNRECOGNIZED
```

Constraints:

```sql
CHECK (row_count >= 0)
CHECK (column_count >= 0)
CHECK (has_header_row IN (0,1))
CHECK (has_header_column IN (0,1))
```

---

## 24.2 `document_table_cells`

| Column | Type | Constraint |
|---|---|---|
| `id` | TEXT | Primary key |
| `table_id` | TEXT | Not null, foreign key |
| `row_index` | INTEGER | Not null |
| `column_index` | INTEGER | Not null |
| `row_span` | INTEGER | Not null |
| `column_span` | INTEGER | Not null |
| `cell_role` | TEXT | Not null |
| `source_text` | TEXT | Nullable |
| `segment_id` | TEXT | Nullable, foreign key |
| `source_geometry_json` | TEXT | Not null |
| `target_geometry_json` | TEXT | Nullable |
| `style_json` | TEXT | Nullable |
| `created_at` | TEXT | Not null |
| `updated_at` | TEXT | Not null |

Constraints:

```sql
CHECK (row_index >= 0)
CHECK (column_index >= 0)
CHECK (row_span >= 1)
CHECK (column_span >= 1)
```

Unique:

```sql
CREATE UNIQUE INDEX uq_document_table_cells_position
ON document_table_cells(table_id, row_index, column_index);
```

---

# 25. Annotation and Relationship Tables

## 25.1 `document_annotations`

| Column | Type |
|---|---|
| `id` | TEXT primary key |
| `page_id` | TEXT foreign key |
| `annotation_type` | TEXT |
| `source_geometry_json` | TEXT |
| `target_geometry_json` | TEXT nullable |
| `visible_text` | TEXT nullable |
| `target_value` | TEXT nullable |
| `preservation_policy` | TEXT |
| `status` | TEXT |
| `metadata_json` | TEXT nullable |
| `created_at` | TEXT |
| `updated_at` | TEXT |

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

## 25.2 `document_relationships`

| Column | Type |
|---|---|
| `id` | TEXT primary key |
| `document_id` | TEXT foreign key |
| `relationship_type` | TEXT |
| `source_entity_type` | TEXT |
| `source_entity_id` | TEXT |
| `target_entity_type` | TEXT |
| `target_entity_id` | TEXT |
| `confidence` | REAL nullable |
| `metadata_json` | TEXT nullable |
| `created_at` | TEXT |

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

Polymorphic entity IDs tidak menggunakan foreign key langsung. Application validator wajib memeriksa referential integrity.

---

# 26. Footnote Tables

## 26.1 `document_footnotes`

| Column | Type |
|---|---|
| `id` | TEXT primary key |
| `document_id` | TEXT foreign key |
| `reference_segment_id` | TEXT foreign key |
| `note_block_id` | TEXT foreign key |
| `marker` | TEXT |
| `source_page_id` | TEXT foreign key |
| `target_page_id` | TEXT nullable |
| `status` | TEXT |
| `created_at` | TEXT |
| `updated_at` | TEXT |

Unique:

```sql
CREATE UNIQUE INDEX uq_document_footnotes_reference
ON document_footnotes(reference_segment_id, marker);
```

---

# 27. Glossary Tables

## 27.1 `glossaries`

| Column | Type | Constraint |
|---|---|---|
| `id` | TEXT | Primary key |
| `project_id` | TEXT | Nullable, foreign key |
| `name` | TEXT | Not null |
| `description` | TEXT | Nullable |
| `source_language` | TEXT | Not null |
| `target_language` | TEXT | Not null |
| `scope` | TEXT | Not null |
| `domain` | TEXT | Nullable |
| `status` | TEXT | Not null |
| `version` | INTEGER | Not null |
| `is_default` | INTEGER | Not null |
| `created_at` | TEXT | Not null |
| `updated_at` | TEXT | Not null |
| `deleted_at` | TEXT | Nullable |

Personal MVP scope:

```text
SYSTEM
DOMAIN
USER
PROJECT
DOCUMENT
SECTION
PAGE
SEGMENT
```

`USER` berarti glossary personal lokal, bukan multi-user account.

Constraint:

```sql
CHECK (version >= 1)
CHECK (is_default IN (0,1))
```

---

## 27.2 `glossary_terms`

| Column | Type | Constraint |
|---|---|---|
| `id` | TEXT | Primary key |
| `glossary_id` | TEXT | Not null, foreign key |
| `source_term` | TEXT | Not null |
| `normalized_source_term` | TEXT | Not null |
| `rule_type` | TEXT | Not null |
| `target_term` | TEXT | Nullable |
| `scope` | TEXT | Not null |
| `scope_reference_id` | TEXT | Nullable |
| `priority` | INTEGER | Not null |
| `case_sensitive` | INTEGER | Not null |
| `whole_word` | INTEGER | Not null |
| `match_mode` | TEXT | Not null |
| `capitalization_policy` | TEXT | Not null |
| `inflection_policy` | TEXT | Not null |
| `first_use_policy` | TEXT | Not null |
| `status` | TEXT | Not null |
| `term_source` | TEXT | Not null |
| `confidence` | REAL | Nullable |
| `notes` | TEXT | Nullable |
| `created_at` | TEXT | Not null |
| `updated_at` | TEXT | Not null |

Constraint:

```sql
CHECK (priority >= 0)
CHECK (case_sensitive IN (0,1))
CHECK (whole_word IN (0,1))
CHECK (
    rule_type <> 'TRANSLATE_AS'
    OR target_term IS NOT NULL
)
```

Index:

```sql
CREATE INDEX ix_glossary_terms_normalized
ON glossary_terms(normalized_source_term);

CREATE INDEX ix_glossary_terms_active
ON glossary_terms(glossary_id, status, priority DESC);
```

Potential duplicate constraint:

```sql
CREATE UNIQUE INDEX uq_glossary_terms_identity
ON glossary_terms(
    glossary_id,
    normalized_source_term,
    scope,
    COALESCE(scope_reference_id, '')
)
WHERE status NOT IN ('ARCHIVED', 'REJECTED');
```

Jika SQLite expression index menimbulkan compatibility issue, uniqueness diverifikasi pada service layer.

---

## 27.3 `glossary_context_rules`

| Column | Type |
|---|---|
| `id` | TEXT primary key |
| `term_id` | TEXT foreign key |
| `condition_type` | TEXT |
| `operator` | TEXT |
| `condition_value_json` | TEXT |
| `result_rule_type` | TEXT |
| `result_target_term` | TEXT nullable |
| `priority` | INTEGER |
| `status` | TEXT |
| `created_at` | TEXT |
| `updated_at` | TEXT |

---

## 27.4 `glossary_revisions`

| Column | Type |
|---|---|
| `id` | TEXT primary key |
| `term_id` | TEXT foreign key |
| `revision_number` | INTEGER |
| `revision_type` | TEXT |
| `previous_value_json` | TEXT nullable |
| `new_value_json` | TEXT |
| `reason` | TEXT nullable |
| `created_at` | TEXT |

Unique:

```sql
CREATE UNIQUE INDEX uq_glossary_revisions_number
ON glossary_revisions(term_id, revision_number);
```

---

## 27.5 `glossary_snapshots`

Snapshot bersifat immutable.

| Column | Type |
|---|---|
| `id` | TEXT primary key |
| `project_id` | TEXT foreign key |
| `document_id` | TEXT nullable, foreign key |
| `version` | INTEGER |
| `checksum_sha256` | TEXT |
| `term_count` | INTEGER |
| `source_versions_json` | TEXT |
| `snapshot_file_id` | TEXT foreign key |
| `created_at` | TEXT |

Unique:

```sql
CREATE UNIQUE INDEX uq_glossary_snapshots_version
ON glossary_snapshots(project_id, version);
```

Snapshot tidak boleh diperbarui setelah dibuat.

---

## 27.6 `term_candidates`

| Column | Type |
|---|---|
| `id` | TEXT primary key |
| `project_id` | TEXT foreign key |
| `document_id` | TEXT foreign key |
| `source_term` | TEXT |
| `normalized_source_term` | TEXT |
| `candidate_type` | TEXT |
| `recommended_rule_type` | TEXT |
| `recommended_target_term` | TEXT nullable |
| `occurrence_count` | INTEGER |
| `confidence` | REAL |
| `status` | TEXT |
| `created_at` | TEXT |
| `updated_at` | TEXT |

Unique:

```sql
CREATE UNIQUE INDEX uq_term_candidates_project_term
ON term_candidates(project_id, normalized_source_term);
```

---

## 27.7 `term_occurrences`

| Column | Type |
|---|---|
| `id` | TEXT primary key |
| `project_id` | TEXT foreign key |
| `document_id` | TEXT foreign key |
| `term_id` | TEXT nullable, foreign key |
| `candidate_id` | TEXT nullable, foreign key |
| `segment_id` | TEXT foreign key |
| `page_id` | TEXT foreign key |
| `start_offset` | INTEGER |
| `end_offset` | INTEGER |
| `matched_text` | TEXT |
| `match_method` | TEXT |
| `confidence` | REAL nullable |
| `created_at` | TEXT |

Constraint:

```sql
CHECK (start_offset >= 0)
CHECK (end_offset > start_offset)
CHECK (term_id IS NOT NULL OR candidate_id IS NOT NULL)
```

Indexes:

```sql
CREATE INDEX ix_term_occurrences_term
ON term_occurrences(term_id);

CREATE INDEX ix_term_occurrences_candidate
ON term_occurrences(candidate_id);

CREATE INDEX ix_term_occurrences_segment
ON term_occurrences(segment_id);
```

---

## 27.8 `glossary_conflicts`

| Column | Type |
|---|---|
| `id` | TEXT primary key |
| `project_id` | TEXT foreign key |
| `source_term` | TEXT |
| `conflict_type` | TEXT |
| `rules_json` | TEXT |
| `status` | TEXT |
| `resolution_type` | TEXT nullable |
| `resolution_json` | TEXT nullable |
| `created_at` | TEXT |
| `resolved_at` | TEXT nullable |

---

# 28. Protected Content Tables

## 28.1 `protected_items`

| Column | Type |
|---|---|
| `id` | TEXT primary key |
| `segment_id` | TEXT foreign key |
| `glossary_term_id` | TEXT nullable, foreign key |
| `item_type` | TEXT |
| `placeholder` | TEXT |
| `source_value` | TEXT |
| `replacement_value` | TEXT |
| `rule_type` | TEXT |
| `start_offset` | INTEGER |
| `end_offset` | INTEGER |
| `capitalization_policy` | TEXT |
| `status` | TEXT |
| `created_at` | TEXT |
| `restored_at` | TEXT nullable |

Unique:

```sql
CREATE UNIQUE INDEX uq_protected_items_placeholder
ON protected_items(segment_id, placeholder);
```

---

# 29. Translation Tables

## 29.1 `translation_batches`

| Column | Type |
|---|---|
| `id` | TEXT primary key |
| `project_id` | TEXT foreign key |
| `document_id` | TEXT foreign key |
| `section_id` | TEXT nullable |
| `glossary_snapshot_id` | TEXT foreign key |
| `provider_type` | TEXT |
| `model_id` | TEXT |
| `prompt_version` | TEXT |
| `pipeline_version` | TEXT |
| `status` | TEXT |
| `segment_count` | INTEGER |
| `source_character_count` | INTEGER |
| `estimated_input_tokens` | INTEGER nullable |
| `actual_input_tokens` | INTEGER nullable |
| `actual_output_tokens` | INTEGER nullable |
| `batch_order` | INTEGER |
| `idempotency_key` | TEXT unique |
| `settings_json` | TEXT |
| `created_at` | TEXT |
| `started_at` | TEXT nullable |
| `completed_at` | TEXT nullable |
| `error_code` | TEXT nullable |

Indexes:

```sql
CREATE INDEX ix_translation_batches_project_status
ON translation_batches(project_id, status);

CREATE INDEX ix_translation_batches_document_order
ON translation_batches(document_id, batch_order);
```

---

## 29.2 `translation_batch_segments`

Join table.

| Column | Type |
|---|---|
| `batch_id` | TEXT foreign key |
| `segment_id` | TEXT foreign key |
| `segment_order` | INTEGER |

Primary key:

```sql
PRIMARY KEY (batch_id, segment_id)
```

Unique:

```sql
CREATE UNIQUE INDEX uq_translation_batch_segments_order
ON translation_batch_segments(batch_id, segment_order);
```

---

## 29.3 `translation_attempts`

| Column | Type |
|---|---|
| `id` | TEXT primary key |
| `batch_id` | TEXT foreign key |
| `attempt_number` | INTEGER |
| `provider_type` | TEXT |
| `model_id` | TEXT |
| `status` | TEXT |
| `request_hash` | TEXT |
| `response_hash` | TEXT nullable |
| `latency_ms` | INTEGER nullable |
| `input_tokens` | INTEGER nullable |
| `output_tokens` | INTEGER nullable |
| `retry_reason` | TEXT nullable |
| `error_code` | TEXT nullable |
| `error_message` | TEXT nullable |
| `provider_metadata_json` | TEXT nullable |
| `created_at` | TEXT |
| `completed_at` | TEXT nullable |

Unique:

```sql
CREATE UNIQUE INDEX uq_translation_attempts_number
ON translation_attempts(batch_id, attempt_number);
```

---

## 29.4 `segment_translations`

Menyimpan hasil per attempt tanpa menimpa hasil sebelumnya.

| Column | Type |
|---|---|
| `id` | TEXT primary key |
| `segment_id` | TEXT foreign key |
| `batch_id` | TEXT foreign key |
| `attempt_id` | TEXT foreign key |
| `translated_text_raw` | TEXT |
| `translated_text_restored` | TEXT nullable |
| `status` | TEXT |
| `confidence_overall` | REAL nullable |
| `confidence_json` | TEXT nullable |
| `validation_status` | TEXT |
| `created_at` | TEXT |

Index:

```sql
CREATE INDEX ix_segment_translations_segment
ON segment_translations(segment_id, created_at DESC);
```

---

## 29.5 `translation_validations`

| Column | Type |
|---|---|
| `id` | TEXT primary key |
| `segment_translation_id` | TEXT foreign key |
| `validator_type` | TEXT |
| `status` | TEXT |
| `score` | REAL nullable |
| `details_json` | TEXT nullable |
| `created_at` | TEXT |

Validator type:

```text
SEGMENT_MAPPING
PLACEHOLDER_INTEGRITY
NUMERICAL_INTEGRITY
URL_INTEGRITY
CODE_INTEGRITY
CITATION_INTEGRITY
LANGUAGE
TERMINOLOGY
SEMANTIC
LENGTH_RATIO
HALLUCINATION
```

Unique:

```sql
CREATE UNIQUE INDEX uq_translation_validations_type
ON translation_validations(
    segment_translation_id,
    validator_type
);
```

---

# 30. Segment Revision Tables

## 30.1 `segment_revisions`

| Column | Type |
|---|---|
| `id` | TEXT primary key |
| `segment_id` | TEXT foreign key |
| `revision_number` | INTEGER |
| `revision_type` | TEXT |
| `previous_text` | TEXT nullable |
| `new_text` | TEXT |
| `source_translation_id` | TEXT nullable |
| `reason` | TEXT nullable |
| `metadata_json` | TEXT nullable |
| `created_at` | TEXT |

Revision type:

```text
MACHINE_TRANSLATION
AUTOMATIC_RETRY
GLOSSARY_REAPPLICATION
USER_EDIT
APPROVE
UNAPPROVE
LOCK
UNLOCK
RESTORE_VERSION
```

Unique:

```sql
CREATE UNIQUE INDEX uq_segment_revisions_number
ON segment_revisions(segment_id, revision_number);
```

Current segment state is stored in `document_segments`.

Revision table is append-only.

---

# 31. Comment Tables

## 31.1 `review_comments`

Walaupun Personal MVP hanya memiliki satu pengguna, komentar tetap berguna sebagai catatan.

| Column | Type |
|---|---|
| `id` | TEXT primary key |
| `project_id` | TEXT foreign key |
| `scope_type` | TEXT |
| `scope_id` | TEXT |
| `content` | TEXT |
| `status` | TEXT |
| `created_at` | TEXT |
| `resolved_at` | TEXT nullable |

Status:

```text
OPEN
RESOLVED
ARCHIVED
```

---

# 32. Application Job Tables

Huey mengatur task execution pada `tasks.db`.

Database utama tetap menyimpan business job.

## 32.1 `application_jobs`

| Column | Type |
|---|---|
| `id` | TEXT primary key |
| `project_id` | TEXT nullable, foreign key |
| `document_id` | TEXT nullable, foreign key |
| `parent_job_id` | TEXT nullable |
| `job_type` | TEXT |
| `queue_name` | TEXT |
| `status` | TEXT |
| `progress` | REAL |
| `current_stage` | TEXT nullable |
| `idempotency_key` | TEXT unique |
| `payload_json` | TEXT |
| `result_json` | TEXT nullable |
| `retry_count` | INTEGER |
| `max_retries` | INTEGER |
| `error_code` | TEXT nullable |
| `error_message` | TEXT nullable |
| `created_at` | TEXT |
| `queued_at` | TEXT nullable |
| `started_at` | TEXT nullable |
| `completed_at` | TEXT nullable |
| `cancelled_at` | TEXT nullable |
| `heartbeat_at` | TEXT nullable |

`document_id` mereferensikan `documents.id`, sehingga migration ini dijalankan setelah model dan migration document dari M3-T06 tersedia.

Job type:

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

Status:

```text
CREATED
QUEUED
RUNNING
RETRYING
COMPLETED
COMPLETED_WITH_WARNINGS
PARTIALLY_COMPLETED
FAILED
CANCELLATION_REQUESTED
CANCELLED
STALE
```

Constraints:

```sql
CHECK (progress BETWEEN 0 AND 1)
CHECK (retry_count >= 0)
CHECK (max_retries >= 0)
```

Indexes:

```sql
CREATE INDEX ix_application_jobs_project_status
ON application_jobs(project_id, status);

CREATE INDEX ix_application_jobs_type_status
ON application_jobs(job_type, status);

CREATE INDEX ix_application_jobs_heartbeat
ON application_jobs(status, heartbeat_at);
```

---

## 32.2 `job_attempts`

| Column | Type |
|---|---|
| `id` | TEXT primary key |
| `job_id` | TEXT foreign key |
| `attempt_number` | INTEGER |
| `status` | TEXT |
| `worker_identifier` | TEXT nullable |
| `started_at` | TEXT |
| `completed_at` | TEXT nullable |
| `duration_ms` | INTEGER nullable |
| `error_code` | TEXT nullable |
| `error_message` | TEXT nullable |
| `details_json` | TEXT nullable |

Status:

```text
RUNNING
COMPLETED
COMPLETED_WITH_WARNINGS
PARTIALLY_COMPLETED
FAILED
CANCELLED
STALE
```

Unique:

```sql
CREATE UNIQUE INDEX uq_job_attempts_number
ON job_attempts(job_id, attempt_number);
```

---

## 32.3 `job_dependencies`

| Column | Type |
|---|---|
| `job_id` | TEXT foreign key |
| `depends_on_job_id` | TEXT foreign key |
| `dependency_type` | TEXT |

Primary key:

```sql
PRIMARY KEY (job_id, depends_on_job_id)
```

Dependency type:

```text
REQUIRED
OPTIONAL
ORDER_ONLY
```

---

# 33. Quality Tables

## 33.1 `quality_reports`

| Column | Type |
|---|---|
| `id` | TEXT primary key |
| `project_id` | TEXT foreign key |
| `document_id` | TEXT foreign key |
| `report_type` | TEXT |
| `version` | TEXT |
| `status` | TEXT |
| `overall_score` | REAL nullable |
| `critical_warning_count` | INTEGER |
| `high_warning_count` | INTEGER |
| `medium_warning_count` | INTEGER |
| `low_warning_count` | INTEGER |
| `summary_json` | TEXT nullable |
| `created_at` | TEXT |

Report type:

```text
EXTRACTION
OCR
TRANSLATION
TERMINOLOGY
RECONSTRUCTION
FINAL_EXPORT
```

---

## 33.2 `quality_checks`

| Column | Type |
|---|---|
| `id` | TEXT primary key |
| `report_id` | TEXT foreign key |
| `check_type` | TEXT |
| `scope_type` | TEXT |
| `scope_id` | TEXT |
| `status` | TEXT |
| `score` | REAL nullable |
| `details_json` | TEXT nullable |
| `created_at` | TEXT |

---

## 33.3 `warnings`

Satu warning table untuk seluruh pipeline.

| Column | Type |
|---|---|
| `id` | TEXT primary key |
| `project_id` | TEXT foreign key |
| `document_id` | TEXT nullable |
| `page_id` | TEXT nullable |
| `block_id` | TEXT nullable |
| `segment_id` | TEXT nullable |
| `job_id` | TEXT nullable |
| `warning_type` | TEXT |
| `severity` | TEXT |
| `message` | TEXT |
| `details_json` | TEXT nullable |
| `status` | TEXT |
| `resolution_type` | TEXT nullable |
| `resolution_note` | TEXT nullable |
| `created_at` | TEXT |
| `resolved_at` | TEXT nullable |

Severity:

```text
INFO
LOW
MEDIUM
HIGH
CRITICAL
```

Status:

```text
OPEN
RESOLVED
ACCEPTED
FALSE_POSITIVE
IGNORED_BY_POLICY
```

Indexes:

```sql
CREATE INDEX ix_warnings_project_open
ON warnings(project_id, status, severity);

CREATE INDEX ix_warnings_segment
ON warnings(segment_id);

CREATE INDEX ix_warnings_page
ON warnings(page_id);
```

---

# 34. Reconstruction Tables

## 34.1 `reconstruction_jobs`

| Column | Type |
|---|---|
| `id` | TEXT primary key |
| `project_id` | TEXT foreign key |
| `document_id` | TEXT foreign key |
| `application_job_id` | TEXT nullable, foreign key |
| `mode` | TEXT |
| `settings_version` | TEXT |
| `settings_json` | TEXT |
| `status` | TEXT |
| `progress` | REAL |
| `reconstruction_hash` | TEXT |
| `created_at` | TEXT |
| `started_at` | TEXT nullable |
| `completed_at` | TEXT nullable |
| `error_code` | TEXT nullable |

Unique:

```sql
CREATE UNIQUE INDEX uq_reconstruction_jobs_hash
ON reconstruction_jobs(
    project_id,
    reconstruction_hash
)
WHERE status IN ('COMPLETED', 'COMPLETED_WITH_WARNINGS');
```

---

## 34.2 `reconstruction_pages`

| Column | Type |
|---|---|
| `id` | TEXT primary key |
| `reconstruction_job_id` | TEXT foreign key |
| `source_page_id` | TEXT foreign key |
| `target_page_start` | INTEGER |
| `target_page_end` | INTEGER |
| `strategy` | TEXT |
| `status` | TEXT |
| `output_file_id` | TEXT nullable, foreign key |
| `page_hash` | TEXT |
| `warning_count` | INTEGER |
| `metadata_json` | TEXT nullable |
| `created_at` | TEXT |
| `updated_at` | TEXT |

---

## 34.3 `reconstruction_blocks`

| Column | Type |
|---|---|
| `id` | TEXT primary key |
| `reconstruction_page_id` | TEXT foreign key |
| `block_id` | TEXT foreign key |
| `strategy` | TEXT |
| `fit_strategy` | TEXT nullable |
| `source_geometry_json` | TEXT |
| `target_geometry_json` | TEXT nullable |
| `status` | TEXT |
| `font_mapping_json` | TEXT nullable |
| `overflow_json` | TEXT nullable |
| `collision_json` | TEXT nullable |
| `created_at` | TEXT |
| `updated_at` | TEXT |

Unique:

```sql
CREATE UNIQUE INDEX uq_reconstruction_blocks_page_block
ON reconstruction_blocks(
    reconstruction_page_id,
    block_id
);
```

---

## 34.4 `target_page_mappings`

| Column | Type |
|---|---|
| `id` | TEXT primary key |
| `reconstruction_job_id` | TEXT foreign key |
| `source_page_id` | TEXT foreign key |
| `target_page_number` | INTEGER |
| `mapping_type` | TEXT |
| `mapping_order` | INTEGER |
| `created_at` | TEXT |

Mapping type:

```text
ONE_TO_ONE
ONE_TO_MANY
MANY_TO_ONE
UNMAPPED
```

---

# 35. Export Tables

## 35.1 `exports`

| Column | Type |
|---|---|
| `id` | TEXT primary key |
| `project_id` | TEXT foreign key |
| `document_id` | TEXT foreign key |
| `reconstruction_job_id` | TEXT nullable, foreign key |
| `file_id` | TEXT nullable, foreign key |
| `export_type` | TEXT |
| `output_profile` | TEXT |
| `version_number` | INTEGER |
| `status` | TEXT |
| `page_count` | INTEGER nullable |
| `size_bytes` | INTEGER nullable |
| `checksum_sha256` | TEXT nullable |
| `validation_report_id` | TEXT nullable |
| `settings_json` | TEXT |
| `created_at` | TEXT |
| `completed_at` | TEXT nullable |
| `error_code` | TEXT nullable |

Export type:

```text
TRANSLATED_PDF
BILINGUAL_PDF
QUALITY_REPORT
GLOSSARY_CSV
DOCUMENT_IR_PACKAGE
```

Unique:

```sql
CREATE UNIQUE INDEX uq_exports_project_type_version
ON exports(project_id, export_type, version_number);
```

---

# 36. Document IR Snapshot Tables

## 36.1 `document_ir_snapshots`

| Column | Type |
|---|---|
| `id` | TEXT primary key |
| `document_id` | TEXT foreign key |
| `snapshot_type` | TEXT |
| `ir_version` | TEXT |
| `revision_number` | INTEGER |
| `file_id` | TEXT foreign key |
| `checksum_sha256` | TEXT |
| `created_at` | TEXT |

Snapshot type:

```text
EXTRACTED
OCR_COMPLETE
STRUCTURED
TERMS_DETECTED
TRANSLATED
REVIEWED
RECONSTRUCTED
EXPORTED
```

Unique:

```sql
CREATE UNIQUE INDEX uq_document_ir_snapshots_revision
ON document_ir_snapshots(
    document_id,
    snapshot_type,
    revision_number
);
```

---

# 37. Model Benchmark Tables

## 37.1 `hardware_profiles`

| Column | Type |
|---|---|
| `id` | TEXT primary key |
| `operating_system` | TEXT |
| `operating_system_version` | TEXT nullable |
| `cpu_model` | TEXT nullable |
| `physical_cores` | INTEGER nullable |
| `logical_cores` | INTEGER nullable |
| `ram_total_gb` | REAL nullable |
| `gpu_vendor` | TEXT nullable |
| `gpu_model` | TEXT nullable |
| `gpu_vram_total_gb` | REAL nullable |
| `disk_free_gb` | REAL nullable |
| `ollama_version` | TEXT nullable |
| `details_json` | TEXT nullable |
| `created_at` | TEXT |

---

## 37.2 `local_models`

| Column | Type |
|---|---|
| `id` | TEXT primary key |
| `ollama_model_name` | TEXT unique |
| `model_family` | TEXT nullable |
| `parameter_class` | TEXT nullable |
| `quantization` | TEXT nullable |
| `disk_size_bytes` | INTEGER nullable |
| `license_name` | TEXT nullable |
| `license_status` | TEXT |
| `is_installed` | INTEGER |
| `is_selected_translation` | INTEGER |
| `is_selected_validation` | INTEGER |
| `metadata_json` | TEXT nullable |
| `last_detected_at` | TEXT |

---

## 37.3 `benchmark_runs`

| Column | Type |
|---|---|
| `id` | TEXT primary key |
| `hardware_profile_id` | TEXT foreign key |
| `local_model_id` | TEXT foreign key |
| `benchmark_version` | TEXT |
| `dataset_version` | TEXT |
| `prompt_version` | TEXT |
| `profile` | TEXT |
| `status` | TEXT |
| `settings_json` | TEXT |
| `started_at` | TEXT |
| `completed_at` | TEXT nullable |
| `error_code` | TEXT nullable |

---

## 37.4 `benchmark_results`

| Column | Type |
|---|---|
| `id` | TEXT primary key |
| `benchmark_run_id` | TEXT unique, foreign key |
| `quality_json` | TEXT |
| `performance_json` | TEXT |
| `stability_json` | TEXT |
| `overall_score` | REAL nullable |
| `recommendation_status` | TEXT |
| `report_file_id` | TEXT nullable |
| `created_at` | TEXT |

---

# 38. Backup Tables

## 38.1 `backups`

| Column | Type |
|---|---|
| `id` | TEXT primary key |
| `backup_type` | TEXT |
| `file_id` | TEXT foreign key |
| `application_version` | TEXT |
| `database_schema_version` | TEXT |
| `status` | TEXT |
| `size_bytes` | INTEGER nullable |
| `checksum_sha256` | TEXT nullable |
| `included_content_json` | TEXT |
| `created_at` | TEXT |
| `completed_at` | TEXT nullable |
| `error_code` | TEXT nullable |

Backup type:

```text
DATABASE_ONLY
METADATA
FULL_PROJECTS
FULL_APPLICATION
PRE_RESTORE
```

---

## 38.2 `maintenance_runs`

| Column | Type |
|---|---|
| `id` | TEXT primary key |
| `maintenance_type` | TEXT |
| `status` | TEXT |
| `details_json` | TEXT nullable |
| `started_at` | TEXT |
| `completed_at` | TEXT nullable |
| `error_code` | TEXT nullable |

Maintenance type:

```text
DATABASE_INTEGRITY_CHECK
FILE_INTEGRITY_CHECK
CACHE_CLEANUP
TEMP_CLEANUP
ORPHAN_FILE_SCAN
VACUUM
BACKUP_VERIFY
```

---

# 39. Operational Event Table

## 39.1 `operation_events`

Personal MVP tidak membutuhkan audit keamanan multi-user, tetapi membutuhkan event history untuk troubleshooting.

| Column | Type |
|---|---|
| `id` | TEXT primary key |
| `project_id` | TEXT nullable |
| `document_id` | TEXT nullable |
| `job_id` | TEXT nullable |
| `event_type` | TEXT |
| `severity` | TEXT |
| `message` | TEXT |
| `metadata_json` | TEXT nullable |
| `created_at` | TEXT |

Jangan menyimpan:

- full document text;
- full translation prompt;
- model secret;
- absolute personal path;
- isi PDF.

---

# 40. Foreign Key Deletion Policy

## Cascade Delete

Gunakan `ON DELETE CASCADE` untuk child yang tidak bermakna tanpa parent:

```text
project → document
document → page
page → block
block → segment
table → cell
batch → attempt
segment → protected item
report → quality check
```

## Restrict Delete

Gunakan `ON DELETE RESTRICT` untuk entity yang masih direferensikan output atau history:

```text
stored file yang menjadi original
glossary snapshot yang digunakan translation batch
translation attempt yang digunakan revision
reconstruction job yang digunakan export
```

## Set Null

Gunakan `ON DELETE SET NULL` untuk optional operational reference:

```text
warning.job_id
project.active_document_id
comment scope yang telah dihapus
```

---

# 41. Project Deletion Flow

Project tidak langsung dihapus dari route request.

Flow:

```text
ACTIVE
→ DELETION_QUEUED
→ worker validates dependencies
→ files moved to deletion state
→ database children deleted in transaction
→ files deleted
→ deletion verified
```

Jika file deletion gagal:

```text
PARTIALLY_DELETED
```

Project record dapat dipertahankan sementara sebagai tombstone tanpa isi dokumen.

---

# 42. Transaction Boundaries

Gunakan transaction pendek.

Transaction tidak boleh tetap terbuka ketika:

- memanggil Ollama;
- menjalankan OCR;
- merender halaman;
- membaca PDF besar;
- menulis export;
- menunggu user input.

Pattern:

```text
Read required records
→ close transaction
→ perform heavy operation
→ open transaction
→ write result
→ close transaction
```

---

# 43. Optimistic Locking

Entity yang sering diedit menggunakan revision number:

- `document_segments`;
- `glossaries`;
- `glossary_terms`;
- project settings.

Update harus menyertakan expected revision.

Contoh:

```sql
UPDATE document_segments
SET
    reviewed_translation = :text,
    current_revision = current_revision + 1,
    updated_at = :updated_at
WHERE id = :segment_id
  AND current_revision = :expected_revision;
```

Jika affected row `0`:

```text
409 CONFLICT
```

---

# 44. Full-Text Search

Personal MVP menggunakan SQLite FTS5 jika tersedia.

Virtual table:

```sql
CREATE VIRTUAL TABLE segment_search USING fts5(
    segment_id UNINDEXED,
    project_id UNINDEXED,
    source_text,
    final_text,
    tokenize = 'unicode61'
);
```

Trigger atau application service memperbarui search index setelah:

- segment dibuat;
- final text berubah;
- project dihapus.

FTS table bukan sumber kebenaran.

Jika FTS5 tidak tersedia, fallback menggunakan indexed `LIKE` untuk dokumen kecil.

---

# 45. Integrity Rules

Application integrity checker harus memastikan:

1. Semua project document memiliki original file.
2. Semua page memiliki document.
3. Semua block memiliki page.
4. Semua segment memiliki block.
5. Semua translation batch segment tersedia.
6. Semua placeholder memiliki protected item.
7. Semua glossary snapshot file tersedia.
8. Semua export file tersedia.
9. Semua referenced local file berada di dalam data directory.
10. Tidak ada duplicate page number dalam satu document.
11. Tidak ada duplicate reading order dalam satu page.
12. Revision number berurutan.
13. Approved segment memiliki final text.
14. Locked segment tidak berubah tanpa revision.
15. File checksum sesuai jika integrity scan dijalankan.

---

# 46. Application-Level Constraints

Beberapa constraint terlalu kompleks untuk SQLite dan harus diperiksa application layer:

- geometry berada dalam batas page;
- table cell tidak overlap secara tidak sah;
- source-target page mapping valid;
- glossary scope reference sesuai scope;
- polymorphic relationship entity tersedia;
- first-use glossary policy;
- approved translation tidak ditimpa;
- file path tetap di dalam data directory;
- page order lintas section;
- job state transition.

---

# 47. Job State Transitions

Valid:

```text
CREATED → QUEUED
QUEUED → RUNNING
RUNNING → COMPLETED
RUNNING → COMPLETED_WITH_WARNINGS
RUNNING → RETRYING
RUNNING → FAILED
RUNNING → CANCELLATION_REQUESTED
CANCELLATION_REQUESTED → CANCELLED
RETRYING → QUEUED
```

Tidak valid:

```text
COMPLETED → RUNNING
CANCELLED → COMPLETED
FAILED → COMPLETED
```

Retry membuat attempt baru dan dapat mengubah job ke `QUEUED`.

---

# 48. Segment Final Text Resolution

`final_text` mengikuti:

```text
reviewed_translation
    jika tersedia dan current review state valid

machine_translation
    jika reviewed translation tidak tersedia

source_text
    jika segment NOT_TRANSLATABLE atau IGNORED
```

`final_text` dapat disimpan untuk performa, tetapi harus diperbarui secara transaction-safe ketika source resolution berubah.

---

# 49. Sensitive Data Policy

Database lokal dapat berisi dokumen sensitif.

Karena itu:

- database tidak dikirim ke telemetry;
- log tidak menyimpan segment text secara default;
- backup diberi peringatan bahwa isinya dapat sensitif;
- absolute path pengguna tidak disimpan;
- database tidak dibuka melalui network;
- debug dump harus opt-in.

Encryption-at-rest untuk Personal MVP bergantung pada keamanan disk dan sistem operasi.

Database-level encryption dapat dipertimbangkan kemudian.

---

# 50. Database Backup

Gunakan SQLite online backup API atau command yang setara.

Jangan hanya:

```text
copy transloka.db
```

saat aplikasi dan worker aktif.

Recommended flow:

1. pause new heavy jobs;
2. wait active write transaction selesai;
3. run SQLite backup;
4. copy referenced metadata files;
5. calculate checksum;
6. verify backup database;
7. resume jobs.

---

# 51. Database Restore

Restore flow:

1. stop API write operations;
2. stop Huey consumer;
3. create pre-restore backup;
4. validate backup manifest;
5. restore database to temporary path;
6. run `PRAGMA integrity_check`;
7. validate schema version;
8. replace active database;
9. restore referenced files;
10. run Alembic migration if required;
11. restart application;
12. run application integrity check.

---

# 52. Vacuum and Cleanup

`VACUUM` tidak dijalankan setiap startup.

Dijalankan hanya:

- melalui maintenance action;
- setelah penghapusan besar;
- ketika disk space cukup;
- saat tidak ada active job.

WAL checkpoint dapat dijalankan saat aplikasi idle.

---

# 53. Migration Strategy

Migration ID menggunakan format:

```text
0001_initial_application
0002_projects_and_files
0003_document_ir_core
0004_glossary
0005_translation
0006_jobs
0007_quality
0008_reconstruction
0009_exports
0010_benchmark_and_backup
```

Setiap migration harus:

- memiliki revision ID;
- memiliki parent revision;
- memiliki upgrade;
- memiliki downgrade jika aman;
- diuji pada database kosong;
- diuji pada fixture database;
- dicatat dalam changelog.

---

# 54. Initial Migration Order

## Migration 0001

- `app_metadata`
- `app_settings`

## Migration 0002

- `projects`
- `stored_files`
- `documents`

Circular foreign key seperti `projects.active_document_id` dapat ditambahkan melalui migration terpisah atau dikelola tanpa database foreign key pada tahap awal.

## Migration 0003

- `document_sections`
- `document_pages`
- `document_blocks`
- `document_segments`
- `segment_fragments`
- `document_assets`
- `document_tables`
- `document_table_cells`
- `document_annotations`
- `document_relationships`
- `document_footnotes`
- `document_ir_snapshots`

## Migration 0004

- `glossaries`
- `glossary_terms`
- `glossary_context_rules`
- `glossary_revisions`
- `glossary_snapshots`
- `term_candidates`
- `term_occurrences`
- `glossary_conflicts`
- `protected_items`

## Migration 0005

- `translation_batches`
- `translation_batch_segments`
- `translation_attempts`
- `segment_translations`
- `translation_validations`
- `segment_revisions`
- `review_comments`

## Migration 0006

- `application_jobs`
- `job_attempts`
- `job_dependencies`

## Migration 0007

- `quality_reports`
- `quality_checks`
- `warnings`
- `operation_events`

## Migration 0008

- `reconstruction_jobs`
- `reconstruction_pages`
- `reconstruction_blocks`
- `target_page_mappings`

## Migration 0009

- `exports`

## Migration 0010

- `hardware_profiles`
- `local_models`
- `benchmark_runs`
- `benchmark_results`
- `backups`
- `maintenance_runs`

---

# 55. Migration Safety

Migration tidak boleh:

- menghapus source text;
- menghapus revision history;
- mengubah checksum original;
- mengubah entity ID;
- mengganti enum value tanpa data migration;
- membuat column required tanpa default atau migration logic;
- menghapus table aktif tanpa backup.

Untuk perubahan berisiko:

1. buat table baru;
2. copy data;
3. validate;
4. rename;
5. pertahankan rollback path.

---

# 56. ORM Module Structure

```text
python/transloka-core/
└── transloka_core/
    └── database/
        ├── base.py
        ├── session.py
        ├── pragmas.py
        ├── types.py
        ├── models/
        │   ├── application.py
        │   ├── projects.py
        │   ├── documents.py
        │   ├── glossary.py
        │   ├── translation.py
        │   ├── jobs.py
        │   ├── quality.py
        │   ├── reconstruction.py
        │   ├── exports.py
        │   └── benchmarks.py
        └── repositories/
```

Model tidak boleh menyimpan business logic kompleks.

Business rules berada pada service layer.

---

# 57. Repository Interfaces

Minimum repository:

```text
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
BenchmarkRepository
BackupRepository
```

Repository harus mendukung transaction injection agar beberapa operasi dapat dijalankan secara atomik.

---

# 58. Query Pagination

Endpoint list menggunakan cursor atau offset pagination.

Personal MVP dapat menggunakan offset pagination untuk:

- project;
- glossary term;
- warning;
- revision.

Segment pada dokumen besar sebaiknya menggunakan:

```text
page_id
global_order
limit
```

Contoh:

```sql
SELECT *
FROM document_segments
WHERE section_id = :section_id
  AND global_order > :cursor
ORDER BY global_order
LIMIT :limit;
```

---

# 59. Common Query Indexes

Index minimum:

```text
projects(status, updated_at)
documents(project_id, status)
document_pages(document_id, source_page_number)
document_blocks(page_id, page_reading_order)
document_segments(block_id, segment_order)
document_segments(section_id, global_order)
document_segments(status)
document_segments(review_status)
glossary_terms(normalized_source_term)
glossary_terms(glossary_id, status, priority)
term_occurrences(segment_id)
application_jobs(project_id, status)
warnings(project_id, status, severity)
segment_revisions(segment_id, revision_number)
translation_batches(project_id, status)
exports(project_id, export_type, version_number)
```

Jangan membuat index pada setiap column tanpa bukti kebutuhan.

---

# 60. Development Seed Data

Development dapat membuat:

- satu sample project;
- satu sample digital PDF metadata;
- glossary sample;
- fake translation;
- warnings sample.

Seed data tidak dijalankan pada normal local installation.

Command:

```bash
uv run transloka db seed-development
```

---

# 61. Database CLI

Required commands:

```bash
uv run transloka db migrate
uv run transloka db current
uv run transloka db history
uv run transloka db integrity-check
uv run transloka db backup
uv run transloka db restore
uv run transloka db vacuum
uv run transloka db orphan-scan
```

Destructive command membutuhkan explicit confirmation.

---

# 62. Testing Requirements

## 62.1 Migration Tests

- migrate empty database to latest;
- downgrade satu revision jika supported;
- upgrade fixture database;
- preserve source text;
- preserve revision history;
- verify indexes;
- verify foreign keys.

## 62.2 Constraint Tests

- duplicate page number ditolak;
- duplicate reading order ditolak;
- invalid confidence ditolak;
- missing parent ditolak;
- invalid boolean ditolak;
- `TRANSLATE_AS` tanpa target term ditolak;
- duplicate idempotency key ditolak.

## 62.3 Transaction Tests

- segment edit dan revision dibuat atomik;
- translation result dan validation dibuat atomik;
- job retry tidak menggandakan result;
- export metadata tidak dibuat jika file gagal.

## 62.4 Concurrency Tests

- reader saat worker menulis;
- busy timeout;
- optimistic locking;
- cancellation update;
- WAL recovery setelah process termination.

## 62.5 Backup Tests

- database backup dapat dibuka;
- checksum valid;
- restore menghasilkan project sama;
- interrupted backup tidak dianggap valid.

---

# 63. Database Acceptance Criteria

Database schema siap digunakan apabila:

1. SQLite berjalan dalam WAL mode.
2. Foreign key aktif.
3. Application dan queue menggunakan database berbeda.
4. Project dapat dibuat.
5. Original file dapat direferensikan.
6. Document dapat dibuat.
7. Page, block, dan segment dapat disimpan.
8. Source dan translation terpisah.
9. Segment revision dapat dicatat.
10. Glossary dapat disimpan.
11. Glossary snapshot immutable.
12. Protected item dapat disimpan.
13. Translation batch dan attempt dapat dicatat.
14. Validation dapat disimpan.
15. Job status dapat dilacak.
16. Retry tidak membuat hasil duplikat.
17. Warning dapat difilter.
18. Reconstruction dapat dicatat.
19. Export dapat memiliki version.
20. Benchmark dapat disimpan.
21. Backup dapat dicatat.
22. Semua binary tetap berada di filesystem.
23. File path disimpan relatif.
24. Database dapat dimigrasi.
25. Database dapat di-backup.
26. Database dapat di-restore.
27. Integrity check tersedia.
28. Optimistic locking tersedia.
29. Index utama tersedia.
30. Automated database tests lulus.

---

# 64. Recommended Implementation Order

1. Database configuration.
2. SQLite pragmas.
3. SQLAlchemy base.
4. Alembic setup.
5. Application metadata.
6. Project model.
7. Stored file model.
8. Document model.
9. Page model.
10. Block model.
11. Segment model.
12. Asset model.
13. Glossary models.
14. Translation models.
15. Job models.
16. Warning and quality models.
17. Reconstruction models.
18. Export models.
19. Benchmark models.
20. Backup models.
21. Repository interfaces.
22. Integrity checker.
23. Backup command.
24. Restore command.
25. FTS search.
26. Performance benchmark.

---

# 65. Open Decisions

1. Apakah seluruh table menggunakan `STRICT`.
2. Apakah FTS5 tersedia pada seluruh target installation.
3. Apakah line, span, dan token perlu table tersendiri.
4. Apakah geometry disimpan dalam normalized form juga.
5. Apakah project deletion menggunakan tombstone permanen.
6. Berapa lama translation attempt disimpan.
7. Berapa maksimum segment revision.
8. Apakah raw model response disimpan sebagai file.
9. Apakah old IR snapshot dibersihkan otomatis.
10. Apakah database perlu encryption.
11. Apakah absolute data directory disimpan dalam app settings.
12. Apakah multi-document project masuk Personal MVP.
13. Apakah benchmark case result disimpan per test case.
14. Apakah operation event memiliki retention limit.
15. Apakah warning yang sudah resolved dapat dibersihkan.
16. Apakah full-text search mengindeks machine translation atau final text saja.
17. Apakah backup mencakup `tasks.db`.
18. Apakah Huey pending task dipulihkan setelah restore.
19. Apakah reconstructed page cache direferensikan dalam table khusus.
20. Apakah page render cache memiliki automatic least-recently-used cleanup.

---

# 66. Definition of Done

Implementasi database dinyatakan selesai apabila:

- seluruh migration awal tersedia;
- SQLite configuration diterapkan;
- schema dapat dibuat dari database kosong;
- model SQLAlchemy sesuai migration;
- project dan Document IR dapat disimpan;
- glossary dapat disimpan;
- translation history tidak menimpa hasil lama;
- revision bersifat append-only;
- job idempotency dapat diterapkan;
- warning dan quality report tersedia;
- reconstruction dan export dapat dicatat;
- binary tidak disimpan dalam database;
- backup dan restore tersedia;
- integrity check tersedia;
- test migration, constraint, transaction, dan backup lulus.
