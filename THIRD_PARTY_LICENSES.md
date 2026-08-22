# Third-Party License Inventory

**Project:** TransLoka
**Inventory date:** 2026-08-23
**Project license:** All Rights Reserved (not yet selected for redistribution)
**Distribution status:** Personal MVP; not publicly distributed

This is an engineering inventory, not legal advice. It records the direct
third-party dependencies declared by the repository and their resolved
versions. First-party TransLoka workspace packages are listed separately and
are not third-party dependencies.

## Evidence and review method

- Declarations were read from the root, Python workspace, service, and Node
  workspace manifests.
- Python versions were resolved from `uv.lock` (`uv tree --depth 1` reports the
  same resolution); Node versions were resolved from `pnpm-lock.yaml` and
  checked with `pnpm list -r --depth 0 --json`.
- License values were checked against the installed package metadata and,
  where metadata was incomplete, the package's installed license files.
- `uv.lock` contains 57 resolved package records (including first-party
  packages); `pnpm-lock.yaml` contains 341 package records. The tables below
  are the complete direct-dependency review. Transitive notices must still be
  regenerated before any public distribution.

Review statuses:

- `VERIFIED_DIRECT_METADATA` — version and license verified from local package
  metadata or the package's installed license file.
- `VERIFIED_BUNDLED_NOTICES` — package metadata and bundled native/dependency
  license files were identified; those notices must travel with a distribution.
- `UNRESOLVED_BUILD_METADATA` — a build-system constraint is declared but is
  not resolved in the application lockfile.
- `NOT_SELECTED` — optional model/runtime component has no selected artifact.

## Direct Python runtime dependencies

| Package | Workspace | Version | Function | License | Review status | Distribution implication |
| --- | --- | ---: | --- | --- | --- | --- |
| `alembic` | `transloka-core` | 1.18.5 | Database schema migrations | MIT (`License-Expression`) | VERIFIED_DIRECT_METADATA | Preserve the MIT notice; review transitive notices before redistribution. |
| `sqlalchemy` | `transloka-core` | 2.0.51 | Synchronous database engine, ORM, and persistence primitives | MIT (package metadata) | VERIFIED_DIRECT_METADATA | Preserve the MIT notice; review transitive notices before redistribution. |
| `pydantic` | `transloka-document-ir` | 2.13.4 | Typed document and API validation models | MIT (`License-Expression`) | VERIFIED_DIRECT_METADATA | Preserve the MIT notice; review transitive notices before redistribution. |
| `pdfplumber` | `transloka-documents` | 0.11.10 | Digital PDF text, geometry, and table extraction | MIT (license classifier and `LICENSE.txt`) | VERIFIED_DIRECT_METADATA | Preserve the MIT notice; review PDF fixture rights and transitive notices before redistribution. |
| `pypdf` | `transloka-documents` (`crypto` extra) | 6.14.2 | PDF structure, page manipulation, and encrypted-PDF support | BSD-3-Clause (`License-Expression`) | VERIFIED_DIRECT_METADATA | Preserve the BSD notice/disclaimer; review the `cryptography` extra and all transitive notices before redistribution. |
| `pypdfium2` | `transloka-documents` | 5.12.1 | PDF rendering through PDFium | BSD-3-Clause, Apache-2.0, and bundled dependency licenses | VERIFIED_BUNDLED_NOTICES | Ship the package's PDFium and dependency license files/notices with any redistribution. |
| `reportlab` | `transloka-reconstruction` | 5.0.1 | Generates transparent translated-text overlays for reconstructed PDFs | BSD-3-Clause (installed `LICENSE`) | VERIFIED_DIRECT_METADATA | Preserve ReportLab's BSD license notice and disclaimer; review transitive notices before redistribution. |
| `fastapi` | `transloka-api` | 0.140.0 | Local HTTP API framework | MIT (`License-Expression`) | VERIFIED_DIRECT_METADATA | Preserve the MIT notice; review transitive notices before redistribution. |
| `pydantic-settings` | `transloka-api` | 2.14.2 | Typed environment and application settings | MIT (`License-Expression`) | VERIFIED_DIRECT_METADATA | Preserve the MIT notice; review transitive notices before redistribution. |
| `python-multipart` | `transloka-api` | 0.0.32 | Multipart upload parsing | Apache-2.0 (`License-Expression`) | VERIFIED_DIRECT_METADATA | Include the Apache-2.0 license and NOTICE information and mark modifications, if any. |
| `uvicorn` | `transloka-api` | 0.51.0 | Local ASGI server | BSD-3-Clause (`License-Expression`) | VERIFIED_DIRECT_METADATA | Preserve the BSD notice/disclaimer; review transitive notices before redistribution. |
| `huey` | `transloka-worker` | 3.3.2 | Local background job queue | MIT (installed `LICENSE` file) | VERIFIED_DIRECT_METADATA | Preserve the MIT notice; review transitive notices before redistribution. |

