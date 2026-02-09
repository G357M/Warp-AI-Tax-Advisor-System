'use client';

import { motion } from 'framer-motion';
import { SourceInfo } from '@/lib/api';

interface SourcesProps {
  sources: SourceInfo[];
  retrievedCount: number;
}

export function Sources({ sources, retrievedCount }: SourcesProps) {
  if (!sources || sources.length === 0) {
    return null;
  }

  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5, delay: 0.2 }}
      style={{
        width: '100%',
        maxWidth: '800px',
        margin: '24px auto',
      }}
    >
      {/* Header */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: '12px',
          marginBottom: '16px',
        }}
      >
        <span style={{ fontSize: '24px' }}>📚</span>
        <h3
          style={{
            margin: 0,
            fontSize: '18px',
            fontWeight: '600',
            color: '#ffffff',
          }}
        >
          Источники ({retrievedCount})
        </h3>
      </div>

      {/* Sources List */}
      <div
        style={{
          display: 'flex',
          flexDirection: 'column',
          gap: '12px',
        }}
      >
        {sources.map((source, index) => (
          <motion.div
            key={index}
            initial={{ opacity: 0, x: -20 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ duration: 0.3, delay: 0.3 + index * 0.1 }}
            style={{
              padding: '16px',
              borderRadius: '16px',
              background: 'rgba(255, 255, 255, 0.05)',
              backdropFilter: 'blur(10px)',
              border: '1px solid rgba(255, 255, 255, 0.1)',
              transition: 'all 0.3s ease',
            }}
            onMouseEnter={(e) => {
              e.currentTarget.style.background = 'rgba(255, 255, 255, 0.08)';
              e.currentTarget.style.transform = 'translateX(4px)';
              e.currentTarget.style.borderColor = 'rgba(102, 126, 234, 0.5)';
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.background = 'rgba(255, 255, 255, 0.05)';
              e.currentTarget.style.transform = 'translateX(0)';
              e.currentTarget.style.borderColor = 'rgba(255, 255, 255, 0.1)';
            }}
          >
            {/* Source Header */}
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                marginBottom: '8px',
              }}
            >
              <span
                style={{
                  fontSize: '14px',
                  fontWeight: '600',
                  color: '#667eea',
                }}
              >
                Источник #{index + 1}
              </span>
              
              {/* Relevance Badge */}
              <div
                style={{
                  padding: '4px 12px',
                  borderRadius: '12px',
                  background: getRelevanceColor(source.relevance),
                  fontSize: '12px',
                  fontWeight: '600',
                  color: '#ffffff',
                }}
              >
                {(source.relevance * 100).toFixed(0)}% релевантность
              </div>
            </div>

            {/* Source Text */}
            <p
              style={{
                margin: 0,
                fontSize: '14px',
                lineHeight: '1.6',
                color: '#e0e0e0',
              }}
            >
              {source.text}
            </p>

            {/* Metadata */}
            {source.metadata && Object.keys(source.metadata).length > 0 && (
              <div
                style={{
                  marginTop: '12px',
                  paddingTop: '12px',
                  borderTop: '1px solid rgba(255, 255, 255, 0.1)',
                  display: 'flex',
                  flexWrap: 'wrap',
                  gap: '8px',
                }}
              >
                {Object.entries(source.metadata).map(([key, value]) => {
                  if (key === 'text' || key === 'title' || !value) return null;
                  
                  return (
                    <span
                      key={key}
                      style={{
                        padding: '4px 8px',
                        borderRadius: '8px',
                        background: 'rgba(255, 255, 255, 0.05)',
                        fontSize: '11px',
                        color: 'rgba(255, 255, 255, 0.6)',
                      }}
                    >
                      {key}: {String(value)}
                    </span>
                  );
                })}
              </div>
            )}
          </motion.div>
        ))}
      </div>

      {/* Footer Note */}
      <div
        style={{
          marginTop: '16px',
          padding: '12px',
          borderRadius: '12px',
          background: 'rgba(102, 126, 234, 0.1)',
          border: '1px solid rgba(102, 126, 234, 0.2)',
          display: 'flex',
          alignItems: 'center',
          gap: '8px',
          fontSize: '12px',
          color: 'rgba(255, 255, 255, 0.7)',
        }}
      >
        <span>ℹ️</span>
        <span>
          Эти документы были использованы для генерации ответа. Релевантность показывает,
          насколько точно документ соответствует вашему запросу.
        </span>
      </div>
    </motion.div>
  );
}

function getRelevanceColor(relevance: number): string {
  if (relevance >= 0.8) {
    return 'linear-gradient(135deg, #10b981 0%, #059669 100%)'; // Green
  } else if (relevance >= 0.6) {
    return 'linear-gradient(135deg, #3b82f6 0%, #2563eb 100%)'; // Blue
  } else if (relevance >= 0.4) {
    return 'linear-gradient(135deg, #f59e0b 0%, #d97706 100%)'; // Orange
  } else {
    return 'linear-gradient(135deg, #6b7280 0%, #4b5563 100%)'; // Gray
  }
}
