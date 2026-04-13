import { createElement, type ReactElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it, vi } from 'vitest';

import { DashboardHomeView, QueueRouteView } from './_components/operator-console';
import type { OperatorDashboardSnapshot } from './_lib/operator-dashboard';
import HomePage from './page';
import { createPolicyUpdateSubmission } from './policy-editor.helpers';
import {
  HUMAN_BOUNDARY_COPY,
  createMarkPostedSubmission,
  createReelReviewSubmission,
  createReelTriggerSubmission,
  createRunTriggerSubmission,
  formatApiError,
  submitOperatorRequest,
} from './operator-console.helpers';

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

async function renderRoute(
  node: Promise<ReactElement | null> | ReactElement | null,
): Promise<string> {
  const resolved = await node;
  if (resolved === null) {
    throw new Error('Route rendered null');
  }
  return renderToStaticMarkup(resolved);
}

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

  it('renders explicit human-review and human-posting controls on the home route', async () => {
    const html = await renderRoute(HomePage());

    expect(html).toContain('Trigger Run');
    expect(html).toContain('Trigger Reel');
    expect(html).toContain('Approve Reel');
    expect(html).toContain('Archive Reel');
    expect(html).toContain('Mark Posted');
    expect(html).toContain('Human Review');
    expect(html).toContain('Human Posting');
    expect(html).toContain(HUMAN_BOUNDARY_COPY);
    expect(html).toContain('/approve');
    expect(html).toContain('/archive');
    expect(html).toContain('/mark-posted');
  });
});

describe('queue view', () => {
  it('renders ready-for-review, QA-failed, and posted states in one working queue', () => {
    const markup = renderToStaticMarkup(
      createElement(QueueRouteView, {
        dashboard: {
          ...readyDashboard,
          reels: {
            state: 'ready',
            data: [
              readyDashboard.reels.data[0],
              {
                id: 'reel-2',
                pageId: 'page-1',
                pageName: 'Northwind Fitness',
                variantLabel: 'Coach intro B',
                origin: 'generated',
                status: 'qa_failed',
                createdAt: '2026-04-09T09:18:00.000Z',
                updatedAt: '2026-04-09T09:22:00.000Z',
                currentStep: 'qa_review',
                lastRunId: 'run-2',
                packageStatus: 'failed',
                packageMessage: 'Package QA failed.',
              },
              {
                id: 'reel-3',
                pageId: 'page-1',
                pageName: 'Northwind Fitness',
                variantLabel: 'Coach intro C',
                origin: 'generated',
                status: 'posted',
                createdAt: '2026-04-09T09:20:00.000Z',
                updatedAt: '2026-04-09T09:28:00.000Z',
                currentStep: 'posted',
                lastRunId: 'run-3',
                packageStatus: 'ready',
                packageMessage: 'Package is ready for operator review.',
              },
            ],
          },
        },
      }),
    );

    expect(markup).toContain('Package-ready working queue');
    expect(markup).toContain('ready for review');
    expect(markup).toContain('qa failed');
    expect(markup).toContain('posted');
    expect(markup).toContain('Reel detail');
    expect(markup).toContain('Row actions');
  });
});

