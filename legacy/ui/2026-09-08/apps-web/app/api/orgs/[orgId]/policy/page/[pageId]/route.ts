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
  _request: Request,
  { params }: { params: Promise<{ orgId: string; pageId: string }> },
) {
  const { orgId, pageId } = await params;
  const response = await fetch(`${resolveApiBaseUrl()}/orgs/${orgId}/policy/page/${pageId}`, {
    method: 'GET',
    headers: {
      Accept: 'application/json',
    },
    cache: 'no-store',
  });

  return new NextResponse(await response.text(), {
    status: response.status,
    headers: {
      'Content-Type': response.headers.get('content-type') ?? 'application/json',
      'X-Request-Id': response.headers.get('x-request-id') ?? '',
    },
  });
}

export async function PATCH(
  request: Request,
  { params }: { params: Promise<{ orgId: string; pageId: string }> },
) {
  const { orgId, pageId } = await params;
  const body = await request.text();
  const response = await fetch(`${resolveApiBaseUrl()}/orgs/${orgId}/policy/page/${pageId}`, {
    method: 'PATCH',
    headers: {
      Accept: 'application/json',
      'Content-Type': 'application/json',
      'X-Actor-Id': request.headers.get('x-actor-id') ?? 'operator:ui-rebuild',
    },
    body,
    cache: 'no-store',
  });

  return new NextResponse(await response.text(), {
    status: response.status,
    headers: {
      'Content-Type': response.headers.get('content-type') ?? 'application/json',
      'X-Request-Id': response.headers.get('x-request-id') ?? '',
    },
  });
}
