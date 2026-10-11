'use client';

import Link from 'next/link';
import { Suspense, useCallback, useEffect, useState } from 'react';
import { usePathname, useRouter, useSearchParams } from 'next/navigation';
import { adminSend, errorText } from '@/lib/admin-api';
import { formatDate, formatDateTime, formatNumber, useAdminCopy } from '@/lib/admin-i18n';
import type { AdminUserRow, UsersPage } from '@/lib/admin-types';
import { useAdminFetch } from '@/lib/use-admin-fetch';
import { PageHeader } from '@/components/admin/PageHeader';
import { DataTable, type Column } from '@/components/admin/DataTable';
import { Pagination } from '@/components/admin/Pagination';
import { ConfirmDialog } from '@/components/admin/ConfirmDialog';
import { Badge } from '@/components/admin/Badge';
import styles from '../admin.module.css';

const PLAN_FILTERS = ['free', 'pro', 'business', 'expiring'] as const;
const STATUS_FILTERS = ['active', 'blocked', 'unverified', 'admin'] as const;
const SORTS = ['created_desc', 'last_login_desc', 'period_end_asc'] as const;
const LIMIT = 50;

function pick<T extends string>(value: string | null, allowed: readonly T[]): T | '' {
  return value !== null && (allowed as readonly string[]).includes(value) ? (value as T) : '';
}

interface SettleResult { email: string; plan: string; period_end: string | null; replayed: boolean }

type AdminCopy = ReturnType<typeof useAdminCopy>['c'];

function StatusBadge({ user, c }: Readonly<{ user: AdminUserRow; c: AdminCopy }>) {
  if (!user.is_active) return <Badge tone="error">{c.users.statuses.blocked}</Badge>;
  if (!user.email_verified) return <Badge tone="warning">{c.users.statuses.unverified}</Badge>;
  if (user.role === 'admin') return <Badge tone="neutral">{c.users.statuses.admin}</Badge>;
  return <>{c.common.dash}</>;
}

