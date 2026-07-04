'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';

const nav = [
  { name: 'Чат', href: '/#chat' },
  { name: 'Законы', href: '/laws' },
  { name: 'Статистика решений', href: '/#stats' },
  { name: 'Тарифы', href: '/#pricing' },
];

export function SiteHeader() {
  const pathname = usePathname();
  if (pathname?.startsWith('/admin')) return null;

  return (
    <header className="glass sticky top-0 z-50 border-b">
      <div className="mx-auto flex h-14 max-w-page items-center justify-between px-6">
        <Link href="/" className="flex items-baseline gap-2">
          <span className="text-[17px] font-semibold tracking-display">Tax Advisor</span>
          <span className="text-xs text-muted-foreground">საქართველო</span>
        </Link>
        <nav className="hidden items-center gap-7 sm:flex">
          {nav.map((item) => (
            <Link
              key={item.name}
              href={item.href}
              className="text-[13px] text-muted-foreground transition-colors hover:text-foreground"
            >
              {item.name}
            </Link>
          ))}
        </nav>
      </div>
    </header>
  );
}
