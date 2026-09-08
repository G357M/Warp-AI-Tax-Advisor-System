'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import {
  Check,
  CreditCard,
  FileText,
  History,
  Landmark,
  LifeBuoy,
  ReceiptText,
  RefreshCw,
  X,
} from 'lucide-react';
import { authFetch, isLoggedIn, logout } from '@/lib/auth';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { useT, DATE_LOCALES } from '@/lib/i18n';
import {
  BillingCatalog,
  BillingPlan,
  formatMinorMoney,
  loadBillingCatalog,
  PaymentMethod,
  PlanId,
  PLANS,
} from '@/lib/plans';

interface Account {
  email: string;
  username: string;
  full_name: string | null;
  role: string;
  plan: PlanId;
  usage: { questions_today: number; daily_limit: number | null };
}

interface SubscriptionInfo {
  plan: PlanId;
  status: string | null;
  period_start: string | null;
  period_end: string | null;
  auto_renew: boolean;
  payment_provider: string | null;
}

interface BillingCheckout {
  id: string;
  plan: 'pro' | 'business';
  months: number;
  amount_minor: number;
  currency: string;
  provider: 'manual' | 'tbc';
  status: 'pending' | 'paid' | 'expired' | 'cancelled' | 'failed' | 'provider_unknown' | 'provider_review';
  provider_status: string | null;
  provider_redirect_url: string | null;
  provider_checked_at: string | null;
  expires_at: string;
  created_at: string;
}

interface BillingPayment {
  id: string;
  amount_minor: number;
  currency: string;
  provider: string;
  status: 'succeeded' | 'pending' | 'failed';
  created_at: string;
}

interface BillingOverview {
  subscription: SubscriptionInfo;
  checkouts: BillingCheckout[];
  payments: BillingPayment[];
  payment_methods: PaymentMethod[];
}

interface CheckoutResponse {
  checkout: BillingCheckout;
  payment_method: PaymentMethod & { instruction_code?: string; redirect_url?: string | null };
  replayed: boolean;
}

interface ConversationSummary {
  id: string;
  title: string | null;
  created_at: string;
  updated_at: string;
  messages_count: number;
}

const PLAN_LABELS: Record<string, string> = {
  free: 'Free',
  pro: 'Pro',
  business: 'Business',
};

const PLAN_RANK: Record<PlanId, number> = { free: 0, pro: 1, business: 2 };

const FEATURE_KEYS: Record<string, string> = {
  daily_questions_5: 'plan.free.f1',
  precise_sources: 'plan.free.f2',
  no_chat_history: 'plan.free.f3',
  unlimited_questions: 'plan.pro.f1',
  chat_history: 'plan.pro.f2',
  dispute_statistics: 'plan.pro.f3',
  law_change_timeline: 'plan.pro.f4',
  everything_in_pro: 'plan.business.f1',
  company_invoice: 'plan.business.f2',
  priority_support: 'plan.business.f3',
};

const FALLBACK_METHODS: PaymentMethod[] = [
  {
    id: 'manual_invoice',
    provider: 'manual',
    status: 'available',
    recurring: false,
    contact_email: null,
  },
  {
    id: 'tbc_checkout',
    provider: 'tbc',
    status: 'requires_merchant_activation',
    recurring: false,
    contact_email: null,
  },
  {
    id: 'bog_checkout',
    provider: 'bog',
    status: 'requires_merchant_activation',
    recurring: true,
    contact_email: null,
  },
];

function trustedTbcRedirect(value: string | null | undefined): string | null {
  if (!value) return null;
  try {
    const redirect = new URL(value);
    if (
      redirect.protocol !== 'https:'
      || redirect.hostname !== 'tpay.tbcbank.ge'
      || (redirect.port && redirect.port !== '443')
      || redirect.username
      || redirect.password
    ) {
      return null;
    }
    return redirect.toString();
  } catch {
    return null;
  }
}

function PaymentMethodIcon({ provider }: { provider: PaymentMethod['provider'] }) {
  if (provider === 'manual') return <FileText aria-hidden className="h-5 w-5" />;
  if (provider === 'tbc') return <Landmark aria-hidden className="h-5 w-5" />;
  return <CreditCard aria-hidden className="h-5 w-5" />;
}

