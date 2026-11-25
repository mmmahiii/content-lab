import { mkdtemp, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { ReelTimeline } from '@content-lab/reel-templates';

import { absolutizeVisuals, jobView, RenderQueue, type RenderFn } from './render-queue';

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
