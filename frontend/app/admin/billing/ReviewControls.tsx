'use client';

import { useEffect, useRef, useState } from 'react';
import { authFetch } from '@/lib/auth';
import { useT } from '@/lib/i18n';
import { formatMinorMoney } from '@/lib/plans';
import { DecisionBody, DecisionHistory, ReviewAction, ReviewDecision, ReviewPreview, reviewCopy } from '@/lib/billing-review';
import type { ReconciliationItem } from '@/lib/billing-reconciliation';
import styles from './reconciliation.module.css';

export default function ReviewControls({ order, date, onRefresh, onAccessError }: {
  order: ReconciliationItem; date: (value: string | null) => string;
  onRefresh: () => void; onAccessError: (status: number) => void;
}) {
  const { lang } = useT();
  const c = reviewCopy[lang];
  const url = `/api/v1/billing/admin/reconciliation/${encodeURIComponent(order.id)}`;
  const [preview, setPreview] = useState<ReviewPreview>();
  const [action, setAction] = useState<ReviewAction>('keep_review');
  const [reason, setReason] = useState('');
  const [confirmed, setConfirmed] = useState(false);
  const [busy, setBusy] = useState(false);
  const [hasPending, setHasPending] = useState(false);
  const [error, setError] = useState<'unavailable' | 'stale' | 'uncertain' | 'invalid'>();
  const [receipt, setReceipt] = useState<ReviewDecision>();
  const [history, setHistory] = useState<DecisionHistory>();
  const [historyError, setHistoryError] = useState(false);
  const [historyBusy, setHistoryBusy] = useState(false);
  const request = useRef<AbortController | null>(null);
  const historyRequest = useRef<AbortController | null>(null);
  const pending = useRef<{ key: string; body: DecisionBody } | null>(null);
  const form = useRef<HTMLDivElement>(null);
  useEffect(() => () => { request.current?.abort(); historyRequest.current?.abort(); }, []);

  async function prepare(bank: boolean) {
    if (request.current || pending.current) return;
    const controller = new AbortController();
    request.current = controller;
    setBusy(true); setError(undefined); setConfirmed(false); setPreview(undefined);
    try {
      const response = await authFetch(`${url}/preview?verify_provider=${bank}`, { method: 'POST', signal: AbortSignal.any([controller.signal, AbortSignal.timeout(45_000)]) });
      if (!response.ok) throw response.status;
      const data: ReviewPreview = await response.json();
      if (controller.signal.aborted) return;
      setPreview(data); setAction('keep_review');
      requestAnimationFrame(() => form.current?.focus());
    } catch (status) {
      if (!controller.signal.aborted) {
        if (status === 401 || status === 403) onAccessError(status);
        else setError(status === 409 ? 'stale' : 'unavailable');
      }
    } finally {
      request.current = null;
      if (!controller.signal.aborted) setBusy(false);
    }
  }

  async function save() {
    if (request.current) return;
    if (!pending.current) {
      if (!preview || !confirmed || reason.trim().length < 10 || !preview.actions[action]) return;
      pending.current = { key: crypto.randomUUID(), body: {
        action, reason: reason.trim(), expected_state_sha256: preview.state_sha256,
        expected_provider_sha256: preview.provider_sha256, expected_access_effect: preview.actions[action]!,
      } };
      setHasPending(true);
    }
    const controller = new AbortController();
    request.current = controller;
    setBusy(true); setError(undefined);
    try {
      const response = await authFetch(`${url}/decisions`, {
        method: 'POST', signal: AbortSignal.any([controller.signal, AbortSignal.timeout(45_000)]),
        headers: { 'Content-Type': 'application/json', 'Idempotency-Key': pending.current.key },
        body: JSON.stringify(pending.current.body),
      });
      if (!response.ok) throw response.status;
      const data: { decision: ReviewDecision } = await response.json();
      if (controller.signal.aborted) return;
      setReceipt(data.decision); setPreview(undefined); pending.current = null; setHasPending(false);
      // Inserting at the front shifts every server offset. Restart history
      // instead of retaining the old page boundary, including in-flight reads.
      historyRequest.current?.abort(); historyRequest.current = null;
      setHistory(undefined); setHistoryBusy(false); setHistoryError(false);
    } catch (status) {
      if (!controller.signal.aborted) {
        if (status === 401 || status === 403) onAccessError(status);
        else if (status === 409 || status === 422) {
          pending.current = null; setHasPending(false); setPreview(undefined); setConfirmed(false);
          setError(status === 409 ? 'stale' : 'invalid');
        } else setError('uncertain');
      }
    } finally {
      request.current = null;
      if (!controller.signal.aborted) setBusy(false);
    }
  }

  async function loadHistory(offset = 0) {
    if (historyRequest.current) return;
    const controller = new AbortController(); historyRequest.current = controller;
    setHistoryBusy(true); setHistoryError(false);
    try {
      const response = await authFetch(`${url}/decisions?limit=25&offset=${offset}`, { signal: AbortSignal.any([controller.signal, AbortSignal.timeout(45_000)]), cache: 'no-store' });
      if (!response.ok) throw response.status;
      const data: DecisionHistory = await response.json();
      if (!controller.signal.aborted) setHistory((old) => ({ ...data,
        items: [...new Map((offset ? [...(old?.items ?? []), ...data.items] : data.items).map((item) => [item.id, item])).values()],
      }));
    } catch (status) {
      if (!controller.signal.aborted) {
        if (status === 401 || status === 403) onAccessError(status);
        else setHistoryError(true);
      }
    } finally {
      if (historyRequest.current === controller) {
        historyRequest.current = null;
        if (!controller.signal.aborted) setHistoryBusy(false);
      }
    }
  }

  return <div className={styles.review}>
    <h3>{c.title}</h3><p>{c.intro}</p>
    {receipt ? <div role="status" className={styles.guidance}>
      <h3>{c.saved}</h3><p>{c[receipt.action]}</p><p className={styles.mono}>{receipt.id}</p>
      <button type="button" className={styles.button} onClick={onRefresh}>{c.refresh}</button>
    </div> : <>
      {!preview && <div className={styles.actions}>
        <button type="button" className={styles.button} disabled={busy || hasPending || !order.reason} onClick={() => prepare(false)}>{c.hold}</button>
        <button type="button" className={styles.button} disabled={busy || hasPending || !order.reason || order.provider !== 'tbc' || !order.provider_order_id} onClick={() => prepare(true)}>{c.verify}</button>
      </div>}
      {busy && <p role="status">{hasPending ? c.saving : c.checking}</p>}
      {error && <div className={styles.error} role="alert"><p>{c[error]}</p>
        {error === 'uncertain' && <button type="button" className={styles.button} disabled={busy} onClick={save}>{c.retry}</button>}
      </div>}
      {preview && <div ref={form} tabIndex={-1} className={styles.reviewForm}>
        {preview.provider_evidence && <p>{c.bank}: <strong>{preview.provider_evidence.status}</strong> · {formatMinorMoney(preview.provider_evidence.amount_minor, preview.provider_evidence.currency, lang)}</p>}
        {Object.keys(preview.actions).length === 1 && <p>{c.noResolution}</p>}
        <label htmlFor="review-action">{c.action}</label>
        <select id="review-action" value={action} disabled={busy || hasPending} onChange={(event) => { setAction(event.target.value as ReviewAction); setConfirmed(false); }}>
          {(Object.keys(preview.actions) as ReviewAction[]).map((item) => <option key={item} value={item}>{c[item]}</option>)}
        </select>
        <p className={styles.impact} role="status">{preview.actions[action] === 'grant_period' ? c.grant.replace('{days}', String(Number(preview.before.checkout.months) * 30)) : c.unchanged}</p>
        <label htmlFor="review-reason">{c.reason}</label>
        <textarea id="review-reason" value={reason} rows={4} maxLength={2000} disabled={busy || hasPending}
          aria-describedby="review-reason-hint" onChange={(event) => { setReason(event.target.value); setConfirmed(false); }} />
        <p id="review-reason-hint" className={styles.footnote}>{c.reasonHint}</p>
        <label className={styles.confirm}><input type="checkbox" checked={confirmed} disabled={busy || hasPending} onChange={(event) => setConfirmed(event.target.checked)} /><span>{c.confirm}</span></label>
        <div className={styles.actions}>
          <button type="button" className={styles.button} disabled={busy || hasPending || !confirmed || reason.trim().length < 10} onClick={save}>{c.save}</button>
          <button type="button" className={styles.button} disabled={busy || hasPending} onClick={() => { setPreview(undefined); setConfirmed(false); }}>{c.cancel}</button>
        </div>
      </div>}
    </>}
    <p className={styles.footnote}>{c.refund}</p>
    <div className={styles.eventHeading}><h3>{c.history}</h3></div>
    {historyBusy && <p role="status">{c.historyLoading}</p>}
    {historyError && <p role="alert">{c.historyError}</p>}
    {(!history || historyError) && <button type="button" className={styles.button} disabled={historyBusy} onClick={() => loadHistory()}>{c.load}</button>}
    {history?.items.length === 0 && <p>{c.empty}</p>}
    <ol className={styles.events} aria-label={c.history}>{history?.items.map((item) => <li key={item.id}>
      <details><summary><span><strong>{c[item.action]}</strong><time>{date(item.created_at)}</time></span></summary>
        <p className={styles.journalReason}>{item.reason}</p>
        <p className={styles.journalReason}>{item.access_effect === 'unchanged' ? c.unchangedPast : c.granted}</p>
        <dl className={styles.facts}><div className={styles.wide}><dt>{c.actor}</dt><dd className={styles.mono}>{item.actor_id}</dd></div>
          <div className={styles.wide}><dt>{c.id}</dt><dd className={styles.mono}>{item.id}</dd></div></dl>
      </details>
    </li>)}</ol>
    {history?.next_offset != null && <button type="button" className={styles.button} disabled={historyBusy} onClick={() => loadHistory(history.next_offset!)}>{c.more}</button>}
  </div>;
}
