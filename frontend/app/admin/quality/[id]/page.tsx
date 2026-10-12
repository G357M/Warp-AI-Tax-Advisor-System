'use client';

import Link from 'next/link';
import { Suspense } from 'react';
import { useParams, useSearchParams } from 'next/navigation';
import { useAdminCopy } from '@/lib/admin-i18n';
import type { QualityDetail } from '@/lib/admin-types';
import { useAdminFetch } from '@/lib/use-admin-fetch';
import { PageHeader } from '@/components/admin/PageHeader';
import { AdminState } from '@/components/admin/AdminState';
import { ReviewPanel } from './ReviewPanel';
import styles from '../../admin.module.css';

/** The feed filters to forward to the detail endpoint, which computes prev/next for that selection. */
function detailQuery(backQuery: string) {
  const params = new URLSearchParams(backQuery);
  params.delete('limit');
  params.delete('offset');
  const s = params.toString();
  return s ? `?${s}` : '';
}

function Review() {
  const { c } = useAdminCopy();
  const { id } = useParams<{ id: string }>();
  const back = useSearchParams().get('back');
  const backQuery = back?.startsWith('?') ? back : '';
  const { data, error, status, loading, reload, setData } = useAdminFetch<QualityDetail>(
    `/api/v1/admin/quality/answers/${id}${detailQuery(backQuery)}`);

  const backLink = <Link href={`/admin/quality${backQuery}`} className={styles.back}>{c.quality.back}</Link>;
  if (error && (status === 404 || status === 422)) {
    return <div className={styles.page}>{backLink}<AdminState kind="empty" message={c.errors.message_not_found} /></div>;
  }
  if (error) return <div className={styles.page}>{backLink}<AdminState kind="error" onRetry={reload} /></div>;
  if (!data || (loading && data.message.id !== id)) return <div className={styles.page}>{backLink}<AdminState kind="loading" /></div>;

  const { message, conversation, neighbors } = data;
  const suffix = backQuery ? `?back=${encodeURIComponent(backQuery)}` : '';
  const neighborLink = (target: string | null, label: string) => (target
    ? <Link href={`/admin/quality/${target}${suffix}`} className={styles.button}>{label}</Link>
    : null);
  const roleLabel = { user: c.quality.you, assistant: c.quality.assistant };

  return <div className={styles.page}>
    {backLink}
    <PageHeader title={c.quality.reviewing} subtitle={conversation.pseudonym} />
    <div className={styles.toolbar}>
      {neighborLink(neighbors.prev_id, c.quality.prev)}
      {neighborLink(neighbors.next_id, c.quality.next)}
    </div>

    <div className={styles.reviewGrid}>
      <div className={styles.page}>
        <div className={styles.thread}>
          {conversation.messages.map((m) => <div key={m.id}
            className={m.id === message.id ? `${styles.bubble} ${styles.bubbleFocus}` : styles.bubble}>
            <span className={styles.bubbleRole}>{roleLabel[m.role]}</span>
            {m.content}
          </div>)}
        </div>
        {message.sources.length > 0 && <section className={`liquid-glass ${styles.panel}`}>
          <h2 className={styles.panelTitle}>{c.quality.sources}</h2>
          <ul>
            {message.sources.map((s, i) => <li key={`${s.url ?? s.title ?? ''}-${i}`}>
              {s.url ? <a href={s.url} target="_blank" rel="noopener noreferrer">{s.title ?? s.url}</a> : s.title}
              {s.article_ref && <span className={styles.muted}> · {s.article_ref}</span>}
            </li>)}
          </ul>
        </section>}
      </div>
      <ReviewPanel key={message.id} detail={data}
        onUpdated={(next) => setData({ ...next, neighbors })} />
    </div>
  </div>;
}

export default function AdminQualityReview() {
  return <Suspense><Review /></Suspense>;
}
