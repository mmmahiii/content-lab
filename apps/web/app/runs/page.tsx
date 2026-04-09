import { RunsRouteView } from '../_components/operator-console';
import { loadOperatorDashboard } from '../_lib/operator-dashboard';

export default async function RunsPage() {
  const dashboard = await loadOperatorDashboard();

  return <RunsRouteView dashboard={dashboard} />;
}
