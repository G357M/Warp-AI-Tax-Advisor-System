'use client';

import { useEffect, useState } from 'react';
import { authFetch } from '@/lib/auth';

interface AdminStats {
  documents: { total: number; by_type: Record<string, number>; last_ingest: string | null };
  decisions: { total: number; extracted: number; pending: number };
  amendments: { acts_total: number; extracted: number; resolved: number; pending: number };
  users: { total: number; admins: number };
  subscriptions: Record<string, number>;
  conversations: { total: number; messages: number; messages_7d: number };
}

const card: React.CSSProperties = {
  background: 'rgba(255,255,255,0.05)',
  border: '1px solid rgba(255,255,255,0.1)',
  borderRadius: '12px',
  padding: '1.25rem',
};

function Tile({ label, value, detail }: { label: string; value: string; detail?: string }) {
  return (
    <div style={card}>
      <div style={{ fontSize: '0.75rem', opacity: 0.7 }}>{label}</div>
      <div style={{ fontSize: '1.8rem', fontWeight: 700, marginTop: '0.2rem' }}>{value}</div>
      {detail && <div style={{ fontSize: '0.75rem', opacity: 0.6, marginTop: '0.3rem' }}>{detail}</div>}
    </div>
  );
}

export default function AdminDashboard() {
  const [stats, setStats] = useState<AdminStats | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    authFetch('/api/v1/admin/stats')
      .then((r) => (r.ok ? r.json() : Promise.reject()))
      .then(setStats)
      .catch(() => setError(true));
  }, []);

  if (error) return <div style={{ padding: '2rem', color: '#f87171' }}>Не получилось загрузить статистику.</div>;
  if (!stats) return <div style={{ padding: '2rem', opacity: 0.7 }}>Загружаю…</div>;

  const subsTotal = Object.values(stats.subscriptions).reduce((a, b) => a + b, 0);

  return (
    <div style={{ padding: '2rem', display: 'flex', flexDirection: 'column', gap: '1.5rem', maxWidth: '1100px' }}>
      <h1 style={{ margin: 0, fontSize: '1.6rem' }}>Dashboard</h1>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(210px, 1fr))', gap: '1rem' }}>
        <Tile
          label="Документов в базе"
          value={stats.documents.total.toLocaleString('ru-RU')}
          detail={
            stats.documents.last_ingest
              ? `последний ингест ${new Date(stats.documents.last_ingest).toLocaleString('ru-RU')}`
              : undefined
          }
        />
        <Tile
          label="Решения: извлечено фактов"
          value={`${stats.decisions.extracted.toLocaleString('ru-RU')} / ${stats.decisions.total.toLocaleString('ru-RU')}`}
          detail={`в очереди ${stats.decisions.pending.toLocaleString('ru-RU')}`}
        />
        <Tile
          label="Поправки: извлечено"
          value={`${stats.amendments.extracted} / ${stats.amendments.acts_total}`}
          detail={`закон найден: ${stats.amendments.resolved} · в очереди ${stats.amendments.pending}`}
        />
        <Tile
          label="Пользователи"
          value={String(stats.users.total)}
          detail={`админов: ${stats.users.admins}`}
        />
        <Tile
          label="Активные подписки"
          value={String(subsTotal)}
          detail={Object.entries(stats.subscriptions).map(([p, n]) => `${p}: ${n}`).join(' · ') || 'пока нет'}
        />
        <Tile
          label="Сообщений за 7 дней"
          value={String(stats.conversations.messages_7d)}
          detail={`всего диалогов: ${stats.conversations.total}`}
        />
      </div>

      <div style={card}>
        <div style={{ fontSize: '0.85rem', opacity: 0.7, marginBottom: '0.6rem' }}>Корпус по типам</div>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.5rem' }}>
          {Object.entries(stats.documents.by_type).map(([t, n]) => (
            <span
              key={t}
              style={{
                border: '1px solid rgba(255,255,255,0.15)',
                borderRadius: '999px',
                padding: '0.25rem 0.75rem',
                fontSize: '0.8rem',
              }}
            >
              {t}: {n.toLocaleString('ru-RU')}
            </span>
          ))}
        </div>
      </div>
    </div>
  );
}
