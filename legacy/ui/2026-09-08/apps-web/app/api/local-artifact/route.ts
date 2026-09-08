import { createReadStream, existsSync, statSync } from 'node:fs';
import { extname, resolve } from 'node:path';
import { Readable } from 'node:stream';

import { NextResponse } from 'next/server';

export const runtime = 'nodejs';

const allowedRoot = resolve(process.env.TEMP ?? process.env.TMP ?? '', 'content-lab-process-reel');

const contentTypes: Record<string, string> = {
  '.json': 'application/json',
  '.mp4': 'video/mp4',
  '.png': 'image/png',
  '.txt': 'text/plain; charset=utf-8',
};

function parseRange(range: string | null, size: number): { start: number; end: number } | null {
  if (!range?.startsWith('bytes=')) {
    return null;
  }
  const [startRaw, endRaw] = range.slice('bytes='.length).split('-', 2);
  const start = Number.parseInt(startRaw, 10);
  const end = endRaw ? Number.parseInt(endRaw, 10) : size - 1;
  if (!Number.isFinite(start) || !Number.isFinite(end) || start < 0 || end < start) {
    return null;
  }
  return { start, end: Math.min(end, size - 1) };
}

export async function GET(request: Request) {
  const requestUrl = new URL(request.url);
  const rawPath = requestUrl.searchParams.get('path');
  if (!rawPath) {
    return NextResponse.json({ error: 'Missing artifact path.' }, { status: 400 });
  }

  const artifactPath = resolve(rawPath);
  if (!allowedRoot || !artifactPath.startsWith(`${allowedRoot}\\`)) {
    return NextResponse.json({ error: 'Artifact path is outside the allowed run output root.' }, { status: 400 });
  }
  if (!existsSync(artifactPath)) {
    return NextResponse.json({ error: 'Artifact file was not found.' }, { status: 404 });
  }

  const stat = statSync(artifactPath);
  const contentType = contentTypes[extname(artifactPath).toLowerCase()] ?? 'application/octet-stream';
  const range = parseRange(request.headers.get('range'), stat.size);
  const headers = new Headers({
    'Accept-Ranges': 'bytes',
    'Content-Type': contentType,
  });

  if (range) {
    headers.set('Content-Length', String(range.end - range.start + 1));
    headers.set('Content-Range', `bytes ${range.start}-${range.end}/${stat.size}`);
    const stream = createReadStream(artifactPath, { start: range.start, end: range.end });
    return new NextResponse(Readable.toWeb(stream) as ReadableStream, {
      status: 206,
      headers,
    });
  }

  headers.set('Content-Length', String(stat.size));
  const stream = createReadStream(artifactPath);
  return new NextResponse(Readable.toWeb(stream) as ReadableStream, {
    status: 200,
    headers,
  });
}
