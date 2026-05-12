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
  return NextResponse.redirect(body.url, 307);
}
