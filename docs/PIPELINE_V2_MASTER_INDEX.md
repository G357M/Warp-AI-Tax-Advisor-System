# PIPELINE V2 MASTER INDEX

## Purpose

This file is the entry point for the pipeline v2 project documentation.

It explains:
- what each document is for,
- in which order to read them,
- how to move from design to implementation.

For public-surface smoke operations, also see `PUBLIC_SMOKE_OPERATIONAL.md`.

---

## Document map

### 1. `PIPELINE_V2_BLUEPRINT.md`
Read this first.

This is the architecture document.
It explains:
- why pipeline v1 fails,
- what pipeline v2 is supposed to do,
- the end-to-end module flow,
- rollout principles.

Use it when you need the big picture.

---

### 2. `PIPELINE_V2_DECISION_TABLE.md`
Read this second.

This is the routing rules document.
It explains:
- question classes,
- trigger signals,
- source priorities,
- excluded noise,
- answer shapes.

Use it as the main routing source-of-truth.

---

### 3. `PIPELINE_V2_EXPLAINABILITY_TRACE_SCHEMA.md`
Read this third.

This is the observability and audit document.
It explains:
- what the system should log,
- how to inspect decisions,
- what a full trace looks like,
- how domain experts and developers can review answers.

Use it when implementing debugging, auditability, and trust layers.

---

### 4. `PIPELINE_V2_TODO.md`
Read this fourth.

This is the implementation roadmap.
It explains:
- phases,
- milestones,
- deliverables,
- rollout order,
- practical next steps.

Use it as the execution checklist.

---

### 5. `PUBLIC_SMOKE_OPERATIONAL.md`
Read this when checking production/public behavior.

This is the public smoke workflow note.
It explains:
- why browser-path smoke and API-client smoke must be separated,
- how Cloudflare `1010` should be interpreted,
- which commands are canonical,
- which `make`/script wrappers to use.

Use it for day-to-day operational verification of `tax-advisor.ge`.

---

## Recommended reading order

For strategy:
1. `PIPELINE_V2_BLUEPRINT.md`
2. `PIPELINE_V2_DECISION_TABLE.md`
3. `PIPELINE_V2_EXPLAINABILITY_TRACE_SCHEMA.md`
4. `PIPELINE_V2_TODO.md`

For implementation:
1. `PIPELINE_V2_DECISION_TABLE.md`
2. `PIPELINE_V2_BLUEPRINT.md`
3. `PIPELINE_V2_EXPLAINABILITY_TRACE_SCHEMA.md`
4. `PIPELINE_V2_TODO.md`

For review by domain expert:
1. `PIPELINE_V2_DECISION_TABLE.md`
2. `PIPELINE_V2_BLUEPRINT.md`
3. `PIPELINE_V2_EXPLAINABILITY_TRACE_SCHEMA.md`

For public production checks:
1. `PUBLIC_SMOKE_OPERATIONAL.md`
2. `make smoke-public`
3. `make smoke-public-core`
4. `make smoke-public-multilang`
5. `make smoke-public-multilang-core`
6. `make smoke-public-api`
7. `make smoke-public-both`

---

## Implementation start order

Recommended first coding steps:

1. query parser
2. query classifier
3. candidate schema
4. exact/citation/metadata/BM25/semantic channel interfaces
5. legal reranker
6. explainability trace scaffolding
7. pipeline v2 integration in shadow mode

---

## Current project status

### Completed
- architecture blueprint
- decision table
- implementation roadmap
- explainability trace schema

### Next implementation targets
- create `backend/rag_v2/`
- add parser and classifier scaffolding
- define structured models/interfaces
- prepare pipeline v2 shadow entry point

---

## Success definition

This project is successful when:
- named-document queries resolve directly to the named document,
- canonical law questions are answered primarily from normative sources,
- practical questions are routed to practical guidance first,
- dispute questions route to dispute practice first,
- local questions route to local acts first,
- every answer can be inspected via explainability trace.
