# M11-REM-07 Python Line Ending Normalization Plan

1. Record the failing formatter gate and current Git attributes.
2. Add LF attributes for `*.py` and `*.pyi`.
3. Normalize only the two Ruff-reported Python files.
4. Verify byte-level line endings and normalized-content equivalence.
5. Run formatter, lint, type-check, and focused database tests.
6. Review and commit only M11-REM-07 files.

Do not start worker, model benchmark, or release-tag work.
