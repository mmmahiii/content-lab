import { cn } from '@/lib/cn';

export interface StoryBarsProps {
  /** One entry per segment, 0..1. */
  progress: number[];
  className?: string;
  label?: string;
}

/** Story-style segmented progress (one bar per reel segment). */
export function StoryBars({ progress, className, label = 'Reel progress' }: StoryBarsProps) {
  const total = progress.reduce((sum, p) => sum + p, 0) / Math.max(1, progress.length);
  return (
    <div
      role="progressbar"
      aria-label={label}
      aria-valuemin={0}
      aria-valuemax={100}
      aria-valuenow={Math.round(total * 100)}
      className={cn('flex w-full gap-1.5', className)}
    >
      {progress.map((p, i) => (
        <div key={i} className="h-[3px] flex-1 overflow-hidden rounded-full bg-white/28">
          <div
            data-testid="story-bar-fill"
            className="h-full rounded-full bg-white"
            style={{ width: `${Math.min(1, Math.max(0, p)) * 100}%` }}
          />
        </div>
      ))}
    </div>
  );
}
