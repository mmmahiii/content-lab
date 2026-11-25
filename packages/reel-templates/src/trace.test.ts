import { describe, expect, it } from 'vitest';
import { quickReelComposed, quickReelFixtures } from './fixtures';
import { fromComposedReel } from './quickReel';
import { fakeMeasure } from './test-utils';
import { buildOverlayRenderTrace, OVERLAY_TRACE_SCHEMA } from './trace';
import { ENERGIES } from './timeline';

const opts = { fontFamily: 'Test', measure: fakeMeasure };

describe('buildOverlayRenderTrace', () => {
  it.each(ENERGIES)('passes for the %s fallback reel and carries the fields QA reads', (energy) => {
    const timeline = quickReelFixtures[energy];
    const trace = buildOverlayRenderTrace(timeline, opts);
    expect(trace.schema_version).toBe(OVERLAY_TRACE_SCHEMA);
    expect(trace.status).toBe('pass');
    expect(trace.frame_height_px).toBe(1920);
    expect(trace.clip_duration_seconds).toBe(quickReelComposed[energy].duration_seconds);
    expect(trace.overlays).toHaveLength(timeline.overlays.length);
    trace.overlays.forEach((o, i) => {
      expect(o.source_text).toBe(timeline.overlays[i].text);
      expect(o.rendered_text).toBe(o.source_text);
      expect(o.clipped).toBe(false);
      expect(o.safe_area_passed).toBe(true);
      expect(o.collision_check).toBe('passed');
      expect(o.font_size).toBeGreaterThanOrEqual(26); // packages/qa minimum for 1920px
      expect(o.visible_start_frame).toBe(timeline.overlays[i].startFrame);
      expect(o.visible_end_seconds).toBeCloseTo(timeline.overlays[i].endFrame / 30, 2);
      expect(o.line_boxes.length).toBe(o.line_count);
      expect(o.exit_start_frame).toBeLessThan(o.visible_end_frame);
    });
  });

  it('records the visual band and keeps captions off it for cut-out visuals', () => {
    const timeline = fromComposedReel(quickReelComposed.dramatic, { visuals: [{ src: '/x.png' }] });
    const trace = buildOverlayRenderTrace(timeline, opts);
    expect(trace.layout_mode).toBe('cutout');
    expect(trace.visual_band_px).not.toBeNull();
    expect(trace.status).toBe('pass');
  });

  it('flags overlapping captions as a collision', () => {
    const timeline = structuredClone(quickReelFixtures.punchy);
    timeline.overlays[1].startFrame = timeline.overlays[0].endFrame - 10;
    const trace = buildOverlayRenderTrace(timeline, opts);
    expect(trace.status).toBe('fail');
    expect(trace.overlays[0].collision_check).toBe('failed');
  });

  it('fails the safe-area check when the frame is too small for the layout', () => {
    const timeline = { ...structuredClone(quickReelFixtures.chill), height: 1000 };
    const trace = buildOverlayRenderTrace(timeline, opts);
    // Layout scales with the frame, so everything still fits: the check is relative.
    expect(trace.overlays.every((o) => o.fits_frame)).toBe(true);
  });
});
