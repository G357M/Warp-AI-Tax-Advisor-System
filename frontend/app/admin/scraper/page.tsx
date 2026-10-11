'use client';

import { useCallback, useEffect, useState } from 'react';
import { authFetch } from '@/lib/auth';
import { formatDateTime, formatNumber, useAdminCopy } from '@/lib/admin-i18n';
import { PageHeader } from '@/components/admin/PageHeader';
import { StatTile } from '@/components/admin/StatTile';
import { AdminState } from '@/components/admin/AdminState';
import styles from '../admin.module.css';

interface OpsStatus {
  last_ingest: string | null;
  documents_today: number;
  pending: { decision_facts: number; law_amendments: number };
  logs: Record<string, string[]>;
}

export default function AdminScraper() {
  const { c, locale } = useAdminCopy();
  const [ops, setOps] = useState<OpsStatus | null>(null);
  const [error, setError] = useState(false);

  const load = useCallback(() => {
    authFetch('/api/v1/admin/ops').then((r) => (r.ok ? r.json() : Promise.reject()))
      .then((d) => { setOps(d); setError(false); }).catch(() => setError(true));
  }, []);
  useEffect(load, [load]);

  const retry = () => { setError(false); load(); };

  return <div className={styles.page}>
    <PageHeader title={c.scraper.title}
      actions={<button type="button" className={styles.button} onClick={retry}>{c.common.refresh}</button>} />
    {error ? <AdminState kind="error" onRetry={retry} /> : !ops ? <AdminState kind="loading" /> : <>
      <div className={styles.tiles}>
        <StatTile label={c.scraper.lastIngest} value={formatDateTime(ops.last_ingest, locale)}
          detail={c.scraper.today(formatNumber(ops.documents_today, locale))} />
        <StatTile label={c.scraper.decisions} value={formatNumber(ops.pending.decision_facts, locale)} />
        <StatTile label={c.scraper.amendments} value={formatNumber(ops.pending.law_amendments, locale)} />
      </div>
      {Object.entries(ops.logs).map(([key, lines]) => <section key={key} className={`liquid-glass ${styles.panel}`}>
        <h2 className={styles.panelTitle}>{c.scraper.logs[key] ?? key}</h2>
        {lines.length === 0 ? <p className={styles.notice}>{c.scraper.logEmpty}</p>
          : <pre className={styles.log}>{lines.join('\n')}</pre>}
      </section>)}
    </>}
  </div>;
}
