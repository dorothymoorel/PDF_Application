# Optional Groq translation: design and implementation handoff

Date: 2026-09-07
Status: CLOUD-02 implemented and verified; user setup/UI integration not started
Repository: F:\PDF_Application

## Intent and authority

The owner requested a free cloud translation engine before continuing PDF
debugging, then authorized the proposed architecture/design step. This document
records a narrow optional Groq integration. It does not claim cloud support is
implemented or supersede the canonical documents by itself.

Before runtime wiring, reconcile MVP_SCOPE section 60, TECH_STACK_DECISIONS
sections 13 and Add Cloud AI Provider, SECURITY sections 6.5 and local-network
rules, MASTER_CODEX_PROMPT cloud restrictions, API_CONTRACT,
TRANSLATION_PIPELINE, IMPLEMENTATION_PLAN and CODEX_TASKS. Register the tasks
below with their exact scopes. The user has already requested this product
direction; another general question about whether cloud is wanted is unnecessary.

Application servers, storage, OCR, PDF reconstruction and export remain local.
The exception permits text inference to the selected Groq endpoint after explicit
document/job consent. Existing prohibitions on automatic uploads and remote
Ollama endpoints remain meaningful and must continue to be tested.

## Findings verified in the repository

- providers/base.py already defines TranslationProvider, cancellation and typed
  provider errors, including RATE_LIMIT and AUTHENTICATION_FAILED.
- providers/ollama.py implements bounded request/response handling and explicitly
  rejects remote URLs. Do not relax that validator to enable Groq.
- services/api/src/transloka_api/routers/translation.py requires an installed,
  selected LocalModelRecord and checks Ollama health even before dispatch.
- services/worker/src/transloka_worker/translation.py validates mdl_ identifiers,
  loads LocalModelRecord, records provider_type=OLLAMA, and constructs the
  provider using ollama_model_name. Changing a URL alone cannot work.
- TranslationOperation and the translation batch/attempt database models already
  accept provider_type/model_id strings. Their model_id is not a local-model FK.
  Preserve local_models semantics; do not invent a locally installed cloud model.
- Production calls TranslationOrchestrator directly. retry.py's separate
  TranslationRetryCoordinator is not the production retry entry point.
- Orchestration currently records provider exceptions as batch failures. Cloud
  quota/auth failures must stop subsequent dispatch rather than fail every
  remaining segment or trigger smaller batches against an exhausted quota.
- Worker progress and database writes use attempt ownership checks. Preserve
  those checks during network waits and on resume.

## Provider and model decision

Use Groq as the initial provider with qwen/qwen3.8-27b as an evaluation candidate.
The official catalog currently marks this model PREVIEW. It is not established
as the best English-Indonesian translator and may be discontinued. An explicit
alternative for comparison is openai/gpt-oss-120b, listed as production by Groq.
Do not automatically switch between them within a translation run.

Model access and actual quotas must be verified with the user's Groq account.
The published free-tier Qwen limits currently include 30 requests/minute,
1,000 requests/day, 8,000 tokens/minute and 200,000 tokens/day. These are reference
limits, not an account guarantee or a book completion estimate. Count prompt,
context, output and retry usage; segment count alone cannot predict duration.

Both candidates are listed for strict structured outputs. Use a provider wire
schema with all fields required and additionalProperties=false, then normalize
into the existing response/parser contract. Schema compliance does not guarantee
correct translation, placeholder preservation or complete content.

Sources checked on the date above:

- https://console.groq.com/docs/models
- https://console.groq.com/docs/model/qwen/qwen3.8-27b
- https://console.groq.com/docs/rate-limits
- https://console.groq.com/docs/structured-outputs
- https://console.groq.com/docs/your-data

## Configuration and data flow

1. Server/worker configuration uses TRANSLOKA_CLOUD_TRANSLATION_ENABLED=false
   by default. Explicit enabling is required before provider discovery or calls.
2. Read GROQ_API_KEY only from the API/worker process environment. Initial setup
   uses a masked local prompt when launching processes; do not place the value
   in CLI arguments, browser storage, SQLite, source files or committed .env.
   Environment configuration is not encrypted secret storage. A persistent key
   UI/Windows Credential Manager integration is a separately scoped follow-up.
