import type { ProcessReelOperatorDebugOut } from '@shared/types';
import React, { type ReactElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';

import { CreativeReviewPanel } from './creative-review-panel';

function renderMarkup(node: ReactElement): string {
  return renderToStaticMarkup(node);
}

const baseDebug: ProcessReelOperatorDebugOut = {
  creative_trace: null,
  scene_plan: null,
  scene_plan_summary: null,
  prompt_trace: null,
  prompt_trace_summary: null,
  qa: {
    passed: true,
    verdict: 'pass',
    semantic_script: {
      verdict: 'fail',
      message: 'Semantic gate failed',
      findings: [
        {
          code: 'meta_placeholder',
          outcome: 'fail',
          message: 'Copy still reads like a planner note, not viewer-facing language.',
        },
      ],
      failure_reasons: ['meta_placeholder'],
    },
    format: { verdict: 'pass' },
    repetition: { verdict: 'pass' },
    alignment: { verdict: 'pass' },
    checks: [],
    structured_findings: [],
  },
  package_qa: { passed: true },
};

describe('CreativeReviewPanel', () => {
  it('surfaces semantic findings without requiring raw logs', () => {
    const markup = renderMarkup(
      <CreativeReviewPanel
        orgId="org-1"
        pageId="page-1"
        reelId="reel-1"
        runId="run-1"
        operatorDebug={baseDebug}
        creativePlanning={null}
        packageDetail={null}
      />,
    );

    expect(markup).toContain('Creative review');
    expect(markup).toContain('Semantic QA');
    expect(markup).toContain('meta placeholder');
    expect(markup).toContain('planner note');
  });

  it('explains empty state when no debug payloads exist', () => {
    const markup = renderMarkup(
      <CreativeReviewPanel
        orgId="org-1"
        pageId="page-1"
        reelId="reel-1"
        runId={null}
        operatorDebug={null}
        creativePlanning={null}
        packageDetail={null}
      />,
    );

    expect(markup).toContain('No creative debug payload');
  });
});
