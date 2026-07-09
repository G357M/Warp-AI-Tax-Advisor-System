---
target: frontend/app/page.tsx
total_score: 28
p0_count: 0
p1_count: 2
timestamp: 2026-07-09T09-55-01Z
slug: frontend-app-page-tsx
---
⚠️ DEGRADED: single-context (Assessment A sub-agent terminated early on API session limit; A performed inline by parent after Assessment B's findings were already in context — anchoring risk acknowledged. Assessment B ran isolated and completed normally.)

# Critique: frontend/app/page.tsx (landing, tax-advisor.ge)

## Design Health Score

| # | Heuristic | Score | Key Issue |
|---|-----------|-------|-----------|
| 1 | Visibility of System Status | 2 | Stats tiles show eternal «…»/«—» when analytics API is down/slow; no skeleton, no error state |
| 2 | Match System / Real World | 3 | Domain language excellent (ставки, режимы, споры, ₾), but raw axios error leaks to users |
| 3 | User Control and Freedom | 3 | Nothing traps; can't cancel an in-flight query (minor) |
| 4 | Consistency and Standards | 3 | Token discipline strong; error red (red-50/200/700) is off-token; Pro-card glow is a third, undocumented shadow |
| 5 | Error Prevention | 3 | Submit disabled on empty; example chips prevent bad queries; free CTA routes by auth state |
| 6 | Recognition Rather Than Recall | 3 | Everything labeled; «Оформление — в личном кабинете» assumes pre-knowledge |
| 7 | Flexibility and Efficiency | 3 | Example chips are real accelerators; Enter submits; nothing for power users beyond that |
| 8 | Aesthetic and Minimalist Design | 4 | Genuinely disciplined; every element earns its place |
| 9 | Error Recovery | 2 | «Request failed with status code 404» shown verbatim, half-English in ka UI; no retry button; stats fail silently |
| 10 | Help and Documentation | 2 | «Как это работает» is good inline onboarding; no FAQ/help beyond footer disclaimer |
| **Total** | | **28/40** | **Good — solid foundation, address weak areas** |

## Anti-Patterns Verdict

**Does this look AI-generated? No.**

**LLM assessment:** The page passes the slop test. No eyebrow-kickers on every section (the hero counter line is one deliberate kicker), the 1-2-3 markers sit on a real sequence («Как это работает»), pricing cards have hierarchy (Pro visually promoted), color discipline is real (blue ≈ citations + actions only), and the citation-tick motif (hero eyebrow → SectionTitle → footer columns → SourceChip) is recognizable brand grammar, not decor. Second-order check: "Apple-like near-white + single blue" is itself a saturated family, but the citation motif and honest-numbers copy pull it out of anonymity. Borderline: the Pro card pairs a 1px primary border with a wide 24px blue glow (ghost-card pattern) — the one decorative moment on the page, and it contradicts the documented «Правило шёпота».

**Deterministic scan:** CLI detector: exit 0, zero findings across page.tsx + all components — rare. Runtime detector (injected in live page): 3 findings — `line-length` ~96ch at page.tsx:105 (stats intro, max-w-2xl at 14px), `line-length` ~166ch at page.tsx:196 (pricing note — false positive in spirit: one-line centered caption, not prose), `single-font` (Inter only — deliberate doctrine, «Правило одного семейства», not a defect). Citation tick triggered nothing; no false positives to discount there.

**Agreement:** Detector confirmed the visual system is clean; the real issues are state-handling and i18n depth, which only the human-style review caught.

## Overall Impression

A disciplined, trustworthy surface that matches the «дорогой консультант» brief — until something fails. The visual system is airtight; the failure states aren't. For a product whose whole pitch is verifiable honesty, the stats section shipping «…» forever and error copy leaking axios internals are the two places where the design contradicts the brand promise. Biggest opportunity: make failure states as honest as the success states.

## What's Working

1. **The citation-tick motif is carried, not decorated.** Same 3px bar in hero eyebrow position, section titles, footer column headers, and source chips. This is what «узнаваемость на дисциплине» looks like in practice.
2. **Georgian is engineered, not tolerated.** Hero type steps down for ka (28→48px vs 36→56px), zero horizontal overflow at 390px in ka, header fits all five nav items + lang switch. The +35% rule is honored in code, verified live.
3. **Zero detector findings on markup.** The page survives an adversarial slop scan clean — almost no AI-built landing does.

## Priority Issues

1. **[P1] Stats section fails silently into «…» / «—».** With `/api/v1/analytics/decisions` unavailable, all three StatTiles render placeholder ellipses indefinitely — verified live. Why it matters: this section carries the brand's core claim (честные живые числа); an eternal «…» reads as a broken promise, and PRODUCT.md's own principle says «Нет данных — говорим прямо». Fix: add a real fallback — cached last-known values with an «обновлено N дней назад» stamp, or an explicit «статистика временно недоступна» state, or server-render the numbers. Suggested command: $impeccable harden
2. **[P1] Error copy leaks internals and breaks the language contract.** «Не получилось получить ответ: Request failed with status code 404. Попробуйте ещё раз.» — and in ka UI the axios string stays English mid-sentence. Also: SourceChip TYPE_LABELS are hardcoded Russian («закон», «подзаконный акт»), so ka/en users see Russian type labels inside the signature component. Why it matters: the high-stakes moment (trusting an answer) is exactly where jargon kills confidence — Nino and Jordan both bounce here. Fix: map HTTP/network failures to localized human copy, add a retry button, localize TYPE_LABELS via i18n keys. Suggested command: $impeccable clarify
3. **[P2] `<html lang="ru">` is hardcoded while the UI switches ka/en client-side.** Metadata (title/description) is Russian-only too. Why it matters: screen readers pronounce Georgian text with Russian rules (WCAG 3.1.1), and ka/en SEO is nil for a product whose expat audience searches in English. Fix: sync `document.documentElement.lang` on language switch as a minimum; consider localized metadata/routes later. Suggested command: $impeccable harden
4. **[P2] Touch targets below 44px on mobile.** Example question chips (~26px tall), language switch segments (~26px), footer/nav links. Why it matters: Casey's one-thumb flow — the example chips are the primary mobile activation path and they're the smallest targets on the page. Fix: min-height 44px hit area on mobile (padding or ::after hit-area expansion), keep visual size if desired. Suggested command: $impeccable adapt
5. **[P3] Off-system styling drift.** Pro card: 1px primary border + 0 4px 24px blue glow (third shadow, ghost-card pairing, contradicts «Правило шёпота»); error box: ad-hoc red-50/200/700 outside the token set (no error token exists); pricing bullets are horizontal dashes while the brand tick is vertical — two dialects of one motif. Fix: define an error color token; replace the Pro glow with border + «рекомендуем» label or secondary wash; unify bullet motif orientation. Suggested command: $impeccable polish

## Persona Red Flags

**Jordan (expat first-timer):** Example chips teach what to ask — good. Breaks: the 404 error message jargon at the exact moment of first trust; «Оформление — в личном кабинете, оплата по счёту» assumes knowing what личный кабинет is before registering; no FAQ/help anywhere — his only path is the footer email.

**Casey (mobile, one thumb):** No horizontal overflow, burger is 40px (passable). Breaks: example chips ~26px tall are the primary activation tap and the smallest target; language switch segments ~26px; chat input sits at top of a long page — after reading pricing she has to scroll all the way back (no floating «спросить» affordance).

**Riley (stress tester):** Refresh mid-answer loses question and answer (acceptable for a landing, but no draft preservation). Language edge: asks in Russian while ka UI is active — `submitQuery(text, lang)` sends `lang=ka`, so the answer language may not match the question language. Analytics 404 → eternal «…» found immediately. Console shows repeated failed fetch noise.

**Nino (Georgian accountant, skeptical of AI):** ka typography is genuinely good (Noto Sans Georgian, stepped hero). Breaks: SourceChip — the one component built to earn her trust — shows document types in Russian in her ka UI; the error message is half-English; and if stats show «…» she reads the whole «честные числа» pitch as vaporware.

## Minor Observations

- Stats intro paragraph at max-w-2xl / 14px runs ~96 chars/line (detector-confirmed); max-w-xl would land in the 65–75ch band.
- Analytics fetch has no timeout/retry and logs 404 noise to console.
- «Цены предварительные» is honest (on-brand) but sits at the end of the pricing read — consider whether it needs that prominence.
- The chat answer paragraph (15px in max-w-2xl) will also exceed 75ch on long answers.
- `.dark` theme tokens exist and are documented, but no toggle is exposed anywhere — dead code or future feature?

## Questions to Consider

1. What does a first-time visitor see in the stats section on a Monday morning if the API hiccups — and is «…» an acceptable answer for a product selling verifiable numbers?
2. Should the demo answer follow the UI language or the question's language? An expat asking in English from the ka UI is a real scenario.
3. Is the blue glow really the strongest way to say «рекомендуем» on the Pro plan — or would a plain word in the brand's own voice do it better?
