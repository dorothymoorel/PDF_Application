# Reconstruction font fidelity: production wiring and baseline

Date: 2026-09-05

Scope: user-authorized first repair following the PDF fidelity review. This is a
remediation of M10-T03 (Font Resolver in `CODEX_TASKS.md`) with the production
worker wiring and regression tests explicitly included in the accepted proposal.
It is not a new milestone or a claim of DeepL parity.

## Requirements and boundaries

- `CODEX_TASKS.md`, M10-T03: source/system/metric-compatible/fallback resolution;
  do not extract or redistribute unreviewed proprietary source fonts.
- `RECONSTRUCTION_ENGINE.md`, sections 18-20: measure with the rendered font,
  support styles and glyphs, and record embedding decisions.
- `TEST_PLAN.md`, sections 58 and 61: preserve source artwork, check available,
  unavailable, styled, unsupported and restricted fonts, and source immutability.
- `DOCUMENT_IR.md`, section 24, and `DATABASE_SCHEMA.md`, section 34.3:
  source style and the existing `font_mapping_json` field.
- `MVP_SCOPE.md` section 26 and `TECH_STACK_DECISIONS.md` section 15:
  existing ReportLab/pypdf overlay and HYBRID default remain in force.
- `SECURITY.md`: local resources only, sanitized derivative PDFs, no source changes.

The earlier recommendation to make OVERLAY the application default was not
applied: HYBRID is the documented default. This repair benefits explicit OVERLAY
and pages for which HYBRID selects overlay. Whole-page reflow is a separate issue.

## Root cause and repair

The production worker reduced every nonstandard source font to a PDF base font.
The existing FontResolver was metadata-only and was not connected to ReportLab.
Filename-based font discovery also missed real family/PostScript names and styles.

The new local adapter reads real family/PostScript names, OS/2 weight and embedding
flags, and italic metadata using the already-installed ReportLab parser. It uses
FontResolver, loads and registers only selected faces, verifies actual character
coverage, and supplies the same registered font to wrapping and rendering. Common
PDF subset prefixes and PostScript name variants now match local font families.
Metric-compatible groups are explicitly named; the adapter does not treat every
sans-serif font as metrically equivalent to every other sans-serif font.

Source font programs are never extracted. Source font names are lookup keys, not
paths to open. Unsupported formats, oversized/symlink files, malformed fonts,
missing OS/2 embedding information, restricted embedding, no-subsetting and
bitmap-only flags cause the candidate to be skipped. No embedding override is
enabled. A configured fallback is used where it covers the text. If none of the
eligible candidates covers the text, rendering raises a controlled error instead
of publishing missing-glyph boxes. Standard font encoding checks also cover Symbol.

Per-block metadata records the source and selected family, resolution stage,
embedding status, weight, italic style and fallback warning in the existing
database field. Resolved filesystem paths and font bytes are not stored there.
No dependency, schema, migration, endpoint or frontend contract changed.

## Files in this repair

- `python/transloka-reconstruction/src/transloka_reconstruction/fonts/resolver.py`
- `python/transloka-reconstruction/src/transloka_reconstruction/fonts/reportlab.py`
- `services/worker/src/transloka_worker/reconstruction.py`
- `tests/unit/reconstruction/fonts/test_resolver.py`
- `tests/unit/reconstruction/fonts/test_reportlab.py`
- `tests/integration/worker/test_reconstruction_runtime.py`
- `tests/e2e/runtime/test_reconstruction_worker_runtime.py`
- This report.

Existing translation, recovery and UI changes were preserved. Nothing was staged
or committed by this task.

## Verification

- Final focused font, worker and production E2E tests: 44 passed. This includes
  three final base-font alias cases added during the wider regression run.
- Broader reconstruction/API regression before the final Symbol coverage check:
  145 passed, 5 skipped. Skips are optional WeasyPrint runtime tests; the package
  is not installed in this environment.
- `uv run ruff check .`: passed.
- `uv run ruff format --check .`: passed (365 files).
- `uv run mypy .`: passed (379 source files).
- `git diff --check`: passed; existing LF/CRLF warnings are unrelated.
- `uv run pytest -m "not slow and not requires_ollama and not requires_gpu" -q`:
  **1508 passed, 7 skipped, 1 failed in 704.94 seconds**. The single failure is
  diagnosed below. This broader run began before the final base-font alias guard;
  the final 44-test focused run verifies that guard and its three added cases.
- Frontend commands were not run because this repair does not change frontend,
  API schema or dependencies.

