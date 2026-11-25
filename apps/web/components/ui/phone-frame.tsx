import type { ReactNode } from 'react';

import { cn } from '@/lib/cn';

/**
 * Full-screen on phones; a centred 9:16 device frame on larger screens, with an optional
 * side panel (keyboard help) next to it.
 */
export function PhoneFrame({
  children,
  aside,
  className,
}: {
  children: ReactNode;
  aside?: ReactNode;
  className?: string;
}) {
  return (
    <div className="flex min-h-[100dvh] w-full items-center justify-center gap-10 bg-ink sm:p-6">
      <div
        className={cn(
          'relative h-[100dvh] w-full overflow-hidden bg-ink-sunken',
          'sm:aspect-[9/16] sm:h-[min(92dvh,900px)] sm:w-auto sm:rounded-[var(--radius-phone)] sm:border sm:border-line-strong sm:shadow-[0_40px_120px_rgba(0,0,0,0.6)]',
          className,
        )}
        data-testid="phone-frame"
      >
        {children}
      </div>
      {aside ? <aside className="hidden w-64 shrink-0 lg:block">{aside}</aside> : null}
    </div>
  );
}
