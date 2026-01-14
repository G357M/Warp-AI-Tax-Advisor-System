'use client'

import { useState } from 'react'
import { motion } from 'framer-motion'
import { PaperPlaneIcon, RocketIcon, LightningBoltIcon, MagnifyingGlassIcon, StarIcon } from '@radix-ui/react-icons'

export default function Home() {
  const [isLoggedIn, setIsLoggedIn] = useState(false)
  const [query, setQuery] = useState('')

  return (
    <div style={{
      minHeight: '100vh',
      background: 'linear-gradient(135deg, #667eea 0%, #764ba2 100%)',
      color: 'white',
      fontFamily: 'system-ui, -apple-system, sans-serif'
    }}>
      {/* Header */}
      <motion.header 
        initial={{ y: -50, opacity: 0 }}
        animate={{ y: 0, opacity: 1 }}
        style={{
          padding: '1.5rem 2rem',
          borderBottom: '1px solid rgba(255,255,255,0.1)',
          backgroundColor: 'rgba(255,255,255,0.05)',
          backdropFilter: 'blur(10px)'
        }}
      >
        <div style={{ maxWidth: '1200px', margin: '0 auto', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
            <motion.div
              animate={{ rotate: 360 }}
              transition={{ duration: 20, repeat: Infinity, ease: "linear" }}
              style={{
                background: 'linear-gradient(135deg, #f093fb 0%, #f5576c 100%)',
                padding: '1rem',
                borderRadius: '1rem',
                boxShadow: '0 10px 25px rgba(240,147,251,0.3)'
              }}
            >
              <RocketIcon style={{ width: '24px', height: '24px', color: 'white' }} />
            </motion.div>
            <div>
              <h1 style={{ fontSize: '1.5rem', fontWeight: 'bold', margin: 0 }}>InfoHub AI</h1>
              <p style={{ fontSize: '0.75rem', margin: 0, opacity: 0.8 }}>Tax Assistant</p>
            </div>
          </div>
          <div style={{ display: 'flex', gap: '1rem' }}>
            {!isLoggedIn ? (
              <>
                <motion.a
                  whileHover={{ scale: 1.05 }}
                  href="/login"
                  style={{
                    padding: '0.75rem 1.5rem',
                    borderRadius: '0.75rem',
                    backgroundColor: 'rgba(255,255,255,0.1)',
                    color: 'white',
                    textDecoration: 'none',
                    fontWeight: '500'
                  }}
                >
                  Login
                </motion.a>
                <motion.a
                  whileHover={{ scale: 1.05 }}
                  href="/register"
                  style={{
                    padding: '0.75rem 1.5rem',
                    borderRadius: '0.75rem',
                    background: 'linear-gradient(135deg, #f093fb 0%, #f5576c 100%)',
                    color: 'white',
                    textDecoration: 'none',
                    fontWeight: 'bold',
                    boxShadow: '0 10px 25px rgba(240,147,251,0.3)',
                    display: 'flex',
                    alignItems: 'center',
                    gap: '0.5rem'
                  }}
                >
                  <StarIcon style={{ width: '16px', height: '16px' }} />
                  Get Started
                </motion.a>
              </>
            ) : (
              <button style={{ color: 'white', background: 'none', border: 'none', cursor: 'pointer' }}>
                Logout
              </button>
            )}
          </div>
        </div>
      </motion.header>

      {/* Main Content */}
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', minHeight: 'calc(100vh - 200px)', padding: '3rem 1.5rem' }}>
        <div style={{ maxWidth: '1200px', width: '100%' }}>
          {/* Hero */}
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
              <LightningBoltIcon style={{ width: '80px', height: '80px', color: '#f5576c', filter: 'drop-shadow(0 0 20px rgba(245,87,108,0.5))' }} />
            </motion.div>
            
            <h2 style={{ fontSize: '3.5rem', fontWeight: '900', marginBottom: '1.5rem', lineHeight: '1.2' }}>
              Georgian Tax Law<br />
              <span style={{ background: 'linear-gradient(135deg, #f093fb 0%, #f5576c 100%)', WebkitBackgroundClip: 'text', WebkitTextFillColor: 'transparent', backgroundClip: 'text', color: 'transparent' }}>
                AI Assistant
              </span>
            </h2>
            
            <p style={{ fontSize: '1.25rem', opacity: 0.9, maxWidth: '800px', margin: '0 auto 2rem' }}>
              Get instant AI-powered answers from official tax documents, court decisions, and regulatory guidelines
            </p>

            <div style={{ display: 'flex', justifyContent: 'center', gap: '2rem', flexWrap: 'wrap' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', padding: '0.5rem 1rem', background: 'rgba(255,255,255,0.1)', borderRadius: '2rem' }}>
                <div style={{ width: '8px', height: '8px', borderRadius: '50%', background: '#4ade80' }}></div>
                <span>AI Ready</span>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', padding: '0.5rem 1rem', background: 'rgba(255,255,255,0.1)', borderRadius: '2rem' }}>
                <MagnifyingGlassIcon style={{ width: '16px', height: '16px' }} />
                <span>1000+ Documents</span>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', padding: '0.5rem 1rem', background: 'rgba(255,255,255,0.1)', borderRadius: '2rem' }}>
                <StarIcon style={{ width: '16px', height: '16px', color: '#fbbf24' }} />
                <span>Instant Answers</span>
              </div>
            </div>
          </motion.div>

          {/* Examples */}
          <motion.div
            initial={{ opacity: 0, y: 30 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.4, duration: 0.8 }}
            style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(300px, 1fr))', gap: '1.5rem', marginBottom: '3rem' }}
          >
            <motion.div
              whileHover={{ scale: 1.03, y: -5 }}
              onClick={() => setQuery('When do I need to register for VAT in Georgia?')}
              style={{
                padding: '2rem',
                borderRadius: '1.5rem',
                background: 'rgba(255,255,255,0.1)',
                backdropFilter: 'blur(10px)',
                border: '1px solid rgba(255,255,255,0.1)',
                cursor: 'pointer'
              }}
            >
              <div style={{ marginBottom: '1rem', padding: '1rem', background: 'linear-gradient(135deg, #f093fb 0%, #f5576c 100%)', borderRadius: '1rem', display: 'inline-block' }}>
                <RocketIcon style={{ width: '24px', height: '24px', color: 'white' }} />
              </div>
              <h3 style={{ fontSize: '1.25rem', fontWeight: 'bold', marginBottom: '0.5rem' }}>VAT Registration</h3>
              <p style={{ opacity: 0.8, margin: 0 }}>When do I need to register for VAT in Georgia?</p>
            </motion.div>

            <motion.div
              whileHover={{ scale: 1.03, y: -5 }}
              onClick={() => setQuery('What is the corporate tax rate for companies?')}
              style={{
                padding: '2rem',
                borderRadius: '1.5rem',
                background: 'rgba(255,255,255,0.1)',
                backdropFilter: 'blur(10px)',
                border: '1px solid rgba(255,255,255,0.1)',
                cursor: 'pointer'
              }}
            >
              <div style={{ marginBottom: '1rem', padding: '1rem', background: 'linear-gradient(135deg, #f5576c 0%, #f093fb 100%)', borderRadius: '1rem', display: 'inline-block' }}>
                <LightningBoltIcon style={{ width: '24px', height: '24px', color: 'white' }} />
              </div>
              <h3 style={{ fontSize: '1.25rem', fontWeight: 'bold', marginBottom: '0.5rem' }}>Corporate Tax</h3>
              <p style={{ opacity: 0.8, margin: 0 }}>What is the corporate tax rate for companies?</p>
            </motion.div>
          </motion.div>

          {/* Input */}
          <motion.div
            initial={{ y: 50, opacity: 0 }}
            animate={{ y: 0, opacity: 1 }}
            transition={{ delay: 0.6, duration: 0.8 }}
            style={{
              padding: '2rem',
              borderRadius: '1.5rem',
              background: 'rgba(255,255,255,0.1)',
              backdropFilter: 'blur(10px)',
              border: '1px solid rgba(255,255,255,0.1)'
            }}
          >
            <div style={{ display: 'flex', gap: '1rem', flexWrap: 'wrap' }}>
              <input
                type="text"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="Ask anything about Georgian tax law..."
                disabled={!isLoggedIn}
                style={{
                  flex: '1',
                  minWidth: '300px',
                  padding: '1.25rem 1.5rem',
                  borderRadius: '1rem',
                  border: '2px solid rgba(255,255,255,0.2)',
                  background: 'rgba(255,255,255,0.05)',
                  color: 'white',
                  fontSize: '1rem',
                  outline: 'none'
                }}
              />
              <motion.button
                whileHover={{ scale: 1.05 }}
                whileTap={{ scale: 0.95 }}
                disabled={!isLoggedIn || !query.trim()}
                style={{
                  padding: '1.25rem 2.5rem',
                  borderRadius: '1rem',
                  background: 'linear-gradient(135deg, #f093fb 0%, #f5576c 100%)',
                  color: 'white',
                  border: 'none',
                  fontWeight: 'bold',
                  fontSize: '1rem',
                  cursor: 'pointer',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '0.5rem',
                  boxShadow: '0 10px 25px rgba(240,147,251,0.3)',
                  opacity: (!isLoggedIn || !query.trim()) ? 0.5 : 1
                }}
              >
                <span>Send</span>
                <PaperPlaneIcon style={{ width: '18px', height: '18px' }} />
              </motion.button>
            </div>
            
            {!isLoggedIn && (
              <p style={{ marginTop: '1rem', textAlign: 'center', opacity: 0.8 }}>
                Please <a href="/login" style={{ color: '#f5576c', textDecoration: 'underline' }}>login</a> or{' '}
                <a href="/register" style={{ color: '#f093fb', textDecoration: 'underline' }}>create an account</a> to ask questions
              </p>
            )}
          </motion.div>
        </div>
      </div>

      {/* Footer */}
      <footer style={{
        padding: '2rem',
        borderTop: '1px solid rgba(255,255,255,0.1)',
        background: 'rgba(255,255,255,0.05)',
        textAlign: 'center'
      }}>
        <p style={{ margin: '0 0 1rem 0', opacity: 0.8 }}>
          <strong>InfoHub AI Tax Advisor</strong> • AI-powered assistant for Georgian tax law
        </p>
        <div style={{ display: 'inline-flex', alignItems: 'center', gap: '0.5rem', padding: '0.5rem 1rem', background: 'rgba(251,191,36,0.1)', borderRadius: '2rem', fontSize: '0.875rem', color: '#fbbf24' }}>
          <span>⚠️</span>
          <span>This is an AI assistant. Always consult with a professional tax advisor.</span>
        </div>
      </footer>
    </div>
  )
}
