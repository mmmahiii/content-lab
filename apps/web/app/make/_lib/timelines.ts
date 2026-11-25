import {
  fromComposedReel,
  hookTimeline,
  loopWindow,
  previewWindow,
  quickReelSegments,
  type FrameWindow,
  type QuickReelVisual,
  type ReelTimeline,
} from '@content-lab/reel-templates';

import type { Segment } from './machine';
import type { ComposedReel, Moment } from './types';

/** The full reel as exported (in-video progress bar on). */
export function reelTimeline(composed: ComposedReel, visuals: QuickReelVisual[]): ReelTimeline {
  return fromComposedReel(composed, { visuals, showProgress: true });
}

/** While building, the app draws its own story bars, so the in-video bar is hidden. */
export function buildTimeline(composed: ComposedReel, visuals: QuickReelVisual[]): ReelTimeline {
  return fromComposedReel(composed, { visuals, showProgress: false });
}

export function segmentWindow(composed: ComposedReel, segment: Segment): FrameWindow {
  return quickReelSegments(composed)[segment];
}

/** Which segment each moment's cards preview: the part of the reel that choice changes. */
const PREVIEWED: Record<Moment, Segment> = {
  structure: 'firstBeat',
  energy: 'restBeats',
  ending: 'ending',
};

/** A ~2 s looping mini-preview of what tapping a card would play next. */
export function cardTimeline(
  composed: ComposedReel,
  moment: Moment,
  visuals: QuickReelVisual[],
): ReelTimeline {
  const timeline = buildTimeline(composed, visuals);
  return loopWindow(timeline, previewWindow(segmentWindow(composed, PREVIEWED[moment])));
}

export function hookReelTimeline(overlayText: string, visuals: QuickReelVisual[]): ReelTimeline {
  return hookTimeline(overlayText, { visuals: visuals.slice(0, 1), energy: 'punchy' });
}

/** Motion while waiting (seed preview, hooks loading): the topic as kinetic text. */
export function idleTimeline(text: string, visuals: QuickReelVisual[]): ReelTimeline {
  return hookTimeline(text, { visuals: visuals.slice(0, 1), energy: 'chill', seconds: 4 });
}

/** Per-segment progress (0..1) for the story bars, given the current frame. */
export function segmentProgress(
  composed: ComposedReel,
  completed: number,
  current: Segment | null,
  frame: number,
): number[] {
  const segments = quickReelSegments(composed);
  const order: Segment[] = ['hook', 'firstBeat', 'restBeats', 'ending'];
  return order.map((name, i) => {
    if (i < completed) return 1;
    if (name !== current) return 0;
    const w = segments[name];
    return Math.min(1, Math.max(0, (frame - w.startFrame) / Math.max(1, w.endFrame - w.startFrame)));
  });
}