3. The backend exposes only configured/available status and allowlisted models.
   Model discovery uses https://api.groq.com/openai/v1/models; inference uses
   https://api.groq.com/openai/v1/chat/completions. Reject redirects, arbitrary
   endpoints and environment proxies. Verify TLS normally.
4. The translation setup displays Local (Ollama) and Cloud (Groq), model name,
   preview status, selected document/page scope and a text-sharing explanation.
   Require cloud_consent=true for each new cloud job. Old requests default to
   OLLAMA and false consent. Reject contradictory provider/model selections.
5. The cloud request includes only selected segment text, IDs, needed context,
   language/style instructions and relevant glossary/placeholder data. Context
   and glossary are also disclosed text; masking placeholders is not anonymization.
   Do not transmit PDF files, images, absolute paths, full IR or job logs.
6. Snapshot provider_type, cloud model name, document scope, consent version and
   generation settings in the durable job payload. Never include a key. Retries
   use that snapshot, not a newly changed UI model selection. Check cloud-enable
   configuration again before sending each request so revocation stops new calls.
7. Normalize responses into existing parsing, glossary/placeholder validation,
   review protection and checkpoint persistence. Cloud replaces inference only;
   layout fidelity is still the reconstruction engine's responsibility.

Use the existing stdlib HTTP approach for the first adapter; no provider SDK is
needed. Bound request and response bodies to 1 MiB, connection/read time and total
request duration. Use a cancellation-aware async wrapper; timed-out background
network work must not be allowed to persist a result after loss of ownership.

Proposed request extension: provider_type=OLLAMA|GROQ (default OLLAMA), existing
model_id reserved for local mdl_ IDs, cloud_model_name required only for GROQ,
cloud_consent default false. For cloud, model_id may be null. A versioned v2
worker command retains v1 decoding as OLLAMA. Existing queued local jobs remain
executable. API/client request types and generated schema change together.

## Quota and failure behavior

Start with one in-flight cloud request and conservative token-aware batch sizing.
Use response usage and rate-limit headers to pace subsequent requests. Never
rotate accounts/keys to evade quotas. Do not infer free account status solely
from a model ID: paid accounts can charge for the same API. Setup must identify
the account tier; if free status is unverified, display that fact and perform no
automatic paid fallback or billing upgrade.

Transient 429/network/5xx: at most three total network attempts per batch, with
cancellable bounded backoff, honoring Retry-After within the allowed wait budget.
Do not run a second nested content retry policy over the same transport failure.
If the required wait exceeds the budget, stop and preserve the retry timestamp.
401/403, removed model, daily quota exhaustion and invalid configuration: stop
dispatch immediately; provide a sanitized actionable error code.

Initial resume behavior deliberately uses existing FAILED + error_code and the
existing explicit retry action. Do not invent a PAUSED job enum or keep a worker
sleeping overnight. Describe recoverable quota failures in the UI as a quota
stop, while preserving the actual backend state. Persist any known retry time in
existing JSON metadata and expose it in an optional response field.

On resume, skip durably completed/approved/locked segments, keep failed and
unattempted segments distinguishable, and dispatch only eligible work. UI must
allow resume even when quota stopped the job with zero content-failed segments.
Continue to fence writes with the current attempt token. Atomic DB persistence
prevents duplicate accepted results, but an uncertain network timeout can still
consume provider quota twice; do not promise exactly-once external inference.

Provider outages, credentials and quota errors are operational failures, not
content quality warnings. Manual review applies to actual translation validation
failures. Raw provider errors, prompts, responses and authorization headers must
not be included in API errors or logs.

## Ordered implementation scopes

CLOUD-01 and CLOUD-02 are registered in CODEX_TASKS.md and implemented. CLOUD-03..04
remain proposed follow-up labels. Execute one registered task at a time.

### CLOUD-01: governance and Groq adapter

Allowed documentation paths:

```text
docs/MVP_SCOPE.md
docs/TECH_STACK_DECISIONS.md
docs/SECURITY.md
docs/MASTER_CODEX_PROMPT.md
docs/API_CONTRACT.md
docs/TRANSLATION_PIPELINE.md
docs/IMPLEMENTATION_PLAN.md
docs/CODEX_TASKS.md
docs/releases/CLOUD_TRANSLATION_DESIGN_2026-09-07.md
```

