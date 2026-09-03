# Temporal review admission v1

## Scope and trust boundary

This is the controlled importer following the offline expert dossiers. It admits
**independently reviewed decisions about existing operation candidates** into
`legal_review_events`. It does not reconstruct or publish historical law.

- Only explicit `confirm` / `reject` of unblocked operation candidates is supported.
  `correct`, `defer`, source drift and unresolved targets remain in expert review.
  Select a disjoint review file containing the intended subset; unsupported rows
  are never silently skipped. All-pending input cannot create an admission.
- A second, distinct reviewer must agree with every exact decision/evidence row.
  Names, rationales and actual UTC review times must be supplied by the reviewers.
  The tool checks syntax and normalized name inequality, **not human identity**.
  Hash pins bind operator-selected evidence; they are not digital signatures.
- `expert_verified` is an event on an **amendment operation**, not on a provision
  version. Original `needs_expert_review` extraction payloads stay immutable.
  Consumers must consider lifecycle events, not rewrite the extraction payload.
- No source/operation/version updates or deletes, no new operations or versions,
  no `published` event, no public routing, schema, infrastructure or LLM changes.

## Files and commands

Use the backend Python environment. Files with reviewer identities and legal
quotations belong in protected, ignored `.state`, never Git or a public directory.
Outputs are exclusive-create `0600` on Linux and cannot be inside the source bundle.

`python scripts/admit_legal_temporal_review.py` prints an offline safety plan.
All subsequent commands require these same inputs:

```text
--bundle ORIGINAL_COMPLETE_BACKFILL_DIRECTORY
--expected-manifest-sha256 CANONICAL_MANIFEST_SHA256
--reviews SELECTED_ORIGINAL_REVIEW_BATCH.json [OTHER_DISJOINT_BATCH.json ...]
--expected-proposal-sha256 CANONICAL_PROPOSAL_SHA256
```

The proposal SHA comes from `review_legal_temporal.py validate` for exactly those
files. A saved proposals JSON alone is **not** accepted: the importer revalidates
all original source bytes and regenerates the immutable evidence again.

1. Run `template` with the common arguments and `--output NEW_SECOND_REVIEW.json`.
   It creates only blank/pending independent decisions. For each row the second
   expert fills `state: agree`, `reviewer`, `reviewed_at_utc`, `rationale`, leaving
   `row_id` and `row_sha256` unchanged. A disagreement stops the admission; resolve
   it in a new version of the primary review before obtaining a new second review.
2. Run `validate` with common arguments plus `--independent-review FILE` and
   `--expected-independent-review-sha256 RAW_FILE_SHA256`. This is offline and
   emits the canonical `admission_sha256`, exact event count, and no legal text.
3. Run `preflight` with the same arguments against production. This is a genuine
   PostgreSQL repeatable-read, read-only transaction. Optional `--output NEW.json`
   retains its scope hash and aggregate counts. It does not need a backup because
   it cannot insert even accidentally.

Do not replace the symbolic arguments above with invented values. On Linux use
`sha256sum FILE` for raw-file pins; on PowerShell use `Get-FileHash -Algorithm SHA256`.
Canonical manifest/proposal/admission hashes are different from file byte hashes.

## Recovery and application gate

Before the first real import:

1. Take a fresh complete database backup and hash its actual bytes. Run the existing
   `scripts/test_database_restore.sh` isolated restore drill with that exact pin.
   Retain its successful schema-v2 evidence and hash the evidence file. Both backup
   creation and restore completion must be within 24 hours when applying.
2. Using the same backup, provision a separately authorized isolated restored DB for
   the rehearsal. The existing drill removes its own disposable container; this
   importer does not create containers, expose ports, extract credentials or change
   database settings. Configure the restored copy through the normal `DATABASE_URL`
   of a dedicated process. Never point the rehearsal at production.
3. Run `rehearse` with the common/independent arguments, `--isolated-restore`,
   `--expected-admission-sha256 PIN`, `--max-events EXACT_COUNT`, and:

   ```text
   --backup ACTUAL_DUMP_FILE
   --expected-backup-sha256 RAW_DUMP_SHA256
   --restore-evidence SUCCESSFUL_RESTORE_DRILL.json
   --expected-restore-evidence-sha256 RAW_RESTORE_EVIDENCE_SHA256
   --output NEW_ROLLBACK_PROOF.json
   ```

   The command inserts the real candidate-review events inside one transaction,
   rechecks them, rolls back, then verifies that the original scope is unchanged.
   A pre-import restored copy is required; an already-imported copy is rejected.
   The proof binds the admission, dump, restore receipt, scope and exact event count.
4. Only after operator review, run `apply` in the production backend environment
   with the same pinned inputs/recovery files and exact count, plus
   `--rollback-proof FILE --expected-rollback-proof-sha256 RAW_PROOF_SHA256`.
   A fresh proof and matching production pre-state are mandatory. Do not use
   `--output` for apply: the durable receipt is the database event itself, and a
   post-commit filesystem failure must not be mistaken for a database rollback.

Recovery receipts are trusted operator evidence, not cryptographic attestation
that a restore actually ran. The importer verifies the actual backup bytes and
requires the restored temporal entities/evidence/history to match production;
operators remain responsible for provenance of the isolated restored database.
An old successful restore or a Hetzner snapshot alone does not satisfy this gate.

## Atomicity, lineage and conflicts

The transaction covers at most 100 events with an exact count (not a loose maximum).
It checks the installed schema pin, candidate fingerprint uniqueness, source blobs
and SHA-256, both publication anchors and reviewed observations, normalized source
text, target act/article, operation type/date, pending machine history and absence
of existing provision versions or superseding operations.

Metadata-only API observations are supported without replacing the first
publication anchor: both old and reviewed raw blobs are independently verified,
and the frozen normalized text must be exactly equal. A hash or URL match alone,
or mere whitespace equivalence between the two snapshots, is insufficient.

Advisory and table locks serialize competing writers; lock wait is capped at 5s,
each SQL statement at 30s and the checked transaction budget at 120s. Any lineage,
scope, count or lifecycle conflict aborts the entire transaction. Under load,
retry a smaller explicitly reviewed packet after a new rehearsal; do not raise
limits to force an import through.

Each operation has one deterministic admission-event ID. Repeating the identical
input after uncertain commit is a no-op; a changed decision, evidence, second
review, input-file pin or prior human lifecycle event is a conflict, not a replay.
Revisions/withdrawals need a separately designed append-only lifecycle workflow.

The event contains both decisions, exact quotations/locators and all admission
pins in its structured JSON rationale. Do not log/export full events publicly.
Review time and database record time remain separate.

An interrupted transaction rolls back. A **committed incorrect human decision**
cannot be undone by deleting its immutable event. Stop downstream consumption and
use an explicitly approved full restore or a future compensating lifecycle event;
never disable the append-only triggers. Rehearsal proves transactional rollback,
not automatic undo of a later committed legal decision.

## Verification and next boundary

Mandatory offline tests cover original-evidence tampering, exact pins, empty and
unsupported decisions, second-review coverage/identity syntax/time, fresh real-file
backup hashing, restore isolation, rollback proof and CLI defaults. Disposable
PostgreSQL CI exercises atomic insertion/rollback, replay/conflicts, changed scope,
exact budgets, metadata-only observations and database-enforced read-only mode.

No actual expert decisions are supplied by this software release. Next: complete
the first real two-person review, rehearse/import only those decisions, then build
source-quoted provision reconstruction, valid-time coverage and KA/RU/EN historical
answer canaries. A green CI is not expert approval or proof of complete legal coverage.
