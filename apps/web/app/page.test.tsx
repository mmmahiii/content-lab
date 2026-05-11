import React from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';

import HomePage from './page';
import { AssetPackGenerationWorkspace, HookImageCreator } from './page-workspace';

describe('HomePage', () => {
  it('renders the current workspace UI', () => {
    const markup = renderToStaticMarkup(<HomePage />);

    expect(markup).toContain('Content Lab');
    expect(markup).toContain('Pages');
    expect(markup).toContain('Reel workbench');
    expect(markup).toContain('Create your first page');
    expect(markup).not.toContain('Inspector');
  });

  it('renders the collapsible reusable asset library inside asset pack generation', () => {
    const markup = renderToStaticMarkup(
      <AssetPackGenerationWorkspace
        selectedPage={{
          id: 'page-1',
          platform: 'instagram',
          display_name: 'Demo page',
          external_page_id: null,
          handle: '@demo',
          ownership: 'owned',
          created_at: '2026-05-07T00:00:00.000Z',
          updated_at: '2026-05-07T00:00:00.000Z',
        }}
        onRunsChanged={() => undefined}
        setWorkspaceMessage={() => undefined}
      />,
    );

    expect(markup).toContain('Asset combinator');
    expect(markup).toContain('Reusable assets');
    expect(markup).toContain('Collapse');
    expect(markup).toContain('Asset pack planner');
    expect(markup).toContain('Pack plan outbox');
    expect(markup).toContain('Pack browser');
    expect(markup).toContain('View pack');
    expect(markup).toContain('Combinator output');
    expect(markup).toContain('Generated hook / cover');
    expect(markup).toContain('Saved pack');
    expect(markup).toContain('No saved packs loaded');
  });

  it('renders the local hook image creator as a standalone workspace', () => {
    const markup = renderToStaticMarkup(<HookImageCreator />);

    expect(markup).toContain('Live hook image creator');
    expect(markup).toContain('Reel hook image');
    expect(markup).toContain('Reset local image');
  });
});
