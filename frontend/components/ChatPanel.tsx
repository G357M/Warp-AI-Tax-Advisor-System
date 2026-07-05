'use client';

import { FormEvent, useState } from 'react';
import { useQuery } from '@/hooks/useQuery';
import { Button } from '@/components/ui/Button';
import { SourceChip } from '@/components/ui/SourceChip';
import { useT } from '@/lib/i18n';

export function ChatPanel() {
  const { data, loading, error, submitQuery } = useQuery();
  const { lang, t } = useT();
  const [question, setQuestion] = useState('');
  const [asked, setAsked] = useState<string | null>(null);

  const ask = (q: string) => {
    const text = q.trim();
    if (!text || loading) return;
    setAsked(text);
    submitQuery(text, lang);
  };

  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    ask(question);
  };

  const examples = [t('chat.ex1'), t('chat.ex2'), t('chat.ex3')];

  return (
    <div id="chat" className="mx-auto w-full max-w-2xl scroll-mt-24">
      <form onSubmit={onSubmit} className="relative">
        <input
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          placeholder={t('chat.placeholder')}
          aria-label={t('chat.placeholder')}
          className="h-14 w-full rounded-full border bg-white pl-6 pr-32 text-[15px] shadow-[0_2px_12px_rgba(0,0,0,0.05)] placeholder:text-muted-foreground focus-visible:border-primary"
        />
        <div className="absolute right-2 top-1/2 flex -translate-y-1/2 items-center gap-2">
          <Button type="submit" disabled={loading || !question.trim()}>
            {loading ? t('chat.asking') : t('chat.ask')}
          </Button>
        </div>
      </form>

      <div className="mt-3 flex flex-wrap items-center justify-center gap-2">
        {examples.map((q) => (
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
          {asked && (
            <div className="mb-3 text-[13px] text-muted-foreground">
              {t('chat.question')} {asked}
            </div>
          )}
          {error && (
            <div className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-[13px] text-red-700">
              {t('chat.error')} {error}. {t('chat.retry')}
            </div>
          )}
          {loading && (
            <div className="rounded-lg border bg-white p-5 text-[14px] text-muted-foreground">
              {t('chat.searching')}
            </div>
          )}
          {!loading && data && (
            <div className="rounded-lg border bg-white p-5">
              <p className="whitespace-pre-wrap text-[15px] leading-7">{data.response}</p>
              {data.sources?.length > 0 && (
                <div className="mt-4 border-t pt-4">
                  <div className="mb-2 text-xs font-medium uppercase tracking-wide text-muted-foreground">
                    {t('chat.sources')}
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
