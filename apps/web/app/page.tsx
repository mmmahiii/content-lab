import Link from 'next/link';

import { buttonVariants } from '@/components/ui/button';
import { cn } from '@/lib/cn';

const surfaces = [
  {
    href: '/make',
    title: 'Quick Reel',
    body: 'One idea in, a finished vertical reel out. Pick a hook, make three choices, ship it.',
    cta: 'Make a reel',
    ready: true,
  },
  {
    href: null,
    title: 'Studio',
    body: 'Pages, asset packs, plans, review and posting. Not built yet: use the API for now.',
    cta: 'Coming next',
    ready: false,
  },
] as const;

export default function HomePage() {
  return (
    <main className="mx-auto flex min-h-[100dvh] max-w-3xl flex-col justify-center gap-10 px-6 py-16">
      <header className="space-y-3">
        <p className="text-sm font-semibold uppercase tracking-[0.2em] text-fg-subtle">Content Lab</p>
        <h1 className="font-display text-4xl font-black leading-tight sm:text-5xl">
          Make reels people stop for.
        </h1>
        <p className="max-w-xl text-fg-muted">Internal tools for the team. Nothing here posts on its own.</p>
      </header>
      <div className="grid gap-4 sm:grid-cols-2">
        {surfaces.map((surface) => (
          <section
            key={surface.title}
            className={cn(
              'flex flex-col justify-between gap-6 rounded-[var(--radius-card)] border border-line bg-ink-raised p-6',
              !surface.ready && 'opacity-60',
            )}
          >
            <div className="space-y-2">
              <h2 className="text-xl font-bold">{surface.title}</h2>
              <p className="text-sm leading-relaxed text-fg-muted">{surface.body}</p>
            </div>
            {surface.href ? (
              <Link href={surface.href} className={cn(buttonVariants({ variant: 'accent' }), 'self-start')}>
                {surface.cta}
              </Link>
            ) : (
              <span className={cn(buttonVariants({ variant: 'ghost' }), 'self-start')} aria-disabled>
                {surface.cta}
              </span>
            )}
          </section>
        ))}
      </div>
    </main>
  );
}
