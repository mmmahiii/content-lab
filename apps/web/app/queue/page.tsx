import React from 'react';

import { QueueRouteView } from '../_components/operator-console';
import { loadOperatorDashboard } from '../_lib/operator-dashboard';

function firstString(value: string | string[] | undefined): string | undefined {
  if (Array.isArray(value)) {
    return value[0];
  }

  return value;
}

export default async function QueuePage(
  props: {
    searchParams?: Record<string, string | string[] | undefined>;
  } = {},
) {
  const searchParams = props.searchParams ?? {};
  const dashboard = await loadOperatorDashboard();
  const qaFailureFilter = firstString(searchParams.qaFailure);

  return <QueueRouteView dashboard={dashboard} qaFailureFilter={qaFailureFilter} />;
}
