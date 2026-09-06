/** Runtime plan catalog returned by the backend billing authority. */
export type PlanId = 'free' | 'pro' | 'business';

export interface BillingPlan {
  id: PlanId;
  name: string;
  price_minor: number;
  currency: string;
  billing_period: 'month' | null;
  daily_questions: number | null;
  history_enabled: boolean;
  feature_codes: string[];
  highlighted: boolean;
  pricing_preliminary: boolean;
}

export interface PaymentMethod {
  id: 'manual_invoice' | 'tbc_checkout' | 'bog_checkout';
  provider: 'manual' | 'tbc' | 'bog';
  status: 'available' | 'requires_merchant_activation';
  recurring: boolean;
  contact_email: string | null;
}

export interface BillingCatalog {
  version: string;
  currency_minor_unit: number;
  plans: BillingPlan[];
  payment_methods: PaymentMethod[];
}

/**
 * Build-time fallback only. The live API remains the price authority; keeping
 * this copy lets the public landing page render honestly during an API outage.
 */
export const PLANS: BillingPlan[] = [
  {
    id: 'free',
    name: 'Free',
    price_minor: 0,
    currency: 'GEL',
    billing_period: null,
    daily_questions: 5,
    history_enabled: false,
    feature_codes: ['daily_questions_5', 'precise_sources', 'no_chat_history'],
    highlighted: false,
    pricing_preliminary: true,
  },
  {
    id: 'pro',
    name: 'Pro',
    price_minor: 4900,
    currency: 'GEL',
    billing_period: 'month',
    daily_questions: null,
    history_enabled: true,
    feature_codes: [
      'unlimited_questions',
      'chat_history',
      'dispute_statistics',
      'law_change_timeline',
    ],
    highlighted: true,
    pricing_preliminary: true,
  },
  {
    id: 'business',
    name: 'Business',
    price_minor: 14900,
    currency: 'GEL',
    billing_period: 'month',
    daily_questions: null,
    history_enabled: true,
    feature_codes: ['everything_in_pro', 'company_invoice', 'priority_support'],
    highlighted: false,
    pricing_preliminary: true,
  },
];

export async function loadBillingCatalog(signal?: AbortSignal): Promise<BillingCatalog> {
  const response = await fetch('/api/v1/billing/catalog', { signal });
  if (!response.ok) throw new Error('billing_catalog');
  return response.json();
}

export function formatMinorMoney(
  amountMinor: number,
  currency: string,
  locale: string,
): string {
  if (currency === 'GEL') {
    return `${new Intl.NumberFormat(locale, {
      minimumFractionDigits: amountMinor % 100 === 0 ? 0 : 2,
      maximumFractionDigits: 2,
    }).format(amountMinor / 100)} ₾`;
  }
  return new Intl.NumberFormat(locale, {
    style: 'currency',
    currency,
    minimumFractionDigits: amountMinor % 100 === 0 ? 0 : 2,
    maximumFractionDigits: 2,
  }).format(amountMinor / 100);
}
