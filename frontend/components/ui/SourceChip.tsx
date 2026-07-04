/**
 * SourceChip — the signature element of the design system.
 *
 * Every answer the product gives rests on an official document; this chip is
 * that document made visible: a quiet card with a blue citation tick, the
 * Georgian title of the act and, when known, its type. Reused in the chat,
 * the hero demo and (later) the law timeline.
 */
import { clsx } from 'clsx';

const TYPE_LABELS: Record<string, string> = {
  law: 'закон',
  regulation: 'подзаконный акт',
  court_decision: 'решение по спору',
  guideline: 'разъяснение',
  news: 'новости законодательства',
  bill: 'законопроект',
};

interface SourceChipProps {
  title: string;
  documentType?: string;
  url?: string;
  className?: string;
}

export function SourceChip({ title, documentType, url, className }: SourceChipProps) {
  const label = TYPE_LABELS[documentType ?? ''] ?? documentType;
  const body = (
    <span className="flex items-start gap-2.5">
      <span aria-hidden className="mt-[5px] h-3.5 w-[3px] shrink-0 rounded-full bg-primary" />
      <span className="min-w-0">
        <span className="block truncate text-[13px] font-medium leading-5">{title}</span>
        {label && <span className="block text-xs text-muted-foreground">{label}</span>}
      </span>
    </span>
  );
  const base = clsx(
    'block max-w-full rounded-md border bg-white px-3.5 py-2.5 text-left dark:bg-muted',
    url && 'transition-colors hover:border-primary/40',
    className,
  );
  if (url) {
    return (
      <a href={url} target="_blank" rel="noopener noreferrer" className={base}>
        {body}
      </a>
    );
  }
  return <span className={base}>{body}</span>;
}
