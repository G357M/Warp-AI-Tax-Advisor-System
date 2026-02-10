'use client';

import { useState } from 'react';
import { motion } from 'framer-motion';
import { PersonIcon, Cross2Icon, CheckIcon } from '@radix-ui/react-icons';

export default function UsersPage() {
  const [users] = useState([
    { id: '1', email: 'admin@infohub.ge', role: 'admin', queries: 245, created: '2024-01-10', active: true },
    { id: '2', email: 'user1@example.com', role: 'user', queries: 89, created: '2024-01-15', active: true },
    { id: '3', email: 'user2@example.com', role: 'user', queries: 156, created: '2024-01-20', active: true },
    { id: '4', email: 'banned@example.com', role: 'user', queries: 12, created: '2024-02-01', active: false },
  ]);

  return (
    <div>
      <div style={{ marginBottom: '2rem' }}>
        <h1 style={{ fontSize: '2rem', fontWeight: 'bold', margin: '0 0 0.5rem 0' }}>Users</h1>
        <p style={{ fontSize: '1rem', opacity: 0.7, margin: 0 }}>Manage user accounts and permissions</p>
      </div>

      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: '1rem', marginBottom: '2rem' }}>
        {[
          { label: 'Total Users', value: '89', color: '#667eea' },
          { label: 'Active Today', value: '34', color: '#4ade80' },
          { label: 'Total Queries', value: '1,247', color: '#f093fb' },
        ].map((stat, i) => (
          <div
            key={i}
            style={{
              background: 'linear-gradient(135deg, rgba(255,255,255,0.05) 0%, rgba(255,255,255,0.02) 100%)',
              border: '1px solid rgba(255,255,255,0.1)',
              borderRadius: '1rem',
              padding: '1.5rem',
            }}
          >
            <div style={{ fontSize: '0.875rem', opacity: 0.7, marginBottom: '0.5rem' }}>{stat.label}</div>
            <div style={{ fontSize: '2rem', fontWeight: 'bold', color: stat.color }}>{stat.value}</div>
          </div>
        ))}
      </div>

      <div
        style={{
          background: 'linear-gradient(135deg, rgba(255,255,255,0.05) 0%, rgba(255,255,255,0.02) 100%)',
          border: '1px solid rgba(255,255,255,0.1)',
          borderRadius: '1rem',
          padding: '1.5rem',
        }}
      >
        <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
          {users.map((user) => (
            <motion.div
              key={user.id}
              whileHover={{ x: 4 }}
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                padding: '1.5rem',
                background: 'rgba(255,255,255,0.02)',
                borderRadius: '0.75rem',
                border: '1px solid rgba(255,255,255,0.05)',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '1rem', flex: 1 }}>
                <div
                  style={{
                    background: user.active ? 'rgba(74,222,128,0.2)' : 'rgba(248,113,113,0.2)',
                    padding: '0.75rem',
                    borderRadius: '0.5rem',
                  }}
                >
                  <PersonIcon style={{ width: '24px', height: '24px', color: user.active ? '#4ade80' : '#f87171' }} />
                </div>
                <div style={{ flex: 1 }}>
                  <h3 style={{ fontSize: '1rem', fontWeight: '600', margin: '0 0 0.25rem 0' }}>{user.email}</h3>
                  <p style={{ fontSize: '0.875rem', opacity: 0.5, margin: 0 }}>
                    {user.queries} queries • {user.role} • Joined {user.created}
                  </p>
                </div>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                <span
                  style={{
                    padding: '0.25rem 0.75rem',
                    borderRadius: '1rem',
                    fontSize: '0.75rem',
                    background: user.active ? 'rgba(74,222,128,0.1)' : 'rgba(248,113,113,0.1)',
                    color: user.active ? '#4ade80' : '#f87171',
                  }}
                >
                  {user.active ? 'Active' : 'Banned'}
                </span>
                <button
                  style={{
                    background: user.active ? 'rgba(248,113,113,0.1)' : 'rgba(74,222,128,0.1)',
                    border: `1px solid ${user.active ? 'rgba(248,113,113,0.2)' : 'rgba(74,222,128,0.2)'}`,
                    borderRadius: '0.5rem',
                    padding: '0.5rem 1rem',
                    color: user.active ? '#f87171' : '#4ade80',
                    cursor: 'pointer',
                    fontSize: '0.875rem',
                    display: 'flex',
                    alignItems: 'center',
                    gap: '0.25rem',
                  }}
                >
                  {user.active ? <><Cross2Icon /> Ban</> : <><CheckIcon /> Unban</>}
                </button>
              </div>
            </motion.div>
          ))}
        </div>
      </div>
    </div>
  );
}
