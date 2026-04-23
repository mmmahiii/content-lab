import React, { type ReactElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';

import { QaFailedWorkbench } from './qa-failed-workbench';

function renderMarkup(node: ReactElement): string {
  return renderToStaticMarkup(node);
}

describe('QaFailedWorkbench', () => {
  it('renders filter links and row content', () => {
    const markup = renderMarkup(
      <QaFailedWorkbench
        orgId="org-1"
        basePath="/queue"
        activeFilter="semantic"
        rows={[
          {
            id: 'reel-1',
            pageId: 'page-1',
            pageName: 'Demo page',
            variantLabel: 'Variant A',
            qaFailureClass: 'semantic',
            qaFailureGates: ['Semantic script'],
            qaFailureNextAction: 'Fix copy',
            lastRunId: 'run-1',
          },
        ]}
      />,
    );

    expect(markup).toContain('/queue?qaFailure=semantic');
    expect(markup).toContain('/queue?qaFailure=technical');
    expect(markup).toContain('Variant A');
    expect(markup).toContain('Demo page');
    expect(markup).toContain('Failing gates');
  });
});
