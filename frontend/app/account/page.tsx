'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { authFetch, clearToken, isLoggedIn } from '@/lib/auth';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { useT, DATE_LOCALES } from '@/lib/i18n';

interface Account {
  email: string;
  username: string;
  full_name: string | null;
  role: string;
  plan: string;
  usage: { questions_today: number; daily_limit: number | null };
}

interface SubscriptionInfo {
  plan: string;
  status: string | null;
  period_end: string | null;
}

const PLAN_LABELS: Record<string, string> = {
  free: 'Free',
  pro: 'Pro',
  business: 'Business',
};

export default function AccountPage() {
  const router = useRouter();
  const { lang, t } = useT();
  const [account, setAccount] = useState<Account | null>(null);
  const [sub, setSub] = useState<SubscriptionInfo | null>(null);
  const [instructions, setInstructions] = useState<string | null>(null);
  const [bugOpen, setBugOpen] = useState(false);
  const [bugText, setBugText] = useState('');
  const [bugState, setBugState] = useState<'idle' | 'sending' | 'sent' | 'error' | 'short'>('idle');

  useEffect(() => {
    if (!isLoggedIn()) {
      router.replace('/login');
      return;
    }
    authFetch('/api/v1/account')
      .then((r) => (r.ok ? r.json() : Promise.reject()))
      .then(setAccount)
      .catch(() => router.replace('/login'));
    authFetch('/api/v1/billing/subscription')
      .then((r) => (r.ok ? r.json() : null))
      .then(setSub)
      .catch(() => null);
  }, [router]);

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
    const res = await authFetch('/api/v1/billing/checkout', {
      method: 'POST',
      body: JSON.stringify({ plan }),
    });
    if (res.ok) {
      const data = await res.json();
      setInstructions(data.instructions ?? null);
    }
  };

  if (!account) {
    return (
      <main className="mx-auto max-w-page px-6 py-16 text-[14px] text-muted-foreground">
        {t('acc.loading')}
      </main>
    );
  }

  const locale = DATE_LOCALES[lang];

  return (
    <main className="mx-auto min-h-[70vh] max-w-2xl px-6 py-16">
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-display">{t('acc.title')}</h1>
          <p className="mt-1 text-[14px] text-muted-foreground">{account.email}</p>
        </div>
        <div className="flex items-center gap-2">
          {account.role === 'admin' && (
            <Link
              href="/admin"
              className="rounded-full bg-primary px-4 py-2 text-[13px] font-medium text-white transition-all duration-300 hover:bg-[#B91C1C]"
            >
              {t('acc.admin')}
            </Link>
          )}
          <Button
            variant="ghost"
            onClick={() => {
              clearToken();
              router.push('/');
            }}
          >
            {t('acc.logout')}
          </Button>
        </div>
      </div>

      <Card className="mt-8 p-6">
        <div className="flex items-center justify-between">
          <div>
            <div className="text-xs text-muted-foreground">{t('acc.plan')}</div>
            <div className="mt-1 text-[22px] font-semibold tracking-display">
              {PLAN_LABELS[account.plan] ?? account.plan}
            </div>
            {sub?.period_end && (
              <div className="mt-1 text-[13px] text-muted-foreground">
                {t('acc.until', { d: new Date(sub.period_end).toLocaleDateString(locale) })}
              </div>
            )}
          </div>
          {account.plan === 'free' && (
            <div className="flex gap-2">
              <Button onClick={() => upgrade('pro')}>{t('acc.upgrade_pro')}</Button>
              <Button variant="glass" onClick={() => upgrade('business')}>
                Business
              </Button>
            </div>
          )}
        </div>
        {instructions && (
          <p className="mt-4 rounded-md bg-secondary px-4 py-3 text-[13px] leading-relaxed text-secondary-foreground">
            {instructions}
          </p>
        )}
      </Card>

      <Card className="mt-4 p-6">
        <div className="text-xs text-muted-foreground">{t('acc.today')}</div>
        <div className="mt-1 text-[22px] font-semibold tracking-display">
          {account.usage.questions_today}
          {account.usage.daily_limit != null && (
            <span className="text-[15px] font-normal text-muted-foreground">
              {' '}
              {t('acc.of', { n: account.usage.daily_limit })}
            </span>
          )}
        </div>
        {account.usage.daily_limit == null && (
          <div className="mt-1 text-[13px] text-muted-foreground">{t('acc.unlimited')}</div>
        )}
      </Card>

      <Card className="mt-4 p-6">
        <div className="flex items-center justify-between gap-4">
          <div>
            <div className="text-[15px] font-semibold tracking-display">{t('acc.bug_title')}</div>
            <p className="mt-1 text-[13px] leading-relaxed text-muted-foreground">
              {t('acc.bug_hint')}
            </p>
          </div>
          {!bugOpen && bugState !== 'sent' && (
            <Button variant="glass" onClick={() => setBugOpen(true)}>
              {t('acc.bug_button')}
            </Button>
          )}
        </div>
        {bugOpen && (
          <div className="mt-4">
            <textarea
              value={bugText}
              onChange={(e) => setBugText(e.target.value)}
              placeholder={t('acc.bug_placeholder')}
              rows={4}
              maxLength={4000}
              className="w-full rounded-md border border-white/15 bg-white/5 px-4 py-3 text-[14px] text-white placeholder:text-white/50"
            />
            <div className="mt-3 flex items-center gap-3">
              <Button onClick={sendBug} disabled={bugState === 'sending'}>
                {bugState === 'sending' ? t('acc.bug_sending') : t('acc.bug_send')}
              </Button>
              <Button
                variant="ghost"
                onClick={() => {
                  setBugOpen(false);
                  setBugState('idle');
                }}
              >
                ✕
              </Button>
              {bugState === 'error' && (
                <span className="text-[13px] text-red-600">{t('acc.bug_error')}</span>
              )}
              {bugState === 'short' && (
                <span className="text-[13px] text-muted-foreground">{t('acc.bug_short')}</span>
              )}
            </div>
          </div>
        )}
        {bugState === 'sent' && (
          <p className="mt-3 text-[13px] text-emerald-600">{t('acc.bug_sent')}</p>
        )}
      </Card>

      <p className="mt-8 text-[13px] text-muted-foreground">
        {t('acc.laws_hint')}{' '}
        <Link href="/laws" className="text-primary hover:underline">
          {t('nav.laws')}
        </Link>
        .
      </p>
    </main>
  );
}
