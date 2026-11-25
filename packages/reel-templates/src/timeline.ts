/**
 * ReelTimeline: the props contract every Remotion reel template renders.
 *
 * Frame-based on one clock: intervals are half-open [startFrame, endFrame).
 * `fromPipelineOverlays` adapts the Python pipeline's seconds-based
 * `overlay_timeline` (see packages/creative OverlayCue) into this shape.
 */

export type OverlayRole = 'hook' | 'value' | 'cta';

export interface TimelineOverlay {
  text: string;
  role: OverlayRole;
  startFrame: number;
  endFrame: number;
}

export interface TimelineVisual {
  /** File name under the Remotion public dir; omitted = plain backdrop. */
  src?: string;
  startFrame: number;
  endFrame: number;
}

// A type alias (not an interface) so Remotion accepts it as composition props.
export type ReelTimeline = {
  fps: number;
  durationInFrames: number;
  width: number;
  height: number;
  /** CSS colours for the backdrop gradient (top, bottom). */
  backdrop: [string, string];
  overlays: TimelineOverlay[];
  visuals: TimelineVisual[];
};

/** Shape of one entry in the pipeline's `script.overlay_timeline`. */
export interface PipelineOverlayCue {
  text: string;
  emphasis: string;
  start_seconds: number;
  end_seconds: number;
}

const ROLE_BY_EMPHASIS: Record<string, OverlayRole> = {
  hook: 'hook',
  value: 'value',
  emphasis: 'value',
  cta: 'cta',
};

export function fromPipelineOverlays(
  cues: PipelineOverlayCue[],
  opts: { fps: number; durationSeconds: number },
): Pick<ReelTimeline, 'fps' | 'durationInFrames' | 'overlays'> {
  const durationInFrames = Math.round(opts.durationSeconds * opts.fps);
  const overlays = cues.map((cue) => {
    const role = ROLE_BY_EMPHASIS[cue.emphasis];
    if (!role) {
      throw new Error(`Unknown overlay emphasis "${cue.emphasis}"`);
    }
    const startFrame = Math.round(cue.start_seconds * opts.fps);
    const endFrame = Math.min(Math.round(cue.end_seconds * opts.fps), durationInFrames);
    if (endFrame <= startFrame) {
      throw new Error(`Overlay "${cue.text}" has an empty interval`);
    }
    return { text: cue.text, role, startFrame, endFrame };
  });
  for (let i = 1; i < overlays.length; i++) {
    if (overlays[i].startFrame < overlays[i - 1].endFrame) {
      throw new Error(`Overlays "${overlays[i - 1].text}" and "${overlays[i].text}" overlap`);
    }
  }
  return { fps: opts.fps, durationInFrames, overlays };
}
