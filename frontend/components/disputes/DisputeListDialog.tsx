'use client';

import { useEffect, useState } from 'react';
import { GlassDialog } from '@/components/ui/Dialog';
import { DATE_LOCALES, useT } from '@/lib/i18n';
import { DisputeFilter, OUTCOME_META, gel } from './shared';

interface DisputeItem {
  facts_id: string;
  title: string;
  decision_number: string | null;
  decision_date: string | null;
  authority_body: string | null;
  contested_articles: string[];
  amount_gel: number | null;
  outcome: string | null;
  source_url: string;
}

interface ListResponse {
  total: number;
  items: DisputeItem[];
}

const PAGE = 25;

const OUTCOME_COLOR: Record<string, string> = Object.fromEntries(
  OUTCOME_META.map(({ key, color }) => [key, color])
);

function filterParams(filter: DisputeFilter, offset: number): URLSearchParams {
  const params = new URLSearchParams({ limit: String(PAGE), offset: String(offset) });
  if (filter.article) params.set('article', filter.article);
  if (filter.body) params.set('body', filter.body);
  if (filter.outcome) params.set('outcome', filter.outcome);
  if (filter.year) params.set('year', String(filter.year));
  if (filter.has_amount) params.set('has_amount', 'true');
  return params;
}

/** Drill-down modal: the individual disputes behind a clicked stat. */
export function DisputeListDialog({
  filter,
  onClose,
}: {
  filter: DisputeFilter | null;
  onClose: () => void;
}) {
  if (!filter) return null;

  return (
    <DisputeListDialogContent
      key={JSON.stringify(filter)}
      filter={filter}
      onClose={onClose}
    />
  );
}

function DisputeListDialogContent({
  filter,
  onClose,
}: {
  filter: DisputeFilter;
  onClose: () => void;
}) {
  const { t, lang } = useT();
  const locale = DATE_LOCALES[lang];
  const [data, setData] = useState<ListResponse | null>(null);
  const [items, setItems] = useState<DisputeItem[]>([]);
  const [error, setError] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);

  useEffect(() => {
    const controller = new AbortController();
    fetch(`/api/v1/analytics/decisions/list?${filterParams(filter, 0)}`, {
      signal: controller.signal,
    })
      .then((r) => (r.ok ? r.json() : Promise.reject()))
      .then((payload: ListResponse) => {
        setData(payload);
        setItems(payload.items);
      })
      .catch(() => {
        if (!controller.signal.aborted) setError(true);
      });
    return () => controller.abort();
  }, [filter]);

  const loadMore = () => {
    setError(false);
    setLoadingMore(true);
    fetch(`/api/v1/analytics/decisions/list?${filterParams(filter, items.length)}`)
      .then((r) => (r.ok ? r.json() : Promise.reject()))
      .then((payload: ListResponse) => setItems((prev) => [...prev, ...payload.items]))
      .catch(() => setError(true))
      .finally(() => setLoadingMore(false));
  };

  const filterChips: string[] = [];
  if (filter.article) filterChips.push(t('stats.art', { n: filter.article }));
  if (filter.body) filterChips.push(t(`disputes.body.${filter.body}`));
  if (filter.outcome) filterChips.push(t(`disputes.outcome.${filter.outcome}`));
  if (filter.year) filterChips.push(String(filter.year));
  if (filter.has_amount) filterChips.push(t('disputes.with_amount'));

  return (
    <GlassDialog
      open
      onOpenChange={(open) => !open && onClose()}
      closeLabel={t('disputes.dialog.close')}
      title={
        <span className="flex flex-wrap items-center gap-2">
          {t('disputes.dialog.title', { n: data?.total ?? '…' })}
          {filterChips.map((chip) => (
            <span
              key={chip}
              className="rounded-full border border-white/15 bg-white/5 px-2.5 py-0.5 font-body text-[12px] not-italic text-white/70"
            >
              {chip}
            </span>
          ))}
        </span>
      }
    >
      {error && <p className="py-6 text-[14px] text-white/60">{t('laws.error')}</p>}
      {!data && !error && <p className="py-6 text-[14px] text-white/60">{t('laws.loading')}</p>}
      {data && items.length === 0 && (
        <p className="py-6 text-[14px] text-white/60">{t('disputes.dialog.empty')}</p>
      )}

      <div className="divide-y divide-white/10">
        {items.map((item) => (
          <a
            key={item.facts_id}
            href={item.source_url}
            target="_blank"
            rel="noopener noreferrer"
            className="block py-3.5 transition-colors hover:bg-white/5"
          >
            <span className="flex flex-wrap items-center gap-x-3 gap-y-1 text-[12px] text-white/60">
              {item.decision_date && (
                <span>{new Date(item.decision_date).toLocaleDateString(locale)}</span>
              )}
              {item.authority_body && (
                <span className="rounded-full bg-secondary px-2.5 py-0.5 text-secondary-foreground">
                  {t(`disputes.body.${item.authority_body}`)}
                </span>
              )}
              {item.contested_articles.map((a) => (
                <span key={a} className="text-white/70">{t('stats.art', { n: a })}</span>
              ))}
              {item.amount_gel != null && (
                <span className="text-white/80">{gel(item.amount_gel, locale)}</span>
              )}
              {item.outcome && (
                <span className="inline-flex items-center gap-1.5">
                  <span
                    className="inline-block h-2 w-2 rounded-full"
                    style={{ background: OUTCOME_COLOR[item.outcome] ?? 'rgba(255,255,255,0.3)' }}
                  />
                  {t(`disputes.outcome.${item.outcome}`)}
                </span>
              )}
            </span>
            <span className="mt-1 block text-[14px] font-medium leading-snug text-white/90 [display:-webkit-box] [-webkit-box-orient:vertical] [-webkit-line-clamp:2] overflow-hidden">
              {item.title} ↗
            </span>
          </a>
        ))}
      </div>

      {data && items.length < data.total && (
        <div className="flex justify-center py-4">
          <button
            type="button"
            onClick={loadMore}
            disabled={loadingMore}
            className="rounded-full border border-white/15 px-5 py-2 text-[13px] text-white/70 transition-colors hover:text-white disabled:opacity-50"
          >
            {loadingMore ? t('laws.loading') : t('disputes.dialog.more')}
          </button>
        </div>
      )}
    </GlassDialog>
  );
}
