'use client';

import { useEffect, useState } from 'react';
import { SectionTitle } from '@/components/ui/SectionTitle';
import { DATE_LOCALES, formatNum, useT } from '@/lib/i18n';
import {
  BODY_ORDER,
  DisputeFilter,
  OutcomeRow,
  gel,
  pct,
} from '@/components/disputes/shared';
import { OutcomeLegend, StackedBar } from '@/components/disputes/StackedBar';
import { AmountHistogram, AmountsData } from '@/components/disputes/AmountHistogram';
import { ArticleRow, ArticleTable } from '@/components/disputes/ArticleTable';
import { ChainFunnel, ChainsData } from '@/components/disputes/ChainFunnel';
import { DisputeListDialog } from '@/components/disputes/DisputeListDialog';

interface Overview {
  coverage: { decisions_in_corpus: number; decisions_extracted: number };
  overall: OutcomeRow;
  by_year: (OutcomeRow & { year: number })[];
  by_body: (OutcomeRow & { body: string })[];
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="liquid-glass mt-8 rounded-3xl p-7 md:p-10">
      <h2 className="font-heading text-2xl italic text-white">{title}</h2>
      <div className="mt-6">{children}</div>
    </section>
  );
}

export default function DisputesPage() {
  const { t, lang } = useT();
  const locale = DATE_LOCALES[lang];
  const [overview, setOverview] = useState<Overview | null>(null);
  const [amounts, setAmounts] = useState<AmountsData | null>(null);
  const [articles, setArticles] = useState<ArticleRow[] | null>(null);
  const [chains, setChains] = useState<ChainsData | null>(null);
  const [error, setError] = useState(false);
  const [dialogFilter, setDialogFilter] = useState<DisputeFilter | null>(null);

  useEffect(() => {
    const load = <T,>(url: string, set: (v: T) => void, required: boolean) =>
      fetch(url)
        .then((r) => (r.ok ? r.json() : Promise.reject()))
        .then(set)
        .catch(() => {
          if (required) setError(true);
        });
    load<Overview>('/api/v1/analytics/decisions', setOverview, true);
    load<AmountsData>('/api/v1/analytics/decisions/amounts', setAmounts, false);
    load<{ items: ArticleRow[] }>(
      '/api/v1/analytics/decisions/articles',
      (d) => setArticles(d.items),
      false
    );
    load<ChainsData>('/api/v1/analytics/decisions/chains', setChains, false);
  }, []);

  const bodies = overview
    ? BODY_ORDER.map((b) => overview.by_body.find((r) => r.body === b))
        .filter((r): r is Overview['by_body'][number] => Boolean(r && r.total))
    : [];

  return (
    <main className="mx-auto min-h-[70vh] max-w-page px-6 py-16">
      <SectionTitle as="h1" className="text-3xl font-semibold tracking-display">
        {t('disputes.title')}
      </SectionTitle>
      <p className="mt-3 max-w-2xl text-[15px] leading-relaxed text-muted-foreground">
        {t('disputes.sub')}
      </p>
      {overview && (
        <p className="mt-2 text-[13px] text-white/50">
          {t('disputes.coverage', {
            a: formatNum(lang, overview.coverage.decisions_extracted),
            b: formatNum(lang, overview.coverage.decisions_in_corpus),
          })}
        </p>
      )}

      {error && <p className="mt-10 text-[14px] text-muted-foreground">{t('laws.error')}</p>}
      {!overview && !error && (
        <p className="mt-10 text-[14px] text-muted-foreground">{t('laws.loading')}</p>
      )}

      {overview && (
        <>
          {/* Stat tiles */}
          <div className="mt-10 grid grid-cols-2 gap-4 lg:grid-cols-4">
            <button
              type="button"
              onClick={() => setDialogFilter({})}
              className="liquid-glass rounded-2xl p-6 text-left transition-colors hover:bg-white/5"
            >
              <div className="font-heading text-4xl italic text-white md:text-5xl">
                {formatNum(lang, overview.overall.total)}
              </div>
              <div className="mt-2 text-[13px] font-light text-white/60">
                {t('disputes.tile.analyzed')}
              </div>
            </button>
            <div className="liquid-glass rounded-2xl p-6">
              <div className="font-heading text-4xl italic text-white md:text-5xl">
                {pct(overview.overall.taxpayer_relief_rate)}
              </div>
              <div className="mt-2 text-[13px] font-light text-white/60">
                {t('disputes.tile.relief')}
              </div>
            </div>
            <button
              type="button"
              onClick={() => setDialogFilter({ has_amount: true })}
              className="liquid-glass rounded-2xl p-6 text-left transition-colors hover:bg-white/5"
            >
              <div className="font-heading text-4xl italic text-white md:text-5xl">
                {amounts ? gel(amounts.overall.median, locale) : '—'}
              </div>
              <div className="mt-2 text-[13px] font-light text-white/60">
                {t('disputes.tile.median')}
                {amounts && (
                  <span className="block text-white/40">
                    {t('disputes.tile.median_note', { n: amounts.coverage.with_amount })}
                  </span>
                )}
              </div>
            </button>
            <div className="liquid-glass rounded-2xl p-6">
              <div className="font-heading text-4xl italic text-white md:text-5xl">
                {chains ? formatNum(lang, chains.links_total) : '—'}
              </div>
              <div className="mt-2 text-[13px] font-light text-white/60">
                {t('disputes.tile.chains')}
              </div>
            </div>
          </div>

          {/* By year */}
          <Section title={t('disputes.sec.year')}>
            <OutcomeLegend />
            <div className="mt-5 flex flex-col gap-2.5">
              {overview.by_year.map((r) => (
                <div key={r.year} className="flex items-center gap-3">
                  <button
                    type="button"
                    onClick={() => setDialogFilter({ year: r.year })}
                    className="w-14 shrink-0 text-left text-[13px] text-white/80 transition-colors hover:text-primary"
                  >
                    {r.year}
                  </button>
                  <StackedBar
                    row={r}
                    onSegment={(outcome) => setDialogFilter({ year: r.year, outcome })}
                  />
                  <span className="w-28 shrink-0 text-right text-[12px] text-white/55">
                    {r.total} · {pct(r.taxpayer_relief_rate)}
                  </span>
                </div>
              ))}
            </div>
          </Section>

          {/* By instance */}
          <Section title={t('disputes.sec.instance')}>
            <OutcomeLegend />
            <div className="mt-5 flex flex-col gap-2.5">
              {bodies.map((r) => (
                <div key={r.body} className="flex items-center gap-3">
                  <button
                    type="button"
                    onClick={() => setDialogFilter({ body: r.body })}
                    className="w-44 shrink-0 truncate text-left text-[13px] text-white/80 transition-colors hover:text-primary sm:w-60"
                    title={t(`disputes.body.${r.body}`)}
                  >
                    {t(`disputes.body.${r.body}`)}
                  </button>
                  <StackedBar
                    row={r}
                    onSegment={(outcome) => setDialogFilter({ body: r.body, outcome })}
                  />
                  <span className="w-28 shrink-0 text-right text-[12px] text-white/55">
                    {r.total} · {pct(r.taxpayer_relief_rate)}
                  </span>
                </div>
              ))}
            </div>
          </Section>

          {/* Amounts */}
          {amounts && amounts.coverage.with_amount > 0 && (
            <Section title={t('disputes.sec.amounts')}>
              <AmountHistogram
                data={amounts}
                onBucket={() => setDialogFilter({ has_amount: true })}
              />
            </Section>
          )}

          {/* Articles */}
          {articles && articles.length > 0 && (
            <Section title={t('disputes.sec.articles')}>
              <OutcomeLegend />
              <div className="mt-5">
                <ArticleTable items={articles} onDrill={setDialogFilter} />
              </div>
            </Section>
          )}

          {/* Appeal chains — hidden until the v2 backfill produced links */}
          {chains && chains.links_total > 0 && (
            <Section title={t('disputes.sec.chains')}>
              <ChainFunnel data={chains} />
            </Section>
          )}
        </>
      )}

      <DisputeListDialog filter={dialogFilter} onClose={() => setDialogFilter(null)} />
    </main>
  );
}
