'use client';

import Link from 'next/link';
import { Suspense, useState } from 'react';
import { useParams, useSearchParams } from 'next/navigation';
import { formatDate, formatDateTime, formatNumber, useAdminCopy } from '@/lib/admin-i18n';
import type { UserCard } from '@/lib/admin-types';
import { useAdminFetch } from '@/lib/use-admin-fetch';
import { PageHeader } from '@/components/admin/PageHeader';
import { AdminState } from '@/components/admin/AdminState';
import { Badge } from '@/components/admin/Badge';
import { StatTile } from '@/components/admin/StatTile';
import { DataTable, type Column } from '@/components/admin/DataTable';
import { UserActions } from './UserActions';
import styles from '../../admin.module.css';

function money(minor: number, currency: string, locale: string | string[]) {
  return new Intl.NumberFormat(locale, { style: 'currency', currency }).format(minor / 100);
}

function Card() {
  const { c, locale } = useAdminCopy();
  const { id } = useParams<{ id: string }>();
  const back = useSearchParams().get('back');
  const backHref = `/admin/users${back && back.startsWith('?') ? back : ''}`;
  const { data, error, status, loading, reload, setData } = useAdminFetch<UserCard>(`/api/v1/admin/users/${id}`);
  const [notice, setNotice] = useState<string | null>(null);

  const backLink = <Link href={backHref} className={styles.back}>{c.card.back}</Link>;
  if (error && status === 404) return <div className={styles.page}>{backLink}<AdminState kind="empty" message={c.card.notFound} /></div>;
  if (error) return <div className={styles.page}>{backLink}<AdminState kind="error" onRetry={reload} /></div>;
  if (!data || (loading && data.profile.id !== id)) return <div className={styles.page}>{backLink}<AdminState kind="loading" /></div>;

  const { profile, subscription, payments, checkouts, activity } = data;
  const n = (v: number) => formatNumber(v, locale);
  const paymentColumns: Column<UserCard['payments'][number]>[] = [
    { key: 'date', header: c.card.date, render: (p) => formatDateTime(p.created_at, locale) },
    { key: 'amount', header: c.card.amount, render: (p) => money(p.amount_minor, p.currency, locale) },
    { key: 'provider', header: c.card.provider, render: (p) => p.provider },
    { key: 'state', header: c.card.state, render: (p) => p.status },
  ];
  const checkoutColumns: Column<UserCard['checkouts'][number]>[] = [
    { key: 'date', header: c.card.date, render: (o) => formatDateTime(o.created_at, locale) },
    { key: 'plan', header: c.card.plan, render: (o) => `${o.plan} · ${c.users.months(o.months)}` },
    { key: 'amount', header: c.card.amount, render: (o) => money(o.amount_minor, o.currency, locale) },
    { key: 'state', header: c.card.state, render: (o) => <span className={styles.mono}>{o.status}</span> },
  ];

  return <div className={styles.page}>
    {backLink}
    <PageHeader title={profile.username} subtitle={profile.email} />
    <div className={styles.badges}>
      {profile.role === 'admin' && <Badge tone="neutral">{c.users.statuses.admin}</Badge>}
      {!profile.is_active && <Badge tone="error">{c.users.statuses.blocked}</Badge>}
      {!profile.email_verified && <Badge tone="warning">{c.users.statuses.unverified}</Badge>}
      <Badge tone={profile.effective_plan === 'free' ? 'neutral' : 'success'}>{c.users.plans[profile.effective_plan]}</Badge>
    </div>
    {notice && <p className={styles.notice} role="status">{notice}</p>}

    <div className={styles.cardGrid}>
      <section className={`liquid-glass ${styles.panel}`}>
        <h2 className={styles.panelTitle}>{c.card.profile}</h2>
        <dl className={styles.facts}>
          <dt>{c.card.fullName}</dt><dd>{profile.full_name ?? c.common.dash}</dd>
          <dt>{c.card.registered}</dt><dd>{formatDateTime(profile.created_at, locale)}</dd>
          <dt>{c.card.lastLogin}</dt><dd>{formatDateTime(profile.last_login, locale)}</dd>
          <dt>{c.card.role}</dt><dd>{profile.role}</dd>
        </dl>
      </section>

      <section className={`liquid-glass ${styles.panel}`}>
        <h2 className={styles.panelTitle}>{c.card.subscription}</h2>
        {subscription ? <dl className={styles.facts}>
          <dt>{c.card.plan}</dt><dd>{c.users.plans[subscription.plan]}</dd>
          <dt>{c.card.status}</dt><dd>{c.card.subStatuses[subscription.status]}</dd>
          <dt>{c.card.until}</dt><dd>{formatDate(subscription.period_end, locale)}
            {subscription.days_left !== null && <span className={styles.muted}> · {c.card.daysLeft(subscription.days_left)}</span>}</dd>
          <dt>{c.card.source}</dt><dd>{c.card.sources[subscription.source]}</dd>
        </dl> : <p className={styles.muted}>{c.card.noSubscription}</p>}
      </section>
    </div>

    <section>
      <h2 className={styles.panelTitle}>{c.card.activity}</h2>
      <div className={styles.tiles}>
        <StatTile label={c.card.questions7d} value={n(activity.questions_7d)} detail={c.card.conversations(n(activity.conversations_7d))} />
        <StatTile label={c.card.questions30d} value={n(activity.questions_30d)} detail={c.card.conversations(n(activity.conversations_30d))} />
        {activity.daily_limit !== null && <StatTile label={c.card.today}
          value={activity.questions_today === null ? c.common.dash : c.card.todayValue(n(activity.questions_today), n(activity.daily_limit))}
          detail={activity.questions_today === null ? c.card.noData : undefined} />}
        <StatTile label={c.card.feedback} value={n(activity.feedback_total)} />
      </div>
    </section>

    <UserActions card={data} onUpdated={(next, text) => { setData(next); setNotice(text); }} onReload={reload} />

    <section>
      <h2 className={styles.panelTitle}>{c.card.payments}</h2>
      <DataTable columns={paymentColumns} rows={payments} rowKey={(p) => p.id} emptyText={c.card.none} />
    </section>
    <section>
      <h2 className={styles.panelTitle}>{c.card.checkouts}</h2>
      <DataTable columns={checkoutColumns} rows={checkouts} rowKey={(o) => o.id} emptyText={c.card.none} />
    </section>
  </div>;
}

export default function AdminUserCard() {
  return <Suspense><Card /></Suspense>;
}
