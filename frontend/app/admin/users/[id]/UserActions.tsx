'use client';

import { useEffect, useState } from 'react';
import { adminSend, errorText } from '@/lib/admin-api';
import { formatDate, useAdminCopy } from '@/lib/admin-i18n';
import type { PlanId, UserCard, UserCardResponse } from '@/lib/admin-types';
import { authFetch } from '@/lib/auth';
import { useAdminFetch } from '@/lib/use-admin-fetch';
import { ConfirmDialog } from '@/components/admin/ConfirmDialog';
import styles from '../../admin.module.css';

type Paid = Exclude<PlanId, 'free'>;
type Category = 'refund' | 'mistaken_activation' | 'fraud' | 'other';
type Simple = 'block' | 'unblock' | 'role' | 'grant' | 'payment' | 'cancel' | 'reset' | 'verify';
type Dialog = Simple | { settle: string } | null;
const DAY = 86_400_000;

/** Client-side preview of core.admin_users.grant_window (the server stays authoritative). */
function grantUntil(card: UserCard, plan: Paid, days: number): Date {
  const sub = card.subscription;
  const sameActive = sub && card.profile.effective_plan === plan && sub.plan === plan && sub.period_end;
  const base = sameActive ? new Date(`${sub.period_end}Z`).getTime() : Date.now();
  return new Date(base + days * DAY);
}

function AccessButton({ isAdmin, active, onBlock, onUnblock }: {
  isAdmin: boolean; active: boolean; onBlock: () => void; onUnblock: () => void;
}) {
  const { c } = useAdminCopy();
  if (isAdmin) return <p className={styles.muted}>{c.card.demoteFirst}</p>;
  if (active) return <button type="button" className={styles.button} onClick={onBlock}>{c.card.block}</button>;
  return <button type="button" className={styles.button} onClick={onUnblock}>{c.card.unblock}</button>;
}

