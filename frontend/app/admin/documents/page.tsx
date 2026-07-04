'use client';

import { useCallback, useEffect, useState } from 'react';
import { authFetch } from '@/lib/auth';

interface AdminDoc {
  id: string;
  title: string;
  document_type: string;
  document_number: string | null;
  date_published: string | null;
  authority: string | null;
  source_url: string;
  created_at: string | null;
}

const TYPES = ['', 'law', 'regulation', 'court_decision', 'guideline', 'news', 'bill'];

const card: React.CSSProperties = {
  background: 'rgba(255,255,255,0.05)',
  border: '1px solid rgba(255,255,255,0.1)',
  borderRadius: '12px',
};

const input: React.CSSProperties = {
  background: 'rgba(255,255,255,0.08)',
  border: '1px solid rgba(255,255,255,0.15)',
  borderRadius: '8px',
  color: 'white',
  padding: '0.45rem 0.7rem',
  fontSize: '0.85rem',
};

export default function AdminDocuments() {
  const [items, setItems] = useState<AdminDoc[]>([]);
  const [total, setTotal] = useState(0);
  const [search, setSearch] = useState('');
  const [docType, setDocType] = useState('');
  const [loading, setLoading] = useState(false);

  const load = useCallback(() => {
    setLoading(true);
    const params = new URLSearchParams({ limit: '50' });
    if (search.trim()) params.set('search', search.trim());
    if (docType) params.set('doc_type', docType);
    authFetch(`/api/v1/admin/documents?${params}`)
      .then((r) => (r.ok ? r.json() : Promise.reject()))
      .then((d) => {
        setItems(d.items);
        setTotal(d.total);
      })
      .catch(() => null)
      .finally(() => setLoading(false));
  }, [search, docType]);

  useEffect(load, [load]);

  return (
    <div style={{ padding: '2rem', display: 'flex', flexDirection: 'column', gap: '1.25rem', maxWidth: '1200px' }}>
      <h1 style={{ margin: 0, fontSize: '1.6rem' }}>
        Документы ({total.toLocaleString('ru-RU')})
      </h1>

      <div style={{ display: 'flex', gap: '0.6rem', flexWrap: 'wrap' }}>
        <input
          style={{ ...input, width: '320px' }}
          placeholder="Поиск по названию или номеру…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
        />
        <select style={input} value={docType} onChange={(e) => setDocType(e.target.value)}>
          {TYPES.map((t) => (
            <option key={t} value={t}>{t || 'все типы'}</option>
          ))}
        </select>
        {loading && <span style={{ alignSelf: 'center', fontSize: '0.8rem', opacity: 0.6 }}>ищу…</span>}
      </div>

      <div style={{ ...card, overflowX: 'auto' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.83rem' }}>
          <thead>
            <tr style={{ textAlign: 'left', opacity: 0.7 }}>
              {['Название', 'Тип', 'Номер', 'Дата', 'Орган'].map((h) => (
                <th key={h} style={{ padding: '0.7rem 1rem', borderBottom: '1px solid rgba(255,255,255,0.1)' }}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {items.map((d) => (
              <tr key={d.id} style={{ borderBottom: '1px solid rgba(255,255,255,0.06)' }}>
                <td style={{ padding: '0.55rem 1rem', maxWidth: '480px' }}>
                  <a
                    href={d.source_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    style={{ color: 'inherit', textDecoration: 'none' }}
                    title={d.title}
                  >
                    <span style={{ display: 'block', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {d.title}
                    </span>
                  </a>
                </td>
                <td style={{ padding: '0.55rem 1rem' }}>{d.document_type}</td>
                <td style={{ padding: '0.55rem 1rem', opacity: 0.8 }}>{d.document_number ?? '—'}</td>
                <td style={{ padding: '0.55rem 1rem', opacity: 0.8 }}>
                  {d.date_published ? new Date(d.date_published).toLocaleDateString('ru-RU') : '—'}
                </td>
                <td style={{ padding: '0.55rem 1rem', opacity: 0.8, maxWidth: '220px', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {d.authority ?? '—'}
                </td>
              </tr>
            ))}
            {!loading && items.length === 0 && (
              <tr>
                <td colSpan={5} style={{ padding: '1rem', opacity: 0.6 }}>Ничего не найдено.</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
