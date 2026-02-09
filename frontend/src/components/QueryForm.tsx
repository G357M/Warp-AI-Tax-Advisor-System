'use client';

import { useState, FormEvent } from 'react';
import { motion } from 'framer-motion';

interface QueryFormProps {
  onSubmit: (query: string, language: 'ka' | 'ru' | 'en') => void;
  loading?: boolean;
}

const LANGUAGES = [
  { value: 'ru', label: 'Русский', flag: '🇷🇺' },
  { value: 'ka', label: 'ქართული', flag: '🇬🇪' },
  { value: 'en', label: 'English', flag: '🇬🇧' },
] as const;

export function QueryForm({ onSubmit, loading = false }: QueryFormProps) {
  const [query, setQuery] = useState('');
  const [language, setLanguage] = useState<'ka' | 'ru' | 'en'>('ru');

  const handleSubmit = (e: FormEvent) => {
    e.preventDefault();
    if (query.trim() && !loading) {
      onSubmit(query.trim(), language);
    }
  };

  return (
    <motion.form
      onSubmit={handleSubmit}
      initial={{ opacity: 0, y: 20 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.5 }}
      style={{
        width: '100%',
        maxWidth: '800px',
        margin: '0 auto',
      }}
    >
      {/* Language Selector */}
      <div style={{ marginBottom: '16px' }}>
        <label
          style={{
            display: 'block',
            marginBottom: '8px',
            fontSize: '14px',
            fontWeight: '500',
            color: '#e0e0e0',
          }}
        >
          Язык запроса / Query Language
        </label>
        <div
          style={{
            display: 'flex',
            gap: '12px',
            flexWrap: 'wrap',
          }}
        >
          {LANGUAGES.map((lang) => (
            <button
              key={lang.value}
              type="button"
              onClick={() => setLanguage(lang.value)}
              disabled={loading}
              style={{
                padding: '8px 16px',
                borderRadius: '12px',
                border: language === lang.value ? '2px solid #667eea' : '2px solid transparent',
                background: language === lang.value
                  ? 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)'
                  : 'rgba(255, 255, 255, 0.1)',
                color: '#ffffff',
                fontSize: '14px',
                cursor: loading ? 'not-allowed' : 'pointer',
                transition: 'all 0.3s ease',
                backdropFilter: 'blur(10px)',
                opacity: loading ? 0.6 : 1,
              }}
              onMouseEnter={(e) => {
                if (!loading && language !== lang.value) {
                  e.currentTarget.style.background = 'rgba(255, 255, 255, 0.15)';
                  e.currentTarget.style.transform = 'translateY(-2px)';
                }
              }}
              onMouseLeave={(e) => {
                if (language !== lang.value) {
                  e.currentTarget.style.background = 'rgba(255, 255, 255, 0.1)';
                  e.currentTarget.style.transform = 'translateY(0)';
                }
              }}
            >
              {lang.flag} {lang.label}
            </button>
          ))}
        </div>
      </div>

      {/* Query Input */}
      <div style={{ marginBottom: '16px' }}>
        <label
          htmlFor="query"
          style={{
            display: 'block',
            marginBottom: '8px',
            fontSize: '14px',
            fontWeight: '500',
            color: '#e0e0e0',
          }}
        >
          Ваш вопрос / Your Question
        </label>
        <textarea
          id="query"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          disabled={loading}
          placeholder="Например: Какой размер НДС в Грузии?"
          rows={4}
          style={{
            width: '100%',
            padding: '16px',
            borderRadius: '16px',
            border: '2px solid rgba(255, 255, 255, 0.1)',
            background: 'rgba(255, 255, 255, 0.05)',
            backdropFilter: 'blur(10px)',
            color: '#ffffff',
            fontSize: '16px',
            fontFamily: 'inherit',
            resize: 'vertical',
            transition: 'all 0.3s ease',
            outline: 'none',
          }}
          onFocus={(e) => {
            e.currentTarget.style.borderColor = '#667eea';
            e.currentTarget.style.background = 'rgba(255, 255, 255, 0.08)';
          }}
          onBlur={(e) => {
            e.currentTarget.style.borderColor = 'rgba(255, 255, 255, 0.1)';
            e.currentTarget.style.background = 'rgba(255, 255, 255, 0.05)';
          }}
        />
      </div>

      {/* Submit Button */}
      <motion.button
        type="submit"
        disabled={!query.trim() || loading}
        whileHover={!loading && query.trim() ? { scale: 1.02 } : {}}
        whileTap={!loading && query.trim() ? { scale: 0.98 } : {}}
        style={{
          width: '100%',
          padding: '16px 32px',
          borderRadius: '16px',
          border: 'none',
          background: loading || !query.trim()
            ? 'rgba(255, 255, 255, 0.2)'
            : 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
          color: '#ffffff',
          fontSize: '18px',
          fontWeight: '600',
          cursor: loading || !query.trim() ? 'not-allowed' : 'pointer',
          transition: 'all 0.3s ease',
          boxShadow: loading || !query.trim()
            ? 'none'
            : '0 8px 32px rgba(102, 126, 234, 0.3)',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          gap: '12px',
        }}
      >
        {loading ? (
          <>
            <motion.div
              animate={{ rotate: 360 }}
              transition={{ duration: 1, repeat: Infinity, ease: 'linear' }}
              style={{
                width: '20px',
                height: '20px',
                border: '3px solid rgba(255, 255, 255, 0.3)',
                borderTop: '3px solid #ffffff',
                borderRadius: '50%',
              }}
            />
            Обработка...
          </>
        ) : (
          <>
            <span style={{ fontSize: '24px' }}>🚀</span>
            Отправить запрос
          </>
        )}
      </motion.button>
    </motion.form>
  );
}
