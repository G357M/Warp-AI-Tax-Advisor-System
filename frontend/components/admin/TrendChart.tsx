'use client';

import { useState, type CSSProperties } from 'react';
import styles from '@/app/admin/admin.module.css';

export type ChartSeries = { key: string; label: string; color: string; values: (number | null)[] };

interface TrendChartProps {
  readonly title: string;
  readonly labels: string[];
  /** One series, or several stacked bottom-up in the given order. One axis only. */
  readonly series: ChartSeries[];
  readonly format: (v: number) => string;
  readonly partialLast: boolean;
  readonly emptyText: string;
  readonly dataLabel: string;
  readonly periodLabel: string;
  readonly partialLabel: string;
  readonly dash: string;
  readonly note?: string;
  /** Shares: a real 0 is data, so only all-null means "no data". Counts: all-zero means "no data". */
  readonly zeroIsData?: boolean;
}

const MAX_X_LABELS = 8;
const vars = (v: Record<string, string>) => v as CSSProperties;

/** Smallest 1/2/5 × 10ⁿ at or above `v`, so the top gridline is a round number. */
export function niceMax(v: number): number {
  if (v <= 0) return 1;
  const power = 10 ** Math.floor(Math.log10(v));
  const step = [1, 2, 5, 10].find((m) => v <= m * power) ?? 10;
  return step * power;
}

function shownLabel(i: number, n: number): boolean {
  const step = Math.ceil(n / MAX_X_LABELS);
  return i === n - 1 || (i % step === 0 && n - 1 - i > step / 2);
}

export function TrendChart(props: TrendChartProps) {
  const { title, labels, series, format, partialLast, emptyText, dataLabel, periodLabel, partialLabel, dash, note, zeroIsData } = props;
  const [active, setActive] = useState<number | null>(null);
  const n = labels.length;
  const totals = labels.map((_, i) => series.reduce((sum, s) => sum + (s.values[i] ?? 0), 0));
  const max = niceMax(Math.max(0, ...totals));
  const empty = zeroIsData
    ? series.every((s) => s.values.every((v) => v === null))
    : totals.every((t) => t === 0);
  const value = (v: number | null) => (v === null ? dash : format(v));
  const last = n - 1;
  const summary = `${title}: ${labels[0] ?? ''} – ${labels[last] ?? ''}, max ${format(Math.max(0, ...totals))}`;
  const tipX = active === null ? 0 : Math.min(85, Math.max(15, ((active + 0.5) / n) * 100));

  return <figure className={styles.chart}>
    <figcaption className={styles.panelTitle}>{title}</figcaption>
    {series.length > 1 && <div className={styles.legend}>
      {series.map((s) => <span key={s.key}><span className={styles.swatch} style={vars({ '--c': s.color })} />{s.label}</span>)}
    </div>}
    <div className={styles.chartBody}>
      <div className={styles.chartAxis} aria-hidden="true">
        <span>{format(max)}</span><span>{format(max / 2)}</span><span>{format(0)}</span>
      </div>
      <div className={styles.chartPlot} style={vars({ '--n': String(n) })} role="img" aria-label={summary}
        onMouseLeave={() => setActive(null)}>
        {labels.map((label, i) => <button key={label} type="button" className={styles.chartCol} tabIndex={-1}
          aria-hidden="true" data-active={active === i} data-partial={partialLast && i === last}
          onMouseEnter={() => setActive(i)} onFocus={() => setActive(i)} onBlur={() => setActive(null)}>
          {series.map((s) => {
            const v = s.values[i];
            return v ? <span key={s.key} className={styles.chartSeg}
              style={vars({ '--h': `${(v / max) * 100}%`, '--c': s.color })} /> : null;
          })}
        </button>)}
        {empty && <span className={styles.chartEmpty}>{emptyText}</span>}
        {active !== null && <div className={styles.chartTip} style={vars({ '--x': `${tipX}%` })}>
          <strong>{labels[active]}{partialLast && active === last ? ` · ${partialLabel}` : ''}</strong>
          {series.map((s) => <span key={s.key}>
            <span className={styles.swatch} style={vars({ '--c': s.color })} />{s.label}: {value(s.values[active])}
          </span>)}
        </div>}
      </div>
      <span />
      <div className={styles.chartX} style={vars({ '--n': String(n) })} aria-hidden="true" data-axis="x">
        {labels.map((label, i) => <span key={label}>{shownLabel(i, n) ? label : ''}</span>)}
      </div>
    </div>
    {note && <p className={styles.chartNote}>{note}</p>}
    <details className={styles.chartData}>
      <summary>{dataLabel}</summary>
      <table>
        <thead><tr><th scope="col">{periodLabel}</th>{series.map((s) => <th key={s.key} scope="col">{s.label}</th>)}</tr></thead>
        <tbody>{labels.map((label, i) => <tr key={label}>
          <td>{label}{partialLast && i === last ? ` (${partialLabel})` : ''}</td>
          {series.map((s) => <td key={s.key}>{value(s.values[i])}</td>)}
        </tr>)}</tbody>
      </table>
    </details>
  </figure>;
}
