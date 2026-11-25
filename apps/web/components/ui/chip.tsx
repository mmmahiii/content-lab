import { forwardRef, type ButtonHTMLAttributes } from 'react';

import { cn } from '@/lib/cn';

export interface ChipProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  selected?: boolean;
}

/** A tappable pill: suggestions, page picker, "change one thing" targets. */
export const Chip = forwardRef<HTMLButtonElement, ChipProps>(
  ({ className, selected = false, type, ...props }, ref) => (
    <button
      ref={ref}
      type={type ?? 'button'}
      aria-pressed={selected}
      className={cn(
        'inline-flex h-10 shrink-0 items-center gap-2 rounded-full border px-4 text-sm font-medium transition-colors duration-150 active:scale-[0.97]',
        selected
          ? 'border-fg bg-fg text-ink'
          : 'border-line bg-white/6 text-fg hover:border-line-strong hover:bg-white/12',
        className,
      )}
      {...props}
    />
  ),
);
Chip.displayName = 'Chip';
