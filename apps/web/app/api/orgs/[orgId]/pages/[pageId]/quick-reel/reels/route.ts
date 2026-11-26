import { NextResponse } from 'next/server';

import { proxyJsonPost } from '../../../../../../../_lib/api-proxy';
import { getRenderQueue } from '../../../../../../../_lib/quick-reel/render-queue';
import { ReviewUploadError, uploadRenderForReview } from '../../../../../../../_lib/quick-reel/review-upload';

/**
 * Send to Review: save a finished Quick Reel into the page's review queue. When the reel was
 * rendered, its MP4 is first uploaded to object storage and QA-checked by the API, which
 * attaches the QA report (and marks the reel `qa_failed` if a blocking gate failed).
 */
export async function POST(
  request: Request,
  { params }: { params: Promise<{ orgId: string; pageId: string }> },
) {
  const { orgId, pageId } = await params;
  const raw = await request.text();
  type SendBody = { render?: { render_id?: unknown } | null } | null;
  let body: SendBody = null;
  try {
    body = raw ? (JSON.parse(raw) as SendBody) : null;
  } catch {
    return NextResponse.json({ detail: 'Body must be JSON' }, { status: 400 });
  }
  const renderId = body?.render?.render_id;
  if (typeof renderId === 'string' && renderId) {
    try {
      await uploadRenderForReview({
        orgId,
        pageId,
        renderId,
        queue: await getRenderQueue(),
        actor: request.headers.get('x-actor-id') ?? 'operator:ui-rebuild',
      });
    } catch (error) {
      const status = error instanceof ReviewUploadError ? error.status : 502;
      const detail = error instanceof Error ? error.message : String(error);
      return NextResponse.json({ detail: detail.slice(0, 600) }, { status });
    }
  }
  const forwarded = new Request(request.url, {
    method: 'POST',
    headers: request.headers,
    body: raw || '{}',
  });
  return proxyJsonPost(forwarded, `/orgs/${orgId}/pages/${pageId}/quick-reel/reels`);
}
