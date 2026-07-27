# TransLoka Documentation Index

**Document Name:** `README.md`  
**Document Version:** 0.1  
**Status:** Draft  
**Decision Date:** 2026-07-26

This index is the reading guide and authority map for the TransLoka
documentation set.

## Project Status

TransLoka is a local application for translating English PDF documents into
Bahasa Indonesia while preserving document structure and producing a
translated PDF.

| Field | Current Personal MVP Decision |
| --- | --- |
| Project | TransLoka |
| Stage | Personal MVP |
| Mode | Local-First |
| Users | Single User |
| Primary Platform | Windows |
| Primary Input | PDF |
| Primary Output | Translated PDF |
| Primary Language Pair | English → Bahasa Indonesia |
| Translation Runtime | Ollama Local |
| OCR Runtime | Local OCR |
| Cloud Requirement | None |
| Paid Service Requirement | None |
| Monetization | Deferred |

Authentication, cloud dependencies, public deployment, paid services, and
monetization are outside the current Personal MVP.

## Documentation Authority

When requirements conflict, use this authority order:

1. [`MVP_SCOPE.md`](./MVP_SCOPE.md)
2. [`TECH_STACK_DECISIONS.md`](./TECH_STACK_DECISIONS.md)
3. [`SECURITY.md`](./SECURITY.md)
4. [`DATABASE_SCHEMA.md`](./DATABASE_SCHEMA.md)
5. [`API_CONTRACT.md`](./API_CONTRACT.md)
6. Component-specific specification documents
7. [`IMPLEMENTATION_PLAN.md`](./IMPLEMENTATION_PLAN.md)
8. [`CODEX_TASKS.md`](./CODEX_TASKS.md)
9. The task-specific prompt

Document roles:

- [`PRD.md`](./PRD.md) Version 0.2 defines the active product requirements and
  intent for the Local-First Personal MVP.
- [`ARCHITECTURE.md`](./ARCHITECTURE.md) Version 0.2 defines the active
  Local-First system structure and boundaries.
- [`GLOSSARY_ENGINE.md`](./GLOSSARY_ENGINE.md) Version 0.2 defines terminology
  control, matching, protection, and revision behavior.
- [`MASTER_CODEX_PROMPT.md`](./MASTER_CODEX_PROMPT.md) defines Codex execution
  governance.
- [`CODEX_TASKS.md`](./CODEX_TASKS.md) defines atomic implementation tasks and
  controls task execution.
- A task-specific prompt may narrow work but cannot override a
  higher-authority document.

If two documents conflict at the same authority level, Codex must identify and
report the conflict, then stop before implementing the conflicting behavior.
Codex must not guess.

## Required Reading Before Implementation

Read these documents before every implementation task:

1. [`MASTER_CODEX_PROMPT.md`](./MASTER_CODEX_PROMPT.md)
2. [`MVP_SCOPE.md`](./MVP_SCOPE.md)
3. [`TECH_STACK_DECISIONS.md`](./TECH_STACK_DECISIONS.md)
4. [`SECURITY.md`](./SECURITY.md)
5. [`IMPLEMENTATION_PLAN.md`](./IMPLEMENTATION_PLAN.md)
6. [`CODEX_TASKS.md`](./CODEX_TASKS.md)

Read the following when relevant to the task:

- Product intent: [`PRD.md`](./PRD.md)
- System boundaries: [`ARCHITECTURE.md`](./ARCHITECTURE.md)
- Persistence: [`DATABASE_SCHEMA.md`](./DATABASE_SCHEMA.md)
- HTTP interface: [`API_CONTRACT.md`](./API_CONTRACT.md)
- Verification: [`TEST_PLAN.md`](./TEST_PLAN.md)
- Document representation: [`DOCUMENT_IR.md`](./DOCUMENT_IR.md)
- Translation: [`TRANSLATION_PIPELINE.md`](./TRANSLATION_PIPELINE.md)
- Model selection: [`LOCAL_MODEL_BENCHMARK.md`](./LOCAL_MODEL_BENCHMARK.md)
- PDF reconstruction:
  [`RECONSTRUCTION_ENGINE.md`](./RECONSTRUCTION_ENGINE.md)
