import { mkdtemp, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import type { ReelTimeline } from '@content-lab/reel-templates';

import { RenderQueue } from './render-queue';
import { ReviewUploadError, uploadRenderForReview } from './review-upload';

const ORG = '11111111-1111-4111-8111-111111111111';
const SID = 'abcdef0123456789abcdef01';
const timeline: ReelTimeline = {
  fps: 30,
  durationInFrames: 90,
  width: 1080,
  height: 1920,
  backdrop: ['#000000', '#111111'],
  overlays: [{ text: 'Hook', role: 'hook', startFrame: 0, endFrame: 90 }],
  visuals: [],
  audio: { src: `http://127.0.0.1:3000/api/orgs/${ORG}/quick-reel/soundtracks/${SID}/file` },
};
const RENDER_ID = 'a'.repeat(20);

let outDir: string;
beforeEach(async () => {
  outDir = await mkdtemp(path.join(tmpdir(), 'review-upload-'));
});
afterEach(async () => {
  await rm(outDir, { recursive: true, force: true });
});

async function finishedQueue(): Promise<RenderQueue> {
  const render = vi.fn(async (options: { outDir: string; basename?: string }) => {
    await writeFile(path.join(options.outDir, `${options.basename}.mp4`), 'MP4BYTES');
    await writeFile(
      path.join(options.outDir, `${options.basename}.overlay_render_trace.json`),
      JSON.stringify({ status: 'pass', overlays: [] }),
    );
    return { trace: { status: 'pass' } } as never;
  });
  const queue = new RenderQueue(render as never, outDir, () => RENDER_ID);
  queue.enqueue(timeline);
  await vi.waitFor(() => expect(queue.get(RENDER_ID)?.status).toBe('done'));
  return queue;
}

describe('uploadRenderForReview', () => {
  it('uploads the MP4, then runs QA with the trace and the soundtrack id', async () => {
    const queue = await finishedQueue();
    const calls: Array<{ url: string; init: RequestInit }> = [];
    const fetcher = vi.fn(async (url: string | URL | Request, init?: RequestInit) => {
      calls.push({ url: String(url), init: init ?? {} });
      const body = String(url).endsWith('/qa')
        ? { status: 'warn', video_storage_uri: 's3://x', blocking_failures: [], warnings: ['audio_content'] }
        : { video_storage_uri: 's3://x' };
      return new Response(JSON.stringify(body), { status: 200 });
    });

    const report = await uploadRenderForReview({
      orgId: ORG,
      pageId: 'page-1',
      renderId: RENDER_ID,
      queue,
      actor: 'operator:test',
      fetcher: fetcher as never,
    });

    expect(report.status).toBe('warn');
    expect(calls.map((c) => [c.init.method, c.url.replace(/^.*\/orgs\//, '/orgs/')])).toEqual([
      ['PUT', `/orgs/${ORG}/pages/page-1/quick-reel/renders/${RENDER_ID}/video`],
      ['POST', `/orgs/${ORG}/pages/page-1/quick-reel/renders/${RENDER_ID}/qa`],
    ]);
    expect(Buffer.from(calls[0].init.body as Uint8Array).toString()).toBe('MP4BYTES');
    expect(JSON.parse(String(calls[1].init.body))).toEqual({
      overlay_render_trace: { status: 'pass', overlays: [] },
      soundtrack_id: SID,
    });
  });

  it('refuses renders this server has not finished, and surfaces API errors', async () => {
    const queue = await finishedQueue();
    await expect(
      uploadRenderForReview({ orgId: ORG, pageId: 'p', renderId: 'b'.repeat(20), queue, actor: 'a' }),
    ).rejects.toMatchObject({ status: 409 });

    const failing = vi.fn(async () => new Response('Render upload is not an MP4', { status: 422 }));
    const error = await uploadRenderForReview({
      orgId: ORG,
      pageId: 'p',
      renderId: RENDER_ID,
      queue,
      actor: 'a',
      fetcher: failing as never,
    }).catch((e: unknown) => e);
    expect(error).toBeInstanceOf(ReviewUploadError);
    expect((error as ReviewUploadError).status).toBe(422);
  });
});
