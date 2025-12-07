import './globals.css'
import type { Metadata } from 'next'

export const metadata: Metadata = {
  title: 'InfoHub AI Tax Advisor',
  description: 'AI-powered tax advisor for Georgia tax law',
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="en">
      <body>{children}</body>
    </html>
  )
}