function UsersList() {
  const { c, locale } = useAdminCopy();
  const params = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const q = (params.get('q') ?? '').trim().slice(0, 100);
  const plan = pick(params.get('plan'), PLAN_FILTERS);
  const status = pick(params.get('status'), STATUS_FILTERS);
  const sort = pick(params.get('sort'), SORTS);
  const offset = Math.max(0, Math.floor(Number(params.get('offset')) || 0));

  const update = useCallback((patch: Record<string, string>) => {
    const next = new URLSearchParams(params.toString());
    for (const [k, v] of Object.entries(patch)) { if (v) next.set(k, v); else next.delete(k); }
    if (!('offset' in patch)) next.delete('offset');
    const s = next.toString();
    router.replace(s ? `${pathname}?${s}` : pathname, { scroll: false });
  }, [params, pathname, router]);

  // The box follows the URL (back/forward, reset) without clobbering what the user is typing.
  const [draft, setDraft] = useState(q);
  const [seenQ, setSeenQ] = useState(q);
  if (q !== seenQ) { setSeenQ(q); if (draft.trim() !== q) setDraft(q); }
  useEffect(() => {
    if (draft.trim().slice(0, 100) === q) return;
    const t = setTimeout(() => update({ q: draft.trim().slice(0, 100) }), 300);
    return () => clearTimeout(t);
  }, [draft, q, update]);

  const query = new URLSearchParams({ limit: String(LIMIT), offset: String(offset) });
  if (q) query.set('q', q);
  if (plan) query.set('plan', plan);
  if (status) query.set('status', status);
  if (sort) query.set('sort', sort);
  const { data, error, loading, reload } = useAdminFetch<UsersPage>(`/api/v1/admin/users?${query}`);
  const users = data?.items ?? [];
  const total = data?.total ?? 0;
  const filtered = Boolean(q || plan || status || sort);
  const listQuery = params.toString();
  const cardHref = (id: string) => `/admin/users/${id}${listQuery ? `?back=${encodeURIComponent(`?${listQuery}`)}` : ''}`;
  const reset = () => { setDraft(''); router.replace(pathname, { scroll: false }); };

  const [checkoutId, setCheckoutId] = useState('');
  const [settling, setSettling] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const settle = async (reason: string) => {
    if (!settling) return;
    let d: SettleResult;
    try {
      d = await adminSend<SettleResult>('/api/v1/billing/admin/activate', 'POST', { checkout_id: settling, reason });
    } catch (e) {
      throw new Error(errorText(c, e));
    }
    setMessage((d.replayed ? c.users.replayed : c.users.settled)(d.email, d.plan, formatDate(d.period_end, locale)));
    setCheckoutId('');
    reload();
  };

  const columns: Column<AdminUserRow>[] = [
    { key: 'login', header: c.users.login, render: (u) => <Link href={cardHref(u.id)}><strong>{u.username}</strong></Link> },
    { key: 'email', header: c.users.email, render: (u) => u.email },
    { key: 'plan', header: c.users.plan, render: (u) => <Badge tone={u.plan === 'free' ? 'neutral' : 'success'}>{c.users.plans[u.plan]}</Badge> },
    { key: 'until', header: c.users.until, render: (u) => formatDate(u.period_end, locale) },
    { key: 'status', header: c.users.status, render: (u) => <StatusBadge user={u} c={c} /> },
    { key: 'last', header: c.users.lastLogin, render: (u) => <span className={styles.muted}>{formatDateTime(u.last_login, locale)}</span> },
  ];

  return <div className={styles.page}>
    <PageHeader title={`${c.users.title} (${formatNumber(total, locale)})`} />

    <section className={`liquid-glass ${styles.panel}`}>
      <div className={styles.toolbar}>
        <input className={styles.input} type="search" aria-label={c.users.search} placeholder={c.users.search}
          maxLength={100} value={draft} onChange={(e) => setDraft(e.target.value)} />
        <select className={styles.select} aria-label={c.users.planFilter} value={plan} onChange={(e) => update({ plan: e.target.value })}>
          <option value="">{c.users.planFilter}: {c.common.all}</option>
          {PLAN_FILTERS.map((p) => <option key={p} value={p}>{c.users.plans[p]}</option>)}
        </select>
        <select className={styles.select} aria-label={c.users.statusFilter} value={status} onChange={(e) => update({ status: e.target.value })}>
          <option value="">{c.users.statusFilter}: {c.common.all}</option>
          {STATUS_FILTERS.map((s) => <option key={s} value={s}>{c.users.statuses[s]}</option>)}
        </select>
        <select className={styles.select} aria-label={c.users.sortLabel} value={sort || 'created_desc'}
          onChange={(e) => update({ sort: e.target.value === 'created_desc' ? '' : e.target.value })}>
          {SORTS.map((s) => <option key={s} value={s}>{c.users.sorts[s]}</option>)}
        </select>
        {filtered && <button type="button" className={styles.button} onClick={reset}>{c.users.reset}</button>}
      </div>
    </section>

    <DataTable columns={columns} rows={users} rowKey={(u) => u.id} loading={loading} error={error} onRetry={reload}
      emptyText={filtered ? c.users.notFound : undefined} />
    {!loading && !error && filtered && users.length === 0 &&
      <button type="button" className={styles.button} onClick={reset}>{c.users.reset}</button>}
    <Pagination offset={offset} limit={LIMIT} total={total} onChange={(next) => update({ offset: next ? String(next) : '' })} />

    <section className={`liquid-glass ${styles.panel}`}>
      <h2 className={styles.panelTitle}>{c.users.settleTitle}</h2>
      <div className={styles.toolbar}>
        <input className={styles.input} aria-label={c.users.checkoutPlaceholder} placeholder={c.users.checkoutPlaceholder}
          value={checkoutId} onChange={(e) => setCheckoutId(e.target.value)} />
        <button type="button" className={`${styles.button} ${styles.buttonPrimary}`} disabled={!checkoutId.trim()}
          onClick={() => setSettling(checkoutId.trim())}>{c.users.settle}</button>
      </div>
      {message && <p className={styles.notice} role="status">{message}</p>}
    </section>

    <ConfirmDialog open={settling !== null} onOpenChange={(open) => { if (!open) setSettling(null); }}
      title={c.users.confirmSettle} onConfirm={settle} />
  </div>;
}

export default function AdminUsers() {
  return <Suspense><UsersList /></Suspense>;
}
