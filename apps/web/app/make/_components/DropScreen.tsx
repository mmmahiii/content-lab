'use client';

import type { ReelTimeline } from '@content-lab/reel-templates';

import type { RenderJobView } from '../_lib/types';
import { ReelPlayer } from './ReelPlayer';

/**
 * ⑤ The drop: the finished reel, start to finish. The MP4 is built while it plays; a thin
 * bar at the bottom shows its progress so Download being ready at Ship is no surprise.
 */
export function DropScreen({
  timeline,
  dropCount,
  render,
  onEnded,
}: {
  timeline: ReelTimeline;
  dropCount: number;
  render?: RenderJobView | null;
  onEnded: () => void;
}) {
  const ready = render?.status === 'done';
  const progress = ready ? 1 : (render?.progress ?? 0);
  return (
    <div className="absolute inset-0" data-testid="drop">
      <ReelPlayer key={dropCount} timeline={timeline} onEnded={onEnded} />
      {render && render.status !== 'failed' && (
        <div
          className="pointer-events-none absolute inset-x-6 bottom-[max(1rem,env(safe-area-inset-bottom))] flex items-center gap-2 text-xs text-white/80"
          aria-live="polite"
          data-testid="drop-export-progress"
        >
          <div className="h-1 flex-1 overflow-hidden rounded-full bg-white/20">
            <div
              className="h-full rounded-full bg-white/80 transition-[width] duration-300"
              style={{ width: `${Math.round(progress * 100)}%` }}
            />
          </div>
          <span>{ready ? 'MP4 ready' : 'Preparing MP4'}</span>
        </div>
      )}
    </div>
  );
}
