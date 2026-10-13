'use client';

import { useEffect, useState } from 'react';
import { formatDateTime, formatNumber, useAdminCopy, type AdminCopy, type AdminLocale } from '@/lib/admin-i18n';
import { CARD_ACTIONS, type JobRequest, type ManualJob, type SystemJob, type SystemJobName, type SystemJobState, type SystemStatus } from '@/lib/admin-types';
import { adminSend, AdminApiError, errorText } from '@/lib/admin-api';
import { ConfirmDialog } from '@/components/admin/ConfirmDialog';
import { useAdminFetch } from '@/lib/use-admin-fetch';
import { PageHeader } from '@/components/admin/PageHeader';
import { AdminState } from '@/components/admin/AdminState';
import { Badge, type BadgeTone } from '@/components/admin/Badge';
import styles from '../admin.module.css';

const TONE: Record<SystemJobState, BadgeTone> = { ok: 'success', stale: 'warning', failed: 'error', skipped: 'neutral', unknown: 'neutral' };
const ICON: Record<SystemJobState, string> = { ok: '●', stale: '◐', failed: '✕', skipped: '○', unknown: '○' };
const HOUR = 3_600_000;

function age(finishedAt: string, c: AdminCopy, locale: AdminLocale): string {
  const iso = /(?:[zZ]|[+-]\d\d:?\d\d)$/.test(finishedAt) ? finishedAt : `${finishedAt}Z`;
  const hours = Math.floor((Date.now() - Date.parse(iso)) / HOUR);
  if (hours < 1) return c.system.justNow;
  if (hours < 48) return c.system.hoursAgo(formatNumber(hours, locale));
  return c.system.daysAgo(formatNumber(Math.floor(hours / 24), locale));
}

const POLL_MS = 15_000;
const isActive = (r: JobRequest | null) => r !== null && (r.state === 'queued' || r.state === 'running');
const cardOf = (job: ManualJob): SystemJobName => (job === 'canary' || job === 'backup' ? job : 'scraper');

function RequestLine({ request, c, locale }: Readonly<{ request: JobRequest; c: AdminCopy; locale: AdminLocale }>) {
  const at = (value: string | null) => (value ? formatDateTime(value, locale) : '');
  const r = c.system.request;
  let text: string;
  switch (request.state) {
    case 'queued': text = r.queued; break;
    case 'running': text = r.running(at(request.started_at)); break;
    case 'done': text = r.done(at(request.finished_at)); break;
    case 'skipped': text = r.skipped; break;
    default: text = request.reason === 'interrupted' ? r.interrupted : r.failed;
  }
  return <p className={styles.jobMeta} role="status">{c.system.run[request.job]}: {text}</p>;
}

function JobCard({ job, c, locale, onRun, error }: Readonly<{
  job: SystemJob; c: AdminCopy; locale: AdminLocale; onRun: (job: ManualJob) => void; error: string | undefined;
}>) {
  const title = c.system.jobs[job.job];
  return <article className={`liquid-glass ${styles.jobCard}`} aria-labelledby={`job-${job.job}`}>
    <div className={styles.jobHead}>
      <h2 id={`job-${job.job}`} className={styles.jobTitle}>{title}</h2>
      <Badge tone={TONE[job.state]}><span aria-hidden="true">{ICON[job.state]}</span>{c.system.states[job.state]}</Badge>
    </div>
    {job.finished_at === null ? <p className={styles.jobMeta}>{c.system.noData}</p> : <>
      <p className={styles.jobMeta}>
        {c.system.lastRun(formatDateTime(job.finished_at, locale))} · {age(job.finished_at, c, locale)}
        {job.trigger === 'manual' && <> · {c.system.manual}</>}
        {!job.skipped && job.exit_code !== null && job.exit_code !== 0 && <> · {c.system.exitCode(String(job.exit_code))}</>}
      </p>
      {job.summary && <p className={`${styles.jobSummary} ${styles.mono}`}>{job.summary}</p>}
    </>}
    {job.request && <RequestLine request={job.request} c={c} locale={locale} />}
    {CARD_ACTIONS[job.job].length > 0 && <div className={styles.jobActions}>
      {CARD_ACTIONS[job.job].map((action) => <button key={action} type="button" className={styles.button}
        disabled={isActive(job.request)} onClick={() => onRun(action)}>{c.system.run[action]}</button>)}
    </div>}
    {error && <p className={styles.noticeError} role="alert">{error}</p>}
    <p className={styles.jobMeta}>{c.system.expected[job.job]}</p>
    {job.log_tail.length > 0 && <details className={styles.jobLog}>
      <summary>{c.system.showLog}</summary>
      <pre className={styles.log}>{job.log_tail.join('\n')}</pre>
    </details>}
  </article>;
}

export default function AdminSystem() {
  const { c, locale } = useAdminCopy();
  const { data, error, reload } = useAdminFetch<SystemStatus>('/api/v1/admin/system');

  const [dialog, setDialog] = useState<ManualJob | null>(null);
  const [errors, setErrors] = useState<Partial<Record<SystemJobName, string>>>({});
  const polling = data?.jobs.some((j) => isActive(j.request)) ?? false;

  useEffect(() => {
    if (!polling) return;
    const id = window.setInterval(reload, POLL_MS);
    return () => window.clearInterval(id);
  }, [polling, reload]);

  const run = async () => {
    if (dialog === null) return;
    const card = cardOf(dialog);
    try {
      await adminSend(`/api/v1/admin/system/jobs/${dialog}`, 'POST', {});
      setErrors((prev) => ({ ...prev, [card]: undefined }));
    } catch (e) {
      // 409 is about the job, not the dialog: close it and say why on the card.
      if (!(e instanceof AdminApiError && e.status === 409)) throw new Error(errorText(c, e));
      setErrors((prev) => ({ ...prev, [card]: errorText(c, e) }));
    }
    reload();
  };

  let body = <AdminState kind="loading" />;
  if (error) body = <AdminState kind="error" onRetry={reload} />;
  else if (data) body = <div className={styles.jobGrid}>
    {data.jobs.map((job) => <JobCard key={job.job} job={job} c={c} locale={locale} onRun={setDialog} error={errors[job.job]} />)}
  </div>;

  return <div className={styles.page}>
    <PageHeader title={c.system.title} subtitle={c.system.subtitle}
      actions={<button type="button" className={styles.button} onClick={reload}>{c.common.refresh}</button>} />
    {body}
    <ConfirmDialog open={dialog !== null} onOpenChange={(open) => { if (!open) setDialog(null); }}
      title={dialog ? c.system.run[dialog] : ''} description={dialog ? c.system.cost[dialog] : undefined}
      confirmLabel={c.system.confirmRun} withReason={false} onConfirm={run} />
  </div>;
}
