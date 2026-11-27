import { existsSync, readFileSync } from 'node:fs';
import { availableParallelism } from 'node:os';
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
 * Render queue: up to `concurrency` headless Chrome renders at once (default 2; they are CPU
 * heavy, so more than the core count only slows each one down), jobs keyed by the
 * timeline's content hash so the same reel is never rendered twice, and finished files on
 * disk so a server restart still serves earlier renders.
 */
export class RenderQueue {
  private jobs = new Map<string, RenderJob>();
  private order: string[] = [];
  private active = 0;

  constructor(
    private readonly render: RenderFn,
    readonly outDir: string,
    private readonly idFor: (timeline: ReelTimeline) => string,
    readonly concurrency = 1,
  ) {
    if (!Number.isInteger(concurrency) || concurrency < 1) {
      throw new Error(`Render concurrency must be a positive integer (got ${concurrency})`);
    }
  }

  /** Renders currently running (for tests and diagnostics). */
  get running(): number {
    return this.active;
  }

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

  /** Start queued jobs until `concurrency` renders are running. */
  private async pump(): Promise<void> {
    while (this.active < this.concurrency) {
      const id = this.order.shift();
      if (id === undefined) return;
      const job = this.jobs.get(id);
      if (!job || job.status !== 'queued') continue;
      this.active += 1;
      void this.run(id, job).finally(() => {
        this.active -= 1;
        void this.pump();
      });
    }
  }

  private async run(id: string, job: RenderJob): Promise<void> {
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

/**
 * Visuals must be same-origin asset proxy paths (optionally the downscaled `?max_px=` copy);
 * the render tab loads them from here.
 */
const ALLOWED_VISUAL =
  /^\/api\/orgs\/[0-9a-fA-F-]{36}\/assets\/[0-9a-fA-F-]{36}\/file(\?max_px=\d{2,4})?$/;
/** The soundtrack must be the same-origin soundtrack proxy path. */
const ALLOWED_AUDIO = /^\/api\/orgs\/[0-9a-fA-F-]{36}\/quick-reel\/soundtracks\/[0-9a-f]{8,64}\/file$/;

/** The soundtrack id a timeline plays, if any (Send to Review passes it to QA). */
export function soundtrackIdOf(timeline: ReelTimeline): string | null {
  const match = timeline.audio?.src.match(/\/quick-reel\/soundtracks\/([0-9a-f]{8,64})\/file$/);
  return match ? match[1] : null;
}

export function absolutizeVisuals(timeline: ReelTimeline, origin: string): ReelTimeline {
  let audio = timeline.audio;
  if (audio) {
    if (!ALLOWED_AUDIO.test(audio.src)) {
      throw new Error(`Audio source not allowed: ${audio.src.slice(0, 120)}`);
    }
    audio = { ...audio, src: `${origin}${audio.src}` };
  }
  return {
    ...timeline,
    ...(audio ? { audio } : {}),
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

/**
 * Parallel renders: `QUICK_REEL_RENDER_CONCURRENCY` (default 1). Renders are CPU-bound, so on a
 * small machine two at once just halve each one's Chrome tabs (measured: a 16 s reel took 62 s
 * at 2 x 2 tabs vs ~20 s at 1 x 4 tabs on 4 cores). Raise it on machines with many cores.
 */
export function renderConcurrency(env: Record<string, string | undefined> = process.env): number {
  const raw = env.QUICK_REEL_RENDER_CONCURRENCY;
  if (!raw) return 1;
  const value = Number(raw);
  if (!Number.isInteger(value) || value < 1 || value > 8) {
    throw new Error(`QUICK_REEL_RENDER_CONCURRENCY must be 1-8 (got ${raw})`);
  }
  return value;
}

/**
 * Chrome tabs per render: the cores split across the renders that may run at once (renders
 * are CPU-bound on frame painting; measured ~20% faster at 4 tabs than 2 on 4 cores).
 * `QUICK_REEL_RENDER_TAB_CONCURRENCY` overrides.
 */
export function renderTabConcurrency(
  renders: number,
  env: Record<string, string | undefined> = process.env,
  cores = availableParallelism(),
): number {
  const raw = env.QUICK_REEL_RENDER_TAB_CONCURRENCY;
  if (raw) {
    const value = Number(raw);
    if (!Number.isInteger(value) || value < 1 || value > 32) {
      throw new Error(`QUICK_REEL_RENDER_TAB_CONCURRENCY must be 1-32 (got ${raw})`);
    }
    return value;
  }
  return Math.max(1, Math.floor(cores / Math.max(1, renders)));
}

const GLOBAL_KEY = '__quickReelRenderQueue';

/** Process-wide queue (shared across route bundles and dev reloads). */
export async function getRenderQueue(): Promise<RenderQueue> {
  const store = globalThis as Record<string, unknown>;
  if (!store[GLOBAL_KEY]) {
    const { renderQuickReel, timelineRenderId } = await import('@content-lab/reel-templates/render');
    const browserExecutable = process.env.REMOTION_BROWSER_EXECUTABLE || null;
    const concurrency = renderConcurrency();
    const tabs = renderTabConcurrency(concurrency);
    store[GLOBAL_KEY] = new RenderQueue(
      (options) => renderQuickReel({ ...options, browserExecutable, concurrency: tabs }),
      renderOutDir(),
      timelineRenderId,
      concurrency,
    );
  }
  return store[GLOBAL_KEY] as RenderQueue;
}
