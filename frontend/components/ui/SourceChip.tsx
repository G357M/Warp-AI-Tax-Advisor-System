'use client';

/**
 * SourceChip — the signature element of the design system.
 *
 * Every answer the product gives rests on an official document; this chip is
 * that document made visible: a liquid-glass card with the red citation tick,
 * the Georgian title of the act and, when known, its type. Reused in the
 * chat, the hero demo and the law timeline.
 */
import { clsx } from 'clsx';
import { useT } from '@/lib/i18n';

/** Known document types → dictionary keys; unknown types render as-is. */
const TYPE_KEYS: Record<string, string> = {
  law: 'doc.law',
  regulation: 'doc.regulation',
  court_decision: 'doc.court_decision',
  guideline: 'doc.guideline',
  news: 'doc.news',
  bill: 'doc.bill',
};

interface SourceChipProps {
  title: string;
  documentType?: string;
  url?: string;
  articleRef?: string | null;
  pointRef?: string | null;
  documentNumber?: string | null;
  datePublished?: string | null;
  dateEffective?: string | null;
  className?: string;
}

export function SourceChip({
  title,
  documentType,
  url,
  articleRef,
  pointRef,
  documentNumber,
  datePublished,
  dateEffective,
  className,
}: SourceChipProps) {
  const { t } = useT();
  const typeKey = TYPE_KEYS[documentType ?? ''];
  const label = typeKey ? t(typeKey) : documentType;
  const pointNumber = pointRef?.includes('.') ? pointRef.split('.').slice(1).join('.') : pointRef;
  const details = [
    label,
    articleRef ? t('doc.article', { n: articleRef }) : null,
    pointNumber ? t('doc.point', { n: pointNumber }) : null,
    documentNumber ? t('doc.number', { n: documentNumber }) : null,
    dateEffective
      ? t('doc.effective', { d: dateEffective })
      : datePublished
        ? t('doc.published', { d: datePublished })
        : null,
  ].filter(Boolean).join(' · ');
  const body = (
    <span className="flex items-start gap-2.5">
      <span aria-hidden className="mt-[5px] h-3.5 w-[3px] shrink-0 rounded-full bg-primary" />
      <span className="min-w-0">
        <span className="block truncate text-[13px] font-medium leading-5 text-white">{title}</span>
        {details && <span className="block truncate text-xs text-muted-foreground">{details}</span>}
      </span>
    </span>
  );
  const base = clsx(
    'liquid-glass block max-w-full rounded-xl px-3.5 py-2.5 text-left',
    url && 'transition-all duration-300 hover:bg-white/5',
    className,
  );
  if (url) {
    return (
      <a href={url} target="_blank" rel="noopener noreferrer" className={base} title={title}>
        {body}
      </a>
    );
  }
  return (
    <span className={base} title={title}>
      {body}
    </span>
  );
}
