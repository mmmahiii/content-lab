import { describe, expect, it } from 'vitest';

import {
  describeOperatorContextSource,
  normalizeOrgId,
  resolveOperatorOrgId,
} from './operator-context';

describe('operator context helpers', () => {
  it('normalizes valid org IDs and rejects invalid values', () => {
    expect(normalizeOrgId(' 7d3d7599-820e-4c8d-9c74-3d3b6d6f2785 ')).toBe(
      '7d3d7599-820e-4c8d-9c74-3d3b6d6f2785',
    );
    expect(normalizeOrgId('not-a-uuid')).toBeNull();
    expect(normalizeOrgId('')).toBeNull();
  });

  it('prefers a saved browser org over the environment default', () => {
    expect(
      resolveOperatorOrgId({
        cookieOrgId: '7d3d7599-820e-4c8d-9c74-3d3b6d6f2785',
        envOrgId: '495d0d7e-acde-4c1d-b7ef-e5bc0d8ba3f4',
      }),
    ).toEqual({
      orgId: '7d3d7599-820e-4c8d-9c74-3d3b6d6f2785',
      source: 'cookie',
    });
  });

  it('falls back to the environment org when no saved browser org exists', () => {
    expect(
      resolveOperatorOrgId({
        cookieOrgId: null,
        envOrgId: '495d0d7e-acde-4c1d-b7ef-e5bc0d8ba3f4',
      }),
    ).toEqual({
      orgId: '495d0d7e-acde-4c1d-b7ef-e5bc0d8ba3f4',
      source: 'env',
    });
  });

  it('describes the source in plain language', () => {
    expect(describeOperatorContextSource('cookie')).toBe('Saved from the console');
    expect(describeOperatorContextSource('env')).toBe('Loaded from environment');
    expect(describeOperatorContextSource('unconfigured')).toBe('Not selected yet');
  });
});
