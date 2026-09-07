# Client account and billing roadmap

Updated: 2026-09-07

## Implemented foundation

- The backend plan catalog is the runtime price authority. Amounts for new
  checkout intents are integer minor units (tetri), never a client-supplied
  floating-point value.
- Every checkout is persisted with user, plan, amount, currency, provider,
  status, expiry and a per-user idempotency key.
- Repeating the same request cannot create a second order. Reusing its key for
  a different plan is rejected.
- The manual invoice workflow remains executable. Admin settlement can use the
  exact checkout UUID and is itself replay-safe; the legacy email path remains
  temporarily available for old invoices.
- The client account shows current plan and period, quota, package comparison,
  payment-method readiness, pending checkout reference, payment history, saved
  conversations and support.
- The TBC Checkout adapter is implemented behind an explicit feature gate. It
  obtains a short-lived access token server-side, creates a hosted-bank order,
  validates the returned `payId`, amount, currency and redirect host, verifies
  every browser return or callback through the authenticated Get Payment API,
  and settles a checkout at most once.
- Callback evidence is retained as a normalized SHA-256 digest and status, not
  a raw provider body. Unknown payment IDs are acknowledged without an outbound
  lookup; returns and partial returns stop in a manual-review state.
- Production TBC checkout and Bank of Georgia remain fail-closed as
  `requires_merchant_activation` until merchant onboarding and credentials are
  completed. TBC can become `available` only when its feature flag and all
  three required credentials are present. Bank of Georgia has no adapter yet.

The application never collects card details. The code can create and reconcile
TBC bank orders, but production activation, refunds, recurring charges and
Business organizations/seats remain incomplete stages.

## Provider options

| Option | Best fit | Recurring path | Current recommendation |
|---|---|---|---|
| Manual invoice / bank transfer | Immediate Georgian B2B and early paid pilots | No | Keep available as fallback and reconciliation path |
| TBC E-Commerce | Primary local online checkout candidate | Saved-card recurring flow is documented and requires separate merchant activation | Adapter implemented; production activation and recurring remain gated |
| Bank of Georgia Online Payments | Strong local alternative or second acquiring route | Saved-card / recurring capabilities are documented | Evaluate commercial terms in parallel with TBC |
| Paysera Checkout | Secondary cross-border and method-coverage option | Recurring payments are offered | Consider after the first Georgian bank adapter |
| Stripe | International product only when the contracting entity is eligible | Mature subscription stack | Do not design the Georgian launch around it while Georgia is absent from the supported-business-country list |

Official references:

- TBC Checkout API overview: <https://developers.tbcbank.ge/docs/checkout-api-overview>
- TBC e-commerce FAQ and recurring activation: <https://developers.tbcbank.ge/docs/e-commerce-faq>
- TBC payment creation and callback contract: <https://developers.tbcbank.ge/docs/checkout-create-checkout-payment>
- Bank of Georgia Payments API: <https://api.bog.ge/docs/en/payments/introduction>
- Paysera Checkout: <https://www.paysera.ge/v2/en-GE/payment-gateway-checkout>
- Stripe global availability: <https://stripe.com/global>

## Next implementation gates

1. Complete TBC merchant onboarding and compare the signed commercial terms
   against Bank of Georgia: commission, settlement time, refund and chargeback
   operations, cards/wallets, sandbox quality and recurring-payment approval.
2. Provision the production secrets outside Git, register the exact return and
   callback URLs, confirm the four documented callback source IPs with TBC and
   run the additive provider-schema migration before enabling the feature flag.
3. Add an operator reconciliation queue for `provider_unknown`, returns,
   partial returns and disputed events. Refund execution must be a separate,
   audited command; the current adapter only observes those states and does not
   change an entitlement silently.
4. Run provider sandbox end-to-end tests for success, rejection, duplicate callback,
   delayed callback, browser return without callback, callback without browser
   return, refund and provider outage.
5. Enable production only after the merchant contract, callback allowlist,
   secret rotation, alerts, database backup and rollback evidence are verified.
6. Design recurring billing only after TBC activates the merchant's recurring
   capability. The current payment method truthfully reports `recurring: false`.
7. Build Business organizations separately: organization ownership, invitations,
   seats, role permissions, audit log and organization-scoped billing. Only then
   advertise a team-seat count.
