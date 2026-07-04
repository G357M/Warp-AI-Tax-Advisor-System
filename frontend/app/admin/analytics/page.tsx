'use client';

import { useEffect, useState } from 'react';

// Outcome palette — validated (dataviz six checks, dark surface):
// satisfied #059669, partially satisfied #d97706, rejected #3b82f6
const OUTCOME_META = [
  { key: 'satisfied', label: 'Satisfied', color: '#059669' },
  { key: 'partially_satisfied', label: 'Partially satisfied', color: '#d97706' },
  { key: 'rejected', label: 'Rejected', color: '#3b82f6' },
] as const;

const BODY_LABELS: Record<string, string> = {
  revenue_service_council: 'Revenue Service dispute council',
  mof_dispute_council: 'MoF dispute council',
  city_court: 'City court',
  appeals_court: 'Appeals court',
  supreme_court: 'Supreme court',
  other: 'Other',
};

interface OutcomeRow {
  total: number;
  satisfied: number;
  partially_satisfied: number;
  rejected: number;
  unclear: number;
  taxpayer_relief_rate: number | null;
}

interface Analytics {
  coverage: { decisions_in_corpus: number; decisions_extracted: number };
  overall: OutcomeRow;
  by_year: (OutcomeRow & { year: number })[];
  by_body: (OutcomeRow & { body: string })[];
  by_dispute_type: (OutcomeRow & { dispute_type: string })[];
  top_articles: (OutcomeRow & { article: string })[];
}

const card: React.CSSProperties = {
  background: 'rgba(255,255,255,0.05)',
  border: '1px solid rgba(255,255,255,0.1)',
  borderRadius: '12px',
  padding: '1.5rem',
};

function pct(rate: number | null): string {
  return rate == null ? '—' : `${Math.round(rate * 100)}%`;
}

function StackedBar({ row }: { row: OutcomeRow }) {
  const total = row.satisfied + row.partially_satisfied + row.rejected;
  if (!total) return <div style={{ flex: 1 }} />;
  return (
    <div style={{ display: 'flex', gap: '2px', flex: 1, height: '18px', alignItems: 'stretch' }}>
      {OUTCOME_META.map(({ key, label, color }) => {
        const value = row[key];
        if (!value) return null;
        return (
          <div
            key={key}
            title={`${label}: ${value} (${Math.round((value / total) * 100)}%)`}
            style={{
              width: `${(value / total) * 100}%`,
              minWidth: '2px',
              background: color,
              borderRadius: '4px',
            }}
          />
        );
      })}
    </div>
  );
}

function Legend() {
  return (
    <div style={{ display: 'flex', gap: '1rem', flexWrap: 'wrap', marginBottom: '0.75rem' }}>
      {OUTCOME_META.map(({ key, label, color }) => (
        <span key={key} style={{ display: 'inline-flex', alignItems: 'center', gap: '0.4rem', fontSize: '0.8rem', opacity: 0.85 }}>
          <span style={{ width: '10px', height: '10px', borderRadius: '3px', background: color, display: 'inline-block' }} />
          {label}
        </span>
      ))}
    </div>
  );
}

