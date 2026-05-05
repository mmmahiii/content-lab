import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';

import HomePage from './page';

describe('HomePage', () => {
  it('renders the current workspace UI', () => {
    const markup = renderToStaticMarkup(<HomePage />);

    expect(markup).toContain('Content Lab');
    expect(markup).toContain('Pages');
    expect(markup).toContain('Reel workflow');
    expect(markup).toContain('Create your first page');
    expect(markup).toContain('Package plan');
    expect(markup).toContain('Policy');
  });
});
