'use client';

import Link from 'next/link';
import { Suspense, useCallback, useEffect, useState } from 'react';
import { usePathname, useRouter, useSearchParams } from 'next/navigation';
import { formatDateTime, formatNumber, useAdminCopy } from '@/lib/admin-i18n';
import { QUALITY_FLAGS } from '@/lib/admin-types';
import type { QualityFlag, QualityPage, QualityRow, QualitySummary, Verdict } from '@/lib/admin-types';
import { useAdminFetch } from '@/lib/use-admin-fetch';
import { PageHeader } from '@/components/admin/PageHeader';
import { StatTile } from '@/components/admin/StatTile';
import { DataTable, type Column } from '@/components/admin/DataTable';
import { Pagination } from '@/components/admin/Pagination';
import { Badge } from '@/components/admin/Badge';
import styles from '../admin.module.css';

const PERIODS = ['7d', '30d', '90d', 'all'] as const;
const RATINGS = ['up', 'down', 'none'] as const;
const VERDICT_FILTERS = ['unreviewed', 'correct', 'partial', 'wrong'] as const;
const DEFAULT_PERIOD = '7d';
const LIMIT = 50;

type AdminCopy = ReturnType<typeof useAdminCopy>['c'];
type Patch = Record<string, string | readonly string[]>;

function pick<T extends string>(value: string | null, allowed: readonly T[]): T | '' {
  return value !== null && (allowed as readonly string[]).includes(value) ? (value as T) : '';
}

function FlagBadges({ flags, c }: Readonly<{ flags: QualityFlag[]; c: AdminCopy }>) {
  if (flags.length === 0) return <>{c.common.dash}</>;
  return <span className={styles.pills}>
    {flags.map((f) => <Badge key={f} tone="warning">{c.quality.flags[f]}</Badge>)}
  </span>;
}

const VERDICT_TONES = { correct: 'success', partial: 'warning', wrong: 'error' } as const satisfies Record<Verdict, string>;

function VerdictBadge({ verdict, c }: Readonly<{ verdict: Verdict | null; c: AdminCopy }>) {
  if (!verdict) return <>{c.common.dash}</>;
  return <Badge tone={VERDICT_TONES[verdict]}>{c.quality.verdicts[verdict]}</Badge>;
}

function RatingMark({ rating, c }: Readonly<{ rating: QualityRow['rating']; c: AdminCopy }>) {
  if (rating === 1) return <>{c.quality.ratings.up}</>;
  if (rating === -1) return <>{c.quality.ratings.down}</>;
  return <>{c.common.dash}</>;
}

function sameFlags(a: readonly string[], b: readonly string[]) {
  return a.length === b.length && a.every((f) => b.includes(f));
}

