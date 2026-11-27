import { NextResponse } from 'next/server';

import { proxySignedDownload } from '../../../../../../../_lib/signed-download-proxy';

/** A stored Quick Reel MP4 (exports are content-addressed, so the bytes never change). */
export async function GET(
  request: Request,
  { params }: { params: Promise<{ orgId: string; renderId: string }> },
) {
  const { orgId, renderId } = await params;
  if (!/^[0-9a-f]{8,64}$/.test(renderId)) {
    return NextResponse.json({ detail: 'Invalid render id' }, { status: 422 });
  }
  return proxySignedDownload(request, `/orgs/${orgId}/quick-reel/renders/${renderId}/download`, {
    immutable: true,
  });
}
