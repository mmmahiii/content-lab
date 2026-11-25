'use client';

import type { PlayerRef } from '@remotion/player';
import { AnimatePresence, motion } from 'framer-motion';
import { useEffect, useMemo, useRef, useState } from 'react';

import {
  captionExitFrames,
  energyStyle,
  type FrameWindow,
  type QuickReelVisual,
  type ReelTimeline,
} from '@content-lab/reel-templates';

import { StoryBars } from '@/components/ui/story-bars';

import { completedSegments, MOMENT_AFTER, SEGMENTS, type Phase, type Segment } from '../_lib/machine';
import { buildTimeline, hookReelTimeline, segmentWindow } from '../_lib/timelines';
import type { ComposedReel, HookCandidate } from '../_lib/types';
import { ChoiceSheet, type ChoiceSheetProps } from './ChoiceSheet';
import { ReelPlayer } from './ReelPlayer';

/** Last frame where the segment's caption is fully on screen (before its exit fade). */
export function holdFrame(timeline: ReelTimeline, window: FrameWindow): number {
  const last = timeline.overlays.find((o) => o.endFrame === window.endFrame);
  const exit = last
    ? captionExitFrames(last.endFrame - last.startFrame, energyStyle(timeline.energy))
    : 0;
  return Math.max(window.startFrame, window.endFrame - 1 - exit);
}

/** The segment that ends at a choice moment (what is on screen while choosing). */
function segmentBefore(phase: Phase): Segment | null {
  if (phase.name === 'playing') return phase.segment;
  if (phase.name === 'choosing') {
    return SEGMENTS.find((s) => MOMENT_AFTER[s] === phase.moment) ?? null;
  }
  return null;
}

interface Run {
  key: string;
  segment: Segment;
  timeline: ReelTimeline;
  window: FrameWindow;
  hold: number;
}

export interface BuildStageProps {
  phase: Phase;
  /** Composed reel for the choices so far (defaults for the rest); undefined while loading. */
  composed: ComposedReel | undefined;
  hook: HookCandidate;
  visuals: QuickReelVisual[];
  choice: Omit<ChoiceSheetProps, 'moment'> | null;
  onSegmentEnded: (segment: Segment) => void;
}

/** ③-④ Plays the reel segment by segment; pauses on a cliffhanger for each choice. */
export function BuildStage({ phase, composed, hook, visuals, choice, onSegmentEnded }: BuildStageProps) {
  const player = useRef<PlayerRef | null>(null);
  const [frame, setFrame] = useState(0);
  const [run, setRun] = useState<Run | null>(null);
  const ended = useRef<string | null>(null);
  const segment = segmentBefore(phase);
  const playing = phase.name === 'playing';

  const fallback = useMemo(
    () => ({ ...hookReelTimeline(hook.overlay_text, visuals), energy: undefined }),
    [hook.overlay_text, visuals],
  );
  const timeline = useMemo(
    () => (composed ? buildTimeline(composed, visuals) : null),
    [composed, visuals],
  );

  // Fix the timeline for a segment when it starts, so data arriving mid-segment never
  // restarts playback. The hook may start on a hook-only clip while branches load.
  const runKey = `${phase.name}:${segment}`;
  useEffect(() => {
    if (!segment) return;
    if (run?.key === runKey) return;
    let next: Run | null = null;
    if (timeline && composed) {
      const window = segmentWindow(composed, segment);
      next = { key: runKey, segment, timeline, window, hold: holdFrame(timeline, window) };
    } else if (segment === 'hook') {
      const window = { startFrame: 0, endFrame: fallback.durationInFrames };
      next = { key: runKey, segment, timeline: fallback, window, hold: holdFrame(fallback, window) };
    }
    if (next) setRun(next);
  }, [runKey, segment, timeline, composed, fallback, run?.key]);

  // Start playback for a new run, or hold its last frame while choosing.
  useEffect(() => {
    const p = player.current;
    if (!p || !run) return;
    if (playing) {
      ended.current = null;
      p.seekTo(run.window.startFrame);
      p.play();
    } else {
      p.pause();
      p.seekTo(run.hold);
    }
  }, [run, playing]);

  const onFrame = (f: number) => {
    setFrame(f);
    if (!run || !playing || ended.current === run.key) return;
    if (f >= run.hold) {
      ended.current = run.key;
      player.current?.pause();
      player.current?.seekTo(run.hold);
      onSegmentEnded(run.segment);
    }
  };

  const completed = completedSegments(phase);
  const bars = SEGMENTS.map((name, i) => {
    if (i < completed) return 1;
    if (!run || name !== run.segment || !playing) return 0;
    const span = Math.max(1, run.hold - run.window.startFrame);
    return Math.min(1, Math.max(0, (frame - run.window.startFrame) / span));
  });

  return (
    <div className="absolute inset-0" data-testid="build-stage">
      {run ? <ReelPlayer ref={player} timeline={run.timeline} autoPlay={false} onFrame={onFrame} /> : null}
      <AnimatePresence>
        {phase.name === 'choosing' ? (
          <motion.div
            key="dim"
            className="absolute inset-0 bg-gradient-to-b from-black/30 via-black/55 to-black/85"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.35 }}
          />
        ) : null}
      </AnimatePresence>
      <div className="absolute inset-x-0 top-0 px-4 pt-[max(0.75rem,env(safe-area-inset-top))]">
        <StoryBars progress={bars} />
      </div>
      <AnimatePresence>
        {phase.name === 'choosing' && choice ? (
          <ChoiceSheet key={phase.moment} moment={phase.moment} {...choice} />
        ) : null}
      </AnimatePresence>
    </div>
  );
}
