import { NextResponse } from 'next/server';

import { proxySignedDownload } from '../../../../../../../_lib/signed-download-proxy';

/** The Quick Reel soundtrack WAV (voice + music), played by the player and the render. */
export async function GET(
  request: Request,
  { params }: { params: Promise<{ orgId: string; soundtrackId: string }> },
) {
  const { orgId, soundtrackId } = await params;
  if (!/^[0-9a-f]{8,64}$/.test(soundtrackId)) {
    return NextResponse.json({ detail: 'Invalid soundtrack id' }, { status: 422 });
  }
  return proxySignedDownload(request, `/orgs/${orgId}/quick-reel/soundtracks/${soundtrackId}/download`, {
    immutable: true,
  });
}
