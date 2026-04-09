import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';

import { DashboardHomeView } from './_components/operator-console';
import type { OperatorDashboardSnapshot } from './_lib/operator-dashboard';

const readyDashboard: OperatorDashboardSnapshot = {
  context: {
    apiBaseUrl: 'http://127.0.0.1:8000',
    orgId: 'f67e1d69-2190-468c-b14d-6306f282f9d6',
  },
  pages: {
    state: 'ready',
    data: [
      {
        id: 'page-1',
        displayName: 'Northwind Fitness',
        platform: 'instagram',
        handle: '@northwind.fit',
        ownership: 'owned',
        updatedAt: '2026-04-09T09:10:00.000Z',
      },
    ],
  },
  runs: {
    state: 'ready',
    data: [
      {
        id: 'run-1',
        workflowKey: 'process_reel',
        flowTrigger: 'reel_trigger',
        status: 'running',
        updatedAt: '2026-04-09T09:16:00.000Z',
        externalRef: 'outbox:123',
        taskSummary: '1 running, 2 succeeded',
        currentStep: 'packaging',
        pageName: 'Northwind Fitness',
        reelId: 'reel-1',
        packageStatus: 'pending',
      },
    ],
  },
  reels: {
    state: 'ready',
    data: [
      {
        id: 'reel-1',
        pageId: 'page-1',
        pageName: 'Northwind Fitness',
        variantLabel: 'Coach intro A',
        origin: 'generated',
        status: 'ready',
        createdAt: '2026-04-09T09:12:00.000Z',
        updatedAt: '2026-04-09T09:16:00.000Z',
        currentStep: 'packaging',
        lastRunId: 'run-1',
        packageStatus: 'ready',
        packageMessage: 'Package is ready for operator review.',
      },
    ],
  },
};

describe('HomePage', () => {
  it('renders an operator dashboard shell with the production sections', () => {
    const markup = renderToStaticMarkup(
      createElement(DashboardHomeView, { dashboard: readyDashboard }),
    );

    expect(markup).toContain('Production visibility for pages, runs, reels, and packages');
    expect(markup).toContain('Owned pages');
    expect(markup).toContain('Current runs');
    expect(markup).toContain('Recent reels');
    expect(markup).toContain('Northwind Fitness');
    expect(markup).toContain('package ready');
  });

  it('renders configuration and empty-state messaging when data is unavailable', () => {
    const markup = renderToStaticMarkup(
      createElement(DashboardHomeView, {
        dashboard: {
          context: {
            apiBaseUrl: 'http://127.0.0.1:8000',
            orgId: null,
            configurationMessage:
              'Set CONTENT_LAB_OPERATOR_ORG_ID to an org UUID so the operator dashboard can load API data.',
          },
          pages: {
            state: 'unconfigured',
            data: [],
            message:
              'Set CONTENT_LAB_OPERATOR_ORG_ID to an org UUID so the operator dashboard can load API data.',
          },
          runs: {
            state: 'empty',
            data: [],
            message: 'Runs will appear after the first reel workflow starts.',
          },
          reels: {
            state: 'error',
            data: [],
            message: 'Recent reels depend on the owned page feed and are currently unavailable.',
          },
        },
      }),
    );

    expect(markup).toContain('Set CONTENT_LAB_OPERATOR_ORG_ID');
    expect(markup).toContain('Runs will appear after the first reel workflow starts.');
    expect(markup).toContain('Recent reels depend on the owned page feed');
  });
});
