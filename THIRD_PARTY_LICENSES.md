# Third-Party License Inventory

**Project:** TransLoka  
**Inventory Date:** 2026-07-26  
**Project License:** All Rights Reserved  
**Distribution Status:** Personal MVP; not publicly distributed

This inventory records direct dependencies and approved future components. It
does not constitute legal advice or a complete transitive dependency review.
First-party TransLoka workspace packages are not third-party dependencies.

## Current Direct Dependency Inventory

The repository currently has no third-party runtime dependency. The following
development dependencies are declared and locked. `uv-build` is declared as
the workspace build backend but is not recorded in `uv.lock`.

| Component | Category | Purpose | Current Status | Version | License | License Source | Distribution Consideration | Review Status | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| @eslint/js | Node development dependency | ESLint JavaScript rule configuration | DECLARED_LOCKED_DIRECT_DEV | 10.0.1 | MIT | Local cached package metadata (`package.json` license field) | Development-only; review transitive notices before distribution | LOCAL_METADATA_VERIFIED | Direct dependency from `package.json` and `pnpm-lock.yaml` |
| ESLint | Node development dependency | JavaScript and TypeScript lint runner | DECLARED_LOCKED_DIRECT_DEV | 10.8.0 | MIT | Local cached package metadata (`package.json` license field) | Development-only; review transitive notices before distribution | LOCAL_METADATA_VERIFIED | Direct dependency from `package.json` and `pnpm-lock.yaml` |
| TypeScript | Node development dependency | TypeScript compiler and type checker | DECLARED_LOCKED_DIRECT_DEV | 6.0.2 | Apache-2.0 | Local cached package metadata (`package.json` license field) | Development-only; preserve required notices if redistributed | LOCAL_METADATA_VERIFIED | Direct dependency from `package.json` and `pnpm-lock.yaml` |
| typescript-eslint | Node development dependency | Type-aware ESLint integration | DECLARED_LOCKED_DIRECT_DEV | 8.65.0 | MIT | Local cached package metadata (`package.json` license field) | Development-only; review transitive notices before distribution | LOCAL_METADATA_VERIFIED | Direct dependency from `package.json` and `pnpm-lock.yaml` |
| mypy | Python development dependency | Static Python type checking | DECLARED_LOCKED_DIRECT_DEV | 2.3.0 | MIT | Local cached Python `METADATA` license expression | Development-only; review transitive notices before distribution | LOCAL_METADATA_VERIFIED | Direct development dependency from `pyproject.toml` and `uv.lock` |
| Ruff | Python development dependency | Python linting, import sorting, and formatting | DECLARED_LOCKED_DIRECT_DEV | 0.16.0 | MIT | Local cached Python `METADATA` license expression | Development-only; review binary and transitive notices before distribution | LOCAL_METADATA_VERIFIED | Direct development dependency from `pyproject.toml` and `uv.lock` |
| uv-build / `uv_build` | Python build dependency | Build backend for workspace packages | CONFIGURED_BUILD_DEPENDENCY_NOT_LOCKED | `>=0.11.26,<0.12` | REQUIRES_VERIFICATION | Workspace `pyproject.toml` files; no local license metadata found | Do not bundle or distribute until exact resolved version and license are verified | REQUIRES_VERIFICATION | Version is a manifest constraint, not a locked resolution |

Transitive packages are intentionally excluded from this bootstrap inventory.
They must be regenerated and reviewed before distribution.

## Approved but Not Yet Installed

Every component in this section has version `TBD` and status
`APPROVED_NOT_INSTALLED`. A listed component is not approved for distribution
until its exact package, version, direct and transitive licenses, notices, and
Windows compatibility are verified.

### Frontend

