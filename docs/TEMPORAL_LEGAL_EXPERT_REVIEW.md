# Temporal Legal Engine — evidence-pinned expert review v1

## Outcome

The offline review command turns the full backfill queue into small dossiers
grouped by target law and review lane. It includes **every** candidate and one
row for an amendment without candidates. Each row has stable source-bound
identity, both official URLs, exact raw-source SHA-256, frozen normalized text,
article navigation excerpts, proposed date/action and the reasons it is blocked.
The index starts with laws having the most review rows, and within each law
lists technically confirmable candidates first. This is corpus-coverage order,
not a claim about user query popularity; unresolved targets are listed last.

This is a review-preparation and proposal-validation package, not a historical
answer release. There is no database connection, LLM, network fetch or apply
command. It creates no review event, operation or authoritative provision version.
Neither public routing nor the PostgreSQL schema changes.

## Operator workflow

Run inside the backend environment; no database credentials are needed. The
source `bundle` is the existing complete backfill directory, not its CSV file.
The expected SHA is the canonical `manifest_sha256`, not the file's byte hash.
Full-corpus validation also requires the production-pinned Scrapling parser
for legacy Scrapling-repaired sources. Verified normalized text is reused from
the bundle validator, avoiding a second parse of every official response.

```bash
python scripts/review_legal_temporal.py

python scripts/review_legal_temporal.py build \
  --bundle /protected/legal-temporal-backfill/RUN_ID \
  --expected-manifest-sha256 REVIEWED_CANONICAL_MANIFEST_SHA256 \
  --output /protected/legal-temporal-expert-review/NEW_RUN_ID \
  --batch-size 50

python scripts/review_legal_temporal.py validate \
  --bundle /protected/legal-temporal-backfill/RUN_ID \
  --expected-manifest-sha256 REVIEWED_CANONICAL_MANIFEST_SHA256 \
  --reviews /protected/legal-temporal-expert-review/NEW_RUN_ID/batches/BATCH_ID.json \
  --output /protected/legal-temporal-expert-review/NEW_RUN_ID/proposals-v1.json
```

Use `--review-dir .../batches` instead of `--reviews` to validate all generated
`BATCH-*.json` files. Multiple explicit files must contain disjoint row IDs.
Selecting one file or removing unreviewed rows is supported: omitted rows are
reported as `not_submitted_rows`, never inferred to be approved. Two versions
of a row are an error; the operator must explicitly select the intended version.

Outputs are exclusive-create, with directory `0700` / file `0600` permissions
on Linux. Existing output paths are never overwritten. The build validates the
pin and **every raw source** before writing. `index.json` is written last as the
completion marker. An incomplete directory after interruption must be preserved
for investigation or replaced by a new run directory, not silently resumed.
Keep dossiers, reviewer identity and proposals under ignored, protected `.state`;
never commit them or expose the directory through the public web server.

## Expert experience

Open `INDEX.md`, choose a law, then open its `.md` dossier. Follow the archived
full-text link and the official source link. `sources/*.txt` reproduces the frozen
legacy normalization; it is not a new consolidation, and it does not replace the
original API bytes retained in the source bundle. Live source content can differ
from the snapshot, so report differences instead of editing immutable evidence.

There are three lanes, not three degrees of legal certainty:

- `expert_confirmation`: no machine blocker; still needs legal verification.
- `candidate_resolution`: ambiguous/missing article, target, action or date.
- `source_reconciliation`: amendment or target source differs from legacy text.

The expert may supply a row ID, decision, exact quotations, rationale, name and
actual review time to the operator in plain language. They need not hand-edit
JSON. The operator transcribes only what the expert supplied, never fabricates
an approval, identity, date or quotation. The generated `README.md` is in Russian
and specifies each editable `decision` field.

## Validation contract

- Input is UTF-8 JSON (BOM accepted), capped at 32 MiB/file, 128 MiB combined,
  500 batches and 10,000 rows/batch. Symlink files, duplicate JSON keys,
  non-finite JSON numbers, extra fields, unknown IDs and overlapping rows fail.
- The validator regenerates rows from the pinned complete original bundle.
  All immutable evidence must match exactly, including classification, source
  identities, excerpts and checksums. A self-recomputed review hash is not trust.
- `pending` must contain no filled-in decision fields; otherwise the validator
  explains that its state must be set. This avoids silently discarding work.
- `confirm`, `correct`, `reject`, `defer` require a real reviewer, rationale and
  UTC timestamp no earlier than source capture and no more than five minutes
  in the future. The code checks syntax, not the person's identity.
- `confirm` is forbidden for source drift, row issues, missing target/date and
  non-operation candidates. The validator never clears quarantine.
- `confirm` and `correct` require an operative quotation and a commencement
  quotation occurring verbatim in the frozen amendment text. A specific
  provision/subdivision locator is also required. Quote presence alone cannot
  establish that the quotation applies to this provision or supports the date.
- `correct` contains exactly target source ID (from the pinned bundle), canonical
  article, operation type and ISO date. It remains a proposal, including when it
  concerns quarantined data. It cannot rewrite evidence or insert a new law.
- One invalid row suppresses the **entire** proposal export; the command exits
  nonzero. Valid partial results are not accidentally applied.
- Successful output is labelled `non_executable_expert_proposals` and records
  input hashes, omissions, state counts and its canonical proposal hash. A
  `confirm` is an expert assertion, not `expert_verified` in the database.

## Release gates and next boundary

Unit/CLI tests cover deterministic export, complete/empty-candidate coverage,
private file creation, source tampering, all decision states, time/quote checks,
partial batches, overlap rejection, invalid output suppression and import-time
independence from database settings. They run in the mandatory backend CI job;
existing PostgreSQL, RAG, visual and image gates remain unchanged.

The test environment pins AnyIO 4.14.2, the resolution in the last green
`719b358` CI run. Newly resolved 4.15 emits a deprecation through Starlette 1.6's
TestClient during test collection. The strict warnings-as-errors gate is kept;
this test-only compatibility pin does not alter production dependencies.

The separate [review admission command](TEMPORAL_LEGAL_REVIEW_ADMISSION.md) now
provides independently reviewed, hash-pinned import of candidate review events,
with exact transaction ceilings and backup/rollback rehearsal gates. This offline
dossier tool remains non-executable. Corrections and unresolved candidates are
not auto-applied. Next: genuine expert decisions, provision reconstruction,
valid-time coverage and multilingual historical answer canaries. Neither an
unchecked LLM extraction nor successful JSON validation is publication approval.