function BarSection({ title, rows }: { title: string; rows: { label: string; row: OutcomeRow }[] }) {
  return (
    <div style={card}>
      <h2 style={{ margin: '0 0 0.75rem 0', fontSize: '1.1rem' }}>{title}</h2>
      <Legend />
      <div style={{ display: 'flex', flexDirection: 'column', gap: '0.5rem' }}>
        {rows.map(({ label, row }) => (
          <div key={label} style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
            <span style={{ width: '220px', fontSize: '0.85rem', opacity: 0.85, flexShrink: 0 }}>{label}</span>
            <StackedBar row={row} />
            <span style={{ width: '110px', fontSize: '0.8rem', opacity: 0.7, textAlign: 'right', flexShrink: 0 }}>
              {row.total} · relief {pct(row.taxpayer_relief_rate)}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

export default function AnalyticsPage() {
  const [data, setData] = useState<Analytics | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetch('/api/v1/analytics/decisions')
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      })
      .then(setData)
      .catch((e) => setError(String(e)));
  }, []);

  if (error) {
    return <div style={{ padding: '2rem', color: '#f87171' }}>Failed to load analytics: {error}</div>;
  }
  if (!data) {
    return <div style={{ padding: '2rem', opacity: 0.7 }}>Loading dispute analytics…</div>;
  }

  const coveragePct = data.coverage.decisions_in_corpus
    ? Math.round((data.coverage.decisions_extracted / data.coverage.decisions_in_corpus) * 100)
    : 0;

  return (
    <div style={{ padding: '2rem', display: 'flex', flexDirection: 'column', gap: '1.5rem', maxWidth: '1100px' }}>
      <div>
        <h1 style={{ margin: 0, fontSize: '1.75rem' }}>Dispute Analytics</h1>
        <p style={{ margin: '0.25rem 0 0 0', opacity: 0.7, fontSize: '0.9rem' }}>
          Outcomes of tax/customs dispute decisions extracted from the official corpus
        </p>
      </div>

      {/* Stat tiles */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(220px, 1fr))', gap: '1rem' }}>
        <div style={card}>
          <div style={{ fontSize: '0.8rem', opacity: 0.7 }}>Decisions analyzed</div>
          <div style={{ fontSize: '2rem', fontWeight: 700 }}>
            {data.coverage.decisions_extracted.toLocaleString('en-US')}
          </div>
          <div style={{ fontSize: '0.8rem', opacity: 0.6 }}>
            {coveragePct}% of {data.coverage.decisions_in_corpus.toLocaleString('en-US')} in corpus
          </div>
        </div>
        <div style={card}>
          <div style={{ fontSize: '0.8rem', opacity: 0.7 }}>Taxpayer relief rate</div>
          <div style={{ fontSize: '2rem', fontWeight: 700 }}>{pct(data.overall.taxpayer_relief_rate)}</div>
          <div style={{ fontSize: '0.8rem', opacity: 0.6 }}>complaint satisfied fully or partially</div>
        </div>
        <div style={card}>
          <div style={{ fontSize: '0.8rem', opacity: 0.7 }}>Fully satisfied</div>
          <div style={{ fontSize: '2rem', fontWeight: 700 }}>{data.overall.satisfied.toLocaleString('en-US')}</div>
          <div style={{ fontSize: '0.8rem', opacity: 0.6 }}>
            vs {data.overall.rejected.toLocaleString('en-US')} rejected
          </div>
        </div>
      </div>

      <BarSection
        title="Outcomes by year"
        rows={data.by_year.map((r) => ({ label: String(r.year), row: r }))}
      />

      <BarSection
        title="Outcomes by deciding body"
        rows={data.by_body
          .filter((r) => r.body)
          .map((r) => ({ label: BODY_LABELS[r.body] ?? r.body, row: r }))}
      />

      {/* Top contested articles */}
      <div style={card}>
        <h2 style={{ margin: '0 0 0.75rem 0', fontSize: '1.1rem' }}>Top contested Tax Code articles</h2>
        <Legend />
        <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '0.85rem' }}>
          <thead>
            <tr style={{ textAlign: 'left', opacity: 0.7 }}>
              <th style={{ padding: '0.4rem 0.5rem' }}>Article</th>
              <th style={{ padding: '0.4rem 0.5rem' }}>Decisions</th>
              <th style={{ padding: '0.4rem 0.5rem', width: '40%' }}>Outcome split</th>
              <th style={{ padding: '0.4rem 0.5rem', textAlign: 'right' }}>Relief rate</th>
            </tr>
          </thead>
          <tbody>
            {data.top_articles.map((r) => (
              <tr key={r.article} style={{ borderTop: '1px solid rgba(255,255,255,0.08)' }}>
                <td style={{ padding: '0.4rem 0.5rem', fontWeight: 600 }}>{r.article}</td>
                <td style={{ padding: '0.4rem 0.5rem' }}>{r.total}</td>
                <td style={{ padding: '0.4rem 0.5rem' }}>
                  <StackedBar row={r} />
                </td>
                <td style={{ padding: '0.4rem 0.5rem', textAlign: 'right' }}>{pct(r.taxpayer_relief_rate)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
