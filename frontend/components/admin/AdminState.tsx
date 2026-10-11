'use client';

import styles from '@/app/admin/admin.module.css';
import { useAdminCopy } from '@/lib/admin-i18n';

export function AdminState({ kind, message, onRetry }: { kind: 'loading' | 'error' | 'empty'; message?: string; onRetry?: () => void }) {
  const { c } = useAdminCopy();
  const text = message ?? (kind === 'loading' ? c.common.loading : kind === 'error' ? c.common.loadError : c.common.empty);
  return <div className={`${styles.state} ${kind === 'error' ? styles.stateError : ''}`}
    role={kind === 'error' ? 'alert' : 'status'}>
    <p>{text}</p>
    {kind === 'error' && onRetry && <button type="button" className={styles.button} onClick={onRetry}>{c.common.retry}</button>}
  </div>;
}
