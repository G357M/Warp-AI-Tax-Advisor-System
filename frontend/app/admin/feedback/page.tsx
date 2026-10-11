'use client';

import { useCallback, useEffect, useState } from 'react';
import { authFetch } from '@/lib/auth';
import { formatDateTime, useAdminCopy } from '@/lib/admin-i18n';
import { PageHeader } from '@/components/admin/PageHeader';
import { DataTable, type Column } from '@/components/admin/DataTable';
import { ConfirmDialog } from '@/components/admin/ConfirmDialog';
import { Badge, type BadgeTone } from '@/components/admin/Badge';
import styles from '../admin.module.css';

type Status = 'new' | 'in_progress' | 'fixed';
interface FeedbackItem { id: string; message: string; page: string | null; status: Status; created_at: string | null; email: string; username: string }
interface FeedbackResponse { total: number; counts: Record<Status, number>; items: FeedbackItem[] }

const STATUSES: Status[] = ['new', 'in_progress', 'fixed'];
const TONE: Record<Status, BadgeTone> = { new: 'warning', in_progress: 'neutral', fixed: 'success' };

export default function AdminFeedback() {
  const { c, locale } = useAdminCopy();
  const [data, setData] = useState<FeedbackResponse | null>(null);
  const [error, setError] = useState(false);
  const [filter, setFilter] = useState<Status | ''>('');
  const [pending, setPending] = useState<{ item: FeedbackItem; status: Status } | null>(null);

  const load = useCallback(() => {
    authFetch(`/api/v1/admin/feedback?limit=100${filter ? `&status=${filter}` : ''}`)
      .then((r) => (r.ok ? r.json() : Promise.reject())).then((d) => { setData(d); setError(false); }).catch(() => setError(true));
  }, [filter]);
  useEffect(load, [load]);

  const confirm = async (reason: string) => {
    if (!pending) return;
    const res = await authFetch(`/api/v1/admin/feedback/${pending.item.id}`, {
      method: 'PATCH', body: JSON.stringify({ status: pending.status, reason }),
    });
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      throw new Error(typeof body.detail === 'string' ? body.detail : c.common.saveError);
    }
    load();
  };

  const columns: Column<FeedbackItem>[] = [
    { key: 'date', header: c.feedback.date, render: (f) => <span className={styles.muted}>{formatDateTime(f.created_at, locale)}</span> },
    { key: 'user', header: c.feedback.user, render: (f) => f.email },
    { key: 'page', header: c.feedback.page, render: (f) => <span className={styles.mono}>{f.page ?? c.common.dash}</span> },
    { key: 'message', header: c.feedback.message, render: (f) => f.message, className: styles.prewrap },
    { key: 'status', header: c.feedback.status, render: (f) => <div className={styles.toolbar}>
      <Badge tone={TONE[f.status]}>{c.feedback.statuses[f.status]}</Badge>
      <select className={styles.select} aria-label={c.feedback.status} value={f.status}
        onChange={(e) => setPending({ item: f, status: e.target.value as Status })}>
        {STATUSES.map((s) => <option key={s} value={s}>{c.feedback.statuses[s]}</option>)}
      </select>
    </div> },
  ];

  return <div className={styles.page}>
    <PageHeader title={`${c.feedback.title}${data ? ` (${data.total})` : ''}`} />
    <div className={styles.toolbar} role="group" aria-label={c.feedback.status}>
      {(['', ...STATUSES] as const).map((s) => <button key={s || 'all'} type="button"
        className={`${styles.button} ${styles.chip}`} aria-pressed={filter === s} onClick={() => { setError(false); setFilter(s); }}>
        {s === '' ? c.common.all : `${c.feedback.statuses[s]}${data ? ` · ${data.counts[s]}` : ''}`}
      </button>)}
    </div>
    <DataTable columns={columns} rows={data?.items ?? []} rowKey={(f) => f.id}
      loading={!data && !error} error={error} onRetry={() => { setError(false); load(); }} />
    <ConfirmDialog open={pending !== null} onOpenChange={(open) => { if (!open) setPending(null); }}
      title={pending ? c.feedback.confirmStatus(c.feedback.statuses[pending.status]) : ''} onConfirm={confirm} />
  </div>;
}
