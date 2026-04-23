import type {
  JsonObject,
  PackageDetailOut,
  ProcessReelOperatorDebugOut,
  ReelDetailOut,
  RunDetailOut,
} from '@shared/types';
import { describe, expect, it } from 'vitest';

import { mergeOperatorDebug } from './creative-review';

const debug = (label: string): ProcessReelOperatorDebugOut => ({
  creative_trace: null,
  scene_plan: null,
  scene_plan_summary: null,
  prompt_trace: null,
  prompt_trace_summary: null,
  qa: {
    passed: true,
    verdict: 'pass',
    semantic_script: { verdict: 'pass', findings: [{ code: label, outcome: 'warn', message: 'x' }] },
    format: null,
    repetition: null,
    alignment: null,
    checks: [],
  },
  package_qa: null,
});

const minimalReel = {
  id: 'reel-1',
  org_id: 'org-1',
  page_id: 'page-1',
  reel_family_id: 'fam-1',
  origin: 'generated',
  status: 'ready',
  variant_label: 'A',
  external_reel_id: null,
  metadata: {},
  approved_at: null,
  approved_by: null,
  posted_at: null,
  posted_by: null,
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-01T00:00:00Z',
  operator_debug: null,
} satisfies ReelDetailOut;

function firstSemanticFindingCode(debug: ProcessReelOperatorDebugOut | null): string | undefined {
  const findings = debug?.qa?.semantic_script?.findings;
  if (!Array.isArray(findings) || findings.length === 0) {
    return undefined;
  }
  const head = findings[0] as JsonObject;
  return typeof head.code === 'string' ? head.code : undefined;
}

describe('mergeOperatorDebug', () => {
  it('prefers run debug over reel and package', () => {
    const run = { operator_debug: debug('run') } as RunDetailOut;
    const reel = { ...minimalReel, operator_debug: debug('reel') };
    const pkg = { operator_debug: debug('package') } as PackageDetailOut;

    const merged = mergeOperatorDebug(reel, run, pkg);
    expect(firstSemanticFindingCode(merged)).toBe('run');
  });

  it('falls back to package then reel', () => {
    const reel = { ...minimalReel, operator_debug: debug('reel') };
    const pkg = { operator_debug: debug('package') } as PackageDetailOut;

    expect(firstSemanticFindingCode(mergeOperatorDebug(reel, null, pkg))).toBe('package');
    expect(firstSemanticFindingCode(mergeOperatorDebug(reel, null, null))).toBe('reel');
  });
});
