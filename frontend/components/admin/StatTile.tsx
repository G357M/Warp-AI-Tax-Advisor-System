import Link from 'next/link';
import styles from '@/app/admin/admin.module.css';

export function StatTile({ label, value, detail, href }: { label: string; value: string; detail?: string; href?: string }) {
  const body = <>
    <span className={styles.tileLabel}>{label}</span>
    <span className={styles.tileValue}>{value}</span>
    {detail && <span className={styles.tileDetail}>{detail}</span>}
  </>;
  const className = `liquid-glass ${styles.tile}`;
  return href ? <Link href={href} className={className}>{body}</Link> : <div className={className}>{body}</div>;
}
