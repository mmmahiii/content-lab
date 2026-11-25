import { describe, expect, it } from 'vitest';
import { operationsBaseline, quickReelFixtures, ratatouilleAssets } from './fixtures';
import { parseReelTimeline } from './schema';

describe('reelTimelineSchema', () => {
  it('accepts every fixture timeline unchanged', () => {
    for (const t of [operationsBaseline, ratatouilleAssets, ...Object.values(quickReelFixtures)]) {
      expect(parseReelTimeline(structuredClone(t))).toEqual(t);
    }
  });

  it('rejects unknown keys, bad colours and overruns', () => {
    const t = structuredClone(quickReelFixtures.punchy);
    expect(() => parseReelTimeline({ ...t, script: 'x' })).toThrow();
    expect(() => parseReelTimeline({ ...t, backdrop: ['red;background:url(x)', '#000'] })).toThrow();
    const late = structuredClone(t);
    late.overlays[0].endFrame = t.durationInFrames + 1;
    expect(() => parseReelTimeline(late)).toThrow(/past the end/);
    expect(() => parseReelTimeline({ ...t, durationInFrames: 30 * 600 })).toThrow(/longer than/);
  });
});
