# Temporal Legal Engine — foundation v1

## Purpose

This package adds the storage and evidence boundary required to answer which
version of a Georgian legal provision applied on a particular date.  It does
not infer historical law from the existing `law_amendments` summaries and it
does not switch public answers to unreviewed temporal data.

The existing `documents`, `document_chunks`, `law_amendments`, RAG routes and
public timeline remain backward compatible.  Historical backfill is a separate
reviewed package.  Temporal models are deliberately not registered by the
public runtime's common `models` package, so its startup `create_all()` cannot
replace the pinned installer.

## Invariants

1. Valid time uses half-open intervals: `[valid_from, valid_to)`.
2. System-time corrections are new rows linked by `supersedes_version_id`;
   provision-version rows are never updated in place.
3. There may be only one active head version of a provision on any date.
4. A correction may supersede only the current head of the same provision.
5. Exact official response bytes are addressed by SHA-256.
6. Source blobs, URL/content snapshots, fetch observations, provision versions,
   amendment operations, review events and the migration record reject SQL
   `UPDATE` and `DELETE` through PostgreSQL triggers.
7. Snapshot capture accepts only bounded bytes from the approved official HTTPS
   hosts.  The storage function performs no network request.
8. An official locator is stored separately from the fragment-free URL whose
   bytes were captured.
9. The schema is additive.  Version 1 performs no backfill and changes no public
   answer route.

## Tables

| Table | Role |
|---|---|
| `legal_temporal_schema_migrations` | Installed schema contract and SHA-256 |
| `legal_source_blobs` | Exact immutable bytes keyed by content SHA-256 |
| `legal_source_snapshots` | Immutable official URL/content identity |
| `legal_source_observations` | Append-only evidence of repeated official fetches |
| `legal_acts` | Stable identity of one act independent of editions |
| `legal_act_publications` | Official publication or consolidated edition |
| `legal_provisions` | Stable article/part/point/subpoint identity |
| `legal_provision_versions` | Bitemporal authoritative Georgian provision text |
| `legal_amendment_operations` | Structured add/replace/repeal/etc. operation |
| `legal_review_events` | Append-only machine/expert lifecycle evidence |

The schema deliberately stores the authoritative Georgian text.  RU/EN
translations and their review workflow will be a separate derivative layer;
they must never overwrite the source text.

## Bitemporal correction example

Suppose the system initially records article X as valid from 2020 with no known
end date.  Later evidence shows that edition ended on 2025-01-01:

1. Keep the original row unchanged.
2. Insert a corrected row with the same `valid_from`, `valid_to=2025-01-01` and
   `supersedes_version_id` pointing to the original.
3. Insert the new legal edition with `valid_from=2025-01-01`.

An `as_known_at` query before the correction still sees the original fact.  A
current query sees the two non-overlapping corrected head intervals.

## Snapshot boundary

`legal_temporal.snapshots.prepare_snapshot()` validates the URL, exact bytes,
media type, response metadata and 64 MiB ceiling, then calculates the content
and observation hashes.  `store_prepared_snapshot()` deduplicates:

- identical bytes globally at the blob layer;
- identical URL/content pairs at the snapshot layer;
- identical fetch evidence at the observation layer.

The caller owns the SQL transaction.  A scraper or backfill must fetch the
official source outside this module, prepare it, persist it and commit only
after all related publication/provision facts pass validation.

## Installation and audit

Dry-run makes no database call:

```bash
cd /root/infohub
docker compose run --rm --no-deps backend \
  python scripts/install_legal_temporal_schema.py
docker compose run --rm --no-deps backend \
  python scripts/audit_legal_temporal_schema.py
```

Production apply is executed only by the pinned deployment gate.  The contract
SHA-256 covers the normalized model columns, constraints, indexes, trigger functions and
trigger definitions.  An unreviewed schema change therefore cannot silently
reuse the deployment pin.

The read-only execute audit verifies tables, migration contract, triggers,
referential integrity, blob lengths and bounded payload hashes, valid intervals
and overlapping active heads.  It emits aggregate counts only.

## CI proof

The dedicated disposable PostgreSQL job installs the exact schema and verifies:

- source bytes cannot be updated;
- overlapping provision heads are rejected under an advisory transaction lock;
- one append-only correction may supersede its predecessor;
- a predecessor cannot receive a second successor;
- the post-rollback aggregate audit passes.

Production image builds depend on this job in addition to the existing backend,
frontend and visual gates.

## Controlled backfill package

The next layer is implemented by the dry-run-first exact-source bundle and
atomic importer documented in `docs/TEMPORAL_LEGAL_BACKFILL.md`. It can
materialize official snapshots, stable act/publication identity and
deterministically correlated operations at bulk scale while every operation
remains `needs_review`. It still creates no authoritative provision version and
does not change public answer routing.

## Explicitly deferred

Foundation v1 does not:

- promote unreviewed amendment candidates to authoritative historical text;
- resolve the existing unmatched amendment queue;
- reconstruct a consolidated law;
- parse `as_of_date` from public questions;
- expose temporal tables through a public API;
- treat an LLM summary as an authoritative provision version.

Those actions require a separately bounded backfill contract, official-source
coverage report and expert review workflow.