export default function AccountPage() {
  const router = useRouter();
  const { lang, t } = useT();
  const locale = DATE_LOCALES[lang];
  const checkoutKeys = useRef<Record<string, string>>({});
  const [account, setAccount] = useState<Account | null>(null);
  const [catalog, setCatalog] = useState<BillingCatalog | null>(null);
  const [overview, setOverview] = useState<BillingOverview | null>(null);
  const [latestCheckout, setLatestCheckout] = useState<BillingCheckout | null>(null);
  const [checkoutContact, setCheckoutContact] = useState<string | null>(null);
  const [billingState, setBillingState] = useState<'loading' | 'ready' | 'error'>('loading');
  const [selectedProvider, setSelectedProvider] = useState<'manual' | 'tbc'>('manual');
  const [paymentReturnState, setPaymentReturnState] = useState<
    'idle' | 'checking' | 'paid' | 'pending' | 'review' | 'error'
  >('idle');
  const [conversations, setConversations] = useState<ConversationSummary[]>([]);
  const [historyState, setHistoryState] = useState<'idle' | 'loading' | 'error'>('idle');
  const [upgradingPlan, setUpgradingPlan] = useState<'pro' | 'business' | null>(null);
  const [upgradeState, setUpgradeState] = useState<'idle' | 'error'>('idle');
  const [termsAccepted, setTermsAccepted] = useState(false);
  const [immediateServiceRequested, setImmediateServiceRequested] = useState(false);
  const [bugOpen, setBugOpen] = useState(false);
  const [bugText, setBugText] = useState('');
  const [bugState, setBugState] = useState<'idle' | 'sending' | 'sent' | 'error' | 'short'>('idle');

  const loadBilling = useCallback(async () => {
    setBillingState('loading');
    try {
      const response = await authFetch('/api/v1/billing/overview');
      if (!response.ok) throw new Error('billing');
      let data: BillingOverview = await response.json();
      const returnParams = new URLSearchParams(window.location.search);
      const returnedFromTbc = returnParams.get('payment_return') === 'tbc';
      const returnedCheckoutId = returnParams.get('checkout_id');
      const returnedCheckout = data.checkouts.find(
        (row) => row.provider === 'tbc'
          && (!returnedCheckoutId || row.id === returnedCheckoutId)
          && ['pending', 'expired', 'failed'].includes(row.status),
      );
      if (returnedFromTbc) {
        if (returnedCheckout) {
          setPaymentReturnState('checking');
          const refresh = await authFetch(`/api/v1/billing/checkout/${returnedCheckout.id}/refresh`, {
            method: 'POST',
          });
          if (refresh.ok) {
            const refreshed: { checkout: BillingCheckout } = await refresh.json();
            setPaymentReturnState(
              refreshed.checkout.status === 'paid'
                ? 'paid'
                : refreshed.checkout.status === 'provider_review'
                  ? 'review'
                  : 'pending',
            );
            const updated = await authFetch('/api/v1/billing/overview');
            if (updated.ok) data = await updated.json();
          } else {
            setPaymentReturnState('error');
          }
        } else {
          setPaymentReturnState('error');
        }
        const cleanUrl = new URL(window.location.href);
        cleanUrl.searchParams.delete('payment_return');
        cleanUrl.searchParams.delete('checkout_id');
        window.history.replaceState({}, '', `${cleanUrl.pathname}${cleanUrl.search}${cleanUrl.hash}`);
      }
      setOverview(data);
      setLatestCheckout(
        data.checkouts.find((row) =>
          ['pending', 'provider_unknown', 'provider_review'].includes(row.status),
        ) ?? null,
      );
      setCheckoutContact(
        data.payment_methods.find((method) => method.provider === 'manual')?.contact_email ?? null,
      );
      setSelectedProvider((current) =>
        data.payment_methods.some(
          (method) => method.provider === current && method.status === 'available',
        )
          ? current
          : 'manual',
      );
      setBillingState('ready');
    } catch {
      setBillingState('error');
    }
  }, [setSelectedProvider]);

  useEffect(() => {
    if (!isLoggedIn()) {
      router.replace('/login');
      return;
    }
    const controller = new AbortController();
    authFetch('/api/v1/account')
      .then((response) => (response.ok ? response.json() : Promise.reject(new Error('account'))))
      .then(async (data: Account) => {
        setAccount(data);
        void loadBilling();
        if (data.plan !== 'free') {
          setHistoryState('loading');
          const response = await authFetch('/api/v1/query/conversations?limit=20');
          if (!response.ok) throw new Error('history');
          setConversations(await response.json());
          setHistoryState('idle');
        }
      })
      .catch((error) => {
        if (error instanceof Error && error.message === 'history') {
          setHistoryState('error');
          return;
        }
        router.replace('/login');
      });
    loadBillingCatalog(controller.signal)
      .then(setCatalog)
      .catch(() => undefined);
    return () => controller.abort();
  }, [loadBilling, router]);

  const sendBug = async () => {
    if (bugText.trim().length < 5) {
      setBugState('short');
      return;
    }
    setBugState('sending');
    try {
      const res = await authFetch('/api/v1/feedback', {
        method: 'POST',
        body: JSON.stringify({ message: bugText.trim(), page: window.location.pathname }),
      });
      if (!res.ok) throw new Error();
      setBugState('sent');
      setBugText('');
      setBugOpen(false);
    } catch {
      setBugState('error');
    }
  };

  const upgrade = async (plan: 'pro' | 'business') => {
    setUpgradingPlan(plan);
    setUpgradeState('idle');
    const key = `${plan}:${selectedProvider}`;
    checkoutKeys.current[key] ??= `checkout:${crypto.randomUUID()}`;
    try {
      const res = await authFetch('/api/v1/billing/checkout', {
        method: 'POST',
        headers: { 'Idempotency-Key': checkoutKeys.current[key] },
        body: JSON.stringify({
          plan,
          provider: selectedProvider,
          language: lang,
          terms_version: catalog?.terms_version ?? '2026-09-08',
          terms_accepted: termsAccepted,
          immediate_service_requested: immediateServiceRequested,
        }),
      });
      if (!res.ok) {
        if (res.status === 409 && selectedProvider === 'manual') delete checkoutKeys.current[key];
        throw new Error();
      }
      const data: CheckoutResponse = await res.json();
      setLatestCheckout(data.checkout);
      setCheckoutContact(data.payment_method.contact_email);
      setOverview((current) =>
        current
          ? {
              ...current,
              checkouts: [
                data.checkout,
                ...current.checkouts.filter((row) => row.id !== data.checkout.id),
              ],
            }
          : current,
      );
      const redirectUrl = data.payment_method.redirect_url;
      if (selectedProvider === 'tbc' && redirectUrl) {
        const trustedRedirect = trustedTbcRedirect(redirectUrl);
        if (!trustedRedirect) throw new Error('untrusted_payment_redirect');
        window.location.assign(trustedRedirect);
      }
    } catch {
      setUpgradeState('error');
    } finally {
      setUpgradingPlan(null);
    }
  };

  const refreshOnlineCheckout = async (checkout: BillingCheckout) => {
    setPaymentReturnState('checking');
    try {
      const response = await authFetch(`/api/v1/billing/checkout/${checkout.id}/refresh`, {
        method: 'POST',
      });
      if (!response.ok) throw new Error('refresh');
      const refreshed: { checkout: BillingCheckout } = await response.json();
      setPaymentReturnState(
        refreshed.checkout.status === 'paid'
          ? 'paid'
          : refreshed.checkout.status === 'provider_review'
            ? 'review'
            : 'pending',
      );
      await loadBilling();
    } catch {
      setPaymentReturnState('error');
    }
  };

  if (!account) {
    return (
      <main className="mx-auto max-w-page px-6 py-16 text-[14px] text-muted-foreground">
        {t('acc.loading')}
      </main>
    );
  }

  const plans: BillingPlan[] = catalog?.plans ?? PLANS;
  const methods = overview?.payment_methods ?? catalog?.payment_methods ?? FALLBACK_METHODS;
  const subscription = overview?.subscription;
  const activePlan = subscription?.plan ?? account.plan;
  const currentCheckout = latestCheckout;
  const currentCheckoutRedirect = currentCheckout?.provider === 'tbc'
    ? trustedTbcRedirect(currentCheckout.provider_redirect_url)
    : null;
  const currentCheckoutNeedsReview = currentCheckout
    ? ['provider_unknown', 'provider_review'].includes(currentCheckout.status)
    : false;
  const hasPreliminaryPrice = plans.some((plan) => plan.pricing_preliminary);
  const checkoutConfirmed = termsAccepted && immediateServiceRequested;

  return (
    <main className="mx-auto min-h-[70vh] max-w-page px-6 py-12 sm:py-16">
      <div className="flex flex-col items-start justify-between gap-6 sm:flex-row">
        <div>
          <h1 className="font-heading text-4xl font-normal italic tracking-display sm:text-5xl">
            {t('acc.title')}
          </h1>
          <p className="mt-2 max-w-2xl text-[14px] leading-relaxed text-muted-foreground">
            {t('acc.subtitle')}
          </p>
        </div>
        <div className="flex items-center gap-2">
          {account.role === 'admin' && (
            <Link
              href="/admin"
              className="rounded-full bg-primary px-4 py-2 text-[13px] font-medium text-white transition-colors duration-300 hover:bg-[#B91C1C]"
            >
              {t('acc.admin')}
            </Link>
          )}
          <Button
            variant="ghost"
            onClick={async () => {
              await logout();
              router.push('/');
            }}
          >
            {t('acc.logout')}
          </Button>
        </div>
      </div>

      <Card className="mt-10 p-0">
        <div className="grid gap-0 lg:grid-cols-[1fr_340px]">
          <div className="p-7 sm:p-9">
            <div className="flex flex-wrap items-center gap-3">
              <h2 className="font-heading text-4xl italic tracking-display text-white">
                {PLAN_LABELS[activePlan] ?? activePlan}
              </h2>
              <span className="rounded-full bg-white/10 px-3 py-1 text-xs font-medium text-white/80">
                {subscription?.status ? t(`acc.status.${subscription.status}`) : t('acc.status.active')}
              </span>
            </div>
            <p className="mt-3 text-[14px] text-muted-foreground">{account.email}</p>
            {subscription?.period_end && (
              <p className="mt-1 text-[13px] text-muted-foreground">
                {t('acc.until', { d: new Date(subscription.period_end).toLocaleDateString(locale) })}
              </p>
            )}
            {!subscription?.auto_renew && activePlan !== 'free' && (
              <p className="mt-5 max-w-xl text-[13px] leading-relaxed text-white/70">
                {t('acc.no_auto_renew')}
              </p>
            )}
          </div>
          <div className="border-t border-white/10 p-7 lg:border-l lg:border-t-0 lg:p-9">
            <p className="text-xs text-muted-foreground">{t('acc.today')}</p>
            <div className="mt-2 font-heading text-4xl italic tracking-display text-white">
              {account.usage.questions_today}
              {account.usage.daily_limit != null && (
                <span className="ml-2 font-body text-[15px] font-normal not-italic text-muted-foreground">
                  {t('acc.of', { n: account.usage.daily_limit })}
                </span>
              )}
            </div>
            <p className="mt-2 text-[13px] text-muted-foreground">
              {account.usage.daily_limit == null ? t('acc.unlimited') : t('acc.quota_resets')}
            </p>
          </div>
        </div>
      </Card>

      <section className="mt-14">
        <div className="flex flex-col justify-between gap-3 sm:flex-row sm:items-end">
          <div>
            <h2 className="font-heading text-3xl italic tracking-display">{t('acc.manage_plan')}</h2>
            <p className="mt-2 max-w-2xl text-[14px] leading-relaxed text-muted-foreground">
              {t('acc.manage_plan_hint')}
            </p>
          </div>
          <span className="text-xs text-muted-foreground">
            {hasPreliminaryPrice ? t('acc.pricing_preliminary') : t('acc.pricing_final')}
          </span>
        </div>

        <div className="liquid-glass mt-6 rounded-2xl p-6 sm:p-7">
          <div className="flex flex-col gap-5">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <h3 className="text-[15px] font-semibold text-white">{t('acc.legal_title')}</h3>
              <Link href="/legal/terms" target="_blank" className="text-xs text-primary transition-colors hover:text-white">
                {t('acc.legal_read')} ↗
              </Link>
            </div>
            <label className="flex cursor-pointer items-start gap-3 text-[13px] font-light leading-6 text-white/70">
              <input
                type="checkbox"
                checked={termsAccepted}
                onChange={(event) => setTermsAccepted(event.target.checked)}
                className="mt-1 h-4 w-4 shrink-0 accent-red-600"
              />
              <span>
                {t('acc.legal_terms_accept')}{' '}
                <Link href="/legal/refunds" target="_blank" className="text-primary underline-offset-4 hover:underline">{t('legal.refunds')}</Link>
              </span>
            </label>
            <label className="flex cursor-pointer items-start gap-3 text-[13px] font-light leading-6 text-white/70">
              <input
                type="checkbox"
                checked={immediateServiceRequested}
                onChange={(event) => setImmediateServiceRequested(event.target.checked)}
                className="mt-1 h-4 w-4 shrink-0 accent-red-600"
              />
              <span>{t('acc.legal_immediate')}</span>
            </label>
            <a href="#payment-methods" className="w-fit text-xs text-white/50 transition-colors hover:text-white">
              {t('acc.method_jump')} ↓
            </a>
          </div>
        </div>

        <Card className="mt-5 p-0">
          <div className="divide-y divide-white/10">
            {plans.map((plan) => {
              const isCurrent = activePlan === plan.id;
              const isFree = plan.id === 'free';
              const isLower = PLAN_RANK[plan.id] < PLAN_RANK[activePlan];
              const canChoose = !isFree && !isLower;
              return (
                <div
                  key={plan.id}
                  className="grid gap-5 p-6 sm:grid-cols-[150px_1fr_auto] sm:items-center sm:p-7"
                >
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="font-heading text-2xl italic text-white">{plan.name}</span>
                      {plan.highlighted && (
                        <span className="h-2 w-2 rounded-full bg-primary" title={t('pricing.recommended')} />
                      )}
                    </div>
                    <div className="mt-1 text-[13px] text-muted-foreground">
                      {plan.price_minor === 0
                        ? t('acc.free_price')
                        : `${formatMinorMoney(plan.price_minor, plan.currency, locale)} ${t('pricing.month')}`}
                    </div>
                  </div>
                  <ul className="grid gap-2 text-[13px] text-white/75 sm:grid-cols-2">
                    {plan.feature_codes.map((feature) => (
                      <li key={feature} className="flex items-start gap-2">
                        <Check aria-hidden className="mt-0.5 h-3.5 w-3.5 shrink-0 text-primary" />
                        <span>{t(FEATURE_KEYS[feature] ?? feature)}</span>
                      </li>
                    ))}
                  </ul>
                  <Button
                    variant={plan.highlighted && !isCurrent ? 'primary' : 'glass'}
                    disabled={!canChoose || upgradingPlan !== null || !checkoutConfirmed}
                    onClick={() => !isFree && upgrade(plan.id as 'pro' | 'business')}
                    className="w-full sm:w-auto"
                  >
                    {upgradingPlan === plan.id
                        ? t('acc.checkout_creating')
                        : isCurrent && !isFree
                          ? t('acc.renew_plan')
                          : isCurrent
                            ? t('acc.current_plan')
                            : isLower
                              ? t('acc.included')
                              : t('acc.buy_plan', {
                                  plan: plan.name,
                                  amount: formatMinorMoney(plan.price_minor, plan.currency, locale),
                                })}
                  </Button>
                </div>
              );
            })}
          </div>
        </Card>

        {upgradeState === 'error' && (
          <p className="mt-4 text-[13px] text-error-foreground" role="alert">
            {t('acc.upgrade_error')}
          </p>
        )}
      </section>

      <section id="payment-methods" className="mt-14 scroll-mt-32">
        <h2 className="font-heading text-3xl italic tracking-display">{t('acc.payment_methods')}</h2>
        <p className="mt-2 max-w-2xl text-[14px] leading-relaxed text-muted-foreground">
          {t('acc.payment_methods_hint')}
        </p>

        <Card className="mt-6 p-0">
          <div className="divide-y divide-white/10">
            {methods.map((method) => {
              const available = method.status === 'available';
              const selectable = available && (method.provider === 'manual' || method.provider === 'tbc');
              const selected = selectable && selectedProvider === method.provider;
              return (
                <div
                  key={method.id}
                  className="grid grid-cols-[auto_1fr] items-start gap-x-4 gap-y-4 p-6 sm:grid-cols-[auto_1fr_auto] sm:items-center sm:p-7"
                >
                  <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-white/[0.08] text-white">
                    <PaymentMethodIcon provider={method.provider} />
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="flex flex-wrap items-center gap-2">
                      <h3 className="text-[15px] font-semibold text-white">
                        {t(`acc.method.${method.provider}.title`)}
                      </h3>
                      <span
                        className={`rounded-full px-2.5 py-1 text-[11px] font-medium ${
                          available ? 'bg-emerald-400/10 text-emerald-300' : 'bg-white/[0.08] text-white/55'
                        }`}
                      >
                        {available ? t('acc.method.available') : t('acc.method.preparing')}
                      </span>
                    </div>
                    <p className="mt-1 text-[13px] leading-relaxed text-muted-foreground">
                      {t(`acc.method.${method.provider}.hint`)}
                    </p>
                  </div>
                  {selectable && (
                    <Button
                      variant={selected ? 'primary' : 'glass'}
                      aria-pressed={selected}
                      onClick={() => setSelectedProvider(method.provider as 'manual' | 'tbc')}
                      className="col-span-2 w-full sm:col-span-1 sm:w-auto"
                    >
                      {selected ? t('acc.method.selected') : t('acc.method.select')}
                    </Button>
                  )}
                </div>
              );
            })}
          </div>
        </Card>

        {billingState === 'error' && (
          <div className="mt-4 flex flex-wrap items-center gap-3 text-[13px] text-error-foreground" role="alert">
            <span>{t('acc.billing_error')}</span>
            <Button variant="ghost" onClick={loadBilling}>{t('stats.retry')}</Button>
          </div>
        )}

        {paymentReturnState !== 'idle' && (
          <p
            className={`mt-4 text-[13px] ${
              paymentReturnState === 'paid'
                ? 'text-emerald-300'
                : paymentReturnState === 'review' || paymentReturnState === 'error'
                  ? 'text-error-foreground'
                  : 'text-white/65'
            }`}
            role="status"
          >
            {t(`acc.payment_return.${paymentReturnState}`)}
          </p>
        )}

        {currentCheckout && (
          <div className="mt-6 rounded-2xl bg-secondary p-6 sm:p-7" role="status">
            <div className="flex flex-col justify-between gap-5 sm:flex-row sm:items-start">
              <div className="flex gap-4">
                <ReceiptText aria-hidden className="mt-1 h-5 w-5 shrink-0 text-primary" />
                <div>
                  <h3 className="text-[16px] font-semibold text-white">
                    {currentCheckoutNeedsReview ? t('acc.checkout_review_title') : t('acc.checkout_ready')}
                  </h3>
                  <p className="mt-2 max-w-2xl text-[13px] leading-relaxed text-white/65">
                    {currentCheckoutNeedsReview
                      ? t('acc.checkout_review_hint')
                      : currentCheckout.provider === 'tbc'
                        ? t('acc.checkout_online_instructions', {
                            plan: PLAN_LABELS[currentCheckout.plan],
                            amount: formatMinorMoney(
                              currentCheckout.amount_minor,
                              currentCheckout.currency,
                              locale,
                            ),
                          })
                        : t('acc.checkout_instructions', {
                            plan: PLAN_LABELS[currentCheckout.plan],
                            amount: formatMinorMoney(
                              currentCheckout.amount_minor,
                              currentCheckout.currency,
                              locale,
                            ),
                            email: checkoutContact ?? t('acc.support_email_pending'),
                          })}
                  </p>
                  <div className="mt-4 flex flex-wrap gap-x-6 gap-y-2 text-xs text-white/50">
                    <span>
                      {t('acc.checkout_reference')}: <span className="font-mono text-white/80">{currentCheckout.id}</span>
                    </span>
                    <span>
                      {t('acc.checkout_expires', {
                        d: currentCheckout.provider === 'tbc'
                          ? new Date(currentCheckout.expires_at).toLocaleString(locale)
                          : new Date(currentCheckout.expires_at).toLocaleDateString(locale),
                      })}
                    </span>
                    {currentCheckout.provider_status && (
                      <span>{t('acc.provider_status')}: {currentCheckout.provider_status}</span>
                    )}
                  </div>
                </div>
              </div>
              {currentCheckout.provider === 'manual' && checkoutContact && (
                <a
                  href={`mailto:${checkoutContact}?subject=${encodeURIComponent(`Tax Advisor ${currentCheckout.plan} ${currentCheckout.id}`)}`}
                  className="inline-flex h-11 shrink-0 items-center justify-center rounded-full bg-primary px-5 text-sm font-medium text-white transition-colors duration-300 hover:bg-[#B91C1C]"
                >
                  {t('acc.request_invoice')}
                </a>
              )}
              {currentCheckout.provider === 'tbc' && !currentCheckoutNeedsReview && (
                <div className="flex shrink-0 flex-wrap gap-2">
                  {currentCheckoutRedirect && (
                    <a
                      href={currentCheckoutRedirect}
                      className="inline-flex h-11 items-center justify-center rounded-full bg-primary px-5 text-sm font-medium text-white transition-colors duration-300 hover:bg-[#B91C1C]"
                    >
                      {t('acc.continue_to_bank')}
                    </a>
                  )}
                  <Button
                    variant="glass"
                    onClick={() => refreshOnlineCheckout(currentCheckout)}
                    disabled={paymentReturnState === 'checking'}
                  >
                    <RefreshCw aria-hidden className="h-4 w-4" />
                    {t('acc.check_payment')}
                  </Button>
                </div>
              )}
            </div>
          </div>
        )}
      </section>

      <section className="mt-14 grid gap-6 lg:grid-cols-[1.15fr_0.85fr]">
        <Card className="p-6 sm:p-7">
          <div className="flex items-start gap-3">
            <ReceiptText aria-hidden className="mt-0.5 h-5 w-5 text-primary" />
            <div>
              <h2 className="text-[16px] font-semibold tracking-display">{t('acc.billing_history')}</h2>
              <p className="mt-1 text-[13px] leading-relaxed text-muted-foreground">
                {t('acc.billing_history_hint')}
              </p>
            </div>
          </div>
          {billingState === 'loading' && (
            <p className="mt-5 text-[13px] text-muted-foreground">{t('acc.billing_loading')}</p>
          )}
          {billingState === 'ready' && (overview?.payments.length ?? 0) === 0 && (
            <p className="mt-5 text-[13px] text-muted-foreground">{t('acc.billing_empty')}</p>
          )}
          {(overview?.payments.length ?? 0) > 0 && (
            <div className="mt-5 divide-y divide-white/10">
              {overview?.payments.map((payment) => (
                <div key={payment.id} className="flex items-center justify-between gap-4 py-3 first:pt-0">
                  <div>
                    <p className="text-[13px] font-medium text-white">
                      {formatMinorMoney(payment.amount_minor, payment.currency, locale)}
                    </p>
                    <p className="mt-1 text-xs text-muted-foreground">
                      {new Date(payment.created_at).toLocaleDateString(locale)} · {payment.provider}
                    </p>
                  </div>
                  <span className="text-xs text-emerald-300">{t(`acc.payment.${payment.status}`)}</span>
                </div>
              ))}
            </div>
          )}
        </Card>

        <Card className="p-6 sm:p-7">
          <div className="flex items-start gap-3">
            <LifeBuoy aria-hidden className="mt-0.5 h-5 w-5 text-primary" />
            <div className="min-w-0 flex-1">
              <h2 className="text-[16px] font-semibold tracking-display">{t('acc.bug_title')}</h2>
              <p className="mt-1 text-[13px] leading-relaxed text-muted-foreground">
                {t('acc.bug_hint')}
              </p>
            </div>
          </div>
          {!bugOpen && bugState !== 'sent' && (
            <Button variant="glass" className="mt-5" onClick={() => setBugOpen(true)}>
              {t('acc.bug_button')}
            </Button>
          )}
          {bugOpen && (
            <div className="mt-5">
              <textarea
                value={bugText}
                onChange={(event) => setBugText(event.target.value)}
                placeholder={t('acc.bug_placeholder')}
                rows={4}
                maxLength={4000}
                className="w-full rounded-xl border border-white/15 bg-white/5 px-4 py-3 text-[14px] text-white placeholder:text-white/50"
              />
              <div className="mt-3 flex flex-wrap items-center gap-3">
                <Button onClick={sendBug} disabled={bugState === 'sending'}>
                  {bugState === 'sending' ? t('acc.bug_sending') : t('acc.bug_send')}
                </Button>
                <Button
                  variant="ghost"
                  aria-label={t('acc.bug_cancel')}
                  onClick={() => {
                    setBugOpen(false);
                    setBugState('idle');
                  }}
                >
                  <X aria-hidden className="h-4 w-4" />
                </Button>
                {bugState === 'error' && <span className="text-[13px] text-error-foreground">{t('acc.bug_error')}</span>}
                {bugState === 'short' && <span className="text-[13px] text-muted-foreground">{t('acc.bug_short')}</span>}
              </div>
            </div>
          )}
          {bugState === 'sent' && <p className="mt-4 text-[13px] text-emerald-300">{t('acc.bug_sent')}</p>}
        </Card>
      </section>

      <Card className="mt-6 p-6 sm:p-7">
        <div className="flex items-start gap-3">
          <History aria-hidden className="mt-0.5 h-5 w-5 text-primary" />
          <div>
            <h2 className="text-[16px] font-semibold tracking-display">{t('acc.history')}</h2>
            <p className="mt-1 text-[13px] leading-relaxed text-muted-foreground">
              {activePlan === 'free' ? t('acc.history_locked') : t('acc.history_hint')}
            </p>
          </div>
        </div>
        {activePlan !== 'free' && historyState === 'loading' && (
          <p className="mt-5 text-[13px] text-muted-foreground">{t('acc.history_loading')}</p>
        )}
        {activePlan !== 'free' && historyState === 'error' && (
          <p className="mt-5 text-[13px] text-error-foreground">{t('acc.history_error')}</p>
        )}
        {activePlan !== 'free' && historyState === 'idle' && conversations.length === 0 && (
          <p className="mt-5 text-[13px] text-muted-foreground">{t('acc.history_empty')}</p>
        )}
        {activePlan === 'free' && (
          <Button variant="glass" className="mt-5" onClick={() => upgrade('pro')} disabled={upgradingPlan !== null}>
            {t('acc.upgrade_pro')}
          </Button>
        )}
        {conversations.length > 0 && (
          <div className="mt-5 divide-y divide-white/10">
            {conversations.map((conversation) => (
              <Link
                key={conversation.id}
                href={`/account/conversations/${conversation.id}`}
                className="flex min-h-[56px] items-center justify-between gap-4 py-3 text-left transition-colors hover:text-white"
              >
                <span className="min-w-0 truncate text-[14px] text-white/90">
                  {conversation.title || t('acc.history_untitled')}
                </span>
                <span className="shrink-0 text-xs text-muted-foreground">
                  {new Date(conversation.updated_at).toLocaleDateString(locale)} · {conversation.messages_count}
                </span>
              </Link>
            ))}
          </div>
        )}
      </Card>

      <p className="mt-8 text-[13px] text-muted-foreground">
        {t('acc.laws_hint')}{' '}
        <Link href="/laws" className="text-primary underline-offset-4 hover:underline">
          {t('nav.laws')}
        </Link>
        .
      </p>
    </main>
  );
}
