import { NextResponse } from 'next/server';

import { getRenderQueue, jobView } from '../../../../_lib/quick-reel/render-queue';

export const runtime = 'nodejs';
export const dynamic = 'force-dynamic';

export async function GET(_request: Request, { params }: { params: Promise<{ renderId: string }> }) {
  const { renderId } = await params;
  const job = (await getRenderQueue()).get(renderId);
  if (!job) return NextResponse.json({ detail: 'Render not found' }, { status: 404 });
  return NextResponse.json(jobView(job), { headers: { 'Cache-Control': 'no-store' } });
}
