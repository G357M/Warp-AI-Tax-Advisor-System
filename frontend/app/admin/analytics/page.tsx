'use client';

import { useCallback, useEffect, useState, type CSSProperties } from 'react';
import { formatNumber, useAdminCopy, type AdminCopy } from '@/lib/admin-i18n';
import { PageHeader } from '@/components/admin/PageHeader';
import { StatTile } from '@/components/admin/StatTile';
import { AdminState } from '@/components/admin/AdminState';
import styles from '../admin.module.css';

// Outcome palette — validated (dataviz six checks, dark surface).
const OUTCOMES = [
  { key: 'satisfied', color: '#059669' },
  { key: 'partially_satisfied', color: '#d97706' },
  { key: 'rejected', color: '#3b82f6' },
] as const;

interface OutcomeRow { total: number; satisfied: number; partially_satisfied: number; rejected: number; unclear: number; taxpayer_relief_rate: number | null }
interface Analytics {
  coverage: { decisions_in_corpus: number; decisions_extracted: number };
  overall: OutcomeRow;
  by_year: (OutcomeRow & { year: number })[];
  by_body: (OutcomeRow & { body: string })[];
  top_articles: (OutcomeRow & { article: string })[];
}

const pct = (rate: number | null) => (rate == null ? '—' : `${Math.round(rate * 100)}%`);
const vars = (v: Record<string, string>) => v as CSSProperties;

function StackedBar({ row, c }: Readonly<{ row: OutcomeRow; c: AdminCopy }>) {
  const total = row.satisfied + row.partially_satisfied + row.rejected;
  if (!total) return <div className={styles.barTrack} />;
  return <div className={styles.barTrack}>
    {OUTCOMES.map(({ key, color }) => row[key] ? <span key={key} className={styles.barSegment}
      title={`${c.analytics.outcomes[key]}: ${row[key]} (${Math.round((row[key] / total) * 100)}%)`}
      style={vars({ '--w': `${(row[key] / total) * 100}%`, '--c': color })} /> : null)}
  </div>;
}

function Legend({ c }: Readonly<{ c: AdminCopy }>) {
  return <div className={styles.legend}>
    {OUTCOMES.map(({ key, color }) => <span key={key}>
      <span className={styles.swatch} style={vars({ '--c': color })} />{c.analytics.outcomes[key]}</span>)}
  </div>;
}

function BarSection({ title, rows, c }: Readonly<{ title: string; rows: { label: string; row: OutcomeRow }[]; c: AdminCopy }>) {
  return <section className={`liquid-glass ${styles.panel}`}>
    <h2 className={styles.panelTitle}>{title}</h2>
    <Legend c={c} />
    <div className={styles.bars}>
      {rows.map(({ label, row }) => <div key={label} className={styles.barRow}>
        <span>{label}</span>
        <StackedBar row={row} c={c} />
        <span className={styles.barMeta}>{row.total} · {c.analytics.reliefShort} {pct(row.taxpayer_relief_rate)}</span>
      </div>)}
    </div>
  </section>;
}

export default function AnalyticsPage() {
  const { c, locale } = useAdminCopy();
  const [data, setData] = useState<Analytics | null>(null);
  const [error, setError] = useState(false);

  const load = useCallback(() => {
    fetch('/api/v1/analytics/decisions').then((r) => (r.ok ? r.json() : Promise.reject()))
      .then((d) => { setData(d); setError(false); }).catch(() => setError(true));
  }, []);
  useEffect(load, [load]);
  const retry = () => { setError(false); load(); };

  if (error) return <AdminState kind="error" onRetry={retry} />;
  if (!data) return <AdminState kind="loading" />;
  const n = (v: number) => formatNumber(v, locale);
  const coverage = data.coverage.decisions_in_corpus
    ? Math.round((data.coverage.decisions_extracted / data.coverage.decisions_in_corpus) * 100) : 0;

  return <div className={styles.page}>
    <PageHeader title={c.analytics.title} subtitle={c.analytics.subtitle} />
    <div className={styles.tiles}>
      <StatTile label={c.analytics.analyzed} value={n(data.coverage.decisions_extracted)}
        detail={c.analytics.coverage(coverage, n(data.coverage.decisions_in_corpus))} />
      <StatTile label={c.analytics.relief} value={pct(data.overall.taxpayer_relief_rate)} detail={c.analytics.reliefDetail} />
      <StatTile label={c.analytics.satisfied} value={n(data.overall.satisfied)} detail={c.analytics.vsRejected(n(data.overall.rejected))} />
    </div>
    <BarSection c={c} title={c.analytics.byYear} rows={data.by_year.map((r) => ({ label: String(r.year), row: r }))} />
    <BarSection c={c} title={c.analytics.byBody}
      rows={data.by_body.filter((r) => r.body).map((r) => ({ label: c.analytics.bodies[r.body] ?? r.body, row: r }))} />
    <section className={`liquid-glass ${styles.panel}`}>
      <h2 className={styles.panelTitle}>{c.analytics.topArticles}</h2>
      <Legend c={c} />
      <div className={styles.tableWrap}>
        <table className={styles.table}>
          <thead><tr>
            <th scope="col">{c.analytics.article}</th><th scope="col">{c.analytics.decisions}</th>
            <th scope="col">{c.analytics.split}</th><th scope="col">{c.analytics.reliefRate}</th>
          </tr></thead>
          <tbody>{data.top_articles.map((r) => <tr key={r.article}>
            <td data-label={c.analytics.article}><strong>{r.article}</strong></td>
            <td data-label={c.analytics.decisions}>{r.total}</td>
            <td data-label={c.analytics.split}><StackedBar row={r} c={c} /></td>
            <td data-label={c.analytics.reliefRate}>{pct(r.taxpayer_relief_rate)}</td>
          </tr>)}</tbody>
        </table>
      </div>
    </section>
  </div>;
}
