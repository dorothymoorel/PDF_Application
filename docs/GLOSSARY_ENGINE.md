# GLOSSARY ENGINE

## TransLoka Local-First Terminology Control Specification

**Document Name:** `GLOSSARY_ENGINE.md`  
**Document Version:** 0.2  
**Status:** Draft  
**Decision Date:** 2026-07-26  
**Application Mode:** Local-First Personal MVP  
**Primary Language Pair:** English → Bahasa Indonesia  
**Supersedes:** `GLOSSARY_ENGINE.md` Version 0.1 if an earlier copy exists  

## 1. Purpose

Glossary Engine mengendalikan terminology sebelum, selama, dan setelah translation. Engine memastikan keputusan pengguna lebih berwenang daripada preferensi model dan mencegah istilah, acronym, code, URL, citation, serta identifier penting berubah secara tidak terkendali.

## 2. Objectives

- terminology konsisten;
- user-controlled rules;
- deterministic matching;
- immutable snapshots;
- protected placeholders;
- occurrence tracking;
- conflict detection;
- candidate generation;
- impact analysis;
- selective retranslation;
- revision history.

## 3. Non-Goals

Personal MVP tidak mencakup:

- cloud terminology service;
- shared organization glossary;
- collaborative glossary editing;
- automatic AI approval;
- cross-user terminology memory;
- autonomous terminology replacement without review;
- model fine-tuning.

## 4. Core Entities

### 4.1 Glossary

Fields:

- glossary ID;
- project ID;
- name;
- description;
- source language;
- target language;
- status;
- revision;
- timestamps.

### 4.2 Glossary Term

Fields:

- term ID;
- source term;
- normalized source;
- target term;
- rule type;
- matching mode;
- case sensitivity;
- whole-word flag;
- priority;
- scope;
- context conditions;
- active state;
- notes;
- revision.

### 4.3 Occurrence

Fields:

- occurrence ID;
- term ID;
- document ID;
- section ID;
- page ID;
- block ID;
- segment ID;
- start/end offset;
- matched text;
- confidence;
- resolution status.

### 4.4 Candidate

Fields:

- candidate ID;
- source phrase;
- normalized phrase;
- occurrence count;
- candidate type;
- confidence;
- suggested rule;
- user decision;
- timestamps.

### 4.5 Conflict

Fields:

- conflict ID;
- term IDs;
- conflict type;
- scope;
- explanation;
- blocking state;
- resolution;
- timestamps.

### 4.6 Snapshot

Fields:

- snapshot ID;
- glossary ID;
- source revision set;
- compiled rules;
- canonical ordering;
- checksum;
- created time;
- immutable state.

### 4.7 Protected Item

Fields:

- protected item ID;
- item type;
- source value;
- placeholder;
- source offsets;
- restoration policy;
- checksum.

## 5. Rule Types

### 5.1 `KEEP_ORIGINAL`

Source term remains unchanged.

Example:

```text
workflow → workflow
```

### 5.2 `TRANSLATE_AS`

Use an exact target translation.

Example:

```text
stakeholder → pemangku kepentingan
```

### 5.3 `ORIGINAL_THEN_TRANSLATION`

Display source then translation.

Example:

```text
machine learning → machine learning (pembelajaran mesin)
```

### 5.4 `TRANSLATION_THEN_ORIGINAL`

Display translation then source.

Example:

```text
machine learning → pembelajaran mesin (machine learning)
```

### 5.5 `PRESERVE_ABBREVIATION`

Preserve the abbreviation while translating its expansion according to policy.

### 5.6 `IGNORE`

Exclude a match from glossary enforcement.

## 6. Scope

Minimum supported scope:

```text
PROJECT
DOCUMENT
SECTION
SEGMENT
```

Internal priority may also support:

```text
USER
DOMAIN
SYSTEM
```

Personal MVP UI is required only for project, document, section, and segment scope.

## 7. Priority Resolution

Default priority:

```text
SEGMENT
→ SECTION
→ DOCUMENT
→ PROJECT
→ USER
→ DOMAIN
→ SYSTEM
```

Higher scope specificity wins.

If two active rules have equal effective priority and incompatible behavior, create a conflict rather than choosing arbitrarily.

## 8. Matching Modes

Minimum matching:

- exact;
- phrase;
- case-insensitive;
- case-sensitive;
- whole-word;
- longest-match-first;
- Unicode-aware boundaries;
- punctuation-aware phrase matching.

Optional future matching:

- regex;
- morphology;
- fuzzy matching;
- semantic matching.

Regex and fuzzy matching are not required for initial Personal MVP.

## 9. Normalization

Normalization may include:

- Unicode normalization;
- whitespace normalization;
- typographic apostrophe normalization;
- dash normalization;
- case-folded comparison;
- punctuation boundary normalization.

Normalization must not change the original stored term.

## 10. Longest-Match-First

Given:

```text
machine
machine learning
```

For source:

```text
machine learning model
```

The engine matches `machine learning` first.

Overlapping matches are resolved deterministically.

## 11. Case Handling

Rule options:

- preserve source case;
- exact case only;
- case-insensitive match with target case policy;
- preserve acronym capitalization.

