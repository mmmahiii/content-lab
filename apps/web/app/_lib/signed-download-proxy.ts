import { NextResponse } from 'next/server';

import { resolveApiBaseUrl } from './api-proxy';

/**
 * Stream an object the API exposes as a signed download (`{ url }` JSON) through this origin,
 * so the browser and the headless render tab never talk to object storage directly. Range
 * requests are forwarded (audio and video seeking). Pass `immutable` only for objects whose
 * bytes never change for the URL.
 */
export async function proxySignedDownload(
  request: Request,
  apiPath: string,
  options: { immutable?: boolean } = {},
): Promise<NextResponse> {
  let response: Response;
  try {
    response = await fetch(`${resolveApiBaseUrl()}${apiPath}`, {
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
      headers: { 'Content-Type': response.headers.get('content-type') ?? 'application/json' },
    });
  }
  const body = (await response.json()) as { url?: string };
  if (!body.url) {
    return NextResponse.json({ detail: 'Download URL is unavailable.' }, { status: 404 });
  }

  let objectResponse: Response;
  try {
    objectResponse = await fetch(body.url, {
      method: 'GET',
      headers: request.headers.get('range') ? { Range: request.headers.get('range') ?? '' } : {},
      cache: 'no-store',
    });
  } catch {
    return NextResponse.json(
      { detail: 'Object storage is not reachable. Start MinIO, then try again.' },
      { status: 503 },
    );
  }
  const cacheable = options.immutable === true && objectResponse.ok;
  const headers = new Headers({
    // Immutable objects (an asset's bytes, a content-addressed soundtrack) may be cached:
    // Remotion's render tabs otherwise re-download every image for every frame batch.
    'Cache-Control': cacheable ? 'private, max-age=86400, immutable' : 'no-store',
    'Content-Type': objectResponse.headers.get('content-type') ?? 'application/octet-stream',
  });
  for (const name of ['content-length', 'content-range', 'accept-ranges']) {
    const value = objectResponse.headers.get(name);
    if (value) headers.set(name, value);
  }
  return new NextResponse(objectResponse.body, { status: objectResponse.status, headers });
}
