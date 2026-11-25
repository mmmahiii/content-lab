import { createReadStream } from 'node:fs';
import { stat } from 'node:fs/promises';
import { Readable } from 'node:stream';

import { NextResponse } from 'next/server';

import { getRenderQueue } from '../../../../../_lib/quick-reel/render-queue';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

/** The rendered MP4. `?download=1` asks the browser to save it. */
export async function GET(request: Request, { params }: { params: Promise<{ renderId: string }> }) {
  const { renderId } = await params;
  const job = (await getRenderQueue()).get(renderId);
  if (!job) return NextResponse.json({ detail: 'Render not found' }, { status: 404 });
  if (job.status !== 'done') {
    return NextResponse.json({ detail: 'Render is not finished', status: job.status }, { status: 409 });
  }
  const info = await stat(job.videoPath).catch(() => null);
  if (!info) return NextResponse.json({ detail: 'Rendered file is missing' }, { status: 410 });
  const download = new URL(request.url).searchParams.get('download') === '1';
  const stream = Readable.toWeb(createReadStream(job.videoPath)) as ReadableStream<Uint8Array>;
  return new NextResponse(stream, {
    headers: {
      'Content-Type': 'video/mp4',
      'Content-Length': String(info.size),
      'Cache-Control': 'private, max-age=3600',
      'Content-Disposition': `${download ? 'attachment' : 'inline'}; filename="quick-reel-${renderId}.mp4"`,
    },
  });
}
