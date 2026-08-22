'use client';

import { FormEvent, Suspense, useEffect, useState } from 'react';
import Link from 'next/link';
import { useSearchParams } from 'next/navigation';
import { resetPassword } from '@/lib/auth';
import { AuthFrame, authInputClass, FormMessage } from '@/components/auth/AuthFrame';
import { Button } from '@/components/ui/Button';
import { useT } from '@/lib/i18n';

type ResetError = 'short' | 'match' | 'token';

function ResetPasswordContent() {
  const { t } = useT();
  const searchParams = useSearchParams();
  const [rawToken] = useState(() => searchParams.get('token'));
  const [password, setPassword] = useState('');
  const [confirmation, setConfirmation] = useState('');
  const [busy, setBusy] = useState(false);
  const [success, setSuccess] = useState(false);
  const [error, setError] = useState<ResetError | null>(null);

  useEffect(() => {
    window.history.replaceState({}, '', '/reset-password');
  }, []);

  const token = success ? null : rawToken;
  const effectiveError: ResetError | null = error || (!token && !success ? 'token' : null);
  const displayedError = effectiveError === 'short'
    ? t('reg.pwshort')
    : effectiveError === 'match'
      ? t('reset.error.match')
      : effectiveError === 'token'
        ? t('reset.error.token')
        : null;

  const onSubmit = async (event: FormEvent) => {
    event.preventDefault();
    if (!token) return;
    if (password.length < 8) {
      setError('short');
      return;
    }
    if (password !== confirmation) {
      setError('match');
      return;
    }
    setError(null);
    setBusy(true);
    try {
      await resetPassword(token, password);
      setSuccess(true);
    } catch {
      setError('token');
    } finally {
      setBusy(false);
    }
  };

  return (
    <AuthFrame
      title={success ? t('reset.success.title') : t('reset.title')}
      description={success ? t('reset.success.body') : t('reset.sub')}
      footer={success ? (
        <p className="text-center">
          <Link href="/login" className="text-white underline decoration-white/30 underline-offset-4 hover:decoration-primary">
            {t('auth.signin')}
          </Link>
        </p>
      ) : undefined}
    >
      {!success && (
        <form onSubmit={onSubmit} className="space-y-5">
          <input
            type="text"
            name="username"
            autoComplete="username"
            tabIndex={-1}
            aria-hidden="true"
            className="hidden"
          />
          <label className="block text-[13px] text-white/75">
            {t('reset.password')}
            <input
              type="password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              autoComplete="new-password"
              minLength={8}
              required
              disabled={!token}
              className={authInputClass}
            />
          </label>
          <label className="block text-[13px] text-white/75">
            {t('reset.confirm')}
            <input
              type="password"
              value={confirmation}
              onChange={(event) => setConfirmation(event.target.value)}
              autoComplete="new-password"
              minLength={8}
              required
              disabled={!token}
              className={authInputClass}
            />
          </label>
          {displayedError && (
            <FormMessage>
              {displayedError}{' '}
              {effectiveError === 'token' && (
                <Link href="/forgot-password" className="font-medium underline underline-offset-4">
                  {t('reset.request.new')}
                </Link>
              )}
            </FormMessage>
          )}
          <Button type="submit" size="lg" className="w-full" disabled={busy || !token || !password || !confirmation}>
            {busy ? t('reset.saving') : t('reset.save')}
          </Button>
        </form>
      )}
      {success && <FormMessage tone="success">{t('reset.success.session')}</FormMessage>}
    </AuthFrame>
  );
}

export default function ResetPasswordPage() {
  return (
    <Suspense fallback={null}>
      <ResetPasswordContent />
    </Suspense>
  );
}
