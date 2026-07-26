# API CONTRACT

## TransLoka Local FastAPI Interface Specification

**Document Name:** `API_CONTRACT.md`  
**Document Version:** 0.1  
**Status:** Draft  
**Decision Date:** 2026-07-26  
**API Framework:** FastAPI  
**API Version:** `v1`  
**Application Mode:** Local-First, Single User  
**Authentication:** Tidak digunakan pada Personal MVP  
**Base URL:** `http://127.0.0.1:8000/api/v1`

**Related Documents:**

- `PRD.md`
- `ARCHITECTURE.md`
- `TECH_STACK_DECISIONS.md`
- `DOCUMENT_IR.md`
- `TRANSLATION_PIPELINE.md`
- `GLOSSARY_ENGINE.md`
- `LOCAL_MODEL_BENCHMARK.md`
- `RECONSTRUCTION_ENGINE.md`
- `DATABASE_SCHEMA.md`

---

# 1. Purpose

Dokumen ini menetapkan kontrak HTTP API antara:

```text
Next.js frontend
        ↕
FastAPI backend
        ↕
Application services
        ↕
SQLite, Huey worker, local filesystem, Ollama, dan PaddleOCR
```

Kontrak ini mencakup:

- URL dan versioning;
- request header;
- response envelope;
- error format;
- project management;
- import PDF lokal;
- document analysis;
- Document IR;
- halaman dan segment;
- glossary;
- terminology candidate;
- translation;
- review;
- reconstruction;
- export;
- local model;
- benchmark;
- backup;
- maintenance;
- job status;
- cancellation;
- pagination;
- optimistic locking;
- OpenAPI generation.

Codex harus mengikuti kontrak ini dan tidak membuat endpoint alternatif tanpa perubahan dokumen atau Architecture Decision Record.

---

# 2. API Design Principles

## 2.1 Local-Only

API hanya boleh bind secara default ke:

```text
127.0.0.1
```

Dilarang bind ke:

```text
0.0.0.0
```

tanpa konfigurasi eksplisit.

## 2.2 Versioned

Semua endpoint produk berada di bawah:

```text
/api/v1
```

Endpoint health teknis dapat berada di:

```text
/health
```

## 2.3 JSON by Default

Request dan response menggunakan:

```text
application/json
```

Pengecualian:

- import PDF: `multipart/form-data`;
- download file: binary stream;
- preview image: image response;
- OpenAPI schema: JSON;
- HTML documentation: Swagger atau ReDoc development-only.

## 2.4 Explicit Jobs

Proses panjang tidak menahan HTTP connection sampai selesai.

Proses berikut harus membuat background job:

- document analysis;
- OCR;
- term detection;
- translation;
- reconstruction;
- export;
- full benchmark;
- backup;
- restore;
- maintenance berat.

## 2.5 Stable Resource IDs

Frontend menggunakan resource ID, bukan database row number atau path file.

## 2.6 No Silent Mutation

Endpoint baca tidak boleh:

- memulai OCR;
- memulai translation;
- mengubah glossary;
- membuat export;
- menghapus cache penting.

## 2.7 Idempotent Operations

Operasi yang dapat dikirim ulang harus mendukung:

```text
Idempotency-Key
```

## 2.8 Optimistic Concurrency

Edit segment dan glossary menggunakan revision number.

Update dengan revision lama menghasilkan:

```text
409 CONFLICT
```

## 2.9 Filesystem Is Hidden

API tidak mengembalikan absolute filesystem path.

Frontend hanya menerima:

- resource ID;
- file role;
- filename aman;
- ukuran;
- download endpoint.

---

# 3. API Base URLs

## 3.1 Application API

```text
http://127.0.0.1:8000/api/v1
```

## 3.2 Health Check

```text
http://127.0.0.1:8000/health
```

## 3.3 OpenAPI

Development:

```text
http://127.0.0.1:8000/openapi.json
```

## 3.4 Swagger

Development-only:

```text
http://127.0.0.1:8000/docs
```

## 3.5 ReDoc

Development-only:

```text
http://127.0.0.1:8000/redoc
```

Swagger dan ReDoc dapat dinonaktifkan pada packaged release.

---

# 4. Required Request Headers

Semua request frontend ke `/api/v1` harus menyertakan:

```http
X-TransLoka-Client: web
X-TransLoka-Client-Version: 0.1.0
```

Request mutation harus menggunakan custom header tersebut agar browser menjalankan CORS preflight.

Optional:

```http
X-Request-ID: client-generated-id
Idempotency-Key: unique-operation-key
```

Backend menghasilkan request ID jika tidak diberikan.

---

# 5. Origin and CORS Policy

Allowed origin default:

```text
http://127.0.0.1:3000
http://localhost:3000
```

Backend harus:

- memvalidasi `Origin`;
- menolak origin lain;
- tidak menggunakan wildcard;
- tidak mengizinkan arbitrary local network origin;
- membatasi HTTP method;
- membatasi request header.

Allowed methods:

```text
GET
POST
PATCH
DELETE
OPTIONS
```

`PUT` tidak digunakan pada API awal kecuali kemudian diperlukan.

---

# 6. Request and Response Naming

Gunakan:

```text
snake_case
```

Contoh:

```json
{
  "source_language": "en",
  "target_language": "id",
  "translation_style": "PROFESSIONAL"
}
```

Jangan gunakan campuran:

```text
sourceLanguage
source_language
```

---

# 7. Date and Time

Gunakan ISO 8601 UTC:

```text
2026-07-26T08:30:00.123Z
```

Frontend bertanggung jawab mengubahnya ke waktu lokal.

---

# 8. Enum Convention

Nilai enum menggunakan uppercase:

```text
CREATED
TRANSLATING
COMPLETED_WITH_WARNINGS
```

Frontend tidak boleh bergantung pada urutan enum.

---

# 9. Success Response Envelope

Response JSON normal menggunakan:

```json
{
  "data": {},
  "meta": {
    "request_id": "req_123"
  }
}
```

Untuk collection:

```json
{
  "data": [],
  "meta": {
    "request_id": "req_123",
    "pagination": {
      "next_cursor": null,
      "has_more": false,
      "limit": 50
    }
  }
}
```

`meta` dapat berisi:

- request ID;
- pagination;
- warning;
- processing hint;
- generated timestamp.

---

# 10. Empty Success Response

Untuk operation yang berhasil tanpa resource body:

```http
204 No Content
```

Contoh:

- menghapus temporary file;
- resolve warning tanpa kebutuhan response lengkap.

Jika frontend membutuhkan resource terbaru, endpoint dapat mengembalikan:

```http
200 OK
```

dengan resource.

---

# 11. Error Response

Format error:

```json
{
  "error": {
    "code": "PROJECT_NOT_FOUND",
    "message": "The requested project was not found.",
    "details": {},
    "request_id": "req_123"
  }
}
```

Field:

| Field | Required | Description |
|---|---|---|
| `code` | Ya | Machine-readable error |
| `message` | Ya | Pesan singkat |
| `details` | Ya | Detail terstruktur atau object kosong |
| `request_id` | Ya | ID troubleshooting |

Pesan tidak boleh mengandung:

- stack trace;
- absolute path;
- secret;
- document text;
- prompt;
- API internal detail yang tidak perlu.

---

# 12. HTTP Status Codes

| Status | Penggunaan |
|---|---|
| `200` | Request berhasil |
| `201` | Resource dibuat |
| `202` | Background job diterima |
| `204` | Berhasil tanpa body |
| `400` | Request secara semantik tidak valid |
| `404` | Resource tidak ditemukan |
| `409` | Conflict atau revision mismatch |
| `413` | File terlalu besar |
| `415` | Media type tidak didukung |
| `422` | Pydantic validation error |
| `423` | Resource terkunci |
| `429` | Local concurrency atau rate limit |
| `500` | Internal error |
| `503` | Dependency lokal tidak tersedia |
| `507` | Disk space tidak cukup |

---

# 13. Validation Error

Pydantic validation error dinormalisasi menjadi:

```json
{
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "The request contains invalid values.",
    "details": {
      "fields": [
        {
          "path": "body.translation_style",
          "message": "Invalid translation style.",
          "type": "enum"
        }
      ]
    },
    "request_id": "req_123"
  }
}
```

Frontend tidak boleh bergantung pada raw FastAPI validation response.

---

# 14. Pagination