The generated two-language fixture includes a bold heading, two regular lines,
an italic caption, an image and a vector border. At 144 DPI, same-text
reconstruction is pixel-identical to the source. With translated text, the image
region remains pixel-identical; embedded image bytes, page dimensions, font family,
font size, first-line position and line spacing are verified independently.
The rendered source and translation were also visually inspected.

This is a controlled regression baseline, not a 20-50-document benchmark or a
test on the user's entire book. Actual Windows discovery selected Calibri Bold
Italic (700/italic), Times New Roman (400/regular) and Arial (400/regular) with
SYSTEM resolution, subset embedding and no missing glyphs.

Cold Windows catalog discovery and three font resolutions took 6.11 seconds;
100 subsequent cached Calibri resolutions took 1.106 seconds in a separate smoke
check. These are local observations, not universal performance guarantees.

### Wider-suite failure diagnosis

`tests/integration/ollama/test_ollama.py::test_models_router_blocks_remote_configuration`
fails during application startup: `sqlite3.OperationalError: no such table:
application_jobs`. This test creates a fresh data root without migrating its
database, and startup recovery queries the jobs table before the health request.

The same failure reproduced independently and with the HEAD versions of the
previously clean font-resolver and reconstruction-worker modules loaded only in
memory. No checkout, file restoration or database change to user data was involved.
The failure therefore persists without this task's reconstruction changes.
At the time of that audit, the Ollama fixture/startup case was outside the active
font repair. The full repository was not reported as all-green or release-ready.

### Authorized follow-up: Ollama test database preparation

The user subsequently authorized repairing that remaining failure. The change is
within `CODEX_TASKS.md` M7-T02's `tests/integration/ollama/**` scope: the remote-URL
test now runs `command.upgrade(..., "head")` against its isolated temporary data
root before creating the application, matching the existing `models_api` fixture.
The original 403 / `REMOTE_OLLAMA_BLOCKED` assertions remain unchanged. Production
startup, remote URL validation and recovery behavior were not modified.

Verification after the one-line test change:

- `uv run pytest tests/integration/ollama/test_ollama.py tests/recovery/test_stale_job_recovery.py -q`:
  **106 passed in 72.54 seconds**, including the formerly failing remote-URL test.
- `uv run ruff check .`: passed.
- `uv run ruff format --check .`: passed (365 files).
- `uv run mypy .`: passed (379 source files).
- `git diff --check`: passed, existing LF/CRLF warnings only.

The 12-minute full Python suite was not repeated for this fixture-only change;
the historical full-suite result above remains an accurately dated observation,
not a claim about a new full-suite run. This follow-up changed only
`tests/integration/ollama/test_ollama.py` and this report. Nothing was staged or
committed. Reflow changes and service restarts were not started in this follow-up.

### Authorized follow-up: bounded HYBRID paragraph reflow

The next authorized continuation repairs the production integration of M10-T11
(per-block strategy selection). Previously, a single REFLOW block or a
reflow-friendly page caused `_render_page` to call the whole-document reflow
renderer. That path omitted untranslated artwork and reset text layout.

HYBRID now composes onto the source page using the existing ReportLab/pypdf
overlay renderer, which wraps translated paragraphs inside their original boxes
using the resolved output font, source size and leading. Classifier-selected
paragraphs retain block strategy REFLOW; fixed text uses OVERLAY and untranslated
blocks use PRESERVE. The page composition strategy is OVERLAY, an existing
database enum value, while the requested job mode remains HYBRID. No migration
or dependency change is needed. Explicit REFLOW mode remains unchanged.

This is bounded region wrapping, not the complete M10-T15 fallback chain:
oversized text raises the existing layout error before output publication.
There is no silent clipping, automatic whole-page fallback, box expansion,
font reduction, movement of neighboring blocks or automatic added page here.
Existing source-box overlap and non-white backgrounds remain separate issues.

Changed in this follow-up only: the reconstruction worker, its integration test,
the existing reconstruction runtime E2E test, and this report. Pre-existing
translation/font changes were retained; nothing was staged or committed, no
user job was started and no service was restarted.

Verification:

- Before the fix, three new paragraph/overflow cases reproduced the whole-page
  routing failure (attempting to invoke unavailable optional WeasyPrint).
- `uv run pytest tests/unit/reconstruction tests/integration/reconstruction tests/security/reconstruction tests/integration/worker/test_reconstruction_runtime.py tests/e2e/runtime/test_reconstruction_worker_runtime.py tests/integration/api/test_reconstruction.py -q`:
  **180 passed, 5 skipped in 26.17 seconds**. Skips require optional WeasyPrint.
