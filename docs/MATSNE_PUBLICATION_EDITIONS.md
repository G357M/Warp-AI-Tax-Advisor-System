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

## Automated same-origin browser capture

The repository includes `backend/scripts/matsne_same_origin_capture.js` for
Chrome or Edge DevTools. It is not a crawler and does not bypass Matsne access
controls. It runs only while the active top-level page has the exact origin
`https://matsne.gov.ge`, uses that browser session for same-origin requests and
writes only to a directory explicitly selected by the operator.

One-time operator procedure:

1. Open an official Matsne page in a current Chrome or Edge window and confirm
   that the page itself is readable (not an access/challenge response).
2. Open Developer Tools (`F12`), select **Sources**, then **Snippets**, create a
   new snippet and paste the complete contents of
   `backend/scripts/matsne_same_origin_capture.js`.
3. Run the snippet with `Ctrl+Enter`, then click the temporary blue
   **Start verified Matsne capture** button at the top right of the Matsne page.
   In the directory picker select the root of the pre-created capture packet:
   the directory that directly contains `capture_plan.json` and
   `edition_metadata.csv`. The button exists only to provide the browser-required
   user gesture and removes itself immediately after selection.
4. Leave that Matsne tab open until the console reports completion. The default
   delay is one second after every newly captured publication. Existing valid
   receipts are verified and skipped, so rerunning the snippet safely resumes a
   stopped pass.

The collector processes the immutable plan, not hand-written URLs. For every
publication it fetches the page and tree sequentially, rejects redirects,
non-200 responses, unexpected media types, oversized bodies, invalid JSON and
known challenge-page markers, then writes:

```text
editions/000000/page.html
editions/000000/tree.json
editions/000000/browser_capture_receipt.json
```

Source files are new-only. A file already present is reused only when its bytes
match the newly observed SHA-256; a mismatch stops the pass without overwrite.
The receipt records the exact planned and final URLs, selected non-secret HTTP
headers, status, UTC observation time, length and SHA-256. Cookies and response
bodies are never uploaded to another service.

To process a bounded segment, set this in the DevTools Console before running
the snippet:

```javascript
window.__MATSNE_CAPTURE_OPTIONS__ = {
  startPublication: 100,
  maxNewCaptures: 25,
  delayMs: 1000,
};
```

To stop safely between publications:

```javascript
window.__MATSNE_CAPTURE_ABORT__ = true;
```

After a pass, independently audit the receipts and exact stored bodies from
`backend`:

```bash
python scripts/audit_matsne_browser_capture_receipts.py \
  --plan /secure/evidence/tax-code-capture/capture_plan.json \
  --bundle /secure/evidence/tax-code-capture \
  --expected-plan-sha256 <plan-sha256>
```

This audit is read-only and exits `2` while any source pair or receipt is
missing or inconsistent. It recomputes every source hash, validates every tree
and article boundary, and returns one exact `next_action`. A green receipt audit
proves a complete, internally consistent browser observation; it does not
establish when a publication entered into force and does not authorize public
answers.

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

## Mass capture packet

Do not construct 246 URLs, directories or hashes manually. Generate the
Tax Code capture packet once:

```bash
python scripts/plan_matsne_publication_capture.py \
  --output-dir /secure/evidence/tax-code-capture \
  --act-key ge-tax-code \
  --document-id 1043717 \
  --title-ka "საქართველოს საგადასახადო კოდექსი" \
  --first-publication 0 \
  --last-publication 245
```

The packet contains an immutable `capture_plan.json`, an Excel-compatible
UTF-8 `edition_metadata.csv` and one pre-created directory per publication.
Only these metadata columns are editable: `valid_from`, the effective-date
evidence fields, `date_evidence_state`, reviewer, UTC review time, rationale
and notes. URL and file columns are immutable and validated against the plan.

After browser capture, run the read-only audit as often as needed:

```bash
python scripts/audit_matsne_publication_capture.py \
  --plan /secure/evidence/tax-code-capture/capture_plan.json \
  --metadata /secure/evidence/tax-code-capture/edition_metadata.csv \
  --bundle /secure/evidence/tax-code-capture \
  --expected-plan-sha256 <plan-sha256>
```

An incomplete audit exits `2` and prints one exact `next_action` with the page
URL, tree URL, destination files and blockers. It does not create a manifest.
Access/challenge pages, missing files, bad trees and unconfirmed dates remain
quarantined instead of becoming partial legal history.

When all publications are ready, finalize once:

```bash
python scripts/finalize_matsne_publication_capture.py \
  --plan /secure/evidence/tax-code-capture/capture_plan.json \
  --metadata /secure/evidence/tax-code-capture/edition_metadata.csv \
  --bundle /secure/evidence/tax-code-capture \
  --expected-plan-sha256 <plan-sha256> \
  --manifest-output /secure/evidence/tax-code-capture/manifest.json \
  --admission-output /secure/evidence/tax-code-capture/capture_admission.json
```

Finalization calculates every source hash and article count automatically. The
admission sidecar binds the plan, reviewed metadata, full read-only audit and
generated manifest by SHA-256. Both outputs are new-only; no source capture is
overwritten.

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
