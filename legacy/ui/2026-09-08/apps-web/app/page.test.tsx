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

  it('renders the compact pack browser inside asset pack generation', () => {
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

    expect(markup).toContain('Saved packs and asset library');
    expect(markup).toContain('Collapse');
    expect(markup).toContain('Planner + creator');
    expect(markup).toContain('Pack browser');
    expect(markup).toContain('Pack');
    expect(markup).toContain('Asset');
    expect(markup).toContain('Name');
    expect(markup).toContain('Total asset count');
    expect(markup).toContain('Create pack');
    expect(markup).toContain('Delete pack');
    expect(markup).toContain('Create asset');
    expect(markup).toContain('Delete asset');
    expect(markup).toContain('Quality');
    expect(markup).toContain('Format');
    expect(markup).toContain('Style');
    expect(markup).toContain('Provider');
    expect(markup).toContain('Model');
    expect(markup).toContain('All backgrounds and objects');
    expect(markup).toContain('All');
    expect(markup).toContain('Backgrounds');
    expect(markup).toContain('Objects');
    expect(markup).toContain('backgrounds');
    expect(markup).toContain('objects');
    expect(markup).not.toContain('Asset library categories');
    expect(markup).not.toContain('No saved packs loaded');
    expect(markup).not.toContain('Save pack plan');
    expect(markup).not.toContain('Approve pack plan');
    expect(markup).not.toContain('Pack plan outbox');
    expect(markup).not.toContain('Optional asset split');
  });

  it('renders the local hook image creator as a standalone workspace', () => {
    const markup = renderToStaticMarkup(<HookImageCreator />);

    expect(markup).toContain('Live hook image creator');
    expect(markup).toContain('Reel hook image');
    expect(markup).toContain('Live asset browser');
    expect(markup).toContain('Existing saved image');
    expect(markup).toContain('Cinematic Planner');
    expect(markup).toContain('Saved pack');
    expect(markup).toContain('Content goal');
    expect(markup).toContain('Duration seconds');
    expect(markup).toContain('Brand/persona constraints JSON');
    expect(markup).toContain('Platform constraints JSON');
    expect(markup).toContain('Pin prompt paths');
    expect(markup).toContain('Ban prompt paths');
    expect(markup).toContain('Master prompt');
    expect(markup).toContain('Paste ChatGPT JSON');
    expect(markup).toContain('Canvas contents');
    expect(markup).toContain('All backgrounds and objects');
    expect(markup).toContain('Refresh packs');
    expect(markup).toContain('Generate master prompt');
    expect(markup).toContain('Copy prompt');
    expect(markup).toContain('Validate plan JSON');
    expect(markup).toContain('Reset local image');
    expect(markup).toContain('Save image');
    expect(markup).toContain('Create blank/new');
    expect(markup).not.toContain('Create on canvas');
    expect(markup).not.toContain('Score');
    expect(markup).not.toContain('<h4>Generation</h4>');
    expect(markup).not.toContain('<h4>Background</h4>');
    expect(markup).not.toContain('<h4>Assets</h4>');
    expect(markup).not.toContain('Foreground object');
  });
});
