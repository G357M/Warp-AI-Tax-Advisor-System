---
name: Tax Advisor — Payment reconciliation
description: Local design record for the admin payment-evidence worklist and audited operator decisions.
colors:
  navy-background: "#0f172a"
  navy-surface: "#1e293b"
  slate-hover: "#334155"
  divider: "#475569"
  control-border: "#64748b"
  selection-border: "#94a3b8"
  secondary-text: "#cbd5e1"
  primary-text: "#fff"
  focus-error: "#fca5a5"
typography:
  body:
    fontFamily: "var(--font-barlow), var(--font-inter), var(--font-georgian), Inter Fallback, Barlow Fallback, system-ui, sans-serif"
  headline:
    fontSize: "clamp(1.6rem, 2.8vw, 2.2rem)"
    fontWeight: 500
    lineHeight: 1.2
  section-title:
    fontSize: "20px"
    fontWeight: 500
    lineHeight: 1.4
  guidance-title:
    fontSize: "18px"
    fontWeight: 500
    lineHeight: 1.5
  review-title:
    fontSize: "18px"
    fontWeight: 500
    lineHeight: 1.7
  empty-title:
    fontSize: "17px"
    fontWeight: 500
    lineHeight: 1.7
  order-value:
    fontSize: "16px"
    fontWeight: 500
  control:
    fontSize: "14px"
    lineHeight: 1.3
  reason:
    fontSize: "14px"
    lineHeight: 1.5
  fact-value:
    fontSize: "14px"
    lineHeight: 1.6
  review-body:
    fontSize: "14px"
    lineHeight: 1.7
  queue-metadata:
    fontSize: "13px"
  fact-label:
    fontSize: "12px"
    lineHeight: 1.6
  footnote:
    fontSize: "12px"
    lineHeight: 1.7
  evidence:
    fontFamily: "ui-monospace, SFMono-Regular, Consolas, monospace"
    fontSize: "12px"
    lineHeight: 1.6
rounded:
  field: "8px"
  row: "12px"
  control: "9999px"
spacing:
  small: "8px"
  medium: "16px"
  section: "24px"
  content: "32px"
---

# Design record: /admin/billing

## Overview

This is a scoped record of the implemented payment reconciliation surface as of 2026-09-10, including the third-stage decision controls. Its persisted surface mode is **Operate**: an administrator scans unresolved orders, compares evidence, prepares an allowed decision, checks its access effect, and records an audited reason. The incumbent navy admin worklist is the visual authority; this narrow extension has no approved design comp and does not establish a new visual world or replace root `DESIGN.md`.

The product commitments applied here are precise language, visible uncertainty, and equal billing functionality in Russian, Georgian, and English. The implemented operator process supports retaining review, confirming payment, or confirming bank failure/expiry when the preview allows it. Actual refunds and access revocation remain outside this surface.

The implementation lives in `page.tsx`, `ReviewControls.tsx`, and the locally scoped CSS Module namespace `reconciliation.module.css` (imported as `styles`). The shared shell uses `../layout.tsx` and its separate `../admin.module.css` namespace. Copy and types come from `../../../lib/billing-reconciliation.ts` and `../../../lib/billing-review.ts`.

## Colors

Navy background and slightly lighter surfaces continue the existing admin palette. White carries headings and primary evidence; light slate carries labels, identifiers, and supporting copy. Slate borders divide the queue and detail region and make selected rows distinguishable. Pale red is reserved for visible focus and error text. Payment uncertainty is expressed in words; there is no decorative health indicator or color-only payment verdict.

## Typography

The surface inherits the application's body stack (Barlow, Inter, Georgian and system fallbacks) without introducing a display face. The frontmatter records observed role sizes, including 18px decision titles, 17px empty-state titles, 16px order amounts, 14px controls/form copy/facts, and 12–13px supporting metadata. Omitted properties retain their source inheritance; the body stack does not establish a new global size. Monetary values and factual numbers use tabular numerals.

UUIDs, bank order references, event identifiers, review codes, and SHA-256 digests use the evidence monospace stack, selectable text, and `overflow-wrap: anywhere`. Long factual values wrap rather than truncate. Introductory copy is limited to 65ch and the final explanatory note to 75ch.

## Layout

The billing page has a centered maximum width of 1280px. Above 1150px the work area has queue/detail columns in a `.85fr / 1.15fr` ratio; the queue has a 300px minimum and a right divider. The shell has a 240px sidebar and 32px content padding. The work area is an open divided layout rather than nested cards.

At 1150px and below, the queue precedes details in one column with a horizontal separator. At 767px and below, the admin menu becomes an inline expandable navigation area, with two columns of links and 16px horizontal content padding. It occupies document flow rather than covering the page. At 600px and below, the heading and refresh control stack, row padding narrows, and pagination remains able to wrap. The intended mobile width is 390px. Within the stacked detail region, short facts still use two columns; long identifiers span both.

The main spacing rhythm is 8/16/24/32px. Selecting an order focuses the details region and allows it to scroll into view, including on mobile.

Decision controls follow verified events inside the detail column, separated by a top rule, 32px margin and 24px padding. Preview fields stay in document flow at full width; action rows wrap with 12px gaps. The decision journal follows the form. The established desktop and mobile compositions remain the accepted layout.

## Elevation & Depth

These CSS Modules add no shadows or decorative animation. Depth comes from tonal differences, dividers, hover surfaces, and a visible selected-row outline. The admin shell offsets the root layout's reserved public-header space so the workspace begins at the top.

