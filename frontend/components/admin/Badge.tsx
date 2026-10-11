import type { ReactNode } from 'react';
import styles from '@/app/admin/admin.module.css';

export type BadgeTone = 'success' | 'warning' | 'error' | 'neutral';

export function Badge({ tone, children }: { tone: BadgeTone; children: ReactNode }) {
  return <span className={`${styles.badge} ${styles[`badge-${tone}`]}`}>{children}</span>;
}
