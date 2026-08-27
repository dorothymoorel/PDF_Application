# M11-REM-10 Production OCR Worker Runtime Design

## Goal

Close the OCR portion of release blocker `REL-HIGH-002` by connecting the
canonical OCR API contract to the local SqliteHuey queue and a production OCR
runner. The API process persists an immutable, versioned command and enqueues
only the application job identifier. The worker reconstructs every dependency
from the application database and local storage.

## Scope

The production runtime must support:

- `POST /api/v1/documents/{document_id}/ocr/start` with `AUTO` and `FORCE`
  page selection;
- `GET /api/v1/documents/{document_id}/ocr/status`;
- a stable Huey task name, `transloka.ocr.execute`;
- fail-closed queue configuration in the production app factory;
- a durable `transloka.ocr.command.v1` payload stored in
  `application_jobs.payload_json`;
- worker-side loading of the document, selected pages, immutable original PDF,
  and OCR settings from trusted local state;
- local PaddleOCR composition, raw OCR artifact persistence, job progress,
  attempts, cancellation, partial failure, and safe resource shutdown.

No PDF bytes, OCR text, filesystem paths, provider objects, or SQLAlchemy
sessions cross the queue boundary.

## API Contract

The start request follows `docs/API_CONTRACT.md`:

```json
{
  "page_ids": null,
  "mode": "AUTO",
  "language": "en",
  "detect_tables": true,
  "detect_formulas": true
}
```

`FORCE` requires at least one page identifier. `AUTO` rejects explicit page
identifiers and selects persisted pages classified as `SCANNED` or `HYBRID`.
All selected pages must belong to the path document. The API returns `202` with
the application job identifier and status. Reusing an idempotency key for a
different command returns `409`. Missing queue configuration or enqueue failure
returns `503`; enqueue failure leaves the application job in the canonical
`QUEUE_DISPATCH_FAILED` state.

The status route returns the latest OCR job for the document, including job
status, progress, stage, selected/completed/failed page counts, and active job
identifier. With no prior OCR job it returns a stable `NOT_STARTED` response.

## Durable Command

`OCRCommand` contains only JSON-safe identifiers and bounded settings:

- schema version;
- project and document identifiers;
- mode;
- selected page identifiers (empty for `AUTO`);
- language;
- table/formula detection flags;
- allowed render DPI;
- provider timeout and confidence threshold;
- maximum page attempts.

Decoding rejects duplicate JSON keys, unknown/missing fields, wrong types,
unsupported schemas, invalid identifiers, conflicting selectors, and unsafe or
unbounded values.

## Worker Composition

`DatabaseOCRRequestLoader` validates that:

- the job exists, is `OCR_DOCUMENT`, and is executable;
- the command, job foreign keys, project, document, and pages agree;
- the document original points to a validated immutable `ORIGINAL` PDF record;
- every selected page belongs to the document;
- the source is opened through `LocalFileStorage`, never from command input.

The worker factory creates one application engine/session factory, one local
storage adapter, one OCR loader, one `OCRPageOrchestrator`, and one
`OCRJobRunner`. The default provider is `PaddleOCRProviderAdapter` constrained
to the controlled data-root cache. Tests may inject a provider factory without
installing or contacting PaddleOCR.

The consumer registers both translation and OCR task factories. API producers
register only the task signature they enqueue and must never execute work.
Every engine and Huey storage connection closes exactly once.

## Security and Failure Handling

- OCR receives only internally rendered raster pages.
- Original files and raw OCR artifacts remain under the resolved local data
  root.
- Provider/model absence fails the job explicitly; there is no fake or cloud
  fallback.
- Raw exception internals, source content, OCR text, and absolute paths are not
  exposed by API errors or normal logs.
- Invalid commands or inconsistent database state fail closed.
- Page-level failures preserve successful raw outputs and result in
  `PARTIALLY_COMPLETED` when applicable.

## Verification

Focused tests cover command validation, database loading, AUTO/FORCE selection,
task-name stability, producer isolation, worker registration, resource closure,
queue failure, and API status.

The production E2E test uses a temporary data root and must:

1. migrate the application database;
2. seed a project, document, original PDF, and scanned page;
3. start the production app lifespan with a temporary SqliteHuey database;
4. submit the canonical OCR start request;
5. prove the application job is queued and the named task exists in `tasks.db`;
6. restart/construct the production worker with an injected deterministic local
   OCR provider;
7. execute the real queued task through the worker registry;
8. verify job/attempt completion and immutable raw OCR output;
9. verify production status endpoints and factory isolation.

No automated test downloads OCR models, uses a remote URL, or requires a live
PaddleOCR installation.

## Expected Files

- `services/api/src/transloka_api/app.py`;
- `services/api/src/transloka_api/routers/ocr.py`;
- `services/worker/src/transloka_worker/app.py`;
- `services/worker/src/transloka_worker/ocr.py`;
- `services/worker/src/transloka_worker/queue.py`;
- `services/worker/src/transloka_worker/tasks/ocr.py` and task exports;
- `services/worker/pyproject.toml` and `uv.lock` for the direct documents
  dependency;
- focused API/worker/OCR integration tests and one runtime E2E test;
- generated API client only if the public OpenAPI contract changes.

No migration or schema change is expected. If one becomes necessary, stop and
revise this design before editing migrations.

## Out of Scope

- OCR normalization-to-IR persistence redesign or OCR review UI changes;
- reconstruction, backup, export, maintenance, or benchmark task registration;
- worker launcher/process-manager changes or concurrency redesign;
- PaddleOCR package/model installation or download behavior;
- release checklist edits, release tag creation, or M11-T18 execution.
