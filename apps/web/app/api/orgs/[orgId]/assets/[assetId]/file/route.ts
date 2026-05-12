import { NextResponse } from 'next/server';

const DEFAULT_API_BASE_URL = 'http://127.0.0.1:8000';

function resolveApiBaseUrl(): string {
  const raw =
    process.env.CONTENT_LAB_API_BASE_URL ??
    process.env.NEXT_PUBLIC_CONTENT_LAB_API_BASE_URL ??
    DEFAULT_API_BASE_URL;

  return raw.replace(/\/$/, '');
}

export async function GET(
  request: Request,
  { params }: { params: Promise<{ orgId: string; assetId: string }> },
) {
  const { orgId, assetId } = await params;
  let response: Response;
  try {
    response = await fetch(`${resolveApiBaseUrl()}/orgs/${orgId}/assets/${assetId}/download`, {
      method: 'GET',
      headers: {
        Accept: 'application/json',
        'X-Actor-Id': request.headers.get('x-actor-id') ?? 'operator:ui-rebuild',
      },
      cache: 'no-store',
    });
  } catch {
    return NextResponse.json(
      { detail: 'API is not reachable. Start the backend on port 8000, then try again.' },
      { status: 503 },
    );
  }

  if (!response.ok) {
    return new NextResponse(await response.text(), {
      status: response.status,
      headers: {
        'Content-Type': response.headers.get('content-type') ?? 'application/json',
      },
    });
  }

  const body = (await response.json()) as { url?: string };
  if (!body.url) {
    return NextResponse.json({ detail: 'Asset download URL is unavailable.' }, { status: 404 });
  }

  let assetResponse: Response;
  try {
    assetResponse = await fetch(body.url, {
      method: 'GET',
      headers: {
        ...(request.headers.get('range') ? { Range: request.headers.get('range') ?? '' } : {}),
      },
      cache: 'no-store',
    });
  } catch {
    return NextResponse.json(
      { detail: 'Asset storage is not reachable. Start MinIO, then try again.' },
      { status: 503 },
    );
  }

  const headers = new Headers({
    'Cache-Control': 'no-store',
    'Content-Type': assetResponse.headers.get('content-type') ?? 'application/octet-stream',
  });
  const contentLength = assetResponse.headers.get('content-length');
  const contentRange = assetResponse.headers.get('content-range');
  const acceptRanges = assetResponse.headers.get('accept-ranges');
  if (contentLength) {
    headers.set('Content-Length', contentLength);
  }
  if (contentRange) {
    headers.set('Content-Range', contentRange);
  }
  if (acceptRanges) {
    headers.set('Accept-Ranges', acceptRanges);
  }

  if (!assetResponse.body) {
    return new NextResponse(null, {
      status: assetResponse.status,
      headers,
    });
  }

  return new NextResponse(assetResponse.body, {
    status: assetResponse.status,
    headers,
  });
}
