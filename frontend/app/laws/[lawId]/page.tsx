'use client';

import { useEffect, useMemo, useState } from 'react';
import { useParams } from 'next/navigation';
import Link from 'next/link';
import { SourceChip } from '@/components/ui/SourceChip';

interface AffectedArticle {
  article: string;
  action: 'amended' | 'added' | 'repealed';
  summary_ru?: string | null;
  old_norm?: string | null;
  new_norm?: string | null;
}

interface TimelineItem {
  id: string;
  adoption_date: string | null;
  effective_date: string | null;
  status: 'in_force' | 'not_yet' | 'unknown' | null;
  articles: AffectedArticle[];
  act_title: string;
  document_number: string | null;
  source_url: string;
}

interface Timeline {
  law_title: string;
  timeline: TimelineItem[];
}

const ACTION_LABELS: Record<string, string> = {
  amended: 'изменена',
  added: 'добавлена',
  repealed: 'отменена',
};

const STATUS_BADGE: Record<string, { label: string; className: string }> = {
  in_force: { label: 'действует', className: 'bg-success/10 text-success' },
  not_yet: { label: 'ещё не вступила', className: 'bg-secondary text-secondary-foreground' },
  unknown: { label: 'дата вступления не указана', className: 'bg-muted text-muted-foreground' },
};

function fmt(d: string | null): string {
  return d ? new Date(d).toLocaleDateString('ru-RU') : '—';
}

export default function LawTimelinePage() {
  const { lawId } = useParams<{ lawId: string }>();
  const [data, setData] = useState<Timeline | null>(null);
  const [error, setError] = useState(false);
  const [article, setArticle] = useState('');

  useEffect(() => {
    if (!lawId) return;
    fetch(`/api/v1/amendments/timeline?law_id=${lawId}`)
      .then((r) => (r.ok ? r.json() : Promise.reject()))
      .then(setData)
      .catch(() => setError(true));
  }, [lawId]);

  const items = useMemo(() => {
    if (!data) return [];
    if (!article.trim()) return data.timeline;
    return data.timeline.filter((t) =>
      t.articles.some((a) => a.article === article.trim()),
    );
  }, [data, article]);

  const years = useMemo(() => {
    const seen = new Set<string>();
    return items.map((item) => {
      const y = item.adoption_date ? String(new Date(item.adoption_date).getFullYear()) : '';
      const first = y && !seen.has(y);
      if (y) seen.add(y);
      return { item, yearMarker: first ? y : null };
    });
  }, [items]);

  return (
    <main className="mx-auto min-h-[70vh] max-w-3xl px-6 py-16">
      <Link href="/laws" className="text-[13px] text-muted-foreground hover:text-foreground">
        ← Все законы
      </Link>
      {error && (
        <p className="mt-8 text-[14px] text-muted-foreground">
          Не получилось загрузить таймлайн. Обновите страницу.
        </p>
      )}
      {!data && !error && <p className="mt-8 text-[14px] text-muted-foreground">Загружаю…</p>}
      {data && (
        <>
          <h1 className="mt-4 text-2xl font-semibold leading-snug tracking-display">
            {data.law_title}
          </h1>
          <div className="mt-4 flex flex-wrap items-center gap-3">
            <input
              value={article}
              onChange={(e) => setArticle(e.target.value)}
              placeholder="Фильтр по статье, напр. 165"
              aria-label="Фильтр по номеру статьи"
              className="h-10 w-56 rounded-full border bg-white px-4 text-[13px] placeholder:text-muted-foreground"
            />
            <span className="text-[13px] text-muted-foreground">
              {items.length} поправок{article.trim() ? ` к ст. ${article.trim()}` : ''}
            </span>
          </div>

          <ol className="relative mt-10 space-y-8 border-l pl-8">
            {years.map(({ item, yearMarker }) => (
              <li key={item.id} className="relative">
                <span
                  aria-hidden
                  className="absolute -left-[37px] top-1.5 h-2.5 w-2.5 rounded-full border-2 border-background bg-primary"
                />
                {yearMarker && (
                  <div className="mb-3 text-[13px] font-semibold text-muted-foreground">
                    {yearMarker}
                  </div>
                )}
                <div className="rounded-lg border bg-white p-5">
                  <div className="flex flex-wrap items-center gap-x-4 gap-y-1 text-[13px] text-muted-foreground">
                    <span>принята {fmt(item.adoption_date)}</span>
                    <span>вступила {fmt(item.effective_date)}</span>
                    {item.status && STATUS_BADGE[item.status] && (
                      <span
                        className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${STATUS_BADGE[item.status].className}`}
                      >
                        {STATUS_BADGE[item.status].label}
                      </span>
                    )}
                  </div>

                  {item.articles.length > 0 && (
                    <ul className="mt-4 space-y-3">
                      {item.articles.map((a, i) => (
                        <li key={i} className="text-[14px] leading-relaxed">
                          <span className="font-semibold">ст. {a.article}</span>{' '}
                          <span className="text-muted-foreground">
                            {ACTION_LABELS[a.action] ?? a.action}
                          </span>
                          {a.summary_ru && <> — {a.summary_ru}</>}
                          {(a.old_norm || a.new_norm) && (
                            <div className="mt-1.5 grid gap-1.5 text-[13px] sm:grid-cols-2">
                              {a.old_norm && (
                                <div className="rounded-md bg-muted px-3 py-2 text-muted-foreground">
                                  <span className="font-medium">Было:</span> {a.old_norm}
                                </div>
                              )}
                              {a.new_norm && (
                                <div className="rounded-md bg-secondary px-3 py-2 text-secondary-foreground">
                                  <span className="font-medium">Стало:</span> {a.new_norm}
                                </div>
                              )}
                            </div>
                          )}
                        </li>
                      ))}
                    </ul>
                  )}

                  <div className="mt-4">
                    <SourceChip
                      title={item.act_title}
                      documentType="law"
                      url={item.source_url}
                    />
                  </div>
                </div>
              </li>
            ))}
          </ol>
          {items.length === 0 && (
            <p className="mt-8 text-[14px] text-muted-foreground">
              {article.trim()
                ? `Поправок к статье ${article.trim()} в базе не найдено.`
                : 'Поправки к этому закону ещё обрабатываются.'}
            </p>
          )}
        </>
      )}
    </main>
  );
}
