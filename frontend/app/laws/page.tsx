'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { SectionTitle } from '@/components/ui/SectionTitle';
import { useT, DATE_LOCALES } from '@/lib/i18n';

interface AmendedLaw {
  law_id: string;
  title: string;
  amendments: number;
  last_adoption: string | null;
}

export default function LawsPage() {
  const { lang, t } = useT();
  const [laws, setLaws] = useState<AmendedLaw[] | null>(null);
  const [error, setError] = useState(false);
  const [filter, setFilter] = useState('');
  const [expanded, setExpanded] = useState(false);

  useEffect(() => {
    fetch('/api/v1/amendments/laws')
      .then((r) => (r.ok ? r.json() : Promise.reject()))
      .then((d) => setLaws(d.laws))
      .catch(() => setError(true));
  }, []);

  const locale = DATE_LOCALES[lang];
  const featured = (laws ?? []).slice(0, 4);
  const matched = (laws ?? []).filter((l) =>
    l.title.toLowerCase().includes(filter.toLowerCase()),
  );
  // The full catalog is ~150 rows; collapse it until asked. Search always
  // runs over everything.
  const PAGE = 30;
  const shown = filter.trim() || expanded ? matched : matched.slice(0, PAGE);
  const hidden = matched.length - shown.length;

  return (
    <main className="mx-auto min-h-[70vh] max-w-page px-6 py-16">
      <SectionTitle as="h1" className="text-3xl font-semibold tracking-display">
        {t('laws.title')}
      </SectionTitle>
      <p className="mt-3 max-w-2xl text-[15px] leading-relaxed text-muted-foreground">
        {t('laws.sub')}
      </p>

      {/* Most frequently amended acts */}
      {featured.length > 0 && !filter.trim() && (
        <section className="mt-10">
          <h2 className="text-[13px] font-medium uppercase tracking-wide text-muted-foreground">
            {t('laws.featured')}
          </h2>
          <div className="mt-3 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {featured.map((law) => (
              <Link
                key={law.law_id}
                href={`/laws/${law.law_id}`}
                className="flex flex-col justify-between rounded-lg border bg-white p-5 transition-colors hover:border-primary/40"
                title={law.title}
              >
                <span className="text-[14px] font-medium leading-snug [display:-webkit-box] [-webkit-line-clamp:3] [-webkit-box-orient:vertical] overflow-hidden">
                  {law.title}
                </span>
                <span className="mt-4 flex items-baseline gap-2">
                  <span className="text-[26px] font-semibold leading-none tracking-display text-primary">
                    {law.amendments}
                  </span>
                  <span className="text-xs text-muted-foreground">
                    {t('laws.amendments', { n: '' }).replace(/\s+/g, ' ').trim()}
                  </span>
                </span>
              </Link>
            ))}
          </div>
        </section>
      )}

      <input
        value={filter}
        onChange={(e) => setFilter(e.target.value)}
        placeholder={t('laws.search')}
        aria-label={t('laws.search')}
        className="mt-10 h-11 w-full max-w-md rounded-full border bg-white px-5 text-[14px] placeholder:text-muted-foreground"
      />

      {error && <p className="mt-10 text-[14px] text-muted-foreground">{t('laws.error')}</p>}
      {!laws && !error && <p className="mt-10 text-[14px] text-muted-foreground">{t('laws.loading')}</p>}

      <div className="mt-6 divide-y rounded-lg border bg-white">
        {shown.map((law) => (
          <Link
            key={law.law_id}
            href={`/laws/${law.law_id}`}
            className="flex items-center justify-between gap-4 px-5 py-4 transition-colors hover:bg-muted"
            title={law.title}
          >
            <span className="min-w-0">
              <span className="block truncate text-[15px] font-medium">{law.title}</span>
              {law.last_adoption && (
                <span className="block text-[13px] text-muted-foreground">
                  {t('laws.last', { d: new Date(law.last_adoption).toLocaleDateString(locale) })}
                </span>
              )}
            </span>
            <span className="shrink-0 rounded-full bg-secondary px-3 py-1 text-[13px] font-medium text-secondary-foreground">
              {law.amendments}
            </span>
          </Link>
        ))}
        {laws && shown.length === 0 && (
          <p className="px-5 py-6 text-[14px] text-muted-foreground">
            {laws.length === 0 ? t('laws.empty') : t('laws.nomatch')}
          </p>
        )}
      </div>

      {hidden > 0 && (
        <div className="mt-6 flex justify-center">
          <button
            onClick={() => setExpanded(true)}
            className="rounded-full border px-6 py-2 text-[14px] text-muted-foreground transition-colors hover:border-primary/40 hover:text-foreground"
          >
            {t('laws.showmore', { n: hidden })}
          </button>
        </div>
      )}
    </main>
  );
}
