# M11-REM-07 Python Line Ending Normalization Design

## Goal

Close release-gate defect `REL-MEDIUM-001` by making Ruff's configured LF policy
reproducible on Windows checkouts.

## Evidence

- the machine-level Git configuration sets `core.autocrlf=true`;
- the repository has no `.gitattributes` policy;
- `infrastructure/migrations/versions/0006_application_jobs.py` contains 204 CRLF
  line endings;
- `tests/integration/database/test_jobs.py` contains 518 CRLF line endings;
- these are the only files rejected by `uv run ruff format --check .`.

## Design

Add a repository-level `.gitattributes` rule that treats Python source and stub files
as text with LF line endings. Normalize only the two current offenders with Ruff.

The task must not alter Python syntax, migration behavior, tests, dependency files,
or non-Python line-ending policy.

## Acceptance Criteria

- Git reports `text: set` and `eol: lf` for Python files;
- the two affected files contain LF and no CRLF bytes;
- their normalized contents are identical to the committed blobs after Git text
  normalization;
- Ruff format-check, Ruff lint, mypy, and the relevant database tests pass;
- no file outside this task's policy, design, and two normalized targets changes.
