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

## Remaining fidelity work

- Source-only embedded fonts need a separately reviewed reuse path. CFF outlines
  and non-first faces in TrueType collections are not implemented by this adapter.
- Font styles are currently selected from block metadata. Mixed styles within one
  block, precise kerning/tracking, rotations and complex shaping remain follow-ups.
- Automatic whole-page HYBRID reflow is now replaced by bounded block wrapping.
  Background-aware text replacement and overflow fitting remain follow-ups.
  Scanned PDFs cannot recover an original font file from pixels.
- Font mappings are persisted; a dedicated user-facing font-warning view is not
  part of this repair.
- Font discovery is cached for the worker lifetime. Restart the worker after font
  installation or to load this code. No running user job was restarted here.
- Benchmark a representative PDF corpus before claiming broad fidelity parity.
