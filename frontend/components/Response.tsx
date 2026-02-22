'use client';

import { motion } from 'framer-motion';

interface ResponseProps {
  response: string;
  processingTime?: number;
}

export function Response({ response, processingTime }: ResponseProps) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5, delay: 0.1 }}
      style={{
        width: '100%',
        maxWidth: '800px',
        margin: '24px auto',
        padding: '24px',
        borderRadius: '20px',
        background: 'rgba(255, 255, 255, 0.05)',
        backdropFilter: 'blur(10px)',
        border: '1px solid rgba(255, 255, 255, 0.1)',
      }}
    >
      {/* Header */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: '12px',
          marginBottom: '16px',
          paddingBottom: '16px',
          borderBottom: '1px solid rgba(255, 255, 255, 0.1)',
        }}
      >
        <span style={{ fontSize: '28px' }}>🤖</span>
        <div style={{ flex: 1 }}>
          <h3
            style={{
              margin: 0,
              fontSize: '18px',
              fontWeight: '600',
              color: '#ffffff',
            }}
          >
            AI Ответ
          </h3>
          {processingTime !== undefined && (
            <p
              style={{
                margin: '4px 0 0 0',
                fontSize: '12px',
                color: 'rgba(255, 255, 255, 0.6)',
              }}
            >
              Обработано за {processingTime.toFixed(2)} сек
            </p>
          )}
        </div>
      </div>

      {/* Response Content */}
      <motion.div
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ duration: 0.8, delay: 0.3 }}
        style={{
          fontSize: '16px',
          lineHeight: '1.7',
          color: '#e0e0e0',
          whiteSpace: 'pre-wrap',
          wordBreak: 'break-word',
        }}
      >
        {response}
      </motion.div>

      {/* Footer */}
      <div
        style={{
          marginTop: '20px',
          paddingTop: '16px',
          borderTop: '1px solid rgba(255, 255, 255, 0.1)',
          display: 'flex',
          alignItems: 'center',
          gap: '8px',
          fontSize: '12px',
          color: 'rgba(255, 255, 255, 0.5)',
        }}
      >
        <span>💡</span>
        <span>
          Ответ сгенерирован на основе документов грузинского налогового законодательства
        </span>
      </div>
    </motion.div>
  );
}