- Glossary behavior: [`GLOSSARY_ENGINE.md`](./GLOSSARY_ENGINE.md)

The following grouped tables form the catalog of every current Markdown
document under `docs/`.

## Product and Scope Documents

| Document | Version | Status | Purpose | When to Read | Authority or Role |
| --- | --- | --- | --- | --- | --- |
| [`MVP_SCOPE.md`](./MVP_SCOPE.md) | 0.1 | Draft | Defines the Personal MVP boundary, supported behavior, deferred features, and prohibitions | Before every task and every scope decision | Authority 1; highest implementation scope control |
| [`PRD.md`](./PRD.md) | 0.2 | Draft | Defines active Local-First Personal MVP product requirements, goals, behavior, and non-goals | For product behavior and user intent | Canonical product requirements; supersedes Version 0.1 |

## Architecture and Technical Decisions

| Document | Version | Status | Purpose | When to Read | Authority or Role |
| --- | --- | --- | --- | --- | --- |
| [`TECH_STACK_DECISIONS.md`](./TECH_STACK_DECISIONS.md) | 0.2 | Draft | Defines the active Local-First Personal MVP stack and deployment decisions | Before every technical or dependency decision | Authority 2; active stack decision for the Personal MVP; supersedes its Version 0.1 |
| [`ARCHITECTURE.md`](./ARCHITECTURE.md) | 0.2 | Draft | Defines the active Local-First modular-monolith structure, local worker, components, and system boundaries | For cross-component structure and boundaries | Active architecture for the Personal MVP; supersedes Version 0.1 |

## Domain and Processing Specifications

| Document | Version | Status | Purpose | When to Read | Authority or Role |
| --- | --- | --- | --- | --- | --- |
| [`DOCUMENT_IR.md`](./DOCUMENT_IR.md) | 0.1 | Draft | Defines the intermediate representation for documents, pages, blocks, and segments | For extraction, OCR, translation, QA, and reconstruction work | Component-specific specification |
| [`TRANSLATION_PIPELINE.md`](./TRANSLATION_PIPELINE.md) | 0.1 | Draft | Defines terminology protection, segmentation, translation, validation, and retry behavior | For translation-provider and translation-workflow tasks | Component-specific specification |
| [`GLOSSARY_ENGINE.md`](./GLOSSARY_ENGINE.md) | 0.2 | Draft | Defines deterministic terminology matching, protection, snapshots, conflicts, and revision behavior | For glossary, protected-content, translation, and review tasks | Active component-specific specification |
| [`LOCAL_MODEL_BENCHMARK.md`](./LOCAL_MODEL_BENCHMARK.md) | 0.1 | Draft | Defines local model evaluation, hardware profiling, and selection evidence | For Ollama model selection and benchmarking | Component-specific specification |
| [`RECONSTRUCTION_ENGINE.md`](./RECONSTRUCTION_ENGINE.md) | 0.1 | Draft | Defines PDF layout preservation, reflow, reconstruction, and export validation | For reconstruction and export tasks | Component-specific specification |

## Data, API, Security, and Testing

| Document | Version | Status | Purpose | When to Read | Authority or Role |
| --- | --- | --- | --- | --- | --- |
| [`DATABASE_SCHEMA.md`](./DATABASE_SCHEMA.md) | 0.1 | Draft | Defines the local SQLite schema, persistence invariants, and migration expectations | For models, repositories, migrations, jobs, and backup work | Authority 4 |
| [`API_CONTRACT.md`](./API_CONTRACT.md) | 0.1 | Draft | Defines the local FastAPI interface, request/response contracts, and error behavior | For API, client, and integration tasks | Authority 5 |
| [`SECURITY.md`](./SECURITY.md) | 0.1 | Draft | Defines local-only security, document protection, trust boundaries, and dependency controls | Before every task and every security-sensitive change | Authority 3 |
| [`TEST_PLAN.md`](./TEST_PLAN.md) | 0.1 | Draft | Defines test layers, markers, fixtures, quality gates, and acceptance coverage | For every task that changes behavior | Verification specification |

