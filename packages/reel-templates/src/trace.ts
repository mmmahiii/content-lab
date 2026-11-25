import { captionExitFrames, energyStyle } from './energy';
import {
  captionGeometry,
  layoutMode,
  rectInside,
  rectsOverlap,
  safeRect,
  SAFE_INSETS,
  visualBand,
  type Rect,
} from './geometry';
import type { MeasureFn } from './layout';
import type { ReelTimeline } from './timeline';

export const OVERLAY_TRACE_SCHEMA = 'remotion_overlay_render_trace.v1';

export interface TraceLineBox {
  text: string;
  left_px: number;
  top_px: number;
  width_px: number;
  height_px: number;
}

export interface OverlayTraceEntry {
  index: number;
  role: string;
  /** Copy from the timeline. */
  source_text: string;
  /** Copy drawn on screen, before CSS text-transform (QA compares this to source_text). */
  rendered_text: string;
  /** Copy as it appears on screen, after text-transform. */
  display_text: string;
  text_transform: 'none' | 'uppercase';
  font_family: string;
  font_weight: number;
  font_size: number;
  line_height_px: number;
  letter_spacing_em: number;
  line_count: number;
  text_box: { left_px: number; top_px: number; width_px: number; height_px: number };
  line_boxes: TraceLineBox[];
  /** Half-open [start, end) frame interval on the composition clock. */
  visible_start_frame: number;
  visible_end_frame: number;
  visible_start_seconds: number;
  visible_end_seconds: number;
  /** Frame from which the caption starts fading out. */
  exit_start_frame: number;
  clipped: boolean;
  fits_frame: boolean;
  safe_area_passed: boolean;
  collision_check: 'passed' | 'failed';
}

export interface OverlayRenderTrace {
  schema_version: typeof OVERLAY_TRACE_SCHEMA;
  renderer: 'remotion';
  composition: string;
  fps: number;
  duration_in_frames: number;
  clip_duration_seconds: number;
  frame_width_px: number;
  frame_height_px: number;
  energy: string | null;
  layout_mode: string;
  safe_insets_px: { left: number; right: number; top: number; bottom: number };
  visual_band_px: { top_px: number; height_px: number } | null;
  status: 'pass' | 'fail';
  overlays: OverlayTraceEntry[];
}

const round = (n: number) => Math.round(n * 100) / 100;

function box(rect: Rect) {
  return {
    left_px: round(rect.left),
    top_px: round(rect.top),
    width_px: round(rect.width),
    height_px: round(rect.height),
  };
}

/**
 * Build the overlay render trace for a timeline: the exact caption boxes `KineticReel`
 * draws (settled, after entrance motion) and when each is visible. Call it in a browser
 * with the reel font loaded (the render service does this inside the headless page), or
 * pass `measure` for tests.
 */
export function buildOverlayRenderTrace(
  timeline: ReelTimeline,
  opts: { fontFamily: string; composition?: string; measure?: MeasureFn },
): OverlayRenderTrace {
  const mode = layoutMode(timeline);
  const style = energyStyle(timeline.energy);
  const frame: Rect = { left: 0, top: 0, width: timeline.width, height: timeline.height };
  const safe = safeRect(timeline.width, timeline.height);
  const band = mode === 'cutout' ? visualBand(timeline.width, timeline.height) : null;

  const overlays = timeline.overlays.map((overlay, index): OverlayTraceEntry => {
    const g = captionGeometry(overlay, {
      width: timeline.width,
      height: timeline.height,
      mode,
      style,
      fontFamily: opts.fontFamily,
      measure: opts.measure,
    });
    const drawnWords = g.lines.flatMap((line) => line.words).join(' ');
    const sourceWords = overlay.text.split(/\s+/).filter(Boolean).join(' ');
    const fitsFrame = rectInside(g.box, frame);
    const collides =
      (band !== null && rectsOverlap(g.box, band)) ||
      timeline.overlays.some(
        (other, j) =>
          j !== index && other.startFrame < overlay.endFrame && overlay.startFrame < other.endFrame,
      );
    const length = overlay.endFrame - overlay.startFrame;
    return {
      index,
      role: overlay.role,
      source_text: overlay.text,
      rendered_text: drawnWords === sourceWords ? overlay.text : drawnWords,
      display_text: g.displayText,
      text_transform: g.textTransform,
      font_family: g.fontFamily,
      font_weight: Number(g.fontWeight),
      font_size: g.fontSize,
      line_height_px: round(g.lineHeightPx),
      letter_spacing_em: g.letterSpacingEm,
      line_count: g.lines.length,
      text_box: box(g.box),
      line_boxes: g.lines.map((line) => ({ text: line.text, ...box(line) })),
      visible_start_frame: overlay.startFrame,
      visible_end_frame: overlay.endFrame,
      visible_start_seconds: round(overlay.startFrame / timeline.fps),
      visible_end_seconds: round(overlay.endFrame / timeline.fps),
      exit_start_frame: overlay.endFrame - captionExitFrames(length, style),
      clipped: drawnWords !== sourceWords || !fitsFrame,
      fits_frame: fitsFrame,
      safe_area_passed: rectInside(g.box, safe),
      collision_check: collides ? 'failed' : 'passed',
    };
  });

  const ok = overlays.every(
    (o) => !o.clipped && o.fits_frame && o.safe_area_passed && o.collision_check === 'passed',
  );
  return {
    schema_version: OVERLAY_TRACE_SCHEMA,
    renderer: 'remotion',
    composition: opts.composition ?? 'QuickReel',
    fps: timeline.fps,
    duration_in_frames: timeline.durationInFrames,
    clip_duration_seconds: round(timeline.durationInFrames / timeline.fps),
    frame_width_px: timeline.width,
    frame_height_px: timeline.height,
    energy: timeline.energy ?? null,
    layout_mode: mode,
    safe_insets_px: { ...SAFE_INSETS },
    visual_band_px: band ? { top_px: round(band.top), height_px: round(band.height) } : null,
    status: ok ? 'pass' : 'fail',
    overlays,
  };
}
