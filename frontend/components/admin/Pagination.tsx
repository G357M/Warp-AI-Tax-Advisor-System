'use client';

import styles from '@/app/admin/admin.module.css';
import { formatNumber, useAdminCopy } from '@/lib/admin-i18n';

export function Pagination({ offset, limit, total, onChange }: { offset: number; limit: number; total: number; onChange: (offset: number) => void }) {
  const { c, locale } = useAdminCopy();
  if (total <= limit && offset === 0) return null;
  const to = Math.min(offset + limit, total);
  return <div className={styles.pagination}>
    <span>{c.common.range(total ? offset + 1 : 0, to, formatNumber(total, locale))}</span>
    <div className={styles.toolbar}>
      <button type="button" className={styles.button} disabled={offset === 0}
        onClick={() => onChange(Math.max(offset - limit, 0))}>{c.common.prev}</button>
      <button type="button" className={styles.button} disabled={to >= total}
        onClick={() => onChange(offset + limit)}>{c.common.next}</button>
    </div>
  </div>;
}
