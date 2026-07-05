'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { isLoggedIn } from '@/lib/auth';
import { useT, setLang, Lang } from '@/lib/i18n';

const LANGS: { code: Lang; label: string }[] = [
  { code: 'ru', label: 'Рус' },
  { code: 'ka', label: 'ქარ' },
  { code: 'en', label: 'Eng' },
];

export function SiteHeader() {
  const pathname = usePathname();
  const { lang, t } = useT();
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

  const nav = [
    { name: t('nav.chat'), href: '/#chat' },
    { name: t('nav.laws'), href: '/laws' },
    { name: t('nav.guides'), href: '/guides' },
    { name: t('nav.stats'), href: '/#stats' },
    { name: t('nav.pricing'), href: '/#pricing' },
  ];

  return (
    <header className="glass sticky top-0 z-50 border-b">
      <div className="mx-auto flex h-14 max-w-page items-center justify-between px-6">
        <Link href="/" className="flex items-baseline gap-2">
          <span className="text-[17px] font-semibold tracking-display">Tax Advisor</span>
          <span className="text-xs text-muted-foreground">საქართველო</span>
        </Link>
        <nav className="flex items-center gap-5">
          {nav.map((item) => (
            <Link
              key={item.href}
              href={item.href}
              className="hidden text-[13px] text-muted-foreground transition-colors hover:text-foreground lg:block"
            >
              {item.name}
            </Link>
          ))}
          <div className="flex overflow-hidden rounded-full border" role="group" aria-label="Language">
            {LANGS.map((l) => (
              <button
                key={l.code}
                type="button"
                onClick={() => setLang(l.code)}
                className={`px-2.5 py-1 text-xs transition-colors ${
                  lang === l.code
                    ? 'bg-foreground text-background'
                    : 'text-muted-foreground hover:text-foreground'
                }`}
              >
                {l.label}
              </button>
            ))}
          </div>
          <Link
            href={authed ? '/account' : '/login'}
            className="rounded-full bg-foreground px-4 py-1.5 text-[13px] font-medium text-background transition-opacity hover:opacity-85"
          >
            {authed ? t('nav.account') : t('nav.login')}
          </Link>
        </nav>
      </div>
    </header>
  );
}
