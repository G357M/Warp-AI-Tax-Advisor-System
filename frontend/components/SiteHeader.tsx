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

function BrandMark({ className }: { className?: string }) {
  return (
    <svg viewBox="0 0 64 64" className={className} aria-hidden="true">
      <rect width="64" height="64" rx="14" fill="#0E62D9" />
      <rect x="16" y="17" width="32" height="9" rx="2" fill="#fff" />
      <rect x="27.5" y="17" width="9" height="30" rx="2" fill="#fff" />
    </svg>
  );
}

function LangSwitch({ lang, className }: { lang: Lang; className?: string }) {
  return (
    <div
      className={`flex overflow-hidden rounded-full border ${className ?? ''}`}
      role="group"
      aria-label="Language"
    >
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
  );
}

export function SiteHeader() {
  const pathname = usePathname();
  const { lang, t } = useT();
  const [authed, setAuthed] = useState(false);
  const [open, setOpen] = useState(false);

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

  useEffect(() => setOpen(false), [pathname]);

  if (pathname?.startsWith('/admin')) return null;

  const nav = [
    { name: t('nav.chat'), href: '/#chat' },
    { name: t('nav.laws'), href: '/laws' },
    { name: t('nav.guides'), href: '/guides' },
    { name: t('nav.stats'), href: '/#stats' },
    { name: t('nav.pricing'), href: '/#pricing' },
  ];

  const accountHref = authed ? '/account' : '/login';
  const accountLabel = authed ? t('nav.account') : t('nav.login');

  return (
    <header className="glass sticky top-0 z-50 border-b">
      <div className="mx-auto flex h-14 max-w-page items-center justify-between gap-4 px-6">
        <Link href="/" className="flex shrink-0 items-center gap-2.5" onClick={() => setOpen(false)}>
          <BrandMark className="h-[22px] w-[22px] shrink-0" />
          <span className="flex items-baseline gap-2 whitespace-nowrap">
            <span className="text-[17px] font-semibold tracking-display">Tax Advisor</span>
            <span className="hidden text-xs text-muted-foreground min-[420px]:inline">
              საქართველო
            </span>
          </span>
        </Link>

        {/* Desktop */}
        <nav className="hidden items-center gap-5 lg:flex">
          {nav.map((item) => (
            <Link
              key={item.href}
              href={item.href}
              className="whitespace-nowrap text-[13px] text-muted-foreground transition-colors hover:text-foreground"
            >
              {item.name}
            </Link>
          ))}
          <LangSwitch lang={lang} />
          <Link
            href={accountHref}
            className="whitespace-nowrap rounded-full bg-foreground px-4 py-1.5 text-[13px] font-medium text-background transition-opacity hover:opacity-85"
          >
            {accountLabel}
          </Link>
        </nav>

        {/* Mobile: burger */}
        <button
          type="button"
          onClick={() => setOpen((v) => !v)}
          aria-expanded={open}
          aria-label={t('nav.menu')}
          className="-mr-2 flex h-10 w-10 shrink-0 flex-col items-center justify-center gap-[5px] lg:hidden"
        >
          <span
            className={`h-[1.5px] w-[18px] rounded-full bg-foreground transition-transform duration-200 ${
              open ? 'translate-y-[3.25px] rotate-45' : ''
            }`}
          />
          <span
            className={`h-[1.5px] w-[18px] rounded-full bg-foreground transition-transform duration-200 ${
              open ? '-translate-y-[3.25px] -rotate-45' : ''
            }`}
          />
        </button>
      </div>

      {/* Mobile panel */}
      <div
        className={`absolute inset-x-0 top-full border-b bg-background/95 backdrop-blur-xl transition-all duration-200 lg:hidden ${
          open ? 'visible translate-y-0 opacity-100' : 'invisible -translate-y-2 opacity-0'
        }`}
      >
        <nav className="mx-auto max-w-page px-6 pb-6 pt-2">
          {nav.map((item) => (
            <Link
              key={item.href}
              href={item.href}
              onClick={() => setOpen(false)}
              className="block border-b py-3.5 text-[17px] font-medium tracking-display last:border-0"
            >
              {item.name}
            </Link>
          ))}
          <div className="mt-5 flex items-center justify-between gap-4">
            <LangSwitch lang={lang} />
            <Link
              href={accountHref}
              onClick={() => setOpen(false)}
              className="whitespace-nowrap rounded-full bg-foreground px-5 py-2 text-[14px] font-medium text-background transition-opacity hover:opacity-85"
            >
              {accountLabel}
            </Link>
          </div>
        </nav>
      </div>
    </header>
  );
}