Allowed implementation/test paths:

```text
python/transloka-translation/src/transloka_translation/providers/groq.py
python/transloka-translation/src/transloka_translation/providers/base.py
tests/unit/translation/providers/test_groq.py
tests/unit/translation/providers/test_contract.py
```

The new adapter implements the existing protocol and returns raw normalized JSON
for the current parser. Keep LocalModel as the existing protocol return type for
compatibility (size_bytes=None for cloud); it does not create LocalModelRecord.
Optional retry metadata on TranslationProviderError must default compatibly.

Acceptance: no calls when disabled/missing consent at runtime boundary; adapter
requires explicit enabled configuration; exact endpoint and bounded I/O; safe
error mapping; cancellation; schema/finish-reason checks; no secret/content logs;
mocked tests covering 200, invalid JSON, truncation, 401/403/429/5xx, redirects,
oversize bodies and timeout. No live user document is needed for this phase.

### CLOUD-02: API/worker persistence and resume

Dependency: CLOUD-01. Allowed additional paths:

```text
services/api/src/transloka_api/routers/translation.py
services/worker/src/transloka_worker/translation.py
python/transloka-translation/src/transloka_translation/orchestration/models.py
python/transloka-translation/src/transloka_translation/orchestration/service.py
python/transloka-translation/src/transloka_translation/orchestration/persistence.py
tests/integration/api/test_translation.py
tests/integration/worker/test_translation_runtime.py
tests/integration/translation/test_orchestration.py
tests/e2e/runtime/test_translation_worker_runtime.py
packages/api-client/src/generated/schema.ts
```

Acceptance: local v1 command compatibility; provider-aware readiness; durable
v2 snapshot and consent; no fabricated local model; provider-wide failure stops
remaining calls; retry respects stored successes and user review; cancelled or
stale worker cannot publish; persisted provider/model correct. Confirm every
existing model-ID consumer before implementation. If a new FK/schema constraint
is discovered, update this scope rather than fabricating local rows.

### CLOUD-03: user setup and generated client

Dependency: CLOUD-02. Allowed additional paths:

```text
apps/web/src/features/translation/types.ts
apps/web/src/features/translation/translation-settings.tsx
apps/web/src/features/translation/translation-settings.test.tsx
apps/web/src/features/translation/translation-progress.tsx
apps/web/src/features/translation/translation-progress.test.tsx
apps/web/features/workspace/project-workspace.tsx
packages/api-client/src/client.ts
packages/api-client/src/generated/schema.ts
packages/api-client/tests/client.test.ts
```

The workspace caller and API-client test paths above were resolved from current
imports and the file inventory. Acceptance: local default, cloud disclosure and
explicit selection, no key field, preview marker, truthful quota/retry UI, no
automatic provider change and passing generated-client drift check.

### CLOUD-04: account smoke and translation evaluation

Dependencies: CLOUD-01..03. Requires the user to configure their own free Groq
account/API key locally. Verify model availability using metadata first. Evaluate
50 synthetic/public-domain English segments with Indonesian references, including
glossary terms, placeholders, long sentences and formatting markers. Record
completion/validation rates, latency, tokens, retry behavior and human-review
limitations. Do not upload the user's book merely to test connectivity. A real
document trial follows its in-app consent and selected scope.

## Verification commands for the runtime implementation

```powershell
uv run ruff check .
uv run ruff format --check .
uv run mypy .
uv run pytest tests/unit/translation/providers tests/unit/translation/schemas tests/unit/translation/parsing -q
uv run pytest tests/integration/ollama tests/integration/translation tests/integration/api/test_translation.py tests/integration/worker/test_translation_runtime.py tests/e2e/runtime/test_translation_worker_runtime.py -q
uv run pytest -m "not slow and not requires_ollama and not requires_gpu" -q
pnpm --filter @transloka/api-client generate
pnpm --filter @transloka/api-client check-generated
pnpm lint
pnpm typecheck
pnpm test
pnpm build
pnpm audit --audit-level high
git diff --check
git status --porcelain
```

The initial design-only step was checked against current code, schemas and
official provider documentation. Its runtime checks were not run at that stage.

## CLOUD-01 implementation evidence - 2026-09-07

