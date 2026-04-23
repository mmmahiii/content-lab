import { describe, expect, it } from 'vitest';

import type { PagePolicyStateOut, PolicyStateDocument } from '@shared/types';

import { policyEditorSourceFromApi } from './operator-policy';

const baseState: PolicyStateDocument = {
  mode_ratios: { exploit: 0.3, explore: 0.4, mutation: 0.2, chaos: 0.1 },
  budget: { per_run_usd_limit: 10, daily_usd_limit: 40, monthly_usd_limit: 800 },
  thresholds: {
    similarity: { warn_at: 0.72, block_at: 0.88 },
    min_quality_score: 0.55,
  },
};

function pagePolicy(partial: Partial<PagePolicyStateOut>): PagePolicyStateOut {
  return {
    id: null,
    org_id: 'org-1',
    scope_type: 'page',
    scope_id: 'page-1',
    state: baseState,
    updated_at: null,
    is_explicit_override: false,
    inherited_from: 'default',
    ...partial,
  };
}

describe('policyEditorSourceFromApi', () => {
  it('treats persisted page rows as saved', () => {
    const policy = pagePolicy({
      id: '550e8400-e29b-41d4-a716-446655440000',
      is_explicit_override: true,
      inherited_from: null,
      updated_at: '2026-04-09T10:00:00Z',
    });
    expect(policyEditorSourceFromApi(policy)).toBe('saved');
  });

  it('treats org-wide inheritance as inherited', () => {
    const policy = pagePolicy({
      inherited_from: 'global',
      updated_at: '2026-04-09T10:00:00Z',
    });
    expect(policyEditorSourceFromApi(policy)).toBe('inherited');
  });

  it('treats built-in defaults as inherited', () => {
    const policy = pagePolicy({
      inherited_from: 'default',
    });
    expect(policyEditorSourceFromApi(policy)).toBe('inherited');
  });
});
