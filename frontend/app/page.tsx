'use client';

import { motion } from 'framer-motion';
import { RocketIcon, LightningBoltIcon, StarIcon } from '@radix-ui/react-icons';
import { QueryForm } from '@/components/QueryForm';
import { Response } from '@/components/Response';
import { Sources } from '@/components/Sources';
import { useQuery } from '@/hooks/useQuery';

export default function Home() {
  const { data, loading, error, submitQuery } = useQuery();

  return (
    <div
      style={{
        minHeight: '100vh',
        background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
        color: 'white',
        fontFamily: 'system-ui, -apple-system, sans-serif',
        position: 'relative',
        overflow: 'hidden',
      }}
    >
      {/* Animated Background */}
      <div style={{ position: 'absolute', width: '100%', height: '100%', overflow: 'hidden', zIndex: 0 }}>
        <motion.div
          animate={{ scale: [1, 1.2, 1], rotate: [0, 180, 360] }}
          transition={{ duration: 20, repeat: Infinity, ease: 'linear' }}
          style={{
            position: 'absolute',
            top: '10%',
            left: '10%',
            width: '300px',
            height: '300px',
            borderRadius: '50%',
            background: 'radial-gradient(circle, rgba(240,147,251,0.3) 0%, transparent 70%)',
            filter: 'blur(60px)',
          }}
        />
        <motion.div
          animate={{ scale: [1, 1.3, 1], rotate: [360, 180, 0] }}
          transition={{ duration: 25, repeat: Infinity, ease: 'linear' }}
          style={{
            position: 'absolute',
            bottom: '10%',
            right: '10%',
            width: '400px',
            height: '400px',
            borderRadius: '50%',
            background: 'radial-gradient(circle, rgba(118,75,162,0.3) 0%, transparent 70%)',
            filter: 'blur(70px)',
          }}
        />
      </div>

      {/* Header */}
      <motion.header
        initial={{ y: -50, opacity: 0 }}
        animate={{ y: 0, opacity: 1 }}
        style={{
          position: 'relative',
          zIndex: 10,
          padding: '1.5rem 2rem',
          borderBottom: '1px solid rgba(255,255,255,0.1)',
          backgroundColor: 'rgba(255,255,255,0.05)',
          backdropFilter: 'blur(10px)',
        }}
      >
        <div
          style={{
            maxWidth: '1200px',
            margin: '0 auto',
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
            <motion.div
              animate={{ rotate: 360 }}
              transition={{ duration: 20, repeat: Infinity, ease: 'linear' }}
              style={{
                background: 'linear-gradient(135deg, #f093fb 0%, #f5576c 100%)',
                padding: '1rem',
                borderRadius: '1rem',
                boxShadow: '0 10px 25px rgba(240,147,251,0.3)',
              }}
            >
              <RocketIcon style={{ width: '24px', height: '24px', color: 'white' }} />
            </motion.div>
            <div>
              <h1 style={{ fontSize: '1.5rem', fontWeight: 'bold', margin: 0 }}>InfoHub AI</h1>
              <p style={{ fontSize: '0.75rem', margin: 0, opacity: 0.8 }}>Tax Assistant</p>
            </div>
          </div>
          <div style={{ display: 'flex', gap: '0.5rem', fontSize: '0.875rem' }}>
            <div
              style={{
                padding: '0.5rem 1rem',
                borderRadius: '0.75rem',
                background: 'rgba(255,255,255,0.1)',
                display: 'flex',
                alignItems: 'center',
                gap: '0.5rem',
              }}
            >
              <div style={{ width: '8px', height: '8px', borderRadius: '50%', background: '#4ade80' }} />
              <span>Public Beta</span>
            </div>
          </div>
        </div>
      </motion.header>

      {/* Main Content */}
      <div
        style={{
          position: 'relative',
          zIndex: 1,
          padding: '3rem 1.5rem',
          maxWidth: '1200px',
          margin: '0 auto',
        }}
      >
        {/* Hero Section - only show when no data */}
        {!data && (
          <motion.div
            initial={{ opacity: 0, y: 30 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.8 }}
            style={{ textAlign: 'center', marginBottom: '4rem' }}
          >
            <motion.div
              animate={{ y: [0, -10, 0] }}
              transition={{ duration: 3, repeat: Infinity }}
              style={{ marginBottom: '2rem' }}
            >
              <LightningBoltIcon
                style={{
                  width: '80px',
                  height: '80px',
                  color: '#f5576c',
                  filter: 'drop-shadow(0 0 20px rgba(245,87,108,0.5))',
                }}
              />
            </motion.div>

            <h2
              style={{
                fontSize: '3.5rem',
                fontWeight: '900',
                marginBottom: '1.5rem',
                lineHeight: '1.2',
              }}
            >
              Georgian Tax Law
              <br />
              <span
                style={{
                  background: 'linear-gradient(135deg, #f093fb 0%, #f5576c 100%)',
                  WebkitBackgroundClip: 'text',
                  WebkitTextFillColor: 'transparent',
                  backgroundClip: 'text',
                }}
              >
                AI Assistant
              </span>
            </h2>

            <p
              style={{
                fontSize: '1.25rem',
                opacity: 0.9,
                maxWidth: '800px',
                margin: '0 auto 2rem',
              }}
            >
              Получайте мгновенные ответы от AI на основе официальных налоговых документов Грузии
            </p>

            <div
              style={{
                display: 'flex',
                justifyContent: 'center',
                gap: '2rem',
                flexWrap: 'wrap',
                marginBottom: '3rem',
              }}
            >
              <div
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '0.5rem',
                  padding: '0.5rem 1rem',
                  background: 'rgba(255,255,255,0.1)',
                  borderRadius: '2rem',
                }}
              >
                <div style={{ width: '8px', height: '8px', borderRadius: '50%', background: '#4ade80' }} />
                <span>AI Powered</span>
              </div>
              <div
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '0.5rem',
                  padding: '0.5rem 1rem',
                  background: 'rgba(255,255,255,0.1)',
                  borderRadius: '2rem',
                }}
              >
                <StarIcon style={{ width: '16px', height: '16px', color: '#fbbf24' }} />
                <span>Мгновенные ответы</span>
              </div>
              <div
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '0.5rem',
                  padding: '0.5rem 1rem',
                  background: 'rgba(255,255,255,0.1)',
                  borderRadius: '2rem',
                }}
              >
                <span>🇬🇪 🇷🇺 🇬🇧</span>
                <span>3 языка</span>
              </div>
            </div>
          </motion.div>
        )}

        {/* Query Form */}
        <QueryForm onSubmit={submitQuery} loading={loading} />

        {/* Error Display */}
        {error && (
          <motion.div
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            style={{
              maxWidth: '800px',
              margin: '24px auto',
              padding: '16px 24px',
              borderRadius: '16px',
              background: 'rgba(239, 68, 68, 0.1)',
              border: '1px solid rgba(239, 68, 68, 0.3)',
              color: '#fca5a5',
              display: 'flex',
              alignItems: 'center',
              gap: '12px',
            }}
          >
            <span style={{ fontSize: '24px' }}>⚠️</span>
            <div>
              <strong>Ошибка:</strong> {error}
            </div>
          </motion.div>
        )}

        {/* Response Display */}
        {data && (
          <>
            <Response response={data.response} processingTime={data.processing_time} />
            <Sources sources={data.sources} retrievedCount={data.retrieved_count} />
          </>
        )}
      </div>

      {/* Footer */}
      <footer
        style={{
          position: 'relative',
          zIndex: 10,
          padding: '2rem',
          borderTop: '1px solid rgba(255,255,255,0.1)',
          background: 'rgba(255,255,255,0.05)',
          textAlign: 'center',
        }}
      >
        <p style={{ margin: '0 0 1rem 0', opacity: 0.8 }}>
          <strong>InfoHub AI Tax Advisor</strong> • AI-powered assistant for Georgian tax law
        </p>
        <div
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: '0.5rem',
            padding: '0.5rem 1rem',
            background: 'rgba(251,191,36,0.1)',
            borderRadius: '2rem',
            fontSize: '0.875rem',
            color: '#fbbf24',
          }}
        >
          <span>⚠️</span>
          <span>Это AI-помощник. Всегда консультируйтесь с профессиональным налоговым консультантом.</span>
        </div>
      </footer>
    </div>
  );
}