## 14.1 Cursor Pagination

Digunakan untuk:

- segments;
- revisions;
- warnings;
- events;
- jobs;
- terminology occurrences.

Query:

```text
?limit=50&cursor=<opaque-cursor>
```

Response:

```json
{
  "data": [],
  "meta": {
    "pagination": {
      "limit": 50,
      "next_cursor": "opaque-value",
      "has_more": true
    },
    "request_id": "req_123"
  }
}
```

## 14.2 Offset Pagination

Dapat digunakan untuk small collections:

- projects;
- glossaries;
- exports;
- backups.

Query:

```text
?limit=20&offset=0
```

Maksimum limit default:

```text
100
```

---

# 15. Sorting

Format:

```text
?sort=updated_at&order=desc
```

Backend hanya menerima allowlisted sort fields.

Arbitrary SQL field tidak diperbolehkan.

---

# 16. Filtering

Filter menggunakan query parameter eksplisit.

Contoh:

```text
?status=NEEDS_REVIEW
?severity=CRITICAL
?page_id=pag_123
?section_id=sec_123
```

Jangan menerima arbitrary filter expression dari client pada Personal MVP.

---

# 17. Idempotency

Endpoint berikut membutuhkan atau sangat direkomendasikan menggunakan:

```text
Idempotency-Key
```

- import document;
- start analysis;
- start OCR;
- start translation;
- start reconstruction;
- create export;
- create backup;
- restore backup;
- retry job.

Response untuk key yang sama harus:

- mengembalikan job atau resource yang sama;
- tidak membuat operation duplikat;
- tidak membuat translation revision duplikat.

Idempotency key disimpan sesuai operation scope.

---

# 18. Optimistic Locking

Request edit menggunakan:

```json
{
  "expected_revision": 4
}
```

Jika current revision berbeda:

```http
409 Conflict
```

Response:

```json
{
  "error": {
    "code": "REVISION_CONFLICT",
    "message": "The resource was changed after it was loaded.",
    "details": {
      "expected_revision": 4,
      "current_revision": 5
    },
    "request_id": "req_123"
  }
}
```

---

# 19. Job Resource

Semua proses panjang mengembalikan job.

```json
{
  "id": "job_123",
  "job_type": "TRANSLATE_DOCUMENT",
  "status": "QUEUED",
  "progress": 0.0,
  "current_stage": "QUEUED",
  "project_id": "prj_123",
  "document_id": "doc_123",
  "retry_count": 0,
  "max_retries": 3,
  "created_at": "2026-07-26T08:00:00Z",
  "started_at": null,
  "completed_at": null,
  "error": null
}
```

---

# 20. Job Polling

Frontend melakukan polling:

```text
GET /api/v1/jobs/{job_id}
```

Recommended interval:

```text
2 detik ketika RUNNING
5 detik ketika QUEUED
```

Backend dapat mengirim:

```http
Retry-After: 2
```

Polling berhenti ketika status:

```text
COMPLETED
COMPLETED_WITH_WARNINGS
PARTIALLY_COMPLETED
FAILED
CANCELLED
```

Server-Sent Events ditunda.

---

# 21. Job Status Endpoints

## Get Job

```http
GET /api/v1/jobs/{job_id}
```

## List Jobs

```http
GET /api/v1/jobs
```

Query:

```text
project_id
document_id
job_type
status
limit
cursor
```

## Cancel Job

```http
POST /api/v1/jobs/{job_id}/cancel
```

Body:

```json
{
  "reason": "Cancelled by user."
}
```

## Retry Job

```http
POST /api/v1/jobs/{job_id}/retry
Idempotency-Key: retry-job-123
```

Body:

```json
{
  "retry_failed_items_only": true
}
```

## Get Job Attempts

```http
GET /api/v1/jobs/{job_id}/attempts
```

---

# 22. Health Endpoints

## 22.1 Basic Health

```http
GET /health
```

Response:

```json
{
  "status": "ok",
  "service": "transloka-api",
  "version": "0.1.0"
}
```

Tidak menggunakan standard API envelope agar sederhana untuk process manager.

## 22.2 Detailed System Health

```http
GET /api/v1/system/health
```

Response:

```json
{
  "data": {
    "status": "DEGRADED",
    "components": {
      "database": {
        "status": "AVAILABLE"
      },
      "filesystem": {
        "status": "AVAILABLE"
      },
      "worker": {
        "status": "AVAILABLE"
      },
      "ollama": {
        "status": "UNAVAILABLE"
      },
      "ocr": {
        "status": "AVAILABLE"
      }
    }
  },
  "meta": {
    "request_id": "req_123"
  }
}
```

Overall status:

```text
HEALTHY
DEGRADED
UNHEALTHY
```

---

# 23. System Information

```http
GET /api/v1/system/info
```

Response tidak boleh mengembalikan secret.

```json
{
  "data": {
    "application_version": "0.1.0",
    "database_schema_version": "0010",
    "python_version": "3.12",
    "node_version": "24",
    "operating_system": "Windows",
    "data_directory_configured": true,
    "free_disk_bytes": 100000000000,
    "local_only": true
  },
  "meta": {
    "request_id": "req_123"
  }
}
```

Absolute data directory hanya boleh ditampilkan pada settings lokal jika diperlukan, bukan pada log atau generic error.

---

# 24. Settings Endpoints

## List Settings

```http
GET /api/v1/settings
```

Optional:

```text
?category=TRANSLATION
```

## Get Setting

```http
GET /api/v1/settings/{key}
```

## Update Setting

```http
PATCH /api/v1/settings/{key}
```

Body:

```json
{
  "value": 5
}
```

Settings update harus melalui allowlist.

Tidak boleh membuat arbitrary setting key dari frontend.

## Validate Settings

```http
POST /api/v1/settings/validate
```

Body:

```json
{
  "settings": {
    "translation_batch_size": 5,
    "ocr_concurrency": 1
  }
}
```

---

# 25. Project Resource

```json
{
  "id": "prj_123",
  "name": "System Design Book",
  "description": null,
  "status": "WAITING_FOR_SETTINGS",
  "source_language": "en",
  "target_language": "id",
  "document_type": "TECHNICAL_BOOK",
  "translation_style": "PROFESSIONAL",
  "reconstruction_mode": "HYBRID",
  "progress": 0.12,
  "active_document_id": "doc_123",
  "settings": {},
  "created_at": "2026-07-26T08:00:00Z",
  "updated_at": "2026-07-26T08:05:00Z"
}
```

---

# 26. Project Endpoints

## Create Project

```http
POST /api/v1/projects
```

Body:

```json
{
  "name": "System Design Book",
  "description": null,
  "source_language": "en",
  "target_language": "id",
  "document_type": "TECHNICAL_BOOK",
  "translation_style": "PROFESSIONAL",
  "reconstruction_mode": "HYBRID"
}
```

Response:

```http
201 Created
```

## List Projects

```http
GET /api/v1/projects
```

Query:

```text
status
search
sort
order
limit
offset
```

## Get Project

```http
GET /api/v1/projects/{project_id}
```

## Update Project

```http
PATCH /api/v1/projects/{project_id}
```

Body:

```json
{
  "name": "Updated Name",
  "translation_style": "ACADEMIC",
  "reconstruction_mode": "HYBRID"
}
```

Field yang tidak dikirim tidak berubah.

## Archive Project

```http
POST /api/v1/projects/{project_id}/archive
```

## Restore Archived Project

```http
POST /api/v1/projects/{project_id}/unarchive
```

## Delete Project

```http
DELETE /api/v1/projects/{project_id}
```

Body:

```json
{
  "confirmation": "DELETE",
  "delete_original_file": true,
  "delete_exports": true
}
```

Response:

```http
202 Accepted
```

Mengembalikan deletion job.

---

# 27. Project Summary

```http
GET /api/v1/projects/{project_id}/summary
```

Response:

```json
{
  "data": {
    "project_id": "prj_123",
    "document": {
      "page_count": 240,
      "digital_pages": 220,
      "scanned_pages": 20
    },
    "translation": {
      "total_segments": 5400,
      "translated_segments": 3200,
      "approved_segments": 1200,
      "review_required_segments": 140
    },
    "warnings": {
      "critical": 0,
      "high": 5,
      "medium": 28,
      "low": 92
    },
    "storage": {
      "total_bytes": 1234567890
    }
  },
  "meta": {
    "request_id": "req_123"
  }
}
```

