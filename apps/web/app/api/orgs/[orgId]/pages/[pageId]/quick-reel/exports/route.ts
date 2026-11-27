import { NextResponse } from 'next/server';

import { proxyJsonPost } from '../../../../../../../_lib/api-proxy';

/** Fast FFmpeg export of a composed Quick Reel (built, stored and QA-checked by the API). */
export async function POST(
  request: Request,
  { params }: { params: Promise<{ orgId: string; pageId: string }> },
) {
  const { orgId, pageId } = await params;
  const response = await proxyJsonPost(request, `/orgs/${orgId}/pages/${pageId}/quick-reel/exports`);
  if (!response.ok) return response;
  const body = (await response.json()) as { export_id: string };
  return NextResponse.json({
    ...body,
    video_url: `/api/orgs/${orgId}/quick-reel/renders/${body.export_id}/file`,
  });
}
