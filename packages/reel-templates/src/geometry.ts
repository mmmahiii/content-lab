import type { EnergyStyle } from './energy';
import { blockHeight, layoutText, lineWidth, type MeasureFn } from './layout';
import type { OverlayRole, ReelTimeline, TimelineOverlay } from './timeline';

/**
 * Caption geometry shared by the renderer (`KineticReel`) and the render trace, so the
 * trace describes exactly the boxes that are drawn.
 *
 * Coordinates are in composition pixels for a 1080x1920 frame (other sizes scale).
 */

export type LayoutMode = 'text' | 'cutout' | 'cover';

export interface Rect {
  left: number;
  top: number;
  width: number;
  height: number;
}

/** Text-safe zone for 9:16 feeds: platform UI covers the top bar and the bottom caption area. */
export const SAFE_INSETS = { left: 90, right: 90, top: 220, bottom: 380 } as const;

/** The middle band cut-out visuals sit in, between the hook and the captions. */
export const VISUAL_BAND = { top: 660, height: 580 } as const;

/** Story progress bar position (decorative; sits in the top inset like platform UI does). */
export const PROGRESS_TOP = 150;

export const LINE_HEIGHT = 1.08;
export const WORD_GAP_EM = 0.24;

type Anchor = { kind: 'top' | 'center' | 'bottom'; y: number };

interface RoleSpec {
  maxLines: number;
  maxSize: number;
  minSize: number;
  weight: '800' | '900';
  boxed: boolean;
  insetXEm: number;
  insetYEm: number;
  anchor: Anchor;
  maxHeight: number;
}

const BOX_INSET = { x: 0.5, y: 0.28 };
/** The hook keyword highlight bleeds this far past the glyphs (drawn with box-shadow). */
export const ACCENT_BLEED_EM = 0.12;

const SPECS: Record<LayoutMode, Record<OverlayRole, RoleSpec>> = {
  text: {
    hook: spec(4, 140, 60, '900', false, { kind: 'center', y: 800 }, 640),
    value: spec(4, 120, 52, '900', true, { kind: 'center', y: 980 }, 560),
    cta: spec(4, 104, 50, '800', true, { kind: 'center', y: 1040 }, 480),
    disclosure: spec(4, 64, 40, '800', true, { kind: 'center', y: 1040 }, 360),
  },
  cutout: {
    hook: spec(4, 124, 48, '900', false, { kind: 'top', y: 240 }, 400),
    value: spec(4, 100, 44, '900', true, { kind: 'top', y: 1262 }, 270),
    cta: spec(4, 90, 44, '800', true, { kind: 'top', y: 1262 }, 270),
    disclosure: spec(4, 60, 36, '800', true, { kind: 'top', y: 1262 }, 270),
  },
  cover: {
    hook: spec(4, 128, 50, '900', false, { kind: 'top', y: 250 }, 480),
    value: spec(4, 104, 48, '900', true, { kind: 'bottom', y: 1530 }, 420),
    cta: spec(4, 96, 46, '800', true, { kind: 'bottom', y: 1530 }, 380),
    disclosure: spec(4, 60, 36, '800', true, { kind: 'bottom', y: 1530 }, 300),
  },
};

function spec(
  maxLines: number,
  maxSize: number,
  minSize: number,
  weight: '800' | '900',
  boxed: boolean,
  anchor: Anchor,
  maxHeight: number,
): RoleSpec {
  return {
    maxLines,
    maxSize,
    minSize,
    weight,
    boxed,
    insetXEm: boxed ? BOX_INSET.x : ACCENT_BLEED_EM,
    insetYEm: boxed ? BOX_INSET.y : ACCENT_BLEED_EM,
    anchor,
    maxHeight,
  };
}

export function layoutMode(timeline: Pick<ReelTimeline, 'visuals'>): LayoutMode {
  const shown = timeline.visuals.filter((v) => v.src);
  if (shown.length === 0) return 'text';
  return shown.some((v) => (v.fit ?? 'cutout') === 'cover') ? 'cover' : 'cutout';
}

export interface LineBox extends Rect {
  text: string;
  words: string[];
}

export interface CaptionGeometry {
  role: OverlayRole;
  mode: LayoutMode;
  sourceText: string;
  /** What appears on screen (after text-transform). */
  displayText: string;
  textTransform: 'none' | 'uppercase';
  fontFamily: string;
  fontWeight: '800' | '900';
  fontSize: number;
  lineHeightPx: number;
  letterSpacingEm: number;
  gapEm: number;
  boxed: boolean;
  insetX: number;
  insetY: number;
  /** The caption block including box padding / highlight bleed. */
  box: Rect;
  /** Glyph boxes per line. */
  lines: LineBox[];
  /** The area the caption was fitted into (centred horizontally within it). */
  zone: Rect;
}

export interface GeometryContext {
  width: number;
  height: number;
  mode: LayoutMode;
  style: EnergyStyle;
  fontFamily: string;
  measure?: MeasureFn;
}

