import type { ReactElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';

import HomePage from './page';
import { demoIds } from './_lib/content-lab-data';
import PackageDetailPage from './orgs/[orgId]/packages/[runId]/page';
import PageDetailPage from './orgs/[orgId]/pages/[pageId]/page';
import PagePolicyPage from './orgs/[orgId]/pages/[pageId]/policy/page';
import PageReelsPage from './orgs/[orgId]/pages/[pageId]/reels/page';
import ReelDetailPage from './orgs/[orgId]/pages/[pageId]/reels/[reelId]/page';
import PageRunsPage from './orgs/[orgId]/pages/[pageId]/runs/page';
import RunDetailPage from './orgs/[orgId]/runs/[runId]/page';

async function renderRoute(
  node: Promise<ReactElement | null> | ReactElement | null,
): Promise<string> {
  const resolved = await node;
  if (resolved === null) {
    throw new Error('Route rendered null');
  }
  return renderToStaticMarkup(resolved);
}

describe('operator detail routes', () => {
  it('renders the home page with org-safe entry points', async () => {
    const markup = await renderRoute(HomePage());

    expect(markup).toContain('A guided operator workspace for Content Lab');
    expect(markup).toContain('Start here today');
    expect(markup).toContain('Workspace map');
    expect(markup).toContain(`/orgs/${demoIds.orgId}/pages/${demoIds.pageId}`);
  });

  it('renders the page overview with page-scoped sections', async () => {
    const markup = await renderRoute(
      PageDetailPage({
        params: Promise.resolve({
          orgId: demoIds.orgId,
          pageId: demoIds.pageId,
        }),
      }),
    );

    expect(markup).toContain('Page workspace');
    expect(markup).toContain('Continue from this page');
    expect(markup).toContain('Operator diary A');
  });

  it('renders the page reels tab with page-scoped actions', async () => {
    const markup = await renderRoute(
      PageReelsPage({
        params: Promise.resolve({
          orgId: demoIds.orgId,
          pageId: demoIds.pageId,
        }),
      }),
    );

    expect(markup).toContain('Page reels');
    expect(markup).toContain('Open reel detail');
    expect(markup).toContain('Open in Actions');
  });

  it('renders the page runs tab with page-scoped actions', async () => {
    const markup = await renderRoute(
      PageRunsPage({
        params: Promise.resolve({
          orgId: demoIds.orgId,
          pageId: demoIds.pageId,
        }),
      }),
    );

    expect(markup).toContain('Page runs');
    expect(markup).toContain('Open run detail');
    expect(markup).toContain('Open package');
  });

  it('renders the page policy tab inside the page workspace', async () => {
    const markup = await renderRoute(
      PagePolicyPage({
        params: Promise.resolve({
          orgId: demoIds.orgId,
          pageId: demoIds.pageId,
        }),
      }),
    );

    expect(markup).toContain('Page policy editor');
    expect(markup).toContain('Save policy');
    expect(markup).not.toContain('<select');
  });

  it('renders the reel detail view with lifecycle and package artifacts', async () => {
    const markup = await renderRoute(
      ReelDetailPage({
        params: Promise.resolve({
          orgId: demoIds.orgId,
          pageId: demoIds.pageId,
          reelId: demoIds.reelId,
        }),
      }),
    );

    expect(markup).toContain('Lifecycle timeline');
    expect(markup).toContain('Package artifacts');
    expect(markup).toContain('Back to page reels');
    expect(markup).toContain('Download final_video');
  });

  it('renders the run detail view with task summaries', async () => {
    const markup = await renderRoute(
      RunDetailPage({
        params: Promise.resolve({
          orgId: demoIds.orgId,
          runId: demoIds.runId,
        }),
      }),
    );

    expect(markup).toContain('Task summaries');
    expect(markup).toContain('qa_review');
    expect(markup).toContain('Back to page runs');
    expect(markup).toContain('Run payloads');
  });

  it('renders the package detail view with provenance and downloads', async () => {
    const markup = await renderRoute(
      PackageDetailPage({
        params: Promise.resolve({
          orgId: demoIds.orgId,
          runId: demoIds.runId,
        }),
      }),
    );

    expect(markup).toContain('Provenance');
    expect(markup).toContain('Download manifest');
    expect(markup).toContain('Back to page runs');
    expect(markup).toContain('Downloadable artifacts');
  });
});
