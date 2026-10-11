import type { ReactNode } from 'react';
import styles from '@/app/admin/admin.module.css';

export function PageHeader({ title, subtitle, actions }: { title: ReactNode; subtitle?: ReactNode; actions?: ReactNode }) {
  return <div className={styles.pageHeader}>
    <div>
      <h1>{title}</h1>
      {subtitle && <p>{subtitle}</p>}
    </div>
    {actions && <div className={styles.toolbar}>{actions}</div>}
  </div>;
}
