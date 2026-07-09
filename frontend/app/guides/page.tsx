'use client';

import { useEffect, useMemo, useState } from 'react';
import { SectionTitle } from '@/components/ui/SectionTitle';
import { useT } from '@/lib/i18n';

interface RegistryItem {
  number: string;
  title: string;
  status: 'active' | 'withdrawn';
  date: string | null;
  old_edition: string | null;
  doc_url: string | null;
}

interface RegistrySection {
  code: string;
  name: string;
  items: RegistryItem[];
}

interface Registry {
  published: string | null;
  source_url: string;
  total: number;
  active: number;
  withdrawn: number;
  sections: RegistrySection[];
}

type StatusFilter = 'all' | 'active' | 'withdrawn';

export default function GuidesPage() {
  const { t } = useT();
  const [registry, setRegistry] = useState<Registry | null>(null);
  const [search, setSearch] = useState('');
  const [filter, setFilter] = useState<StatusFilter>('all');
  const [error, setError] = useState(false);

  useEffect(() => {
    fetch('/api/v1/guides/registry')
      .then((r) => (r.ok ? r.json() : Promise.reject()))
      .then(setRegistry)
      .catch(() => setError(true));
  }, []);

  const sections = useMemo(() => {
    if (!registry) return [];
    const q = search.trim().toLowerCase();
    return registry.sections
      .map((s) => ({
        ...s,
        items: s.items.filter(
          (i) =>
            (filter === 'all' || i.status === filter) &&
            (!q || i.title.toLowerCase().includes(q) || i.number.includes(q))
        ),
      }))
      .filter((s) => s.items.length > 0);
  }, [registry, search, filter]);

  const shown = sections.reduce((n, s) => n + s.items.length, 0);

  return (
    <main className="mx-auto min-h-[70vh] max-w-page px-6 py-16">
      <SectionTitle as="h1" className="text-3xl font-semibold tracking-display">
        {t('guides.title')}
      </SectionTitle>
      <p className="mt-3 max-w-2xl text-[15px] leading-relaxed text-muted-foreground">
        {t('guides.sub')}
      </p>

      {registry && (
        <div className="mt-6 flex flex-wrap items-center gap-x-5 gap-y-2 text-[13px] text-muted-foreground">
          <span>{t('guides.total', { n: registry.total })}</span>
          <span className="inline-flex items-center gap-1.5">
            <span className="h-2 w-2 rounded-full bg-emerald-500" />
            {t('guides.active_n', { n: registry.active })}
          </span>
          <span className="inline-flex items-center gap-1.5">
            <span className="h-2 w-2 rounded-full bg-muted-foreground/50" />
            {t('guides.withdrawn_n', { n: registry.withdrawn })}
          </span>
          <a
            href={registry.source_url}
            target="_blank"
            rel="noopener noreferrer"
            className="text-primary hover:underline"
          >
            {t('guides.registry_src')} ↗
          </a>
        </div>
      )}

      <div className="mt-6 flex flex-wrap items-center gap-3">
        <input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder={t('guides.search')}
          aria-label={t('guides.search')}
          className="h-11 w-full max-w-md rounded-full border border-white/15 bg-white/5 px-5 text-[14px] text-white placeholder:text-white/50"
        />
        <div className="flex gap-1.5">
          {(['all', 'active', 'withdrawn'] as StatusFilter[]).map((f) => (
            <button
              key={f}
              onClick={() => setFilter(f)}
              className={`rounded-full border px-4 py-1.5 text-[13px] transition-colors ${
                filter === f
                  ? 'border-primary bg-primary text-white'
                  : 'text-muted-foreground hover:text-foreground'
              }`}
            >
              {t(f === 'all' ? 'guides.filter_all' : f === 'active' ? 'guides.active' : 'guides.withdrawn')}
            </button>
          ))}
        </div>
      </div>

      {error && <p className="mt-10 text-[14px] text-muted-foreground">{t('laws.error')}</p>}
      {!registry && !error && (
        <p className="mt-10 text-[14px] text-muted-foreground">{t('laws.loading')}</p>
      )}

      {registry &&
        sections.map((section) => (
          <section key={section.code} className="mt-10">
            <h2 className="flex items-baseline gap-2 text-[17px] font-semibold tracking-display">
              <span className="text-muted-foreground">{section.code}</span>
              {section.name}
            </h2>
            <div className="mt-3 divide-y divide-white/10 rounded-2xl border border-white/10 bg-white/[0.03]">
              {section.items.map((g) => {
                const inner = (
                  <>
                    <span className="min-w-0">
                      <span
                        className={`block text-[15px] font-medium leading-snug ${
                          g.status === 'withdrawn' ? 'text-muted-foreground' : ''
                        }`}
                      >
                        {g.title}
                      </span>
                      <span className="mt-0.5 block text-[13px] text-muted-foreground">
                        {g.status === 'active' ? (
                          <span className="text-emerald-600">
                            {t('guides.active')}
                            {g.date && ` · ${t('guides.edition', { d: g.date })}`}
                          </span>
                        ) : (
                          <span>{g.date ? t('guides.withdrawn_on', { d: g.date }) : t('guides.withdrawn')}</span>
                        )}
                      </span>
                    </span>
                    <span className="shrink-0 rounded-full bg-secondary px-3 py-1 text-[13px] font-medium text-secondary-foreground">
                      N {g.number}
                    </span>
                  </>
                );
                const cls =
                  'flex items-center justify-between gap-4 px-5 py-4 transition-colors hover:bg-muted';
                return g.doc_url ? (
                  <a
                    key={g.number}
                    href={g.doc_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className={cls}
                  >
                    {inner}
                  </a>
                ) : (
                  <div key={g.number} className={cls}>
                    {inner}
                  </div>
                );
              })}
            </div>
          </section>
        ))}

      {registry && shown === 0 && (
        <p className="mt-10 text-[14px] text-muted-foreground">{t('laws.nomatch')}</p>
      )}
    </main>
  );
}
