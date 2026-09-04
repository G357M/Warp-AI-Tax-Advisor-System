# Matsne publication editions: exact historical provision proposals

## Purpose and safety boundary

This offline package turns exact, browser-saved Matsne publication editions
into a date-indexed proposal for each Georgian article. It exists because the
current consolidated text cannot be replayed backwards or forwards to invent
past law. Every proposed version comes from the text of one concrete official
publication edition.

The builder performs no HTTP request, database write or public RAG routing. Its
output is explicitly non-executable and requires independent legal review
before a separate materializer may create authoritative provision versions.

## Why capture is browser-assisted

Matsne exposes numbered publication pages and document trees, but automated
server requests may receive an access-challenge page. The pipeline does not
bypass that protection. An operator saves the Georgian publication page and
its matching `/ka/document/tree/<document>/<publication>` response through a
normal browser session. The evidence bundle then works fully offline.

## Evidence bundle v1

The directory contains `manifest.json` plus unique source files. The manifest
has this exact shape:

```json
{
  "contract": "matsne-publication-editions-v1",
  "act": {
    "act_key": "ge-tax-code",
    "document_id": "1043717",
    "title_ka": "საქართველოს საგადასახადო კოდექსი",
    "language": "ka",
    "official_document_url": "https://matsne.gov.ge/ka/document/view/1043717"
  },
  "editions": [
    {
      "publication": 245,
      "valid_from": "2026-08-01",
      "page_url": "https://matsne.gov.ge/ka/document/view/1043717?publication=245",
      "page_file": "editions/245/page.html",
      "page_sha256": "<lowercase sha256>",
      "tree_url": "https://matsne.gov.ge/ka/document/tree/1043717/245",
      "tree_file": "editions/245/tree.json",
      "tree_sha256": "<lowercase sha256>",
      "expected_article_count": 320,
      "effective_date_evidence": {
        "official_url": "<official Matsne URL>",
        "file": "editions/245/page.html",
        "sha256": "<lowercase sha256>",
        "quote": "<verbatim official effective-date passage>"
      }
    }
  ]
}
```

Publication numbers must increase; effective dates may repeat but must not go
backwards. When several consolidated publications start on the same date, the
last numbered publication is the queryable state and every suppressed edition
remains listed in the audit report.

The effective-date quote must occur verbatim in its hash-pinned official
source. This proves source membership, not legal interpretation; therefore the
result still requires independent expert review.

## Fail-closed checks

- strict UTF-8 JSON, duplicate-key and non-finite-value rejection;
- exact Matsne host, document id and publication number in each URL;
- lowercase SHA-256 for the manifest and every source file;
- regular files only, bounded sizes and bundle-confined paths;
- access/challenge pages are rejected;
- article anchors must match the official tree and occur exactly once;
- every article range must stay inside one non-page document container;
- expected article counts must match exactly;
- future and shared/ambiguous anchors are excluded and counted;
- output cannot be written into or over the evidence bundle.

## Build and query

First calculate and record the exact manifest hash. Then run from `backend`:

```bash
python scripts/build_matsne_publication_editions.py \
  --bundle /secure/evidence/tax-code \
  --output /secure/review/tax-code-proposals.json \
  --expected-manifest-sha256 <manifest-sha256>
```

The output prints and embeds a proposal SHA-256. A date query requires that
second pin:

```bash
python scripts/query_matsne_provision_history.py \
  --proposals /secure/review/tax-code-proposals.json \
  --expected-proposal-sha256 <proposal-sha256> \
  --article 60 \
  --as-of 2024-03-15
```

Possible statuses are `exact_version_proposal`, `coverage_gap`,
`not_in_observed_force` and `unknown_article`. Even an exact proposal returns
`authoritative_for_public_answers: false`.

## What remains before public use

1. Capture every required edition and resolve every reported gap.
2. Independently verify publication applicability dates and exact article
   boundaries against the official acts.
3. Admit reviewed versions through a separate, rollback-protected PostgreSQL
   materializer with immutable review events.
4. Add multilingual derivative text without replacing the Georgian source.
5. Only then evaluate a bounded public temporal-answer canary.
