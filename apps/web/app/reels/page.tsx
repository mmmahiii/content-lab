import React from 'react';

import { ReelsRouteView } from '../_components/operator-console';
import { loadOperatorDashboard } from '../_lib/operator-dashboard';

function firstString(value: string | string[] | undefined): string | undefined {
  if (Array.isArray(value)) {
    return value[0];
  }

  return value;
}

type ReelsPageProps = {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
};

export default async function ReelsPage({ searchParams: searchParamsPromise }: ReelsPageProps) {
  const searchParams = await searchParamsPromise;
  const dashboard = await loadOperatorDashboard();
  const qaFailureFilter = firstString(searchParams.qaFailure);

  return <ReelsRouteView dashboard={dashboard} qaFailureFilter={qaFailureFilter} />;
}