## Direct Python development dependencies

| Package | Declared by | Version | Function | License | Review status | Distribution implication |
| --- | --- | ---: | --- | --- | --- | --- |
| `httpx2` | root `dev` group | 2.9.1 | HTTP client for API/integration tests | BSD-3-Clause (`License-Expression`) | VERIFIED_DIRECT_METADATA | Development-only; if bundled, preserve the BSD notice/disclaimer and review transitive notices. |
| `mypy` | root `dev` group | 2.3.0 | Static Python type checking | MIT (`License-Expression`) | VERIFIED_DIRECT_METADATA | Development-only; if bundled, preserve the MIT notice and review transitive notices. |
| `pytest` | root `dev` group | 9.1.1 | Python test runner | MIT (`License-Expression`) | VERIFIED_DIRECT_METADATA | Development-only; if bundled, preserve the MIT notice and review transitive notices. |
| `ruff` | root `dev` group | 0.16.0 | Python linting and formatting | MIT (`License-Expression`) | VERIFIED_DIRECT_METADATA | Development-only; if bundled, preserve the MIT notice and review transitive notices. |

## Direct Node runtime dependencies

| Package | Workspace | Version | Function | License | Review status | Distribution implication |
| --- | --- | ---: | --- | --- | --- | --- |
| `@hookform/resolvers` | `apps/web` | 5.5.7 | Connects form state to schema resolvers | MIT (`package.json`) | VERIFIED_DIRECT_METADATA | Preserve the MIT notice; review transitive notices before redistribution. |
| `@tanstack/react-query` | `apps/web` | 5.101.4 | Client-side server-state and cache management | MIT (`package.json`) | VERIFIED_DIRECT_METADATA | Preserve the MIT notice; review transitive notices before redistribution. |
| `next` | `apps/web` | 16.2.12 | React web application framework | MIT (`package.json`) | VERIFIED_DIRECT_METADATA | Preserve the MIT notice; review framework transitive notices before redistribution. |
| `pdfjs-dist` | `apps/web` | 6.2.108 | Browser-side PDF rendering | Apache-2.0 (`package.json`) | VERIFIED_DIRECT_METADATA | Include the Apache-2.0 license and NOTICE information and review bundled worker/transitive notices. |
| `react` | `apps/web` | 19.2.8 | UI runtime | MIT (`package.json`) | VERIFIED_DIRECT_METADATA | Preserve the MIT notice; review transitive notices before redistribution. |
| `react-dom` | `apps/web` | 19.2.8 | React DOM renderer | MIT (`package.json`) | VERIFIED_DIRECT_METADATA | Preserve the MIT notice; review transitive notices before redistribution. |
| `react-hook-form` | `apps/web` | 7.83.0 | Browser form state management | MIT (`package.json`) | VERIFIED_DIRECT_METADATA | Preserve the MIT notice; review transitive notices before redistribution. |
| `zod` | `apps/web` | 4.4.3 | Runtime TypeScript/JavaScript schema validation | MIT (`package.json`) | VERIFIED_DIRECT_METADATA | Preserve the MIT notice; review transitive notices before redistribution. |

