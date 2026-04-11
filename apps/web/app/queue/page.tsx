import { QueueRouteView } from '../_components/operator-console';
import { loadOperatorDashboard } from '../_lib/operator-dashboard';

export default async function QueuePage() {
  const dashboard = await loadOperatorDashboard();

  return <QueueRouteView dashboard={dashboard} />;
}
