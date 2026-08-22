'use client';

import { Suspense, useEffect, useState } from 'react';
import Link from 'next/link';
import { useSearchParams } from 'next/navigation';
import { AuthFrame, FormMessage } from '@/components/auth/AuthFrame';
import { useT } from '@/lib/i18n';

function CheckEmailContent() {
  const { t } = useT();
  const searchParams = useSearchParams();
  const [purpose] = useState<'verify' | 'reset'>(() => (
    searchParams.get('purpose') === 'reset' ? 'reset' : 'verify'
  ));

  useEffect(() => {
    window.history.replaceState({}, '', '/check-email');
  }, []);

  return (
    <AuthFrame
      title={t('email.sent.title')}
      description={purpose === 'reset' ? t('email.sent.reset') : t('email.sent.verify')}
      footer={(
        <p className="text-center">
          <Link href="/login" className="text-white underline decoration-white/30 underline-offset-4 hover:decoration-primary">
            {t('recovery.back')}
          </Link>
        </p>
      )}
    >
      <FormMessage tone="neutral">{t('email.sent.privacy')}</FormMessage>
      {purpose === 'verify' && (
        <p className="mt-5 text-[13px] text-white/60">
          {t('email.sent.missing')}{' '}
          <Link href="/resend-verification" className="text-white underline decoration-white/30 underline-offset-4">
            {t('auth.resend.link')}
          </Link>
        </p>
      )}
    </AuthFrame>
  );
}

export default function CheckEmailPage() {
  return (
    <Suspense fallback={null}>
      <CheckEmailContent />
    </Suspense>
  );
}
