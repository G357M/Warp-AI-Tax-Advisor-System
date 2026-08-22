import '@fontsource/instrument-serif/400-italic.css'
import '@fontsource/barlow/300.css'
import '@fontsource/barlow/400.css'
import '@fontsource/barlow/500.css'
import '@fontsource/barlow/600.css'
import '@fontsource-variable/inter/wght.css'
import '@fontsource-variable/noto-sans-georgian/wght.css'
import '@fontsource-variable/noto-serif-georgian/wght.css'
import './globals.css'
import type { Metadata } from 'next'
import { SiteHeader } from '@/components/SiteHeader'
import { SiteFooter } from '@/components/SiteFooter'

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
    <html lang="ru">
      <body className="bg-black font-body">
        <SiteHeader />
        {/* Offset for the fixed floating header */}
        <div className="pt-24">{children}</div>
        <SiteFooter />
      </body>
    </html>
  )
}
