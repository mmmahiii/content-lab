import { readFile } from 'node:fs/promises';

import { resolveApiBaseUrl } from '../api-proxy';
import { soundtrackIdOf, type RenderQueue } from './render-queue';

export class ReviewUploadError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
    this.name = 'ReviewUploadError';
  }
}

export interface RenderQaReport {
  status: 'pass' | 'warn' | 'fail';
  video_storage_uri: string;
  blocking_failures: Array<{ gate_name: string; message: string }>;
  warnings: string[];
}

type Fetch = typeof fetch;

/**
 * Before Send to Review: store the finished MP4 in object storage through the API
 * (`PUT …/quick-reel/renders/{id}/video`) and run pipeline QA on it (`POST …/qa`) with the
 * overlay render trace and soundtrack. The API then attaches that QA report to the reel, so
 * the reviewed file is the one in storage, not a file on this web server's disk.
 */
export async function uploadRenderForReview(options: {
  orgId: string;
  pageId: string;
  renderId: string;
  queue: RenderQueue;
  actor: string;
  fetcher?: Fetch;
}): Promise<RenderQaReport> {
  const fetcher = options.fetcher ?? fetch;
  const job = options.queue.get(options.renderId);
  if (!job || job.status !== 'done') {
    throw new ReviewUploadError(409, `Render ${options.renderId} is not finished on this server`);
  }
  const [video, trace] = await Promise.all([readFile(job.videoPath), readFile(job.tracePath, 'utf8')]);
  const base = `${resolveApiBaseUrl()}/orgs/${options.orgId}/pages/${options.pageId}/quick-reel/renders/${options.renderId}`;
  const headers = { 'X-Actor-Id': options.actor };

  const put = await fetcher(`${base}/video`, {
    method: 'PUT',
    headers: { ...headers, 'Content-Type': 'video/mp4' },
    body: video,
    cache: 'no-store',
  });
  if (!put.ok) throw new ReviewUploadError(put.status, `Render upload failed: ${await put.text()}`);

  const qa = await fetcher(`${base}/qa`, {
    method: 'POST',
    headers: { ...headers, 'Content-Type': 'application/json', Accept: 'application/json' },
    body: JSON.stringify({
      overlay_render_trace: JSON.parse(trace) as unknown,
      soundtrack_id: soundtrackIdOf(job.timeline),
    }),
    cache: 'no-store',
  });
  if (!qa.ok) throw new ReviewUploadError(qa.status, `Render QA failed to run: ${await qa.text()}`);
  return (await qa.json()) as RenderQaReport;
}
