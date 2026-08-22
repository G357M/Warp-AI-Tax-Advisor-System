'use client';

import { FormEvent, useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { AuthClientError, login } from '@/lib/auth';
import { Button } from '@/components/ui/Button';
import { AuthFrame, authInputClass, FormMessage } from '@/components/auth/AuthFrame';
import { useT } from '@/lib/i18n';

export default function LoginPage() {
  const router = useRouter();
  const { t } = useT();
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      await login(username.trim(), password);
      router.push('/account');
    } catch (err: unknown) {
      const key = err instanceof AuthClientError && err.code === 'credentials'
        ? 'auth.err.credentials'
        : err instanceof AuthClientError && err.code === 'verification_required'
          ? 'auth.err.verification'
        : err instanceof AuthClientError && err.code === 'inactive'
          ? 'auth.err.inactive'
          : 'auth.err.service';
      setError(t(key));
    } finally {
      setBusy(false);
    }
  };

  return (
    <AuthFrame title={t('auth.login')} description={t('auth.sub')} footer={(
      <p className="text-center">
        {t('auth.noaccount')}{' '}
        <Link href="/register" className="text-white underline decoration-white/30 underline-offset-4 hover:decoration-primary">
          {t('auth.createfree')}
        </Link>
      </p>
    )}>
      <form onSubmit={onSubmit} className="mt-8 space-y-4">
        <label className="block text-[13px] text-white/75">
          {t('auth.username')}
        <input
          value={username}
          onChange={(e) => setUsername(e.target.value)}
          autoComplete="username"
          required
          className={authInputClass}
        />
        </label>
        <label className="block text-[13px] text-white/75">
          {t('auth.password')}
        <input
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          autoComplete="current-password"
          required
          className={authInputClass}
        />
        </label>
        <div className="flex justify-end">
          <Link href="/forgot-password" className="text-[13px] text-white/65 underline decoration-white/25 underline-offset-4 hover:text-white">
            {t('auth.forgot')}
          </Link>
        </div>
        {error && (
          <FormMessage>
            {error}{' '}
            {error === t('auth.err.verification') && (
              <Link href="/resend-verification" className="font-medium underline underline-offset-4">
                {t('auth.resend.link')}
              </Link>
            )}
          </FormMessage>
        )}
        <Button type="submit" size="lg" className="w-full" disabled={busy || !username || !password}>
          {busy ? t('auth.signing') : t('auth.signin')}
        </Button>
      </form>
    </AuthFrame>
  );
}
