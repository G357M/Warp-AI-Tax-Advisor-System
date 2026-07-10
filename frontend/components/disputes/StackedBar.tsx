'use client';

import { useT } from '@/lib/i18n';
import { OUTCOME_META, OutcomeRow } from './shared';

/** Proportional outcome split; every segment is a button that drills down. */
export function StackedBar({
  row,
  onSegment,
}: {
  row: OutcomeRow;
  onSegment?: (outcome: string) => void;
}) {
  const { t } = useT();
  const total = row.satisfied + row.partially_satisfied + row.rejected;
  if (!total) return <div className="flex-1" />;
  return (
    <div className="flex h-[22px] flex-1 items-stretch gap-[2px]">
      {OUTCOME_META.map(({ key, color }) => {
        const value = row[key];
        if (!value) return null;
        const label = `${t(`disputes.outcome.${key}`)}: ${value} (${Math.round((value / total) * 100)}%)`;
        return (
          <button
            key={key}
            type="button"
            title={label}
            aria-label={label}
            onClick={onSegment ? () => onSegment(key) : undefined}
            className={`min-w-[3px] rounded transition-[filter] ${
              onSegment ? 'cursor-pointer hover:brightness-125 hover:ring-1 hover:ring-primary' : 'cursor-default'
            }`}
            style={{ width: `${(value / total) * 100}%`, background: color }}
          />
        );
      })}
    </div>
  );
}

export function OutcomeLegend() {
  const { t } = useT();
  return (
    <div className="flex flex-wrap gap-4">
      {OUTCOME_META.map(({ key, color }) => (
        <span key={key} className="inline-flex items-center gap-1.5 text-[12px] text-white/70">
          <span className="inline-block h-2.5 w-2.5 rounded-[3px]" style={{ background: color }} />
          {t(`disputes.outcome.${key}`)}
        </span>
      ))}
    </div>
  );
}
