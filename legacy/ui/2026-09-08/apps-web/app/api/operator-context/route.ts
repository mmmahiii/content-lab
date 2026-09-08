import { NextResponse } from 'next/server';

import {
  normalizeOrgId,
  OPERATOR_ORG_COOKIE,
} from '../../_lib/operator-context';

export async function POST(request: Request) {
  const payload = (await request.json().catch(() => null)) as { orgId?: unknown } | null;
  const orgId = normalizeOrgId(typeof payload?.orgId === 'string' ? payload.orgId : null);

  if (!orgId) {
    return NextResponse.json(
      { detail: 'Enter a valid org UUID before saving the workspace.' },
      { status: 400 },
    );
  }

  const response = NextResponse.json({ ok: true, orgId });
  response.cookies.set({
    name: OPERATOR_ORG_COOKIE,
    value: orgId,
    httpOnly: false,
    sameSite: 'lax',
    maxAge: 60 * 60 * 24 * 30,
    path: '/',
  });

  return response;
}

export async function DELETE() {
  const response = NextResponse.json({ ok: true });
  response.cookies.set({
    name: OPERATOR_ORG_COOKIE,
    value: '',
    httpOnly: false,
    sameSite: 'lax',
    expires: new Date(0),
    path: '/',
  });

  return response;
}
