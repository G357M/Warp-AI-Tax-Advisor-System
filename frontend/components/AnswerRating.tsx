'use client';

import { useState } from 'react';
import { authFetch } from '@/lib/auth';
import { useT } from '@/lib/i18n';

type Rating = { value: 1 | -1; comment: string | null } | null;

export function AnswerRating({ messageId, initial = null }: { messageId: string; initial?: Rating }) {
  const { t } = useT();
  const [rating, setRating] = useState<Rating>(initial);
  const [comment, setComment] = useState(initial?.comment ?? '');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const url = `/api/v1/query/messages/${messageId}/rating`;

  const save = async (next: Rating) => {
    const previous = rating;
    setRating(next);
    setBusy(true);
    setError(null);
    try {
      const res = next
        ? await authFetch(url, {
            method: 'PUT',
            body: JSON.stringify({ value: next.value, comment: next.comment || undefined }),
          })
        : await authFetch(url, { method: 'DELETE' });
      if (!res.ok) throw Object.assign(new Error('rating'), { status: res.status });
    } catch (e) {
      setRating(previous);
      setError(t((e as { status?: number }).status === 429 ? 'rating.rate_limited' : 'rating.error'));
    } finally {
      setBusy(false);
    }
  };

  const toggle = (value: 1 | -1) =>
    save(rating?.value === value ? null : { value, comment: value === -1 ? comment.trim() || null : null });

  return (
    <div className="mt-4 flex flex-col gap-2 border-t border-white/10 pt-3 text-xs text-white/60">
      <div className="flex items-center gap-2">
        {([1, -1] as const).map((value) => (
          <button
            key={value}
            type="button"
            disabled={busy}
            aria-pressed={rating?.value === value}
            aria-label={t(value === 1 ? 'rating.up' : 'rating.down')}
            className={`min-h-[44px] min-w-[44px] rounded-full border px-3 py-1 text-base transition focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring ${
              rating?.value === value
                ? 'border-primary bg-primary/20 text-white'
                : 'border-white/15 hover:border-white/40'
            }`}
            onClick={() => toggle(value)}
          >
            <span aria-hidden>{value === 1 ? '👍' : '👎'}</span>
          </button>
        ))}
        {rating && <span role="status">{t('rating.thanks')}</span>}
      </div>
      {rating?.value === -1 && (
        <div className="flex flex-col gap-2 sm:flex-row sm:items-end">
          <label className="flex min-w-0 flex-1 flex-col gap-1">
            {t('rating.comment_label')}
            <textarea
              maxLength={1000}
              rows={2}
              value={comment}
              onChange={(e) => setComment(e.target.value)}
              className="rounded-xl border border-white/15 bg-white/5 p-2 text-sm text-white/90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            />
          </label>
          <button
            type="button"
            disabled={busy}
            className="min-h-[44px] rounded-full border border-white/20 px-4 py-2 text-sm text-white/90 hover:border-white/40 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            onClick={() => save({ value: -1, comment: comment.trim() || null })}
          >
            {t('rating.comment_send')}
          </button>
        </div>
      )}
      {error && (
        <p role="alert" className="text-error-foreground">
          {error}
        </p>
      )}
    </div>
  );
}
