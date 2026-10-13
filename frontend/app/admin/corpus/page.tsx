'use client';

import Link from 'next/link';
import { formatDateTime, formatNumber, useAdminCopy, type AdminCopy, type AdminLocale } from '@/lib/admin-i18n';
import { DOCUMENT_TYPES, type Corpus, type CorpusTypeRow } from '@/lib/admin-types';
import { useAdminFetch } from '@/lib/use-admin-fetch';
import { PageHeader } from '@/components/admin/PageHeader';
import { StatTile } from '@/components/admin/StatTile';
import { AdminState } from '@/components/admin/AdminState';
import { DataTable, type Column } from '@/components/admin/DataTable';
import { TrendChart } from '@/components/admin/TrendChart';
import styles from '../admin.module.css';

// Validated with the dataviz palette checker on the dark admin surface (stage 3).
const BLUE = '#3b82f6';

function weekLabel(start: string, locale: AdminLocale): string {
  return new Intl.DateTimeFormat(locale, { day: '2-digit', month: '2-digit', timeZone: 'UTC' })
    .format(new Date(`${start}T00:00:00Z`));
}

function CorpusView({ data, c, locale }: Readonly<{ data: Corpus; c: AdminCopy; locale: AdminLocale }>) {
  const n = (v: number) => formatNumber(v, locale);
  const gap = (v: number) => (v > 0 ? <strong className={styles.warning}>{n(v)}</strong> : n(v));
  const columns: Column<CorpusTypeRow>[] = [
    { key: 'type', header: c.corpus.type, render: (r) =>
      (DOCUMENT_TYPES as readonly string[]).includes(r.document_type)
        ? <Link href={`/admin/documents?doc_type=${encodeURIComponent(r.document_type)}`}>{r.document_type}</Link>
        : r.document_type },
    { key: 'documents', header: c.corpus.total, render: (r) => n(r.documents) },
    { key: 'new', header: c.corpus.new30, render: (r) => n(r.added_30d) },
    { key: 'noDate', header: c.corpus.withoutDate, render: (r) => gap(r.without_date) },
    { key: 'noChunks', header: c.corpus.withoutChunks, render: (r) => gap(r.without_chunks) },
  ];
  const { totals, pending } = data;
  return <>
    <div className={`${styles.tiles} ${styles.tiles3}`}>
      <StatTile label={c.corpus.documents} value={n(totals.documents)} />
      <StatTile label={c.corpus.chunks} value={n(totals.chunks)} />
      <StatTile label={c.corpus.lastIngest} value={formatDateTime(totals.last_ingest, locale)} />
      <StatTile label={c.corpus.added7d} value={n(totals.added_7d)} />
      <StatTile label={c.corpus.added30d} value={n(totals.added_30d)} />
      <StatTile label={c.corpus.decisionsQueue} value={n(pending.decision_facts)}
        detail={`${c.corpus.amendmentsQueue}: ${n(pending.law_amendments)}`} />
    </div>
    <section className={`liquid-glass ${styles.panel}`}>
      <h2 className={styles.panelTitle}>{c.corpus.byType}</h2>
      <DataTable columns={columns} rows={data.by_type} rowKey={(r) => r.document_type} emptyText={c.common.empty} />
    </section>
    <section className={`liquid-glass ${styles.panel}`}>
      <TrendChart title={c.corpus.weekly} format={n}
        labels={data.weekly.map((w) => weekLabel(w.week_start, locale))}
        series={[{ key: 'added', label: c.corpus.added, color: BLUE, values: data.weekly.map((w) => w.added) }]}
        partialLast={data.weekly.at(-1)?.partial ?? false} emptyText={c.trends.empty} dataLabel={c.trends.showData}
        periodLabel={c.corpus.week} partialLabel={c.trends.partial} dash={c.common.dash} />
    </section>
  </>;
}

export default function AdminCorpus() {
  const { c, locale } = useAdminCopy();
  const { data, error, reload } = useAdminFetch<Corpus>('/api/v1/admin/corpus');

  let body = <AdminState kind="loading" />;
  if (error) body = <AdminState kind="error" onRetry={reload} />;
  else if (data) body = <CorpusView data={data} c={c} locale={locale} />;

  return <div className={styles.page}>
    <PageHeader title={c.corpus.title} subtitle={c.corpus.subtitle}
      actions={<button type="button" className={styles.button} onClick={reload}>{c.common.refresh}</button>} />
    {body}
  </div>;
}
