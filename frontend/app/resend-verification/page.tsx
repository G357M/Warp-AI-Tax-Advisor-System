'use client';

import { FormEvent, useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { resendVerification } from '@/lib/auth';
import { AuthFrame, authInputClass, FormMessage } from '@/components/auth/AuthFrame';
import { Button } from '@/components/ui/Button';
import { useT } from '@/lib/i18n';

export default function ResendVerificationPage() {
  const router = useRouter();
  const { t } = useT();
  const [email, setEmail] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(false);

  const onSubmit = async (event: FormEvent) => {
    event.preventDefault();
    setError(false);
    setBusy(true);
    try {
      await resendVerification(email.trim());
      router.push('/check-email?purpose=verify');
    } catch {
      setError(true);
    } finally {
      setBusy(false);
    }
  };

  return (
    <AuthFrame
      title={t('verify.resend.title')}
      description={t('verify.resend.sub')}
      footer={(
        <p className="text-center">
          <Link href="/login" className="text-white underline decoration-white/30 underline-offset-4 hover:decoration-primary">
            {t('recovery.back')}
          </Link>
        </p>
      )}
    >
      <form onSubmit={onSubmit} className="space-y-5">
        <label className="block text-[13px] text-white/75">
          Email
          <input
            type="email"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            autoComplete="email"
            required
            className={authInputClass}
          />
        </label>
        {error && <FormMessage>{t('recovery.err.service')}</FormMessage>}
        <Button type="submit" size="lg" className="w-full" disabled={busy || !email}>
          {busy ? t('recovery.sending') : t('verify.resend.send')}
        </Button>
      </form>
    </AuthFrame>
  );
}
