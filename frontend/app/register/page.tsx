'use client';

import { FormEvent, useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { AuthClientError, register } from '@/lib/auth';
import { Button } from '@/components/ui/Button';
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
      await register(username.trim(), email.trim(), password);
      router.push('/account');
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
    <main className="mx-auto flex min-h-[70vh] max-w-sm flex-col justify-center px-6 py-16">
      <h1 className="text-2xl font-semibold tracking-display">{t('reg.title')}</h1>
      <p className="mt-2 text-[13px] text-muted-foreground">{t('reg.sub')}</p>
      <form onSubmit={onSubmit} className="mt-8 space-y-4">
        <input
          value={username}
          onChange={(e) => setUsername(e.target.value)}
          placeholder={t('reg.username')}
          autoComplete="username"
          className="h-11 w-full rounded-md border border-white/15 bg-white/5 px-4 text-[14px] text-white placeholder:text-white/50"
        />
        <input
          type="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder="Email"
          autoComplete="email"
          className="h-11 w-full rounded-md border border-white/15 bg-white/5 px-4 text-[14px] text-white placeholder:text-white/50"
        />
        <input
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          placeholder={t('reg.password')}
          autoComplete="new-password"
          className="h-11 w-full rounded-md border border-white/15 bg-white/5 px-4 text-[14px] text-white placeholder:text-white/50"
        />
        {error && <p className="text-[13px] text-red-600">{error}</p>}
        <Button type="submit" size="lg" className="w-full" disabled={busy || !username || !email || !password}>
          {busy ? t('reg.creating') : t('reg.create')}
        </Button>
      </form>
      <p className="mt-6 text-center text-[13px] text-muted-foreground">
        {t('reg.have')}{' '}
        <Link href="/login" className="text-primary hover:underline">
          {t('auth.signin')}
        </Link>
      </p>
    </main>
  );
}
