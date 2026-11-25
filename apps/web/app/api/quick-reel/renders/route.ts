import { NextResponse } from 'next/server';

import { parseReelTimeline } from '@content-lab/reel-templates/schema';

import { absolutizeVisuals, getRenderQueue, jobView } from '../../../_lib/quick-reel/render-queue';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

/** Start (or join) a local MP4 render of a Quick Reel timeline. */
export async function POST(request: Request) {
  const body = (await request.json().catch(() => null)) as {
    timeline?: unknown;
    replaces?: unknown;
  } | null;
  let timeline;
  try {
    timeline = absolutizeVisuals(parseReelTimeline(body?.timeline), new URL(request.url).origin);
  } catch (error) {
    const detail = error instanceof Error ? error.message : 'Invalid timeline';
    return NextResponse.json({ detail: `Invalid timeline: ${detail.slice(0, 400)}` }, { status: 422 });
  }
  const queue = await getRenderQueue();
  const replaces = typeof body?.replaces === 'string' ? body.replaces : null;
  const job = queue.enqueue(timeline, { replaces });
  return NextResponse.json(jobView(job), { status: job.status === 'done' ? 200 : 202 });
}
