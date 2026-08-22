'use client';

import { Suspense, useEffect, useRef, useState } from 'react';
import Link from 'next/link';
import { useSearchParams } from 'next/navigation';
import { verifyEmail } from '@/lib/auth';
import { AuthFrame, FormMessage } from '@/components/auth/AuthFrame';
import { useT } from '@/lib/i18n';

type VerifyState = 'working' | 'success' | 'error';

function VerifyEmailContent() {
  const { t } = useT();
  const searchParams = useSearchParams();
  const [token] = useState(() => searchParams.get('token'));
  const started = useRef(false);
  const [state, setState] = useState<VerifyState>('working');

  useEffect(() => {
    if (started.current) return;
    started.current = true;
    window.history.replaceState({}, '', '/verify-email');
    if (!token) return;
    verifyEmail(token).then(
      () => setState('success'),
      () => setState('error'),
    );
  }, [token]);

  const effectiveState: VerifyState = token ? state : 'error';

  return (
    <AuthFrame
      title={effectiveState === 'success' ? t('verify.success.title') : t('verify.title')}
      description={effectiveState === 'working' ? t('verify.working') : undefined}
      footer={effectiveState === 'success' ? (
        <p className="text-center">
          <Link href="/login" className="text-white underline decoration-white/30 underline-offset-4 hover:decoration-primary">
            {t('auth.signin')}
          </Link>
        </p>
      ) : undefined}
    >
      {effectiveState === 'working' && <div className="h-1 w-24 animate-pulse rounded-full bg-primary" aria-hidden />}
      {effectiveState === 'success' && <FormMessage tone="success">{t('verify.success.body')}</FormMessage>}
      {effectiveState === 'error' && (
        <FormMessage>
          {t('verify.error')}{' '}
          <Link href="/resend-verification" className="font-medium underline underline-offset-4">
            {t('auth.resend.link')}
          </Link>
        </FormMessage>
      )}
    </AuthFrame>
  );
}

export default function VerifyEmailPage() {
  return (
    <Suspense fallback={null}>
      <VerifyEmailContent />
    </Suspense>
  );
}