function QualityFeed() {
  const { c, locale } = useAdminCopy();
  const params = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const q = (params.get('q') ?? '').trim().slice(0, 100);
  const period = pick(params.get('period'), PERIODS) || DEFAULT_PERIOD;
  const rating = pick(params.get('rating'), RATINGS);
  const verdict = pick(params.get('verdict'), VERDICT_FILTERS);
  const flags = params.getAll('flags').filter((f): f is QualityFlag => (QUALITY_FLAGS as readonly string[]).includes(f));
  const offset = Math.max(0, Math.floor(Number(params.get('offset')) || 0));

  const update = useCallback((patch: Patch) => {
    const next = new URLSearchParams(params.toString());
    for (const [k, v] of Object.entries(patch)) {
      next.delete(k);
      const values = typeof v === 'string' ? [v] : v;
      for (const item of values) { if (item) next.append(k, item); }
    }
    if (next.get('period') === DEFAULT_PERIOD) next.delete('period');
    if (!('offset' in patch)) next.delete('offset');
    const s = next.toString();
    router.replace(s ? `${pathname}?${s}` : pathname, { scroll: false });
  }, [params, pathname, router]);

  // The box follows external URL changes (back/forward, reset) but never our own pushes, which would
  // otherwise overwrite a character typed while the debounced replace was landing.
  const [draft, setDraft] = useState(q);
  const [seenQ, setSeenQ] = useState(q);
  const [pushedQ, setPushedQ] = useState(q);
  if (q !== seenQ) { setSeenQ(q); if (q !== pushedQ) { setPushedQ(q); setDraft(q); } }
  useEffect(() => {
    const next = draft.trim().slice(0, 100);
    if (next === q) return;
    const t = setTimeout(() => { setPushedQ(next); update({ q: next }); }, 300);
    return () => clearTimeout(t);
  }, [draft, q, update]);

  const query = new URLSearchParams({ limit: String(LIMIT), offset: String(offset), period });
  if (rating) query.set('rating', rating);
  if (verdict) query.set('verdict', verdict);
  if (q) query.set('q', q);
  flags.forEach((f) => query.append('flags', f));
  const { data, error, loading, reload } = useAdminFetch<QualityPage>(`/api/v1/admin/quality/answers?${query}`);
  const summary = useAdminFetch<QualitySummary>(`/api/v1/admin/quality/summary?period=${period}`).data;
  const rows = data?.items ?? [];
  const total = data?.total ?? 0;
  const filtered = Boolean(q || rating || verdict || flags.length > 0);
  const listQuery = params.toString();
  const reviewHref = (id: string) => `/admin/quality/${id}${listQuery ? `?back=${encodeURIComponent(`?${listQuery}`)}` : ''}`;
  const reset = () => { setDraft(''); setPushedQ(''); router.replace(pathname, { scroll: false }); };

  const toggleFlag = (f: QualityFlag) => update({ flags: flags.includes(f) ? flags.filter((x) => x !== f) : [...flags, f] });
  const queue = (patch: { rating?: string; verdict?: string; flags?: readonly string[] }) =>
    update({ rating: patch.rating ?? '', verdict: patch.verdict ?? '', flags: patch.flags ?? [] });
  const downActive = rating === 'down' && verdict === 'unreviewed' && flags.length === 0;
  const citationActive = !rating && !verdict && sameFlags(flags, ['no_precise_citation']);
  const wrongActive = !rating && verdict === 'wrong' && flags.length === 0;

  const percent = (share: number | null) => (share === null ? c.common.dash : `${formatNumber(Math.round(share * 100), locale)}%`);
  const wrongShare = summary && summary.reviewed > 0 ? summary.verdicts.wrong / summary.reviewed : null;
  const medianMs = summary?.median_processing_ms ?? null;

  const columns: Column<QualityRow>[] = [
    { key: 'when', header: c.quality.when, render: (r) => <span className={styles.muted}>{formatDateTime(r.created_at, locale)}</span> },
    { key: 'user', header: c.quality.user, render: (r) => <span className={styles.mono}>{r.pseudonym}</span> },
    { key: 'question', header: c.quality.question, render: (r) => <Link href={reviewHref(r.message_id)}>{r.question}</Link> },
    { key: 'signals', header: c.quality.signals, render: (r) => <FlagBadges flags={r.flags} c={c} /> },
    { key: 'rating', header: c.quality.rating, render: (r) => <RatingMark rating={r.rating} c={c} /> },
    { key: 'verdict', header: c.quality.verdict, render: (r) => <VerdictBadge verdict={r.verdict} c={c} /> },
  ];

  return <div className={styles.page}>
    <PageHeader title={c.quality.title} subtitle={c.quality.subtitle} />

    {summary && <div className={styles.tiles}>
      <StatTile label={c.quality.summary.downShare} value={percent(summary.down_share)} detail={c.quality.summary.ofRated(formatNumber(summary.rated, locale))} />
      <StatTile label={c.quality.summary.reviewed} value={formatNumber(summary.reviewed, locale)} detail={c.quality.summary.ofAnswers(formatNumber(summary.answers, locale))} />
      <StatTile label={c.quality.summary.wrongShare} value={percent(wrongShare)} />
      <StatTile label={c.quality.summary.noCitation} value={percent(summary.no_precise_citation_share)} />
      <StatTile label={c.quality.summary.median} value={medianMs === null ? c.common.dash : c.quality.seconds((medianMs / 1000).toFixed(1))} />
    </div>}

    <section className={`liquid-glass ${styles.panel}`}>
      <div className={styles.toolbar}>
        <select className={styles.select} aria-label={c.quality.period} value={period} onChange={(e) => update({ period: e.target.value })}>
          {PERIODS.map((p) => <option key={p} value={p}>{c.quality.periods[p]}</option>)}
        </select>
        <button type="button" className={styles.chip} aria-pressed={downActive}
          onClick={() => queue({ rating: 'down', verdict: 'unreviewed' })}>{c.quality.queues.downUnreviewed}</button>
        <button type="button" className={styles.chip} aria-pressed={citationActive}
          onClick={() => queue({ flags: ['no_precise_citation'] })}>{c.quality.queues.noCitation}</button>
        <button type="button" className={styles.chip} aria-pressed={wrongActive}
          onClick={() => queue({ verdict: 'wrong' })}>{c.quality.queues.wrong}</button>
      </div>
      <div className={styles.toolbar}>
        <input className={styles.input} type="search" aria-label={c.quality.search} placeholder={c.quality.search}
          maxLength={100} value={draft} onChange={(e) => setDraft(e.target.value)} />
        <select className={styles.select} aria-label={c.quality.ratingFilter} value={rating} onChange={(e) => update({ rating: e.target.value })}>
          <option value="">{c.quality.ratingFilter}: {c.common.all}</option>
          {RATINGS.map((r) => <option key={r} value={r}>{c.quality.ratings[r]}</option>)}
        </select>
        <select className={styles.select} aria-label={c.quality.verdictFilter} value={verdict} onChange={(e) => update({ verdict: e.target.value })}>
          <option value="">{c.quality.verdictFilter}: {c.common.all}</option>
          {VERDICT_FILTERS.map((v) => <option key={v} value={v}>{c.quality.verdictFilters[v]}</option>)}
        </select>
        {filtered && <button type="button" className={styles.button} onClick={reset}>{c.quality.reset}</button>}
      </div>
      <div className={styles.toolbar}>
        {QUALITY_FLAGS.map((f) => <label key={f}>
          <input type="checkbox" checked={flags.includes(f)} onChange={() => toggleFlag(f)} /> {c.quality.flags[f]}
        </label>)}
      </div>
    </section>

    <DataTable columns={columns} rows={rows} rowKey={(r) => r.message_id} loading={loading} error={error} onRetry={reload}
      emptyText={filtered ? c.quality.notFound : undefined} />
    {!loading && !error && filtered && rows.length === 0 &&
      <button type="button" className={styles.button} onClick={reset}>{c.quality.reset}</button>}
    <Pagination offset={offset} limit={LIMIT} total={total} onChange={(next) => update({ offset: next ? String(next) : '' })} />
  </div>;
}

export default function AdminQuality() {
  return <Suspense><QualityFeed /></Suspense>;
}
