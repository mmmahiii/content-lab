export { KineticReel, pickAccentWord, resolveVisualSrc } from './KineticReel';
export { REEL_FONT_FAMILY, waitForReelFont } from './fonts';
export {
  BASE_STYLE,
  captionExitFrames,
  ENERGY_STYLES,
  energyStyle,
  shakeOffset,
  type EnergyStyle,
  type SpringSettings,
} from './energy';
export {
  captionGeometry,
  layoutMode,
  safeRect,
  SAFE_INSETS,
  VISUAL_BAND,
  visualBand,
  type CaptionGeometry,
  type LayoutMode,
  type LineBox,
  type Rect,
} from './geometry';
export {
  blockHeight,
  domMeasure,
  layoutText,
  lineWidth,
  type MeasureFn,
  type MeasureInput,
  type TextLayout,
} from './layout';
export {
  assignVisuals,
  fromComposedReel,
  hookTimeline,
  loopWindow,
  previewWindow,
  QUICK_REEL_FPS,
  QUICK_REEL_SIZE,
  quickReelSegments,
  sceneWindows,
  type ComposedReelInput,
  type FrameWindow,
  type QuickReelOptions,
  type QuickReelSegments,
  type QuickReelVisual,
  type SceneWindow,
} from './quickReel';
export {
  fromPipelineOverlays,
  ENERGIES,
  type Energy,
  type OverlayRole,
  type PipelineOverlayCue,
  type ReelTimeline,
  type TimelineOverlay,
  type TimelineVisual,
  type VisualFit,
} from './timeline';
export {
  buildOverlayRenderTrace,
  OVERLAY_TRACE_SCHEMA,
  type OverlayRenderTrace,
  type OverlayTraceEntry,
  type TraceLineBox,
} from './trace';
export { MAX_RENDER_SECONDS, parseReelTimeline, reelTimelineSchema } from './schema';