- Long-paragraph fixtures cover both mixed-page classification and artwork
  absent from the IR. All target text is selectable, remains in bounds and
  retains 12-point Helvetica; the heading retains 20-point Helvetica Bold and
  its position. Source checksum, page dimensions, image bytes and raster pixels
  below the text are unchanged. The rendered pair was visually inspected.
- Explicit REFLOW dispatch is tested with a stub (not an actual WeasyPrint run).
- API/queue/worker E2E runs both OVERLAY and HYBRID through real migrated temp
  databases and verifies persisted page/block strategies and font metadata.
- Ruff check, Ruff format check (365 files), mypy (379 source files), and
  `git diff --check`: passed.

The full Python repository suite and frontend suite were not rerun in this
backend-only follow-up. These controlled fixtures do not establish fidelity for
the user's entire book or parity with DeepL.

### Authorized follow-up: preserve per-line typography metadata

Review date: 2026-09-08. Follow-up label: REL-FID-02.

Digital analysis previously retained font and geometry data in memory for words,
characters, and lines, then persisted only one block-level font name and size.
The worker now keeps the existing block-level keys for compatibility and adds
ordered `source_lines`. Each line records its source geometry, font name, font
size, and contiguous `style_runs`; each run records source geometry, font name,
font size, upright orientation, and a zero-based `word_start` (inclusive) /
`word_end` (exclusive) range relative to that line's extracted words. The stored
block `source_text` retains the visual line breaks and space-joined words used by
these ranges. They refer to extracted source words, including fragments split at
font changes, and do not imply a word-for-word mapping to the translation.

This uses the existing valid `document_blocks.style_json` field. No schema,
migration, dependency, API, extraction model, or source-PDF mutation is needed.
The reconstruction renderer remains block-level in this follow-up; consuming the
line/run metadata is separate work.
The metadata is written by new digital analysis runs after loading the updated
worker; existing document rows are not backfilled or reanalyzed by this repair.

Verification for this follow-up:

- `uv run pytest tests/golden tests/unit/documents tests/integration/worker/test_analysis_runtime.py tests/integration/worker/test_reconstruction_runtime.py -q`:
  **47 passed**.
- The production-path fixture verifies three ordered source lines at their
  expected positions (20-point spacing), mixed regular/bold/italic runs at 12/11
  points, run geometry measured from the fixture fonts, merged adjacent words of
  the same style, source-word ranges, and byte-identical original PDF storage.
- `uv run ruff check .`: passed.
- `uv run ruff format --check .`: passed (374 files).
- `uv run mypy .`: passed (383 source files).
- `git diff --check`: passed.

### Authorized follow-up: bounded per-line and source-run rendering

Review date: 2026-09-08. Follow-up label: REL-FID-03.

OVERLAY and the bounded HYBRID path now consume REL-FID-02 `source_lines`.
Uniform-style translations use the original line positions, indents, font and
font size, wrapping only within the original block and available source lines.
Explicit translated newlines remain hard breaks. Oversized words or paragraphs
raise a layout error before publication; there is no clipping, font shrinking,
extra page or whole-page fallback. Legacy blocks without this metadata keep
their existing renderer, and explicit REFLOW is unchanged.

For unchanged text, each source style run is rendered at its recorded geometry
with its own font and size. Changed mixed-style text requires a reviewed
source-to-target alignment that the current IR does not contain. It raises
`SourceStyleAlignmentError`; equal source/target word counts are not evidence
of alignment. This is a bounded implementation, not general translated inline
bold/italic support. Invalid ranges, non-finite sizes, out-of-order/overlapping
lines or runs, out-of-parent geometry and unsupported orientation are rejected.

The loader retains the raw block text separately from normalized segment text
so stored source-word ranges remain valid. Per-line/run font mappings are saved
in the existing reconstruction metadata field. The shared overlay wrapper also
uses the renderer's existing 0.01-point width tolerance: floating-point noise
previously wrapped an exactly fitting source run into a spurious second line.

Changed files: the reconstruction worker, shared overlay generator, existing
worker integration test, existing reconstruction runtime E2E test, and this
report. No dependency, migration, API or frontend changes. Existing document
rows were not reanalyzed, services were not restarted and user jobs were untouched.

Verification:

- `uv run pytest tests/unit/reconstruction tests/integration/reconstruction tests/security/reconstruction tests/integration/worker/test_reconstruction_runtime.py tests/e2e/runtime/test_reconstruction_worker_runtime.py tests/integration/api/test_reconstruction.py tests/golden tests/unit/documents tests/integration/worker/test_analysis_runtime.py -q`:
  **226 passed, 5 skipped in 68.56 seconds**. Skips require optional WeasyPrint.
