import './globals.css'
import type { Metadata } from 'next'
import { Inter, Noto_Sans_Georgian } from 'next/font/google'
import { SiteHeader } from '@/components/SiteHeader'
import { SiteFooter } from '@/components/SiteFooter'

const inter = Inter({
  subsets: ['latin', 'cyrillic'],
  variable: '--font-inter',
  display: 'swap',
})

const georgian = Noto_Sans_Georgian({
  subsets: ['georgian'],
  variable: '--font-georgian',
  display: 'swap',
})

export const metadata: Metadata = {
  title: 'Tax Advisor — налоговое право Грузии с точными источниками',
  description:
    'Ответы по налоговому праву Грузии строго по официальной базе: Налоговый кодекс, решения советов по спорам, статистика исходов.',
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="ru" className={`${inter.variable} ${georgian.variable}`}>
      <body className="font-sans">
        <SiteHeader />
        {children}
        <SiteFooter />
      </body>
    </html>
  )
}
