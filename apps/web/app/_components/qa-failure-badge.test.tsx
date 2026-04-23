import React, { type ReactElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';

import { QaFailureClassBadge, QaFailureGatesSummary } from './qa-failure-badge';

function renderMarkup(node: ReactElement): string {
  return renderToStaticMarkup(node);
}

describe('QaFailureClassBadge', () => {
  it('renders semantic and technical labels', () => {
    expect(renderMarkup(<QaFailureClassBadge failureClass="semantic" />)).toContain('Semantic / content');
    expect(renderMarkup(<QaFailureClassBadge failureClass="technical" />)).toContain('Packaging / format');
    expect(renderMarkup(<QaFailureClassBadge failureClass="unknown" />)).toContain('Needs classification');
  });
});

describe('QaFailureGatesSummary', () => {
  it('lists failing gates', () => {
    const markup = renderMarkup(<QaFailureGatesSummary gates={['Semantic script', 'Package QA']} />);
    expect(markup).toContain('Failing gates');
    expect(markup).toContain('Semantic script');
    expect(markup).toContain('Package QA');
  });

  it('renders nothing when there are no gates', () => {
    expect(renderMarkup(<QaFailureGatesSummary gates={[]} />)).toBe('');
  });
});
