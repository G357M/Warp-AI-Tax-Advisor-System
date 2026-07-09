'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useT } from '@/lib/i18n';

const ECOSYSTEM = [
  { name: 'Modern Consulting', href: 'https://modern-consulting.ge' },
  { name: 'ModernAsk', href: 'https://modernask.com' },
  { name: 'TaxMate', href: null },
  { name: 'ModernBot', href: null },
  { name: 'Modern Travel', href: 'https://modern-travel.ge' },
];

export function SiteFooter() {
  const pathname = usePathname();
  const { t } = useT();
  if (pathname?.startsWith('/admin')) return null;

  const sections = [
    { name: t('nav.chat'), href: '/#chat' },
    { name: t('nav.laws'), href: '/laws' },
    { name: t('nav.guides'), href: '/guides' },
    { name: t('nav.stats'), href: '/#stats' },
    { name: t('nav.pricing'), href: '/#pricing' },
  ];

  return (
    <footer className="mt-32 border-t border-white/10">
      <div className="mx-auto max-w-page px-6 py-12">
        <div className="grid gap-10 sm:grid-cols-[1fr_auto_auto] sm:gap-16">
          <div>
            <div className="flex items-baseline gap-1.5">
              <span className="font-heading text-xl italic text-white">Tax</span>
              <span className="font-heading text-xl italic text-primary">Advisor</span>
            </div>
            <p className="mt-3 max-w-md text-[13px] font-light leading-relaxed text-white/50">
              {t('footer.disclaimer')}
            </p>
          </div>

          <nav aria-label={t('footer.sections')}>
            <div className="flex items-center gap-2 text-[13px] font-semibold text-white">
              <span aria-hidden className="h-3 w-[3px] rounded-full bg-primary" />
              {t('footer.sections')}
            </div>
            <ul className="mt-3 space-y-2">
              {sections.map((s) => (
                <li key={s.href}>
                  <Link
                    href={s.href}
                    className="text-[13px] font-light text-white/50 transition-colors hover:text-white"
                  >
                    {s.name}
                  </Link>
                </li>
              ))}
            </ul>
          </nav>

          <div>
            <div className="flex items-center gap-2 text-[13px] font-semibold text-white">
              <span aria-hidden className="h-3 w-[3px] rounded-full bg-primary" />
              {t('footer.contact')}
            </div>
            <ul className="mt-3 space-y-2 text-[13px] font-light text-white/50">
              <li>
                <a href="mailto:info@tax-advisor.ge" className="transition-colors hover:text-white">
                  info@tax-advisor.ge
                </a>
              </li>
              <li>
                <a
                  href="https://infohub.rs.ge"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="transition-colors hover:text-white"
                >
                  {t('footer.source')}
                </a>
              </li>
            </ul>
          </div>
        </div>

        <div className="mt-12 flex flex-col items-start justify-between gap-4 border-t border-white/10 pt-6 sm:flex-row sm:items-center">
          <div className="text-[13px] font-light text-white/40">
            © {new Date().getFullYear()} Tax Advisor — {t('footer.ecosystem')}
          </div>
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs font-light text-white/40">
            {ECOSYSTEM.map((p, i) => (
              <span key={p.name} className="flex items-center gap-3">
                {i > 0 && <span aria-hidden>·</span>}
                {p.href ? (
                  <a
                    href={p.href}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="transition-colors hover:text-white"
                  >
                    {p.name}
                  </a>
                ) : (
                  <span>{p.name}</span>
                )}
              </span>
            ))}
          </div>
        </div>
      </div>
    </footer>
  );
}
