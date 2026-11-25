import { describe, expect, it } from 'vitest';

import { composedFor } from './fixtures.test-data';
import { buildTimeline, cardTimeline, reelTimeline, segmentProgress, segmentWindow } from './timelines';

const composed = composedFor({ structure: 'breakdown', energy: 'chill', ending: 'reveal' });

describe('timelines', () => {
  it('hides the in-video progress bar only while building', () => {
    expect(buildTimeline(composed, []).showProgress).toBe(false);
    expect(reelTimeline(composed, []).showProgress).toBe(true);
  });

  it('each card loops the part of the reel its choice changes, for at most 2 s', () => {
    const structure = cardTimeline(composed, 'structure', []);
    const ending = cardTimeline(composed, 'ending', []);
    expect(structure.overlays[0].text).toBe(composed.overlay_timeline[1].text);
    expect(ending.overlays[0].text).toBe(composed.overlay_timeline.at(-1)!.text);
    expect(structure.durationInFrames).toBeLessThanOrEqual(60);
    expect(structure.showProgress).toBe(false);
  });

  it('reports story bar progress per segment', () => {
    const first = segmentWindow(composed, 'firstBeat');
    const mid = Math.round((first.startFrame + first.endFrame) / 2);
    const bars = segmentProgress(composed, 1, 'firstBeat', mid);
    expect(bars[0]).toBe(1);
    expect(bars[1]).toBeCloseTo(0.5, 1);
    expect(bars.slice(2)).toEqual([0, 0]);
  });
});
