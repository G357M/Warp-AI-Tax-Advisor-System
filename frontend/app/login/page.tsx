'use client';

import { FormEvent, useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { login } from '@/lib/auth';
import { Button } from '@/components/ui/Button';
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
    } catch (err: any) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <main className="mx-auto flex min-h-[70vh] max-w-sm flex-col justify-center px-6 py-16">
      <h1 className="text-2xl font-semibold tracking-display">{t('auth.login')}</h1>
      <form onSubmit={onSubmit} className="mt-8 space-y-4">
        <input
          value={username}
          onChange={(e) => setUsername(e.target.value)}
          placeholder={t('auth.username')}
          autoComplete="username"
          className="h-11 w-full rounded-md border bg-white px-4 text-[14px] placeholder:text-muted-foreground"
        />
        <input
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          placeholder={t('auth.password')}
          autoComplete="current-password"
          className="h-11 w-full rounded-md border bg-white px-4 text-[14px] placeholder:text-muted-foreground"
        />
        {error && <p className="text-[13px] text-red-600">{error}</p>}
        <Button type="submit" size="lg" className="w-full" disabled={busy || !username || !password}>
          {busy ? t('auth.signing') : t('auth.signin')}
        </Button>
      </form>
      <p className="mt-6 text-center text-[13px] text-muted-foreground">
        {t('auth.noaccount')}{' '}
        <Link href="/register" className="text-primary hover:underline">
          {t('auth.createfree')}
        </Link>
      </p>
    </main>
  );
}