## Shapes

Queue rows and navigation links have 12px corners. Refresh, paging, retry, sign-in, and menu controls have pill outlines. Controls and navigation links have at least 44px height; event disclosure summaries have at least 52px height. Focus uses a 2px outline with 3px offset, while the programmatically focusable details region uses a slate outline with 6px offset when focus-visible applies.

Decision buttons reuse the pill treatment and permit wrapping labels. Native select and textarea fields have 8px corners, navy surfaces, 12px padding, and a 44px minimum height; the textarea resizes vertically. The confirmation label is at least 44px high around a 20px checkbox. Fields and the checkbox retain visible focus outlines. The native select may ellipsize its closed value; factual identifiers and journal reasons wrap.

## Components

- **Queue:** up to 25 orders per page, with plan, amount, review reason, provider, creation time, and full checkout ID. The count describes only the current page. Each row is a native button with `aria-pressed` and `aria-controls`; selection adds a surface and outline.
- **Evidence panel:** reason-specific guidance, recorded-credit wording, a definition list of amount/status/timestamps/references, and native `details` disclosures for verified events. An explicit notice identifies a response truncated to the latest 50 events. Missing values and an empty event history have visible text.
- **Evidence navigation:** queue and detail requests use authenticated GET reads under `/api/v1/billing/admin/reconciliation`, with `cache: no-store`. Passive viewing does not contact the bank or change payments/access. Refresh returns to page one and clears selection; changing page also clears selection. Requests are abortable and keyed so a stale response cannot display beneath a different selected order.
- **Decision preview:** explicit buttons prepare an offline review note or request fresh bank evidence through POST `/preview?verify_provider=false|true`. Bank verification is enabled only for a reviewable TBC order with a bank order ID. The server preview supplies the available decisions; the initial selection is continued review. A successful preview focuses the inline form, which shows the returned bank status/amount when present and an explanation when only continued review is supported.
- **Reason and access effect:** the native decision select is followed by an explicit effect statement: access remains unchanged, or the payment is credited once and a Pro period of `months × 30` days is granted, extending an unexpired Pro period. Saving requires a trimmed reason of at least 10 characters (textarea maximum 2,000) and confirmation that evidence and access effect were checked. Changing the reason or action clears confirmation. The reason hint excludes secrets, card details and personal contacts. Refunds, partial refunds and preauthorizations stay under review; the form neither sends refunds nor revokes access.
- **Save and uncertain outcomes:** POST `/decisions` submits the selected action, reason, expected state/provider hashes and expected access effect with one idempotency key. During an uncertain response, the form is locked and “Retry same decision” reuses exactly that key and body. A 409 stale response or 422 invalid response clears the pending decision, preview and confirmation so a new preview is required. Preparation/saving announce loading state. Successful saving shows a receipt ID and an explicit refresh control; it also aborts any in-flight journal read and resets journal state so offset boundaries restart after the inserted decision.
- **Decision journal:** loaded on demand through GET `/decisions?limit=25&offset=…`, with a loading status, error recovery and “Older decisions” pagination. Appended entries are deduplicated by decision UUID. Native disclosures show action, UTC date, preserved multiline reason, operator ID, decision ID, and the access effect in past tense. Journal state resets after saving; reopening it loads from the first page.
- **States:** queue/detail loading text uses status semantics and busy regions; failures use alerts. Expired sessions offer sign-in; administrator-only failures do not offer retry. Missing orders and other load failures have retry handling. Initial empty queues and empty later pages have different recovery copy. A 401/403 from evidence, preview, save or journal requests replaces the evidence view, hiding its controls and data.
- **Time and language:** billing strings and known reason explanations support RU/KA/EN through the existing language context. Dates are localized but always formatted in UTC, with an explicit page note; suffixless backend timestamps are interpreted as UTC. Unknown backend reason/status values remain visible. The shared shell localizes its admin labels and billing navigation item, while unrelated navigation names remain English. This surface adds no language picker.
- **Review evidence and limits:** the final independent fix-pass disposition was **ship**, with all three reported findings resolved (journal reset/in-flight cancellation, journal loading feedback, and past-tense recorded effects). The accepted composition is captured in `.impeccable/review/billing-decisions-20260909/{decision-desktop,decision-mobile,desktop,mobile}.png`. These are synthetic fixture captures, not production payment evidence or an approved comp. The implementation handoff reports 17 Chromium checks passed, 546 backend tests passed with 8 skipped, 7 PostgreSQL checks passed, and successful build, TypeScript and ESLint checks; these were not rerun for this documentation-only update and do not establish a production release. The earlier nonblocking screen-reader row-name improvement remains deferred: the accessible name contains only the order label and UUID, omitting visible amount and reason. This record does not claim a complete assistive-technology or WCAG conformance audit.

## Do's and Don'ts

- Do preserve the incumbent admin palette, open queue/detail structure, readable localized copy, 44px control floor, explicit UTC convention, and complete wrapping identifiers.
- Do distinguish stored evidence, missing information, and uncertain payment outcomes. Keep pagination, selection, and error recovery predictable.
- Don't infer bank rejection from local expiry or treat the presence of this page as proof of merchant activation.
- Do preserve server-supported decision choices, explicit access effects, reason/confirmation requirements, and safe retries of uncertain saves.
- Don't add health badges, refund execution, access revocation, unsupported financial claims, or public-site design changes to this scoped surface.
- Don't use the synthetic review screenshots as production data or an approved visual comp. Root design and product records remain authoritative outside this surface.
