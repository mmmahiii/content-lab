import { NextResponse } from 'next/server';

function isAllowedLocalArtifactUrl(url: URL): boolean {
  return ['127.0.0.1', 'localhost'].includes(url.hostname);
}

export async function GET(request: Request) {
  const requestUrl = new URL(request.url);
  const rawUrl = requestUrl.searchParams.get('url');
  if (!rawUrl) {
    return NextResponse.json({ error: 'Missing artifact url.' }, { status: 400 });
  }

  let artifactUrl: URL;
  try {
    artifactUrl = new URL(rawUrl);
  } catch {
    return NextResponse.json({ error: 'Invalid artifact url.' }, { status: 400 });
  }

  if (!isAllowedLocalArtifactUrl(artifactUrl)) {
    return NextResponse.json({ error: 'Artifact proxy only allows local URLs.' }, { status: 400 });
  }

  const response = await fetch(artifactUrl, {
    method: 'GET',
    cache: 'no-store',
  });

  return new NextResponse(await response.text(), {
    status: response.status,
    headers: {
      'Content-Type': response.headers.get('content-type') ?? 'text/plain',
    },
  });
}
