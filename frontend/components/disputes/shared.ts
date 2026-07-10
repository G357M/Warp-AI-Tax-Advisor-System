// Shared types and constants for the public dispute-statistics page.

// Outcome palette — validated (dataviz six checks, dark surface); mirrors the
// admin analytics dashboard.
export const OUTCOME_META = [
  { key: 'satisfied', color: '#059669' },
  { key: 'partially_satisfied', color: '#d97706' },
  { key: 'rejected', color: '#3b82f6' },
] as const;

export type OutcomeKey = (typeof OUTCOME_META)[number]['key'];

// Appeal-ladder order: dispute councils first, then the courts.
export const BODY_ORDER = [
  'revenue_service_council',
  'mof_dispute_council',
  'city_court',
  'appeals_court',
  'supreme_court',
] as const;

export interface OutcomeRow {
  total: number;
  satisfied: number;
  partially_satisfied: number;
  rejected: number;
  unclear: number;
  taxpayer_relief_rate: number | null;
}

/** Filter payload for the drill-down dialog; every clickable stat sets one. */
export interface DisputeFilter {
  article?: string;
  body?: string;
  outcome?: string;
  year?: number;
  has_amount?: boolean;
}

export function pct(rate: number | null): string {
  return rate == null ? '—' : `${Math.round(rate * 100)}%`;
}

export function gel(value: number | null, locale: string): string {
  if (value == null) return '—';
  return `${Math.round(value).toLocaleString(locale)} ₾`;
}
