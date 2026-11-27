'use client';

import { Player, type PlayerRef } from '@remotion/player';
import { forwardRef, useEffect, useImperativeHandle, useRef } from 'react';

import { KineticReel, type ReelTimeline } from '@content-lab/reel-templates';

import { cn } from '@/lib/cn';

export interface ReelPlayerProps {
  timeline: ReelTimeline;
  /** Loop forever (cards, hook reel, ship). */
  loop?: boolean;
  /** Start playing as soon as mounted / when the timeline changes. */
  autoPlay?: boolean;
  className?: string;
  onFrame?: (frame: number) => void;
  onEnded?: () => void;
}

/** KineticReel in @remotion/player, chrome-free: the app owns every control. */
export const ReelPlayer = forwardRef<PlayerRef | null, ReelPlayerProps>(function ReelPlayer(
  { timeline, loop = false, autoPlay = true, className, onFrame, onEnded },
  ref,
) {
  const player = useRef<PlayerRef>(null);
  useImperativeHandle(ref, () => player.current as PlayerRef, []);
  const handlers = useRef({ onFrame, onEnded });
  handlers.current = { onFrame, onEnded };

  useEffect(() => {
    const p = player.current;
    if (!p) return;
    const frame = (e: { detail: { frame: number } }) => handlers.current.onFrame?.(e.detail.frame);
    const ended = () => handlers.current.onEnded?.();
    p.addEventListener('frameupdate', frame);
    p.addEventListener('ended', ended);
    return () => {
      p.removeEventListener('frameupdate', frame);
      p.removeEventListener('ended', ended);
    };
  }, []);

  return (
    // Letterbox bands (taller phones than 9:16) take the reel's own backdrop, so the frame
    // reads as full-bleed while the reel itself stays uncropped: exactly what exports.
    <div
      className={cn('pointer-events-none relative h-full w-full', className)}
      style={{ background: `linear-gradient(180deg, ${timeline.backdrop[0]}, ${timeline.backdrop[1]})` }}
    >
      <Player
        ref={player}
        component={KineticReel}
        inputProps={timeline}
        durationInFrames={timeline.durationInFrames}
        fps={timeline.fps}
        compositionWidth={timeline.width}
        compositionHeight={timeline.height}
        loop={loop}
        autoPlay={autoPlay}
        controls={false}
        clickToPlay={false}
        doubleClickToFullscreen={false}
        spaceKeyToPlayOrPause={false}
        moveToBeginningWhenEnded={false}
        initiallyMuted
        acknowledgeRemotionLicense
        style={{ width: '100%', height: '100%' }}
      />
    </div>
  );
});
