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
- TBC and Bank of Georgia are visible but fail closed as
  `requires_merchant_activation`. Environment variables cannot silently enable
  an unfinished adapter.

This stage does not collect card details, create bank orders, process callbacks,
enable auto-renewal or represent Business organizations/seats as complete.

## Provider options

| Option | Best fit | Recurring path | Current recommendation |
|---|---|---|---|
| Manual invoice / bank transfer | Immediate Georgian B2B and early paid pilots | No | Keep available as fallback and reconciliation path |
| TBC E-Commerce | Primary local online checkout candidate | Saved-card recurring flow is documented and requires merchant activation | First automated adapter to evaluate |
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

1. Choose the primary acquirer after comparing merchant onboarding time,
   commission, settlement time, refund rules, chargeback operations, supported
   cards/wallets, sandbox quality and recurring-payment approval.
2. Add one provider adapter behind the existing checkout contract. The browser
   receives only a bank redirect URL; the application never handles card data.
3. Store a minimal webhook-event digest and provider event ID, not the complete
   raw payload. Verify signature/authentication, amount, currency, order ID and
   current bank status before settlement; acknowledge callbacks idempotently.
4. Add cancel, expiry, refund and reconciliation states, plus an admin queue for
   unmatched or disputed events.
5. Run sandbox end-to-end tests for success, rejection, duplicate callback,
   delayed callback, browser return without callback, callback without browser
   return, refund and provider outage.
6. Enable production only after the merchant contract, callback allowlist,
   secret rotation, alerts, database backup and rollback evidence are verified.
7. Build Business organizations separately: organization ownership, invitations,
   seats, role permissions, audit log and organization-scoped billing. Only then
   advertise a team-seat count.
