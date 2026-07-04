'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { isLoggedIn } from '@/lib/auth';

const nav = [
  { name: 'Чат', href: '/#chat' },
  { name: 'Законы', href: '/laws' },
  { name: 'Статистика решений', href: '/#stats' },
  { name: 'Тарифы', href: '/#pricing' },
];

export function SiteHeader() {
  const pathname = usePathname();
  const [authed, setAuthed] = useState(false);

  useEffect(() => {
    const sync = () => setAuthed(isLoggedIn());
    sync();
    window.addEventListener('ta-auth-changed', sync);
    window.addEventListener('storage', sync);
    return () => {
      window.removeEventListener('ta-auth-changed', sync);
      window.removeEventListener('storage', sync);
    };
  }, []);

  if (pathname?.startsWith('/admin')) return null;

  return (
    <header className="glass sticky top-0 z-50 border-b">
      <div className="mx-auto flex h-14 max-w-page items-center justify-between px-6">
        <Link href="/" className="flex items-baseline gap-2">
          <span className="text-[17px] font-semibold tracking-display">Tax Advisor</span>
          <span className="text-xs text-muted-foreground">საქართველო</span>
        </Link>
        <nav className="flex items-center gap-7">
          {nav.map((item) => (
            <Link
              key={item.name}
              href={item.href}
              className="hidden text-[13px] text-muted-foreground transition-colors hover:text-foreground sm:block"
            >
              {item.name}
            </Link>
          ))}
          <Link
            href={authed ? '/account' : '/login'}
            className="rounded-full bg-foreground px-4 py-1.5 text-[13px] font-medium text-background transition-opacity hover:opacity-85"
          >
            {authed ? 'Кабинет' : 'Войти'}
          </Link>
        </nav>
      </div>
    </header>
  );
}
