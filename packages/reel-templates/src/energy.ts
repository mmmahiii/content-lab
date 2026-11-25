import type { Energy } from './timeline';

export interface SpringSettings {
  damping: number;
  mass: number;
  stiffness: number;
}

/**
 * Everything an energy choice changes. Layout-affecting fields (letter spacing, text
 * transform) are measured by `layoutText`, so every energy keeps the no-clipping guarantee;
 * the rest are transforms, opacity and colour, which never move the laid-out text box.
 */
export interface EnergyStyle {
  /** Frames between hook words popping in. */
  wordStagger: number;
  /** Word entrance spring and its starting offset / scale / blur. */
  wordSpring: SpringSettings;
  wordFromY: number;
  wordFromScale: number;
  wordFromBlur: number;
  /** Caption box entrance spring and starting scale. */
  boxSpring: SpringSettings;
  boxFromScale: number;
  /** Frames for overlays and visuals to fade out at the end of their interval. */
  exitFrames: number;
  /** Highlight colour for the hook keyword and the CTA box, and the text drawn on it. */
  accent: string;
  accentInk: string;
  /** Background of value / disclosure captions. */
  captionBg: string;
  captionRadiusEm: number;
  letterSpacingEm: number;
  valueTransform: 'none' | 'uppercase';
  /** Visual entrance, slow push-in amount (scale) and rotation wobble (deg). */
  visualSpring: SpringSettings;
  visualPush: number;
  visualTilt: number;
  /** Decaying shake on each new caption (px), and a white flash on each cut (opacity). */
  shakePx: number;
  flash: number;
  /** Vignette darkness 0-1 and letterbox bar height in px (0 = none). */
  vignette: number;
  letterboxPx: number;
  /** Default backdrop gradient (top, bottom) and a glow colour for the moving blobs. */
  backdrop: [string, string];
  glow: string;
}

/** The look of the original Remotion proof; used when a timeline has no energy. */
export const BASE_STYLE: EnergyStyle = {
  wordStagger: 3,
  wordSpring: { damping: 11, mass: 0.5, stiffness: 180 },
  wordFromY: 40,
  wordFromScale: 0.6,
  wordFromBlur: 0,
  boxSpring: { damping: 9, mass: 0.6, stiffness: 100 },
  boxFromScale: 0.7,
  exitFrames: 5,
  accent: '#FFD43B',
  accentInk: '#111111',
  captionBg: 'rgba(0,0,0,0.55)',
  captionRadiusEm: 0.4,
  letterSpacingEm: 0,
  valueTransform: 'uppercase',
  visualSpring: { damping: 14, mass: 0.7, stiffness: 100 },
  visualPush: 0.08,
  visualTilt: 2,
  shakePx: 0,
  flash: 0,
  vignette: 0.55,
  letterboxPx: 0,
  backdrop: ['#1b1f3b', '#07080f'],
  glow: 'rgba(120,140,255,0.35)',
};

export const ENERGY_STYLES: Record<Energy, EnergyStyle> = {
  chill: {
    ...BASE_STYLE,
    wordStagger: 5,
    wordSpring: { damping: 22, mass: 0.9, stiffness: 90 },
    wordFromY: 24,
    wordFromScale: 0.94,
    boxSpring: { damping: 20, mass: 0.9, stiffness: 80 },
    boxFromScale: 0.94,
    exitFrames: 10,
    accent: '#FFC09F',
    accentInk: '#2B1608',
    captionBg: 'rgba(36,18,40,0.5)',
    captionRadiusEm: 0.6,
    valueTransform: 'none',
    visualSpring: { damping: 24, mass: 1, stiffness: 70 },
    visualPush: 0.05,
    visualTilt: 0.6,
    vignette: 0.35,
    backdrop: ['#F6A57D', '#4A2158'],
    glow: 'rgba(255,214,170,0.45)',
  },
  punchy: {
    ...BASE_STYLE,
    wordStagger: 2,
    wordSpring: { damping: 10, mass: 0.45, stiffness: 240 },
    wordFromY: 60,
    wordFromScale: 0.4,
    boxSpring: { damping: 8, mass: 0.5, stiffness: 220 },
    boxFromScale: 0.55,
    exitFrames: 3,
    accent: '#FFE135',
    accentInk: '#111111',
    captionBg: 'rgba(10,10,10,0.72)',
    captionRadiusEm: 0.3,
    visualSpring: { damping: 9, mass: 0.5, stiffness: 200 },
    visualPush: 0.12,
    visualTilt: 3,
    shakePx: 10,
    flash: 0.35,
    vignette: 0.5,
    backdrop: ['#FF3D71', '#2B0A3D'],
    glow: 'rgba(255,225,53,0.35)',
  },
  dramatic: {
    ...BASE_STYLE,
    wordStagger: 6,
    wordSpring: { damping: 26, mass: 1.2, stiffness: 60 },
    wordFromY: 0,
    wordFromScale: 1.25,
    wordFromBlur: 14,
    boxSpring: { damping: 24, mass: 1.1, stiffness: 60 },
    boxFromScale: 1.12,
    exitFrames: 12,
    accent: '#FF4D4D',
    accentInk: '#FFFFFF',
    captionBg: 'rgba(0,0,0,0.72)',
    captionRadiusEm: 0.2,
    letterSpacingEm: 0.04,
    visualSpring: { damping: 30, mass: 1.4, stiffness: 50 },
    visualPush: 0.14,
    visualTilt: 0,
    vignette: 0.8,
    letterboxPx: 96,
    backdrop: ['#2A0E0E', '#030303'],
    glow: 'rgba(255,77,77,0.28)',
  },
};

export function energyStyle(energy: Energy | undefined): EnergyStyle {
  return energy ? ENERGY_STYLES[energy] : BASE_STYLE;
}

/** Decaying horizontal shake for the first frames of a caption (0 when settled). */
export function shakeOffset(frame: number, amplitudePx: number, fps: number): number {
  if (amplitudePx <= 0 || frame < 0) return 0;
  const t = frame / fps;
  const decay = Math.max(0, 1 - t / 0.25);
  return Math.sin(frame * 2.4) * amplitudePx * decay;
}

/** Frames a caption spends fading out: the style's exit, capped at a third of its length. */
export function captionExitFrames(lengthInFrames: number, style: EnergyStyle): number {
  return Math.min(style.exitFrames, Math.floor(lengthInFrames / 3));
}
