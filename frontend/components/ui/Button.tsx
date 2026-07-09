'use client';

import { ButtonHTMLAttributes, forwardRef } from 'react';
import { clsx } from 'clsx';

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  /** primary = Signal Red fill; glass = liquid-glass-strong pill; ghost = text-only. */
  variant?: 'primary' | 'glass' | 'ghost';
  size?: 'md' | 'lg';
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  ({ variant = 'primary', size = 'md', className, ...props }, ref) => (
    <button
      ref={ref}
      className={clsx(
        'inline-flex items-center justify-center gap-2 rounded-full font-body font-medium transition-all duration-300 disabled:cursor-not-allowed disabled:opacity-50',
        variant === 'primary' && 'bg-primary text-white hover:bg-[#B91C1C]',
        variant === 'glass' && 'liquid-glass-strong text-white hover:bg-white/5',
        variant === 'ghost' && 'text-muted-foreground hover:text-foreground',
        size === 'md' && 'h-11 px-5 text-sm',
        size === 'lg' && 'h-12 px-7 text-[15px]',
        className,
      )}
      {...props}
    />
  ),
);
Button.displayName = 'Button';
