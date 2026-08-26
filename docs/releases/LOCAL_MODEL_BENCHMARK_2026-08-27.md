# Local Model Full Benchmark Evidence — 2026-08-27

## Verdict

`qwen3:1.7b` is **REJECTED** as the default TransLoka translation model on this
machine. The production full benchmark completed all 90 attempts, but one critical
placeholder-integrity failure requires rejection even though the aggregate success
rate was 98.89%.

This report closes the executable full-run evidence portion of M11-REM-08. It does
not close REL-HIGH-003 because an accepted default model and human blind review are
still outstanding.

## Scope and Safety

- Runner: `ProductionFullBenchmarkRunner` created by the production API lifespan.
- Provider: local Ollama at `127.0.0.1:11434`.
- Data: temporary data root and temporary SQLite database.
- User database and model selections: unchanged.
- Network scanning, model download, worker dispatch, and production changes: none.

## Benchmark Configuration

| Setting | Value |
| --- | --- |
| Model | `qwen3:1.7b` |
| Model size | 1,359,293,444 bytes (approximately 1.27 GiB) |
| Dataset | `translation_benchmark_en_id_0.1` |
| Cases | 30 |
| Repetitions | 3 |
| Total attempts | 90 |
| Temperature | 0.0 |
| Batch sizes | 1 and 5 |
| Context lengths | `SHORT`, `MEDIUM`, and `LONG` |
| Ollama version | 0.32.15 |

## Target Hardware

| Component | Observed value |
| --- | --- |
| Operating system | Windows 10.0.26200 |
| CPU | AMD Ryzen 5 3550H with Radeon Vega Mobile Gfx |
| CPU cores | 4 physical / 8 logical |
| Physical RAM | 15.44 GiB |
| NVIDIA GPU | GeForce GTX 1050, 3 GiB, driver 32.0.15.8180 |
| Integrated GPU | AMD Radeon Vega 8 Graphics, 0.5 GiB reported, driver 31.0.21923.1000 |
| Free disk at profile capture | 72.86 GiB |

## Automated Result

| Metric | Result |
| --- | --- |
| Runner status | `FAILED` |
| Recommendation | `REJECTED` |
| Completed attempts | 90 / 90 |
| Successful attempts | 89 |
| Failed attempts | 1 |
| Critical failures | 1 |
| Success rate | 98.89% |
| Quality score | 0.9889 |
| Average latency | 41.06 seconds per attempt |
| Total elapsed time | 3,696.51 seconds (61m 36.51s) |

The failed case was `full_03_placeholders_medium`. Its failure code was
`PLACEHOLDER_MISMATCH`: the model did not preserve all required placeholders
exactly. The full benchmark policy treats any critical failure as grounds for
rejection.

## Resource Evidence

| Metric | Result |
| --- | --- |
| Available RAM before run | 5.729 GiB |
| Minimum available RAM during run | 0.220 GiB |
| Observed available-RAM delta | 5.509 GiB |
| NVIDIA VRAM before run | 0 MiB |
| Peak NVIDIA VRAM during run | 0 MiB |

The physical-memory headroom became very low and paging likely contributed to the
long run time. NVIDIA VRAM remained unused according to `nvidia-smi`. AMD shared
GPU memory was not measurable with that tool, so the NVIDIA value must not be
interpreted as proof that no GPU acceleration occurred.

## License Evidence

`ollama show qwen3:1.7b --license` reports Apache License 2.0 and Copyright 2024
Alibaba Cloud. The current TransLoka model registry record still reports
`license_status=UNKNOWN`; upstream license output does not automatically populate
the application record.

## Verification Gates

- Python: 1,237 passed, 7 skipped.
- Ruff lint: passed.
- Ruff format check: 338 files already formatted.
- mypy: no issues in 352 source files.
- Node lint and typecheck: passed.
- Node tests: API client 37 passed; web 91 passed.
- Production web build: passed.
- Generated API client drift check: current.
- Dependency audit at high severity: no known vulnerabilities.

## Limitations and Required Follow-up

- No human blind translation-quality review was performed.
- RAM evidence is system-wide available-memory delta, not isolated process peak.
- NVIDIA VRAM telemetry does not capture AMD shared GPU memory.
- The application hardware detector does not currently identify the GPU or physical
  core count; those fields were supplemented from Windows hardware inventory.
- The full runner is wired into application state for future worker execution, but
  no blocking HTTP endpoint, persistence, or worker dispatch was added in this task.
- Before release, benchmark a better-suited licensed model (or fix the model/prompt
  behavior), obtain an accepted full result, and complete the required human review.
