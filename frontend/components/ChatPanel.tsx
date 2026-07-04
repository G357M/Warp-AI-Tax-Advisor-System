'use client';

import { FormEvent, useState } from 'react';
import { useQuery } from '@/hooks/useQuery';
import { Button } from '@/components/ui/Button';
import { SourceChip } from '@/components/ui/SourceChip';

const EXAMPLES = [
  'Какая ставка НДС в Грузии?',
  'Может ли ООО применять налог 1%?',
  'Как обжаловать решение налоговой?',
];

const LANGUAGES = [
  { code: 'ru', label: 'Рус' },
  { code: 'ka', label: 'ქარ' },
  { code: 'en', label: 'Eng' },
] as const;

export function ChatPanel() {
  const { data, loading, error, submitQuery } = useQuery();
  const [question, setQuestion] = useState('');
  const [language, setLanguage] = useState<'ru' | 'ka' | 'en'>('ru');
  const [asked, setAsked] = useState<string | null>(null);

  const ask = (q: string) => {
    const text = q.trim();
    if (!text || loading) return;
    setAsked(text);
    submitQuery(text, language);
  };

  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    ask(question);
  };

  return (
    <div id="chat" className="mx-auto w-full max-w-2xl scroll-mt-24">
      <form onSubmit={onSubmit} className="relative">
        <input
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          placeholder="Спросите о налогах Грузии…"
          aria-label="Вопрос о налоговом праве Грузии"
          className="h-14 w-full rounded-full border bg-white pl-6 pr-32 text-[15px] shadow-[0_2px_12px_rgba(0,0,0,0.05)] placeholder:text-muted-foreground focus-visible:border-primary"
        />
        <div className="absolute right-2 top-1/2 flex -translate-y-1/2 items-center gap-2">
          <Button type="submit" disabled={loading || !question.trim()}>
            {loading ? 'Ищу…' : 'Спросить'}
          </Button>
        </div>
      </form>

      <div className="mt-3 flex flex-wrap items-center justify-center gap-2">
        <div className="mr-2 flex overflow-hidden rounded-full border" role="group" aria-label="Язык ответа">
          {LANGUAGES.map((l) => (
            <button
              key={l.code}
              type="button"
              onClick={() => setLanguage(l.code)}
              className={`px-3 py-1 text-xs transition-colors ${
                language === l.code ? 'bg-foreground text-background' : 'text-muted-foreground hover:text-foreground'
              }`}
            >
              {l.label}
            </button>
          ))}
        </div>
        {EXAMPLES.map((q) => (
          <button
            key={q}
            type="button"
            onClick={() => {
              setQuestion(q);
              ask(q);
            }}
            className="rounded-full border px-3.5 py-1 text-xs text-muted-foreground transition-colors hover:border-primary/40 hover:text-foreground"
          >
            {q}
          </button>
        ))}
      </div>

      {(asked || error) && (
        <div className="mt-8 text-left">
          {asked && <div className="mb-3 text-[13px] text-muted-foreground">Вопрос: {asked}</div>}
          {error && (
            <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-[13px] text-red-700">
              Не получилось получить ответ: {error}. Попробуйте ещё раз.
            </div>
          )}
          {loading && (
            <div className="rounded-lg border bg-white p-5 text-[14px] text-muted-foreground">
              Ищу ответ в официальной базе…
            </div>
          )}
          {!loading && data && (
            <div className="rounded-lg border bg-white p-5">
              <p className="whitespace-pre-wrap text-[15px] leading-7">{data.response}</p>
              {data.sources?.length > 0 && (
                <div className="mt-4 border-t pt-4">
                  <div className="mb-2 text-xs font-medium uppercase tracking-wide text-muted-foreground">
                    Источники
                  </div>
                  <div className="flex flex-col gap-2">
                    {data.sources.slice(0, 5).map((s: any, i: number) => (
                      <SourceChip
                        key={i}
                        title={s.metadata?.title || s.text}
                        documentType={s.metadata?.document_type}
                        url={s.metadata?.source_url}
                      />
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
