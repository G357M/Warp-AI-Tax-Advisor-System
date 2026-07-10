'use client';

import { useEffect, useRef, useState } from 'react';
import { SectionTitle } from '@/components/ui/SectionTitle';
import { DATE_LOCALES, useT } from '@/lib/i18n';

const SUBTYPES = [
  'treaty',
  'loss_norms',
  'dispute_decisions',
  'guidance',
  'legislation',
  'orders_resolutions',
  'general',
] as const;

type Subtype = (typeof SUBTYPES)[number];

interface NewsItem {
  id: string;
  title: string;
  subtype: Subtype;
  document_number: string | null;
  date_published: string | null;
  source_url: string;
}

interface NewsResponse {
  total: number;
  counts: Record<Subtype, number>;
  items: NewsItem[];
}

const PAGE = 30;

export default function NewsPage() {
  const { t, lang } = useT();
  const [data, setData] = useState<NewsResponse | null>(null);
  const [items, setItems] = useState<NewsItem[]>([]);
  const [subtype, setSubtype] = useState<Subtype | null>(null);
  const [search, setSearch] = useState('');
  const [query, setQuery] = useState('');
  const [error, setError] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const requestSeq = useRef(0);

  useEffect(() => {
    const id = setTimeout(() => setQuery(search.trim()), 300);
    return () => clearTimeout(id);
  }, [search]);

  useEffect(() => {
    const seq = ++requestSeq.current;
    setError(false);
    const params = new URLSearchParams({ limit: String(PAGE) });
    if (subtype) params.set('subtype', subtype);
    if (query) params.set('search', query);
    fetch(`/api/v1/news?${params}`)
      .then((r) => (r.ok ? r.json() : Promise.reject()))
      .then((payload: NewsResponse) => {
        if (seq !== requestSeq.current) return;
        setData(payload);
        setItems(payload.items);
      })
      .catch(() => {
        if (seq === requestSeq.current) setError(true);
      });
  }, [subtype, query]);

  const loadMore = () => {
    setLoadingMore(true);
    const params = new URLSearchParams({ limit: String(PAGE), offset: String(items.length) });
    if (subtype) params.set('subtype', subtype);
    if (query) params.set('search', query);
    fetch(`/api/v1/news?${params}`)
      .then((r) => (r.ok ? r.json() : Promise.reject()))
      .then((payload: NewsResponse) => setItems((prev) => [...prev, ...payload.items]))
      .catch(() => setError(true))
      .finally(() => setLoadingMore(false));
  };

  const allTotal = data ? Object.values(data.counts).reduce((a, b) => a + b, 0) : 0;
  const remaining = data ? data.total - items.length : 0;

  const fmtDate = (iso: string | null) =>
    iso
      ? new Date(iso).toLocaleDateString(DATE_LOCALES[lang], {
          day: 'numeric',
          month: 'short',
          year: 'numeric',
        })
      : null;

  return (
    <main className="mx-auto min-h-[70vh] max-w-page px-6 py-16">
      <SectionTitle as="h1" className="text-3xl font-semibold tracking-display">
        {t('news.title')}
      </SectionTitle>
      <p className="mt-3 max-w-2xl text-[15px] leading-relaxed text-muted-foreground">
        {t('news.sub')}
      </p>

      <div className="mt-6 flex flex-wrap items-center gap-3">
        <input
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          placeholder={t('news.search')}
          aria-label={t('news.search')}
          className="h-11 w-full max-w-md rounded-full border border-white/15 bg-white/5 px-5 text-[14px] text-white placeholder:text-white/50"
        />
      </div>

      <div className="mt-4 flex flex-wrap gap-1.5">
        <button
          onClick={() => setSubtype(null)}
          className={`rounded-full border px-4 py-1.5 text-[13px] transition-colors ${
            subtype === null
              ? 'border-primary bg-primary text-white'
              : 'text-muted-foreground hover:text-foreground'
          }`}
        >
          {t('news.all')}
          {data && <span className="ml-1.5 opacity-70">{allTotal}</span>}
        </button>
        {SUBTYPES.map((s) => {
          const n = data?.counts[s] ?? 0;
          if (data && n === 0) return null;
          return (
            <button
              key={s}
              onClick={() => setSubtype(s === subtype ? null : s)}
              className={`rounded-full border px-4 py-1.5 text-[13px] transition-colors ${
                subtype === s
                  ? 'border-primary bg-primary text-white'
                  : 'text-muted-foreground hover:text-foreground'
              }`}
            >
              {t(`news.cat.${s}`)}
              {data && <span className="ml-1.5 opacity-70">{n}</span>}
            </button>
          );
        })}
      </div>

      {error && <p className="mt-10 text-[14px] text-muted-foreground">{t('laws.error')}</p>}
      {!data && !error && (
        <p className="mt-10 text-[14px] text-muted-foreground">{t('laws.loading')}</p>
      )}

      {data && items.length > 0 && (
        <div className="mt-8 divide-y divide-white/10 rounded-2xl border border-white/10 bg-white/[0.03]">
          {items.map((item) => (
            <a
              key={item.id}
              href={item.source_url}
              target="_blank"
              rel="noopener noreferrer"
              className="flex items-center justify-between gap-4 px-5 py-4 transition-colors hover:bg-muted"
            >
              <span className="min-w-0">
                <span className="block text-[15px] font-medium leading-snug [display:-webkit-box] [-webkit-box-orient:vertical] [-webkit-line-clamp:2] overflow-hidden">
                  {item.title}
                </span>
                <span className="mt-0.5 block text-[13px] text-muted-foreground">
                  {fmtDate(item.date_published)}
                </span>
              </span>
              <span className="shrink-0 rounded-full bg-secondary px-3 py-1 text-[13px] font-medium text-secondary-foreground">
                {t(`news.cat.${item.subtype}`)}
              </span>
            </a>
          ))}
        </div>
      )}

      {data && items.length === 0 && (
        <p className="mt-10 text-[14px] text-muted-foreground">{t('laws.nomatch')}</p>
      )}

      {data && remaining > 0 && (
        <div className="mt-6 flex justify-center">
          <button
            onClick={loadMore}
            disabled={loadingMore}
            className="rounded-full border border-white/15 px-6 py-2.5 text-[14px] text-muted-foreground transition-colors hover:text-foreground disabled:opacity-50"
          >
            {loadingMore ? t('laws.loading') : t('news.showmore', { n: Math.min(remaining, PAGE) })}
          </button>
        </div>
      )}
    </main>
  );
}
