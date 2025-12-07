'use client'

import { useState } from 'react'

export default function Home() {
  const [isLoggedIn, setIsLoggedIn] = useState(false)

  return (
    <main className="flex min-h-screen flex-col">
      {/* Header */}
      <header className="border-b border-border bg-background px-4 py-3">
        <div className="container mx-auto flex items-center justify-between">
          <h1 className="text-2xl font-bold text-primary">
            InfoHub AI Tax Advisor
          </h1>
          <nav className="flex gap-4">
            {!isLoggedIn ? (
              <>
                <a
                  href="/login"
                  className="text-sm font-medium text-foreground hover:text-primary"
                >
                  Login
                </a>
                <a
                  href="/register"
                  className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:bg-primary/90"
                >
                  Register
                </a>
              </>
            ) : (
              <button className="text-sm font-medium text-foreground hover:text-primary">
                Logout
              </button>
            )}
          </nav>
        </div>
      </header>

      {/* Main Content */}
      <div className="flex flex-1">
        {/* Chat Interface */}
        <div className="flex flex-1 flex-col">
          {/* Messages Area */}
          <div className="flex-1 overflow-y-auto p-6">
            <div className="container mx-auto max-w-4xl">
              {/* Welcome Message */}
              <div className="mb-8 text-center">
                <h2 className="mb-2 text-3xl font-bold">
                  Welcome to InfoHub AI Tax Advisor
                </h2>
                <p className="text-muted-foreground">
                  Ask questions about Georgian tax law and get AI-powered answers
                </p>
              </div>

              {/* Example Questions */}
              <div className="mb-8 grid gap-4 md:grid-cols-2">
                <div className="rounded-lg border border-border bg-secondary p-4 hover:bg-secondary/80 cursor-pointer">
                  <h3 className="mb-1 font-semibold">VAT Registration</h3>
                  <p className="text-sm text-muted-foreground">
                    When do I need to register for VAT in Georgia?
                  </p>
                </div>
                <div className="rounded-lg border border-border bg-secondary p-4 hover:bg-secondary/80 cursor-pointer">
                  <h3 className="mb-1 font-semibold">Corporate Tax</h3>
                  <p className="text-sm text-muted-foreground">
                    What is the corporate tax rate for companies?
                  </p>
                </div>
              </div>
            </div>
          </div>

          {/* Input Area */}
          <div className="border-t border-border bg-background p-4">
            <div className="container mx-auto max-w-4xl">
              <div className="flex gap-2">
                <input
                  type="text"
                  placeholder="Ask a question about Georgian tax law..."
                  className="flex-1 rounded-md border border-input bg-background px-4 py-3 text-sm ring-offset-background focus:outline-none focus:ring-2 focus:ring-ring"
                  disabled={!isLoggedIn}
                />
                <button
                  className="rounded-md bg-primary px-6 py-3 text-sm font-medium text-primary-foreground hover:bg-primary/90 disabled:opacity-50"
                  disabled={!isLoggedIn}
                >
                  Send
                </button>
              </div>
              {!isLoggedIn && (
                <p className="mt-2 text-center text-sm text-muted-foreground">
                  Please <a href="/login" className="text-primary hover:underline">login</a> to ask questions
                </p>
              )}
            </div>
          </div>
        </div>
      </div>

      {/* Footer */}
      <footer className="border-t border-border bg-muted px-4 py-4 text-center text-sm text-muted-foreground">
        <p>
          InfoHub AI Tax Advisor - AI-powered assistant for Georgian tax law
        </p>
        <p className="mt-1">
          ⚠️ This is an AI assistant. Always consult with a professional tax advisor.
        </p>
      </footer>
    </main>
  )
}
