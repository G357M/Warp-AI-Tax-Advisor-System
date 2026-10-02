'use client';

import { useEffect, useRef, useState } from 'react';
import Link from 'next/link';
import { ArrowLeft, ArrowRight, RefreshCw } from 'lucide-react';
import { authFetch } from '@/lib/auth';
import { DATE_LOCALES, useT } from '@/lib/i18n';
import { formatMinorMoney } from '@/lib/plans';
import {
  ReconciliationDetail, ReconciliationQueue, reconciliationCopy, reviewReason,
} from '@/lib/billing-reconciliation';
import styles from './reconciliation.module.css';
import ReviewControls from './ReviewControls';

const PAGE_SIZE = 25;
const QUEUE_URL = '/api/v1/billing/admin/reconciliation';

// Keep responses tied to their request. A slow prior selection may never
// appear under another order's heading, including after retry or pagination.
function useEvidence<T>(url: string | null, revision: number) {
  const key = `${url}:${revision}`;
  const [result, setResult] = useState<{ key: string; data?: T; error?: number }>();
  useEffect(() => {
    if (!url) return;
    const controller = new AbortController();
    authFetch(url, { signal: controller.signal, cache: 'no-store' })
      .then(async (response) => {
        if (!response.ok) throw response.status;
        return response.json() as Promise<T>;
      })
      .then((data) => {
        if (!controller.signal.aborted) setResult({ key, data });
      })
      .catch((error: unknown) => {
        if (!controller.signal.aborted) setResult({ key, error: typeof error === 'number' ? error : 503 });
      });
    return () => controller.abort();
  }, [url, key]);
  return result?.key === key ? result : undefined;
}