## Direct Node development dependencies

| Package | Workspace | Version | Function | License | Review status | Distribution implication |
| --- | --- | ---: | --- | --- | --- | --- |
| `@eslint/js` | root | 10.0.1 | ESLint JavaScript rule configuration | MIT (`package.json`) | VERIFIED_DIRECT_METADATA | Development-only; if bundled, preserve the MIT notice and review transitive notices. |
| `eslint` | root | 10.8.0 | JavaScript/TypeScript lint runner | MIT (`package.json`) | VERIFIED_DIRECT_METADATA | Development-only; if bundled, preserve the MIT notice and review transitive notices. |
| `typescript` | root | 6.0.2 | TypeScript compiler and type checker | Apache-2.0 (`package.json`) | VERIFIED_DIRECT_METADATA | Development-only; if bundled, include Apache-2.0 license/NOTICE information. |
| `typescript-eslint` | root | 8.65.0 | Type-aware ESLint integration | MIT (`package.json`) | VERIFIED_DIRECT_METADATA | Development-only; if bundled, preserve the MIT notice and review transitive notices. |
| `@tailwindcss/postcss` | `apps/web` | 4.3.3 | Tailwind PostCSS integration | MIT (`package.json`) | VERIFIED_DIRECT_METADATA | Development-only; if bundled, preserve the MIT notice and review transitive notices. |
| `@testing-library/dom` | `apps/web` | 10.4.1 | DOM behavior testing utilities | MIT (`package.json`) | VERIFIED_DIRECT_METADATA | Development-only; if bundled, preserve the MIT notice and review transitive notices. |
| `@testing-library/react` | `apps/web` | 16.3.2 | React component testing utilities | MIT (`package.json`) | VERIFIED_DIRECT_METADATA | Development-only; if bundled, preserve the MIT notice and review transitive notices. |
| `@types/node` | `apps/web` | 24.13.3 | Node.js TypeScript declarations | MIT (`package.json`) | VERIFIED_DIRECT_METADATA | Development-only; if bundled, preserve the MIT notice and review transitive notices. |
| `@types/react` | `apps/web` | 19.2.17 | React TypeScript declarations | MIT (`package.json`) | VERIFIED_DIRECT_METADATA | Development-only; if bundled, preserve the MIT notice and review transitive notices. |
| `@types/react-dom` | `apps/web` | 19.2.3 | React DOM TypeScript declarations | MIT (`package.json`) | VERIFIED_DIRECT_METADATA | Development-only; if bundled, preserve the MIT notice and review transitive notices. |
| `jsdom` | `apps/web` | 30.0.0 | DOM implementation for tests | MIT (`package.json`) | VERIFIED_DIRECT_METADATA | Development-only; if bundled, preserve the MIT notice and review transitive notices. |
| `tailwindcss` | `apps/web` | 4.3.3 | Utility CSS generation | MIT (`package.json`) | VERIFIED_DIRECT_METADATA | Development-only; if bundled, preserve the MIT notice and review transitive notices. |
| `vitest` | `apps/web` and `packages/api-client` | 4.1.10 | JavaScript/TypeScript test runner | MIT (`package.json`) | VERIFIED_DIRECT_METADATA | Development-only; if bundled, preserve the MIT notice and review transitive notices. |
| `openapi-typescript` | `packages/api-client` | 7.13.0 | Generates TypeScript API types from OpenAPI | MIT (`package.json`) | VERIFIED_DIRECT_METADATA | Development-only; if bundled, preserve the MIT notice and review transitive notices. |
| `typescript` | `packages/api-client` | 5.9.3 | API-client TypeScript compiler | Apache-2.0 (`package.json`) | VERIFIED_DIRECT_METADATA | Development-only; if bundled, include Apache-2.0 license/NOTICE information. |