Completed the isolated Groq adapter, optional retry_after_seconds metadata on
TranslationProviderError, 52 mocked adapter cases, and the approved cloud
exception/registry addenda in the eight governing documents above. Existing
dirty translation/reconstruction changes were preserved. No dependencies changed.

The adapter reads GROQ_API_KEY only at request time, sends no request when
disabled or when translation consent is absent, filters discovery to the two
reviewed model candidates, and uses the existing strict TranslationResponse
schema. Qwen uses reasoning_effort=none; GPT-OSS uses low. The adapter rejects
non-stop completions, refusals, unknown/missing/duplicate segment IDs, malformed
JSON and oversize bodies. It performs one transport attempt and returns retry
metadata; production retry/pacing is CLOUD-02 work.

Cancellation/timeout ends the awaitable and discards late results. Stdlib blocking
network work already running in a background thread may continue until its
socket timeout (and OS DNS resolution is not forcibly interruptible). The thread
checks cancellation/deadline between reads and closes the response on exit.
This is a logical total deadline, not a promise of instant network termination;
asyncio.run executor shutdown can wait for that thread. CLOUD-02 must retain
attempt fencing and assess cancellation latency when wiring the worker.

Verification:

- `uv run pytest tests/unit/translation/providers/test_groq.py -q`: 52 passed.
- `uv run pytest tests/unit/translation/providers tests/unit/translation/schemas tests/unit/translation/parsing tests/unit/translation/prompts tests/integration/ollama -q`:
  189 passed in 39.91 seconds.
- `uv run ruff check .`: passed.
- `uv run ruff format --check .`: passed, 367 files.
- `uv run mypy .`: passed, 381 source files.
- `git diff --check`: passed, LF/CRLF notices only; new files separately checked.

The first oversized-body test used its full body as a pytest parameter ID and
hit the Windows fixture-name limit; explicit short IDs corrected the fixture.
No adapter assertion was weakened. All final tests above passed.

The full application and Node suites were not rerun for the isolated adapter;
the phase-appropriate provider and Ollama regression checks above passed. No
account/API-key access, real Groq inference, service restart, stage or commit
occurred. Groq is not selectable in the application UI yet; CLOUD-02 followed.

## CLOUD-02 implementation evidence - 2026-09-08

The API now accepts an explicit OLLAMA or GROQ selection, rejects contradictory
local/cloud fields, and requires both the process opt-in and per-job cloud consent.
The versioned v2 worker command snapshots provider, model, consent version and
generation settings without storing GROQ_API_KEY. Queued v1 local commands continue
to decode as OLLAMA, and cloud models are not represented as LocalModelRecord rows.

The worker constructs the provider from the durable snapshot, rechecks the cloud
enable flag before every inference call, and persists the actual provider/model in
translation batches and attempts. Transient transport errors receive no more than
three total calls per batch with cancellable bounded backoff. Provider-wide failures
stop further batches, preserve Retry-After metadata, report remaining segments as
unattempted rather than content failures, and restore their pre-run status.

Explicit retry creates a new durable translation run keyed by retry count. Its loader
skips completed, approved, edited and locked segments, while keeping unfinished work
eligible. The existing application-job attempt token remains the write guard; the
pre-created retry attempt is atomically claimed instead of bypassed or duplicated.

Verification:

- focused API/worker/orchestration/runtime E2E suite: 123 passed in 151.95 seconds
  on the final code;
- additional focused cloud checks: 6 API, 3 worker, 12 orchestration and 2 E2E passed;
- `uv run ruff check .`: passed;
- `uv run ruff format --check .`: passed, 367 files;
- `uv run mypy .`: passed, 381 source files;
- monorepo TypeScript check: passed;
- Node tests: 113 web and 45 API-client tests passed;
- production web build: passed;
- dependency audit at high severity: no known vulnerabilities;
- generated schema check: current;
- `git diff --check`: passed with line-ending notices only.

No live Groq request, credential entry, dependency change, migration, service restart,
stage or commit occurred. CLOUD-03 is the next proposed scope and must be registered
before adding the provider selector, consent disclosure and quota-stop UI.

The first generated schema made defaulted provider fields required in TypeScript.
The final API contract keeps those additions optional for existing clients while
normalizing omitted values to OLLAMA and false consent inside the backend. This
removed the frontend type regression without moving CLOUD-03 UI work into this task.
