import { z } from 'zod';
import type { ReelTimeline } from './timeline';

/**
 * Runtime schema for `ReelTimeline`, for anything that receives a timeline from outside
 * the process (the render service). Bounds keep a render request cheap and well-formed.
 */

const frame = z.number().int().min(0);

const overlaySchema = z
  .object({
    text: z.string().trim().min(1).max(120),
    role: z.enum(['hook', 'value', 'cta', 'disclosure']),
    startFrame: frame,
    endFrame: frame,
  })
  .refine((o) => o.endFrame > o.startFrame, { message: 'overlay interval is empty' });

const visualSchema = z
  .object({
    src: z.string().min(1).max(2048).optional(),
    startFrame: frame,
    endFrame: frame,
    fit: z.enum(['cutout', 'cover']).optional(),
  })
  .refine((v) => v.endFrame > v.startFrame, { message: 'visual interval is empty' });

const cssColor = z.string().regex(/^(#[0-9a-fA-F]{3,8}|rgba?\([0-9.,\s%]+\))$/, 'expected a hex or rgb() colour');

export const MAX_RENDER_SECONDS = 90;

export const reelTimelineSchema = z
  .object({
    fps: z.number().int().min(1).max(60),
    durationInFrames: z.number().int().min(1),
    width: z.number().int().min(16).max(2160),
    height: z.number().int().min(16).max(3840),
    backdrop: z.tuple([cssColor, cssColor]),
    overlays: z.array(overlaySchema).max(24),
    visuals: z.array(visualSchema).max(24),
    energy: z.enum(['chill', 'punchy', 'dramatic']).optional(),
    showProgress: z.boolean().optional(),
  })
  .strict()
  .refine((t) => t.durationInFrames <= t.fps * MAX_RENDER_SECONDS, {
    message: `timeline is longer than ${MAX_RENDER_SECONDS} s`,
  })
  .refine(
    (t) =>
      [...t.overlays, ...t.visuals].every((item) => item.endFrame <= t.durationInFrames),
    { message: 'an overlay or visual runs past the end of the timeline' },
  );

export function parseReelTimeline(input: unknown): ReelTimeline {
  return reelTimelineSchema.parse(input) as ReelTimeline;
}
