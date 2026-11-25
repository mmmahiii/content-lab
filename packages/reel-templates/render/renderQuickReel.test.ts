import { mkdtemp, readFile, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { quickReelFixtures } from '../src/fixtures';
import { QUICK_REEL_COMPOSITION as ROOT_COMPOSITION } from '../src/Root';
import { fakeMeasure } from '../src/test-utils';
import { buildOverlayRenderTrace } from '../src/trace';
import {
  canonicalJson,
  QUICK_REEL_COMPOSITION,
  renderQuickReel,
  resolveEntryPoint,
  timelineRenderId,
  TraceCheckError,
  type RemotionApi,
} from './renderQuickReel';

vi.mock('../src/fonts', () => ({ REEL_FONT_FAMILY: 'Test', waitForReelFont: async () => {} }));

const timeline = quickReelFixtures.punchy;
const entryPoint = path.resolve(__dirname, '../src/entry.ts');

function fakeRemotion(trace = buildOverlayRenderTrace(timeline, { fontFamily: 'Test', measure: fakeMeasure })) {
  const api: RemotionApi = {
    bundle: vi.fn(async () => 'http://bundle.test'),
    selectComposition: vi.fn(async ({ id, inputProps }) => ({
      id,
      durationInFrames: timeline.durationInFrames,
      fps: timeline.fps,
      width: timeline.width,
      height: timeline.height,
      props: id === 'QuickReelTrace' ? { ...inputProps, trace } : inputProps,
    })),
    renderMedia: vi.fn(async ({ outputLocation, onProgress }) => {
      onProgress?.({ progress: 0.5 });
      onProgress?.({ progress: 1 });
      await writeFile(outputLocation, 'mp4-bytes');
    }),
  };
  return api;
}

let outDir: string;
beforeEach(async () => {
  outDir = await mkdtemp(path.join(tmpdir(), 'quick-reel-render-'));
});
afterEach(async () => {
  await rm(outDir, { recursive: true, force: true });
});

describe('renderQuickReel', () => {
  it('traces in the browser first, renders H.264 and writes the trace next to the MP4', async () => {
    const remotion = fakeRemotion();
    const progress: number[] = [];
    const result = await renderQuickReel({
      timeline,
      outDir,
      basename: 'reel',
      entryPoint,
      remotion,
      onProgress: (p) => progress.push(p),
    });
    expect(result.videoPath).toBe(path.join(outDir, 'reel.mp4'));
    expect(result.tracePath).toBe(path.join(outDir, 'reel.overlay_render_trace.json'));
    expect(await readFile(result.videoPath, 'utf8')).toBe('mp4-bytes');
    const written = JSON.parse(await readFile(result.tracePath, 'utf8'));
    expect(written.status).toBe('pass');
    expect(written.overlays).toHaveLength(timeline.overlays.length);
    expect(progress).toEqual([0.5, 1]);

    const calls = vi.mocked(remotion.selectComposition).mock.calls.map(([o]) => o.id);
    expect(calls).toEqual(['QuickReelTrace', 'QuickReel']);
    const render = vi.mocked(remotion.renderMedia).mock.calls[0][0];
    expect(render.codec).toBe('h264');
    expect(render.inputProps).toEqual(timeline);
  });

  it('refuses to render when the trace finds a problem, and keeps the trace for debugging', async () => {
    const trace = buildOverlayRenderTrace(timeline, { fontFamily: 'Test', measure: fakeMeasure });
    trace.status = 'fail';
    trace.overlays[1].safe_area_passed = false;
    const remotion = fakeRemotion(trace);
    await expect(
      renderQuickReel({ timeline, outDir, basename: 'bad', entryPoint, remotion }),
    ).rejects.toBeInstanceOf(TraceCheckError);
    expect(remotion.renderMedia).not.toHaveBeenCalled();
    const kept = JSON.parse(await readFile(path.join(outDir, 'bad.overlay_render_trace.json'), 'utf8'));
    expect(kept.status).toBe('fail');
  });

  it('bundles once per entry point and reuses it', async () => {
    const remotion = fakeRemotion();
    const other = path.join(outDir, 'entry.ts');
    await writeFile(other, '');
    await renderQuickReel({ timeline, outDir, basename: 'a', entryPoint: other, remotion });
    await renderQuickReel({ timeline, outDir, basename: 'b', entryPoint: other, remotion });
    expect(remotion.bundle).toHaveBeenCalledTimes(1);
  });
});

describe('render ids and entry resolution', () => {
  it('ids depend on content, not key order', () => {
    const shuffled = Object.fromEntries(Object.entries(timeline).reverse()) as typeof timeline;
    expect(timelineRenderId(shuffled)).toBe(timelineRenderId(timeline));
    expect(timelineRenderId(quickReelFixtures.chill)).not.toBe(timelineRenderId(timeline));
    expect(canonicalJson({ b: 1, a: [2, { d: undefined, c: 3 }] })).toBe('{"a":[2,{"c":3}],"b":1}');
  });

  it('finds the entry from the repo root and from apps/web', () => {
    const repo = path.resolve(__dirname, '../../..');
    expect(resolveEntryPoint(undefined, repo)).toBe(entryPoint);
    expect(resolveEntryPoint(undefined, path.join(repo, 'apps/web'))).toBe(entryPoint);
    expect(() => resolveEntryPoint('/nope/entry.ts')).toThrow(/not found/);
  });

  it('uses the composition id registered in Root', () => {
    expect(QUICK_REEL_COMPOSITION).toBe(ROOT_COMPOSITION);
  });
});