describe('operator console helpers', () => {
  it('builds a manual run trigger request for the audited route', () => {
    const result = createRunTriggerSubmission({
      orgId: '11111111-1111-4111-8111-111111111111',
      actorId: 'operator:queue-manager',
      workflowKey: 'daily_reel_factory',
      inputParamsText: '{"page_limit":3}',
      metadataText: '{"operator_note":"morning batch"}',
      idempotencyKey: 'factory-batch-001',
    });

    expect(result.ok).toBe(true);
    if (!result.ok) {
      return;
    }

    expect(result.value.actionPath).toBe('/orgs/11111111-1111-4111-8111-111111111111/runs');
    expect(result.value.headers['X-Actor-Id']).toBe('operator:queue-manager');
    expect(result.value.body).toBe(
      JSON.stringify({
        workflow_key: 'daily_reel_factory',
        input_params: { page_limit: 3 },
        metadata: { operator_note: 'morning batch' },
        idempotency_key: 'factory-batch-001',
      }),
    );
  });

  it('blocks reserved reel trigger keys before the API request is sent', () => {
    const result = createReelTriggerSubmission({
      orgId: '11111111-1111-4111-8111-111111111111',
      pageId: '22222222-2222-4222-8222-222222222222',
      reelId: '33333333-3333-4333-8333-333333333333',
      actorId: 'operator:queue-manager',
      inputParamsText: '{"org_id":"should-not-pass"}',
      metadataText: '{}',
      idempotencyKey: '',
    });

    expect(result.ok).toBe(false);
    if (result.ok) {
      return;
    }

    expect(result.fieldErrors.inputParamsText).toContain('reserved keys');
  });

  it('requires a human confirmation before mark-posted can be submitted', () => {
    const result = createMarkPostedSubmission({
      orgId: '11111111-1111-4111-8111-111111111111',
      pageId: '22222222-2222-4222-8222-222222222222',
      reelId: '33333333-3333-4333-8333-333333333333',
      actorId: 'operator:publisher',
      manualConfirmation: false,
    });

    expect(result.ok).toBe(false);
    if (result.ok) {
      return;
    }

    expect(result.fieldErrors.manualConfirmation).toContain('human has already posted');
  });

  it('maps human review actions directly to audited API routes', () => {
    const result = createReelReviewSubmission(
      {
        orgId: '11111111-1111-4111-8111-111111111111',
        pageId: '22222222-2222-4222-8222-222222222222',
        reelId: '33333333-3333-4333-8333-333333333333',
        actorId: 'operator:reviewer',
      },
      'approve',
    );

    expect(result.ok).toBe(true);
    if (!result.ok) {
      return;
    }

    expect(result.value.actionPath).toBe(
      '/orgs/11111111-1111-4111-8111-111111111111/pages/22222222-2222-4222-8222-222222222222/reels/33333333-3333-4333-8333-333333333333/approve',
    );
  });

  it('formats FastAPI validation errors into readable operator feedback', () => {
    expect(
      formatApiError(422, {
        detail: [
          {
            loc: ['body', 'input_params'],
            msg: 'Field required',
            type: 'missing',
          },
        ],
      }),
    ).toEqual(['body.input_params: Field required']);
  });

  it('surfaces API conflict responses cleanly', async () => {
    const submission = createReelReviewSubmission(
      {
        orgId: '11111111-1111-4111-8111-111111111111',
        pageId: '22222222-2222-4222-8222-222222222222',
        reelId: '33333333-3333-4333-8333-333333333333',
        actorId: 'operator:reviewer',
      },
      'approve',
    );

    expect(submission.ok).toBe(true);
    if (!submission.ok) {
      return;
    }

    const fetchMock = vi.fn(async () => {
      return new Response(
        JSON.stringify({ detail: 'Only ready generated reels can be approved' }),
        {
          status: 409,
          statusText: 'Conflict',
          headers: {
            'Content-Type': 'application/json',
          },
        },
      );
    });

    const feedback = await submitOperatorRequest(
      'http://127.0.0.1:8000',
      submission.value,
      fetchMock as typeof fetch,
    );

    expect(fetchMock).toHaveBeenCalledOnce();
    expect(feedback.kind).toBe('error');
    expect(feedback.route).toBe(submission.value.actionPath);
    expect(feedback.details).toEqual(['Only ready generated reels can be approved']);
  });
});

describe('policy form helpers', () => {
  it('builds a page-policy PATCH request within the allowed schema', () => {
    const result = createPolicyUpdateSubmission({
      orgId: '11111111-1111-4111-8111-111111111111',
      pageId: '22222222-2222-4222-8222-222222222222',
      form: {
        actorId: 'operator:policy-manager',
        state: {
          mode_ratios: {
            exploit: 0.3,
            explore: 0.4,
            mutation: 0.2,
            chaos: 0.1,
          },
          budget: {
            per_run_usd_limit: 12,
            daily_usd_limit: 45,
            monthly_usd_limit: 900,
          },
          thresholds: {
            similarity: {
              warn_at: 0.72,
              block_at: 0.88,
            },
            min_quality_score: 0.62,
          },
        },
      },
    });

    expect(result.ok).toBe(true);
    if (!result.ok) {
      return;
    }

    expect(result.value.actionPath).toBe(
      '/orgs/11111111-1111-4111-8111-111111111111/policy/page/22222222-2222-4222-8222-222222222222',
    );
    expect(result.value.headers['X-Actor-Id']).toBe('operator:policy-manager');
    expect(result.value.body).toBe(
      JSON.stringify({
        mode_ratios: {
          exploit: 0.3,
          explore: 0.4,
          mutation: 0.2,
          chaos: 0.1,
        },
        budget: {
          per_run_usd_limit: 12,
          daily_usd_limit: 45,
          monthly_usd_limit: 900,
        },
        thresholds: {
          similarity: {
            warn_at: 0.72,
            block_at: 0.88,
          },
          min_quality_score: 0.62,
        },
      }),
    );
  });

  it('blocks policy values that violate phase-1 guardrails before PATCH submission', () => {
    const result = createPolicyUpdateSubmission({
      orgId: '11111111-1111-4111-8111-111111111111',
      pageId: '22222222-2222-4222-8222-222222222222',
      form: {
        actorId: 'operator:policy-manager',
        state: {
          mode_ratios: {
            exploit: 0.5,
            explore: 0.4,
            mutation: 0.2,
            chaos: 0.1,
          },
          budget: {
            per_run_usd_limit: 60,
            daily_usd_limit: 45,
            monthly_usd_limit: 900,
          },
          thresholds: {
            similarity: {
              warn_at: 0.9,
              block_at: 0.88,
            },
            min_quality_score: 0.62,
          },
        },
      },
    });

    expect(result.ok).toBe(false);
    if (result.ok) {
      return;
    }

    expect(result.fieldErrors.mode_ratios).toContain('sum to 1.00');
    expect(result.fieldErrors.budget).toContain('Per-run budget');
    expect(result.fieldErrors.thresholds).toContain('warning threshold');
  });
});
