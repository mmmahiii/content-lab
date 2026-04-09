import { ReelsRouteView } from '../_components/operator-console';
import { loadOperatorDashboard } from '../_lib/operator-dashboard';

export default async function ReelsPage() {
  const dashboard = await loadOperatorDashboard();

  return <ReelsRouteView dashboard={dashboard} />;
}
