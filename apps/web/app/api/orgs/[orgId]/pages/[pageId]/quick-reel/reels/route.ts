import { proxyJsonPost } from '../../../../../../../_lib/api-proxy';

/** Send to Review: save a finished Quick Reel into the page's review queue. */
export async function POST(
  request: Request,
  { params }: { params: Promise<{ orgId: string; pageId: string }> },
) {
  const { orgId, pageId } = await params;
  return proxyJsonPost(request, `/orgs/${orgId}/pages/${pageId}/quick-reel/reels`);
}
