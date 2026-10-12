'use client';

import { formatDateTime, formatNumber, useAdminCopy, type AdminCopy, type AdminLocale } from '@/lib/admin-i18n';
import type { SystemJob, SystemJobState, SystemStatus } from '@/lib/admin-types';
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

function JobCard({ job, c, locale }: Readonly<{ job: SystemJob; c: AdminCopy; locale: AdminLocale }>) {
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
        {job.exit_code !== null && job.exit_code !== 0 && <> · {c.system.exitCode(String(job.exit_code))}</>}
      </p>
      {job.summary && <p className={`${styles.jobSummary} ${styles.mono}`}>{job.summary}</p>}
    </>}
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

  let body = <AdminState kind="loading" />;
  if (error) body = <AdminState kind="error" onRetry={reload} />;
  else if (data) body = <div className={styles.jobGrid}>
    {data.jobs.map((job) => <JobCard key={job.job} job={job} c={c} locale={locale} />)}
  </div>;

  return <div className={styles.page}>
    <PageHeader title={c.system.title} subtitle={c.system.subtitle}
      actions={<button type="button" className={styles.button} onClick={reload}>{c.common.refresh}</button>} />
    {body}
  </div>;
}