---

# 28. Local Document Import

Browser tidak mengirim filesystem path.

Gunakan multipart upload.

```http
POST /api/v1/projects/{project_id}/documents/import
Content-Type: multipart/form-data
Idempotency-Key: import-project-123
```

Fields:

```text
file: PDF binary
set_as_active: true
```

Optional JSON field:

```text
import_options
```

Example:

```json
{
  "detect_language": false,
  "calculate_checksum": true
}
```

Response:

```http
202 Accepted
```

```json
{
  "data": {
    "document": {
      "id": "doc_123",
      "project_id": "prj_123",
      "status": "CREATED",
      "original_filename": "system-design.pdf"
    },
    "job": {
      "id": "job_123",
      "job_type": "IMPORT_DOCUMENT",
      "status": "QUEUED"
    }
  },
  "meta": {
    "request_id": "req_123"
  }
}
```

---

# 29. Import Validation Errors

Possible errors:

```text
INVALID_PDF_MAGIC
UNSUPPORTED_FILE_TYPE
FILE_TOO_LARGE
PDF_CORRUPTED
PDF_PASSWORD_PROTECTED
PDF_PAGE_LIMIT_EXCEEDED
INSUFFICIENT_DISK_SPACE
DUPLICATE_DOCUMENT
```

Duplicate checksum tidak selalu ditolak.

Backend dapat mengembalikan:

```http
409 Conflict
```

dengan opsi membuat project reference baru pada fase berikutnya.

---

# 30. Document Resource

```json
{
  "id": "doc_123",
  "project_id": "prj_123",
  "title": "System Design",
  "author": "Example Author",
  "document_type": "TECHNICAL_BOOK",
  "document_class": "HYBRID_PDF",
  "source_language": "en",
  "target_language": "id",
  "page_count": 240,
  "word_count_estimate": 84500,
  "has_text_layer": true,
  "scanned_page_count": 20,
  "image_count": 312,
  "table_count": 48,
  "status": "STRUCTURED",
  "created_at": "2026-07-26T08:00:00Z",
  "updated_at": "2026-07-26T08:30:00Z"
}
```

---

# 31. Document Endpoints

## List Project Documents

```http
GET /api/v1/projects/{project_id}/documents
```

## Get Document

```http
GET /api/v1/documents/{document_id}
```

## Get Document Analysis

```http
GET /api/v1/documents/{document_id}/analysis
```

## Start Analysis

```http
POST /api/v1/documents/{document_id}/analysis/start
Idempotency-Key: analyze-doc-123
```

Body:

```json
{
  "render_pages": true,
  "extract_text": true,
  "detect_tables": true,
  "detect_scanned_pages": true
}
```

Response:

```http
202 Accepted
```

## Retry Analysis

```http
POST /api/v1/documents/{document_id}/analysis/retry
```

## Delete Document

```http
DELETE /api/v1/documents/{document_id}
```

Tidak boleh menghapus active document tanpa confirmation.

---

# 32. Page Resource

```json
{
  "id": "pag_123",
  "document_id": "doc_123",
  "source_page_number": 10,
  "logical_page_number": "3",
  "width_points": 595.28,
  "height_points": 841.89,
  "rotation_degrees": 0,
  "page_type": "DIGITAL",
  "page_classification": "MIXED_LAYOUT",
  "column_count": 2,
  "reading_direction": "LTR",
  "status": "STRUCTURED",
  "confidence": {
    "native_extraction": 0.98,
    "ocr": null,
    "structure": 0.94
  },
  "preview": {
    "thumbnail_url": "/api/v1/pages/pag_123/thumbnail",
    "render_url": "/api/v1/pages/pag_123/render"
  }
}
```

---

# 33. Page Endpoints

## List Pages

```http
GET /api/v1/documents/{document_id}/pages
```

Query:

```text
start_page
end_page
page_type
status
limit
cursor
```

## Get Page

```http
GET /api/v1/pages/{page_id}
```

## Get Page Thumbnail

```http
GET /api/v1/pages/{page_id}/thumbnail
```

Response:

```text
image/webp
```

## Get Full Page Render

```http
GET /api/v1/pages/{page_id}/render
```

Query:

```text
dpi
```

Backend hanya menerima allowlisted DPI.

## Get Page Editor Model

```http
GET /api/v1/pages/{page_id}/editor-view
```

Response:

```json
{
  "data": {
    "page": {},
    "blocks": [],
    "segments": [],
    "warnings": []
  },
  "meta": {
    "request_id": "req_123"
  }
}
```

## Reprocess Page

```http
POST /api/v1/pages/{page_id}/reprocess
```

Body:

```json
{
  "rerun_extraction": false,
  "rerun_ocr": true,
  "rerun_structure_detection": true,
  "invalidate_translation": false
}
```

---

# 34. OCR Endpoints

## Start OCR for Document

```http
POST /api/v1/documents/{document_id}/ocr/start
Idempotency-Key: ocr-doc-123
```

Body:

```json
{
  "page_ids": null,
  "mode": "AUTO",
  "language": "en",
  "detect_tables": true,
  "detect_formulas": true
}
```

`page_ids: null` berarti halaman yang membutuhkan OCR.

## Start OCR for Selected Pages

```json
{
  "page_ids": [
    "pag_001",
    "pag_002"
  ],
  "mode": "FORCE",
  "language": "en"
}
```

## Get OCR Status

```http
GET /api/v1/documents/{document_id}/ocr/status
```

## Get Page OCR Result

```http
GET /api/v1/pages/{page_id}/ocr
```

## Update Resolved OCR Text

```http
PATCH /api/v1/segments/{segment_id}/source-resolution
```

Body:

```json
{
  "resolved_source_text": "Corrected OCR source text.",
  "resolution_source": "MANUAL",
  "expected_revision": 3
}
```

Perubahan ini harus membuat segment revision atau source correction event.

---

# 35. Section Endpoints

## List Sections

```http
GET /api/v1/documents/{document_id}/sections
```

## Get Section

```http
GET /api/v1/sections/{section_id}
```

## Get Section Context

```http
GET /api/v1/sections/{section_id}/context
```

## Update Section Metadata

```http
PATCH /api/v1/sections/{section_id}
```

Body:

```json
{
  "section_type": "CHAPTER",
  "source_summary": "This chapter discusses authentication.",
  "expected_revision": 1
}
```

Manual section editing dapat ditunda jika revision field belum tersedia pada schema awal.

---

# 36. Block Endpoints

## Get Page Blocks

```http
GET /api/v1/pages/{page_id}/blocks
```

## Get Block

```http
GET /api/v1/blocks/{block_id}
```

## Update Block Classification

```http
PATCH /api/v1/blocks/{block_id}
```

Body:

```json
{
  "block_type": "CAPTION",
  "semantic_role": "CAPTION",
  "expected_revision": 2
}
```

## Update Reading Order

```http
PATCH /api/v1/pages/{page_id}/reading-order
```

Body:

```json
{
  "block_ids": [
    "blk_001",
    "blk_003",
    "blk_002"
  ]
}
```

Backend harus memastikan seluruh block berasal dari page yang sama.

---

# 37. Segment Resource

```json
{
  "id": "seg_123",
  "block_id": "blk_123",
  "section_id": "sec_123",
  "segment_order": 1,
  "global_order": 542,
  "source_text": "The workflow validates the credentials.",
  "resolved_source_text": "The workflow validates the credentials.",
  "machine_translation": "Workflow memvalidasi kredensial.",
  "reviewed_translation": null,
  "final_text": "Workflow memvalidasi kredensial.",
  "source_language": "en",
  "target_language": "id",
  "status": "MACHINE_TRANSLATED",
  "review_status": "NOT_REVIEWED",
  "is_locked": false,
  "current_revision": 1,
  "confidence": {
    "overall": 0.94
  },
  "warning_count": 0
}
```

---

# 38. Segment Listing

```http
GET /api/v1/documents/{document_id}/segments
```

Filters:

```text
page_id
section_id
status
review_status
has_warnings
warning_severity
search
limit
cursor
```

Sorting default:

```text
global_order asc
```

---

# 39. Get Segment

```http
GET /api/v1/segments/{segment_id}
```

Optional:

```text
?include=revisions,warnings,protected_items
```

Backend hanya menerima include value yang dikenal.

