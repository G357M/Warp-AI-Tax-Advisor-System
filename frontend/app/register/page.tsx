'use client';

import { FormEvent, useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { register } from '@/lib/auth';
import { Button } from '@/components/ui/Button';

export default function RegisterPage() {
  const router = useRouter();
  const [username, setUsername] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    if (password.length < 8) {
      setError('Пароль — минимум 8 символов.');
      return;
    }
    setBusy(true);
    try {
      await register(username.trim(), email.trim(), password);
      router.push('/account');
    } catch (err: any) {
      setError(err.message);
    } finally {
      setBusy(false);
    }
  };

  return (
    <main className="mx-auto flex min-h-[70vh] max-w-sm flex-col justify-center px-6 py-16">
      <h1 className="text-2xl font-semibold tracking-display">Регистрация</h1>
      <p className="mt-2 text-[13px] text-muted-foreground">
        Бесплатный тариф: 5 вопросов в день с точными источниками.
      </p>
      <form onSubmit={onSubmit} className="mt-8 space-y-4">
        <input
          value={username}
          onChange={(e) => setUsername(e.target.value)}
          placeholder="Логин (от 3 символов)"
          autoComplete="username"
          className="h-11 w-full rounded-md border bg-white px-4 text-[14px] placeholder:text-muted-foreground"
        />
        <input
          type="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder="Email"
          autoComplete="email"
          className="h-11 w-full rounded-md border bg-white px-4 text-[14px] placeholder:text-muted-foreground"
        />
        <input
          type="password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          placeholder="Пароль (минимум 8 символов)"
          autoComplete="new-password"
          className="h-11 w-full rounded-md border bg-white px-4 text-[14px] placeholder:text-muted-foreground"
        />
        {error && <p className="text-[13px] text-red-600">{error}</p>}
        <Button type="submit" size="lg" className="w-full" disabled={busy || !username || !email || !password}>
          {busy ? 'Создаю…' : 'Создать аккаунт'}
        </Button>
      </form>
      <p className="mt-6 text-center text-[13px] text-muted-foreground">
        Уже есть аккаунт?{' '}
        <Link href="/login" className="text-primary hover:underline">
          Войти
        </Link>
      </p>
    </main>
  );
}