| Component | Category | Purpose | Current Status | Version | License | License Source | Distribution Consideration | Review Status | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| Next.js | Frontend | Local web application framework | APPROVED_NOT_INSTALLED | TBD | REQUIRES_VERIFICATION | Not locally verified | Review framework and transitive licenses before distribution | REQUIRES_VERIFICATION | Not installed |
| React | Frontend | User interface runtime | APPROVED_NOT_INSTALLED | TBD | REQUIRES_VERIFICATION | Not locally verified | Review runtime and transitive licenses before distribution | REQUIRES_VERIFICATION | Not installed |
| Tailwind CSS | Frontend | Utility-based styling | APPROVED_NOT_INSTALLED | TBD | REQUIRES_VERIFICATION | Not locally verified | Review generated CSS and package notices before distribution | REQUIRES_VERIFICATION | Not installed |
| shadcn/ui | Frontend | Reusable UI component source | APPROVED_NOT_INSTALLED | TBD | REQUIRES_VERIFICATION | Not locally verified | Review copied component source and bundled notices | REQUIRES_VERIFICATION | Exact components remain TBD |
| TanStack Query | Frontend | Server-state management | APPROVED_NOT_INSTALLED | TBD | REQUIRES_VERIFICATION | Not locally verified | Review package and transitive licenses before distribution | REQUIRES_VERIFICATION | Not installed |
| Zustand | Frontend | Local client-state management | APPROVED_NOT_INSTALLED | TBD | REQUIRES_VERIFICATION | Not locally verified | Review package and transitive licenses before distribution | REQUIRES_VERIFICATION | Not installed |
| React Hook Form | Frontend | Form state and validation integration | APPROVED_NOT_INSTALLED | TBD | REQUIRES_VERIFICATION | Not locally verified | Review package and transitive licenses before distribution | REQUIRES_VERIFICATION | Not installed |
| Zod | Frontend | TypeScript schema validation | APPROVED_NOT_INSTALLED | TBD | REQUIRES_VERIFICATION | Not locally verified | Review package and transitive licenses before distribution | REQUIRES_VERIFICATION | Not installed |
| PDF.js | Frontend | Browser PDF rendering | APPROVED_NOT_INSTALLED | TBD | REQUIRES_VERIFICATION | Not locally verified | Verify exact package and bundled worker notices | REQUIRES_VERIFICATION | Exact package name remains TBD |

### Backend

| Component | Category | Purpose | Current Status | Version | License | License Source | Distribution Consideration | Review Status | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| FastAPI | Backend | Local HTTP API framework | APPROVED_NOT_INSTALLED | TBD | REQUIRES_VERIFICATION | Not locally verified | Review package and transitive licenses before distribution | REQUIRES_VERIFICATION | Not installed |
| Pydantic | Backend | Validation and settings models | APPROVED_NOT_INSTALLED | TBD | REQUIRES_VERIFICATION | Not locally verified | Review package and compiled dependencies before distribution | REQUIRES_VERIFICATION | Not installed |
| SQLAlchemy | Backend | Database ORM and persistence | APPROVED_NOT_INSTALLED | TBD | REQUIRES_VERIFICATION | Not locally verified | Review package and transitive licenses before distribution | REQUIRES_VERIFICATION | Not installed |
| Alembic | Backend | Database migrations | APPROVED_NOT_INSTALLED | TBD | REQUIRES_VERIFICATION | Not locally verified | Review package and transitive licenses before distribution | REQUIRES_VERIFICATION | Not installed |
| Huey | Backend | Local background task queue | APPROVED_NOT_INSTALLED | TBD | REQUIRES_VERIFICATION | Not locally verified | Review package and transitive licenses before distribution | REQUIRES_VERIFICATION | Not installed |

### Document Processing

