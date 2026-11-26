import { NextResponse } from 'next/server';

import { proxyJsonPost } from '../../../../../../../_lib/api-proxy';

/**
 * Build (or reuse) the voice + music soundtrack for a composed Quick Reel. Adds `src`, the
 * same-origin URL the player and the render service load it from.
 */
export async function POST(
  request: Request,
  { params }: { params: Promise<{ orgId: string; pageId: string }> },
) {
  const { orgId, pageId } = await params;
  const response = await proxyJsonPost(request, `/orgs/${orgId}/pages/${pageId}/quick-reel/soundtrack`);
  if (!response.ok) return response;
  const body = (await response.json()) as { soundtrack_id: string; storage_uri: string | null };
  const src = body.storage_uri
    ? `/api/orgs/${orgId}/quick-reel/soundtracks/${body.soundtrack_id}/file`
    : null;
  return NextResponse.json({ ...body, src });
}
