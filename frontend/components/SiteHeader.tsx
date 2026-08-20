'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { isLoggedIn } from '@/lib/auth';
import { useT, setLang, Lang } from '@/lib/i18n';

const LANGS: { code: Lang; label: string }[] = [
  { code: 'en', label: 'EN' },
  { code: 'ru', label: 'RU' },
  { code: 'ka', label: 'KA' },
];

function LangSwitch({ lang, className }: { lang: Lang; className?: string }) {
  return (
    <div className={`flex items-center gap-1 ${className ?? ''}`} role="group" aria-label="Language">
      {LANGS.map((l, i) => (
        <span key={l.code} className="flex items-center gap-1">
          {i > 0 && <span className="text-xs text-white/25">|</span>}
          <button
            type="button"
            onClick={() => setLang(l.code)}
            className={`flex min-h-[44px] min-w-[32px] items-center justify-center px-1 text-xs transition-colors ${
              lang === l.code ? 'font-medium text-white' : 'text-white/50 hover:text-white'
            }`}
          >
            {l.label}
          </button>
        </span>
      ))}
    </div>
  );
}

export function SiteHeader() {
  const pathname = usePathname();
  const { lang, t } = useT();
  const [authed, setAuthed] = useState(false);
  const [openPath, setOpenPath] = useState<string | null>(null);
  const open = openPath === pathname;

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
    { name: t('nav.news'), href: '/news' },
    { name: t('nav.stats'), href: '/disputes' },
    { name: t('nav.pricing'), href: '/#pricing' },
  ];

  // On the auth pages the pill offers the opposite action instead of
  // duplicating the page itself.
  const accountHref = authed ? '/account' : pathname === '/login' ? '/register' : '/login';
  const accountLabel = authed
    ? t('nav.account')
    : pathname === '/login'
      ? t('reg.title')
      : t('nav.login');

  return (
    <header className="fixed inset-x-0 top-4 z-50 px-4">
      <div className="mx-auto flex max-w-page items-center justify-between gap-3">
        <Link href="/" className="flex shrink-0 items-baseline gap-1.5" onClick={() => setOpenPath(null)}>
          <span className="font-heading text-2xl italic leading-none text-white">Tax</span>
          <span className="font-heading text-2xl italic leading-none text-primary">Advisor</span>
        </Link>

        {/* Desktop: glass pill nav */}
        <nav className="liquid-glass hidden items-center gap-6 rounded-full px-6 py-2.5 lg:flex">
          {nav.map((item) => (
            <Link
              key={item.href}
              href={item.href}
              className="whitespace-nowrap text-sm font-medium text-white/80 transition-colors hover:text-white"
            >
              {item.name}
            </Link>
          ))}
        </nav>

        <div className="hidden items-center gap-4 lg:flex">
          <LangSwitch lang={lang} />
          <Link
            href={accountHref}
            className="whitespace-nowrap rounded-full bg-primary px-5 py-2 text-sm font-medium text-white transition-all duration-300 hover:bg-[#B91C1C]"
          >
            {accountLabel}
          </Link>
        </div>

        {/* Mobile: burger */}
        <button
          type="button"
          onClick={() => setOpenPath(open ? null : pathname)}
          aria-expanded={open}
          aria-label={t('nav.menu')}
          className="liquid-glass -mr-1 flex h-11 w-11 shrink-0 flex-col items-center justify-center gap-[5px] rounded-full lg:hidden"
        >
          <span
            className={`h-[1.5px] w-[18px] rounded-full bg-white transition-transform duration-200 ${
              open ? 'translate-y-[3.25px] rotate-45' : ''
            }`}
          />
          <span
            className={`h-[1.5px] w-[18px] rounded-full bg-white transition-transform duration-200 ${
              open ? '-translate-y-[3.25px] -rotate-45' : ''
            }`}
          />
        </button>
      </div>

      {/* Mobile panel */}
      <div
        className={`absolute inset-x-4 top-full mt-3 transition-all duration-200 lg:hidden ${
          open ? 'visible translate-y-0 opacity-100' : 'invisible -translate-y-2 opacity-0'
        }`}
      >
        <nav className="liquid-glass-strong rounded-2xl bg-black/80 px-6 pb-6 pt-2">
          {nav.map((item) => (
            <Link
              key={item.href}
              href={item.href}
              onClick={() => setOpenPath(null)}
              className="block border-b border-white/10 py-3.5 font-heading text-xl italic text-white last:border-0"
            >
              {item.name}
            </Link>
          ))}
          <div className="mt-5 flex items-center justify-between gap-4">
            <LangSwitch lang={lang} />
            <Link
              href={accountHref}
              onClick={() => setOpenPath(null)}
              className="inline-flex min-h-[44px] items-center whitespace-nowrap rounded-full bg-primary px-5 text-sm font-medium text-white transition-all duration-300 hover:bg-[#B91C1C]"
            >
              {accountLabel}
            </Link>
          </div>
        </nav>
      </div>
    </header>
  );
}
