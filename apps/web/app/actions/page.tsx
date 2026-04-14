import React, { Suspense } from 'react';

import { OperatorConsole } from '../operator-console';
import { resolveOperatorContext } from '../_lib/operator-dashboard';

function ActionsFallback() {
  return (
    <div className="cl-page">
      <section className="cl-panel">
        <div className="cl-panel-header">
          <div>
            <h1 className="cl-panel-title">Loading Actions</h1>
            <p className="cl-panel-description">
              Preparing the action workspace and any prefilled IDs from your current route.
            </p>
          </div>
        </div>
      </section>
    </div>
  );
}

export default async function ActionsPage() {
  const context = await resolveOperatorContext();

  return (
    <Suspense fallback={<ActionsFallback />}>
      <OperatorConsole defaultApiBaseUrl={context.apiBaseUrl} defaultOrgId={context.orgId} />
    </Suspense>
  );
}
