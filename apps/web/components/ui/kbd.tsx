import type { HTMLAttributes } from 'react';

import { cn } from '@/lib/cn';

export function Kbd({ className, ...props }: HTMLAttributes<HTMLElement>) {
  return (
    <kbd
      className={cn(
        'inline-flex h-6 min-w-6 items-center justify-center rounded-md border border-line-strong bg-white/8 px-1.5 font-sans text-xs font-semibold text-fg',
        className,
      )}
      {...props}
    />
  );
}
