'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { useParams, useRouter } from 'next/navigation';
import { authFetch, isLoggedIn } from '@/lib/auth';
import { useT, DATE_LOCALES } from '@/lib/i18n';
import { Button } from '@/components/ui/Button';
import { SourceChip } from '@/components/ui/SourceChip';

interface ConversationSource {
  title: string;
  document_type: string;
  url: string;
  article_ref?: string | null;
  point_ref?: string | null;
  document_number?: string | null;
  date_published?: string | null;
  date_effective?: string | null;
}

interface ConversationMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  sources?: ConversationSource[] | null;
  created_at: string;
}

interface ConversationDetail {
  conversation: {
    id: string;
    title: string | null;
    created_at: string;
    updated_at: string;
  };
  messages: ConversationMessage[];
}

export default function ConversationPage() {
  const { conversationId } = useParams<{ conversationId: string }>();
  const router = useRouter();
  const { lang, t } = useT();
  const [data, setData] = useState<ConversationDetail | null>(null);
  const [error, setError] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [deleting, setDeleting] = useState(false);

  useEffect(() => {
    if (!isLoggedIn()) {
      router.replace('/login');
      return;
    }
    authFetch(`/api/v1/query/conversations/${conversationId}`)
      .then((response) => {
        if (response.status === 401) {
          router.replace('/login');
          return null;
        }
        if (response.status === 402) {
          router.replace('/account');
          return null;
        }
        if (!response.ok) throw new Error();
        return response.json();
      })
      .then((result) => result && setData(result))
      .catch(() => setError(true));
  }, [conversationId, router]);

  const removeConversation = async () => {
    setDeleting(true);
    const response = await authFetch(`/api/v1/query/conversations/${conversationId}`, {
      method: 'DELETE',
    });
    if (response.ok) {
      router.push('/account');
      return;
    }
    if (response.status === 401) {
      router.replace('/login');
      return;
    }
    setDeleting(false);
    setError(true);
  };

  if (error) {
    return (
      <main className="mx-auto min-h-[70vh] max-w-2xl px-6 py-16">
        <p className="text-[14px] text-error-foreground">{t('acc.history_detail_error')}</p>
        <Link href="/account" className="mt-4 inline-flex min-h-[44px] items-center text-sm text-primary hover:underline">
          {t('acc.history_back')}
        </Link>
      </main>
    );
  }

  if (!data) {
    return (
      <main className="mx-auto min-h-[70vh] max-w-2xl px-6 py-16 text-[14px] text-muted-foreground">
        {t('acc.history_loading')}
      </main>
    );
  }

  const locale = DATE_LOCALES[lang];

  return (
    <main className="mx-auto min-h-[70vh] max-w-2xl px-6 py-16">
      <Link href="/account" className="inline-flex min-h-[44px] items-center text-sm text-muted-foreground hover:text-white">
        ← {t('acc.history_back')}
      </Link>
      <div className="mt-4 flex flex-col items-start justify-between gap-5 sm:flex-row">
        <div className="flex min-w-0 items-start gap-3">
          <span aria-hidden className="mt-2 h-7 w-1 shrink-0 rounded-full bg-primary" />
          <div className="min-w-0">
            <h1 className="font-heading text-3xl font-normal italic leading-tight text-white">
              {data.conversation.title || t('acc.history_untitled')}
            </h1>
            <p className="mt-2 text-xs text-muted-foreground">
              {new Date(data.conversation.updated_at).toLocaleDateString(locale)}
            </p>
          </div>
        </div>
        {!confirmDelete ? (
          <Button variant="ghost" onClick={() => setConfirmDelete(true)}>
            {t('acc.history_delete')}
          </Button>
        ) : (
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-xs text-muted-foreground">{t('acc.history_delete_confirm')}</span>
            <Button onClick={removeConversation} disabled={deleting}>
              {deleting ? t('acc.history_deleting') : t('acc.history_delete_yes')}
            </Button>
            <Button variant="ghost" onClick={() => setConfirmDelete(false)} disabled={deleting}>
              {t('acc.history_delete_no')}
            </Button>
          </div>
        )}
      </div>

      <div className="mt-8 space-y-4">
        {data.messages.map((message) => (
          <article
            key={message.id}
            className={message.role === 'assistant' ? 'liquid-glass rounded-2xl p-6' : 'px-1 py-3'}
          >
            <div className="mb-2 text-xs font-medium text-muted-foreground">
              {message.role === 'assistant' ? t('acc.history_advisor') : t('acc.history_you')}
            </div>
            <p className="whitespace-pre-wrap text-[15px] font-light leading-7 text-white/90">
              {message.content}
            </p>
            {message.role === 'assistant' && message.sources && message.sources.length > 0 && (
              <div className="mt-4 space-y-2 border-t border-white/10 pt-4">
                {message.sources.slice(0, 5).map((source, index) => (
                  <SourceChip
                    key={`${message.id}-${index}`}
                    title={source.title}
                    documentType={source.document_type}
                    url={source.url}
                    articleRef={source.article_ref}
                    pointRef={source.point_ref}
                    documentNumber={source.document_number}
                    datePublished={source.date_published}
                    dateEffective={source.date_effective}
                  />
                ))}
              </div>
            )}
          </article>
        ))}
      </div>
    </main>
  );
}
