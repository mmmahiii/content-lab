import { DashboardHomeView } from './_components/operator-console';
import { loadOperatorDashboard } from './_lib/operator-dashboard';

export default async function HomePage() {
  const dashboard = await loadOperatorDashboard();

  return <DashboardHomeView dashboard={dashboard} />;
}
