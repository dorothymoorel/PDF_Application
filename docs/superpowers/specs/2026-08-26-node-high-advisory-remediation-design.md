# M11-REM-06 Node High Advisory Remediation Design

## Goal

Close release blocker `REL-HIGH-004` without upgrading the application framework or
changing product behavior.

## Current Evidence

`pnpm audit --audit-level high` reports three High advisories:

- `brace-expansion@5.0.8`, patched in `5.0.9`;
- `js-yaml@4.3.0`, patched in `4.3.1`;
- `nanoid@3.3.16`, patched in `3.3.18`.

The first two vulnerable versions are explicitly selected by workspace overrides. The
third is selected below `postcss@8.5.23`. All three patched releases are available from
the configured package registry.

## Design

Use narrowly scoped pnpm overrides to select only the first patched release in each
affected dependency line:

- update the existing `brace-expansion` override to `5.0.9`;
- update the existing `js-yaml` override to `4.3.1`;
- add a `postcss@8.5.23>nanoid` override for `3.3.18`.

Regenerate `pnpm-lock.yaml` with the existing pnpm version. Do not update Next.js,
ESLint, TypeScript, Vitest, Tailwind, or OpenAPI tooling in this remediation.

## Verification

The remediation is complete when:

- `pnpm why` resolves only the patched versions;
- both High- and Critical-level audits report no findings;
- lint, typecheck, tests, build, and generated-client drift checks pass;
- the lockfile contains no unrelated package churn;
- the working tree contains only this task's documentation, override, and lockfile
  changes.

## Out of Scope

- Python formatting baseline remediation;
- worker runtime composition;
- full model benchmarking;
- framework or tooling upgrades;
- release checklist edits or release tagging.
