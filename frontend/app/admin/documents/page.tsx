'use client';

import { useState } from 'react';
import { motion } from 'framer-motion';
import { FileTextIcon, TrashIcon, UploadIcon, MagnifyingGlassIcon } from '@radix-ui/react-icons';

export default function DocumentsPage() {
  const [documents] = useState([
    { id: '1', title: 'Tax Code 2024', chunks: 145, created: '2024-01-15', status: 'indexed' },
    { id: '2', title: 'VAT Guidelines', chunks: 89, created: '2024-01-20', status: 'indexed' },
    { id: '3', title: 'Corporate Tax Rules', chunks: 112, created: '2024-02-01', status: 'indexed' },
    { id: '4', title: 'Income Tax Regulations', chunks: 78, created: '2024-02-05', status: 'processing' },
  ]);

  return (
    <div>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '2rem' }}>
        <div>
          <h1 style={{ fontSize: '2rem', fontWeight: 'bold', margin: '0 0 0.5rem 0' }}>Documents</h1>
          <p style={{ fontSize: '1rem', opacity: 0.7, margin: 0 }}>Manage your knowledge base</p>
        </div>
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
          <UploadIcon /> Upload Document
        </button>
      </div>

      <div
        style={{
          background: 'linear-gradient(135deg, rgba(255,255,255,0.05) 0%, rgba(255,255,255,0.02) 100%)',
          border: '1px solid rgba(255,255,255,0.1)',
          borderRadius: '1rem',
          padding: '1.5rem',
        }}
      >
        <div style={{ display: 'flex', gap: '1rem', marginBottom: '1.5rem' }}>
          <div style={{ position: 'relative', flex: 1 }}>
            <MagnifyingGlassIcon
              style={{
                position: 'absolute',
                left: '1rem',
                top: '50%',
                transform: 'translateY(-50%)',
                width: '20px',
                height: '20px',
                opacity: 0.5,
              }}
            />
            <input
              type="text"
              placeholder="Search documents..."
              style={{
                width: '100%',
                padding: '0.75rem 1rem 0.75rem 3rem',
                background: 'rgba(255,255,255,0.05)',
                border: '1px solid rgba(255,255,255,0.1)',
                borderRadius: '0.5rem',
                color: 'white',
                fontSize: '0.875rem',
              }}
            />
          </div>
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
          {documents.map((doc) => (
            <motion.div
              key={doc.id}
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
                    background: 'rgba(102,126,234,0.2)',
                    padding: '0.75rem',
                    borderRadius: '0.5rem',
                  }}
                >
                  <FileTextIcon style={{ width: '24px', height: '24px', color: '#667eea' }} />
                </div>
                <div style={{ flex: 1 }}>
                  <h3 style={{ fontSize: '1rem', fontWeight: '600', margin: '0 0 0.25rem 0' }}>{doc.title}</h3>
                  <p style={{ fontSize: '0.875rem', opacity: 0.5, margin: 0 }}>
                    {doc.chunks} chunks • Created {doc.created}
                  </p>
                </div>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
                <span
                  style={{
                    padding: '0.25rem 0.75rem',
                    borderRadius: '1rem',
                    fontSize: '0.75rem',
                    background: doc.status === 'indexed' ? 'rgba(74,222,128,0.1)' : 'rgba(251,191,36,0.1)',
                    color: doc.status === 'indexed' ? '#4ade80' : '#fbbf24',
                  }}
                >
                  {doc.status}
                </span>
                <button
                  style={{
                    background: 'rgba(248,113,113,0.1)',
                    border: '1px solid rgba(248,113,113,0.2)',
                    borderRadius: '0.5rem',
                    padding: '0.5rem',
                    color: '#f87171',
                    cursor: 'pointer',
                  }}
                >
                  <TrashIcon style={{ width: '16px', height: '16px' }} />
                </button>
              </div>
            </motion.div>
          ))}
        </div>
      </div>
    </div>
  );
}
