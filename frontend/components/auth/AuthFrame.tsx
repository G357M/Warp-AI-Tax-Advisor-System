import { ReactNode } from 'react';

export const authInputClass =
  'mt-2 h-12 w-full rounded-xl border border-white/15 bg-white/[0.045] px-4 text-[15px] text-white outline-none transition-colors placeholder:text-white/45 hover:border-white/25 focus:border-primary';

export function AuthFrame({
  title,
  description,
  children,
  footer,
}: {
  title: string;
  description?: string;
  children: ReactNode;
  footer?: ReactNode;
}) {
  return (
    <main className="relative isolate mx-auto flex min-h-[68vh] max-w-page items-center overflow-hidden px-6 py-16">
      <div aria-hidden className="hero-mesh pointer-events-none absolute inset-0 -z-10 opacity-70" />
      <section className="w-full max-w-md">
        <div className="mb-5 flex items-center gap-2 text-[13px] text-white/65">
          <span className="h-3 w-[3px] rounded-full bg-primary" />
          Tax Advisor · Modern Ecosystem
        </div>
        <h1 className="max-w-[12ch] text-balance font-heading text-4xl italic leading-[0.98] tracking-[-0.025em] text-white sm:text-5xl">
          {title}
        </h1>
        {description && (
          <p className="mt-4 max-w-[56ch] text-[14px] font-light leading-relaxed text-white/65">
            {description}
          </p>
        )}
        <div className="mt-9">{children}</div>
        {footer && <div className="mt-7 text-[13px] text-white/60">{footer}</div>}
      </section>
    </main>
  );
}

export function FormMessage({
  children,
  tone = 'error',
}: {
  children: ReactNode;
  tone?: 'error' | 'success' | 'neutral';
}) {
  const toneClass = tone === 'error'
    ? 'border-error-border bg-error text-error-foreground'
    : tone === 'success'
      ? 'border-emerald-800/70 bg-emerald-950/45 text-emerald-200'
      : 'border-white/15 bg-white/5 text-white/70';
  return (
    <p
      aria-live="polite"
      className={`rounded-xl border px-4 py-3 text-[13px] leading-relaxed ${toneClass}`}
    >
      {children}
    </p>
  );
}
