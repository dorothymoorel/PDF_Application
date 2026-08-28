# M11-REM-11 Production Reconstruction Worker Runtime Design

## Goal

Close the reconstruction portion of release blocker `REL-HIGH-002` by
connecting the canonical reconstruction API to the local SqliteHuey queue and
a production runner that creates, validates, and records an immutable PDF
export. The queue carries only an application job identifier; every input is
reloaded from the application database and trusted local storage.

## Scope

The production runtime must support:

- `POST /api/v1/projects/{project_id}/reconstruction/start`;
- `GET /api/v1/projects/{project_id}/reconstruction/status`;
- page retry through the existing canonical route;
- a stable Huey task name, `transloka.reconstruction.execute`;
- fail-closed queue configuration in the production app factory;
- a durable `transloka.reconstruction.command.v1` payload;
- worker-side loading of the project, document, selected pages, translated
  Document IR, immutable source PDF, settings, and open critical warnings;
- deterministic overlay, reflow, and hybrid page planning through the existing
  reconstruction package;
- safe PDF assembly, final-PDF validation, immutable storage, export versioning,
  reconstruction page/mapping records, job progress, attempts, cancellation,
  retry, and resource shutdown.

No PDF bytes, translated text, paths, renderer instances, or SQLAlchemy
sessions cross the queue boundary.

## Durable Command and Dispatch Ordering

`ReconstructionCommand` contains exactly:

- schema version;
- project and document identifiers;
- reconstruction mode;
- selected page identifiers, empty for a full-document run;
- the complete validated reconstruction settings snapshot.

Decoding rejects duplicate JSON keys, unknown or missing fields, unsupported
schemas, malformed identifiers, duplicate pages, invalid settings, and a mode
that disagrees with the settings snapshot.

The API must persist both `ApplicationJob` and `ReconstructionJob` before it
enqueues the application job identifier. This removes the current race in
which a consumer can observe the application job before its reconstruction
row exists. Enqueue failure leaves the application job in the canonical
`QUEUE_DISPATCH_FAILED` state and marks the reconstruction row failed. An
idempotent replay never enqueues a second task.

## Worker Loading and Planning

`DatabaseReconstructionRequestLoader` validates that:

- the application job exists, is `RECONSTRUCT_DOCUMENT`, and is executable;
- the command agrees with all job foreign keys and the linked reconstruction
  row;
- the project owns the active document and every selected page;
- the document original points to a validated immutable `ORIGINAL` PDF;
- selected pages are ordered by source page number;
- every rendered text segment has non-empty final text and trusted geometry;
- settings are reconstructed only through `ReconstructionSettings.from_dict`.

Full-document jobs process every persisted source page. Page-scoped jobs
replace only selected pages and safely sanitize preserved pages during final
assembly. Overlay rendering converts supported top-left geometry into PDF user
space and covers source text before drawing selectable translated text. Reflow
uses sanitized `ReflowDocument` input and the restricted resource boundary.
Hybrid mode uses the deterministic classifier per page and records the chosen
strategy and evidence.

Unsupported geometry, inconsistent page numbering, missing translations,
missing render dependencies, unsafe resources, layout overflow, and invalid
PDF output fail closed with stable error codes; there is no silent source-only
or fake-success fallback.

## Persistence and Validation

The runner:

1. starts the canonical job attempt and records heartbeats/progress;
2. creates or refreshes reconstruction page and target mapping rows;
3. renders and assembles a new PDF without modifying the original;
4. validates page structure, selectable translated text, source residue,
   active content, checksum, and open critical warnings;
5. commits the PDF under the managed project export namespace as immutable;
6. creates a `StoredFile` and the next immutable `Export` version;
7. completes the reconstruction, document, project, application job, and
   attempt atomically.

Validation failure must not publish a completed export. Storage cleanup is
best-effort when database persistence fails after a file commit. Re-executing
an already completed job returns the existing result and does not create
another export version.

## Retry and Cancellation

The worker checks the canonical cancellation service before rendering, between
pages, and before publication. Cancellation finalizes the application attempt
and reconstruction row without publishing a completed export.

The existing page retry route updates the selected page strategy/settings,
creates the canonical retry attempt, and enqueues the same application job only
after durable state is committed. Enqueue failure is explicit and never leaves
a retry reported as running without a queued task.

## Runtime Composition

The worker factory creates one engine/session factory, one local storage
adapter, one reconstruction loader, and one production reconstruction runner.
The consumer registers translation, OCR, and reconstruction tasks. API
producers register only the task signature they enqueue and cannot execute
work. Huey storage and the SQLAlchemy engine close exactly once.

The worker declares direct dependencies on `transloka-reconstruction` and
`transloka-quality`. WeasyPrint remains the canonical locked reflow renderer;
no renderer download or external network access occurs at runtime.

## Verification

Focused tests cover command validation, database ownership and immutable source
loading, geometry conversion, mode selection, task-name stability, producer
isolation, consumer registration, exact-once publication, validation failure,
cancellation, retry dispatch, queue failure, and resource closure.

The production E2E test uses a migrated temporary data root and must:

1. seed a project, translated Document IR, source PDF, and validated original;
2. start the production app and submit the canonical reconstruction request;
3. prove the named task and isolated job identifier are stored in `tasks.db`;
4. execute the task through the production worker registry;
5. verify application/reconstruction job and attempt completion;
6. verify page/mapping rows, immutable stored PDF, export version, checksum,
   translated selectable text, source removal, and status endpoint;
7. prove the original PDF is unchanged and factories close independently.

## Expected Files

- `services/api/src/transloka_api/app.py`;
- `services/api/src/transloka_api/routers/reconstruction.py`;
- `services/worker/src/transloka_worker/app.py`;
- `services/worker/src/transloka_worker/reconstruction.py`;
- `services/worker/src/transloka_worker/queue.py`;
- `services/worker/src/transloka_worker/tasks/reconstruction.py` and exports;
- `services/worker/pyproject.toml` and `uv.lock`;
- focused API/worker/reconstruction tests and one runtime E2E test;
- generated API client only if the public OpenAPI contract changes.

No migration or schema change is expected. If one becomes necessary, stop and
revise this design before editing migrations.

## Out of Scope

- reconstruction UI redesign or new public API resources;
- backup task registration or backup remediation;
- OCR/translation pipeline redesign;
- schema migrations, worker concurrency redesign, or remote rendering;
- release checklist edits, release tag creation, or M11-T18 execution.
