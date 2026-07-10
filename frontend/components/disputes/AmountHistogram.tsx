'use client';

import { DATE_LOCALES, useT } from '@/lib/i18n';
import { gel } from './shared';

export interface AmountsData {
  coverage: { total: number; with_amount: number; share: number | null };
  overall: { sum: number | null; avg: number | null; median: number | null; p90: number | null };
  buckets: { label: string; count: number }[];
}

const MIN_WITH_AMOUNT = 100; // below this, a histogram would mislead

export function AmountHistogram({
  data,
  onBucket,
}: {
  data: AmountsData;
  onBucket?: () => void;
}) {
  const { t, lang } = useT();
  const locale = DATE_LOCALES[lang];
  const max = Math.max(...data.buckets.map((b) => b.count), 1);
  const sharePct = data.coverage.share != null ? Math.round(data.coverage.share * 100) : null;

  const tiles = [
    { label: t('disputes.amounts.sum'), value: gel(data.overall.sum, locale) },
    { label: t('disputes.amounts.avg'), value: gel(data.overall.avg, locale) },
    { label: t('disputes.amounts.median'), value: gel(data.overall.median, locale) },
    { label: t('disputes.amounts.p90'), value: gel(data.overall.p90, locale) },
  ];

  return (
    <div>
      <div className="grid grid-cols-2 gap-4 sm:grid-cols-4">
        {tiles.map(({ label, value }) => (
          <div key={label}>
            <div className="font-heading text-2xl italic text-white md:text-3xl">{value}</div>
            <div className="mt-1 text-[12px] font-light text-white/60">{label}</div>
          </div>
        ))}
      </div>

      {data.coverage.with_amount >= MIN_WITH_AMOUNT && (
        <div className="mt-8 flex h-40 items-end gap-3">
          {data.buckets.map((b) => (
            <button
              key={b.label}
              type="button"
              onClick={onBucket}
              title={`${b.label}: ${b.count}`}
              className="group flex h-full flex-1 cursor-pointer flex-col items-center justify-end gap-1.5"
            >
              <span className="text-[12px] text-white/70">{b.count}</span>
              <span
                className="w-full rounded-t-md bg-white/25 transition-colors group-hover:bg-primary"
                style={{ height: `${Math.max((b.count / max) * 100, 2)}%` }}
              />
              <span className="text-[11px] text-white/50">{b.label}</span>
            </button>
          ))}
        </div>
      )}

      {sharePct != null && (
        <p className="mt-4 text-[12px] font-light leading-relaxed text-white/50">
          {t('disputes.amounts.note', { p: sharePct })}
        </p>
      )}
    </div>
  );
}
