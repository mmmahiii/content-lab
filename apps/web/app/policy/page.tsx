import { PolicyRouteView } from '../_components/operator-console';
import { loadPolicyEditorSnapshot } from '../_lib/operator-policy';

export default async function PolicyPage() {
  const snapshot = await loadPolicyEditorSnapshot();

  return <PolicyRouteView snapshot={snapshot} />;
}
