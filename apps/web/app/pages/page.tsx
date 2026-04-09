import { PagesRouteView } from '../_components/operator-console';
import { loadOperatorDashboard } from '../_lib/operator-dashboard';

export default async function PagesPage() {
  const dashboard = await loadOperatorDashboard();

  return <PagesRouteView dashboard={dashboard} />;
}