| Component | Category | Purpose | Current Status | Version | License | License Source | Distribution Consideration | Review Status | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| pdfplumber | Document processing | Digital PDF text and geometry extraction | APPROVED_NOT_INSTALLED | TBD | REQUIRES_VERIFICATION | Not locally verified | Review package, transitive libraries, and PDF fixture rights | REQUIRES_VERIFICATION | Not installed |
| pypdf | Document processing | PDF structure and page manipulation | APPROVED_NOT_INSTALLED | TBD | REQUIRES_VERIFICATION | Not locally verified | Review package and transitive licenses before distribution | REQUIRES_VERIFICATION | Not installed |
| pypdfium2 | Document processing | PDF rendering | APPROVED_NOT_INSTALLED | TBD | REQUIRES_VERIFICATION | Not locally verified | Review bundled PDFium binary license and notices | REQUIRES_VERIFICATION | Not installed |
| ReportLab | Document processing | Overlay PDF generation | APPROVED_NOT_INSTALLED | TBD | REQUIRES_VERIFICATION | Not locally verified | Review package, font handling, and notices before distribution | REQUIRES_VERIFICATION | Not installed |
| Jinja2 | Document processing | Internal reconstruction templates | APPROVED_NOT_INSTALLED | TBD | REQUIRES_VERIFICATION | Not locally verified | Review package and transitive licenses before distribution | REQUIRES_VERIFICATION | Not installed |
| Pillow | Document processing | Image processing | APPROVED_NOT_INSTALLED | TBD | REQUIRES_VERIFICATION | Not locally verified | Review native libraries and bundled binary notices | REQUIRES_VERIFICATION | Not installed |
| OpenCV | Document processing | Image analysis and preprocessing | APPROVED_NOT_INSTALLED | TBD | REQUIRES_VERIFICATION | Not locally verified | Verify exact distribution and bundled native binaries | REQUIRES_VERIFICATION | Exact Python distribution remains TBD |

### Testing

| Component | Category | Purpose | Current Status | Version | License | License Source | Distribution Consideration | Review Status | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| pytest | Testing | Python test runner | APPROVED_NOT_INSTALLED | TBD | REQUIRES_VERIFICATION | Not locally verified | Development-only; review transitive notices | REQUIRES_VERIFICATION | Not installed |
| pytest-asyncio | Testing | Async Python test support | APPROVED_NOT_INSTALLED | TBD | REQUIRES_VERIFICATION | Not locally verified | Development-only; review transitive notices | REQUIRES_VERIFICATION | Not installed |
| httpx | Testing | API and integration test client | APPROVED_NOT_INSTALLED | TBD | REQUIRES_VERIFICATION | Not locally verified | Review runtime use and transitive licenses | REQUIRES_VERIFICATION | Not installed |
| Vitest | Testing | TypeScript unit test runner | APPROVED_NOT_INSTALLED | TBD | REQUIRES_VERIFICATION | Not locally verified | Development-only; review transitive notices | REQUIRES_VERIFICATION | Not installed |
| Testing Library | Testing | UI behavior testing | APPROVED_NOT_INSTALLED | TBD | REQUIRES_VERIFICATION | Not locally verified | Verify exact packages and transitive licenses | REQUIRES_VERIFICATION | Package selection remains TBD |
| Playwright | Testing | Browser end-to-end testing | APPROVED_NOT_INSTALLED | TBD | REQUIRES_VERIFICATION | Not locally verified | Review browser binary licenses and redistribution terms | REQUIRES_VERIFICATION | Not installed |

### Optional Dependencies

These components are approved only for their documented optional capability.
They must not become unconditional base dependencies without a new task and
dependency review.

| Component | Category | Purpose | Current Status | Version | License | License Source | Distribution Consideration | Review Status | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| PaddleOCR | Optional OCR | OCR provider package | APPROVED_NOT_INSTALLED | TBD | REQUIRES_VERIFICATION | Not locally verified | Review Python package, PaddlePaddle, binaries, and model weights separately | REQUIRES_VERIFICATION | Optional OCR dependency group |
| PP-StructureV3 | Optional OCR | Document layout and structure analysis | APPROVED_NOT_INSTALLED | TBD | REQUIRES_VERIFICATION | Not locally verified | Package and model-weight rights require separate review | REQUIRES_VERIFICATION | Optional OCR capability |
| WeasyPrint | Optional reconstruction | Reflow PDF generation | APPROVED_NOT_INSTALLED | TBD | REQUIRES_VERIFICATION | Not locally verified | Review Python package and all native runtime dependencies | REQUIRES_VERIFICATION | Optional reconstruction dependency group |
| OCRmyPDF | Optional derivative tool | Optional OCR derivative workflow | APPROVED_NOT_INSTALLED | TBD | REQUIRES_VERIFICATION | Not locally verified | Review executable, transitive tools, and redistribution requirements | REQUIRES_VERIFICATION | Not part of the core PDF stack |

