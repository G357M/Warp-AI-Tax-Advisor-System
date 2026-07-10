'use client';

import { DATE_LOCALES, useT } from '@/lib/i18n';
import { BODY_ORDER, DisputeFilter, OutcomeRow, gel, pct } from './shared';
import { StackedBar } from './StackedBar';

export interface ArticleRow extends OutcomeRow {
  article: string;
  amount: { n: number; sum: number | null; median: number | null };
  by_body: Record<string, number>;
}

export function ArticleTable({
  items,
  onDrill,
}: {
  items: ArticleRow[];
  onDrill: (filter: DisputeFilter) => void;
}) {
  const { t, lang } = useT();
  const locale = DATE_LOCALES[lang];

  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[640px] border-collapse text-[13px]">
        <thead>
          <tr className="text-left text-white/60">
            <th className="px-3 py-2 font-normal">{t('disputes.table.article')}</th>
            <th className="px-3 py-2 font-normal">{t('disputes.table.decisions')}</th>
            <th className="w-[34%] px-3 py-2 font-normal">{t('disputes.table.split')}</th>
            <th className="px-3 py-2 text-right font-normal">{t('disputes.table.relief')}</th>
            <th className="px-3 py-2 text-right font-normal">{t('disputes.table.median')}</th>
            <th className="px-3 py-2 text-right font-normal">{t('disputes.table.instances')}</th>
          </tr>
        </thead>
        <tbody>
          {items.map((r) => (
            <tr key={r.article} className="border-t border-white/10 transition-colors hover:bg-white/5">
              <td className="px-3 py-2.5">
                <button
                  type="button"
                  onClick={() => onDrill({ article: r.article })}
                  className="font-heading text-lg italic text-white transition-colors hover:text-primary"
                >
                  {t('stats.art', { n: r.article })}
                </button>
              </td>
              <td className="px-3 py-2.5 text-white/80">{r.total}</td>
              <td className="px-3 py-2.5">
                <StackedBar
                  row={r}
                  onSegment={(outcome) => onDrill({ article: r.article, outcome })}
                />
              </td>
              <td className="px-3 py-2.5 text-right text-white/80">{pct(r.taxpayer_relief_rate)}</td>
              <td className="px-3 py-2.5 text-right text-white/80">
                {r.amount.n > 0 ? gel(r.amount.median, locale) : '—'}
              </td>
              <td className="px-3 py-2.5">
                <span className="flex justify-end gap-1" title={BODY_ORDER
                  .filter((b) => r.by_body[b] > 0)
                  .map((b) => `${t(`disputes.body.${b}`)}: ${r.by_body[b]}`)
                  .join(' · ')}>
                  {BODY_ORDER.map((b) => (
                    <span
                      key={b}
                      className={`h-2 w-2 rounded-full ${
                        r.by_body[b] > 0 ? 'bg-primary' : 'bg-white/15'
                      }`}
                    />
                  ))}
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
