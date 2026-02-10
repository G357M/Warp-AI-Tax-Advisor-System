'use client';

import { useState } from 'react';
import { motion } from 'framer-motion';
import { PlayIcon, StopIcon, ReloadIcon } from '@radix-ui/react-icons';

export default function ScraperPage() {
  const [tasks] = useState([
    { id: '1', url: 'https://infohub.ge/tax-code', status: 'completed', docs: 45, started: '2024-02-10 08:00', duration: '2m 34s' },
    { id: '2', url: 'https://infohub.ge/vat-rules', status: 'running', docs: 12, started: '2024-02-10 09:15', duration: '45s' },
    { id: '3', url: 'https://infohub.ge/corporate', status: 'pending', docs: 0, started: '-', duration: '-' },
  ]);

  return (
    <div>
      <div style={{ marginBottom: '2rem' }}>
        <h1 style={{ fontSize: '2rem', fontWeight: 'bold', margin: '0 0 0.5rem 0' }}>Web Scraper</h1>
        <p style={{ fontSize: '1rem', opacity: 0.7, margin: 0 }}>Control document scraping tasks</p>
      </div>

      <div
        style={{
          background: 'linear-gradient(135deg, rgba(102,126,234,0.1) 0%, rgba(102,126,234,0.05) 100%)',
          border: '1px solid rgba(102,126,234,0.2)',
          borderRadius: '1rem',
          padding: '1.5rem',
          marginBottom: '2rem',
        }}
      >
        <h3 style={{ fontSize: '1rem', fontWeight: '600', margin: '0 0 1rem 0' }}>Start New Scrape Task</h3>
        <div style={{ display: 'flex', gap: '1rem' }}>
          <input
            type="text"
            placeholder="Enter URL to scrape (e.g., https://infohub.ge/tax)"
            style={{
              flex: 1,
              padding: '0.75rem 1rem',
              background: 'rgba(255,255,255,0.05)',
              border: '1px solid rgba(255,255,255,0.1)',
              borderRadius: '0.5rem',
              color: 'white',
              fontSize: '0.875rem',
            }}
          />
          <button
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '0.5rem',
              padding: '0.75rem 1.5rem',
              background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
              border: 'none',
              borderRadius: '0.5rem',
              color: 'white',
              cursor: 'pointer',
              fontSize: '0.875rem',
              fontWeight: '600',
            }}
          >
            <PlayIcon /> Start Scraping
          </button>
        </div>
      </div>

      <div
        style={{
          background: 'linear-gradient(135deg, rgba(255,255,255,0.05) 0%, rgba(255,255,255,0.02) 100%)',
          border: '1px solid rgba(255,255,255,0.1)',
          borderRadius: '1rem',
          padding: '1.5rem',
        }}
      >
        <h3 style={{ fontSize: '1.25rem', fontWeight: 'bold', margin: '0 0 1.5rem 0' }}>Scraper Tasks</h3>
        <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
          {tasks.map((task) => (
            <motion.div
              key={task.id}
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
              <div style={{ flex: 1 }}>
                <h4 style={{ fontSize: '1rem', fontWeight: '600', margin: '0 0 0.5rem 0' }}>{task.url}</h4>
                <div style={{ display: 'flex', gap: '1.5rem', fontSize: '0.875rem', opacity: 0.7 }}>
                  <span>{task.docs} documents</span>
                  <span>Started: {task.started}</span>
                  <span>Duration: {task.duration}</span>
                </div>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
                <span
                  style={{
                    padding: '0.25rem 0.75rem',
                    borderRadius: '1rem',
                    fontSize: '0.75rem',
                    background:
                      task.status === 'completed'
                        ? 'rgba(74,222,128,0.1)'
                        : task.status === 'running'
                        ? 'rgba(251,191,36,0.1)'
                        : 'rgba(148,163,184,0.1)',
                    color:
                      task.status === 'completed'
                        ? '#4ade80'
                        : task.status === 'running'
                        ? '#fbbf24'
                        : '#94a3b8',
                  }}
                >
                  {task.status}
                </span>
                {task.status === 'running' ? (
                  <button
                    style={{
                      background: 'rgba(248,113,113,0.1)',
                      border: '1px solid rgba(248,113,113,0.2)',
                      borderRadius: '0.5rem',
                      padding: '0.5rem 1rem',
                      color: '#f87171',
                      cursor: 'pointer',
                      fontSize: '0.875rem',
                      display: 'flex',
                      alignItems: 'center',
                      gap: '0.5rem',
                    }}
                  >
                    <StopIcon /> Stop
                  </button>
                ) : (
                  <button
                    style={{
                      background: 'rgba(102,126,234,0.1)',
                      border: '1px solid rgba(102,126,234,0.2)',
                      borderRadius: '0.5rem',
                      padding: '0.5rem 1rem',
                      color: '#667eea',
                      cursor: 'pointer',
                      fontSize: '0.875rem',
                      display: 'flex',
                      alignItems: 'center',
                      gap: '0.5rem',
                    }}
                  >
                    <ReloadIcon /> Retry
                  </button>
                )}
              </div>
            </motion.div>
          ))}
        </div>
      </div>
    </div>
  );
}
