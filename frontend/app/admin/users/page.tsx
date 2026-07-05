'use client';

import { useCallback, useEffect, useState } from 'react';
import { authFetch } from '@/lib/auth';

interface AdminUser {
  id: string;
  username: string;
  email: string;
  role: string;
  created_at: string | null;
  last_login: string | null;
  plan: string;
  period_end: string | null;
}

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

export default function AdminUsers() {
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [total, setTotal] = useState(0);
  const [message, setMessage] = useState<string | null>(null);
  const [email, setEmail] = useState('');
  const [plan, setPlan] = useState<'pro' | 'business'>('pro');
  const [months, setMonths] = useState(1);

  const load = useCallback(() => {
    authFetch('/api/v1/admin/users?limit=100')
      .then((r) => (r.ok ? r.json() : Promise.reject()))
      .then((d) => {
        setUsers(d.items);
        setTotal(d.total);
      })
      .catch(() => setMessage('Не получилось загрузить пользователей.'));
  }, []);

  useEffect(load, [load]);

  const activate = async () => {
    setMessage(null);
    const res = await authFetch('/api/v1/billing/admin/activate', {
      method: 'POST',
      body: JSON.stringify({ email: email.trim(), plan, months }),
    });
    const data = await res.json().catch(() => ({}));
    if (res.ok) {
      setMessage(`Активировано: ${data.email} → ${data.plan} до ${new Date(data.period_end).toLocaleDateString('ru-RU')}`);
      setEmail('');
      load();
    } else {
      setMessage(typeof data.detail === 'string' ? data.detail : 'Не получилось активировать подписку.');
    }
  };

  const setRole = async (user: AdminUser, role: string) => {
    setMessage(null);
    const res = await authFetch(`/api/v1/admin/users/${user.id}/role`, {
      method: 'PATCH',
      body: JSON.stringify({ role }),
    });
    const data = await res.json().catch(() => ({}));
    if (res.ok) load();
    else setMessage(typeof data.detail === 'string' ? data.detail : 'Не получилось изменить роль.');
  };

  return (
    <div style={{ padding: '2rem', display: 'flex', flexDirection: 'column', gap: '1.25rem', maxWidth: '1100px' }}>
      <h1 style={{ margin: 0, fontSize: '1.6rem' }}>Пользователи ({total})</h1>

      <div style={card}>
        <div style={{ fontSize: '0.85rem', opacity: 0.7, marginBottom: '0.6rem' }}>
          Активировать подписку вручную (после оплаты по счёту)
        </div>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.6rem', alignItems: 'center' }}>
          <input
            style={{ ...input, width: '260px' }}
            placeholder="email клиента"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
          />
          <select style={input} value={plan} onChange={(e) => setPlan(e.target.value as 'pro' | 'business')}>
            <option value="pro" style={option}>Pro</option>
            <option value="business" style={option}>Business</option>
          </select>
          <select style={input} value={months} onChange={(e) => setMonths(Number(e.target.value))}>
            {[1, 3, 6, 12].map((m) => (
              <option key={m} value={m} style={option}>{m} мес</option>
            ))}
          </select>
          <button
            onClick={activate}
            disabled={!email.trim()}
            style={{
              ...input,
              background: '#2563eb',
              border: 'none',
              cursor: email.trim() ? 'pointer' : 'not-allowed',
              opacity: email.trim() ? 1 : 0.5,
            }}
          >
            Активировать
          </button>
        </div>
        {message && <div style={{ marginTop: '0.7rem', fontSize: '0.85rem', opacity: 0.85 }}>{message}</div>}
      </div>

      <div style={{ ...card, padding: 0, overflowX: 'auto' }}>
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.85rem' }}>
          <thead>
            <tr style={{ textAlign: 'left', opacity: 0.7 }}>
              {['Логин', 'Email', 'Роль', 'Тариф', 'Подписка до', 'Последний вход'].map((h) => (
                <th key={h} style={{ padding: '0.7rem 1rem', borderBottom: '1px solid rgba(255,255,255,0.1)' }}>{h}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {users.map((u) => (
              <tr key={u.id} style={{ borderBottom: '1px solid rgba(255,255,255,0.06)' }}>
                <td style={{ padding: '0.6rem 1rem', fontWeight: 600 }}>{u.username}</td>
                <td style={{ padding: '0.6rem 1rem' }}>{u.email}</td>
                <td style={{ padding: '0.6rem 1rem' }}>
                  <select style={input} value={u.role} onChange={(e) => setRole(u, e.target.value)}>
                    <option value="user" style={option}>user</option>
                    <option value="admin" style={option}>admin</option>
                  </select>
                </td>
                <td style={{ padding: '0.6rem 1rem' }}>{u.plan}</td>
                <td style={{ padding: '0.6rem 1rem' }}>
                  {u.period_end ? new Date(u.period_end).toLocaleDateString('ru-RU') : '—'}
                </td>
                <td style={{ padding: '0.6rem 1rem', opacity: 0.7 }}>
                  {u.last_login ? new Date(u.last_login).toLocaleString('ru-RU') : '—'}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
