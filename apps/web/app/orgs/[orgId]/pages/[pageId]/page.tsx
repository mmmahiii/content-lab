import React from 'react';
import { redirect } from 'next/navigation';

import { PageOverviewRouteView } from '../../../../_components/page-workspace';
import { loadPageWorkspaceSnapshot } from '../../../../_lib/operator-page-workspace';

export default async function PageDetailPage({
  params,
}: {
  params: Promise<{ orgId: string; pageId: string }>;
}) {
  const { orgId, pageId } = await params;
  const snapshot = await loadPageWorkspaceSnapshot(orgId, pageId);

  if (snapshot === null) {
    redirect('/pages');
  }

  return <PageOverviewRouteView snapshot={snapshot} />;
}
