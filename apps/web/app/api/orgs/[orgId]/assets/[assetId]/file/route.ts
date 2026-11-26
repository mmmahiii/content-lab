import { proxySignedDownload } from '../../../../../../_lib/signed-download-proxy';

/**
 * Asset bytes through this origin. `?max_px=1080` serves the API's cached downscaled copy
 * (renders and previews never need more than a 1080x1920 frame).
 */
export async function GET(
  request: Request,
  { params }: { params: Promise<{ orgId: string; assetId: string }> },
) {
  const { orgId, assetId } = await params;
  const maxPx = new URL(request.url).searchParams.get('max_px');
  const query = maxPx && /^\d{2,4}$/.test(maxPx) ? `?max_px=${maxPx}` : '';
  return proxySignedDownload(request, `/orgs/${orgId}/assets/${assetId}/download${query}`, {
    immutable: true,
  });
}
