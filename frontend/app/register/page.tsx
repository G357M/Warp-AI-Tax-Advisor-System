'use client';

import { FormEvent, useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { AuthClientError, register } from '@/lib/auth';
import { Button } from '@/components/ui/Button';
import { AuthFrame, authInputClass, FormMessage } from '@/components/auth/AuthFrame';
import { useT } from '@/lib/i18n';

export default function RegisterPage() {
  const router = useRouter();
  const { t } = useT();
  const [username, setUsername] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    if (password.length < 8) {
      setError(t('reg.pwshort'));
      return;
    }
    setBusy(true);
    try {
      const result = await register(username.trim(), email.trim(), password);
      router.push(result.verificationRequired ? '/check-email?purpose=verify' : '/account');
    } catch (err: unknown) {
      const key = err instanceof AuthClientError && err.code === 'username_exists'
        ? 'reg.err.username'
        : err instanceof AuthClientError && err.code === 'email_exists'
          ? 'reg.err.email'
          : err instanceof AuthClientError && err.code === 'credentials'
            ? 'auth.err.credentials'
            : err instanceof AuthClientError && err.code === 'inactive'
              ? 'auth.err.inactive'
              : 'reg.err.service';
      setError(t(key));
    } finally {
      setBusy(false);
    }
  };

  return (
    <AuthFrame title={t('reg.title')} description={t('reg.sub')} footer={(
      <p className="text-center">
        {t('reg.have')}{' '}
        <Link href="/login" className="text-white underline decoration-white/30 underline-offset-4 hover:decoration-primary">
          {t('auth.signin')}
        </Link>
      </p>
    )}>
      <form onSubmit={onSubmit} className="mt-8 space-y-4">
        <label className="block text-[13px] text-white/75">
          {t('reg.username')}
        <input
          value={username}
          onChange={(e) => setUsername(e.target.value)}
          autoComplete="username"
          minLength={3}
          required
          className={authInputClass}
        />
        </label>
        <label className="block text-[13px] text-white/75">
          Email
        <input
          type="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          autoComplete="email"
          required
          className={authInputClass}
        />
        </label>
        <label className="block text-[13px] text-white/75">
          {t('reg.password')}
        <input
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          autoComplete="new-password"
          minLength={8}
          required
          className={authInputClass}
        />
        </label>
        {error && <FormMessage>{error}</FormMessage>}
        <Button type="submit" size="lg" className="w-full" disabled={busy || !username || !email || !password}>
          {busy ? t('reg.creating') : t('reg.create')}
        </Button>
      </form>
    </AuthFrame>
  );
}
