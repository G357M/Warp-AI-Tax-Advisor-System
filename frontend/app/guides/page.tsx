'use client';

import { useCallback, useEffect, useState } from 'react';
import { useT, DATE_LOCALES } from '@/lib/i18n';

interface Guide {
  id: string;
  title: string;
  number: string | null;
  date_published: string | null;
  source_url: string;
}

const PAGE_SIZE = 50;

export default function GuidesPage() {
  const { lang, t } = useT();
  const [items, setItems] = useState<Guide[]>([]);
  const [total, setTotal] = useState(0);
  const [search, setSearch] = useState('');
  const [page, setPage] = useState(0);
  const [error, setError] = useState(false);
  const [loading, setLoading] = useState(true);

  const load = useCallback(() => {
    setLoading(true);
    const params = new URLSearchParams({
      limit: String(PAGE_SIZE),
      offset: String(page * PAGE_SIZE),
    });
    if (search.trim()) params.set('search', search.trim());
    fetch(`/api/v1/guides?${params}`)
      .then((r) => (r.ok ? r.json() : Promise.reject()))
      .then((d) => {
        setItems(d.items);
        setTotal(d.total);
      })
      .catch(() => setError(true))
      .finally(() => setLoading(false));
  }, [search, page]);

  useEffect(load, [load]);
  useEffect(() => setPage(0), [search]);

  const locale = DATE_LOCALES[lang];
  const pages = Math.max(Math.ceil(total / PAGE_SIZE), 1);

  return (
    <main className="mx-auto min-h-[70vh] max-w-page px-6 py-16">
      <h1 className="text-3xl font-semibold tracking-display">{t('guides.title')}</h1>
      <p className="mt-3 max-w-2xl text-[15px] leading-relaxed text-muted-foreground">
        {t('guides.sub')}
      </p>

      <div className="mt-8 flex flex-wrap items-center gap-3">
        <input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder={t('guides.search')}
          aria-label={t('guides.search')}
          className="h-11 w-full max-w-md rounded-full border bg-white px-5 text-[14px] placeholder:text-muted-foreground"
        />
        <span className="text-[13px] text-muted-foreground">
          {t('guides.total', { n: total.toLocaleString(locale) })}
        </span>
      </div>

      {error && <p className="mt-10 text-[14px] text-muted-foreground">{t('laws.error')}</p>}
      {loading && !error && <p className="mt-10 text-[14px] text-muted-foreground">{t('laws.loading')}</p>}

      {!loading && (
        <div className="mt-6 divide-y rounded-lg border bg-white">
          {items.map((g) => (
            <a
              key={g.id}
              href={g.source_url}
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center justify-between gap-4 px-5 py-4 transition-colors hover:bg-muted"
            >
              <span className="min-w-0">
                <span className="block text-[15px] font-medium leading-snug [display:-webkit-box] [-webkit-line-clamp:2] [-webkit-box-orient:vertical] overflow-hidden">
                  {g.title}
                </span>
                {g.date_published && (
                  <span className="block text-[13px] text-muted-foreground">
                    {new Date(g.date_published).toLocaleDateString(locale)}
                  </span>
                )}
              </span>
              {g.number && (
                <span className="shrink-0 rounded-full bg-secondary px-3 py-1 text-[13px] font-medium text-secondary-foreground">
                  N {g.number}
                </span>
              )}
            </a>
          ))}
          {items.length === 0 && (
            <p className="px-5 py-6 text-[14px] text-muted-foreground">{t('laws.nomatch')}</p>
          )}
        </div>
      )}

      {pages > 1 && (
        <div className="mt-6 flex items-center gap-4">
          <button
            onClick={() => setPage((p) => Math.max(p - 1, 0))}
            disabled={page === 0}
            className="rounded-full border px-4 py-1.5 text-[13px] text-muted-foreground transition-colors hover:text-foreground disabled:opacity-40"
          >
            ←
          </button>
          <span className="text-[13px] text-muted-foreground">
            {page + 1} / {pages.toLocaleString(locale)}
          </span>
          <button
            onClick={() => setPage((p) => Math.min(p + 1, pages - 1))}
            disabled={page >= pages - 1}
            className="rounded-full border px-4 py-1.5 text-[13px] text-muted-foreground transition-colors hover:text-foreground disabled:opacity-40"
          >
            →
          </button>
        </div>
      )}
    </main>
  );
}
