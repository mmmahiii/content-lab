import { mkdtemp, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { ReelTimeline } from '@content-lab/reel-templates';

import {
  absolutizeVisuals,
  jobView,
  renderConcurrency,
  renderTabConcurrency,
  RenderQueue,
  soundtrackIdOf,
  type RenderFn,
} from './render-queue';

const timeline = (n: number): ReelTimeline => ({
  fps: 30,
  durationInFrames: 90 + n,
  width: 1080,
  height: 1920,
  backdrop: ['#000000', '#111111'],
  overlays: [{ text: `Hook ${n}`, role: 'hook', startFrame: 0, endFrame: 90 }],
  visuals: [],
});
const idFor = (t: ReelTimeline) => String(t.durationInFrames).padStart(20, '0');
const flush = () => new Promise((resolve) => setTimeout(resolve, 0));

let outDir: string;
beforeEach(async () => {
  outDir = await mkdtemp(path.join(tmpdir(), 'render-queue-'));
});
afterEach(async () => {
  await rm(outDir, { recursive: true, force: true });
});

function controllableRender() {
  const pending: Array<{ resolve: () => void; reject: (e: Error) => void; progress: (p: number) => void }> = [];
  const render = vi.fn<RenderFn>(
    (options) =>
      new Promise((resolve, reject) => {
        pending.push({
          progress: (p) => options.onProgress?.(p),
          reject,
          resolve: () =>
            resolve({
              videoPath: '',
              tracePath: '',
              trace: { status: 'pass' } as never,
              durationInFrames: options.timeline.durationInFrames,
              fps: 30,
              width: 1080,
              height: 1920,
              renderMs: 1,
            }),
        });
      }),
  );
  return { render, pending };
}

describe('RenderQueue', () => {
  it('renders one job at a time, reports progress, and de-duplicates by timeline', async () => {
    const { render, pending } = controllableRender();
    const queue = new RenderQueue(render, outDir, idFor);
    const a = queue.enqueue(timeline(1));
    const b = queue.enqueue(timeline(2));
    expect(queue.enqueue(timeline(1))).toBe(a);
    await flush();
    expect(render).toHaveBeenCalledTimes(1);
    expect(a.status).toBe('rendering');
    expect(b.status).toBe('queued');

    pending[0].progress(0.4);
    expect(jobView(a).progress).toBe(0.4);
    pending[0].resolve();
    await flush();
    expect(a.status).toBe('done');
    expect(jobView(a)).toMatchObject({ videoUrl: `/api/quick-reel/renders/${a.id}/video`, durationSeconds: 91 / 30 });
    expect(render).toHaveBeenCalledTimes(2);
    expect(b.status).toBe('rendering');
  });

  it('records failures (including a failed overlay trace) and allows a retry', async () => {
    const { render, pending } = controllableRender();
    const queue = new RenderQueue(render, outDir, idFor);
    const job = queue.enqueue(timeline(3));
    await flush();
    pending[0].reject(Object.assign(new Error('Overlay render trace failed for #1'), { trace: { status: 'fail' } }));
    await flush();
    expect(job.status).toBe('failed');
    expect(jobView(job)).toMatchObject({ error: 'Overlay render trace failed for #1', overlayTraceStatus: 'fail', videoUrl: null });
    const retry = queue.enqueue(timeline(3));
    expect(retry).not.toBe(job);
    expect(retry.status).toBe('rendering');
    expect(render).toHaveBeenCalledTimes(2);
  });

  it('cancels the job a remix replaces if it has not started', async () => {
    const { render } = controllableRender();
    const queue = new RenderQueue(render, outDir, idFor);
    queue.enqueue(timeline(4));
    const stale = queue.enqueue(timeline(5));
    const fresh = queue.enqueue(timeline(6), { replaces: stale.id });
    expect(stale.status).toBe('cancelled');
    expect(fresh.status).toBe('queued');
  });

  it('serves renders that finished before a restart from disk, and rejects odd ids', async () => {
    const id = 'a'.repeat(20);
    await writeFile(path.join(outDir, `quick-reel-${id}.mp4`), 'x');
    await writeFile(
      path.join(outDir, `quick-reel-${id}.overlay_render_trace.json`),
      JSON.stringify({ status: 'pass', fps: 30, duration_in_frames: 450, frame_width_px: 1080, frame_height_px: 1920 }),
    );
    const queue = new RenderQueue(vi.fn(), outDir, idFor);
    expect(queue.get(id)).toMatchObject({ status: 'done', overlayTraceStatus: 'pass' });
    expect(jobView(queue.get(id)!).durationSeconds).toBe(15);
    expect(queue.get('../../etc/passwd')).toBeUndefined();
  });
});

describe('absolutizeVisuals', () => {
  const org = '11111111-1111-4111-8111-111111111111';
  const asset = '22222222-2222-4222-8222-222222222222';
  it('prefixes same-origin asset proxy paths with the server origin', () => {
    const t = { ...timeline(1), visuals: [{ src: `/api/orgs/${org}/assets/${asset}/file`, startFrame: 0, endFrame: 90 }] };
    expect(absolutizeVisuals(t, 'http://127.0.0.1:3000').visuals[0].src).toBe(
      `http://127.0.0.1:3000/api/orgs/${org}/assets/${asset}/file`,
    );
  });
  it.each(['http://169.254.169.254/latest', 'file:///etc/passwd', '/api/orgs/x/assets/y/file'])(
    'refuses %s',
    (src) => {
      const t = { ...timeline(1), visuals: [{ src, startFrame: 0, endFrame: 90 }] };
      expect(() => absolutizeVisuals(t, 'http://127.0.0.1:3000')).toThrow(/not allowed/);
    },
  );
});

describe('parallel renders', () => {
  it('runs up to `concurrency` renders at once and starts the next when one finishes', async () => {
    const { render, pending } = controllableRender();
    const queue = new RenderQueue(render, outDir, idFor, 2);
    const jobs = [1, 2, 3].map((n) => queue.enqueue(timeline(n)));
    await flush();

    expect(render).toHaveBeenCalledTimes(2);
    expect(queue.running).toBe(2);
    expect(jobs.map((j) => j.status)).toEqual(['rendering', 'rendering', 'queued']);

    pending[1].resolve();
    await flush();
    await flush();
    expect(jobs[1].status).toBe('done');
    expect(render).toHaveBeenCalledTimes(3);
    expect(jobs[2].status).toBe('rendering');
  });

  it('reads QUICK_REEL_RENDER_CONCURRENCY (default 1) and rejects nonsense', () => {
    expect(renderConcurrency({})).toBe(1);
    expect(renderConcurrency({ QUICK_REEL_RENDER_CONCURRENCY: '3' })).toBe(3);
    expect(() => renderConcurrency({ QUICK_REEL_RENDER_CONCURRENCY: '0' })).toThrow();
    expect(() => renderConcurrency({ QUICK_REEL_RENDER_CONCURRENCY: 'lots' })).toThrow();
    expect(() => new RenderQueue(vi.fn(), outDir, idFor, 0)).toThrow();
  });
});

describe('soundtrack and downscaled visuals', () => {
  const org = '11111111-1111-4111-8111-111111111111';
  const asset = '22222222-2222-4222-8222-222222222222';
  const sid = 'abcdef0123456789abcdef01';

  it('absolutizes the soundtrack proxy path and exposes its id', () => {
    const t = { ...timeline(1), audio: { src: `/api/orgs/${org}/quick-reel/soundtracks/${sid}/file` } };
    const out = absolutizeVisuals(t, 'http://127.0.0.1:3000');
    expect(out.audio?.src).toBe(`http://127.0.0.1:3000/api/orgs/${org}/quick-reel/soundtracks/${sid}/file`);
    expect(soundtrackIdOf(t)).toBe(sid);
    expect(soundtrackIdOf(timeline(1))).toBeNull();
  });

  it.each(['https://evil.example/a.wav', `/api/orgs/${org}/quick-reel/soundtracks/NOT-HEX/file`])(
    'refuses audio %s',
    (src) => {
      expect(() => absolutizeVisuals({ ...timeline(1), audio: { src } }, 'http://x')).toThrow(/not allowed/);
    },
  );

  it('allows the max_px asset copy but no other query', () => {
    const ok = `/api/orgs/${org}/assets/${asset}/file?max_px=1080`;
    const t = { ...timeline(1), visuals: [{ src: ok, startFrame: 0, endFrame: 90 }] };
    expect(absolutizeVisuals(t, 'http://x').visuals[0].src).toBe(`http://x${ok}`);
    const bad = { ...t, visuals: [{ src: `${ok}&redirect=1`, startFrame: 0, endFrame: 90 }] };
    expect(() => absolutizeVisuals(bad, 'http://x')).toThrow(/not allowed/);
  });
});

describe('renderTabConcurrency', () => {
  it('splits the cores across parallel renders, with an override', () => {
    expect(renderTabConcurrency(2, {}, 4)).toBe(2);
    expect(renderTabConcurrency(1, {}, 4)).toBe(4);
    expect(renderTabConcurrency(3, {}, 2)).toBe(1);
    expect(renderTabConcurrency(2, { QUICK_REEL_RENDER_TAB_CONCURRENCY: '6' }, 4)).toBe(6);
    expect(() => renderTabConcurrency(2, { QUICK_REEL_RENDER_TAB_CONCURRENCY: '0' }, 4)).toThrow();
  });
});
