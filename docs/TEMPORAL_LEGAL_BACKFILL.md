# Temporal Legal Engine — controlled backfill v1

## Outcome and safety boundary

This package converts the legacy amendment corpus into immutable official
source evidence and reviewable temporal candidates at bulk scale. It does not
trust `law_amendments.old_norm/new_norm` as legal text, create authoritative
`legal_provision_versions`, or route a public answer through temporal tables.

The production inventory at design time contained 2,391 legacy amendment rows,
2,090 resolved target links across 183 acts and 6,929 affected-item hints. Only
the official source bytes and facts revalidated against those bytes may cross
the backfill boundary.

## Three gates

1. **Inventory:** read legacy rows and calculate the exact unique-source budget.
   No network call or database write is allowed.
2. **Bundle:** fetch only fixed InfoHub document UUIDs from
   `infohubapi.rs.ge`, preserve the exact JSON bytes, rebuild the scraper's
   normalized text and require its MD5 to match the stored legacy document.
3. **Import:** validate every file and manifest hash again, then use one
   PostgreSQL transaction with exact source/act/operation ceilings.

The bundle is non-overwriting and contains:

- `manifest.json` — source identities, exact hashes and candidate lineage;
- `sources/*.json` — exact official API response bytes;
- `expert_review_queue.csv` — one bulk expert queue, including unresolved and
  ambiguous candidates;
- `summary.json` — aggregate counts only.

Directories are mode `0700`; files are mode `0600` on Linux.

The legacy corpus was produced by three historical normalization contracts.
The builder reads only `metadata.extraction.method` and selects the matching
frozen verifier: old API plain text, native Markdown v2, or Scrapling-repaired
native Markdown. Unknown methods fail closed. The chosen method is recorded in
every source manifest entry, so validation cannot silently substitute a newer
normalizer for an older stored hash.

Source comparison has three explicit outcomes. `exact_legacy_md5` and
`whitespace_equivalent_legacy` may support a deterministic operation; the
latter requires the stored and live texts to have the same compact-whitespace
MD5. `source_content_drift` is quarantined as evidence. A drifted amendment is
forced into the expert queue and validation rejects any bundle that promotes
an operation from it. A drifted target-only consolidated act may retain its
official identity and current snapshot because this package creates no
authoritative target provision text.

## Deterministic operation promotion

An old affected-article entry is only materialized as a pending
`legal_amendment_operation` when all of the following hold:

- the amendment is linked to one target legal document;
- its effective date exists;
- the article identifier is canonical (`N` or `N-M`);
- the exact official response reproduces the stored document MD5;
- or it differs only in whitespace and reproduces the separately calculated
  compact-whitespace MD5;
- the official Georgian text contains the referenced article and one
  unambiguous operative formula nearby:
  - add: `დაემატოს` / `დამატებულ იქნეს`;
  - replace: `ჩამოყალიბდეს შემდეგი რედაქციით`;
  - repeal: `ამოღებულ იქნეს` / an explicit invalidation formula;
- that formula agrees with the legacy action hint.

Even then, the operation is stored as `llm_assisted`, with
`authoritative_text_promoted=false`, a `machine_extracted` event and a
`needs_review` event. Marker text is represented by a hash code in the
manifest; complete source text remains in the protected exact snapshot.

Generic Georgian wording such as “change”, conflicting formulas, missing
dates, unresolved laws, non-article references and any source drift remain in
the CSV queue. This deliberately trades recall for legal safety.

## Production workflow

Dry-run plans perform no database or network work:

```bash
docker exec infohub-backend \
  python /app/scripts/build_legal_temporal_backfill_bundle.py
docker exec infohub-backend \
  python /app/scripts/import_legal_temporal_backfill.py
docker exec infohub-backend \
  python /app/scripts/audit_legal_temporal_backfill.py
```

Read the exact inventory for all amendments or one target act:

```bash
docker exec infohub-backend \
  python /app/scripts/build_legal_temporal_backfill_bundle.py \
    --inventory

docker exec infohub-backend \
  python /app/scripts/build_legal_temporal_backfill_bundle.py \
    --inventory \
    --target-law-doc-id LEGACY_TARGET_DOCUMENT_UUID
```

Build a protected bundle using the exact source count returned by inventory:

```bash
docker exec infohub-backend \
  python /app/scripts/build_legal_temporal_backfill_bundle.py \
    --execute \
    --output /tmp/legal-temporal-backfill-RUN_ID \
    --max-source-fetches EXACT_SOURCE_COUNT
```

Validate without connecting to PostgreSQL:

```bash
docker exec infohub-backend \
  python /app/scripts/import_legal_temporal_backfill.py \
    --bundle /tmp/legal-temporal-backfill-RUN_ID \
    --expected-manifest-sha256 REVIEWED_MANIFEST_SHA256
```

Apply only after reviewing `summary.json` and the exact ceilings:

```bash
docker exec infohub-backend \
  python /app/scripts/import_legal_temporal_backfill.py \
    --bundle /tmp/legal-temporal-backfill-RUN_ID \
    --expected-manifest-sha256 REVIEWED_MANIFEST_SHA256 \
    --apply \
    --max-source-snapshots EXACT_SOURCE_COUNT \
    --max-acts EXACT_SOURCE_COUNT \
    --max-operations EXACT_OPERATION_CANDIDATE_COUNT
```

Run the read-only lineage audit against the same immutable bundle:

```bash
docker exec infohub-backend \
  python /app/scripts/audit_legal_temporal_backfill.py \
    --execute \
    --bundle /tmp/legal-temporal-backfill-RUN_ID \
    --expected-manifest-sha256 REVIEWED_MANIFEST_SHA256
```

Copy the complete bundle to a protected ignored `.state` directory before the
container is replaced. Never commit raw source bundles or expert CSVs.

## Idempotency and rollback boundary

The same exact bundle is idempotent: content-addressed snapshots, stable acts,
publications, provisions, operation keys and deterministic review-event UUIDs
are reused. A different source body cannot reuse the reviewed manifest hash.

The import is additive and one-transaction, but imported evidence is immutable
by design. Take and hash a fresh production backup before the first full apply.
Recovery from a bad committed bundle therefore uses the reviewed database
recovery procedure, not ad-hoc `DELETE` statements.

## What remains after this package

Expert verification can approve/correct the generated candidate queue in bulk.
A later package may then append verified amendment operations and reconstruct
authoritative provision versions. Public historical answers remain disabled
until coverage, non-overlap, source lineage and multilingual answer canaries all
pass for the requested `as_of_date`.