## Implementation Governance

| Document | Version | Status | Purpose | When to Read | Authority or Role |
| --- | --- | --- | --- | --- | --- |
| [`README.md`](./README.md) | 0.1 | Draft | Indexes the documentation set and explains authority and reading order | At the start of documentation discovery | Navigation guide; does not override governing documents |
| [`MASTER_CODEX_PROMPT.md`](./MASTER_CODEX_PROMPT.md) | 0.1 | Draft | Defines Codex scope, safety, one-task execution, verification, and reporting rules | Before every implementation task | Codex execution governance |
| [`IMPLEMENTATION_PLAN.md`](./IMPLEMENTATION_PLAN.md) | 0.1 | Draft | Defines milestones, delivery order, quality gates, and implementation practices | For milestone planning and task context | Authority 7 |
| [`CODEX_TASKS.md`](./CODEX_TASKS.md) | 0.1 | Draft | Defines atomic task IDs, allowed files, requirements, and acceptance criteria | Before executing any task | Authority 8; task execution control |

Planned governance locations that do not yet exist:

- `ASSUMPTIONS.md` for recorded implementation assumptions.
- `adr/` for approved architecture decision records.

## Task Execution Order

Implementation begins with `M0-T01 — Create Repository Structure`.

Repository history provides evidence that M0-T01 through M0-T06 are complete.
M0-T07 creates this documentation index. After M0-T07 is verified and
accepted, the next planned task is:

`M1-T01 — Bootstrap Next.js Application`

Do not start M1-T01 automatically.

## Version and Supersession Rules

Supported supersession evidence:

- [`TECH_STACK_DECISIONS.md`](./TECH_STACK_DECISIONS.md) Version 0.2 explicitly
  supersedes Version 0.1 and is the active stack decision for the Personal MVP.
- [`PRD.md`](./PRD.md) Version 0.2 explicitly supersedes Version 0.1 and is the
  active product requirements document.
- [`ARCHITECTURE.md`](./ARCHITECTURE.md) Version 0.2 explicitly supersedes
  Version 0.1 and is the active architecture document.
- [`GLOSSARY_ENGINE.md`](./GLOSSARY_ENGINE.md) Version 0.2 is the active
  glossary specification. Its metadata supersedes Version 0.1 if an earlier
  copy exists.

Only one active copy of each governing document should exist. Obsolete copies
must not remain under ambiguous names such as `(1)`, `(2)`, `final-final`, or
`old`. Superseded documents should be moved outside the active `docs/`
directory or clearly marked as superseded.

## Deferred and Prohibited Features

Deferred from the Personal MVP:

- Authentication
- Multi-user support
- Cloud database
- Cloud storage
- Remote AI providers
- Billing
- Subscriptions
- Advertisements
- Desktop installer
- DOCX
- EPUB
- Real-time collaboration
- Text-in-image translation
- Complex table recreation

Prohibited in the current Personal MVP:

- Paid API dependency
- Public network binding
- Automatic cloud upload
- PyMuPDF
- `fitz`
- `pymupdf4llm`
- Source PDF mutation
- Arbitrary shell execution
- Unvalidated model output
- Silent content deletion

See [`MVP_SCOPE.md`](./MVP_SCOPE.md), [`SECURITY.md`](./SECURITY.md), and
[`TECH_STACK_DECISIONS.md`](./TECH_STACK_DECISIONS.md) for the complete rules.

## Documentation Update Rules

Update documentation when a task changes:

- configuration;
- commands;
- API contracts;
- schemas;
- dependencies;
- security behavior;
- workflows;
- limitations.

Implementation must not silently modify governing documentation to justify a
deviation. A requirement change must be reported and reviewed before
implementation.

## Current Implementation Entry Point

Before starting any task:

1. Read [`MASTER_CODEX_PROMPT.md`](./MASTER_CODEX_PROMPT.md).
2. Read the exact task in [`CODEX_TASKS.md`](./CODEX_TASKS.md).
3. Read the task's referenced governing documents.
4. Inspect the repository.
5. Implement one task only.
6. Run the required verification.
7. Return the standard completion report.

Codex must not automatically start the next task.
