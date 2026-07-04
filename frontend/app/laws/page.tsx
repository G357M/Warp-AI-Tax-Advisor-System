'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';

interface AmendedLaw {
  law_id: string;
  title: string;
  amendments: number;
  last_adoption: string | null;
}

export default function LawsPage() {
  const [laws, setLaws] = useState<AmendedLaw[] | null>(null);
  const [error, setError] = useState(false);
  const [filter, setFilter] = useState('');

  useEffect(() => {
    fetch('/api/v1/amendments/laws')
      .then((r) => (r.ok ? r.json() : Promise.reject()))
      .then((d) => setLaws(d.laws))
      .catch(() => setError(true));
  }, []);

  const shown = (laws ?? []).filter((l) =>
    l.title.toLowerCase().includes(filter.toLowerCase()),
  );

  return (
    <main className="mx-auto min-h-[70vh] max-w-page px-6 py-16">
      <h1 className="text-3xl font-semibold tracking-display">Изменения законов</h1>
      <p className="mt-3 max-w-2xl text-[15px] leading-relaxed text-muted-foreground">
        Хронология поправок к законам Грузии: когда принята, когда вступила в силу,
        какие статьи затронула и что изменилось по существу.
      </p>

      <input
        value={filter}
        onChange={(e) => setFilter(e.target.value)}
        placeholder="Найти закон…"
        aria-label="Поиск по названию закона"
        className="mt-8 h-11 w-full max-w-md rounded-full border bg-white px-5 text-[14px] placeholder:text-muted-foreground"
      />

      {error && (
        <p className="mt-10 text-[14px] text-muted-foreground">
          Не получилось загрузить список законов. Обновите страницу.
        </p>
      )}
      {!laws && !error && <p className="mt-10 text-[14px] text-muted-foreground">Загружаю…</p>}

      <div className="mt-8 divide-y rounded-lg border bg-white">
        {shown.map((law) => (
          <Link
            key={law.law_id}
            href={`/laws/${law.law_id}`}
            className="flex items-center justify-between gap-4 px-5 py-4 transition-colors hover:bg-muted"
          >
            <span className="min-w-0">
              <span className="block truncate text-[15px] font-medium">{law.title}</span>
              {law.last_adoption && (
                <span className="block text-[13px] text-muted-foreground">
                  последняя поправка — {new Date(law.last_adoption).toLocaleDateString('ru-RU')}
                </span>
              )}
            </span>
            <span className="shrink-0 rounded-full bg-secondary px-3 py-1 text-[13px] font-medium text-secondary-foreground">
              {law.amendments}
            </span>
          </Link>
        ))}
        {laws && shown.length === 0 && (
          <p className="px-5 py-6 text-[14px] text-muted-foreground">
            {laws.length === 0
              ? 'Поправки ещё обрабатываются — загляните позже.'
              : 'Ничего не нашлось по этому названию.'}
          </p>
        )}
      </div>
    </main>
  );
}
