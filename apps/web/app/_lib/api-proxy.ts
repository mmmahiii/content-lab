import { NextResponse } from 'next/server';

const DEFAULT_API_BASE_URL = 'http://127.0.0.1:8000';

export function resolveApiBaseUrl(): string {
  const raw =
    process.env.CONTENT_LAB_API_BASE_URL ??
    process.env.NEXT_PUBLIC_CONTENT_LAB_API_BASE_URL ??
    DEFAULT_API_BASE_URL;

  return raw.replace(/\/$/, '');
}

/** Forward a JSON POST body to the API and relay its status, body and request id. */
export async function proxyJsonPost(request: Request, apiPath: string): Promise<NextResponse> {
  let response: Response;
  try {
    response = await fetch(`${resolveApiBaseUrl()}${apiPath}`, {
      method: 'POST',
      headers: {
        Accept: 'application/json',
        'Content-Type': 'application/json',
        'X-Actor-Id': request.headers.get('x-actor-id') ?? 'operator:ui-rebuild',
      },
      body: (await request.text()) || '{}',
      cache: 'no-store',
    });
  } catch {
    return NextResponse.json(
      { detail: 'API is not reachable. Start the backend on port 8000, then try again.' },
      { status: 503 },
    );
  }

  return new NextResponse(await response.text(), {
    status: response.status,
    headers: {
      'Content-Type': response.headers.get('content-type') ?? 'application/json',
      'X-Request-Id': response.headers.get('x-request-id') ?? '',
    },
  });
}
