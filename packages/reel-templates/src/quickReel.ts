import { energyStyle } from './energy';
import {
  fromPipelineOverlays,
  type Energy,
  type PipelineOverlayCue,
  type ReelTimeline,
  type TimelineAudio,
  type TimelineVisual,
  type VisualFit,
} from './timeline';

/**
 * Quick Reel adapter: the API's `quick-reel/compose` response (`ComposedReel`) becomes a
 * `ReelTimeline`, plus the frame windows the interactive player needs (one segment per
 * choice moment) and short looping windows for the choice-card previews.
 */

export const QUICK_REEL_FPS = 30;
export const QUICK_REEL_SIZE = { width: 1080, height: 1920 } as const;

/** The fields of `ComposedReel` this adapter reads (snake_case, as the API returns them). */
export interface ComposedReelInput {
  duration_seconds: number;
  pace: Energy;
  overlay_timeline: PipelineOverlayCue[];
  scenes: Array<{
    scene_id: string;
    purpose: string;
    start_seconds: number;
    end_seconds: number;
  }>;
}

export interface QuickReelVisual {
  src: string;
  fit?: VisualFit;
}

export interface QuickReelOptions {
  fps?: number;
  visuals?: QuickReelVisual[];
  backdrop?: [string, string];
  showProgress?: boolean;
  /** Soundtrack from the API's `quick-reel/soundtrack` (voice + music). */
  audio?: TimelineAudio;
}

export interface FrameWindow {
  startFrame: number;
  endFrame: number;
}

export interface SceneWindow extends FrameWindow {
  sceneId: string;
  purpose: string;
}

const toFrame = (seconds: number, fps: number) => Math.round(seconds * fps);

export function sceneWindows(composed: ComposedReelInput, fps = QUICK_REEL_FPS): SceneWindow[] {
  return composed.scenes.map((scene) => ({
    sceneId: scene.scene_id,
    purpose: scene.purpose,
    startFrame: toFrame(scene.start_seconds, fps),
    endFrame: toFrame(scene.end_seconds, fps),
  }));
}

/** Spread the visuals over the scenes, one per scene, cycling when there are fewer. */
export function assignVisuals(
  scenes: FrameWindow[],
  visuals: QuickReelVisual[],
): TimelineVisual[] {
  if (visuals.length === 0) return [];
  return scenes.map((scene, i) => {
    const visual = visuals[i % visuals.length];
    return {
      src: visual.src,
      fit: visual.fit ?? 'cutout',
      startFrame: scene.startFrame,
      endFrame: scene.endFrame,
    };
  });
}

export function fromComposedReel(
  composed: ComposedReelInput,
  opts: QuickReelOptions = {},
): ReelTimeline {
  const fps = opts.fps ?? QUICK_REEL_FPS;
  const base = fromPipelineOverlays(composed.overlay_timeline, {
    fps,
    durationSeconds: composed.duration_seconds,
  });
  return {
    ...base,
    ...QUICK_REEL_SIZE,
    energy: composed.pace,
    backdrop: opts.backdrop ?? energyStyle(composed.pace).backdrop,
    visuals: assignVisuals(sceneWindows(composed, fps), opts.visuals ?? []),
    showProgress: opts.showProgress ?? true,
    ...(opts.audio ? { audio: opts.audio } : {}),
  };
}

/** A hook on its own, for the hook reel before any branches exist. */
export function hookTimeline(
  overlayText: string,
  opts: QuickReelOptions & { seconds?: number; energy?: Energy } = {},
): ReelTimeline {
  const fps = opts.fps ?? QUICK_REEL_FPS;
  const durationInFrames = Math.round((opts.seconds ?? 3) * fps);
  const energy = opts.energy ?? 'punchy';
  const window = { startFrame: 0, endFrame: durationInFrames };
  return {
    fps,
    durationInFrames,
    ...QUICK_REEL_SIZE,
    energy,
    backdrop: opts.backdrop ?? energyStyle(energy).backdrop,
    overlays: [{ text: overlayText, role: 'hook', ...window }],
    visuals: assignVisuals([window], opts.visuals ?? []),
    showProgress: opts.showProgress ?? false,
  };
}

/**
 * The four playback segments of a composed Quick Reel, in order:
 * hook, first story beat, the rest of the story, ending.
 * Choice moments sit between them (structure after the hook, energy after the first beat,
 * ending after the rest of the story).
 */
export interface QuickReelSegments {
  hook: FrameWindow;
  firstBeat: FrameWindow;
  restBeats: FrameWindow;
  ending: FrameWindow;
}

export function quickReelSegments(
  composed: ComposedReelInput,
  fps = QUICK_REEL_FPS,
): QuickReelSegments {
  const scenes = sceneWindows(composed, fps);
  if (scenes.length < 4) {
    throw new Error(`A Quick Reel needs a hook, 2+ story beats and an ending; got ${scenes.length} scenes`);
  }
  const last = scenes[scenes.length - 1];
  return {
    hook: span(scenes[0]),
    firstBeat: span(scenes[1]),
    restBeats: { startFrame: scenes[2].startFrame, endFrame: scenes[scenes.length - 2].endFrame },
    ending: span(last),
  };
}

const span = (w: FrameWindow): FrameWindow => ({ startFrame: w.startFrame, endFrame: w.endFrame });

/**
 * Cut `timeline` down to `[startFrame, endFrame)`, re-based to frame 0, for a looping
 * mini-preview. Overlays and visuals that cross the window are clipped to it.
 */
export function loopWindow(timeline: ReelTimeline, window: FrameWindow): ReelTimeline {
  const { startFrame, endFrame } = window;
  if (endFrame <= startFrame) throw new Error('Loop window is empty');
  const clip = <T extends FrameWindow>(items: T[]): T[] =>
    items
      .filter((item) => item.startFrame < endFrame && item.endFrame > startFrame)
      .map((item) => ({
        ...item,
        startFrame: Math.max(item.startFrame, startFrame) - startFrame,
        endFrame: Math.min(item.endFrame, endFrame) - startFrame,
      }));
  return {
    ...timeline,
    durationInFrames: endFrame - startFrame,
    overlays: clip(timeline.overlays),
    visuals: clip(timeline.visuals),
    showProgress: false,
  };
}

/** The first `seconds` of a segment: what a choice card loops. */
export function previewWindow(
  segment: FrameWindow,
  fps = QUICK_REEL_FPS,
  seconds = 2,
): FrameWindow {
  return {
    startFrame: segment.startFrame,
    endFrame: Math.min(segment.endFrame, segment.startFrame + Math.round(seconds * fps)),
  };
}
