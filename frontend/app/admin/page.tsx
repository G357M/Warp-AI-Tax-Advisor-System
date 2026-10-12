'use client';

import { useCallback, useEffect, useState } from 'react';
import Link from 'next/link';
import { authFetch } from '@/lib/auth';
import { actionLabel, formatDateTime, formatNumber, useAdminCopy, type AdminCopy, type AdminLocale } from '@/lib/admin-i18n';
import { summarizeChange, type AdminStats, type AuditPage } from '@/lib/admin-types';
import { PageHeader } from '@/components/admin/PageHeader';
import { StatTile } from '@/components/admin/StatTile';
import { AdminState } from '@/components/admin/AdminState';
import styles from './admin.module.css';

type AttentionItem = { href: string; text: string };
type Fmt = (value: number) => string;

function buildAttention(stats: AdminStats, c: AdminCopy, n: Fmt): AttentionItem[] {
  const downUnreviewed = stats.quality?.down_unreviewed ?? 0;
  return [
    stats.feedback.new > 0 && { href: '/admin/feedback', text: c.dashboard.feedbackNew(n(stats.feedback.new)) },
    stats.billing.reconciliation_open > 0 && { href: '/admin/billing', text: c.dashboard.reconciliation(n(stats.billing.reconciliation_open)) },
    stats.billing.manual_pending > 0 && { href: '/admin/users', text: c.dashboard.manualPending(n(stats.billing.manual_pending)) },
    downUnreviewed > 0 && { href: '/admin/quality?period=all&rating=down&verdict=unreviewed', text: c.dashboard.qualityDown(n(downUnreviewed)) },
    stats.attention.ingest_stale && { href: '/admin/scraper', text: c.dashboard.ingestStale },
    stats.decisions.pending > 0 && { href: '/admin/scraper', text: c.dashboard.decisionsQueue(n(stats.decisions.pending)) },
  ].filter((item): item is AttentionItem => Boolean(item));
}

function AttentionBody({ stats, error, items, onRetry, c }: {
  stats: AdminStats | null; error: boolean; items: AttentionItem[]; onRetry: () => void; c: AdminCopy;
}) {
  if (error) return <AdminState kind="error" onRetry={onRetry} />;
  if (!stats) return <AdminState kind="loading" />;
  if (items.length === 0) return <p className={styles.notice}>{c.dashboard.allClear}</p>;
  return <ul className={styles.list}>{items.map((item) => <li key={item.text}><Link href={item.href}>{item.text}</Link></li>)}</ul>;
}

function RecentBody({ audit, error, onRetry, c, locale }: {
  audit: AuditPage | null; error: boolean; onRetry: () => void; c: AdminCopy; locale: AdminLocale;
}) {
  if (error) return <AdminState kind="error" onRetry={onRetry} />;
  if (!audit) return <AdminState kind="loading" />;
  if (audit.items.length === 0) return <AdminState kind="empty" />;
  return <ul className={styles.list}>{audit.items.map((entry) => <li key={entry.id}>
    <span>{actionLabel(c, entry.action)}<br /><span className={styles.muted}>{summarizeChange(entry)}</span></span>
    <span className={styles.muted}>{formatDateTime(entry.created_at, locale)}</span>
  </li>)}</ul>;
}

function StatTiles({ stats, c, n, locale }: { stats: AdminStats; c: AdminCopy; n: Fmt; locale: AdminLocale }) {
  const subsTotal = Object.values(stats.subscriptions).reduce((a, b) => a + b, 0);
  return <div className={styles.tiles}>
    <StatTile label={c.dashboard.documents} value={n(stats.documents.total)}
      detail={stats.documents.last_ingest ? c.dashboard.lastIngest(formatDateTime(stats.documents.last_ingest, locale)) : undefined} />
    <StatTile label={c.dashboard.decisions} value={`${n(stats.decisions.extracted)} / ${n(stats.decisions.total)}`}
      detail={c.dashboard.queue(n(stats.decisions.pending))} />
    <StatTile label={c.dashboard.amendments} value={`${n(stats.amendments.extracted)} / ${n(stats.amendments.acts_total)}`}
      detail={c.dashboard.amendmentsDetail(n(stats.amendments.resolved), n(stats.amendments.pending))} />
    <StatTile label={c.dashboard.users} value={n(stats.users.total)} detail={c.dashboard.admins(n(stats.users.admins))} href="/admin/users" />
    <StatTile label={c.dashboard.subscriptions} value={n(subsTotal)}
      detail={Object.entries(stats.subscriptions).map(([p, v]) => `${p}: ${n(v)}`).join(' · ') || c.dashboard.noSubscriptions} />
    <StatTile label={c.dashboard.messages7d} value={n(stats.conversations.messages_7d)}
      detail={c.dashboard.conversations(n(stats.conversations.total))} />
  </div>;
}

export default function AdminDashboard() {
  const { c, locale } = useAdminCopy();
  const [stats, setStats] = useState<AdminStats | null>(null);
  const [statsError, setStatsError] = useState(false);
  const [audit, setAudit] = useState<AuditPage | null>(null);
  const [auditError, setAuditError] = useState(false);

  const loadStats = useCallback(() => {
    authFetch('/api/v1/admin/stats').then((r) => (r.ok ? r.json() : Promise.reject()))
      .then((d) => { setStats(d); setStatsError(false); }).catch(() => setStatsError(true));
  }, []);
  const loadAudit = useCallback(() => {
    authFetch('/api/v1/admin/audit?limit=5').then((r) => (r.ok ? r.json() : Promise.reject()))
      .then((d) => { setAudit(d); setAuditError(false); }).catch(() => setAuditError(true));
  }, []);
  useEffect(() => { loadStats(); loadAudit(); }, [loadStats, loadAudit]);
  const retryStats = () => { setStatsError(false); loadStats(); };
  const retryAudit = () => { setAuditError(false); loadAudit(); };

  const n = (value: number) => formatNumber(value, locale);
  const attention = stats ? buildAttention(stats, c, n) : [];

  return <div className={styles.page}>
    <PageHeader title={c.dashboard.title} subtitle={c.dashboard.subtitle} />

    <section className={`liquid-glass ${styles.panel}`} aria-labelledby="attention-title">
      <h2 id="attention-title" className={styles.panelTitle}>{c.dashboard.attention}</h2>
      <AttentionBody stats={stats} error={statsError} items={attention} onRetry={retryStats} c={c} />
    </section>

    {stats && <StatTiles stats={stats} c={c} n={n} locale={locale} />}

    <div className={styles.grid2}>
      {stats && <section className={`liquid-glass ${styles.panel}`} aria-labelledby="corpus-title">
        <h2 id="corpus-title" className={styles.panelTitle}>{c.dashboard.corpus}</h2>
        <div className={styles.pills}>
          {Object.entries(stats.documents.by_type).map(([type, count]) =>
            <span key={type} className={`${styles.badge} ${styles['badge-neutral']}`}>{type}: {n(count)}</span>)}
        </div>
      </section>}
      <section className={`liquid-glass ${styles.panel}`} aria-labelledby="recent-title">
        <h2 id="recent-title" className={styles.panelTitle}>{c.dashboard.recent}</h2>
        <RecentBody audit={audit} error={auditError} onRetry={retryAudit} c={c} locale={locale} />
        <p className={styles.notice}><Link href="/admin/audit">{c.dashboard.openAudit}</Link></p>
      </section>
    </div>
  </div>;
}
