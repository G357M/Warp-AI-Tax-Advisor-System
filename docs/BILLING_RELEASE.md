# Billing reconciliation release procedure

Scope: inspection, operator decisions and the append-only journal at
`/admin/billing`. This release does not enable TBC, SMTP, recurring charges,
bank refunds or Business organizations.

## Candidate and gates

The candidate is prepared on `codex/billing-operator-reconciliation`, based on
the tree deployed at `e237d422552525b0ce7ec806de85f2102f19734f`.
Local validation is recorded in `DEVELOPMENT_MEMORY.md`. PR/run identifiers and
their exact tested SHA are recorded in `.state/billing-release/evidence.json`
during release preparation; that local evidence file is not a production
authorization and must be refreshed before deployment.

The PR must pass all five CI jobs: backend contracts/dependency audit,
PostgreSQL immutable evidence, frontend lint/types/build/audit, deterministic
Linux visual regression, and production image builds. No Windows screenshot
baseline substitutions or skipped failing jobs are accepted. Inspect the
exact PR head and tested merge commit before merging; verify CI on the final
main commit before production action.

## Before production approval

1. Record candidate/main SHA and successful CI URL. Ensure the intended change
   list contains only the billing implementation and its tests/documentation.
2. Read the current server SHA, tracked worktree status, backend/frontend image
   IDs, container health and pinned SSH configuration. Historical observations
   in project memory do not prove the current state.
3. Verify a recoverable database backup and record the restore evidence. Check
   space for both rollback images and the new build. Preserve the audit journal
   on application rollback; do not drop it or restore an older DB over new
   payments/decisions as an application rollback shortcut.
4. Present this exact commit, CI, server, backup and rollback evidence for the
   owner's production approval. Keep provider enablement and real-money tests
   outside this release unless separately authorized.

## Schema and deployment ordering

Use `/root/infohub/scripts/deploy_production.sh` on the production `main`
checkout. It fast-forwards from origin, re-executes a changed deploy script,
tags existing backend/frontend images, builds new images, validates readiness,
and installs schema before replacing containers.

The existing provider contract remains unchanged:
`9ea51e942ab67aaf8d215b26df554d40c088b0f4a50d41026ea3622c33559bee`.
The additional operator-journal contract is:
`51ea189e55a2127a0d13bb0a60233714f6adeba4d8458371ae286d12a3bef610`.

The journal installer defaults to a read-only dry plan. Applying it requires
`--apply --expected-contract-sha256` with that exact value and PostgreSQL.
It creates the journal, unique idempotency constraint and ALWAYS immutability
trigger, and audits them in one transaction. It does not settle existing
checkouts or contact the bank. A failed installation must prevent new runtime
containers from starting.

## Verify and recover

After an approved deployment, independently verify the server SHA and actual
running image IDs, backend/frontend/container health, and public health.
With an authorized operator session, verify that the queue and journal load.
Confirm unauthenticated/non-admin access is denied. Do not click bank-preview
or decision controls as a production smoke test without an approved order.

The deploy script creates `infohub/backend:rollback-<old SHA>` and
`infohub/frontend:rollback-<old SHA>` tags, where the old SHA is the recorded
12-character deployment baseline. Verify their actual image IDs before use.
The script reports a failed public health check; it does **not** automatically
restore containers. If recovery is needed, redeploy those verified old images
with the existing Compose service configuration and validate health again.
Keep the additive journal table and its trigger intact. Record the actual
container image IDs separately from the checked-out repository SHA, since
restoring images does not reset the checkout.

Merchant sandbox scenarios remain a separate gate: success, rejection,
duplicate/delayed callbacks, callback/browser-return asymmetry, bank outage,
and verified returned/partial-return states. Local fake-provider tests prove
application behavior only.
