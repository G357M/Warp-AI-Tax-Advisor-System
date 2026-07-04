'use client';

import { useEffect, useState } from 'react';
import { authFetch } from '@/lib/auth';

interface OpsStatus {
  last_ingest: string | null;
  documents_today: number;
  pending: { decision_facts: number; law_amendments: number };
  logs: Record<string, string[]>;
}

const card: React.CSSProperties = {
  background: 'rgba(255,255,255,0.05)',
  border: '1px solid rgba(255,255,255,0.1)',
  borderRadius: '12px',
  padding: '1.25rem',
};

const LOG_TITLES: Record<string, string> = {
  scraper: 'Ночной скрейпер (/app/logs/scraper.log)',
  law_amendments_backfill: 'Бэкфилл поправок',
  decision_facts_backfill: 'Бэкфилл решений',
};

export default function AdminScraper() {
  const [ops, setOps] = useState<OpsStatus | null>(null);
  const [error, setError] = useState(false);

  const load = () => {
    authFetch('/api/v1/admin/ops')
      .then((r) => (r.ok ? r.json() : Promise.reject()))
      .then(setOps)
      .catch(() => setError(true));
  };

  useEffect(load, []);

  if (error) return <div style={{ padding: '2rem', color: '#f87171' }}>Не получилось загрузить статус.</div>;
  if (!ops) return <div style={{ padding: '2rem', opacity: 0.7 }}>Загружаю…</div>;

  return (
    <div style={{ padding: '2rem', display: 'flex', flexDirection: 'column', gap: '1.25rem', maxWidth: '1100px' }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
        <h1 style={{ margin: 0, fontSize: '1.6rem' }}>Ингест и фоновые задачи</h1>
        <button
          onClick={load}
          style={{
            background: 'rgba(255,255,255,0.08)',
            border: '1px solid rgba(255,255,255,0.15)',
            borderRadius: '8px',
            color: 'white',
            padding: '0.4rem 0.9rem',
            fontSize: '0.8rem',
            cursor: 'pointer',
          }}
        >
          Обновить
        </button>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '1rem' }}>
        <div style={card}>
          <div style={{ fontSize: '0.75rem', opacity: 0.7 }}>Последний ингест</div>
          <div style={{ fontSize: '1.2rem', fontWeight: 600, marginTop: '0.3rem' }}>
            {ops.last_ingest ? new Date(ops.last_ingest).toLocaleString('ru-RU') : '—'}
          </div>
          <div style={{ fontSize: '0.75rem', opacity: 0.6, marginTop: '0.3rem' }}>
            сегодня добавлено: {ops.documents_today}
          </div>
        </div>
        <div style={card}>
          <div style={{ fontSize: '0.75rem', opacity: 0.7 }}>Решения в очереди на разметку</div>
          <div style={{ fontSize: '1.8rem', fontWeight: 700, marginTop: '0.2rem' }}>
            {ops.pending.decision_facts.toLocaleString('ru-RU')}
          </div>
        </div>
        <div style={card}>
          <div style={{ fontSize: '0.75rem', opacity: 0.7 }}>Поправки в очереди</div>
          <div style={{ fontSize: '1.8rem', fontWeight: 700, marginTop: '0.2rem' }}>
            {ops.pending.law_amendments.toLocaleString('ru-RU')}
          </div>
        </div>
      </div>

      {Object.entries(ops.logs).map(([key, lines]) => (
        <div key={key} style={card}>
          <div style={{ fontSize: '0.85rem', opacity: 0.7, marginBottom: '0.6rem' }}>
            {LOG_TITLES[key] ?? key}
          </div>
          {lines.length === 0 ? (
            <div style={{ fontSize: '0.8rem', opacity: 0.5 }}>лог пуст или недоступен</div>
          ) : (
            <pre
              style={{
                margin: 0,
                fontSize: '0.72rem',
                lineHeight: 1.5,
                whiteSpace: 'pre-wrap',
                wordBreak: 'break-word',
                opacity: 0.85,
                maxHeight: '220px',
                overflowY: 'auto',
              }}
            >
              {lines.join('\n')}
            </pre>
          )}
        </div>
      ))}
    </div>
  );
}
