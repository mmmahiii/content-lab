import { describe, expect, it } from 'vitest';

import {
  normalizeQaFailureFilter,
  queueItemMatchesQaFailureFilter,
  reelMatchesQaFailureFilter,
  triageQaFailure,
} from './qa-failure-triage';

describe('normalizeQaFailureFilter', () => {
  it('maps known query values', () => {
    expect(normalizeQaFailureFilter('semantic')).toBe('semantic');
    expect(normalizeQaFailureFilter('TECHNICAL')).toBe('technical');
    expect(normalizeQaFailureFilter('Unknown')).toBe('unknown');
  });

  it('falls back to all for empty or unexpected input', () => {
    expect(normalizeQaFailureFilter(undefined)).toBe('all');
    expect(normalizeQaFailureFilter('')).toBe('all');
    expect(normalizeQaFailureFilter('nope')).toBe('all');
  });
});

describe('reelMatchesQaFailureFilter', () => {
  const base = {
    origin: 'generated',
    status: 'qa_failed',
    packageStatus: 'ready' as const,
    qaFailureClass: 'semantic' as const,
  };

  it('includes every reel when filter is all', () => {
    expect(
      reelMatchesQaFailureFilter(
        { ...base, origin: 'observed', status: 'active', packageStatus: 'not_started', qaFailureClass: null },
        'all',
      ),
    ).toBe(true);
  });

  it('keeps only blocked reels that match the class', () => {
    expect(reelMatchesQaFailureFilter(base, 'semantic')).toBe(true);
    expect(reelMatchesQaFailureFilter({ ...base, qaFailureClass: 'technical' }, 'semantic')).toBe(false);
    expect(reelMatchesQaFailureFilter({ ...base, qaFailureClass: null }, 'unknown')).toBe(true);
    expect(reelMatchesQaFailureFilter({ ...base, status: 'ready', packageStatus: 'failed' }, 'semantic')).toBe(true);
  });

  it('ignores non-generated reels for narrowed filters', () => {
    expect(
      reelMatchesQaFailureFilter(
        { ...base, origin: 'observed', status: 'active', packageStatus: 'not_started' },
        'semantic',
      ),
    ).toBe(false);
  });
});

describe('queueItemMatchesQaFailureFilter', () => {
  it('passes every item for all', () => {
    expect(queueItemMatchesQaFailureFilter({ queueState: 'ready_for_review', qaFailureClass: null }, 'all')).toBe(
      true,
    );
  });

  it('requires qa_failed state and class match otherwise', () => {
    expect(
      queueItemMatchesQaFailureFilter({ queueState: 'qa_failed', qaFailureClass: 'technical' }, 'technical'),
    ).toBe(true);
    expect(
      queueItemMatchesQaFailureFilter({ queueState: 'ready_for_review', qaFailureClass: 'technical' }, 'technical'),
    ).toBe(false);
    expect(
      queueItemMatchesQaFailureFilter({ queueState: 'qa_failed', qaFailureClass: null }, 'unknown'),
    ).toBe(true);
  });
});

describe('triageQaFailure', () => {
  it('returns null when nothing is blocked', () => {
    expect(
      triageQaFailure(
        {},
        { reelStatus: 'ready', packageStatus: 'ready' },
      ),
    ).toBeNull();
  });

  it('classifies creative QA failure as semantic when packaging is healthy', () => {
    const result = triageQaFailure(
      {
        operator_debug: {
          qa: {
            semantic_script: { verdict: 'fail', message: 'too robotic' },
            format: { verdict: 'pass' },
            repetition: { verdict: 'pass' },
            alignment: { verdict: 'pass' },
            checks: [],
          },
        },
      },
      { reelStatus: 'qa_failed', packageStatus: 'ready' },
    );

    expect(result?.failureClass).toBe('semantic');
    expect(result?.gates.join(' ')).toContain('Semantic script');
  });

  it('classifies package failure without creative signals as technical', () => {
    const result = triageQaFailure(
      { package: { package_qa: { passed: false, message: 'manifest mismatch' } } },
      { reelStatus: 'ready', packageStatus: 'failed' },
    );

    expect(result?.failureClass).toBe('technical');
    expect(result?.gates.join(' ')).toMatch(/Package/i);
  });

  it('treats format QA failures as technical', () => {
    const result = triageQaFailure(
      {
        operator_debug: {
          qa: {
            semantic_script: { verdict: 'pass' },
            format: { verdict: 'fail' },
            repetition: { verdict: 'pass' },
            alignment: { verdict: 'pass' },
            checks: [],
          },
        },
      },
      { reelStatus: 'qa_failed', packageStatus: 'ready' },
    );

    expect(result?.failureClass).toBe('technical');
    expect(result?.gates.join(' ')).toContain('Format');
  });
});