- After adding a newline-free wrapping regression,
  `uv run pytest tests/integration/worker/test_reconstruction_runtime.py -q`:
  **28 passed**. All translated words remain present in the source line slots.
- Real API/queue/worker tests cover both modes with and without stored line
  metadata, raw multiline text versus normalized segments, persisted run
  mappings, completed exports and byte-identical original storage.
- Raster pairs were visually inspected: irregular spacing and indentation are
  retained; artwork pixels and image bytes are unchanged. The unchanged-text
  mixed regular/bold/italic fixture is pixel-identical to its source.
- Ruff check, Ruff format check (374 files), mypy (383 source files), and
  `git diff --check`: passed.

The full Python and frontend suites were not rerun. No stage, commit or push
was performed for this follow-up. These fixtures do not establish fidelity for
the user's entire book or parity with DeepL.

#### REL-FID-03 review correction: fractional font-size roundoff

The review reproduced false mixed-style failures on uniform 11.04-, 11.1- and
9.6-point text. Extracting three lines across different PDF coordinates produced
slightly different floating-point sizes (for example, `11.04000000000002` and
`11.039999999999992`). Exact tuple equality incorrectly rejected translation.

The existing style guard now compares sizes against the first run with
`math.isclose(rel_tol=0, abs_tol=1e-6)`. Font names still match exactly and
recorded sizes are retained for rendering; no metadata is rounded or rewritten.
Only extraction noise is tolerated, not a general style-alignment fallback.

The six real-PDF regressions failed before the fix in OVERLAY/HYBRID. After the
fix, the worker integration suite passes **37 tests**, including rejection of
real size differences of 0.0001, 0.01 and 1 point and existing mixed-font cases.
Ruff check, Ruff format check (374 files), mypy (383 source files), and
`git diff --check` pass. This correction changes only the worker, its existing
integration tests and this report; no stage, commit, push or service restart.
The broader reconstruction/analysis command listed above was rerun after this
correction: **236 passed, 5 skipped in 58.91 seconds** (optional WeasyPrint).

### Authorized follow-up: bounded HYBRID overflow fitting

Review date: 2026-09-08. Follow-up label: REL-FID-04.

The visual trial exposed a remaining integration gap: valid translated text
could overflow the original line slots even when the source block had enough
vertical space. HYBRID already intentionally uses overlay composition to retain
the source page; replacing it with whole-page reflow is not the repair.

HYBRID now tries the exact source-line layout first. For uniform-style text that
overflows, it rewraps inside the original block with the same resolved font,
font size, and average source-line spacing. If that still fails, it expands
horizontally only into space that ends before the next vertically overlapping
text block or the page edge. The smallest fitting width is retained. Compact
line spacing is attempted only after those source-spacing layouts fail. Font
reduction is last, bounded by `maximum_font_reduction_percent` and
`minimum_body_font_pt`. The existing ReportLab output renderer validates every
candidate. Searches are bounded to 16 iterations with a 0.01-point interval. The
default 10-percent reduction limit is unchanged; no global setting is relaxed.

This fallback deliberately changes line placement or the target width within the
affected block; it is not exact original line-spacing preservation. It does not
move or cover neighboring text blocks, add pages, truncate text or fall back to
whole-page reflow. Unresolved overflow remains a layout error identifying the
block that requires review. Mixed-style translation and invalid typography still fail
their existing validation rather than entering the fitting path. Explicit
OVERLAY remains strict; legacy blocks without source lines and explicit REFLOW
are unchanged.

Fitted blocks persist `REWRAP`, `EXPAND_BOX`, `REDUCE_SPACING`, or `REDUCE_FONT` in
`fit_strategy`, with source/output sizes and `SOURCE_LINE_LAYOUT_ADJUSTED` in
font-mapping metadata. Expanded blocks also persist the new target geometry and
`SOURCE_BOX_EXPANDED`. The page remains `OVERLAY` and fitted blocks are `REFLOW`.
This metadata is not yet a dedicated UI warning or a new application-warning row.

Changed files: the reconstruction worker and API router, their existing
integration/E2E tests, the reconstruction workspace and its existing component
test, and this report. No dependency, migration or API contract changes.

Verification:

- `uv run pytest tests/integration/worker/test_reconstruction_runtime.py tests/e2e/runtime/test_reconstruction_worker_runtime.py -q`:
  **56 passed in 20.41 seconds**. Covers source-line spacing, rewrapping, the
  smallest collision-bounded expansion,
  largest permitted font, configured
  limits, full selectable text, unchanged source checksum and unaffected artwork
  raster, unchanged OVERLAY strictness, invalid/mixed-style rejection in both
  modes, and persisted fitting metadata through the real API/queue/worker path.
