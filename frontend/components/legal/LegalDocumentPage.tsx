'use client';

import Link from 'next/link';
import { ArrowUpRight, Building2, Mail, MapPin, Phone } from 'lucide-react';
import { LEGAL_CONTENT, LEGAL_NAV, LegalSlug, OPERATOR } from '@/lib/legal-content';
import { useT } from '@/lib/i18n';

const legalSlugs: LegalSlug[] = ['terms', 'refunds', 'privacy', 'delivery', 'contact'];

export function LegalDocumentPage({ slug }: { slug: LegalSlug }) {
  const { lang } = useT();
  const document = LEGAL_CONTENT[lang][slug];
  const interfaceCopy = {
    ru: { nav: 'Юридические документы', operator: 'Поставщик', contents: 'Содержание', sources: 'Официальные источники' },
    ka: { nav: 'იურიდიული დოკუმენტები', operator: 'მომსახურების მიმწოდებელი', contents: 'შინაარსი', sources: 'ოფიციალური წყაროები' },
    en: { nav: 'Legal documents', operator: 'Provider', contents: 'Contents', sources: 'Official sources' },
  }[lang];

  return (
    <main className="mx-auto min-h-[70vh] max-w-page px-6 pb-8 pt-10 sm:pt-16">
      <div className="grid gap-12 lg:grid-cols-[240px_minmax(0,1fr)] lg:gap-20">
        <aside className="min-w-0 lg:sticky lg:top-32 lg:self-start">
          <p className="text-xs font-medium text-primary">
            {interfaceCopy.nav}
          </p>
          <nav className="-mx-6 mt-4 flex w-[calc(100%+3rem)] max-w-[100vw] gap-2 overflow-x-auto px-6 pb-2 lg:mx-0 lg:block lg:w-auto lg:max-w-none lg:overflow-visible lg:border-l lg:border-white/15 lg:px-0 lg:pb-0" aria-label={interfaceCopy.nav}>
            {legalSlugs.map((item) => (
              <Link
                key={item}
                href={`/legal/${item}`}
                aria-current={slug === item ? 'page' : undefined}
                className={`block shrink-0 whitespace-nowrap rounded-full border px-4 py-2 text-xs leading-snug transition-colors lg:-ml-px lg:whitespace-normal lg:rounded-none lg:border-y-0 lg:border-r-0 lg:px-5 lg:py-2.5 lg:text-[13px] ${
                  slug === item
                    ? 'border-primary bg-primary/10 text-white'
                    : 'border-white/10 text-white/50 hover:border-white/25 hover:text-white lg:border-transparent'
                }`}
              >
                {LEGAL_NAV[lang][item]}
              </Link>
            ))}
          </nav>
          <div className="mt-9 hidden lg:block">
            <p className="text-xs text-white/40">{interfaceCopy.contents}</p>
            <div className="mt-3 space-y-2">
              {document.sections.map((section) => (
                <a key={section.id} href={`#${section.id}`} className="block text-xs leading-relaxed text-white/40 transition-colors hover:text-white/75">
                  {section.title}
                </a>
              ))}
            </div>
          </div>
        </aside>

        <article className="min-w-0">
          <header className="max-w-4xl">
            <p className="text-sm font-medium text-primary">{document.label}</p>
            <h1 className="mt-5 max-w-3xl font-heading text-4xl italic leading-[0.95] tracking-tight text-white sm:text-7xl">
              {document.title}
            </h1>
            <p className="mt-7 max-w-2xl text-[16px] font-light leading-7 text-white/65">{document.summary}</p>
            <p className="mt-4 text-xs text-white/40">{document.updated}</p>
          </header>

          <section className="liquid-glass mt-10 rounded-2xl p-6 sm:p-7" aria-label={interfaceCopy.operator}>
            <div className="grid gap-5 md:grid-cols-[1fr_1fr]">
              <div>
                <div className="flex items-center gap-2 text-sm font-semibold text-white">
                  <Building2 aria-hidden className="h-4 w-4 text-primary" />
                  {OPERATOR.legalName} · {OPERATOR.identificationCode}
                </div>
                <div className="mt-3 flex items-start gap-2 text-xs leading-relaxed text-white/55">
                  <MapPin aria-hidden className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                  {OPERATOR.address}
                </div>
              </div>
              <div className="grid gap-3 text-xs text-white/55 sm:grid-cols-2 md:grid-cols-1 xl:grid-cols-2">
                <a href={`mailto:${OPERATOR.email}`} className="flex items-center gap-2 transition-colors hover:text-white">
                  <Mail aria-hidden className="h-3.5 w-3.5" /> {OPERATOR.email}
                </a>
                <a href="tel:+995550052050" className="flex items-center gap-2 transition-colors hover:text-white">
                  <Phone aria-hidden className="h-3.5 w-3.5" /> {OPERATOR.phone}
                </a>
              </div>
            </div>
          </section>

          <div className="mt-14 max-w-3xl divide-y divide-white/10">
            {document.sections.map((section, index) => (
              <section key={section.id} id={section.id} className="scroll-mt-32 py-9 first:pt-0">
                <div className="grid gap-4 sm:grid-cols-[42px_1fr] sm:gap-6">
                  <span className="font-heading text-3xl italic text-primary/55">{String(index + 1).padStart(2, '0')}</span>
                  <div>
                    <h2 className="font-heading text-3xl italic leading-tight text-white">{section.title}</h2>
                    {section.body?.map((paragraph) => (
                      <p key={paragraph} className="mt-4 text-[15px] font-light leading-7 text-white/68">{paragraph}</p>
                    ))}
                    {section.bullets && (
                      <ul className="mt-5 space-y-3">
                        {section.bullets.map((item) => (
                          <li key={item} className="flex gap-3 text-[15px] font-light leading-7 text-white/68">
                            <span aria-hidden className="mt-[0.72rem] h-1.5 w-1.5 shrink-0 rounded-full bg-primary" />
                            <span>{item}</span>
                          </li>
                        ))}
                      </ul>
                    )}
                  </div>
                </div>
              </section>
            ))}
          </div>

          {document.sources && (
            <section className="mt-10 max-w-3xl border-t border-white/10 pt-8">
              <p className="text-xs font-medium text-white/45">{interfaceCopy.sources}</p>
              <div className="mt-4 flex flex-col gap-3">
                {document.sources.map((source) => (
                  <a key={source.href} href={source.href} target="_blank" rel="noopener noreferrer" className="inline-flex items-start gap-2 text-sm leading-relaxed text-primary transition-colors hover:text-white">
                    {source.label}<ArrowUpRight aria-hidden className="mt-1 h-3.5 w-3.5 shrink-0" />
                  </a>
                ))}
              </div>
            </section>
          )}
        </article>
      </div>
    </main>
  );
}
