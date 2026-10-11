'use client';

import { useCallback, useEffect, useState } from 'react';
import { authFetch } from '@/lib/auth';
import { formatDateTime, useAdminCopy } from '@/lib/admin-i18n';
import { summarizeChange, type AuditEntry, type AuditPage } from '@/lib/admin-types';
import { PageHeader } from '@/components/admin/PageHeader';
import { DataTable, type Column } from '@/components/admin/DataTable';
import { Pagination } from '@/components/admin/Pagination';
import styles from '../admin.module.css';

const LIMIT = 50;
const ACTIONS = ['user.role_changed', 'subscription.activated', 'feedback.status_changed'];

export default function AdminAudit() {
  const { c, locale } = useAdminCopy();
  const [action, setAction] = useState('');
  const [offset, setOffset] = useState(0);
  const [data, setData] = useState<AuditPage | null>(null);
  const [error, setError] = useState(false);

  const load = useCallback(() => {
    const params = new URLSearchParams({ limit: String(LIMIT), offset: String(offset) });
    if (action) params.set('action', action);
    authFetch(`/api/v1/admin/audit?${params}`).then((r) => (r.ok ? r.json() : Promise.reject()))
      .then((d) => { setData(d); setError(false); }).catch(() => setError(true));
  }, [action, offset]);
  useEffect(load, [load]);
  const retry = () => { setError(false); load(); };

  const columns: Column<AuditEntry>[] = [
    { key: 'when', header: c.audit.when, render: (e) => formatDateTime(e.created_at, locale) },
    { key: 'who', header: c.audit.who, render: (e) => e.actor.username ?? e.actor.id },
    { key: 'action', header: c.audit.action, render: (e) => c.audit.actions[e.action] ?? e.action },
    { key: 'target', header: c.audit.target, render: (e) => <>
      {c.audit.targets[e.target_type] ?? e.target_type}<br /><span className={styles.mono}>{e.target_id}</span></> },
    { key: 'change', header: c.audit.change, render: (e) => summarizeChange(e) || c.common.dash },
    { key: 'reason', header: c.audit.reason, render: (e) => e.reason ?? c.common.dash, className: styles.prewrap },
  ];

  return <div className={styles.page}>
    <PageHeader title={c.audit.title} subtitle={c.audit.subtitle} />
    <div className={styles.toolbar}>
      <select className={styles.select} aria-label={c.audit.action} value={action}
        onChange={(e) => { setOffset(0); setError(false); setAction(e.target.value); }}>
        <option value="">{c.common.all}</option>
        {ACTIONS.map((a) => <option key={a} value={a}>{c.audit.actions[a] ?? a}</option>)}
      </select>
    </div>
    <DataTable columns={columns} rows={data?.items ?? []} rowKey={(e) => e.id}
      loading={!data && !error} error={error} onRetry={retry} />
    {data && <Pagination offset={offset} limit={LIMIT} total={data.total} onChange={setOffset} />}
  </div>;
}
