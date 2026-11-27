/**
 * Local MP4 render for Quick Reel timelines (Node only; no Remotion Lambda).
 *
 * 1. Bundle `src/entry.ts` once per process (webpack, ~10 s) and reuse the bundle.
 * 2. `selectComposition('QuickReelTrace')`: its `calculateMetadata` runs inside the headless
 *    page with the reel font loaded and returns the overlay render trace computed by the same
 *    `captionGeometry` the renderer uses. A trace that fails (clipped, off-frame, outside the
 *    safe area, colliding) stops the render: the plan has to change, not the pixels.
 * 3. `renderMedia('QuickReel')` to H.264 MP4, then write the trace next to it.
 */
import { createHash } from 'node:crypto';
import { existsSync } from 'node:fs';
import { mkdir, rename, writeFile } from 'node:fs/promises';
import path from 'node:path';
import type { ReelTimeline } from '../src/timeline';
import type { OverlayRenderTrace } from '../src/trace';

export const QUICK_REEL_COMPOSITION = 'QuickReel';
export const QUICK_REEL_TRACE_COMPOSITION = 'QuickReelTrace';

/** The subset of @remotion/bundler + @remotion/renderer used here (injectable for tests). */
export interface RemotionApi {
  bundle(options: { entryPoint: string }): Promise<string>;
  selectComposition(options: {
    serveUrl: string;
    id: string;
    inputProps: Record<string, unknown>;
    browserExecutable?: string | null;
    timeoutInMilliseconds?: number;
  }): Promise<{
    id: string;
    durationInFrames: number;
    fps: number;
    width: number;
    height: number;
    props: Record<string, unknown>;
  }>;
  renderMedia(options: {
    composition: { id: string; durationInFrames: number; fps: number; width: number; height: number };
    serveUrl: string;
    codec: 'h264';
    outputLocation: string;
    inputProps: Record<string, unknown>;
    browserExecutable?: string | null;
    concurrency?: number | null;
    crf?: number;
    x264Preset?: 'ultrafast' | 'superfast' | 'veryfast' | 'faster' | 'fast' | 'medium';
    jpegQuality?: number;
    imageFormat?: 'jpeg' | 'png';
    pixelFormat?: 'yuv420p';
    colorSpace?: 'bt709';
    timeoutInMilliseconds?: number;
    onProgress?: (progress: { progress: number }) => void;
  }): Promise<unknown>;
}

export class TraceCheckError extends Error {
  constructor(readonly trace: OverlayRenderTrace) {
    const bad = trace.overlays
      .filter((o) => o.clipped || !o.fits_frame || !o.safe_area_passed || o.collision_check !== 'passed')
      .map((o) => `#${o.index} "${o.source_text}"`);
    super(`Overlay render trace failed for ${bad.join(', ') || 'the reel'}`);
    this.name = 'TraceCheckError';
  }
}

export interface RenderQuickReelOptions {
  timeline: ReelTimeline;
  outDir: string;
  /** File stem: `<basename>.mp4` and `<basename>.overlay_render_trace.json`. */
  basename?: string;
  entryPoint?: string;
  browserExecutable?: string | null;
  concurrency?: number | null;
  onProgress?: (progress: number) => void;
  remotion?: RemotionApi;
}

export interface RenderQuickReelResult {
  videoPath: string;
  tracePath: string;
  trace: OverlayRenderTrace;
  durationInFrames: number;
  fps: number;
  width: number;
  height: number;
  renderMs: number;
}

/** Stable id for a timeline: identical props render to the identical file. */
export function timelineRenderId(timeline: ReelTimeline): string {
  return createHash('sha256').update(canonicalJson(timeline)).digest('hex').slice(0, 20);
}

export function canonicalJson(value: unknown): string {
  if (Array.isArray(value)) return `[${value.map(canonicalJson).join(',')}]`;
  if (value && typeof value === 'object') {
    const entries = Object.entries(value as Record<string, unknown>)
      .filter(([, v]) => v !== undefined)
      .sort(([a], [b]) => (a < b ? -1 : a > b ? 1 : 0));
    return `{${entries.map(([k, v]) => `${JSON.stringify(k)}:${canonicalJson(v)}`).join(',')}}`;
  }
  return JSON.stringify(value);
}

/**
 * Find `packages/reel-templates/src/entry.ts`: explicit option, then
 * `REEL_TEMPLATES_ENTRY`, then walk up from the working directory (works from the repo
 * root, `apps/web` or `packages/reel-templates`, and inside bundled server code).
 */
export function resolveEntryPoint(explicit?: string, cwd = process.cwd()): string {
  const candidates = [explicit, process.env.REEL_TEMPLATES_ENTRY].filter(Boolean) as string[];
  for (const candidate of candidates) {
    if (existsSync(candidate)) return path.resolve(candidate);
    throw new Error(`Reel templates entry not found at ${candidate}`);
  }
  let dir = path.resolve(cwd);
  for (;;) {
    for (const rel of ['packages/reel-templates/src/entry.ts', 'src/entry.ts']) {
      const file = path.join(dir, rel);
      if (existsSync(file) && file.includes(`reel-templates${path.sep}src`)) return file;
    }
    const parent = path.dirname(dir);
    if (parent === dir) break;
    dir = parent;
  }
  throw new Error(`Could not find packages/reel-templates/src/entry.ts above ${cwd}`);
}

