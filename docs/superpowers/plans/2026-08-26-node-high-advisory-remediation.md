# M11-REM-06 Node High Advisory Remediation Plan

1. Record the failing High audit and current dependency paths.
2. Patch only the three vulnerable transitive versions in `pnpm-workspace.yaml`.
3. Regenerate `pnpm-lock.yaml` with pnpm 11.
4. Confirm the resolved dependency graph contains the patched versions only.
5. Run High and Critical audits plus all Node regression gates.
6. Review lockfile churn, stage only allowed files, and commit atomically.

Do not start worker, benchmark, formatting, or release-tag work in this task.
