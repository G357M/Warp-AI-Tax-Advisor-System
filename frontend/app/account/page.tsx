'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { authFetch, clearToken, isLoggedIn } from '@/lib/auth';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';

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
  const [account, setAccount] = useState<Account | null>(null);
  const [sub, setSub] = useState<SubscriptionInfo | null>(null);
  const [instructions, setInstructions] = useState<string | null>(null);

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
    return <main className="mx-auto max-w-page px-6 py-16 text-[14px] text-muted-foreground">Загружаю…</main>;
  }

  return (
    <main className="mx-auto min-h-[70vh] max-w-2xl px-6 py-16">
      <div className="flex items-start justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-display">Кабинет</h1>
          <p className="mt-1 text-[14px] text-muted-foreground">{account.email}</p>
        </div>
        <Button
          variant="ghost"
          onClick={() => {
            clearToken();
            router.push('/');
          }}
        >
          Выйти
        </Button>
      </div>

      <Card className="mt-8 p-6">
        <div className="flex items-center justify-between">
          <div>
            <div className="text-xs text-muted-foreground">Тариф</div>
            <div className="mt-1 text-[22px] font-semibold tracking-display">
              {PLAN_LABELS[account.plan] ?? account.plan}
            </div>
            {sub?.period_end && (
              <div className="mt-1 text-[13px] text-muted-foreground">
                действует до {new Date(sub.period_end).toLocaleDateString('ru-RU')}
              </div>
            )}
          </div>
          {account.plan === 'free' && (
            <div className="flex gap-2">
              <Button onClick={() => upgrade('pro')}>Перейти на Pro</Button>
              <Button variant="secondary" onClick={() => upgrade('business')}>
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
        <div className="text-xs text-muted-foreground">Вопросы сегодня</div>
        <div className="mt-1 text-[22px] font-semibold tracking-display">
          {account.usage.questions_today}
          {account.usage.daily_limit != null && (
            <span className="text-[15px] font-normal text-muted-foreground">
              {' '}из {account.usage.daily_limit}
            </span>
          )}
        </div>
        {account.usage.daily_limit == null && (
          <div className="mt-1 text-[13px] text-muted-foreground">без ограничений</div>
        )}
      </Card>

      <p className="mt-8 text-[13px] text-muted-foreground">
        Хронология изменений законов — в разделе{' '}
        <Link href="/laws" className="text-primary hover:underline">
          Законы
        </Link>
        .
      </p>
    </main>
  );
}