async function loadRemotion(): Promise<RemotionApi> {
  const [bundler, renderer] = await Promise.all([
    import('@remotion/bundler'),
    import('@remotion/renderer'),
  ]);
  return {
    bundle: (options) => bundler.bundle(options),
    selectComposition: (options) => renderer.selectComposition(options) as never,
    renderMedia: (options) => renderer.renderMedia(options as never) as never,
  };
}

// One bundle per process (and per entry point). Kept on globalThis so dev-server module
// reloads and separate route bundles share it.
const bundles: Map<string, Promise<string>> = ((globalThis as Record<string, unknown>)[
  '__quickReelBundles'
] ??= new Map()) as Map<string, Promise<string>>;

export function getServeUrl(remotion: RemotionApi, entryPoint: string): Promise<string> {
  let serveUrl = bundles.get(entryPoint);
  if (!serveUrl) {
    serveUrl = remotion.bundle({ entryPoint });
    serveUrl.catch(() => bundles.delete(entryPoint));
    bundles.set(entryPoint, serveUrl);
  }
  return serveUrl;
}

export async function traceQuickReel(
  options: Pick<RenderQuickReelOptions, 'timeline' | 'entryPoint' | 'browserExecutable' | 'remotion'>,
): Promise<OverlayRenderTrace> {
  const remotion = options.remotion ?? (await loadRemotion());
  const serveUrl = await getServeUrl(remotion, resolveEntryPoint(options.entryPoint));
  const composition = await remotion.selectComposition({
    serveUrl,
    id: QUICK_REEL_TRACE_COMPOSITION,
    inputProps: { timeline: options.timeline },
    browserExecutable: options.browserExecutable ?? null,
    timeoutInMilliseconds: 60_000,
  });
  const trace = composition.props.trace as OverlayRenderTrace | undefined;
  if (!trace) throw new Error('QuickReelTrace returned no trace');
  return trace;
}

export async function renderQuickReel(
  options: RenderQuickReelOptions,
): Promise<RenderQuickReelResult> {
  const started = Date.now();
  const remotion = options.remotion ?? (await loadRemotion());
  const entryPoint = resolveEntryPoint(options.entryPoint);
  const basename = options.basename ?? `quick-reel-${timelineRenderId(options.timeline)}`;
  const videoPath = path.join(options.outDir, `${basename}.mp4`);
  const tracePath = path.join(options.outDir, `${basename}.overlay_render_trace.json`);
  await mkdir(options.outDir, { recursive: true });

  const t0 = Date.now();
  const trace = await traceQuickReel({ ...options, entryPoint, remotion });
  const tTrace = Date.now();
  if (trace.status !== 'pass') {
    await writeFile(tracePath, `${JSON.stringify(trace, null, 2)}\n`);
    throw new TraceCheckError(trace);
  }

  const serveUrl = await getServeUrl(remotion, entryPoint);
  const inputProps = options.timeline as unknown as Record<string, unknown>;
  const composition = await remotion.selectComposition({
    serveUrl,
    id: QUICK_REEL_COMPOSITION,
    inputProps,
    browserExecutable: options.browserExecutable ?? null,
    timeoutInMilliseconds: 60_000,
  });
  const tSelect = Date.now();
  // Render to a temp name and move into place, so a half-written file is never served.
  const partial = `${videoPath}.part.mp4`;
  await remotion.renderMedia({
    composition,
    serveUrl,
    codec: 'h264',
    outputLocation: partial,
    inputProps,
    browserExecutable: options.browserExecutable ?? null,
    concurrency: options.concurrency ?? null,
    crf: 18,
    // Measured on a 16 s reel (4 cores): the default x264 preset + JPEG 80 frames took ~31 s
    // after bundling; veryfast + JPEG 80 ~19 s. Frame painting is the rest.
    x264Preset: 'veryfast',
    jpegQuality: 80,
    imageFormat: 'jpeg',
    // Limited-range 4:2:0, what Instagram / TikTok / Shorts expect (not full-range yuvj420p).
    pixelFormat: 'yuv420p',
    colorSpace: 'bt709',
    timeoutInMilliseconds: 60_000,
    onProgress: ({ progress }) => options.onProgress?.(progress),
  });
  console.info(`[quick-reel-timing] trace=${tTrace - t0}ms select=${tSelect - tTrace}ms render=${Date.now() - tSelect}ms concurrency=${options.concurrency}`);
  await writeFile(tracePath, `${JSON.stringify(trace, null, 2)}\n`);
  await rename(partial, videoPath);

  return {
    videoPath,
    tracePath,
    trace,
    durationInFrames: composition.durationInFrames,
    fps: composition.fps,
    width: composition.width,
    height: composition.height,
    renderMs: Date.now() - started,
  };
}
