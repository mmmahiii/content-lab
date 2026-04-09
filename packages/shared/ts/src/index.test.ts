import { describe, it, expect } from 'vitest';
import type { HealthResponse, ReelResponse, RunCreateRequest } from './types';

describe('types', () => {
  it('compiles', () => {
    const x: HealthResponse = { status: 'ok' };
    const run: RunCreateRequest = {
      workflow_key: 'daily_reel_factory',
      input_params: {},
      metadata: {},
    };
    const reel: ReelResponse = {
      id: '11111111-1111-4111-8111-111111111111',
      org_id: '11111111-1111-4111-8111-111111111111',
      page_id: '22222222-2222-4222-8222-222222222222',
      reel_family_id: '33333333-3333-4333-8333-333333333333',
      origin: 'generated',
      status: 'ready',
      variant_label: 'Ready cut',
      external_reel_id: null,
      metadata: {},
      approved_at: null,
      approved_by: null,
      posted_at: null,
      posted_by: null,
      created_at: '2026-01-01T00:00:00Z',
      updated_at: '2026-01-01T00:00:00Z',
    };

    expect(x.status).toBe('ok');
    expect(run.workflow_key).toBe('daily_reel_factory');
    expect(reel.status).toBe('ready');
  });
});