---

# 40. Edit Segment Translation

```http
PATCH /api/v1/segments/{segment_id}/translation
```

Body:

```json
{
  "reviewed_translation": "Workflow tersebut memvalidasi kredensial.",
  "expected_revision": 1,
  "reason": "Improved naturalness."
}
```

Response mengembalikan updated segment.

Edit harus:

- membuat revision;
- memperbarui final text;
- mengubah status menjadi `USER_EDITED`;
- mengubah review status menjadi `EDITED`;
- membatalkan reconstruction cache yang terkait.

---

# 41. Approve Segment

```http
POST /api/v1/segments/{segment_id}/approve
```

Body:

```json
{
  "expected_revision": 2,
  "lock_after_approval": false
}
```

Approval harus membuat revision.

---

# 42. Unapprove Segment

```http
POST /api/v1/segments/{segment_id}/unapprove
```

Body:

```json
{
  "expected_revision": 3,
  "reason": "Needs terminology revision."
}
```

---

# 43. Lock Segment

```http
POST /api/v1/segments/{segment_id}/lock
```

Body:

```json
{
  "expected_revision": 3
}
```

---

# 44. Unlock Segment

```http
POST /api/v1/segments/{segment_id}/unlock
```

Body:

```json
{
  "expected_revision": 4,
  "reason": "Glossary update requires review."
}
```

---

# 45. Retranslate Segment

```http
POST /api/v1/segments/{segment_id}/retranslate
Idempotency-Key: retranslate-seg-123-rev-4
```

Body:

```json
{
  "model_id": null,
  "translation_style": null,
  "preserve_reviewed_translation": true,
  "reason": "Retry with updated glossary."
}
```

Locked segment menghasilkan:

```http
423 Locked
```

kecuali dibuka terlebih dahulu.

---

# 46. Bulk Segment Actions

```http
POST /api/v1/segments/bulk-action
```

Body:

```json
{
  "segment_ids": [
    "seg_001",
    "seg_002"
  ],
  "action": "APPROVE",
  "options": {
    "lock_after_approval": false
  }
}
```

Allowed actions Personal MVP:

```text
APPROVE
UNAPPROVE
LOCK
UNLOCK
MARK_REVIEW_REQUIRED
RETRANSLATE
```

Bulk operation yang berat dapat mengembalikan job.

---

# 47. Segment Revisions

## List Revisions

```http
GET /api/v1/segments/{segment_id}/revisions
```

## Get Revision

```http
GET /api/v1/segment-revisions/{revision_id}
```

## Restore Revision

```http
POST /api/v1/segments/{segment_id}/restore-revision
```

Body:

```json
{
  "revision_id": "rev_123",
  "expected_revision": 5
}
```

Restore membuat revision baru.

---

# 48. Search Segments

```http
GET /api/v1/projects/{project_id}/search
```

Query:

```text
q
scope=SOURCE|TRANSLATION|BOTH
section_id
page_id
limit
cursor
```

Minimum query length dapat ditetapkan:

```text
2 karakter
```

---

# 49. Glossary Resource

```json
{
  "id": "gls_123",
  "project_id": "prj_123",
  "name": "Project Glossary",
  "description": null,
  "source_language": "en",
  "target_language": "id",
  "scope": "PROJECT",
  "domain": "SOFTWARE_ENGINEERING",
  "status": "ACTIVE",
  "version": 4,
  "is_default": true,
  "term_count": 82,
  "created_at": "2026-07-26T08:00:00Z",
  "updated_at": "2026-07-26T08:30:00Z"
}
```

---

# 50. Glossary Endpoints

## Create Glossary

```http
POST /api/v1/glossaries
```

Body:

```json
{
  "project_id": "prj_123",
  "name": "Project Glossary",
  "description": null,
  "source_language": "en",
  "target_language": "id",
  "scope": "PROJECT",
  "domain": "SOFTWARE_ENGINEERING",
  "is_default": true
}
```

## List Glossaries

```http
GET /api/v1/glossaries
```

Filters:

```text
project_id
scope
status
search
```

## Get Glossary

```http
GET /api/v1/glossaries/{glossary_id}
```

## Update Glossary

```http
PATCH /api/v1/glossaries/{glossary_id}
```

Body:

```json
{
  "name": "Updated Glossary",
  "description": "Technical terms.",
  "expected_version": 4
}
```

## Deactivate Glossary

```http
POST /api/v1/glossaries/{glossary_id}/deactivate
```

## Activate Glossary

```http
POST /api/v1/glossaries/{glossary_id}/activate
```

## Delete Glossary

```http
DELETE /api/v1/glossaries/{glossary_id}
```

Glossary yang telah digunakan snapshot tidak boleh menghapus snapshot lama.

---

# 51. Glossary Term Resource

```json
{
  "id": "trm_123",
  "glossary_id": "gls_123",
  "source_term": "workflow",
  "rule_type": "KEEP_ORIGINAL",
  "target_term": null,
  "scope": "PROJECT",
  "scope_reference_id": "prj_123",
  "priority": 100,
  "case_sensitive": false,
  "whole_word": true,
  "match_mode": "PHRASE",
  "capitalization_policy": "MATCH_SENTENCE_POSITION",
  "inflection_policy": "USE_BASE_TERM",
  "first_use_policy": "NONE",
  "status": "ACTIVE",
  "term_source": "USER_CREATED",
  "confidence": 1.0,
  "current_revision": 2,
  "occurrence_count": 84
}
```

---

# 52. Glossary Term Endpoints

## Create Term

```http
POST /api/v1/glossaries/{glossary_id}/terms
```

Body:

```json
{
  "source_term": "workflow",
  "rule_type": "KEEP_ORIGINAL",
  "target_term": null,
  "scope": "PROJECT",
  "scope_reference_id": "prj_123",
  "priority": 100,
  "case_sensitive": false,
  "whole_word": true,
  "match_mode": "PHRASE",
  "capitalization_policy": "MATCH_SENTENCE_POSITION",
  "inflection_policy": "USE_BASE_TERM",
  "first_use_policy": "NONE"
}
```

## List Terms

```http
GET /api/v1/glossaries/{glossary_id}/terms
```

Filters:

```text
search
rule_type
status
source
conflicted
limit
offset
```

## Get Term

```http
GET /api/v1/glossary-terms/{term_id}
```

## Update Term

```http
PATCH /api/v1/glossary-terms/{term_id}
```

Body:

```json
{
  "target_term": "alur kerja",
  "rule_type": "TRANSLATE_AS",
  "expected_revision": 2
}
```

## Deactivate Term

```http
POST /api/v1/glossary-terms/{term_id}/deactivate
```

## Delete Term

```http
DELETE /api/v1/glossary-terms/{term_id}
```

Delete dapat berubah menjadi archive jika telah digunakan snapshot.

---

# 53. Term Occurrences

```http
GET /api/v1/glossary-terms/{term_id}/occurrences
```

Filters:

```text
page_id
section_id
translation_status
limit
cursor
```

Response item:

```json
{
  "id": "occ_123",
  "segment_id": "seg_123",
  "page_id": "pag_123",
  "matched_text": "workflow",
  "source_context": "The workflow begins...",
  "final_translation": "Workflow dimulai...",
  "start_offset": 4,
  "end_offset": 12
}
```

---

# 54. Glossary Impact Analysis

```http
POST /api/v1/projects/{project_id}/glossary-impact
```

Body:

```json
{
  "changes": [
    {
      "term_id": "trm_123",
      "proposed_rule_type": "KEEP_ORIGINAL",
      "proposed_target_term": null
    }
  ]
}
```

Response:

```json
{
  "data": {
    "affected_segments": 84,
    "unreviewed_segments": 72,
    "approved_segments": 10,
    "locked_segments": 2,
    "safe_replacement_segments": 60,
    "retranslation_recommended_segments": 24,
    "conflicts": []
  },
  "meta": {
    "request_id": "req_123"
  }
}
```

---

# 55. Apply Glossary Change

```http
POST /api/v1/projects/{project_id}/apply-glossary-change
Idempotency-Key: apply-glossary-change-123
```

Body:

```json
{
  "term_ids": [
    "trm_123"
  ],
  "mode": "UNREVIEWED_SEGMENTS",
  "action": "RETRANSLATE_WHEN_REQUIRED"
}
```

Response:

```http
202 Accepted
```