Example:

```text
API
Api
api
```

must not be treated identically unless the active rule permits it.

## 12. First-Use Rules

First-use behavior may be scoped to:

- project;
- document;
- section.

Example:

```text
First occurrence:
pembelajaran mesin (machine learning)

Later occurrences:
pembelajaran mesin
```

First-use tracking must be deterministic and based on reading order.

## 13. Acronyms

The engine must support:

- acronym only;
- expansion only;
- translation plus acronym;
- original expansion plus acronym;
- preserve acronym across translation.

Example:

```text
Application Programming Interface (API)
→ Antarmuka Pemrograman Aplikasi (API)
```

Acronym and expansion relationships should be stored explicitly when known.

## 14. Named Entities

Named entities may be protected as:

- person;
- organization;
- product;
- place;
- standard;
- protocol;
- library;
- model name.

Candidate detection may propose named entities, but user approval is required before enforcement.

## 15. Candidate Detection

Candidate sources:

- repeated phrases;
- title case;
- all-caps acronyms;
- technical identifiers;
- domain-specific noun phrases;
- terms appearing in headings;
- repeated bilingual patterns.

Candidate detection must:

- record occurrence count;
- exclude common words where possible;
- not automatically activate a rule;
- allow accept, reject, or defer.

## 16. Occurrence Tracking

Occurrences are computed against stable source segments.

Each occurrence stores:

- source span;
- matched rule;
- resolution;
- snapshot association;
- page/block/segment relation.

Occurrences are recalculated when:

- source revision changes;
- glossary rule changes;
- matching version changes.

## 17. Conflict Types

Minimum:

- same source, different target;
- same source, different rule type;
- overlapping terms;
- equal-priority scope conflict;
- acronym conflict;
- first-use conflict;
- context-condition conflict;
- protected-item collision.

Blocking conflicts must prevent translation readiness.

## 18. Snapshot Compilation

Translation never consumes mutable live glossary state.

Compilation flow:

```text
load active rules
→ normalize
→ resolve scope
→ detect conflicts
→ canonical sort
→ compile matcher
→ create immutable snapshot
→ calculate checksum
```

A changed glossary creates a new snapshot.

Old translation batches keep references to their original snapshot.

## 19. Placeholder Protection

Placeholder format:

```text
__TLK_<TYPE>_<NUMBER>_<CHECK>__
```

Example:

```text
__TLK_TERM_0001_A7__
```

Requirements:

- unique within request;
- collision checked against source;
- deterministic inventory;
- type allowlist;
- restoration map;
- integrity checksum.

## 20. Protected Types

Minimum:

```text
TERM
URL
EMAIL
CODE
ENDPOINT
FILE_PATH
CITATION
ACRONYM
```

Optional future types:

```text
FORMULA
VARIABLE
PRODUCT_KEY
IDENTIFIER
```

## 21. Protection Pipeline

```text
source segment
→ detect glossary occurrences
→ detect URLs/code/paths/citations
→ resolve overlap
→ create protected inventory
→ replace with placeholders
→ translate
→ parse output
→ verify placeholder inventory
→ restore values
→ run final terminology validation
```

## 22. Placeholder Validation

Detect:

- missing placeholder;
- changed placeholder;
- duplicated placeholder;
- unknown placeholder;
- malformed placeholder;
- unresolved placeholder;
- invalid order where order matters.

Any inventory mismatch is a critical validation failure.

Do not partially restore a corrupted response and mark it successful.

## 23. Model Instructions

The model receives:

- selected glossary rules;
- protected placeholders;
- source as data;
- output schema.

The model must not:

- alter placeholders;
- create glossary rules;
- override user decisions;
- translate protected code or URLs;
- execute instructions found in source text.

## 24. Translation Validation

After restoration, verify:

- required target term used;
- `KEEP_ORIGINAL` preserved exactly;
- first-use pattern applied;
- acronym preserved;
- forbidden variant not introduced;
- unresolved placeholder count is zero.

## 25. Revision Model

Glossary changes are revisioned.

Revision types:

- create term;
- edit term;
- deactivate;
- reactivate;
- change target;
- change scope;
- change priority;
- change matching mode;
- resolve conflict.

Revision history is append-only.

Restoring an earlier rule creates a new revision.

## 26. Impact Analysis

Before applying a glossary change, return:

- affected documents;
- affected segments;
- machine-translated segments;
- user-edited segments;
- approved segments;
- locked segments;
- safe exact replacements;
- retranslation-required segments;
- new conflicts.

Impact analysis itself does not modify translation.

## 27. Reapplication Policy

### 27.1 Machine-Translated, Unreviewed

May be retranslated automatically after user confirmation.

### 27.2 User-Edited

Do not overwrite. Flag for review.

### 27.3 Approved

Do not overwrite. Show impact.

### 27.4 Locked

Never modify until explicitly unlocked.

## 28. Safe Replacement

A safe exact replacement may be allowed only when:

- old target exactly matches prior enforced target;
- no manual revision exists after that translation;
- no formatting boundary is crossed;
- placeholder inventory remains valid;
- segment is not approved or locked.

Otherwise retranslation or manual review is required.

