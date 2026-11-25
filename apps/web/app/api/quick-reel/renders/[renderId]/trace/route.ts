import { readFile } from 'node:fs/promises';

import { NextResponse } from 'next/server';

import { getRenderQueue } from '../../../../../_lib/quick-reel/render-queue';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

/** The overlay render trace written next to the MP4 (packages/qa field names). */
export async function GET(_request: Request, { params }: { params: Promise<{ renderId: string }> }) {
  const { renderId } = await params;
  const job = (await getRenderQueue()).get(renderId);
  if (!job) return NextResponse.json({ detail: 'Render not found' }, { status: 404 });
  const text = await readFile(job.tracePath, 'utf8').catch(() => null);
  if (text === null) return NextResponse.json({ detail: 'Trace not written yet' }, { status: 409 });
  return new NextResponse(text, { headers: { 'Content-Type': 'application/json' } });
}
