'use client';

import type { ReelTimeline } from '@content-lab/reel-templates';

import { ReelPlayer } from './ReelPlayer';

/** ⑤ The drop: the finished reel, start to finish, nothing on top. */
export function DropScreen({
  timeline,
  dropCount,
  onEnded,
}: {
  timeline: ReelTimeline;
  dropCount: number;
  onEnded: () => void;
}) {
  return (
    <div className="absolute inset-0" data-testid="drop">
      <ReelPlayer key={dropCount} timeline={timeline} onEnded={onEnded} />
    </div>
  );
}
