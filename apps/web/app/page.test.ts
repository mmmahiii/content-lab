import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it, vi } from 'vitest';

import HomePage from './page';
import {
  HUMAN_BOUNDARY_COPY,
  createMarkPostedSubmission,
  createReelReviewSubmission,
  createReelTriggerSubmission,
  createRunTriggerSubmission,
  formatApiError,
  submitOperatorRequest,
} from './operator-console.helpers';

describe('operator console', () => {
  it('renders explicit human-review and human-posting controls', () => {
    const html = renderToStaticMarkup(createElement(HomePage));

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