## First-party workspace packages

The following packages are private, first-party TransLoka workspaces and are
not third-party license entries: `transloka-workspace`, `transloka-api`,
`transloka-core`, `transloka-document-ir`, `transloka-documents`,
`transloka-glossary`, `transloka-quality`, `transloka-reconstruction`,
`transloka-translation`, `transloka-worker`, `@transloka/root`,
`@transloka/web`, `@transloka/api-client`, `@transloka/ui`, and
`@transloka/shared-config`.

The Python packages declare `Private :: Do Not Upload`, and the Node workspaces
are marked `private: true`. These declarations do not grant rights to any
third-party dependency listed above.

## Build-system dependency not resolved in the application lock

| Package | Constraint | Function | License | Review status | Distribution implication |
| --- | --- | --- | --- | --- | --- |
| `uv-build` / `uv_build` | `>=0.11.26,<0.12` in each Python package build-system table | Builds the Python workspace packages | Not locally resolved in `uv.lock` | UNRESOLVED_BUILD_METADATA | Resolve and verify the exact build backend license before bundling or distributing a built artifact. |

## PyMuPDF exclusion

The manifests and lockfiles were checked for `PyMuPDF`, `pymupdf`,
`pymupdf4llm`, and `fitz`. None is present as a dependency in the Python or
Node dependency declarations or lockfiles. The names remain in governing
documentation only as an explicit prohibition. The approved PDF stack is
`pdfplumber`, `pypdf`, `pypdfium2`, `reportlab`, and browser `pdfjs-dist`.

| Prohibited component | Status | Distribution implication |
| --- | --- | --- |
| PyMuPDF | PROHIBITED; not installed or locked | Must not be added or distributed without a new licensing/architecture decision and owner approval. |
| `fitz` | PROHIBITED alias; not installed or locked | Must not substitute for the approved PDF stack. |
| `pymupdf4llm` | PROHIBITED; not installed or locked | Must not be added or distributed without a new approved decision. |

## Local model license register (separate from application dependencies)

Model weights are not application dependencies and their license must be
reviewed separately from the Ollama runtime. No model is selected or pinned in
the repository, and model weights must not be committed to Git.

| Artifact | Version/tag | License | Commercial use | Redistribution | Review status |
| --- | --- | --- | --- | --- | --- |
| Ollama runtime | Not declared or locked | Separate runtime terms; verify the installed release before distribution | REQUIRES_VERIFICATION | REQUIRES_VERIFICATION | NOT_SELECTED |
| Selected local model weights | None selected | Model-specific license required | REQUIRES_VERIFICATION | REQUIRES_VERIFICATION | NOT_SELECTED |
| PaddleOCR / PP-Structure model weights | None selected | Model-specific license required | REQUIRES_VERIFICATION | REQUIRES_VERIFICATION | NOT_SELECTED |

Local availability does not imply commercial-use or redistribution rights.
Selecting a model for a later task requires recording its exact model ID/tag,
source, license, attribution, and redistribution terms in this section.

## Distribution gate and maintenance

The Personal MVP is not currently distributed. Before a public release,
installer, hosted version, paid distribution, or portfolio download:

1. Re-resolve both lockfiles and regenerate the direct and transitive notice
   inventory.
2. Review all transitive licenses, including bundled PDFium and any native
   binaries.
3. Review selected local model and OCR model licenses separately.
4. Include every required license, copyright, NOTICE, and attribution file.
5. Verify font and PDF fixture redistribution rights.
6. Select and record a final project license.

Update this file whenever a manifest, lockfile, build backend, model, or
bundled binary changes. Unresolved license metadata must remain explicitly
marked `UNRESOLVED_BUILD_METADATA` or `REQUIRES_VERIFICATION`; do not infer
distribution rights from package names alone.