## Prohibited Dependencies

The following components must not be installed, used, or substituted for the
approved PDF stack. They are prohibited pending a new licensing and
architecture decision, an approved ADR, and Project Owner approval. This
status is a project governance decision, not a legal conclusion.

| Component | Category | Purpose | Current Status | Version | License | License Source | Distribution Consideration | Review Status | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| PyMuPDF | Prohibited PDF dependency | PDF processing | PROHIBITED | N/A | NOT_ASSESSED | Governing TransLoka documentation | Must not be installed or distributed with this project | PROHIBITED | Prohibited pending a new licensing and architecture decision |
| fitz | Prohibited PDF dependency | PyMuPDF import/package alias | PROHIBITED | N/A | NOT_ASSESSED | Governing TransLoka documentation | Must not be installed or distributed with this project | PROHIBITED | Codex must not substitute it for approved PDF libraries |
| pymupdf4llm | Prohibited PDF dependency | PDF-to-LLM processing | PROHIBITED | N/A | NOT_ASSESSED | Governing TransLoka documentation | Must not be installed or distributed with this project | PROHIBITED | Requires an approved ADR and Project Owner approval |

## Local Model License Register

Model licenses are separate from the TransLoka application license. Local
availability does not imply commercial-use or redistribution rights. Model
weights must not be committed to Git, and model selection must follow
`docs/LOCAL_MODEL_BENCHMARK.md`.

No default model selected.

| Model ID | Model Family | Source | Version or Tag | License | Commercial Use Allowed | Redistribution Allowed | Attribution Required | Review Status | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| TBD | TBD | TBD | TBD | REQUIRES_VERIFICATION | REQUIRES_VERIFICATION | REQUIRES_VERIFICATION | REQUIRES_VERIFICATION | NOT_SELECTED | Complete before selecting or distributing any Ollama model |

## OCR Model License Register

The PaddleOCR and PP-Structure Python packages and their model files may have
different license or redistribution conditions. No rights for model weights
are assumed.

| Model ID | Model Family | Source | Version or Tag | License | Commercial Use Allowed | Redistribution Allowed | Attribution Required | Review Status | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| TBD | PaddleOCR model weights | TBD | TBD | REQUIRES_VERIFICATION | REQUIRES_VERIFICATION | REQUIRES_VERIFICATION | REQUIRES_VERIFICATION | REQUIRES_VERIFICATION | Verify the selected OCR model artifact separately |
| TBD | PP-Structure model weights | TBD | TBD | REQUIRES_VERIFICATION | REQUIRES_VERIFICATION | REQUIRES_VERIFICATION | REQUIRES_VERIFICATION | REQUIRES_VERIFICATION | Verify the selected structure-analysis model artifact separately |

## Distribution Considerations

The current Personal MVP is not being distributed. Before any public release,
installer, paid distribution, hosted version, or portfolio download:

1. Regenerate the dependency inventory.
2. Inspect all direct and transitive dependency licenses.
3. Inspect all selected local model licenses.
4. Inspect all selected OCR model licenses.
5. Include every required notice and attribution.
6. Verify font redistribution rights.
7. Verify bundled binary licenses.
8. Review WeasyPrint runtime dependencies.
9. Review PDF fixture rights.
10. Select a final project license.

## Maintenance Rules

- Update this file whenever a manifest, lockfile, build dependency, model, or
  bundled binary changes.
- Derive installed versions from lockfiles and verify licenses from authoritative
  package metadata.
- Mark unresolved entries `REQUIRES_VERIFICATION`; do not infer license rights.
- Perform a complete direct and transitive review before distribution.