export default function BillingReconciliationPage() {
  const { lang } = useT();
  const c = reconciliationCopy[lang];
  const [offset, setOffset] = useState(0);
  const [revision, setRevision] = useState(0);
  const [detailRevision, setDetailRevision] = useState(0);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [decisionAccessError, setDecisionAccessError] = useState<number>();
  const detailRegion = useRef<HTMLElement>(null);
  const queue = useEvidence<ReconciliationQueue>(`${QUEUE_URL}?limit=${PAGE_SIZE}&offset=${offset}`, revision);
  const detail = useEvidence<ReconciliationDetail>(selectedId ? `${QUEUE_URL}/${encodeURIComponent(selectedId)}` : null, detailRevision);

  function resetQueue() {
    setSelectedId(null);
    setOffset(0);
    setRevision((value) => value + 1);
  }

  function changePage(nextOffset: number) {
    setSelectedId(null);
    setOffset(nextOffset);
  }

  function openOrder(id: string) {
    setSelectedId(id);
    setDetailRevision((value) => value + 1);
    requestAnimationFrame(() => detailRegion.current?.focus({ preventScroll: false }));
  }

  function date(value: string | null) {
    if (!value) return c.noValue;
    // Backend timestamps without a suffix are UTC, never browser-local time.
    const utc = /(?:Z|[+-]\d{2}:\d{2})$/i.test(value) ? value : `${value}Z`;
    const parsed = new Date(utc);
    if (Number.isNaN(parsed.getTime())) return c.noValue;
    return new Intl.DateTimeFormat(DATE_LOCALES[lang], {
      year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit',
      hourCycle: 'h23', timeZone: 'UTC',
    }).format(parsed);
  }

  function errorMessage(status: number) {
    if (status === 401) return c.signedOut;
    if (status === 403) return c.forbidden;
    if (status === 404) return c.missing;
    return c.unavailable;
  }

  function errorState(status: number, retry: () => void) {
    return <div className={styles.error} role="alert">
      <p>{errorMessage(status)}</p>
      {status === 401 ? <Link href="/login" className={styles.button}>{c.login}</Link>
        : status !== 403 && <button type="button" className={styles.button} onClick={retry}>{c.retry}</button>}
    </div>;
  }

  const order = detail?.data?.checkout;
  const reason = order ? reviewReason(order.reason, lang) : null;
  const accessError = [queue?.error, detail?.error, decisionAccessError].find((status) => status === 401 || status === 403);
  if (accessError) return <div className={styles.page}>
    <div className={styles.heading}><h1>{c.title}</h1></div>
    {errorState(accessError, resetQueue)}
  </div>;

  return <div className={styles.page}>
    <div className={styles.heading}>
      <div><h1>{c.title}</h1><p>{c.intro}</p></div>
      <button type="button" className={styles.button} onClick={resetQueue} disabled={!queue}>
        <RefreshCw size={16} aria-hidden="true" />{c.refresh}
      </button>
    </div>
    <p className={styles.notice}>{c.readOnly}</p>
    <div className={styles.workspace}>
      <section aria-labelledby="billing-queue-title" className={styles.queue} aria-busy={!queue}>
        <div className={styles.sectionHeading}>
          <h2 id="billing-queue-title">{c.queue}</h2>
          {queue?.data && <span>{c.rows}: {queue.data.items.length}</span>}
        </div>
        {!queue && <p role="status" className={styles.empty}>{c.loading}</p>}
        {queue?.error && errorState(queue.error, resetQueue)}
        {queue?.data && <>
          {queue.data.items.length === 0 ? <div className={styles.empty} role="status">
            <h3>{offset === 0 ? c.empty : c.pageEmpty}</h3>
            {offset === 0 ? <p>{c.emptyBody}</p> : <button type="button" onClick={resetQueue} className={styles.button}>{c.first}</button>}
          </div> : <ul className={styles.orders}>
            {queue.data.items.map((item) => <li key={item.id}>
              <button type="button" className={styles.order} onClick={() => openOrder(item.id)}
                aria-pressed={selectedId === item.id} aria-controls="billing-detail"
                aria-label={`${c.order} ${item.id}`}>
                <span className={styles.orderTop}><strong>{item.plan === 'pro' ? 'Pro' : item.plan === 'business' ? 'Business' : item.plan}</strong>
                  <strong>{formatMinorMoney(item.amount_minor, item.currency, lang)}</strong></span>
                <span className={styles.reason}>{reviewReason(item.reason, lang).title}</span>
                <span className={styles.orderMeta}><span>{item.provider === 'tbc' ? 'TBC' : item.provider}</span><span>{date(item.created_at)}</span></span>
                <span className={styles.mono}>{item.id}</span>
              </button>
            </li>)}
          </ul>}
          <nav className={styles.pagination} aria-label={c.queue}>
            <button type="button" className={styles.button} disabled={offset === 0} onClick={() => changePage(Math.max(0, offset - PAGE_SIZE))}>
              <ArrowLeft size={16} aria-hidden="true" />{c.previous}
            </button>
            <span>{c.page} {Math.floor(offset / PAGE_SIZE) + 1}</span>
            <button type="button" className={styles.button} disabled={queue.data.next_offset === null}
              onClick={() => { if (queue.data?.next_offset !== null && queue.data?.next_offset !== undefined) changePage(queue.data.next_offset); }}>
              {c.next}<ArrowRight size={16} aria-hidden="true" />
            </button>
          </nav>
        </>}
      </section>

      <section id="billing-detail" ref={detailRegion} tabIndex={-1} aria-labelledby="billing-detail-title"
        className={styles.detail} aria-busy={!!selectedId && !detail}>
        <h2 id="billing-detail-title">{c.details}</h2>
        {!selectedId && <p className={styles.empty}>{c.select}</p>}
        {selectedId && <p className={styles.mono}>{selectedId}</p>}
        {selectedId && !detail && <p role="status" className={styles.empty}>{c.loadingDetail}</p>}
        {detail?.error && errorState(detail.error, () => setDetailRevision((value) => value + 1))}
        {order && reason && <>
          <div className={styles.guidance}><h3>{reason.title}</h3><p>{reason.help}</p></div>
          <p className={styles.credit}>{order.settled_payment_id ? c.recorded : c.unrecorded}</p>
          <dl className={styles.facts}>
            <div><dt>{c.amount}</dt><dd>{formatMinorMoney(order.amount_minor, order.currency, lang)}</dd></div>
            <div><dt>{c.plan}</dt><dd>{order.plan === 'pro' ? 'Pro' : order.plan === 'business' ? 'Business' : order.plan}</dd></div>
            <div><dt>{c.bankStatus}</dt><dd>{order.provider_status || c.noValue}</dd></div>
            <div><dt>{c.checkoutStatus}</dt><dd>{order.status}</dd></div>
            <div><dt>{c.checked}</dt><dd>{date(order.provider_checked_at)}</dd></div>
            <div><dt>{c.expires}</dt><dd>{date(order.expires_at)}</dd></div>
            <div><dt>{c.created}</dt><dd>{date(order.created_at)}</dd></div>
            <div><dt>{c.updated}</dt><dd>{date(order.updated_at)}</dd></div>
            <div className={styles.wide}><dt>{c.bankOrder}</dt><dd className={styles.mono}>{order.provider_order_id || c.noValue}</dd></div>
            <div className={styles.wide}><dt>{c.user}</dt><dd className={styles.mono}>{order.user_id}</dd></div>
            {order.settled_payment_id && <div className={styles.wide}><dt>{c.payment}</dt><dd className={styles.mono}>{order.settled_payment_id}</dd></div>}
          </dl>
          <div className={styles.eventHeading}><h3>{c.events}</h3></div>
          {detail.data?.events_truncated && <p className={styles.notice} role="status">{c.truncated}</p>}
          {detail.data?.events.length === 0 && <p className={styles.empty}>{c.noEvents}</p>}
          <ol className={styles.events}>
            {detail.data?.events.map((event) => <li key={event.id}>
              <details>
                <summary><span><strong>{event.provider_status}</strong><time>{date(event.created_at)}</time></span></summary>
                <dl className={styles.facts}>
                  <div><dt>{c.eventDetails}</dt><dd>{event.processing_status}</dd></div>
                  <div><dt>{c.processed}</dt><dd>{date(event.processed_at)}</dd></div>
                  {event.error_code && <div className={styles.wide}><dt>{c.errorCode}</dt><dd className={styles.mono}>{event.error_code}</dd></div>}
                  <div className={styles.wide}><dt>{c.eventId}</dt><dd className={styles.mono}>{event.id}</dd></div>
                  <div className={styles.wide}><dt>{c.digest}</dt><dd className={styles.mono}>{event.payload_sha256}</dd></div>
                </dl>
              </details>
            </li>)}
          </ol>
          <ReviewControls key={order.id} order={order} date={date} onRefresh={resetQueue} onAccessError={setDecisionAccessError} />
        </>}
      </section>
    </div>
    <p className={styles.footnote}>{c.timezone}</p>
  </div>;
}
