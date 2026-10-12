'use client';

import { FormEvent, useState } from 'react';
import Link from 'next/link';
import { useQuery } from '@/hooks/useQuery';
import { Button } from '@/components/ui/Button';
import { SourceChip } from '@/components/ui/SourceChip';
import { AnswerRating } from '@/components/AnswerRating';
import { isLoggedIn } from '@/lib/auth';
import { useT } from '@/lib/i18n';

type QueryData = NonNullable<ReturnType<typeof useQuery>['data']>;
type QueryError = NonNullable<ReturnType<typeof useQuery>['error']>;

function errorKey(error: QueryError) {
  if (error === 'rate_limit') return 'chat.err.rate';
  if (error === 'auth') return 'chat.err.auth';
  if (error === 'network') return 'chat.err.network';
  return 'chat.err.service';
}

function groundedKey(evidence: QueryData['evidence']) {
  if (!evidence.has_precise_citation) return 'chat.evidence.document';
  return evidence.has_official_provision_link ? 'chat.evidence.provision' : 'chat.evidence.exact';
}

function evidenceKey(evidence: QueryData['evidence']) {
  if (evidence.status === 'grounded') return groundedKey(evidence);
  if (evidence.status === 'partial') return 'chat.evidence.partial';
  if (evidence.status === 'out_of_scope') return 'chat.evidence.out_of_scope';
  return 'chat.evidence.insufficient';
}

function normalizeSource(s: QueryData['sources'][number]) {
  if ('text' in s) {
    return {
      title: s.metadata?.title || s.text,
      documentType: s.metadata?.document_type,
      url: s.metadata?.source_url,
      articleRef: s.metadata?.article_ref,
      pointRef: s.metadata?.point_ref,
      documentNumber: s.metadata?.document_number,
      datePublished: s.metadata?.date_published,
      dateEffective: s.metadata?.date_effective,
      officialActUrl: s.metadata?.official_act_url,
      provisionLinks: s.metadata?.provision_links,
    };
  }
  return {
    title: s.title,
    documentType: s.document_type,
    url: s.url,
    articleRef: s.article_ref,
    pointRef: s.point_ref,
    documentNumber: s.document_number,
    datePublished: s.date_published,
    dateEffective: s.date_effective,
    officialActUrl: s.official_act_url,
    provisionLinks: s.provision_links,
  };
}

type Translate = ReturnType<typeof useT>['t'];

function ErrorNotice({ error, asked, onRetry, t }: Readonly<{
  error: QueryError; asked: string | null; onRetry: (q: string) => void; t: Translate;
}>) {
  return (
    <div className="rounded-2xl border border-error-border bg-error px-4 py-3">
      <p className="text-[13px] leading-relaxed text-error-foreground">{t(errorKey(error))}</p>
      {error === 'auth' && (
        <Link
          href="/login"
          className="mt-0.5 inline-flex min-h-[44px] items-center text-[13px] font-medium text-error-foreground underline underline-offset-2 transition-opacity hover:opacity-80"
        >
          {t('chat.err.signin')}
        </Link>
      )}
      {error !== 'rate_limit' && error !== 'auth' && asked && (
        <button
          type="button"
          onClick={() => onRetry(asked)}
          className="mt-0.5 inline-flex min-h-[44px] items-center text-[13px] font-medium text-error-foreground underline underline-offset-2 transition-opacity hover:opacity-80"
        >
          {t('chat.err.retry_cta')}
        </button>
      )}
    </div>
  );
}

function EvidenceNote({ evidence, t }: Readonly<{ evidence: QueryData['evidence']; t: Translate }>) {
  return (
    <div className="mt-4 flex min-w-0 items-start gap-2.5 text-xs leading-5 text-white/60" role="status">
      {evidence.status === 'grounded' && (
        <span aria-hidden className="mt-[3px] h-3.5 w-[3px] shrink-0 rounded-full bg-primary" />
      )}
      <span className="min-w-0">{t(evidenceKey(evidence))}</span>
    </div>
  );
}

export function ChatPanel() {
  const { data, loading, error, submitQuery } = useQuery();
  const { lang, t } = useT();
  const [question, setQuestion] = useState('');
  const [asked, setAsked] = useState<string | null>(null);

  const ask = (q: string) => {
    const text = q.trim();
    if (!text || loading) return;
    setAsked(text);
    void submitQuery(text, lang);
    // On mobile the answer area renders below the fold; bring it into view.
    const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    document.getElementById('chat')?.scrollIntoView({ behavior: reduce ? 'auto' : 'smooth' });
  };

  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    ask(question);
  };

  const examples = [t('chat.ex1'), t('chat.ex2'), t('chat.ex3')];

  return (
    <div id="chat" className="mx-auto w-full max-w-2xl scroll-mt-28">
      <form onSubmit={onSubmit} className="liquid-glass-strong relative rounded-full">
        <input
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          placeholder={t('chat.placeholder')}
          aria-label={t('chat.placeholder')}
          className="h-14 w-full rounded-full bg-transparent pl-6 pr-28 text-[15px] text-white placeholder:text-white/50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring sm:pr-32"
        />
        <div className="absolute right-2 top-1/2 flex -translate-y-1/2 items-center gap-2">
          <Button type="submit" disabled={loading || !question.trim()}>
            {loading ? t('chat.asking') : t('chat.ask')}
          </Button>
        </div>
      </form>

      <div className="mt-4 flex flex-wrap items-center justify-center gap-2">
        {examples.map((q) => (
          <button
            key={q}
            type="button"
            onClick={() => {
              setQuestion(q);
              ask(q);
            }}
            className="liquid-glass inline-flex min-h-[44px] items-center rounded-full px-4 text-xs font-light text-white/70 transition-all duration-300 hover:bg-white/5 hover:text-white"
          >
            {q}
          </button>
        ))}
      </div>

      {(asked || error) && (
        <div className="mt-8 text-left">
          {asked && (
            <div className="mb-3 text-[13px] font-light text-white/60">
              {t('chat.question')} {asked}
            </div>
          )}
          {error && <ErrorNotice error={error} asked={asked} onRetry={ask} t={t} />}
          {loading && (
            <div className="liquid-glass rounded-2xl p-5 text-[14px] font-light text-white/60">
              {t('chat.searching')}
            </div>
          )}
          {!loading && data && (
            <div className="liquid-glass rounded-2xl p-6" aria-live="polite">
              <p className="whitespace-pre-wrap text-[15px] font-light leading-7 text-white/90">
                {data.response}
              </p>
              <EvidenceNote evidence={data.evidence} t={t} />
              {data.sources?.length > 0 && (
                <div className="mt-4 border-t border-white/10 pt-4">
                  <div className="mb-2 text-xs font-medium uppercase tracking-wide text-white/50">
                    {t('chat.sources')}
                  </div>
                  <div className="flex flex-col gap-2">
                    {data.sources.slice(0, 5).map((s, i) => (
                      <SourceChip key={i} {...normalizeSource(s)} />
                    ))}
                  </div>
                </div>
              )}
              {data.message_id && isLoggedIn() && (
                <AnswerRating key={data.message_id} messageId={data.message_id} />
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
