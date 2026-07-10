'use client';

import { useT } from '@/lib/i18n';

export interface ChainsData {
  links_total: number;
  transitions: {
    from: string;
    to: string;
    count: number;
    outcome_changed: number;
    flipped_to_taxpayer: number;
    flipped_to_authority: number;
  }[];
  chains: { total: number; reached_court: number; reached_supreme: number };
}

/** Appeal transitions between instances; the parent hides this section while
 *  links_total === 0 (before the v2 backfill has run). */
export function ChainFunnel({ data }: { data: ChainsData }) {
  const { t } = useT();
  const max = Math.max(...data.transitions.map((tr) => tr.count), 1);

  return (
    <div>
      <div className="flex flex-wrap gap-x-6 gap-y-1 text-[13px] text-white/70">
        <span>{t('disputes.tile.chains')}: {data.links_total}</span>
        <span>{t('disputes.chains.reached_court', { n: data.chains.reached_court })}</span>
        <span>{t('disputes.chains.reached_supreme', { n: data.chains.reached_supreme })}</span>
      </div>

      <div className="mt-5 flex flex-col gap-3">
        {data.transitions.map((tr) => (
          <div key={`${tr.from}->${tr.to}`} className="flex flex-col gap-1">
            <div className="flex items-baseline justify-between gap-4 text-[13px]">
              <span className="text-white/85">
                {t(`disputes.body.${tr.from}`)}
                <span className="mx-1.5 text-primary">→</span>
                {t(`disputes.body.${tr.to}`)}
              </span>
              <span className="shrink-0 text-white/60">{tr.count}</span>
            </div>
            <div className="h-[10px] w-full rounded bg-white/10">
              <div
                className="h-full rounded bg-primary/70"
                style={{ width: `${(tr.count / max) * 100}%` }}
              />
            </div>
            <div className="flex flex-wrap gap-x-4 text-[11px] text-white/50">
              <span>{t('disputes.chains.changed', { n: tr.outcome_changed })}</span>
              <span>{t('disputes.chains.to_taxpayer', { n: tr.flipped_to_taxpayer })}</span>
              <span>{t('disputes.chains.to_authority', { n: tr.flipped_to_authority })}</span>
            </div>
          </div>
        ))}
      </div>

      <p className="mt-4 text-[12px] font-light leading-relaxed text-white/50">
        {t('disputes.chains.note')}
      </p>
    </div>
  );
}
