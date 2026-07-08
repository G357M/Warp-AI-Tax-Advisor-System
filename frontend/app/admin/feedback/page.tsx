'use client';

import { useCallback, useEffect, useState } from 'react';
import { authFetch } from '@/lib/auth';

interface FeedbackItem {
  id: string;
  message: string;
  page: string | null;
  status: 'new' | 'in_progress' | 'fixed';
  created_at: string | null;
  email: string;
  username: string;
}

interface FeedbackResponse {
  total: number;
  counts: { new: number; in_progress: number; fixed: number };
  items: FeedbackItem[];
}

const STATUS_LABELS: Record<string, string> = {
  new: 'Новый',
  in_progress: 'В работе',
  fixed: 'Исправлено',
};

const STATUS_COLORS: Record<string, string> = {
  new: '#f59e0b',
  in_progress: '#3b82f6',
  fixed: '#059669',
};

const card: React.CSSProperties = {
  background: 'rgba(255,255,255,0.05)',
  border: '1px solid rgba(255,255,255,0.1)',
  borderRadius: '12px',
  padding: '1.25rem',
};

const input: React.CSSProperties = {
  background: 'rgba(255,255,255,0.08)',
  border: '1px solid rgba(255,255,255,0.15)',
  borderRadius: '8px',
  color: 'white',
  padding: '0.45rem 0.7rem',
  fontSize: '0.85rem',
};

// Native dropdown lists need an explicit dark background for readable options.
const option: React.CSSProperties = { background: '#1e293b', color: 'white' };

export default function AdminFeedback() {
  const [data, setData] = useState<FeedbackResponse | null>(null);
  const [filter, setFilter] = useState<string>('');
  const [message, setMessage] = useState<string | null>(null);

  const load = useCallback(() => {
    const qs = filter ? `&status=${filter}` : '';
    authFetch(`/api/v1/admin/feedback?limit=100${qs}`)
      .then((r) => (r.ok ? r.json() : Promise.reject()))
      .then(setData)
      .catch(() => setMessage('Не получилось загрузить багрепорты.'));
  }, [filter]);

  useEffect(load, [load]);

  const setStatus = async (item: FeedbackItem, status: string) => {
    setMessage(null);
    const res = await authFetch(`/api/v1/admin/feedback/${item.id}`, {
      method: 'PATCH',
      body: JSON.stringify({ status }),
    });
    if (res.ok) load();
    else setMessage('Не получилось изменить статус.');
  };

  return (
    <div style={{ padding: '2rem', display: 'flex', flexDirection: 'column', gap: '1.25rem', maxWidth: '1100px' }}>
      <h1 style={{ margin: 0, fontSize: '1.6rem' }}>Багрепорты{data ? ` (${data.total})` : ''}</h1>

      <div style={{ display: 'flex', gap: '0.6rem', flexWrap: 'wrap' }}>
        {['', 'new', 'in_progress', 'fixed'].map((s) => (
          <button
            key={s || 'all'}
            onClick={() => setFilter(s)}
            style={{
              ...input,
              cursor: 'pointer',
              border: filter === s ? '1px solid white' : input.border,
              opacity: filter === s ? 1 : 0.75,
            }}
          >
            {s === '' ? 'Все' : STATUS_LABELS[s]}
            {data && s !== '' && ` · ${data.counts[s as keyof typeof data.counts]}`}
          </button>
        ))}
      </div>

      {message && <div style={{ fontSize: '0.85rem', opacity: 0.85 }}>{message}</div>}

      <div style={{ ...card, padding: 0, overflowX: 'auto' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.85rem' }}>
          <thead>
            <tr style={{ textAlign: 'left', opacity: 0.7 }}>
              {['Дата', 'Пользователь', 'Страница', 'Сообщение', 'Статус'].map((h) => (
                <th key={h} style={{ padding: '0.7rem 1rem', borderBottom: '1px solid rgba(255,255,255,0.1)' }}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {(data?.items ?? []).map((f) => (
              <tr key={f.id} style={{ borderBottom: '1px solid rgba(255,255,255,0.06)' }}>
                <td style={{ padding: '0.6rem 1rem', whiteSpace: 'nowrap', opacity: 0.7 }}>
                  {f.created_at ? new Date(f.created_at + 'Z').toLocaleString('ru-RU') : '—'}
                </td>
                <td style={{ padding: '0.6rem 1rem' }}>{f.email}</td>
                <td style={{ padding: '0.6rem 1rem', opacity: 0.7 }}>{f.page ?? '—'}</td>
                <td style={{ padding: '0.6rem 1rem', maxWidth: '420px', whiteSpace: 'pre-wrap' }}>{f.message}</td>
                <td style={{ padding: '0.6rem 1rem', whiteSpace: 'nowrap' }}>
                  <span
                    style={{
                      display: 'inline-block',
                      width: '8px',
                      height: '8px',
                      borderRadius: '50%',
                      background: STATUS_COLORS[f.status],
                      marginRight: '0.5rem',
                    }}
                  />
                  <select style={input} value={f.status} onChange={(e) => setStatus(f, e.target.value)}>
                    {Object.entries(STATUS_LABELS).map(([value, label]) => (
                      <option key={value} value={value} style={option}>{label}</option>
                    ))}
                  </select>
                </td>
              </tr>
            ))}
            {data && data.items.length === 0 && (
              <tr>
                <td colSpan={5} style={{ padding: '1rem', opacity: 0.7 }}>Пусто.</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
