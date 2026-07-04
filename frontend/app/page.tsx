'use client';

import { useEffect, useState } from 'react';
import { ChatPanel } from '@/components/ChatPanel';
import { StatTile } from '@/components/ui/StatTile';
import { Button } from '@/components/ui/Button';
import { PLANS } from '@/lib/plans';

interface DecisionStats {
  coverage: { decisions_in_corpus: number; decisions_extracted: number; documents_total?: number };
  overall: { total: number; taxpayer_relief_rate: number | null };
  top_articles: { article: string; total: number; taxpayer_relief_rate: number | null }[];
}

const STEPS = [
  {
    n: '1',
    title: 'Вопрос',
    text: 'Задайте вопрос на русском, грузинском или английском — о ставках, режимах, спорах.',
  },
  {
    n: '2',
    title: 'Поиск по официальной базе',
    text: 'Система ищет только в официальных документах: кодексы, приказы, решения советов по спорам.',
  },
  {
    n: '3',
    title: 'Ответ с цитатой',
    text: 'Каждый ответ сопровождается точным источником — вплоть до статьи закона. Если ответа в базе нет, система честно говорит об этом.',
  },
];

export default function Home() {
  const [stats, setStats] = useState<DecisionStats | null>(null);

  useEffect(() => {
    fetch('/api/v1/analytics/decisions')
      .then((r) => (r.ok ? r.json() : null))
      .then(setStats)
      .catch(() => null);
  }, []);

  const docCount = stats?.coverage.documents_total ?? null;

  const reliefPct =
    stats?.overall.taxpayer_relief_rate != null
      ? `${Math.round(stats.overall.taxpayer_relief_rate * 100)}%`
      : '—';

  return (
    <main>
      {/* Hero */}
      <section className="px-6 pb-20 pt-20 text-center sm:pt-28">
        <div className="mx-auto max-w-page">
          <div className="mb-5 text-[13px] font-medium text-secondary-foreground">
            {docCount
              ? `Официальная база · ${docCount.toLocaleString('ru-RU')} документов`
              : 'Официальная база документов Грузии'}
          </div>
          <h1 className="mx-auto max-w-3xl text-4xl font-semibold leading-tight tracking-display sm:text-[56px] sm:leading-[1.08]">
            Налоговое право Грузии.
            <br />
            С точными источниками.
          </h1>
          <p className="mx-auto mt-5 max-w-xl text-[17px] leading-relaxed text-muted-foreground">
            Ответы строго по официальной базе: Налоговый кодекс, подзаконные акты,
            решения советов по спорам — и статистика их исходов.
          </p>
          <div className="mt-10">
            <ChatPanel />
          </div>
        </div>
      </section>

      {/* How it works */}
      <section className="border-t px-6 py-20">
        <div className="mx-auto max-w-page">
          <h2 className="text-2xl font-semibold tracking-display">Как это работает</h2>
          <div className="mt-10 grid gap-10 sm:grid-cols-3">
            {STEPS.map((s) => (
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
          <h2 className="text-2xl font-semibold tracking-display">Статистика налоговых споров</h2>
          <p className="mt-3 max-w-2xl text-[14px] leading-relaxed text-muted-foreground">
            Мы разобрали решения советов по рассмотрению споров Службы доходов и Минфина
            и посчитали, как они заканчиваются — чтобы вы могли трезво оценить свою стратегию.
          </p>
          <div className="mt-8 grid gap-4 sm:grid-cols-3">
            <StatTile
              value={stats ? stats.overall.total.toLocaleString('ru-RU') : '…'}
              label="Решений проанализировано"
              detail={
                stats
                  ? `из ${stats.coverage.decisions_in_corpus.toLocaleString('ru-RU')} в базе`
                  : undefined
              }
            />
            <StatTile
              value={reliefPct}
              label="Жалоб получают облегчение"
              detail="полное или частичное удовлетворение"
            />
            <StatTile
              value={stats?.top_articles?.[0] ? `ст. ${stats.top_articles[0].article}` : '…'}
              label="Самая спорная статья НК"
              detail={
                stats?.top_articles?.[0]
                  ? `${stats.top_articles[0].total} решений`
                  : undefined
              }
            />
          </div>
        </div>
      </section>

      {/* Pricing */}
      <section id="pricing" className="scroll-mt-20 border-t px-6 py-20">
        <div className="mx-auto max-w-page">
          <h2 className="text-center text-2xl font-semibold tracking-display">Тарифы</h2>
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
                  <span className="text-[13px] text-muted-foreground">{plan.period}</span>
                </div>
                <div className="mt-1 text-[13px] text-muted-foreground">{plan.tagline}</div>
                <ul className="mt-5 flex-1 space-y-2.5">
                  {plan.features.map((f) => (
                    <li key={f} className="flex gap-2 text-[14px] leading-snug">
                      <span aria-hidden className="mt-[7px] h-1 w-3 shrink-0 rounded-full bg-primary/60" />
                      {f}
                    </li>
                  ))}
                </ul>
                <Button
                  variant={plan.highlighted ? 'primary' : 'secondary'}
                  className="mt-7 w-full"
                  onClick={() => document.getElementById('chat')?.scrollIntoView()}
                >
                  {plan.id === 'free' ? 'Начать бесплатно' : 'Скоро — начните с Free'}
                </Button>
              </div>
            ))}
          </div>
          <p className="mt-6 text-center text-[13px] text-muted-foreground">
            Подписки Pro и Business откроются вместе с личным кабинетом. Цены предварительные.
          </p>
        </div>
      </section>
    </main>
  );
}
