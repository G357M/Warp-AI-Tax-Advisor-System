'use client';

import { Suspense, useEffect, useState } from 'react';
import { useSearchParams } from 'next/navigation';
import { authFetch } from '@/lib/auth';
import { formatDate, formatNumber, useAdminCopy } from '@/lib/admin-i18n';
import { PageHeader } from '@/components/admin/PageHeader';
import { DataTable, type Column } from '@/components/admin/DataTable';
import { Pagination } from '@/components/admin/Pagination';
import styles from '../admin.module.css';

interface AdminDoc {
  id: string; title: string; document_type: string; document_number: string | null;
  date_published: string | null; authority: string | null; source_url: string; created_at: string | null;
}

const TYPES = ['law', 'regulation', 'court_decision', 'guideline', 'news', 'bill'];
const LIMIT = 50;

function DocumentsPage() {
  const params = useSearchParams();
  const initialType = params.get('doc_type') ?? '';
  const { c, locale } = useAdminCopy();
  const [items, setItems] = useState<AdminDoc[]>([]);
  const [total, setTotal] = useState(0);
  const [search, setSearch] = useState('');
  const [docType, setDocType] = useState(TYPES.includes(initialType) ? initialType : '');
  const [offset, setOffset] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    const controller = new AbortController();
    const params = new URLSearchParams({ limit: String(LIMIT), offset: String(offset) });
    if (search.trim()) params.set('search', search.trim());
    if (docType) params.set('doc_type', docType);
    authFetch(`/api/v1/admin/documents?${params}`, { signal: controller.signal })
      .then((r) => (r.ok ? r.json() : Promise.reject()))
      .then((d) => { setItems(d.items); setTotal(d.total); setError(false); })
      .catch(() => { if (!controller.signal.aborted) setError(true); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [search, docType, offset, attempt]);

  const columns: Column<AdminDoc>[] = [
    { key: 'title', header: c.documents.name, render: (d) =>
      <a href={d.source_url} target="_blank" rel="noopener noreferrer" title={d.title} className={styles.truncate}>{d.title}</a> },
    { key: 'type', header: c.documents.type, render: (d) => d.document_type },
    { key: 'number', header: c.documents.number, render: (d) => d.document_number ?? c.common.dash },
    { key: 'date', header: c.documents.date, render: (d) => formatDate(d.date_published, locale) },
    { key: 'authority', header: c.documents.authority, render: (d) => d.authority ?? c.common.dash },
  ];

  const retry = () => { setError(false); setLoading(true); setAttempt((a) => a + 1); };
  const onSearch = (v: string) => { setOffset(0); setError(false); setLoading(true); setSearch(v); };
  const onType = (v: string) => { setOffset(0); setError(false); setLoading(true); setDocType(v); };
  const onPage = (o: number) => { setError(false); setLoading(true); setOffset(o); };

  return <div className={styles.page}>
    <PageHeader title={`${c.documents.title} (${formatNumber(total, locale)})`} />
    <div className={styles.toolbar}>
      <input className={styles.input} type="search" aria-label={c.documents.search} placeholder={c.documents.search}
        value={search} onChange={(e) => onSearch(e.target.value)} />
      <select className={styles.select} aria-label={c.documents.type} value={docType}
        onChange={(e) => onType(e.target.value)}>
        <option value="">{c.documents.allTypes}</option>
        {TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
      </select>
    </div>
    <DataTable columns={columns} rows={items} rowKey={(d) => d.id} loading={loading} error={error}
      onRetry={retry} emptyText={c.documents.notFound} />
    <Pagination offset={offset} limit={LIMIT} total={total} onChange={onPage} />
  </div>;
}

export default function AdminDocuments() {
  return <Suspense><DocumentsPage /></Suspense>;
}
