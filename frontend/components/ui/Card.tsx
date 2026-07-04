import { HTMLAttributes } from 'react';
import { clsx } from 'clsx';

export function Card({ className, ...props }: HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={clsx('rounded-lg border bg-white shadow-[0_1px_2px_rgba(0,0,0,0.04)] dark:bg-muted', className)}
      {...props}
    />
  );
}
