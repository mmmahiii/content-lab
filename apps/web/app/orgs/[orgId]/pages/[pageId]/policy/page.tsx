import React from 'react';
import { notFound } from 'next/navigation';

import { PagePolicyRouteView } from '../../../../../_components/page-workspace';
import { loadPageWorkspaceSnapshot } from '../../../../../_lib/operator-page-workspace';

export default async function PagePolicyPage({
  params,
}: {
  params: Promise<{ orgId: string; pageId: string }>;
}) {
  const { orgId, pageId } = await params;
  const snapshot = await loadPageWorkspaceSnapshot(orgId, pageId);

  if (snapshot === null) {
    notFound();
  }

  return <PagePolicyRouteView snapshot={snapshot} />;
}
