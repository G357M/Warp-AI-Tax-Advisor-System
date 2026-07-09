'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { BrandMark } from '@/components/ui/BrandMark';
import { useT } from '@/lib/i18n';

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
    <footer className="border-t">
      <div className="mx-auto max-w-page px-6 py-12">
        <div className="grid gap-10 sm:grid-cols-[1fr_auto_auto] sm:gap-16">
          <div>
            <div className="flex items-center gap-2">
              <BrandMark className="h-[18px] w-[18px]" />
              <span className="text-sm font-semibold tracking-display">Tax Advisor</span>
            </div>
            <p className="mt-3 max-w-md text-[13px] leading-relaxed text-muted-foreground">
              {t('footer.disclaimer')}
            </p>
          </div>

          <nav aria-label={t('footer.sections')}>
            <div className="flex items-center gap-2 text-[13px] font-semibold">
              <span aria-hidden className="h-3 w-[3px] rounded-full bg-primary" />
              {t('footer.sections')}
            </div>
            <ul className="mt-3 space-y-2">
              {sections.map((s) => (
                <li key={s.href}>
                  <Link
                    href={s.href}
                    className="text-[13px] text-muted-foreground transition-colors hover:text-foreground"
                  >
                    {s.name}
                  </Link>
                </li>
              ))}
            </ul>
          </nav>

          <div>
            <div className="flex items-center gap-2 text-[13px] font-semibold">
              <span aria-hidden className="h-3 w-[3px] rounded-full bg-primary" />
              {t('footer.contact')}
            </div>
            <ul className="mt-3 space-y-2 text-[13px] text-muted-foreground">
              <li>
                <a href="mailto:info@tax-advisor.ge" className="transition-colors hover:text-foreground">
                  info@tax-advisor.ge
                </a>
              </li>
              <li>
                <a
                  href="https://infohub.rs.ge"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="transition-colors hover:text-foreground"
                >
                  {t('footer.source')}
                </a>
              </li>
              <li>
                <a
                  href="https://modern-consulting.ge"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="transition-colors hover:text-foreground"
                >
                  Modern Consulting
                </a>
              </li>
            </ul>
          </div>
        </div>

        <div className="mt-10 border-t pt-5 text-[13px] text-muted-foreground">
          © {new Date().getFullYear()} Tax Advisor
        </div>
      </div>
    </footer>
  );
}
