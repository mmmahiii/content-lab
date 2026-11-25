import { existsSync, readFileSync } from 'node:fs';
import path from 'node:path';

import type { ReelTimeline } from '@content-lab/reel-templates';
import type {
  RenderQuickReelOptions,
  RenderQuickReelResult,
} from '@content-lab/reel-templates/render';

export type RenderStatus = 'queued' | 'rendering' | 'done' | 'failed' | 'cancelled';

export interface RenderJob {
  id: string;
  status: RenderStatus;
  progress: number;
  error: string | null;
  timeline: ReelTimeline;
  videoPath: string;
  tracePath: string;
  overlayTraceStatus: 'pass' | 'fail' | null;
  createdAt: number;
  finishedAt: number | null;
}

export type RenderFn = (
  options: Pick<RenderQuickReelOptions, 'timeline' | 'outDir' | 'basename' | 'onProgress'>,
) => Promise<RenderQuickReelResult>;

export const RENDER_ID_PATTERN = /^[0-9a-f]{20}$/;

/**
 * Serial render queue: one headless Chrome render at a time (they are CPU heavy), jobs
 * keyed by the timeline's content hash so the same reel is never rendered twice, and
 * finished files on disk so a server restart still serves earlier renders.
 */
export class RenderQueue {
  private jobs = new Map<string, RenderJob>();
  private order: string[] = [];
  private running = false;

  constructor(
    private readonly render: RenderFn,
    readonly outDir: string,
    private readonly idFor: (timeline: ReelTimeline) => string,
  ) {}

  private files(id: string) {
    const basename = `quick-reel-${id}`;
    return {
      basename,
      videoPath: path.join(this.outDir, `${basename}.mp4`),
      tracePath: path.join(this.outDir, `${basename}.overlay_render_trace.json`),
    };
  }

  enqueue(timeline: ReelTimeline, opts: { replaces?: string | null } = {}): RenderJob {
    const id = this.idFor(timeline);
    const existing = this.get(id);
    if (existing && existing.status !== 'failed' && existing.status !== 'cancelled') return existing;

    if (opts.replaces && opts.replaces !== id) {
      const old = this.jobs.get(opts.replaces);
      if (old?.status === 'queued') {
        old.status = 'cancelled';
        old.finishedAt = Date.now();
      }
    }
    const { videoPath, tracePath } = this.files(id);
    const job: RenderJob = {
      id,
      status: 'queued',
      progress: 0,
      error: null,
      timeline,
      videoPath,
      tracePath,
      overlayTraceStatus: null,
      createdAt: Date.now(),
      finishedAt: null,
    };
    this.jobs.set(id, job);
    this.order.push(id);
    void this.pump();
    return job;
  }

  /** A job from memory, or one rendered before this process started. */
  get(id: string): RenderJob | undefined {
    if (!RENDER_ID_PATTERN.test(id)) return undefined;
    const job = this.jobs.get(id);
    if (job) return job;
    const { videoPath, tracePath } = this.files(id);
    if (!existsSync(videoPath) || !existsSync(tracePath)) return undefined;
    try {
      const trace = JSON.parse(readFileSync(tracePath, 'utf8')) as {
        status?: 'pass' | 'fail';
        fps: number;
        duration_in_frames: number;
        frame_width_px: number;
        frame_height_px: number;
      };
      const restored: RenderJob = {
        id,
        status: 'done',
        progress: 1,
        error: null,
        timeline: {
          fps: trace.fps,
          durationInFrames: trace.duration_in_frames,
          width: trace.frame_width_px,
          height: trace.frame_height_px,
          backdrop: ['#000000', '#000000'],
          overlays: [],
          visuals: [],
        },
        videoPath,
        tracePath,
        overlayTraceStatus: trace.status ?? null,
        createdAt: Date.now(),
        finishedAt: Date.now(),
      };
      this.jobs.set(id, restored);
      return restored;
    } catch {
      return undefined;
    }
  }

  private async pump(): Promise<void> {
    if (this.running) return;
    this.running = true;
    try {
      for (;;) {
        const id = this.order.shift();
        if (id === undefined) break;
        const job = this.jobs.get(id);
        if (!job || job.status !== 'queued') continue;
        job.status = 'rendering';
        try {
          const result = await this.render({
            timeline: job.timeline,
            outDir: this.outDir,
            basename: this.files(id).basename,
            onProgress: (progress) => {
              job.progress = Math.max(job.progress, Math.min(1, progress));
            },
          });
          job.status = 'done';
          job.progress = 1;
          job.overlayTraceStatus = result.trace.status;
        } catch (error) {
          job.status = 'failed';
          job.error = error instanceof Error ? error.message : String(error);
          const trace = (error as { trace?: { status?: 'pass' | 'fail' } }).trace;
          job.overlayTraceStatus = trace?.status ?? null;
        } finally {
          job.finishedAt = Date.now();
        }
      }
    } finally {
      this.running = false;
    }
  }
}

export interface RenderJobView {
  renderId: string;
  status: RenderStatus;
  progress: number;
  error: string | null;
  durationSeconds: number;
  width: number;
  height: number;
  fps: number;
  overlayTraceStatus: 'pass' | 'fail' | null;
  videoUrl: string | null;
  traceUrl: string | null;
}

export function jobView(job: RenderJob): RenderJobView {
  const base = `/api/quick-reel/renders/${job.id}`;
  return {
    renderId: job.id,
    status: job.status,
    progress: Math.round(job.progress * 1000) / 1000,
    error: job.error,
    durationSeconds: job.timeline.durationInFrames / job.timeline.fps,
    width: job.timeline.width,
    height: job.timeline.height,
    fps: job.timeline.fps,
    overlayTraceStatus: job.overlayTraceStatus,
    videoUrl: job.status === 'done' ? `${base}/video` : null,
    traceUrl: job.overlayTraceStatus ? `${base}/trace` : null,
  };
}

/** Visuals must be same-origin asset proxy paths; the render tab loads them from here. */
const ALLOWED_VISUAL = /^\/api\/orgs\/[0-9a-fA-F-]{36}\/assets\/[0-9a-fA-F-]{36}\/file$/;

export function absolutizeVisuals(timeline: ReelTimeline, origin: string): ReelTimeline {
  return {
    ...timeline,
    visuals: timeline.visuals.map((visual) => {
      if (!visual.src) return visual;
      if (!ALLOWED_VISUAL.test(visual.src)) {
        throw new Error(`Visual source not allowed: ${visual.src.slice(0, 120)}`);
      }
      return { ...visual, src: `${origin}${visual.src}` };
    }),
  };
}

export function renderOutDir(cwd = process.cwd()): string {
  return process.env.QUICK_REEL_RENDER_DIR ?? path.join(cwd, '.quick-reel-renders');
}

const GLOBAL_KEY = '__quickReelRenderQueue';

/** Process-wide queue (shared across route bundles and dev reloads). */
export async function getRenderQueue(): Promise<RenderQueue> {
  const store = globalThis as Record<string, unknown>;
  if (!store[GLOBAL_KEY]) {
    const { renderQuickReel, timelineRenderId } = await import('@content-lab/reel-templates/render');
    const browserExecutable = process.env.REMOTION_BROWSER_EXECUTABLE || null;
    store[GLOBAL_KEY] = new RenderQueue(
      (options) => renderQuickReel({ ...options, browserExecutable }),
      renderOutDir(),
      timelineRenderId,
    );
  }
  return store[GLOBAL_KEY] as RenderQueue;
}