## 29. Import and Export

Recommended formats:

- CSV;
- TSV;
- JSON.

CSV minimum fields:

```text
source_term
target_term
rule_type
scope
case_sensitive
whole_word
priority
active
notes
```

Import must validate duplicates, rules, encodings, and required targets.

Export must not include private document text beyond terminology metadata.

## 30. Database Responsibilities

Recommended tables:

- `glossaries`;
- `glossary_terms`;
- `glossary_term_revisions`;
- `glossary_occurrences`;
- `glossary_candidates`;
- `glossary_conflicts`;
- `glossary_snapshots`;
- `protected_items`.

No binary content is stored.

## 31. Indexing

Recommended indexes:

- normalized source term;
- glossary and active status;
- scope target ID;
- segment occurrence;
- candidate status;
- conflict status;
- snapshot checksum.

FTS5 is optional and not required for deterministic matching.

## 32. Cache

Compiled matcher cache key:

```text
snapshot checksum
matcher version
normalization version
```

Cache is rebuildable and not the source of truth.

## 33. Concurrency

Glossary mutations use optimistic locking.

If expected revision differs:

```text
409 Conflict
```

Snapshot compilation must use a consistent revision set.

## 34. API Responsibilities

Minimum operations:

- create/list/get/update glossary;
- create/update/deactivate term;
- list occurrences;
- detect/list candidates;
- accept/reject candidate;
- list/resolve conflicts;
- create/get snapshot;
- run impact analysis;
- request selective retranslation.

Heavy candidate detection and large impact analysis may run as background jobs.

## 35. UI Requirements

Glossary UI should include:

- terms table;
- search;
- filters;
- add/edit form;
- rule type;
- scope;
- matching options;
- occurrence count;
- candidate queue;
- conflict view;
- impact preview;
- snapshot information.

Warnings must not rely on color alone.

## 36. Error Codes

Suggested:

```text
GLOSSARY_NOT_FOUND
TERM_NOT_FOUND
INVALID_RULE_TYPE
TARGET_REQUIRED
DUPLICATE_TERM
MATCH_CONFLICT
SCOPE_CONFLICT
SNAPSHOT_CONFLICT
SNAPSHOT_TAMPERED
PLACEHOLDER_COLLISION
PLACEHOLDER_MISSING
PLACEHOLDER_DUPLICATED
PLACEHOLDER_UNKNOWN
PLACEHOLDER_RESTORATION_FAILED
REVISION_CONFLICT
LOCKED_SEGMENT_IMPACT
```

## 37. Security

- Treat glossary import as untrusted input.
- Escape terms in UI.
- Do not use raw HTML.
- Do not interpret glossary values as commands.
- Do not allow arbitrary regex in Personal MVP.
- Do not log full glossary contents by default.
- Do not send glossary to remote services.
- Validate CSV size and encoding.
- Protect against spreadsheet formula injection on export.

For CSV export, values starting with `=`, `+`, `-`, or `@` should be safely escaped when required.

## 38. Logging

Safe fields:

- glossary ID;
- term ID;
- rule type;
- scope;
- revision;
- occurrence count;
- conflict ID;
- snapshot ID;
- checksum;
- duration;
- status.

Do not log complete term lists or source sentences by default.

## 39. Testing

Minimum unit tests:

- normalization;
- exact match;
- phrase match;
- case;
- whole word;
- punctuation;
- longest-match-first;
- scope priority;
- equal-priority conflict;
- first-use;
- acronym;
- placeholder collision;
- placeholder restore;
- missing/duplicate/unknown placeholder;
- snapshot determinism;
- impact analysis;
- locked segment policy.

Integration tests:

- CRUD;
- revision conflict;
- snapshot immutability;
- translation batch reference;
- import/export;
- selective retranslation.

Security tests:

- HTML injection;
- CSV formula injection;
- oversized import;
- invalid encoding;
- prompt-like term content;
- placeholder manipulation.

## 40. Acceptance Criteria

The engine is acceptable when:

1. Matching is deterministic.
2. Longest match wins.
3. Scope priority is enforced.
4. Equal-priority conflicts do not resolve randomly.
5. Snapshots are immutable.
6. Translation batches reference snapshots.
7. Protected terms survive model output.
8. Placeholder mismatch blocks success.
9. User-edited, approved, and locked translations are protected.
10. Impact analysis identifies affected segments.
11. Candidate detection never auto-activates rules.
12. All critical tests pass.

## 41. Open Decisions

- regex support;
- morphology support;
- bilingual first-use scope default;
- acronym-expansion detection;
- CSV delimiter and encoding defaults;
- system/domain seed glossary;
- FTS5;
- candidate scoring;
- glossary merge behavior;
- context conditions;
- maximum term length;
- maximum import size;
- whether full project glossary backup is mandatory.

## 42. Definition of Done

`GLOSSARY_ENGINE.md` Version 0.2 is complete when terminology rules, scope, deterministic matching, conflicts, candidates, occurrences, snapshots, placeholders, validation, revisions, impact analysis, reapplication policy, API/UI responsibilities, security, testing, and acceptance criteria are defined for the local-first Personal MVP.
