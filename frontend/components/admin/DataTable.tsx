'use client';

import type { ReactNode } from 'react';
import styles from '@/app/admin/admin.module.css';
import { AdminState } from './AdminState';

export type Column<T> = { key: string; header: string; render: (row: T) => ReactNode; className?: string };

export function DataTable<T>({ columns, rows, rowKey, loading, error, onRetry, emptyText }: {
  columns: Column<T>[]; rows: T[]; rowKey: (row: T) => string;
  loading?: boolean; error?: boolean; onRetry?: () => void; emptyText?: string;
}) {
  if (error) return <div className={`liquid-glass ${styles.panel}`}><AdminState kind="error" onRetry={onRetry} /></div>;
  if (loading && rows.length === 0) return <div className={`liquid-glass ${styles.panel}`}><AdminState kind="loading" /></div>;
  if (rows.length === 0) return <div className={`liquid-glass ${styles.panel}`}><AdminState kind="empty" message={emptyText} /></div>;
  return <div className={`liquid-glass ${styles.tableWrap}`}>
    <table className={styles.table} aria-busy={loading || undefined}>
      <thead><tr>{columns.map((col) => <th key={col.key} scope="col">{col.header}</th>)}</tr></thead>
      <tbody>
        {rows.map((row) => <tr key={rowKey(row)}>
          {columns.map((col) => <td key={col.key} data-label={col.header} className={col.className}>{col.render(row)}</td>)}
        </tr>)}
      </tbody>
    </table>
  </div>;
}