---

# 56. Glossary Import

```http
POST /api/v1/glossaries/{glossary_id}/import
Content-Type: multipart/form-data
```

Fields:

```text
file
conflict_policy
activate_valid_terms
```

Conflict policy:

```text
SKIP
CREATE_CONFLICT
UPDATE_EXISTING
```

`UPDATE_EXISTING` membutuhkan explicit confirmation.

Response dapat berupa job jika file besar.

---

# 57. Glossary Export

```http
POST /api/v1/glossaries/{glossary_id}/export
```

Body:

```json
{
  "format": "CSV",
  "include_inactive": false,
  "include_history": false
}
```

Response:

```http
202 Accepted
```

Menghasilkan export resource.

---

# 58. Term Candidate Endpoints

## Start Candidate Detection

```http
POST /api/v1/projects/{project_id}/term-candidates/detect
Idempotency-Key: detect-terms-prj-123
```

Body:

```json
{
  "minimum_occurrences": 3,
  "include_named_entities": true,
  "include_domain_terms": true
}
```

## List Candidates

```http
GET /api/v1/projects/{project_id}/term-candidates
```

Filters:

```text
status
minimum_confidence
candidate_type
search
limit
offset
```

## Accept Candidate

```http
POST /api/v1/term-candidates/{candidate_id}/accept
```

Body:

```json
{
  "glossary_id": "gls_123",
  "rule_type": "KEEP_ORIGINAL",
  "target_term": null,
  "scope": "PROJECT"
}
```

## Reject Candidate

```http
POST /api/v1/term-candidates/{candidate_id}/reject
```

Body:

```json
{
  "reason": "Common word, not a protected term."
}
```

---

# 59. Translation Readiness

```http
GET /api/v1/projects/{project_id}/translation-readiness
```

Response:

```json
{
  "data": {
    "ready": false,
    "blocking_issues": [
      {
        "code": "OLLAMA_MODEL_NOT_SELECTED",
        "message": "Select a local translation model."
      }
    ],
    "warnings": [
      {
        "code": "UNREVIEWED_TERM_CANDIDATES",
        "count": 24
      }
    ],
    "segment_count": 5400,
    "estimated_batches": 1080
  },
  "meta": {
    "request_id": "req_123"
  }
}
```

---

# 60. Start Translation

```http
POST /api/v1/projects/{project_id}/translation/start
Idempotency-Key: translate-prj-123-config-hash
```

Body:

```json
{
  "scope": "FULL_DOCUMENT",
  "section_ids": null,
  "page_ids": null,
  "segment_ids": null,
  "model_id": "mdl_123",
  "translation_style": "PROFESSIONAL",
  "batch_size": 5,
  "context_mode": "STANDARD",
  "retranslate_existing": false,
  "skip_locked_segments": true,
  "run_semantic_validation": false
}
```

Scope:

```text
FULL_DOCUMENT
UNTRANSLATED_ONLY
UNREVIEWED_ONLY
SECTION
PAGE
SELECTED_SEGMENTS
```

Response:

```http
202 Accepted
```

---

# 61. Translation Status

```http
GET /api/v1/projects/{project_id}/translation/status
```

Response:

```json
{
  "data": {
    "status": "TRANSLATING",
    "total_segments": 5400,
    "completed_segments": 1200,
    "failed_segments": 4,
    "review_required_segments": 22,
    "progress": 0.222,
    "active_job_id": "job_123",
    "current_batch": 240,
    "total_batches": 1080
  },
  "meta": {
    "request_id": "req_123"
  }
}
```

---

# 62. Cancel Translation

```http
POST /api/v1/projects/{project_id}/translation/cancel
```

Body:

```json
{
  "reason": "User requested cancellation."
}
```

Completed valid results tetap disimpan.

---

# 63. Retry Failed Translation

```http
POST /api/v1/projects/{project_id}/translation/retry-failed
Idempotency-Key: retry-failed-prj-123
```

Body:

```json
{
  "use_smaller_batch": true,
  "use_selected_model": true
}
```

---

# 64. Translation Batch Endpoints

## List Batches

```http
GET /api/v1/projects/{project_id}/translation/batches
```

## Get Batch

```http
GET /api/v1/translation/batches/{batch_id}
```

## Get Attempts

```http
GET /api/v1/translation/batches/{batch_id}/attempts
```

Raw prompt dan full raw response tidak dikirim ke frontend secara default.

Development endpoint khusus dapat ditambahkan di balik debug flag.

---

# 65. Review Queue

```http
GET /api/v1/projects/{project_id}/review-queue
```

Filters:

```text
severity
warning_type
confidence_max
page_id
section_id
review_status
limit
cursor
```

Response item:

```json
{
  "segment": {},
  "warnings": [],
  "source_context": {
    "previous_segment": null,
    "next_segment": null,
    "heading": "Authentication Workflow"
  }
}
```

---

# 66. Comments

## Create Comment

```http
POST /api/v1/comments
```

Body:

```json
{
  "project_id": "prj_123",
  "scope_type": "SEGMENT",
  "scope_id": "seg_123",
  "content": "Check whether this term should remain in English."
}
```

## List Comments

```http
GET /api/v1/comments
```

Filters:

```text
project_id
scope_type
scope_id
status
```

## Resolve Comment

```http
POST /api/v1/comments/{comment_id}/resolve
```

---

# 67. Warning Resource

```json
{
  "id": "wrn_123",
  "project_id": "prj_123",
  "document_id": "doc_123",
  "page_id": "pag_123",
  "segment_id": "seg_123",
  "warning_type": "TERM_INCONSISTENT",
  "severity": "MEDIUM",
  "message": "The protected term is inconsistent.",
  "details": {},
  "status": "OPEN",
  "created_at": "2026-07-26T08:00:00Z",
  "resolved_at": null
}
```

---

# 68. Warning Endpoints

## List Warnings

```http
GET /api/v1/projects/{project_id}/warnings
```

Filters:

```text
status
severity
warning_type
page_id
segment_id
limit
cursor
```

## Get Warning

```http
GET /api/v1/warnings/{warning_id}
```

## Resolve Warning

```http
POST /api/v1/warnings/{warning_id}/resolve
```

Body:

```json
{
  "resolution_type": "USER_FIXED",
  "resolution_note": "Translation manually corrected."
}
```

## Accept Warning

```http
POST /api/v1/warnings/{warning_id}/accept
```

Body:

```json
{
  "resolution_note": "This wording is intentional."
}
```

Critical warning tidak boleh diterima jika policy menetapkan non-overridable.

---

# 69. Quality Report Endpoints

## Generate Translation Quality Report

```http
POST /api/v1/projects/{project_id}/quality/translation
```

## Generate Reconstruction Quality Report

```http
POST /api/v1/projects/{project_id}/quality/reconstruction
```

## List Reports

```http
GET /api/v1/projects/{project_id}/quality/reports
```

## Get Report

```http
GET /api/v1/quality/reports/{report_id}
```

---

# 70. Reconstruction Readiness

```http
GET /api/v1/projects/{project_id}/reconstruction-readiness
```

Response:

```json
{
  "data": {
    "ready": true,
    "blocking_issues": [],
    "warnings": [
      {
        "code": "UNREVIEWED_LOW_CONFIDENCE_SEGMENTS",
        "count": 12
      }
    ],
    "available_modes": [
      "OVERLAY",
      "REFLOW",
      "HYBRID"
    ]
  },
  "meta": {
    "request_id": "req_123"
  }
}
```

---

# 71. Reconstruction Preview

```http
POST /api/v1/projects/{project_id}/reconstruction/preview
```

Body:

```json
{
  "page_id": "pag_123",
  "mode": "HYBRID",
  "settings": {
    "minimum_body_font_pt": 8,
    "maximum_font_reduction_percent": 10,
    "allow_page_addition": true
  }
}
```

Response dapat berupa synchronous result untuk satu page ringan atau `202` job untuk page berat.

Preview file bersifat temporary.

---

# 72. Start Reconstruction

```http
POST /api/v1/projects/{project_id}/reconstruction/start
Idempotency-Key: reconstruct-prj-123-settings-hash
```

Body:

```json
{
  "mode": "HYBRID",
  "page_ids": null,
  "settings": {
    "preserve_page_size": true,
    "preserve_images": true,
    "preserve_headers": true,
    "preserve_footers": true,
    "preserve_page_numbers": true,
    "translate_captions": true,
    "minimum_body_font_pt": 8,
    "maximum_font_reduction_percent": 10,
    "allow_page_addition": true,
    "allow_column_change": false,
    "table_complexity_fallback": "PRESERVE_AS_IMAGE",
    "image_quality": "STANDARD",
    "block_export_on_critical_errors": true
  }
}
```

Response:

```http
202 Accepted
```

---

# 73. Reconstruction Status

```http
GET /api/v1/projects/{project_id}/reconstruction/status
```

Response:

```json
{
  "data": {
    "status": "RENDERING",
    "progress": 0.64,
    "completed_pages": 154,
    "total_source_pages": 240,
    "generated_target_pages": 158,
    "warning_count": 22,
    "critical_warning_count": 0,
    "active_job_id": "job_123"
  },
  "meta": {
    "request_id": "req_123"
  }
}
```

---

# 74. Reconstruction Page Result

```http
GET /api/v1/reconstruction/pages/{reconstruction_page_id}
```

Response memuat:

- strategy;
- target page mapping;
- block status;
- warnings;
- preview endpoint.

---

# 75. Retry Reconstruction Page

```http
POST /api/v1/reconstruction/pages/{reconstruction_page_id}/retry
```

Body:

```json
{
  "fallback_mode": "REFLOW",
  "override_settings": {
    "allow_column_change": true
  }
}
```

---

# 76. Cancel Reconstruction

```http
POST /api/v1/projects/{project_id}/reconstruction/cancel
```

---

# 77. Export Resource

```json
{
  "id": "exp_123",
  "project_id": "prj_123",
  "document_id": "doc_123",
  "export_type": "TRANSLATED_PDF",
  "output_profile": "STANDARD",
  "version_number": 1,
  "status": "COMPLETED",
  "filename": "system-design-id-v1.pdf",
  "page_count": 246,
  "size_bytes": 48392810,
  "checksum_sha256": "example",
  "created_at": "2026-07-26T08:00:00Z",
  "completed_at": "2026-07-26T08:10:00Z"
}
```

---

# 78. Create Export

```http
POST /api/v1/projects/{project_id}/exports
Idempotency-Key: export-prj-123-v1
```

Body:

```json
{
  "export_type": "TRANSLATED_PDF",
  "output_profile": "STANDARD",
  "reconstruction_job_id": "rcj_123",
  "filename": null,
  "validate_before_completion": true
}
```

Response:

```http
202 Accepted
```

---

# 79. List Exports

```http
GET /api/v1/projects/{project_id}/exports
```

Filters:

```text
export_type
status
limit
offset
```

---

# 80. Get Export

```http
GET /api/v1/exports/{export_id}
```

---

# 81. Download Export

```http
GET /api/v1/exports/{export_id}/download
```

Response:

```text
application/pdf
```

Headers:

```http
Content-Disposition: attachment; filename="system-design-id-v1.pdf"
X-Content-Type-Options: nosniff
```

Support:

```text
Range requests
```

bersifat optional untuk Personal MVP.

---

# 82. Delete Export

```http
DELETE /api/v1/exports/{export_id}
```

Original document dan translation tidak ikut dihapus.

---

# 83. Document IR Snapshot Endpoints

## Create Snapshot

Biasanya dipanggil internal, tetapi dapat tersedia:

```http
POST /api/v1/documents/{document_id}/ir-snapshots
```

Body:

```json
{
  "snapshot_type": "REVIEWED"
}
```

## List Snapshots

```http
GET /api/v1/documents/{document_id}/ir-snapshots
```

## Export IR Package

```http
POST /api/v1/documents/{document_id}/ir-export
```

---

# 84. Local Model Health

```http
GET /api/v1/models/ollama/health
```

Response:

```json
{
  "data": {
    "status": "AVAILABLE",
    "base_url": "http://127.0.0.1:11434",
    "version": "unknown"
  },
  "meta": {
    "request_id": "req_123"
  }
}
```

Do not expose remote Ollama credential because Personal MVP does not use one.

---

# 85. List Local Models

```http
GET /api/v1/models
```

Filters:

```text
installed
selected_for_translation
selected_for_validation
```

Response item:

```json
{
  "id": "mdl_123",
  "ollama_model_name": "example-model",
  "model_family": null,
  "parameter_class": "7B",
  "quantization": "Q4",
  "disk_size_bytes": 5000000000,
  "license_status": "APPROVED_FOR_PERSONAL_USE",
  "is_installed": true,
  "is_selected_translation": true,
  "is_selected_validation": false
}
```

---

# 86. Refresh Local Models

```http
POST /api/v1/models/refresh
```

Membaca model Ollama yang terpasang.

Tidak mengunduh model.

---

# 87. Select Model

```http
POST /api/v1/models/{model_id}/select
```

Body:

```json
{
  "role": "TRANSLATION"
}
```

Role:

```text
TRANSLATION
VALIDATION
```

Model harus lolos basic health test.

---

# 88. Quick Model Test

```http
POST /api/v1/models/{model_id}/quick-test
```

Body:

```json
{
  "text": "The workflow validates the credentials.",
  "use_project_glossary_id": null
}
```

Response tidak disimpan sebagai benchmark penuh kecuali diminta.

---

# 89. Hardware Profile

```http
GET /api/v1/system/hardware
```

Response:

```json
{
  "data": {
    "operating_system": "Windows",
    "cpu_model": "Example CPU",
    "physical_cores": 8,
    "logical_cores": 16,
    "ram_total_gb": 32,
    "gpu_vendor": "NVIDIA",
    "gpu_model": "Example GPU",
    "gpu_vram_total_gb": 8,
    "disk_free_gb": 420
  },
  "meta": {
    "request_id": "req_123"
  }
}
```

---

# 90. Benchmark Endpoints

## Start Quick Benchmark

```http
POST /api/v1/models/{model_id}/benchmarks/quick
Idempotency-Key: quick-benchmark-model-123
```

Body:

```json
{
  "dataset_version": "translation_benchmark_en_id_0.1",
  "temperature": 0.1,
  "batch_sizes": [
    1,
    5
  ]
}
```

## Start Full Benchmark

```http
POST /api/v1/models/{model_id}/benchmarks/full
Idempotency-Key: full-benchmark-model-123
```

## List Benchmark Runs

```http
GET /api/v1/benchmarks
```

## Get Benchmark

```http
GET /api/v1/benchmarks/{benchmark_id}
```

## Get Benchmark Comparison

```http
POST /api/v1/benchmarks/compare
```

Body:

```json
{
  "benchmark_ids": [
    "bmk_001",
    "bmk_002"
  ]
}
```

## Submit Human Review

```http
POST /api/v1/benchmarks/{benchmark_id}/human-review
```

Body:

```json
{
  "items": [
    {
      "test_case_id": "case_001",
      "meaning_score": 5,
      "naturalness_score": 4,
      "editing_effort_score": 4,
      "notes": null
    }
  ]
}
```

---

# 91. Backup Resource

```json
{
  "id": "bkp_123",
  "backup_type": "DATABASE_ONLY",
  "status": "COMPLETED",
  "filename": "transloka-backup-20260726.zip",
  "size_bytes": 4839201,
  "checksum_sha256": "example",
  "application_version": "0.1.0",
  "database_schema_version": "0010",
  "created_at": "2026-07-26T08:00:00Z",
  "completed_at": "2026-07-26T08:01:00Z"
}
```

---

# 92. Create Backup

```http
POST /api/v1/backups
Idempotency-Key: backup-20260726-0800
```

Body:

```json
{
  "backup_type": "DATABASE_ONLY",
  "include_original_files": false,
  "include_exports": false,
  "include_intermediate_files": false
}
```

Backup type:

```text
DATABASE_ONLY
METADATA
FULL_PROJECTS
FULL_APPLICATION
```

Response:

```http
202 Accepted
```

---

# 93. List Backups

```http
GET /api/v1/backups
```

---

# 94. Download Backup

```http
GET /api/v1/backups/{backup_id}/download
```

---

# 95. Verify Backup

```http
POST /api/v1/backups/{backup_id}/verify
```

Mengembalikan job atau synchronous result untuk backup kecil.

---

# 96. Restore Backup

```http
POST /api/v1/backups/{backup_id}/restore
Idempotency-Key: restore-backup-123
```

Body:

```json
{
  "confirmation": "RESTORE",
  "create_pre_restore_backup": true,
  "restore_files": true
}
```

Response:

```http
202 Accepted
```

Restore dapat menyebabkan API masuk maintenance mode.

Frontend harus menampilkan warning sebelum request.

---

# 97. Delete Backup

```http
DELETE /api/v1/backups/{backup_id}
```

Body:

```json
{
  "confirmation": "DELETE"
}
```

---

# 98. Maintenance Endpoints

## Database Integrity Check

```http
POST /api/v1/maintenance/database-integrity-check
```

## File Integrity Check

```http
POST /api/v1/maintenance/file-integrity-check
```

## Orphan File Scan

```http
POST /api/v1/maintenance/orphan-file-scan
```

## Temporary File Cleanup

```http
POST /api/v1/maintenance/temp-cleanup
```

Body:

```json
{
  "older_than_days": 7,
  "dry_run": true
}
```

## Cache Cleanup

```http
POST /api/v1/maintenance/cache-cleanup
```

## Vacuum Database

```http
POST /api/v1/maintenance/database-vacuum
```

Vacuum hanya dijalankan jika tidak ada active heavy job.

---

# 99. Storage Usage

```http
GET /api/v1/system/storage
```

Response:

```json
{
  "data": {
    "free_disk_bytes": 100000000000,
    "total_managed_bytes": 4000000000,
    "categories": {
      "originals": 1000000000,
      "page_renders": 700000000,
      "ocr": 500000000,
      "intermediate": 900000000,
      "exports": 600000000,
      "backups": 300000000
    }
  },
  "meta": {
    "request_id": "req_123"
  }
}
```

---

# 100. Project Storage Detail

```http
GET /api/v1/projects/{project_id}/storage
```

---

# 101. Project Cleanup

```http
POST /api/v1/projects/{project_id}/cleanup
```

Body:

```json
{
  "delete_page_render_cache": true,
  "delete_ocr_cache": false,
  "delete_old_exports": false,
  "delete_old_ir_snapshots": false,
  "dry_run": true
}
```

Dry-run response menampilkan file dan ukuran yang akan dihapus.

---

# 102. File Download Security

File download endpoint harus:

- resolve file melalui stored file ID;
- memastikan path berada dalam data directory;
- mencegah `..`;
- tidak menerima arbitrary path;
- mengirim `nosniff`;
- menggunakan safe filename;
- tidak mengembalikan source file melalui generic endpoint tanpa project ownership validation, walaupun aplikasi single-user.

---

# 103. Original Document Download

```http
GET /api/v1/documents/{document_id}/original
```

Response:

```text
application/pdf
```

Original download hanya membaca immutable source.

---

# 104. Preview File Caching

Thumbnail dan render response dapat menggunakan:

```http
ETag
Cache-Control: private, max-age=3600
```

ETag berasal dari checksum atau render hash.

Frontend dapat mengirim:

```http
If-None-Match
```

dan menerima:

```http
304 Not Modified
```

---

# 105. API Rate and Concurrency Limits

Personal MVP tidak menggunakan user rate limiting berbasis account.

Namun, backend harus membatasi:

- satu active full-document translation;
- satu active reconstruction;
- satu active full benchmark;
- satu active restore;
- configurable OCR concurrency.

Conflict response:

```http
429 Too Many Requests
```

Error code:

```text
LOCAL_CONCURRENCY_LIMIT_REACHED
```

Detail:

```json
{
  "active_job_id": "job_123",
  "active_job_type": "TRANSLATE_DOCUMENT"
}
```

---

# 106. Dependency Unavailable Errors

## Ollama

```http
503 Service Unavailable
```

```text
OLLAMA_UNAVAILABLE
OLLAMA_MODEL_NOT_INSTALLED
OLLAMA_MODEL_LOAD_FAILED
```

## OCR

```text
OCR_PROVIDER_UNAVAILABLE
OCR_MODEL_NOT_AVAILABLE
```

## Worker

```text
BACKGROUND_WORKER_UNAVAILABLE
```

## Filesystem

```text
DATA_DIRECTORY_UNAVAILABLE
```

---

# 107. Disk Space Errors

Before heavy processing, backend checks free disk space.

Error:

```http
507 Insufficient Storage
```

```json
{
  "error": {
    "code": "INSUFFICIENT_DISK_SPACE",
    "message": "There is not enough free disk space for this operation.",
    "details": {
      "required_bytes_estimate": 8000000000,
      "available_bytes": 3000000000
    },
    "request_id": "req_123"
  }
}
```

---

# 108. Standard Error Codes

## General

```text
VALIDATION_ERROR
RESOURCE_NOT_FOUND
INTERNAL_ERROR
OPERATION_NOT_ALLOWED
LOCAL_CONCURRENCY_LIMIT_REACHED
INSUFFICIENT_DISK_SPACE
DEPENDENCY_UNAVAILABLE
```

## Project

```text
PROJECT_NOT_FOUND
PROJECT_ARCHIVED
PROJECT_DELETION_IN_PROGRESS
PROJECT_STATE_INVALID
```

## Document

```text
DOCUMENT_NOT_FOUND
INVALID_PDF_MAGIC
UNSUPPORTED_FILE_TYPE
FILE_TOO_LARGE
PDF_CORRUPTED
PDF_PASSWORD_PROTECTED
PDF_PAGE_LIMIT_EXCEEDED
DOCUMENT_ANALYSIS_FAILED
```

## OCR

```text
OCR_PROVIDER_UNAVAILABLE
OCR_FAILED
OCR_LOW_CONFIDENCE
OCR_PAGE_NOT_REQUIRED
```

## Glossary

```text
GLOSSARY_NOT_FOUND
GLOSSARY_VERSION_CONFLICT
TERM_NOT_FOUND
DUPLICATE_TERM
TERM_CONFLICT
TARGET_TERM_REQUIRED
INVALID_MATCH_MODE
UNSAFE_REGEX
IMPACT_ANALYSIS_REQUIRED
```

## Translation

```text
TRANSLATION_NOT_READY
TRANSLATION_ALREADY_RUNNING
OLLAMA_UNAVAILABLE
OLLAMA_MODEL_NOT_SELECTED
OLLAMA_MODEL_NOT_INSTALLED
TRANSLATION_FAILED
INVALID_MODEL_RESPONSE
PLACEHOLDER_MISMATCH
SEGMENT_MAPPING_FAILED
TARGET_LANGUAGE_MISMATCH
```

## Segment

```text
SEGMENT_NOT_FOUND
SEGMENT_LOCKED
REVISION_CONFLICT
INVALID_SEGMENT_STATE
```

## Reconstruction

```text
RECONSTRUCTION_NOT_READY
RECONSTRUCTION_ALREADY_RUNNING
RECONSTRUCTION_BLOCKED
TEXT_OVERFLOW_CRITICAL
LAYOUT_COLLISION_CRITICAL
MISSING_REQUIRED_ASSET
```

## Export

```text
EXPORT_NOT_READY
EXPORT_VALIDATION_FAILED
EXPORT_FILE_MISSING
```

## Backup

```text
BACKUP_NOT_FOUND
BACKUP_INVALID
BACKUP_VERIFICATION_FAILED
RESTORE_IN_PROGRESS
RESTORE_FAILED
```

---

# 109. Request Size Limits

Default configurable values:

```text
JSON request maximum: 5 MB
PDF upload maximum: configured
Glossary CSV maximum: configured
Backup upload: not used in initial API
```

Large source text tidak boleh dikirim ulang dari frontend jika sudah ada di database.

---

# 110. OpenAPI Requirements

FastAPI harus menghasilkan OpenAPI schema untuk seluruh endpoint.

Pydantic model harus digunakan untuk:

- request;
- response;
- error detail;
- pagination;
- job;
- resource.

Generated OpenAPI harus memiliki:

- operation ID stabil;
- tags;
- summary;
- description;
- response schema;
- error response;
- examples untuk critical endpoint.

---

# 111. OpenAPI Tags

```text
System
Settings
Projects
Documents
Pages
Sections
Blocks
Segments
Glossaries
Terms
Candidates
Translation
Review
Warnings
Quality
Reconstruction
Exports
Models
Benchmarks
Backups
Maintenance
Jobs
```

---

# 112. TypeScript Client Generation

Flow:

```text
FastAPI OpenAPI
        ↓
openapi.json
        ↓
generated TypeScript client
        ↓
packages/api-client
```

Generated client disimpan pada:

```text
packages/api-client/
```

Generated file tidak boleh diedit manual.

CI harus memeriksa bahwa generated client sesuai dengan current OpenAPI.

---

# 113. API Client Error Handling

Frontend client harus mengubah error response menjadi:

```ts
type ApiError = {
  code: string;
  message: string;
  details: Record<string, unknown>;
  requestId: string;
};
```

Frontend tidak boleh hanya menampilkan:

```text
Something went wrong
```

jika error code memiliki pesan yang dapat ditindaklanjuti.

---

# 114. API Logging

Setiap request mencatat:

```text
request_id
method
path template
status code
duration
project_id jika tersedia
document_id jika tersedia
job_id jika tersedia
```

Jangan mencatat:

- multipart file content;
- source text;
- translation text;
- glossary content secara penuh;
- backup content;
- local absolute path;
- Ollama prompt.

---

# 115. Maintenance Mode

Saat restore atau migration tertentu, API dapat masuk:

```text
MAINTENANCE_MODE
```

Endpoint yang tetap tersedia:

```text
/health
/api/v1/system/health
/api/v1/jobs/{restore_job_id}
```

Mutation lain mengembalikan:

```http
503 Service Unavailable
```

Error:

```text
APPLICATION_IN_MAINTENANCE_MODE
```

---

# 116. Safe Shutdown

Endpoint shutdown tidak tersedia secara default melalui API.

Startup script atau process manager bertanggung jawab menghentikan aplikasi.

Hal ini mencegah halaman web atau request tidak sah mematikan backend.

---

# 117. API State Transition Validation

Backend wajib memvalidasi state.

Contoh:

Translation hanya dapat dimulai jika project berada pada:

```text
WAITING_FOR_GLOSSARY
TERMS_DETECTED
READY_FOR_REVIEW
PARTIALLY_COMPLETED
```

dan readiness check lulus.

Reconstruction hanya dapat dimulai jika:

- translation tersedia;
- placeholder selesai;
- critical warning policy terpenuhi.

Export hanya dapat dibuat jika:

- reconstruction selesai;
- output file tersedia;
- final validation memenuhi policy.

---

# 118. Atomic Mutation Requirements

Operasi berikut harus transaction-safe:

- edit segment + create revision;
- approve segment + create revision;
- glossary update + revision;
- translation result + validation;
- create export metadata setelah file final valid;
- resolve warning;
- create job + queue dispatch record.

Jika queue dispatch gagal setelah job dibuat:

```text
job status = FAILED
error code = QUEUE_DISPATCH_FAILED
```

atau gunakan outbox-like dispatch mechanism.

---

# 119. API Contract Testing

## Unit Contract Tests

- Pydantic request validation;
- response serialization;
- error normalization;
- enum validation;
- ID validation.

## Integration Contract Tests

- project CRUD;
- import PDF;
- job creation;
- segment edit;
- optimistic locking;
- glossary term creation;
- translation start;
- reconstruction start;
- export download;
- backup creation.

## Generated Client Tests

- OpenAPI generation;
- TypeScript client compilation;
- endpoint operation IDs stable;
- no duplicate schema names.

---

# 120. End-to-End API Flow

Minimum E2E flow:

```text
POST /projects
        ↓
POST /projects/{id}/documents/import
        ↓
GET /jobs/{id}
        ↓
POST /documents/{id}/analysis/start
        ↓
GET /documents/{id}/pages
        ↓
POST /projects/{id}/term-candidates/detect
        ↓
POST /term-candidates/{id}/accept
        ↓
POST /projects/{id}/translation/start
        ↓
GET /projects/{id}/translation/status
        ↓
PATCH /segments/{id}/translation
        ↓
POST /segments/{id}/approve
        ↓
POST /projects/{id}/reconstruction/start
        ↓
GET /projects/{id}/reconstruction/status
        ↓
POST /projects/{id}/exports
        ↓
GET /exports/{id}/download
```

---

# 121. API Acceptance Criteria

API Contract siap diimplementasikan apabila:

1. Seluruh endpoint menggunakan `/api/v1`.
2. API hanya bind ke localhost.
3. Origin frontend divalidasi.
4. Custom client header diwajibkan.
5. Success response konsisten.
6. Error response konsisten.
7. Request ID tersedia.
8. Validation error dinormalisasi.
9. Job resource tersedia.
10. Job dapat dipolling.
11. Job dapat dibatalkan.
12. Job dapat di-retry.
13. Project CRUD tersedia.
14. PDF dapat diimpor melalui multipart.
15. File path tidak diekspos.
16. Document analysis dapat dimulai.
17. Page preview dapat diambil.
18. OCR dapat dimulai per halaman.
19. Segment dapat dibaca dan diedit.
20. Optimistic locking tersedia.
21. Segment dapat di-approve dan di-lock.
22. Glossary dapat dikelola.
23. Term candidate dapat diterima atau ditolak.
24. Glossary impact dapat dianalisis.
25. Translation dapat dimulai dan dipantau.
26. Review queue tersedia.
27. Warning dapat diselesaikan.
28. Reconstruction dapat dimulai.
29. Export dapat dibuat dan diunduh.
30. Local model dapat dideteksi.
31. Benchmark dapat dijalankan.
32. Backup dapat dibuat dan diverifikasi.
33. Restore membutuhkan confirmation.
34. Maintenance endpoint tersedia.
35. Disk space error ditangani.
36. OpenAPI dihasilkan.
37. TypeScript client dapat dibuat.
38. Contract test tersedia.
39. Critical state transition divalidasi.
40. Endpoint tidak mengirim data ke cloud.

---

# 122. Recommended Implementation Order

1. API application bootstrap.
2. Request ID middleware.
3. Error normalization.
4. CORS dan origin validation.
5. System health.
6. Settings.
7. Project endpoints.
8. Document import.
9. Job endpoints.
10. Document analysis endpoints.
11. Page dan preview endpoints.
12. Segment endpoints.
13. Optimistic locking.
14. Glossary endpoints.
15. Candidate endpoints.
16. Translation readiness.
17. Translation start dan status.
18. Review queue.
19. Warning endpoints.
20. Reconstruction endpoints.
21. Export endpoints.
22. Model endpoints.
23. Benchmark endpoints.
24. Backup endpoints.
25. Maintenance endpoints.
26. OpenAPI client generation.
27. Contract test.
28. End-to-end API test.

---

# 123. Open Decisions

1. Nilai default maksimum ukuran PDF.
2. Nilai default maksimum halaman.
3. Apakah SSE ditambahkan setelah polling stabil.
4. Apakah page render endpoint mendukung range atau tile.
5. Apakah raw OCR response memiliki debug endpoint.
6. Apakah raw Ollama response disimpan dan dapat dilihat.
7. Apakah block geometry dapat diedit melalui API Personal MVP.
8. Apakah section editor masuk MVP.
9. Apakah bulk glossary update synchronous atau job.
10. Apakah glossary import menggunakan job untuk semua ukuran.
11. Apakah bilingual export masuk Personal MVP.
12. Apakah API mendukung EPUB setelah fase PDF selesai.
13. Apakah FTS search mengembalikan highlight.
14. Apakah API menggunakan ETag untuk segment resource.
15. Apakah backup dapat diimpor dari file eksternal melalui browser.
16. Apakah application restart dapat dipicu dari UI.
17. Apakah model download dapat dipicu dari UI.
18. Apakah hardware temperature dapat ditampilkan.
19. Apakah preview reconstruction disimpan sebagai export sementara.
20. Apakah debug endpoint tersedia pada packaged release.

---

# 124. Definition of Done

Implementasi API dinyatakan selesai apabila:

- seluruh endpoint prioritas tersedia;
- OpenAPI valid;
- frontend client dapat dihasilkan;
- request dan response sesuai schema;
- error format konsisten;
- file import aman;
- job lifecycle dapat dipantau;
- segment edit transaction-safe;
- glossary dan translation terintegrasi;
- reconstruction dan export terintegrasi;
- local model dan benchmark terintegrasi;
- backup dan maintenance tersedia;
- API hanya dapat diakses melalui localhost secara default;
- tidak ada absolute path atau secret dalam response;
- automated contract test lulus;
- end-to-end API flow utama lulus.