export function roleTransform(role: OverlayRole, style: EnergyStyle): 'none' | 'uppercase' {
  return role === 'value' ? style.valueTransform : 'none';
}

export function captionGeometry(
  overlay: Pick<TimelineOverlay, 'text' | 'role'>,
  ctx: GeometryContext,
): CaptionGeometry {
  const sx = ctx.width / 1080;
  const sy = ctx.height / 1920;
  const s = SPECS[ctx.mode][overlay.role];
  const textTransform = roleTransform(overlay.role, ctx.style);
  // Letter spacing is a headline treatment; keep the small disclosure line plain.
  const letterSpacingEm = overlay.role === 'disclosure' ? 0 : ctx.style.letterSpacingEm;
  const zoneLeft = SAFE_INSETS.left * sx;
  const zoneWidth = ctx.width - (SAFE_INSETS.left + SAFE_INSETS.right) * sx;
  const maxHeight = s.maxHeight * sy;

  const layout = layoutText({
    text: overlay.text,
    fontFamily: ctx.fontFamily,
    fontWeight: s.weight,
    boxWidth: zoneWidth,
    maxLines: s.maxLines,
    maxSize: Math.round(s.maxSize * sx),
    minSize: Math.round(s.minSize * sx),
    letterSpacingEm,
    textTransform,
    insetEm: s.insetXEm,
    gapEm: WORD_GAP_EM,
    lineHeight: LINE_HEIGHT,
    insetYEm: s.insetYEm,
    maxHeight,
    measure: ctx.measure,
  });

  const fontSize = layout.fontSize;
  const lineHeightPx = fontSize * LINE_HEIGHT;
  const insetX = s.insetXEm * fontSize;
  const insetY = s.insetYEm * fontSize;
  const widths = layout.lines.map((words) =>
    lineWidth(words, {
      fontFamily: ctx.fontFamily,
      fontWeight: s.weight,
      fontSize,
      letterSpacingEm,
      textTransform,
      gapEm: WORD_GAP_EM,
      measure: ctx.measure,
    }),
  );
  const contentWidth = Math.max(0, ...widths);
  const boxWidth = contentWidth + 2 * insetX;
  const boxHeight = blockHeight(layout.lines.length, fontSize, LINE_HEIGHT, s.insetYEm);
  const anchorY = s.anchor.y * sy;
  const boxTop =
    s.anchor.kind === 'top'
      ? anchorY
      : s.anchor.kind === 'center'
        ? anchorY - boxHeight / 2
        : anchorY - boxHeight;
  const boxLeft = zoneLeft + (zoneWidth - boxWidth) / 2;
  const zoneTop =
    s.anchor.kind === 'top'
      ? anchorY
      : s.anchor.kind === 'center'
        ? anchorY - maxHeight / 2
        : anchorY - maxHeight;

  const transform = (t: string) => (textTransform === 'uppercase' ? t.toUpperCase() : t);
  const lines: LineBox[] = layout.lines.map((words, i) => ({
    words,
    text: transform(words.join(' ')),
    left: boxLeft + insetX + (contentWidth - widths[i]) / 2,
    top: boxTop + insetY + i * lineHeightPx,
    width: widths[i],
    height: lineHeightPx,
  }));

  return {
    role: overlay.role,
    mode: ctx.mode,
    sourceText: overlay.text,
    displayText: transform(overlay.text),
    textTransform,
    fontFamily: ctx.fontFamily,
    fontWeight: s.weight,
    fontSize,
    lineHeightPx,
    letterSpacingEm,
    gapEm: WORD_GAP_EM,
    boxed: s.boxed,
    insetX,
    insetY,
    box: { left: boxLeft, top: boxTop, width: boxWidth, height: boxHeight },
    lines,
    zone: { left: zoneLeft, top: zoneTop, width: zoneWidth, height: maxHeight },
  };
}

/** The visual band rect for cut-out layouts (scaled to the frame). */
export function visualBand(width: number, height: number): Rect {
  const sy = height / 1920;
  return { left: 0, top: VISUAL_BAND.top * sy, width, height: VISUAL_BAND.height * sy };
}

export function rectsOverlap(a: Rect, b: Rect): boolean {
  return (
    a.left < b.left + b.width &&
    b.left < a.left + a.width &&
    a.top < b.top + b.height &&
    b.top < a.top + a.height
  );
}

export function rectInside(inner: Rect, outer: Rect, tolerance = 0.5): boolean {
  return (
    inner.left >= outer.left - tolerance &&
    inner.top >= outer.top - tolerance &&
    inner.left + inner.width <= outer.left + outer.width + tolerance &&
    inner.top + inner.height <= outer.top + outer.height + tolerance
  );
}

export function safeRect(width: number, height: number): Rect {
  const sx = width / 1080;
  const sy = height / 1920;
  return {
    left: SAFE_INSETS.left * sx,
    top: SAFE_INSETS.top * sy,
    width: width - (SAFE_INSETS.left + SAFE_INSETS.right) * sx,
    height: height - (SAFE_INSETS.top + SAFE_INSETS.bottom) * sy,
  };
}
