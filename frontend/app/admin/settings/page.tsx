'use client';

import { useCallback, useEffect, useState } from 'react';
import { authFetch } from '@/lib/auth';
import { useAdminCopy } from '@/lib/admin-i18n';
import type { AdminConfig } from '@/lib/admin-types';
import { PageHeader } from '@/components/admin/PageHeader';
import { AdminState } from '@/components/admin/AdminState';
import { Badge } from '@/components/admin/Badge';
import styles from '../admin.module.css';

const GROUPS = ['app', 'llm', 'email', 'billing', 'limits', 'secrets'];

export default function AdminConfigPage() {
  const { c } = useAdminCopy();
  const [config, setConfig] = useState<AdminConfig | null>(null);
  const [error, setError] = useState(false);

  const load = useCallback(() => {
    authFetch('/api/v1/admin/config').then((r) => (r.ok ? r.json() : Promise.reject()))
      .then((d) => { setConfig(d); setError(false); }).catch(() => setError(true));
  }, []);
  useEffect(load, [load]);
  const retry = () => { setError(false); load(); };

  const render = (group: string, value: string | number | boolean | null) => {
    if (group === 'secrets') return <Badge tone={value ? 'success' : 'warning'}>{value ? c.common.set : c.common.notSet}</Badge>;
    if (typeof value === 'boolean') return <Badge tone={value ? 'success' : 'neutral'}>{value ? c.common.yes : c.common.no}</Badge>;
    return <span className={styles.mono}>{value === null || value === '' ? c.common.dash : String(value)}</span>;
  };

  return <div className={styles.page}>
    <PageHeader title={c.config.title} subtitle={c.config.subtitle} />
    <p className={styles.notice}>{c.config.howToChange}</p>
    {error ? <AdminState kind="error" onRetry={retry} />
      : !config ? <AdminState kind="loading" />
      : GROUPS.filter((g) => config[g]).map((group) => <section key={group} aria-labelledby={`cfg-${group}`}>
        <h2 id={`cfg-${group}`} className={styles.panelTitle}>{c.config.groups[group]}</h2>
        <div className={`liquid-glass ${styles.tableWrap}`}>
          <table className={styles.table}>
            <thead><tr><th scope="col">{c.config.name}</th><th scope="col">{c.config.value}</th></tr></thead>
            <tbody>{Object.entries(config[group]).map(([name, value]) => <tr key={name}>
              <td data-label={c.config.name} className={styles.mono}>{name}</td>
              <td data-label={c.config.value}>{render(group, value)}</td>
            </tr>)}</tbody>
          </table>
        </div>
      </section>)}
  </div>;
}
