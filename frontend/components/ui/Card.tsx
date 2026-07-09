import { HTMLAttributes } from 'react';
import { clsx } from 'clsx';

/** Liquid-glass surface — the shared Modern Ecosystem card. */
export function Card({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return <div className={clsx('liquid-glass rounded-2xl', className)} {...props} />;
}
