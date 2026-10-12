'use client';

import { Suspense } from 'react';
import { usePathname, useRouter, useSearchParams } from 'next/navigation';
import { formatNumber, useAdminCopy, type AdminCopy, type AdminLocale } from '@/lib/admin-i18n';
import { TREND_PERIODS, type TrendBucket, type TrendPeriod, type Trends } from '@/lib/admin-types';
import { useAdminFetch } from '@/lib/use-admin-fetch';
import { PageHeader } from '@/components/admin/PageHeader';
import { StatTile } from '@/components/admin/StatTile';
import { AdminState } from '@/components/admin/AdminState';
import { TrendChart, type ChartSeries } from '@/components/admin/TrendChart';
import styles from '../admin.module.css';

const DEFAULT_PERIOD: TrendPeriod = '30d';
// Validated with the dataviz palette checker on the dark admin surface (#0b0b0b).
const BLUE = '#3b82f6';
const AMBER = '#d97706';

function pickPeriod(value: string | null): TrendPeriod {
  return (TREND_PERIODS as readonly string[]).includes(value ?? '') ? (value as TrendPeriod) : DEFAULT_PERIOD;
}

function bucketLabel(start: string, bucket: Trends['bucket'], locale: AdminLocale): string {
  const options: Intl.DateTimeFormatOptions = bucket === 'month'
    ? { month: 'short', year: '2-digit', timeZone: 'UTC' }
    : { day: '2-digit', month: '2-digit', timeZone: 'UTC' };
  return new Intl.DateTimeFormat(locale, options).format(new Date(`${start}T00:00:00Z`));
}

function deltaText(current: number, previous: number, c: AdminCopy, locale: AdminLocale): string {
  if (previous === 0) return current === 0 ? c.common.dash : c.trends.newVsPrev;
  const pct = Math.round(((current - previous) / previous) * 100);
  let sign = '±';
  if (pct > 0) sign = '+';
  else if (pct < 0) sign = '−';
  return c.trends.vsPrev(`${sign}${formatNumber(Math.abs(pct), locale)}%`);
}

const share = (part: number, whole: number) => (whole > 0 ? part / whole : null);

function TrendsView({ data, c, locale }: Readonly<{ data: Trends; c: AdminCopy; locale: AdminLocale }>) {
  const n = (v: number) => formatNumber(v, locale);
  const money = (minor: number) => `${formatNumber(Math.round(minor) / 100, locale)} ${c.trends.currency}`;
  const percent = (v: number) => `${formatNumber(Math.round(v * 100), locale)}%`;
  const { current, previous } = data.totals;
  const labels = data.buckets.map((b) => bucketLabel(b.start, data.bucket, locale));
  const partialLast = data.buckets.at(-1)?.partial ?? false;
  const series = (key: string, label: string, pickValue: (b: TrendBucket) => number | null, color = BLUE): ChartSeries =>
    ({ key, label, color, values: data.buckets.map(pickValue) });
  const common = {
    labels, partialLast, emptyText: c.trends.empty, dataLabel: c.trends.showData, periodLabel: c.trends.date,
    partialLabel: c.trends.partial, dash: c.common.dash,
  };
  const rated = current.up + current.down;
  const upShare = share(current.up, rated);
  const qualityNote = data.quality_since === null ? c.trends.noQuality
    : c.trends.qualitySince(bucketLabel(data.quality_since, 'day', locale));
  const median = data.median_processing_ms;

  return <>
    <div className={`${styles.tiles} ${styles.tiles3}`}>
      <StatTile label={c.trends.revenue} value={money(current.revenue_minor)}
        detail={deltaText(current.revenue_minor, previous.revenue_minor, c, locale)} />
      <StatTile label={c.trends.payments} value={n(current.payments)} detail={deltaText(current.payments, previous.payments, c, locale)} />
      <StatTile label={c.trends.signups} value={n(current.signups)} detail={deltaText(current.signups, previous.signups, c, locale)} />
      <StatTile label={c.trends.questions} value={n(current.questions)} detail={deltaText(current.questions, previous.questions, c, locale)} />
      <StatTile label={c.trends.askers} value={n(current.askers)} detail={deltaText(current.askers, previous.askers, c, locale)} />
      <StatTile label={c.trends.upShare} value={upShare === null ? c.common.dash : percent(upShare)} detail={c.trends.ofRated(n(rated))} />
    </div>

    <section className={`liquid-glass ${styles.panel}`}>
      <div className={styles.chartGrid}>
        <TrendChart {...common} title={c.trends.revenue} format={money} series={[series('revenue', c.trends.revenue, (b) => b.revenue_minor)]} />
        <TrendChart {...common} title={c.trends.signups} format={n} series={[series('signups', c.trends.signups, (b) => b.signups)]} />
      </div>
    </section>

    <section className={`liquid-glass ${styles.panel}`}>
      <h2 className={styles.panelTitle}>{c.trends.activity}</h2>
      <div className={styles.chartGrid}>
        <TrendChart {...common} title={c.trends.questions} format={n} series={[series('questions', c.trends.questions, (b) => b.questions)]} />
        <TrendChart {...common} title={c.trends.askers} format={n} series={[series('askers', c.trends.askers, (b) => b.askers)]} />
      </div>
    </section>

    <section className={`liquid-glass ${styles.panel}`}>
      <h2 className={styles.panelTitle}>{c.trends.quality}</h2>
      <div className={styles.chartGrid}>
        <TrendChart {...common} title={c.trends.ratings} format={n} series={[
          series('up', c.trends.up, (b) => b.up),
          series('down', c.trends.down, (b) => b.down, AMBER),
        ]} />
        <TrendChart {...common} title={c.trends.flaggedShare} format={percent} note={qualityNote} zeroIsData
          series={[series('flagged', c.trends.flaggedShare, (b) => share(b.flagged, b.answers_with_evidence))]} />
      </div>
      <p className={styles.chartNote}>
        {c.trends.medianTime}: {median === null ? c.common.dash : c.trends.seconds(formatNumber(Math.round(median / 100) / 10, locale))}
      </p>
    </section>
  </>;
}

function TrendsPage() {
  const { c, locale } = useAdminCopy();
  const params = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const period = pickPeriod(params.get('period'));
  const { data, error, loading, reload } = useAdminFetch<Trends>(`/api/v1/admin/trends?period=${period}`);

  const choose = (next: TrendPeriod) => {
    const query = new URLSearchParams(params.toString());
    if (next === DEFAULT_PERIOD) query.delete('period');
    else query.set('period', next);
    const s = query.toString();
    router.replace(s ? `${pathname}?${s}` : pathname, { scroll: false });
  };

  let body = <AdminState kind="loading" />;
  if (error) body = <AdminState kind="error" onRetry={reload} />;
  else if (data) body = <TrendsView data={data} c={c} locale={locale} />;

  return <div className={styles.page}>
    <PageHeader title={c.trends.title} subtitle={c.trends.subtitle} />
    <div className={styles.toolbar}>
      <div className={styles.segmented} role="group" aria-label={c.trends.period} aria-busy={loading}>
        {TREND_PERIODS.map((p) => <button key={p} type="button" aria-pressed={p === period} onClick={() => choose(p)}>
          {c.trends.periods[p]}
        </button>)}
      </div>
    </div>
    {body}
  </div>;
}

export default function AdminTrends() {
  return <Suspense><TrendsPage /></Suspense>;
}