- The broader reconstruction/analysis command listed under REL-FID-03:
  **251 passed, 5 skipped in 42.26 seconds**. Skips require optional WeasyPrint.
- `uv run ruff check .`: passed.
- `uv run ruff format --check .`: passed (374 files).
- `uv run mypy .`: passed (383 source files).
- `git diff --check`: passed.

A read-only SQLite probe of the existing REL-FID-03 Visual Trial checked all six
source-line blocks against the saved HYBRID settings (10-percent reduction,
8-point minimum). One block retained source lines. Both paragraphs preserved
their original 12-point font and 25.51-point source-line spacing by expanding to
the smallest fitting widths. The page-two title and both page numbers likewise
kept their original 20- and 10-point sizes through bounded horizontal expansion.

After a controlled stack restart, live job
`job_3c7f0a5d-32ca-4a33-b7e9-765015aeee31` completed through the real API,
SQLite queue, worker, database, storage and export path. The two-page export
checksum matches its `StoredFile`, all translated text is selectable, source
font sizes are 10/12/20 points, and the measured paragraph line positions retain
the 25.51-point spacing. Both rasterized pages were inspected: headings, body
text, and complete page-number footers are legible without clipping or overlap.

A preceding live rerun with the same implicit-page command hash as an existing
completed result failed at 75 percent with `INTEGRITYERROR`. Repeating a completed
reconstruction under a new idempotency key is therefore a separate deduplication
defect. The successful live validation selected the same two pages explicitly,
producing a distinct command hash; it did not hide or delete the failed job.

That defect is now repaired at the shared API dispatch boundary. The command hash
includes reconstruction settings version `rel-fid-04`, so a changed rendering
engine does not reuse an output produced by an older engine. Once a hash has a
completed result, a matching start request returns that existing application job
and does not create or enqueue another job. The database uniqueness constraint
remains unchanged as the final concurrency guard.

The API regression suite passes **9 tests**. The broader reconstruction and
analysis selection passes **252 tests with 5 optional WeasyPrint skips**. Ruff,
format, mypy and `git diff --check` pass. After restarting the local stack, the
formerly conflicting implicit-page request completed as
`job_aaaf9fbb-5ef2-40e5-ba84-c79f6d9944ed`. Repeating it with a different
idempotency key returned that same completed job, and a read-only database query
found exactly one `rel-fid-04` row for its hash.

The UI trial then exposed a stale placeholder: when the initial status request
had failed and `POST /reconstruction/start` reused a completed job, the component
displayed `Completed 0%` and `0 of 0`. Successful starts and page retries now
restart the existing status poll instead of inventing empty progress data. The
component regression passes **5 tests**; the full web suite passes **117 tests**,
with web lint and typecheck also passing. A live repeat from the Reconstruction
panel retained `Completed 100%`, `2 of 2 source pages`, `2 target pages`, and
`0 warnings`.

A hard reload also exposed a transient project-header failure while the local API
was warming up. The initial read now retries exactly once after 500 ms only for
network and timeout failures; API and validation errors remain final. Its focused
component regression passes; the full web suite includes it in the 117 passing
tests. Three consecutive live hard reloads restored
the project name and `Ready For Export` state without manual refresh.

No stage, commit or push. Existing untracked `graphify-out/` was left untouched.
The local development stack remains running for user review. The full repository
Python and frontend suites were not rerun.

## Remaining fidelity work

- Source-only embedded fonts need a separately reviewed reuse path. CFF outlines
  and non-first faces in TrueType collections are not implemented by this adapter.
- Source lines and unchanged-text style runs are now rendered. Translated mixed
  styles still need explicit source-to-target alignment; they are not guessed
  from word counts. Precise kerning/tracking, rotations and complex shaping
  remain follow-ups.
- Automatic whole-page HYBRID reflow is now replaced by bounded block wrapping.
  Bounded uniform-style overflow fitting is implemented above; image-aware safe
  regions, unresolved regions without horizontal room, and background-aware text
  replacement remain follow-ups.
  Scanned PDFs cannot recover an original font file from pixels.
- Font mappings are persisted; a dedicated user-facing font-warning view is not
  part of this repair.
- Font discovery is cached for the worker lifetime. Restart the worker after font
  installation or to load this code. No running user job was restarted here.
- Benchmark a representative PDF corpus before claiming broad fidelity parity.
