import { mkdtemp, rm, writeFile } from 'node:fs/promises';
import { tmpdir } from 'node:os';
import path from 'node:path';

import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { quickReelFixtures } from '@content-lab/reel-templates';

import { RenderQueue } from '../../../_lib/quick-reel/render-queue';

const state: { queue: RenderQueue | null } = { queue: null };

vi.mock('../../../_lib/quick-reel/render-queue', async (importOriginal) => {
  const actual = await importOriginal<typeof import('../../../_lib/quick-reel/render-queue')>();
  return { ...actual, getRenderQueue: async () => state.queue! };
});

const { POST } = await import('./route');
const { GET: getJob } = await import('./[renderId]/route');
const { GET: getVideo } = await import('./[renderId]/video/route');
const { GET: getTrace } = await import('./[renderId]/trace/route');

const ORG = '11111111-1111-4111-8111-111111111111';
const ASSET = '22222222-2222-4222-8222-222222222222';
const ID = 'b'.repeat(20);

let outDir: string;
let render: ReturnType<typeof vi.fn>;

beforeEach(async () => {
  outDir = await mkdtemp(path.join(tmpdir(), 'renders-route-'));
  render = vi.fn(async ({ outDir: dir, basename }: { outDir: string; basename: string }) => {
    await writeFile(path.join(dir, `${basename}.mp4`), 'MP4DATA');
    await writeFile(path.join(dir, `${basename}.overlay_render_trace.json`), '{"status":"pass"}');
    return { trace: { status: 'pass' } };
  });
  state.queue = new RenderQueue(render as never, outDir, () => ID);
});
afterEach(async () => {
  await rm(outDir, { recursive: true, force: true });
});

const post = (body: unknown) =>
  POST(new Request('http://127.0.0.1:3000/api/quick-reel/renders', { method: 'POST', body: JSON.stringify(body) }));
const params = (renderId: string) => ({ params: Promise.resolve({ renderId }) });
const flush = () => new Promise((resolve) => setTimeout(resolve, 5));

describe('render routes', () => {
  it('validates, queues, renders, then serves the MP4 and the trace', async () => {
    const timeline = {
      ...quickReelFixtures.punchy,
      visuals: [{ src: `/api/orgs/${ORG}/assets/${ASSET}/file`, startFrame: 0, endFrame: 60, fit: 'cutout' }],
    };
    const started = await post({ timeline });
    expect(started.status).toBe(202);
    expect(await started.json()).toMatchObject({ renderId: ID, status: expect.stringMatching(/queued|rendering/) });
    // Visual paths are made absolute for the headless render tab.
    expect(render.mock.calls[0][0].timeline.visuals[0].src).toBe(
      `http://127.0.0.1:3000/api/orgs/${ORG}/assets/${ASSET}/file`,
    );
    await flush();

    const status = await (await getJob(new Request('http://x'), params(ID))).json();
    expect(status).toMatchObject({ status: 'done', progress: 1, videoUrl: `/api/quick-reel/renders/${ID}/video` });

    const video = await getVideo(new Request(`http://x/video?download=1`), params(ID));
    expect(video.status).toBe(200);
    expect(video.headers.get('content-type')).toBe('video/mp4');
    expect(video.headers.get('content-disposition')).toContain('attachment');
    expect(await video.text()).toBe('MP4DATA');

    const trace = await getTrace(new Request('http://x'), params(ID));
    expect(await trace.json()).toEqual({ status: 'pass' });
  });

  it('rejects malformed timelines and outside image URLs', async () => {
    expect((await post({ timeline: { fps: 30 } })).status).toBe(422);
    const ssrf = {
      ...quickReelFixtures.chill,
      visuals: [{ src: 'http://169.254.169.254/', startFrame: 0, endFrame: 30 }],
    };
    const response = await post({ timeline: ssrf });
    expect(response.status).toBe(422);
    expect((await response.json()).detail).toMatch(/not allowed/);
    expect(render).not.toHaveBeenCalled();
  });

  it('404s unknown renders and 409s a video that is not finished', async () => {
    expect((await getJob(new Request('http://x'), params('c'.repeat(20)))).status).toBe(404);
    render.mockImplementationOnce(() => new Promise(() => {}));
    await post({ timeline: quickReelFixtures.dramatic });
    expect((await getVideo(new Request('http://x'), params(ID))).status).toBe(409);
  });
});
