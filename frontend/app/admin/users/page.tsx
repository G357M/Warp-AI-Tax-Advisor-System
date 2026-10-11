'use client';

import { useCallback, useEffect, useState } from 'react';
import { authFetch } from '@/lib/auth';
import { formatDate, formatDateTime, formatNumber, useAdminCopy } from '@/lib/admin-i18n';
import { PageHeader } from '@/components/admin/PageHeader';
import { DataTable, type Column } from '@/components/admin/DataTable';
import { Pagination } from '@/components/admin/Pagination';
import { ConfirmDialog } from '@/components/admin/ConfirmDialog';
import { Badge } from '@/components/admin/Badge';
import styles from '../admin.module.css';

interface AdminUser {
  id: string; username: string; email: string; role: 'user' | 'admin';
  created_at: string | null; last_login: string | null; plan: string; period_end: string | null;
}

type Pending =
  | { kind: 'role'; user: AdminUser; role: 'user' | 'admin' }
  | { kind: 'settle'; checkoutId: string }
  | { kind: 'activate'; email: string; plan: 'pro' | 'business'; months: number };

const LIMIT = 50;

async function send(url: string, method: string, body: object, fallback: string) {
  const res = await authFetch(url, { method, body: JSON.stringify(body) });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(typeof data.detail === 'string' ? data.detail : fallback);
  return data;
}

export default function AdminUsers() {
  const { c, locale } = useAdminCopy();
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [total, setTotal] = useState(0);
  const [offset, setOffset] = useState(0);
  const [loadedOffset, setLoadedOffset] = useState<number | null>(null);
  const [error, setError] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [checkoutId, setCheckoutId] = useState('');
  const [email, setEmail] = useState('');
  const [plan, setPlan] = useState<'pro' | 'business'>('pro');
  const [months, setMonths] = useState(1);
  const [pending, setPending] = useState<Pending | null>(null);

  const load = useCallback(() => {
    authFetch(`/api/v1/admin/users?limit=${LIMIT}&offset=${offset}`)
      .then((r) => (r.ok ? r.json() : Promise.reject()))
      .then((d) => { setUsers(d.items); setTotal(d.total); setError(false); })
      .catch(() => setError(true))
      .finally(() => setLoadedOffset(offset));
  }, [offset]);
  useEffect(load, [load]);
  const loading = loadedOffset !== offset;
  const retry = () => { setError(false); load(); };
  const goTo = (next: number) => { setError(false); setOffset(next); };

  const confirm = async (reason: string) => {
    if (!pending) return;
    const until = (d: { period_end: string | null }) => formatDate(d.period_end, locale);
    if (pending.kind === 'role') {
      await send(`/api/v1/admin/users/${pending.user.id}/role`, 'PATCH', { role: pending.role, reason }, c.common.saveError);
    } else if (pending.kind === 'settle') {
      const d = await send('/api/v1/billing/admin/activate', 'POST', { checkout_id: pending.checkoutId, reason }, c.common.saveError);
      setMessage((d.replayed ? c.users.replayed : c.users.settled)(d.email, d.plan, until(d)));
      setCheckoutId('');
    } else {
      const d = await send('/api/v1/billing/admin/activate', 'POST',
        { email: pending.email, plan: pending.plan, months: pending.months, reason }, c.common.saveError);
      setMessage(c.users.activated(d.email, d.plan, until(d)));
      setEmail('');
    }
    load();
  };

  const dialogTitle = !pending ? '' : pending.kind === 'role' ? c.users.confirmRole(pending.user.username, pending.role)
    : pending.kind === 'settle' ? c.users.confirmSettle : c.users.confirmActivate(pending.email, pending.plan, pending.months);

  const columns: Column<AdminUser>[] = [
    { key: 'login', header: c.users.login, render: (u) => <strong>{u.username}</strong> },
    { key: 'email', header: c.users.email, render: (u) => u.email },
    { key: 'role', header: c.users.role, render: (u) => <select className={styles.select} aria-label={`${c.users.role}: ${u.username}`}
      value={u.role} onChange={(e) => setPending({ kind: 'role', user: u, role: e.target.value as 'user' | 'admin' })}>
      <option value="user">user</option><option value="admin">admin</option>
    </select> },
    { key: 'plan', header: c.users.plan, render: (u) => <Badge tone={u.plan === 'free' ? 'neutral' : 'success'}>{u.plan}</Badge> },
    { key: 'until', header: c.users.until, render: (u) => formatDate(u.period_end, locale) },
    { key: 'last', header: c.users.lastLogin, render: (u) => <span className={styles.muted}>{formatDateTime(u.last_login, locale)}</span> },
  ];

  return <div className={styles.page}>
    <PageHeader title={`${c.users.title} (${formatNumber(total, locale)})`} />

    <section className={`liquid-glass ${styles.panel}`}>
      <h2 className={styles.panelTitle}>{c.users.settleTitle}</h2>
      <div className={styles.toolbar}>
        <input className={styles.input} aria-label={c.users.checkoutPlaceholder} placeholder={c.users.checkoutPlaceholder}
          value={checkoutId} onChange={(e) => setCheckoutId(e.target.value)} />
        <button type="button" className={`${styles.button} ${styles.buttonPrimary}`} disabled={!checkoutId.trim()}
          onClick={() => setPending({ kind: 'settle', checkoutId: checkoutId.trim() })}>{c.users.settle}</button>
      </div>
      <hr className={styles.divider} />
      <h2 className={styles.panelTitle}>{c.users.legacyTitle}</h2>
      <div className={styles.toolbar}>
        <input className={styles.input} type="email" aria-label={c.users.emailPlaceholder} placeholder={c.users.emailPlaceholder}
          value={email} onChange={(e) => setEmail(e.target.value)} />
        <select className={styles.select} aria-label={c.users.plan} value={plan} onChange={(e) => setPlan(e.target.value as 'pro' | 'business')}>
          <option value="pro">Pro</option><option value="business">Business</option>
        </select>
        <select className={styles.select} aria-label={c.users.period} value={months} onChange={(e) => setMonths(Number(e.target.value))}>
          {[1, 3, 6, 12].map((m) => <option key={m} value={m}>{c.users.months(m)}</option>)}
        </select>
        <button type="button" className={styles.button} disabled={!email.trim()}
          onClick={() => setPending({ kind: 'activate', email: email.trim(), plan, months })}>{c.users.activate}</button>
      </div>
      {message && <p className={styles.notice} role="status">{message}</p>}
    </section>

    <DataTable columns={columns} rows={users} rowKey={(u) => u.id} loading={loading} error={error} onRetry={retry} />
    <Pagination offset={offset} limit={LIMIT} total={total} onChange={goTo} />

    <ConfirmDialog open={pending !== null} onOpenChange={(open) => { if (!open) setPending(null); }}
      title={dialogTitle} onConfirm={confirm} />
  </div>;
}