export function UserActions({ card, onUpdated, onReload }: {
  card: UserCard; onUpdated: (card: UserCard, notice: string) => void; onReload: (notice: string) => void;
}) {
  const { c, locale } = useAdminCopy();
  const { profile, subscription } = card;
  const [dialog, setDialog] = useState<Dialog>(null);
  const [role, setRole] = useState<'user' | 'admin'>(profile.role);
  const [plan, setPlan] = useState<Paid>('pro');
  const [days, setDays] = useState(30);
  const [replace, setReplace] = useState(false);
  const [months, setMonths] = useState(1);
  const [category, setCategory] = useState<Category>('refund');
  const [prices, setPrices] = useState<Record<string, { price_minor: number; currency: string }>>({});
  const me = useAdminFetch<{ username: string }>('/api/v1/auth/me').data;

  useEffect(() => {
    authFetch('/api/v1/billing/catalog').then((r) => (r.ok ? r.json() : null)).then((d) => {
      if (d) setPrices(Object.fromEntries(d.plans.map((p: { id: string; price_minor: number; currency: string }) => [p.id, p])));
    }).catch(() => undefined);
  }, []);

  const isAdmin = profile.role === 'admin';
  const paidActive = !isAdmin && profile.effective_plan !== 'free';
  const otherPlanActive = paidActive && profile.effective_plan !== plan;
  const [now] = useState(() => Date.now());
  const settleable = card.checkouts.filter((o) => o.provider === 'manual' && o.status === 'pending'
    && o.expires_at !== null && new Date(`${o.expires_at}Z`).getTime() > now);

  const open = (next: Dialog) => {
    setRole(profile.role); setPlan('pro'); setDays(30); setReplace(false); setMonths(1); setCategory('refund');
    setDialog(next);
  };

  const call = async (path: string, body: object, method: 'POST' | 'PATCH' = 'POST') => {
    let result: UserCardResponse;
    try {
      result = await adminSend<UserCardResponse>(`/api/v1/admin/users/${profile.id}/${path}`, method, body);
    } catch (e) {
      throw new Error(errorText(c, e));
    }
    const text = result.sent === false ? c.card.emailCooldown
      : result.sent ? c.card.emailSent : result.changed ? c.card.done : c.card.unchanged;
    onUpdated(result, text);
  };

  const confirm = async (reason: string) => {
    if (dialog === null) return;
    if (typeof dialog === 'object') {
      let d: { email: string; plan: string; period_end: string | null; replayed: boolean };
      try {
        d = await adminSend('/api/v1/billing/admin/activate', 'POST', { checkout_id: dialog.settle, reason });
      } catch (e) {
        throw new Error(errorText(c, e));
      }
      onReload((d.replayed ? c.users.replayed : c.users.settled)(d.email, d.plan, formatDate(d.period_end, locale)));
      return;
    }
    const bodies: Record<Simple, [string, object, ('POST' | 'PATCH')?]> = {
      block: ['block', { reason }], unblock: ['unblock', { reason }], role: ['role', { role, reason }, 'PATCH'],
      grant: ['grant', { plan, days, replace_active: replace, reason }],
      payment: ['record-payment', { plan, months, reason }],
      cancel: ['cancel-subscription', { category, reason }],
      reset: ['send-password-reset', { reason }], verify: ['resend-verification', { reason }],
    };
    const [path, body, method] = bodies[dialog];
    await call(path, body, method);
  };

  const u = profile.username;
  const titles: Record<Simple, string> = {
    block: c.card.confirmBlock(u), unblock: c.card.confirmUnblock(u), role: c.card.confirmRole(u),
    grant: c.card.grantTitle(u), payment: c.card.paymentTitle(u), cancel: c.card.cancelTitle(u),
    reset: c.card.confirmReset(profile.email), verify: c.card.confirmVerification(profile.email),
  };
  let title = '';
  if (typeof dialog === 'object' && dialog !== null) title = c.users.confirmSettle;
  else if (dialog !== null) title = titles[dialog];
  const price = prices[plan];

  return <section className={`liquid-glass ${styles.panel}`}>
    <h2 className={styles.panelTitle}>{c.card.actions}</h2>
    <div className={styles.cardGrid}>
      <div className={styles.actionGroup}>
        <h3>{c.card.access}</h3>
        <AccessButton isAdmin={isAdmin} active={profile.is_active} onBlock={() => open('block')} onUnblock={() => open('unblock')} />
        {me !== null && me.username !== profile.username && <button type="button" className={styles.button} onClick={() => open('role')}>{c.card.changeRole}</button>}
      </div>
      {!isAdmin && <div className={styles.actionGroup}>
        <h3>{c.card.subscriptionGroup}</h3>
        <button type="button" className={styles.button} onClick={() => open('grant')}>{c.card.grant}</button>
        <button type="button" className={styles.button} onClick={() => open('payment')}>{c.card.recordPayment}</button>
        {paidActive && <button type="button" className={styles.button} onClick={() => open('cancel')}>{c.card.cancel}</button>}
        {settleable.map((o) => <button key={o.id} type="button" className={`${styles.button} ${styles.buttonPrimary}`}
          onClick={() => open({ settle: o.id })}>{c.card.settle} · {o.plan} · {c.users.months(o.months)}</button>)}
      </div>}
      <div className={styles.actionGroup}>
        <h3>{c.card.emails}</h3>
        {profile.is_active && <button type="button" className={styles.button} onClick={() => open('reset')}>{c.card.sendReset}</button>}
        {!profile.email_verified && <button type="button" className={styles.button} onClick={() => open('verify')}>{c.card.sendVerification}</button>}
      </div>
    </div>

    <ConfirmDialog open={dialog !== null} onOpenChange={(o) => { if (!o) setDialog(null); }} title={title}
      reasonRequired={typeof dialog !== 'object'}
      canConfirm={!(dialog === 'grant' && otherPlanActive && !replace) && !(dialog === 'role' && role === profile.role)}
      onConfirm={confirm}>
      {dialog === 'role' && <label className={styles.field}>{c.card.newRole}
        <select className={styles.select} value={role} onChange={(e) => setRole(e.target.value as 'user' | 'admin')}>
          <option value="user">user</option><option value="admin">admin</option>
        </select></label>}
      {(dialog === 'grant' || dialog === 'payment') && <label className={styles.field}>{c.card.plan}
        <select className={styles.select} value={plan} onChange={(e) => setPlan(e.target.value as Paid)}>
          <option value="pro">Pro</option><option value="business">Business</option>
        </select></label>}
      {dialog === 'grant' && <>
        <label className={styles.field}>{c.card.daysLabel}
          <input className={styles.input} type="number" min={1} max={366} value={days}
            onChange={(e) => setDays(Math.min(366, Math.max(1, Math.floor(Number(e.target.value) || 1))))} /></label>
        <div className={styles.pills}>{[7, 30, 90].map((d) => <button key={d} type="button" className={styles.chip}
          aria-pressed={days === d} onClick={() => setDays(d)}>{c.users.days(d)}</button>)}</div>
        <p className={styles.muted}>{c.card.activeUntil(formatDate(grantUntil(card, plan, days).toISOString().slice(0, 19), locale))}</p>
        {otherPlanActive && <>
          <p className={styles.warning}>{c.card.replaceWarning(c.users.plans[profile.effective_plan])}</p>
          <label className={styles.checkbox}><input type="checkbox" checked={replace} onChange={(e) => setReplace(e.target.checked)} />
            {c.card.replaceConfirm}</label>
        </>}
      </>}
      {dialog === 'payment' && <>
        <label className={styles.field}>{c.card.monthsLabel}
          <select className={styles.select} value={months} onChange={(e) => setMonths(Number(e.target.value))}>
            {[1, 3, 6, 12].map((m) => <option key={m} value={m}>{c.users.months(m)}</option>)}
          </select></label>
        {price && <p>{c.card.amountLabel}: <strong>{new Intl.NumberFormat(locale, { style: 'currency', currency: price.currency })
          .format(price.price_minor * months / 100)}</strong></p>}
      </>}
      {dialog === 'cancel' && <>
        <label className={styles.field}>{c.card.category}
          <select className={styles.select} value={category} onChange={(e) => setCategory(e.target.value as Category)}>
            {(['refund', 'mistaken_activation', 'fraud', 'other'] as const).map((k) => <option key={k} value={k}>{c.card.categories[k]}</option>)}
          </select></label>
        <p className={styles.warning}>{c.card.cancelWarning(subscription?.days_left ?? 0)}</p>
      </>}
    </ConfirmDialog>
  </section>;
}
