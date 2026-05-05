import { NextResponse } from 'next/server';

const DEFAULT_API_BASE_URL = 'http://127.0.0.1:8000';

function resolveApiBaseUrl(): string {
  const raw =
    process.env.CONTENT_LAB_API_BASE_URL ??
    process.env.NEXT_PUBLIC_CONTENT_LAB_API_BASE_URL ??
    DEFAULT_API_BASE_URL;

  return raw.replace(/\/$/, '');
}

export async function POST(
  request: Request,
  { params }: { params: Promise<{ orgId: string; pageId: string; runId: string }> },
) {
  const { orgId, pageId, runId } = await params;
  const response = await fetch(
    `${resolveApiBaseUrl()}/orgs/${orgId}/pages/${pageId}/idea-plans/${runId}/discard`,
    {
      method: 'POST',
      headers: {
        Accept: 'application/json',
        'X-Actor-Id': request.headers.get('x-actor-id') ?? 'operator:ui-rebuild',
      },
      cache: 'no-store',
    },
  );

  return new NextResponse(await response.text(), {
    status: response.status,
    headers: {
      'Content-Type': response.headers.get('content-type') ?? 'application/json',
      'X-Request-Id': response.headers.get('x-request-id') ?? '',
    },
  });
}
