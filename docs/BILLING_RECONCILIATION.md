# Billing reconciliation: operator evidence

Implemented locally: 2026-09-09. Release status and validation evidence are
recorded in `docs/DEVELOPMENT_MEMORY.md`.

## Scope

The operator surface provides authenticated inspection APIs and an administrator
screen at `/admin/billing`, with a separate explicit decision workflow. It shows
unresolved bank orders and their verified event evidence. It does not execute
refunds, release a review hold, contact the bank, activate a plan or write a
decision merely because an operator opens the list or detail.

The existing customer refresh and TBC callback continue to obtain payment
status through the authenticated bank adapter. A callback body alone is never
accepted as payment evidence. TBC production activation remains a separate gate.

## Operator screen

Open **Payment reconciliation / Сверка платежей / გადახდების შეჯერება** in
the administrator navigation. The screen uses the same RU/KA/EN language
selection as the rest of the site. The menu collapses on mobile without
covering the work area.

1. Review the current page of up to 25 orders. The displayed count applies
   only to that page, not the complete unresolved backlog.
2. Select an order to inspect its reason, amount, bank order, settlement
   reference and timestamps. All displayed times are explicitly UTC.
3. Expand a verified event to inspect its processing result, review code and
   evidence SHA-256. The newest 50 events are available; truncation is shown.
4. Refresh the queue to restart at page one. Pagination and refresh clear the
   selected detail; obsolete requests cannot overwrite a newer selection.

Loading, empty results, unavailable service, expired session and denied access
have separate states. Viewing an error is never presented as an empty backlog.
Queue and detail requests are GET-only and use `cache: no-store`.

## Operator API

Use an existing administrator session with the normal API authentication.
Never paste session cookies, merchant secrets or access tokens into tickets.

- `GET /api/v1/billing/admin/reconciliation?limit=25&offset=0`
  returns `items` and `next_offset`. Limit is 1–100; offset is 0–100000.
  Items are ordered by creation time, then checkout UUID. Offset pagination
  reflects the current queue: restart at offset zero when reconciling changes.
- `GET /api/v1/billing/admin/reconciliation/{checkout_uuid}`
  returns the minimal checkout evidence and up to 50 newest provider events.
  `events_truncated=true` means older events remain in the database; it is not
  a complete history export. A checkout can be inspected after it leaves the
  worklist, and its `reason` is then null.

Both routes require `require_admin`: unauthenticated access is 401 and an
ordinary account receives 403. The response omits email, bank redirect links,
raw provider bodies and checkout consent details. Events expose only normalized
SHA-256, status, processing result, error code and timestamps.

## Worklist reasons

| Reason | Meaning | Next operator step |
|---|---|---|
| `provider_unknown` | Order creation had an uncertain result | Find the merchant order using checkout UUID; do not create another charge blindly |
| `provider_review` | Refund, partial return, preauthorization, conflicting evidence or settlement inconsistency | Compare the stored order, amount, currency and verified-event history with bank records; retain the hold |
| `payment_verification_overdue` | A TBC pending/locally expired order passed its expiry without a settled payment or verified terminal failure/expiry | Check the merchant order; local expiry alone does not prove that the bank rejected payment |

Manual invoice expiry and verified bank Failed/Expired states are not presented
as missing bank callbacks. A successful late callback may settle a locally
expired order when no review hold exists and all payment fields match.

## State invariants

1. `provider_review` is sticky. Later Created, Processing, Failed, Expired or
   Succeeded observations cannot silently clear the hold.
2. `settled_payment_id`, rather than only the display status, identifies an
   already credited order. A conflicting bank state moves it to review without
   changing the existing payment or subscription period.
3. The same rule applies when a pre-settlement state reappears as a duplicate
   event after settlement. Replay detection must not hide that conflict.
4. A paid checkout without its settlement reference requires review; a callback
   must not repair missing ledger evidence by granting another period.
5. Bank unavailability does not manufacture a verified event. Another user's
   refresh and an unknown callback ID do not query the bank for that order.

## Audited decisions (local implementation, 2026-09-09)

Select **Prepare review note** to record continued review without contacting
the bank, or **Check bank for a decision** to obtain a fresh authenticated
Get Payment result. Neither preview writes payment, subscription, event or
decision data. Select one of the supported decisions, enter a reason of
10–2000 nonblank characters, check the stated access effect, and record it.

