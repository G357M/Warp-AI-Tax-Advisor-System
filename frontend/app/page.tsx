'use client';

import { ReactNode, useEffect, useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { ChatPanel } from '@/components/ChatPanel';
import { isLoggedIn } from '@/lib/auth';
import { Button } from '@/components/ui/Button';
import { PLANS } from '@/lib/plans';
import { useT, formatNum } from '@/lib/i18n';

interface DecisionStats {
  coverage: { decisions_in_corpus: number; decisions_extracted: number; documents_total?: number };
  overall: { total: number; taxpayer_relief_rate: number | null };
  top_articles: { article: string; total: number; taxpayer_relief_rate: number | null }[];
}

const PLAN_FEATURE_KEYS: Record<string, string[]> = {
  free: ['plan.free.f1', 'plan.free.f2', 'plan.free.f3'],
  pro: ['plan.pro.f1', 'plan.pro.f2'],
  business: ['plan.business.f1', 'plan.business.f2', 'plan.business.f3'],
};

const ECOSYSTEM = [
  { name: 'Modern Consulting', href: 'https://modern-consulting.ge' },
  { name: 'ModernAsk', href: 'https://modernask.com' },
  { name: 'TaxMate', href: null },
  { name: 'ModernBot', href: null },
  { name: 'Modern Travel', href: 'https://modern-travel.ge' },
];

/** Section badge — the shared Modern Ecosystem glass pill. */
function Badge({ children }: { children: ReactNode }) {
  return (
    <span className="liquid-glass inline-block rounded-full px-3.5 py-1 font-body text-xs font-medium text-white">
      {children}
    </span>
  );
}

/** Word-by-word blur reveal for the hero heading (CSS-driven, reduced-motion safe). */
function BlurWords({ text, base = 0 }: { text: string; base?: number }) {
  return (
    <>
      {text.split(' ').map((word, i) => (
        <span
          key={`${word}-${i}`}
          className="blur-in inline-block"
          style={{ animationDelay: `${base + i * 100}ms` }}
        >
          {word}
          {' '}
        </span>
      ))}
    </>
  );
}

export default function Home() {
  const router = useRouter();
  const { lang, t } = useT();
  const [stats, setStats] = useState<DecisionStats | null>(null);
  // 'loading' | 'ready' | 'unavailable': the stats section never shows
  // placeholder numbers — if the data didn't arrive, it says so.
  const [statsState, setStatsState] = useState<'loading' | 'ready' | 'unavailable'>('loading');
  const [statsAttempt, setStatsAttempt] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 8000);
    setStatsState('loading');
    fetch('/api/v1/analytics/decisions', { signal: controller.signal })
      .then((r) => (r.ok ? r.json() : null))
      .then((data: DecisionStats | null) => {
        if (data) {
          setStats(data);
          setStatsState('ready');
        } else {
          setStatsState('unavailable');
        }
      })
      .catch(() => setStatsState('unavailable'))
      .finally(() => clearTimeout(timer));
    return () => {
      clearTimeout(timer);
      controller.abort();
    };
  }, [statsAttempt]);

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

  const wordCount = (t('hero.title1') + ' ' + t('hero.title2')).split(' ').length;

  return (
    <main className="overflow-x-clip bg-black">
      {/* Hero */}
      <section className="relative -mt-24 px-6 pb-24 pt-40 text-center sm:pt-48">
        <div aria-hidden className="hero-mesh absolute inset-0 z-0" />
        <div
          aria-hidden
          className="absolute inset-x-0 bottom-0 z-[1] h-72 bg-gradient-to-b from-transparent to-black"
        />
        <div className="relative z-10 mx-auto max-w-page">
          <div className="liquid-glass mb-8 inline-flex items-center gap-2.5 rounded-full py-1.5 pl-1.5 pr-4">
            <span className="rounded-full bg-primary px-2.5 py-0.5 text-xs font-medium text-white">
              {t('hero.tag')}
            </span>
            <span className="text-xs font-light text-white/80">
              {docCount
                ? t('hero.eyebrow', { n: formatNum(lang, docCount) })
                : t('hero.eyebrow0')}
            </span>
          </div>
          <h1
            className={`mx-auto max-w-4xl text-balance font-heading italic leading-[0.95] tracking-tight text-white ${
              // Georgian runs ~35% longer: step the display size down so the
              // hero stays 2–3 lines on a phone instead of six.
              lang === 'ka'
                ? 'text-[30px] leading-[1.08] sm:text-6xl sm:leading-[0.95]'
                : 'text-5xl sm:text-7xl lg:text-[5.25rem]'
            }`}
          >
            <BlurWords text={t('hero.title1')} />
            <br />
            <BlurWords text={t('hero.title2')} base={200} />
          </h1>
          <p
            className="blur-in mx-auto mt-8 max-w-xl font-body text-[15px] font-light leading-relaxed text-white/60 sm:text-[17px]"
            style={{ animationDelay: `${400 + wordCount * 60}ms` }}
          >
            {t('hero.sub')}
          </p>
          <div
            className="blur-in mt-12"
            style={{ animationDelay: `${600 + wordCount * 60}ms` }}
          >
            <ChatPanel />
          </div>
        </div>
      </section>

      {/* Ecosystem bar */}
      <section className="px-6 py-16 text-center">
        <Badge>{t('eco.badge')}</Badge>
        <div className="mt-8 flex flex-wrap items-center justify-center gap-x-10 gap-y-4">
          {ECOSYSTEM.map((p) =>
            p.href ? (
              <a
                key={p.name}
                href={p.href}
                target="_blank"
                rel="noopener noreferrer"
                className="font-heading text-2xl italic text-white/80 underline-offset-8 transition-all duration-300 hover:text-white hover:underline hover:decoration-primary md:text-3xl"
              >
                {p.name}
              </a>
            ) : (
              <span key={p.name} className="font-heading text-2xl italic text-white/50 md:text-3xl">
                {p.name}
              </span>
            ),
          )}
        </div>
      </section>

      {/* How it works */}
      <section className="relative px-6 py-28">
        <div
          aria-hidden
          className="absolute inset-0 z-0"
          style={{
            background:
              'radial-gradient(50% 40% at 50% 45%, hsl(var(--primary) / 0.06), transparent 75%)',
          }}
        />
        <div className="relative z-10 mx-auto max-w-page text-center">
          <Badge>{t('steps.title')}</Badge>
          <h2 className="mx-auto mt-5 max-w-3xl font-heading text-4xl italic leading-[0.95] tracking-tight text-white md:text-5xl">
            {t('steps.heading')}
          </h2>
          <div className="mt-14 grid gap-6 text-left sm:grid-cols-3">
            {steps.map((s) => (
              <div key={s.n} className="liquid-glass rounded-2xl p-8">
                <div className="font-heading text-6xl italic leading-none text-primary/40">{s.n}</div>
                <h3 className="mt-5 font-heading text-xl italic text-white">{s.title}</h3>
                <p className="mt-3 font-body text-sm font-light leading-relaxed text-white/60">
                  {s.text}
                </p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* Live dispute statistics */}
      <section id="stats" className="scroll-mt-28 px-6 py-28">
        <div className="mx-auto max-w-page text-center">
          <Badge>{t('stats.title')}</Badge>
          <p className="mx-auto mt-5 max-w-xl font-body text-sm font-light leading-relaxed text-white/60">
            {t('stats.sub')}
          </p>
          <div className="liquid-glass mt-12 rounded-3xl p-10 md:p-16">
            {statsState === 'loading' && (
              <div className="grid grid-cols-1 gap-10 sm:grid-cols-3" aria-hidden>
                {[0, 1, 2].map((i) => (
                  <div key={i} className="flex animate-pulse flex-col items-center gap-3">
                    <div className="h-12 w-28 rounded-md bg-white/10" />
                    <div className="h-3 w-36 rounded-full bg-white/10" />
                  </div>
                ))}
              </div>
            )}
            {statsState === 'unavailable' && (
              <div
                role="status"
                className="flex flex-col items-center gap-5 sm:flex-row sm:justify-between sm:text-left"
              >
                <p className="max-w-xl font-body text-sm font-light leading-relaxed text-white/60">
                  {t('stats.unavailable')}
                </p>
                <Button variant="glass" onClick={() => setStatsAttempt((n) => n + 1)}>
                  {t('stats.retry')}
                </Button>
              </div>
            )}
            {statsState === 'ready' && stats && (
              <div className="grid grid-cols-1 gap-10 sm:grid-cols-3">
                <Link href="/disputes" className="rounded-2xl p-2 transition-colors hover:bg-white/5">
                  <div className="font-heading text-5xl italic text-white md:text-6xl">
                    {formatNum(lang, stats.overall.total)}
                  </div>
                  <div className="mt-2 font-body text-sm font-light text-white/60">
                    {t('stats.analyzed')}
                  </div>
                </Link>
                <Link href="/disputes" className="rounded-2xl p-2 transition-colors hover:bg-white/5">
                  <div className="font-heading text-5xl italic text-white md:text-6xl">
                    {reliefPct}
                  </div>
                  <div className="mt-2 font-body text-sm font-light text-white/60">
                    {t('stats.relief')}
                  </div>
                </Link>
                <Link href="/disputes" className="rounded-2xl p-2 transition-colors hover:bg-white/5">
                  <div className="font-heading text-5xl italic text-white md:text-6xl">
                    {stats.top_articles?.[0]
                      ? t('stats.art', { n: stats.top_articles[0].article })
                      : '—'}
                  </div>
                  <div className="mt-2 font-body text-sm font-light text-white/60">
                    {t('stats.top_article')}
                  </div>
                </Link>
              </div>
            )}
          </div>
          {statsState === 'ready' && (
            <Link
              href="/disputes"
              className="mt-8 inline-flex items-center gap-2 font-body text-sm text-primary transition-colors hover:text-white"
            >
              {t('stats.more')} →
            </Link>
          )}
        </div>
      </section>

      {/* Pricing */}
      <section id="pricing" className="scroll-mt-28 px-6 py-28">
        <div className="mx-auto max-w-page text-center">
          <Badge>{t('pricing.title')}</Badge>
          <h2 className="mx-auto mt-5 max-w-3xl font-heading text-4xl italic leading-[0.95] tracking-tight text-white md:text-5xl">
            {t('pricing.heading')}
          </h2>
          <div className="mt-14 grid gap-6 text-left md:grid-cols-3">
            {PLANS.map((plan) => (
              <div
                key={plan.id}
                className={`liquid-glass flex flex-col rounded-2xl p-8 ${
                  plan.highlighted ? 'shadow-[0_0_48px_-12px_hsl(var(--primary)/0.45)] ring-1 ring-primary/50' : ''
                }`}
              >
                <div className="flex items-center justify-between gap-2">
                  <div className="font-heading text-2xl italic text-white">{plan.name}</div>
                  {plan.highlighted && (
                    <span className="rounded-full bg-primary px-2.5 py-0.5 text-xs font-medium text-white">
                      {t('pricing.recommended')}
                    </span>
                  )}
                </div>
                <div className="mt-4 flex items-baseline gap-1.5">
                  <span className="font-heading text-5xl italic leading-none text-white">
                    {plan.priceGel === 0 ? '0 ₾' : `${plan.priceGel} ₾`}
                  </span>
                  {plan.priceGel > 0 && (
                    <span className="font-body text-[13px] font-light text-white/50">
                      {t('pricing.month')}
                    </span>
                  )}
                </div>
                <div className="mt-1 font-body text-[13px] font-light text-white/50">
                  {t(`plan.${plan.id}.tagline`)}
                </div>
                <ul className="mt-6 flex-1 space-y-2.5">
                  {(PLAN_FEATURE_KEYS[plan.id] ?? []).map((key) => (
                    <li key={key} className="flex gap-2.5 font-body text-sm font-light leading-snug text-white/80">
                      <span aria-hidden className="mt-[3px] h-3.5 w-[3px] shrink-0 rounded-full bg-primary/70" />
                      {t(key)}
                    </li>
                  ))}
                </ul>
                <Button
                  variant={plan.highlighted ? 'primary' : 'glass'}
                  className="mt-8 w-full"
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
          <p className="mx-auto mt-8 max-w-xl text-center font-body text-[13px] font-light text-white/50">
            {t('pricing.note')}
          </p>
        </div>
      </section>

      {/* CTA */}
      <section className="relative px-6 pb-10 pt-24 text-center">
        <div
          aria-hidden
          className="absolute inset-0 z-0"
          style={{
            background:
              'radial-gradient(55% 55% at 50% 60%, hsl(var(--primary) / 0.09), transparent 75%)',
          }}
        />
        <div className="relative z-10 mx-auto max-w-page">
          <h2 className="mx-auto max-w-3xl font-heading text-5xl italic leading-[0.95] tracking-tight text-white md:text-6xl lg:text-7xl">
            {t('cta.title')}
          </h2>
          <p className="mx-auto mt-6 max-w-xl font-body text-sm font-light leading-relaxed text-white/60 sm:text-base">
            {t('cta.sub')}
          </p>
          <div className="mt-10 flex flex-wrap items-center justify-center gap-4">
            <Button
              size="lg"
              onClick={() => document.getElementById('chat')?.scrollIntoView({ behavior: 'smooth' })}
            >
              {t('cta.ask')} ↗
            </Button>
            <Button
              size="lg"
              variant="glass"
              onClick={() => document.getElementById('pricing')?.scrollIntoView({ behavior: 'smooth' })}
            >
              {t('cta.pricing')}
            </Button>
          </div>
        </div>
      </section>
    </main>
  );
}
