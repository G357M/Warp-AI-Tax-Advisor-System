'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { ChatPanel } from '@/components/ChatPanel';
import { isLoggedIn } from '@/lib/auth';
import { StatTile } from '@/components/ui/StatTile';
import { Button } from '@/components/ui/Button';
import { PLANS } from '@/lib/plans';
import { useT, DATE_LOCALES } from '@/lib/i18n';

interface DecisionStats {
  coverage: { decisions_in_corpus: number; decisions_extracted: number; documents_total?: number };
  overall: { total: number; taxpayer_relief_rate: number | null };
  top_articles: { article: string; total: number; taxpayer_relief_rate: number | null }[];
}

const PLAN_FEATURE_KEYS: Record<string, string[]> = {
  free: ['plan.free.f1', 'plan.free.f2', 'plan.free.f3'],
  pro: ['plan.pro.f1', 'plan.pro.f2', 'plan.pro.f3', 'plan.pro.f4'],
  business: ['plan.business.f1', 'plan.business.f2', 'plan.business.f3'],
};

export default function Home() {
  const router = useRouter();
  const { lang, t } = useT();
  const [stats, setStats] = useState<DecisionStats | null>(null);

  useEffect(() => {
    fetch('/api/v1/analytics/decisions')
      .then((r) => (r.ok ? r.json() : null))
      .then(setStats)
      .catch(() => null);
  }, []);

  const locale = DATE_LOCALES[lang];
  const docCount = stats?.coverage.documents_total ?? null;
  const reliefPct =
    stats?.overall.taxpayer_relief_rate != null
      ? `${Math.round(stats.overall.taxpayer_relief_rate * 100)}%`
      : '—';

  const steps = [1, 2, 3].map((n) => ({
    n: String(n),
    title: t(`steps.${n}.title`),
    text: t(`steps.${n}.text`),
  }));

  return (
    <main>
      {/* Hero */}
      <section className="px-6 pb-20 pt-20 text-center sm:pt-28">
        <div className="mx-auto max-w-page">
          <div className="mb-5 text-[13px] font-medium text-secondary-foreground">
            {docCount
              ? t('hero.eyebrow', { n: docCount.toLocaleString(locale) })
              : t('hero.eyebrow0')}
          </div>
          <h1
            className={`mx-auto max-w-3xl font-semibold tracking-display ${
              // Georgian runs ~35% longer: step the display size down so the
              // hero stays 2–3 lines on a phone instead of six.
              lang === 'ka'
                ? 'text-[28px] leading-[1.2] sm:text-5xl sm:leading-[1.12]'
                : 'text-4xl leading-tight sm:text-[56px] sm:leading-[1.08]'
            }`}
          >
            {t('hero.title1')}
            <br />
            {t('hero.title2')}
          </h1>
          <p className="mx-auto mt-5 max-w-xl text-[17px] leading-relaxed text-muted-foreground">
            {t('hero.sub')}
          </p>
          <div className="mt-10">
            <ChatPanel />
          </div>
        </div>
      </section>

      {/* How it works */}
      <section className="border-t px-6 py-20">
        <div className="mx-auto max-w-page">
          <h2 className="text-2xl font-semibold tracking-display">{t('steps.title')}</h2>
          <div className="mt-10 grid gap-10 sm:grid-cols-3">
            {steps.map((s) => (
              <div key={s.n}>
                <div className="text-[13px] font-medium text-secondary-foreground">{s.n}</div>
                <h3 className="mt-2 text-[17px] font-semibold">{s.title}</h3>
                <p className="mt-2 text-[14px] leading-relaxed text-muted-foreground">{s.text}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Live dispute statistics */}
      <section id="stats" className="scroll-mt-20 border-t px-6 py-20">
        <div className="mx-auto max-w-page">
          <h2 className="text-2xl font-semibold tracking-display">{t('stats.title')}</h2>
          <p className="mt-3 max-w-2xl text-[14px] leading-relaxed text-muted-foreground">
            {t('stats.sub')}
          </p>
          <div className="mt-8 grid gap-4 sm:grid-cols-3">
            <StatTile
              value={stats ? stats.overall.total.toLocaleString(locale) : '…'}
              label={t('stats.analyzed')}
              detail={
                stats
                  ? t('stats.of', { n: stats.coverage.decisions_in_corpus.toLocaleString(locale) })
                  : undefined
              }
            />
            <StatTile
              value={reliefPct}
              label={t('stats.relief')}
              detail={t('stats.relief_detail')}
            />
            <StatTile
              value={
                stats?.top_articles?.[0]
                  ? t('stats.art', { n: stats.top_articles[0].article })
                  : '…'
              }
              label={t('stats.top_article')}
              detail={
                stats?.top_articles?.[0]
                  ? t('stats.decisions', { n: stats.top_articles[0].total })
                  : undefined
              }
            />
          </div>
        </div>
      </section>

      {/* Pricing */}
      <section id="pricing" className="scroll-mt-20 border-t px-6 py-20">
        <div className="mx-auto max-w-page">
          <h2 className="text-center text-2xl font-semibold tracking-display">{t('pricing.title')}</h2>
          <div className="mt-10 grid gap-5 sm:grid-cols-3">
            {PLANS.map((plan) => (
              <div
                key={plan.id}
                className={`flex flex-col rounded-lg border bg-white p-7 ${
                  plan.highlighted ? 'border-primary shadow-[0_4px_24px_rgba(14,98,217,0.10)]' : ''
                }`}
              >
                <div className="text-[15px] font-semibold">{plan.name}</div>
                <div className="mt-3 flex items-baseline gap-1">
                  <span className="text-[34px] font-semibold leading-none tracking-display">
                    {plan.priceGel === 0 ? '0 ₾' : `${plan.priceGel} ₾`}
                  </span>
                  {plan.priceGel > 0 && (
                    <span className="text-[13px] text-muted-foreground">{t('pricing.month')}</span>
                  )}
                </div>
                <div className="mt-1 text-[13px] text-muted-foreground">
                  {t(`plan.${plan.id}.tagline`)}
                </div>
                <ul className="mt-5 flex-1 space-y-2.5">
                  {(PLAN_FEATURE_KEYS[plan.id] ?? []).map((key) => (
                    <li key={key} className="flex gap-2 text-[14px] leading-snug">
                      <span aria-hidden className="mt-[7px] h-1 w-3 shrink-0 rounded-full bg-primary/60" />
                      {t(key)}
                    </li>
                  ))}
                </ul>
                <Button
                  variant={plan.highlighted ? 'primary' : 'secondary'}
                  className="mt-7 w-full"
                  onClick={() => {
                    if (plan.id === 'free') {
                      if (isLoggedIn()) {
                        document.getElementById('chat')?.scrollIntoView({ behavior: 'smooth' });
                      } else {
                        router.push('/register');
                      }
                    } else {
                      router.push(isLoggedIn() ? '/account' : '/register');
                    }
                  }}
                >
                  {plan.id === 'free' ? t('pricing.free_cta') : t('pricing.paid_cta')}
                </Button>
              </div>
            ))}
          </div>
          <p className="mt-6 text-center text-[13px] text-muted-foreground">{t('pricing.note')}</p>
        </div>
      </section>
    </main>
  );
}
