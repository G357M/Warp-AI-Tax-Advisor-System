import { clsx } from 'clsx';
import { ReactNode } from 'react';

/**
 * Section heading carrying the citation tick — the SourceChip's red bar
 * promoted to a site-wide motif: every section title "cites" the official
 * content below. Headings are Instrument Serif italic per the Modern
 * Ecosystem type system.
 */
interface SectionTitleProps {
  as?: 'h1' | 'h2';
  children: ReactNode;
  className?: string;
  tickClassName?: string;
}

export function SectionTitle({ as: Tag = 'h2', children, className, tickClassName }: SectionTitleProps) {
  return (
    <Tag
      className={clsx(
        'flex items-center gap-4 font-heading italic leading-[0.95] tracking-tight text-white',
        className,
      )}
    >
      <span
        aria-hidden
        className={clsx('h-[0.85em] w-[4px] shrink-0 rounded-full', tickClassName ?? 'bg-primary')}
      />
      <span className="min-w-0">{children}</span>
    </Tag>
  );
}
