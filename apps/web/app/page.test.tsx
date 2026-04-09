import type { ReactElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';

import HomePage from './page';
import { demoIds } from './_lib/content-lab-data';
import PackageDetailPage from './orgs/[orgId]/packages/[runId]/page';
import PageDetailPage from './orgs/[orgId]/pages/[pageId]/page';
import ReelDetailPage from './orgs/[orgId]/pages/[pageId]/reels/[reelId]/page';
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

    expect(markup).toContain('Workspace summary');
    expect(markup).toContain('Operational runs');
    expect(markup).toContain(`/orgs/${demoIds.orgId}/pages/${demoIds.pageId}`);
  });

  it('renders the page detail view with policy summary and recent reels', async () => {
    const markup = await renderRoute(
      PageDetailPage({
        params: {
          orgId: demoIds.orgId,
          pageId: demoIds.pageId,
        },
      }),
    );

    expect(markup).toContain('Policy summary');
    expect(markup).toContain('Recent reels');
    expect(markup).toContain('Operator diary A');
  });

  it('renders the reel detail view with lifecycle and package artifacts', async () => {
    const markup = await renderRoute(
      ReelDetailPage({
        params: {
          orgId: demoIds.orgId,
          pageId: demoIds.pageId,
          reelId: demoIds.reelId,
        },
      }),
    );

    expect(markup).toContain('Lifecycle timeline');
    expect(markup).toContain('Package artifacts');
    expect(markup).toContain('Download final_video');
  });

  it('renders the run detail view with task summaries', async () => {
    const markup = await renderRoute(
      RunDetailPage({
        params: {
          orgId: demoIds.orgId,
          runId: demoIds.runId,
        },
      }),
    );

    expect(markup).toContain('Task summaries');
    expect(markup).toContain('qa_review');
    expect(markup).toContain('Run payloads');
  });

  it('renders the package detail view with provenance and downloads', async () => {
    const markup = await renderRoute(
      PackageDetailPage({
        params: {
          orgId: demoIds.orgId,
          runId: demoIds.runId,
        },
      }),
    );

    expect(markup).toContain('Provenance');
    expect(markup).toContain('Download manifest');
    expect(markup).toContain('Downloadable artifacts');
  });
});
