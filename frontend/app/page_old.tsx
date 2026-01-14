'use client'

import { useState } from 'react'
import { motion } from 'framer-motion'
import { PaperPlaneIcon, RocketIcon, LightningBoltIcon, MagnifyingGlassIcon, StarIcon } from '@radix-ui/react-icons'

export default function Home() {
  const [isLoggedIn, setIsLoggedIn] = useState(false)
  const [query, setQuery] = useState('')

  return (
    <main className="relative flex min-h-screen flex-col overflow-hidden">
      {/* Animated Background */}
      <div className="fixed inset-0 -z-10">
        <div className="absolute inset-0 bg-gradient-to-br from-purple-900 via-slate-900 to-blue-900"></div>
        <div className="absolute top-0 left-1/4 w-96 h-96 bg-purple-500 rounded-full mix-blend-multiply filter blur-3xl opacity-20 animate-pulse-slow"></div>
        <div className="absolute bottom-0 right-1/4 w-96 h-96 bg-pink-500 rounded-full mix-blend-multiply filter blur-3xl opacity-20 animate-pulse-slow animation-delay-2000"></div>
        <div className="absolute top-1/2 left-1/2 w-96 h-96 bg-blue-500 rounded-full mix-blend-multiply filter blur-3xl opacity-20 animate-pulse-slow animation-delay-4000"></div>
      </div>
      {/* Header */}
      <motion.header 
        initial={{ y: -100, opacity: 0 }}
        animate={{ y: 0, opacity: 1 }}
        transition={{ duration: 0.5 }}
        className="border-b border-white/10 bg-white/5 backdrop-blur-xl px-6 py-5 sticky top-0 z-50"
      >
        <div className="container mx-auto flex items-center justify-between">
          <motion.div 
            className="flex items-center gap-3"
            whileHover={{ scale: 1.02 }}
          >
            <motion.div 
              className="rounded-2xl bg-gradient-to-br from-purple-500 to-pink-500 p-3 shadow-lg shadow-purple-500/50"
              animate={{ rotate: [0, 360] }}
              transition={{ duration: 20, repeat: Infinity, ease: "linear" }}
            >
              <RocketIcon className="h-6 w-6 text-white" />
            </motion.div>
            <div>
              <h1 className="text-2xl font-bold text-transparent bg-clip-text bg-gradient-to-r from-purple-400 via-pink-400 to-purple-400">
                InfoHub AI
              </h1>
              <p className="text-xs text-purple-300">Tax Assistant</p>
            </div>
          </motion.div>
          <nav className="flex gap-3">
            {!isLoggedIn ? (
              <>
                <motion.a
                  whileHover={{ scale: 1.05, y: -2 }}
                  whileTap={{ scale: 0.95 }}
                  href="/login"
                  className="px-6 py-2.5 rounded-xl text-sm font-medium text-white/90 hover:text-white hover:bg-white/10 transition-all"
                >
                  Login
                </motion.a>
                <motion.a
                  whileHover={{ scale: 1.05, y: -2 }}
                  whileTap={{ scale: 0.95 }}
                  href="/register"
                  className="px-6 py-2.5 rounded-xl bg-gradient-to-r from-purple-500 to-pink-500 text-sm font-semibold text-white shadow-lg shadow-purple-500/30 hover:shadow-purple-500/50 transition-all"
                >
                  <span className="flex items-center gap-2">
                    <StarIcon className="h-4 w-4" />
                    Get Started
                  </span>
                </motion.a>
              </>
            ) : (
              <motion.button 
                whileHover={{ scale: 1.05 }}
                whileTap={{ scale: 0.95 }}
                className="text-sm font-medium text-white/80 hover:text-white"
              >
                Logout
              </motion.button>
            )}
          </nav>
        </div>
      </motion.header>

      {/* Main Content */}
      <div className="flex flex-1">
        {/* Chat Interface */}
        <div className="flex flex-1 flex-col">
          {/* Messages Area */}
          <div className="flex-1 overflow-y-auto p-6 bg-gradient-to-b from-background via-background/95 to-primary/5">
            <div className="container mx-auto max-w-5xl">
              {/* Welcome Message */}
              <motion.div 
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.2, duration: 0.6 }}
                className="mb-12 text-center"
              >
                <motion.div
                  initial={{ scale: 0.8 }}
                  animate={{ scale: 1 }}
                  transition={{ delay: 0.3, duration: 0.5 }}
                  className="mb-6 inline-flex items-center justify-center"
                >
                  <div className="relative">
                    <div className="absolute inset-0 blur-2xl bg-primary/30 rounded-full"></div>
                    <LightningBoltIcon className="relative h-16 w-16 text-primary" />
                  </div>
                </motion.div>
                <h2 className="mb-4 text-5xl font-bold bg-gradient-to-r from-foreground via-primary to-foreground bg-clip-text text-transparent">
                  Georgian Tax Law Assistant
                </h2>
                <p className="text-lg text-muted-foreground max-w-2xl mx-auto">
                  AI-powered answers from official tax documents, court decisions, and regulatory guidelines
                </p>
                <motion.div 
                  className="mt-6 flex items-center justify-center gap-6 text-sm"
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  transition={{ delay: 0.8 }}
                >
                  <div className="flex items-center gap-2">
                    <div className="h-2 w-2 rounded-full bg-green-500 animate-pulse"></div>
                    <span className="text-muted-foreground">AI Ready</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <MagnifyingGlassIcon className="h-4 w-4 text-primary" />
                    <span className="text-muted-foreground">1000+ Documents</span>
                  </div>
                </motion.div>
              </motion.div>

              {/* Example Questions */}
              <motion.div 
                initial={{ opacity: 0, y: 20 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.5, duration: 0.6 }}
                className="mb-8 grid gap-4 md:grid-cols-2"
              >
                <motion.div 
                  whileHover={{ scale: 1.02, y: -5 }}
                  whileTap={{ scale: 0.98 }}
                  className="group rounded-xl border border-border/50 bg-gradient-to-br from-secondary/80 to-secondary/40 p-6 hover:border-primary/50 cursor-pointer transition-all shadow-lg hover:shadow-xl hover:shadow-primary/10"
                  onClick={() => setQuery('When do I need to register for VAT in Georgia?')}
                >
                  <div className="flex items-start gap-3">
                    <div className="rounded-lg bg-primary/10 p-2 group-hover:bg-primary/20 transition-colors">
                      <RocketIcon className="h-5 w-5 text-primary" />
                    </div>
                    <div className="flex-1">
                      <h3 className="mb-2 font-semibold text-lg group-hover:text-primary transition-colors">VAT Registration</h3>
                      <p className="text-sm text-muted-foreground">
                        When do I need to register for VAT in Georgia?
                      </p>
                    </div>
                  </div>
                </motion.div>
                <motion.div 
                  whileHover={{ scale: 1.02, y: -5 }}
                  whileTap={{ scale: 0.98 }}
                  className="group rounded-xl border border-border/50 bg-gradient-to-br from-secondary/80 to-secondary/40 p-6 hover:border-primary/50 cursor-pointer transition-all shadow-lg hover:shadow-xl hover:shadow-primary/10"
                  onClick={() => setQuery('What is the corporate tax rate for companies?')}
                >
                  <div className="flex items-start gap-3">
                    <div className="rounded-lg bg-primary/10 p-2 group-hover:bg-primary/20 transition-colors">
                      <LightningBoltIcon className="h-5 w-5 text-primary" />
                    </div>
                    <div className="flex-1">
                      <h3 className="mb-2 font-semibold text-lg group-hover:text-primary transition-colors">Corporate Tax</h3>
                      <p className="text-sm text-muted-foreground">
                        What is the corporate tax rate for companies?
                      </p>
                    </div>
                  </div>
                </motion.div>
              </motion.div>
            </div>
          </div>

          {/* Input Area */}
          <motion.div 
            initial={{ y: 100, opacity: 0 }}
            animate={{ y: 0, opacity: 1 }}
            transition={{ delay: 0.4, duration: 0.5 }}
            className="border-t border-border/40 bg-gradient-to-r from-background via-background to-primary/5 backdrop-blur-sm p-6 shadow-2xl"
          >
            <div className="container mx-auto max-w-4xl">
              <div className="flex gap-3">
                <div className="relative flex-1">
                  <input
                    type="text"
                    value={query}
                    onChange={(e) => setQuery(e.target.value)}
                    placeholder="Ask anything about Georgian tax law..."
                    className="w-full rounded-xl border-2 border-border/50 bg-background/80 backdrop-blur-sm px-6 py-4 text-sm shadow-lg focus:border-primary/50 focus:outline-none focus:ring-4 focus:ring-primary/20 transition-all disabled:opacity-50 pr-12"
                    disabled={!isLoggedIn}
                    onKeyDown={(e) => e.key === 'Enter' && !e.shiftKey && console.log('Send query')}
                  />
                  {query && (
                    <motion.button
                      initial={{ scale: 0 }}
                      animate={{ scale: 1 }}
                      className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground transition-colors"
                      onClick={() => setQuery('')}
                    >
                      ×
                    </motion.button>
                  )}
                </div>
                <motion.button
                  whileHover={{ scale: 1.05 }}
                  whileTap={{ scale: 0.95 }}
                  className="rounded-xl bg-gradient-to-r from-primary to-primary/80 px-8 py-4 text-sm font-medium text-primary-foreground shadow-lg shadow-primary/25 hover:shadow-primary/40 transition-all disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-2"
                  disabled={!isLoggedIn || !query.trim()}
                  onClick={() => console.log('Send query:', query)}
                >
                  <span>Send</span>
                  <PaperPlaneIcon className="h-4 w-4" />
                </motion.button>
              </div>
              {!isLoggedIn ? (
                <motion.p 
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  transition={{ delay: 0.6 }}
                  className="mt-4 text-center text-sm text-muted-foreground"
                >
                  Please{' '}
                  <a href="/login" className="text-primary hover:underline font-medium">
                    login
                  </a>
                  {' '}or{' '}
                  <a href="/register" className="text-primary hover:underline font-medium">
                    create an account
                  </a>
                  {' '}to ask questions
                </motion.p>
              ) : (
                <motion.p 
                  initial={{ opacity: 0 }}
                  animate={{ opacity: 1 }}
                  className="mt-3 text-center text-xs text-muted-foreground"
                >
                  Press Enter to send • Shift + Enter for new line
                </motion.p>
              )}
            </div>
          </motion.div>
        </div>
      </div>

      {/* Footer */}
      <motion.footer 
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        transition={{ delay: 0.8 }}
        className="border-t border-border/40 bg-gradient-to-r from-muted/50 via-muted/30 to-primary/5 backdrop-blur-sm px-6 py-6"
      >
        <div className="container mx-auto max-w-4xl">
          <div className="text-center">
            <p className="text-sm text-muted-foreground">
              <span className="font-semibold text-foreground">InfoHub AI Tax Advisor</span> - AI-powered assistant for Georgian tax law
            </p>
            <div className="mt-3 flex items-center justify-center gap-2 text-xs">
              <span className="inline-flex items-center gap-1.5 rounded-full bg-amber-500/10 px-3 py-1 text-amber-700 dark:text-amber-400">
                <span className="text-base">⚠️</span>
                <span>This is an AI assistant. Always consult with a professional tax advisor.</span>
              </span>
            </div>
            <p className="mt-3 text-xs text-muted-foreground/60">
              © 2024 InfoHub AI. All rights reserved.
            </p>
          </div>
        </div>
      </motion.footer>
    </main>
  )
}
