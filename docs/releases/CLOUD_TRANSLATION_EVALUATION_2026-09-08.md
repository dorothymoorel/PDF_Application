# CLOUD-04 Groq Translation Evaluation

Status: **EVALUATION COMPLETED WITH LIMITED COVERAGE; NOT APPROVED FOR FULL-BOOK USE**

The evaluation used synthetic text only. Groq accepted the account credential and selected
model, completed six batches, then returned a retryable rate limit on the seventh batch.
The runner stopped without retrying and left the remaining cases unattempted as designed.

## Configuration

- Provider: Groq
- Selected model: `qwen/qwen3.8-27b`
- Dataset: `cloud_translation_en_id_v1` (50 synthetic English-Indonesian cases)
- Batch size: 5
- Automatic retries: disabled
- Credential source: current-process `GROQ_API_KEY`; value is never recorded
- References: AI-authored Indonesian examples, not independently human-validated gold data

## Measured Results

| Metric | Result |
| --- | ---: |
| Metadata model availability | Available |
| Completed cases | 30 of 50 |
| Failed cases | 5 (`RATE_LIMIT`) |
| Unattempted cases | 15 |
| Completion rate | 60% |
| Schema and placeholder validation rate | 60% of full dataset; 100% of completed cases |
| Total and average batch latency | 7.197 s total; 1.028 s average |
| Estimated input tokens | 656 |
| Estimated output tokens | 560 |
| Retryable provider stops | 1 |
| Retry-After value | 5 seconds |

Token counts are deterministic estimates over segment text. They are not provider-billed
usage because the current provider contract does not expose Groq usage metadata.
Input estimates exclude system prompts, glossary/context and response schema. Output
estimates cover successfully parsed segment text only; rejected response usage is unknown.
Each case records the measured latency of its shared batch. Aggregate latency sums each
batch once, and the average is per request, not a measured per-segment latency.

## Offline Verification

- Evaluation tests: 8 passed with fake providers (including malformed responses,
  missing placeholders, missing models/key, rate limits, latency and output preservation).
- Existing Groq adapter tests: 52 passed with mocked transport.
- Scoped Ruff lint and format checks: passed.
- Whole-workspace `uv run mypy .`: passed, 383 source files.
- Scoped registry mypy command: passed with the workspace source path configured below.

The standalone mypy invocation needs the workspace source directory because the editable
package has no `py.typed` marker. This setup checks source without suppressing import errors:

```powershell
$evaluationPreviousPath = $env:MYPYPATH
try {
    $env:MYPYPATH = (Resolve-Path "python/transloka-translation/src").Path
    uv run mypy tests/performance/cloud_translation_evaluation.py
} finally {
    $env:MYPYPATH = $evaluationPreviousPath
}
```

## Live Run Procedure

Configure the account key locally and confirm the model before running the registry command.
Metadata is checked first; an unavailable model stops before translation. Each provider
failure stops the run, records Retry-After when provided and leaves remaining cases
unattempted. There are at most ten translation requests per run, with no automatic retry.
Exit code 1 means incomplete evaluation; exit code 2 means failed preflight/configuration.
The runner does not retry production jobs or claim to test the worker's resume behavior.

The default command writes metrics only. Add `--review` to the same run to display synthetic
source, reference and translation text for manual assessment. Terminal history/transcripts
may retain that display; no review text is written to the evidence JSON. Do not redirect
review output into repository logs. Existing evidence is never overwritten.

The live evidence is recorded in
`docs/releases/evidence/CLOUD_TRANSLATION_EVALUATION_2026-09-08.json`. It contains metrics
and validation results only, without credentials, prompts, references or translations.

## Human Review

AI assessment of the 30 translations displayed during the run found the meaning broadly
preserved in every completed case. All eight glossary cases used their required target
terms, and all seven placeholder cases preserved every placeholder exactly. The first five
long-sentence cases remained coherent and complete.

Two outputs need editorial attention: case `cloud_005` uses an unnatural Indonesian phrase
for a path leading from a village to a river, and case `cloud_024` renders “code” as
“pengkodean” rather than “kode”. These are fluency or word-choice issues, not schema or
placeholder corruption. Formatting-marker, number and instruction-like categories were not
reached, so their semantic quality remains unevaluated. This is an AI assessment based on
the terminal output, not human sign-off. The references are also AI-authored examples.

Automatic validation covers schema and placeholders only. It does not establish preserved
PDF layout; layout remains the reconstruction pipeline's responsibility.

## Decision

The account, credential, model discovery, response schema and placeholder handling work.
CLOUD-04 is closed as a bounded account evaluation with a negative full-book decision:
20 cases did not complete because the free-tier rate limit stopped the run. The model is
suitable only for continued controlled preview testing; do not approve unrestricted or
full-book cloud translation from this result. A later, separately authorized evaluation
must cover the formatting-marker, number and instruction-like cases and confirm application
pacing/retry behavior under the observed five-second Retry-After value.
