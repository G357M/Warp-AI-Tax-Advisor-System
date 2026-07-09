import { clsx } from 'clsx';
import { ReactNode } from 'react';

/**
 * Heading carrying the citation tick — the SourceChip's blue bar promoted to
 * a site-wide motif: every section title "cites" the official content below.
 */
interface SectionTitleProps {
  as?: 'h1' | 'h2';
  children: ReactNode;
  className?: string;
}

export function SectionTitle({ as: Tag = 'h2', children, className }: SectionTitleProps) {
  return (
    <Tag className={clsx('flex items-center gap-3', className)}>
      <span aria-hidden className="h-[0.8em] w-[3px] shrink-0 rounded-full bg-primary" />
      <span className="min-w-0">{children}</span>
    </Tag>
  );
}
