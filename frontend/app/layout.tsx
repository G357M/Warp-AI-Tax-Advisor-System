import './globals.css'
import type { Metadata } from 'next'
import { Instrument_Serif, Barlow, Inter, Noto_Sans_Georgian, Noto_Serif_Georgian } from 'next/font/google'
import { SiteHeader } from '@/components/SiteHeader'
import { SiteFooter } from '@/components/SiteFooter'

const instrument = Instrument_Serif({
  subsets: ['latin'],
  weight: '400',
  style: 'italic',
  variable: '--font-instrument',
  display: 'swap',
})

// Barlow has no Cyrillic in Google Fonts; Inter carries ru per-glyph fallback.
const barlow = Barlow({
  subsets: ['latin'],
  weight: ['300', '400', '500', '600'],
  variable: '--font-barlow',
  display: 'swap',
})

const inter = Inter({
  subsets: ['cyrillic'],
  variable: '--font-inter',
  display: 'swap',
})

const georgian = Noto_Sans_Georgian({
  subsets: ['georgian'],
  variable: '--font-georgian',
  display: 'swap',
})

const georgianSerif = Noto_Serif_Georgian({
  subsets: ['georgian'],
  variable: '--font-georgian-serif',
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
    <html
      lang="ru"
      className={`${instrument.variable} ${barlow.variable} ${inter.variable} ${georgian.variable} ${georgianSerif.variable}`}
    >
      <body className="bg-black font-body">
        <SiteHeader />
        {/* Offset for the fixed floating header */}
        <div className="pt-24">{children}</div>
        <SiteFooter />
      </body>
    </html>
  )
}
