import { describe, expect, it } from 'vitest';
import { operationsBaseline } from './fixtures';
import { fromPipelineOverlays } from './timeline';

describe('fromPipelineOverlays', () => {
  it('converts seconds to half-open frame intervals on one clock', () => {
    expect(operationsBaseline.durationInFrames).toBe(288);
    expect(operationsBaseline.overlays.map((o) => [o.startFrame, o.endFrame])).toEqual([
      [0, 72],
      [72, 144],
      [144, 216],
      [216, 288],
    ]);
    expect(operationsBaseline.overlays.map((o) => o.role)).toEqual(['hook', 'value', 'value', 'cta']);
  });

  it('rejects overlapping overlays instead of stacking them', () => {
    expect(() =>
      fromPipelineOverlays(
        [
          { text: 'a', emphasis: 'hook', start_seconds: 0, end_seconds: 3 },
          { text: 'b', emphasis: 'value', start_seconds: 2, end_seconds: 4 },
        ],
        { fps: 30, durationSeconds: 4 },
      ),
    ).toThrow(/overlap/);
  });

  it('rejects unknown emphasis values', () => {
    expect(() =>
      fromPipelineOverlays([{ text: 'a', emphasis: 'mystery', start_seconds: 0, end_seconds: 1 }], {
        fps: 30,
        durationSeconds: 1,
      }),
    ).toThrow(/Unknown overlay emphasis/);
  });
});
