import React from 'react';

import { QueueRouteView } from '../_components/operator-console';
import { loadOperatorDashboard } from '../_lib/operator-dashboard';

function firstString(value: string | string[] | undefined): string | undefined {
  if (Array.isArray(value)) {
    return value[0];
  }

  return value;
}

type QueuePageProps = {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
};

export default async function QueuePage({ searchParams: searchParamsPromise }: QueuePageProps) {
  const searchParams = await searchParamsPromise;
  const dashboard = await loadOperatorDashboard();
  const qaFailureFilter = firstString(searchParams.qaFailure);

  return <QueueRouteView dashboard={dashboard} qaFailureFilter={qaFailureFilter} />;
}
