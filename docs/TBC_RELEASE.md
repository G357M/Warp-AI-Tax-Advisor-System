# TBC Checkout release procedure

Scope: switching on online card payment through TBC E-Commerce (Checkout) for
the Pro and Business plans. The adapter, callback, reconciliation queue and
operator journal are already deployed (see `BILLING_RELEASE.md`); this
procedure covers only the merchant contract, credentials, sandbox evidence and
the production switch. It does not cover recurring charges, refunds executed
from the application, Bank of Georgia or Business organizations.

Current state: `BILLING_TBC_ENABLED=false`, no merchant contract. The public
catalog reports `tbc_checkout` as `requires_merchant_activation`; only the
manual invoice path is offered.

## 1. Merchant contract (owner)

Sign the TBC E-Commerce merchant agreement and obtain from TBC:

- production `apikey`, `client_id`, `client_secret`;
- sandbox/test credentials and the sandbox API host, if it differs from
  `https://api.tbcbank.ge`;
- confirmation of the callback source IPs (nginx currently allows
  `193.104.20.44`, `193.104.20.45`, `185.52.80.44`, `185.52.80.45`) and
  whether sandbox callbacks come from the same addresses;
- the merchant portal login used for refunds and order lookup.

Register with TBC, exactly:

| Setting | Value |
|---|---|
| Return URL | `https://tax-advisor.ge/account?payment_return=tbc` |
| Callback URL | `https://tax-advisor.ge/api/v1/billing/providers/tbc/callback` |

Record the commission, settlement time, refund/chargeback procedure and
whether recurring (saved card) is enabled. The application reports
`recurring: false` and must keep doing so until recurring is built separately.

Credentials never go into Git, chat, tickets or screenshots. They live only in
`/root/infohub/.env` on the server (and in a local untracked `.env` for the
sandbox run).

## 2. Application facts the tests rely on

- Prices come from `backend/billing/catalog.py`: Pro 49.00 GEL, Business
  149.00 GEL. A bank order is created for the exact amount; a mismatched
  amount, currency or payment id in the bank response is rejected.
- The browser is redirected only to an `https://tpay.tbcbank.ge` approval URL.
- Bank orders expire after `TBC_CHECKOUT_EXPIRATION_MINUTES` (max 12).
- The callback carries only `PaymentId`. It is never trusted as proof: the
  backend fetches the payment from TBC (`GET /v1/tpay/payments/{id}`) and
  reconciles. Unknown ids are acknowledged without any outbound request.
- The browser return calls `POST /billing/checkout/{id}/refresh`, which does
  the same authoritative lookup. Either path alone must be enough to settle.
- `Succeeded` settles once (one subscription per order, replays are ignored).
  `Failed`/`Expired` close the checkout. `Returned`, `PartialReturned`,
  `WaitingConfirm`, and any amount/currency/id conflict put the checkout into
  `provider_review`; access is not changed automatically. An operator resolves
  it at `/admin/billing` with a journaled decision.
- Refunds are executed in the TBC merchant portal, not in the application.

## 3. Sandbox gate

Run against TBC sandbox credentials with `ENVIRONMENT` not set to
`production` (the production validator only accepts `api.tbcbank.ge` and the
tax-advisor.ge return/callback URLs). Callbacks need a public HTTPS endpoint;
if the sandbox cannot reach one, the browser-return path is still testable and
the callback cases are exercised from a staging host or skipped and recorded
as not covered.

For each scenario record: checkout id, TBC payId, final `checkout.status`,
`provider_status`, provider events, subscription/payment rows, screenshot of
the account page.

| # | Scenario | Expected result |
|---|---|---|
| 1 | Successful card payment, callback and browser return both arrive | `paid`, exactly one subscription and payment row |
| 2 | Card declined / payment rejected | `failed`, no subscription |
| 3 | User abandons the bank page until expiry | `expired`, no subscription |
| 4 | Duplicate callback for a paid order | replay ignored, still one subscription |
| 5 | Callback delayed until after browser return | settled once by whichever arrives first |
| 6 | Browser return without callback (close tab is not enough: block the callback) | settles via refresh |
| 7 | Callback without browser return (close the tab after paying) | settles via callback |
| 8 | Bank API unreachable during refresh/callback | HTTP 503 "could not be verified", nothing settled; succeeds on retry |
| 9 | Full refund in the merchant portal after `paid` | `provider_review`, access unchanged until operator decision |
| 10 | Partial refund | `provider_review`, same as above |
| 11 | Operator decision on 9/10 in `/admin/billing` | decision in the journal, access changes only as decided |

Gate passes when 1-8 behave as expected and 9-11 are either verified or
explicitly recorded as manual-only by the owner.

## 4. Before the production switch

1. `main` CI green; the deployed SHA matches the commit that passed the
   sandbox run (or the difference is reviewed and contains no billing change).
2. Fresh database backup with a verified checksum (nightly dump younger than
   36h, see `ops/backup-infohub-db.sh`).
3. Public terms and the account page describe card payment through TBC,
   one-off (non-recurring) charges and the refund route.
4. Owner approval for production enablement and for one real-money test.

## 5. Production switch (owner, on the server)

Add to `/root/infohub/.env` (edit with an editor, do not echo secrets into
shell history):

```
BILLING_TBC_ENABLED=true
TBC_API_KEY=<production apikey>
TBC_CLIENT_ID=<production client_id>
TBC_CLIENT_SECRET=<production client_secret>
```

Keep the defaults for `TBC_API_BASE_URL`, `TBC_RETURN_URL` and
`TBC_CALLBACK_URL`. Then:

```
cd /root/infohub
docker compose up -d --wait --no-deps backend
docker compose restart nginx
curl -fsS https://tax-advisor.ge/api/v1/billing/catalog
```

If a credential is missing or a URL is wrong, the backend refuses to start
(settings validation) rather than offering a half-configured TBC; fix `.env`
and repeat. The catalog must now report `tbc_checkout` as `available`.

## 6. First live payment

1. Buy Pro with the owner's own card; follow it to `paid` on `/account`.
2. Check `/admin/billing`: no review hold, one subscription.
3. Refund it in the TBC merchant portal; confirm the checkout moves to
   `provider_review`; record an operator decision.
4. Watch the backend log for `tbc_request_failed` / 503 on the callback for
   the first days.

## 7. Rollback

Set `BILLING_TBC_ENABLED=false` in `.env` and restart the backend as above.
New checkouts fall back to manual invoices immediately.

While disabled, callbacks and refreshes for already-created TBC orders return
503 (the bank lookup is unavailable), so an order paid during that window is
not settled automatically. Operator decisions other than `keep_review` also
require a live bank lookup and are refused while TBC is disabled. Prefer
disabling when no TBC order is pending (orders expire within 12 minutes).
Orders left pending appear in `/admin/billing` as
`payment_verification_overdue`; check them in the merchant portal and resolve
them with an operator decision after TBC is re-enabled. Never delete
checkouts, provider events or journal rows as part of a rollback.

Rotate credentials (new values from TBC, edit `.env`, restart backend) if they
were ever exposed.
