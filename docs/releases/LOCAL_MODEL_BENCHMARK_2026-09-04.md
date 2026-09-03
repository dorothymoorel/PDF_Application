# Local Model Acceptance Evidence — 2026-09-04

## Verdict

`qwen3:1.7b` **passes the automated TransLoka model gate** on this machine.
The production full benchmark completed all 90 attempts with no critical
failures and returned `RECOMMENDED_DEFAULT`.

This supersedes the automated result in
`LOCAL_MODEL_BENCHMARK_2026-08-27.md`. It does not by itself approve the MVP
release: a human blind translation-quality review and a clean M11-T18 release
checklist rerun remain required.

## Scope and safety

- Runner: `ProductionFullBenchmarkRunner` using the application model registry.
- Provider: local Ollama at `127.0.0.1:11434`.
- Model download or replacement: none.
- Placeholder validation: unchanged and fail-closed.
- Repository runtime artifacts: none.
- User documents and project records: unchanged.

## Candidate and registry

| Field | Value |
| --- | --- |
| Application model ID | `mdl_f8ce9518-95b6-4e7e-a8ff-e5f24d1de6a9` |
| Ollama model | `qwen3:1.7b` |
| Ollama digest | `8f68893c685c` |
| Model size | 1,359,293,444 bytes (approximately 1.27 GiB) |
| License reported by local model manifest | Apache License 2.0; Copyright 2024 Alibaba Cloud |
| Application registry license name | `Apache-2.0` |
| Application registry license status | `APPROVED_FOR_PERSONAL_USE` |
| Selected role | Translation |

The registry update is local application state under the external TransLoka
data root. It is not a hard-coded application default.

## Production full benchmark

| Setting or metric | Result |
| --- | --- |
| Benchmark ID | `mdl_f8ce9518-95b6-4e7e-a8ff-e5f24d1de6a9:production-full-2026-09-03` |
| Dataset | `translation_benchmark_en_id_0.1` |
| Cases / repetitions | 30 / 3 |
| Total attempts | 90 |
| Temperature | 0.1 |
| Batch sizes | 1 and 5 |
| Context lengths | `SHORT`, `MEDIUM`, and `LONG` |
| Status | `COMPLETED` |
| Successful / failed attempts | 90 / 0 |
| Critical failures | 0 |
| Quality score | 1.0 |
| Average latency | 3.95 seconds per attempt |
| Recommendation | `RECOMMENDED_DEFAULT` |
| Ollama version | 0.33.2 |

The domain runner was also executed independently immediately before the
production run. It completed 90/90 attempts with no failure, a quality score of
1.0, and an average latency of 3.85 seconds. This corroborating run used the
same dataset, temperature, batch sizes, and context lengths.

## Fresh quick benchmark

| Metric | Result |
| --- | --- |
| Benchmark ID | `bmk_quick_46bfcbba8a9c48e1b7711288b1e9a28a` |
| Cases | 6 |
| Successful / failed | 6 / 0 |
| Placeholder case | Passed |
| Status / recommendation | `COMPLETED` / `RECOMMENDED_DEFAULT` |
| Average latency | 7.58 seconds |

## Target hardware

| Component | Observed value |
| --- | --- |
| Operating system | Windows 10.0.26200 |
| CPU | AMD Ryzen 5 3550H, 4 physical / 8 logical cores |
| RAM | 15.44 GiB total; 4.84 GiB available at production-run capture |
| Discrete GPU | NVIDIA GeForce GTX 1050, 3 GiB, driver 32.0.15.8180 |
| Integrated GPU | AMD Radeon Vega 8, 0.5 GiB, driver 31.0.21923.1000 |
| Repository drive free space | 28.66 GiB |

The generic hardware detector did not populate GPU fields, but `ollama ps`
reported the model running with 100% GPU placement and a 4096-token context
during the benchmark. No formal peak RAM or VRAM sampling was captured in this
rerun.

## Interpretation and remaining acceptance

The automated quality score covers deterministic benchmark invariants such as
structured output and placeholder preservation. It is not a semantic or
literary-quality score. Before release:

1. complete a human blind review of representative English-to-Indonesian
   translations;
2. record the review samples, rubric, reviewer decision, and any defects;
3. rerun M11-T18 from the current clean locked environment;
4. create the rollback/release tag only if every release gate passes.