| Decision | Required evidence | Access effect |
|---|---|---|
| `keep_review` | Current unresolved checkout snapshot | Remains under review; access unchanged; works without bank availability |
| `confirm_payment` with a settled reference | Fresh Succeeded, matching order/amount/currency, matching successful payment and owner subscription | Restore paid display status; do not extend or reactivate the subscription |
| `confirm_payment` without settlement | Fresh matching Succeeded, valid stored consent, Pro checkout for 1–24 months, no existing payment, prior grant or missing-settlement evidence, no unexpired other plan | Credit once using existing 30-day-per-month settlement semantics |
| `confirm_no_charge` | Fresh matching Failed/Expired and no settlement or conflicting ledger evidence | Record failed/expired; no access change |

Returned, PartialReturned, WaitingConfirm, mismatched bank evidence and broken
ledger references support continued review only. Actual bank refunds, access
revocation, corrections of broken ledger records and Business plan changes
are outside this command. Do not clear holds with ad-hoc database edits.

Additional admin-only routes:

- `POST /api/v1/billing/admin/reconciliation/{id}/preview?verify_provider=false`
  returns a state SHA-256, optional normalized provider evidence and SHA-256,
  and the supported action/access-effect pairs. Set `verify_provider=true`
  only for an explicit bank check.
- `POST /api/v1/billing/admin/reconciliation/{id}/decisions` requires an
  `Idempotency-Key` (8–128 permitted ASCII characters), action, reason,
  `expected_state_sha256`, optional `expected_provider_sha256`, and
  `expected_access_effect`. Financial resolution rechecks the bank inside the
  decision transaction. Local/provider changes or unsupported effects return
  409 without applying the decision. Bank unavailability returns 503.
- `GET /api/v1/billing/admin/reconciliation/{id}/decisions?limit=25&offset=0`
  returns a paginated newest-first journal, with before/after snapshots,
  normalized provider evidence, reason, action, effect and actor UUID.
  The UI loads it on demand and shows older pages explicitly.

The checkout and then user rows are locked in the same order as settlement.
The state pin includes subscription, ledger and provider-event evidence.
Journal insertion, checkout changes and any payment/subscription write commit
atomically. Replay of the same key, actor and body returns the original result
before calling the bank; conflicting reuse returns 409. The UI freezes the
original body/key after an uncertain response and retries that same request
while the selected form remains mounted. After navigation/reload, inspect the
journal and refresh the evidence before preparing a new decision.

The journal retains actor UUID rather than mutable names or email. It stores
no raw bank bodies, credentials or card details. Free-text reasons must not
contain secrets or personal contacts. The separate additive installer
`backend/scripts/add_billing_review_journal.py` defaults to a dry plan and
requires this explicit reviewed contract for `--apply`:
`51ea189e55a2127a0d13bb0a60233714f6adeba4d8458371ae286d12a3bef610`.
The checked deploy script installs it before starting new runtime containers.
PostgreSQL rejects UPDATE, DELETE and TRUNCATE of the journal with an ALWAYS
trigger; checkout deletion is restricted while decisions exist. Retention or
erasure of this audit evidence therefore requires a separate reviewed policy.
The additive journal must remain intact on application rollback. This protects
ordinary database operations; a database owner can still alter schema/triggers.

Provider contract reference: [TBC Get Payment details](https://developers.tbcbank.ge/docs/checkout-get-checkout-payment-details)
and [TBC create payment and callback](https://developers.tbcbank.ge/docs/checkout-create-checkout-payment).
Reviewed for implementation on 2026-09-09; local fixtures are not a merchant certification.

## Remaining launch gates

Inspection and audited decisions are implemented locally. Provider refund
execution and the associated entitlement policy remain separate work.

Local API tests replace the bank and email delivery boundaries. They verify
payment/recovery/history behavior but do not prove merchant sandbox behavior,
real email delivery, current bank terms or readiness for live charges.

Before enabling production TBC, complete the existing merchant activation,
callback, backup and sandbox gates in `BILLING_AND_CLIENT_ACCOUNT_ROADMAP.md`.
