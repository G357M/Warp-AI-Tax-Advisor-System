'use client';

import { useState, type FormEvent } from 'react';
import { useRouter } from 'next/navigation';
import { adminSend, errorText } from '@/lib/admin-api';
import { formatDateTime, formatNumber, useAdminCopy } from '@/lib/admin-i18n';
import { REVIEW_REASONS, VERDICTS } from '@/lib/admin-types';
import type { QualityDetail, ReviewReason, Verdict } from '@/lib/admin-types';
import { Badge } from '@/components/admin/Badge';
import { ConfirmDialog } from '@/components/admin/ConfirmDialog';
import styles from '../../admin.module.css';

const VERDICT_TONES = { correct: 'success', partial: 'warning', wrong: 'error' } as const satisfies Record<Verdict, string>;

export function ReviewPanel({ detail, onUpdated }: Readonly<{ detail: QualityDetail; onUpdated: (next: QualityDetail) => void }>) {
  const { c, locale } = useAdminCopy();
  const router = useRouter();
  const { message, rating, reviews } = detail;
  const base = `/api/v1/admin/quality/answers/${message.id}`;
  const [verdict, setVerdict] = useState<Verdict | null>(null);
  const [reasons, setReasons] = useState<ReviewReason[]>([]);
  const [note, setNote] = useState('');
  const [reason, setReason] = useState('');
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [formError, setFormError] = useState<string | null>(null);
  const [revealOpen, setRevealOpen] = useState(false);

  const toggleReason = (r: ReviewReason) => setReasons((prev) => (prev.includes(r) ? prev.filter((x) => x !== r) : [...prev, r]));
  const canSave = verdict !== null && reason.trim().length >= 3 && !busy;

  const submit = async (e: FormEvent) => {
    e.preventDefault();
    if (verdict === null || !canSave) return;
    setBusy(true);
    setFormError(null);
    setNotice(null);
    try {
      const result = await adminSend<QualityDetail>(`${base}/review`, 'POST',
        { verdict, reasons, note: note.trim() || undefined, reason: reason.trim() });
      onUpdated(result);
      setVerdict(null); setReasons([]); setNote(''); setReason('');
      setNotice(c.quality.reviewSaved);
    } catch (err) {
      setFormError(errorText(c, err));
    } finally {
      setBusy(false);
    }
  };

  const reveal = async (revealReason: string) => {
    let userId: string;
    try {
      ({ user_id: userId } = await adminSend<{ user_id: string }>(`${base}/reveal-user`, 'POST', { reason: revealReason }));
    } catch (err) {
      throw new Error(errorText(c, err));
    }
    router.push(`/admin/users/${userId}`);
  };

  const ev = message.evidence;
  const ratingMark = rating?.value === 1 ? c.quality.ratings.up : c.quality.ratings.down;

  return <div className={styles.page}>
    <section className={`liquid-glass ${styles.panel}`}>
      <h2 className={styles.panelTitle}>{c.quality.evidence}</h2>
      {ev ? <dl className={styles.facts}>
        <dt>{c.quality.ev.status}</dt><dd>{ev.status ?? c.common.dash}</dd>
        <dt>{c.quality.ev.coverage}</dt><dd>{ev.coverage ?? c.common.dash}</dd>
        <dt>{c.quality.ev.questionClass}</dt><dd>{ev.question_class ?? c.common.dash}</dd>
        <dt>{c.quality.ev.sourceCount}</dt><dd>{ev.source_count === undefined ? c.common.dash : formatNumber(ev.source_count, locale)}</dd>
        <dt>{c.quality.ev.precise}</dt><dd>{ev.has_precise_citation === undefined ? c.common.dash : (ev.has_precise_citation ? c.common.yes : c.common.no)}</dd>
        <dt>{c.quality.ev.time}</dt><dd>{message.processing_ms === null ? c.common.dash : c.quality.seconds((message.processing_ms / 1000).toFixed(1))}</dd>
        <dt>{c.quality.ev.retrieved}</dt><dd>{ev.retrieved_count === undefined ? c.common.dash : formatNumber(ev.retrieved_count, locale)}</dd>
      </dl> : <p className={styles.muted}>{c.quality.noEvidence}</p>}
      {message.flags.length > 0 && <div className={styles.pills}>
        {message.flags.map((f) => <Badge key={f} tone="warning">{c.quality.flags[f]}</Badge>)}
      </div>}
    </section>

    <section className={`liquid-glass ${styles.panel}`}>
      <h2 className={styles.panelTitle}>{c.quality.userRating}</h2>
      {rating ? <>
        <p>{ratingMark}</p>
        {rating.comment && <p className={styles.prewrap}>{rating.comment}</p>}
      </> : <p className={styles.muted}>{c.quality.noRating}</p>}
    </section>

    <section className={`liquid-glass ${styles.panel}`}>
      <h2 className={styles.panelTitle}>{c.quality.review}</h2>
      <form className={styles.actionGroup} onSubmit={submit}>
        <div className={styles.pills}>
          {VERDICTS.map((v) => <button key={v} type="button" className={`${styles.button} ${styles.chip}`}
            aria-pressed={verdict === v} onClick={() => setVerdict(v)}>{c.quality.verdicts[v]}</button>)}
        </div>
        <fieldset className={styles.actionGroup}>
          <legend className={styles.muted}>{c.quality.reviewReasons}</legend>
          {REVIEW_REASONS.map((r) => <label key={r} className={styles.checkbox}>
            <input type="checkbox" checked={reasons.includes(r)} onChange={() => toggleReason(r)} />
            {c.quality.reasons[r]}
          </label>)}
        </fieldset>
        <label className={styles.field}>{c.quality.note}
          <textarea className={styles.textarea} maxLength={2000} value={note} onChange={(e) => setNote(e.target.value)} />
        </label>
        <label className={styles.field}>{c.common.reasonRequired}
          <textarea className={styles.textarea} maxLength={1000} value={reason} onChange={(e) => setReason(e.target.value)} />
          <span className={styles.muted}>{c.common.reasonHint}</span>
        </label>
        <button type="submit" className={`${styles.button} ${styles.buttonPrimary}`} disabled={!canSave}>{c.quality.saveReview}</button>
        {notice && <p className={styles.notice} role="status">{notice}</p>}
        {formError && <p className={styles.noticeError} role="alert">{formError}</p>}
      </form>
    </section>

    <section className={`liquid-glass ${styles.panel}`}>
      <h2 className={styles.panelTitle}>{c.quality.history}</h2>
      {reviews.length === 0 ? <p className={styles.muted}>{c.quality.noReviews}</p> : <ul className={styles.actionGroup}>
        {reviews.map((r, i) => <li key={`${r.created_at ?? ''}-${i}`} className={styles.actionGroup}>
          <span className={styles.muted}>{formatDateTime(r.created_at, locale)} · {r.reviewer.username ?? c.common.dash}</span>
          <span className={styles.pills}>
            <Badge tone={VERDICT_TONES[r.verdict]}>{c.quality.verdicts[r.verdict]}</Badge>
            {r.reasons.map((x) => <Badge key={x} tone="neutral">{c.quality.reasons[x]}</Badge>)}
          </span>
          {r.note && <span className={styles.prewrap}>{r.note}</span>}
        </li>)}
      </ul>}
    </section>

    <div>
      <button type="button" className={styles.button} onClick={() => setRevealOpen(true)}>{c.quality.revealUser}</button>
    </div>
    <ConfirmDialog open={revealOpen} onOpenChange={setRevealOpen} title={c.quality.revealTitle}
      description={c.quality.revealDescription} reasonRequired onConfirm={reveal} />
  </div>;
}
