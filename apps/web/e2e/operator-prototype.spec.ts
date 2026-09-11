import { expect, test, type Page } from '@playwright/test';
import type { WorkspaceState } from '../app/prototype/domain';

const key = 'content-laboratory.operator-prototype.v1';
const unexpectedTraffic = new WeakMap<Page, string[]>();
test.beforeEach(async ({ page }) => {
  const requests: string[] = [];
  unexpectedTraffic.set(page, requests);
  page.on('request', request => {
    const url = new URL(request.url());
    if (url.pathname.startsWith('/api/') || url.origin !== 'http://127.0.0.1:3000') requests.push(request.url());
  });
});
test.afterEach(async ({ page }) => {
  expect(unexpectedTraffic.get(page), 'Each journey must use local static media and mock services only').toEqual([]);
});
async function state(page: Page): Promise<WorkspaceState> {
  return page.evaluate((storageKey) => JSON.parse(localStorage.getItem(storageKey)!).state, key);
}
async function open(page: Page, hash = 'content') {
  await page.goto(`/#${hash}`);
  await expect(page.getByText('Prototype · simulated services', { exact: true })).toBeVisible();
  await expect.poll(async () => page.evaluate((k) => !!localStorage.getItem(k), key)).toBeTruthy();
}
async function dismiss(page: Page) {
  const button = page.getByRole('button', { name: 'Dismiss notification', exact: true });
  if (await button.isVisible()) await button.click();
}
test('all principal workspaces render locally without backend or provider traffic', async ({
  page,
}) => {
  const errors: string[] = [];
  const forbidden: string[] = [];
  page.on('pageerror', (error) => errors.push(error.message));
  page.on('request', (request) => {
    if (request.url().includes('/api/') || !request.url().startsWith('http://127.0.0.1:3000'))
      forbidden.push(request.url());
  });
  await open(page);
  await expect(page.locator('.content-card')).toHaveCount(8);
  for (const [hash, heading] of [
    ['pages', 'Pages'],
    ['ideas', 'Ideas'],
    ['assets', 'Asset Registry'],
    ['packs', 'Asset packs'],
    ['review', 'Review'],
    ['publication', 'Publication'],
    ['operations', 'Operations'],
    ['learning', 'Learning'],
  ]) {
    await page.goto(`/#${hash}`);
    await expect(page.getByRole('heading', { name: heading, level: 1, exact: true })).toBeVisible();
    await expect(
      page.locator('.empty-state').filter({ hasText: 'workspace is unavailable' }),
    ).toHaveCount(0);
  }
  expect(errors).toEqual([]);
  expect(forbidden).toEqual([]);
});

test('asset-based content becomes an exact approved handoff and simulated post', async ({
  page,
}) => {
  await open(page, 'assets');
  for (const name of ['Warm white ceramic mug', 'Warm studio surface', 'Quiet studio tone']) {
    await page.getByRole('checkbox', { name: `Select ${name} for content`, exact: true }).check();
  }
  await page.getByRole('button', { name: 'Create from selected assets', exact: true }).click();
  await expect(page.getByRole('navigation', { name: 'Content workflow' })).toBeVisible();
  const contentId = (await page.evaluate(() => location.hash)).split('/')[1];
  await page
    .getByRole('textbox', { name: 'Publication copy', exact: true })
    .fill('One quiet ritual. A little space for yourself.');
  await page.getByRole('button', { name: 'Create preview', exact: true }).click();
  await expect
    .poll(
      async () =>
        (await state(page)).revisions.filter((r) => r.contentId === contentId && r.previewCreated)
          .length,
    )
    .toBe(1);
  await page.goto(`/#content/${contentId}/run`);
  await page
    .getByRole('button', { name: 'Render saved revision · simulated', exact: true })
    .click();
  await expect
    .poll(async () => (await state(page)).packages.some((p) => p.contentId === contentId))
    .toBe(true);
  await page.goto(`/#content/${contentId}/review`);
  await dismiss(page);
  await page.getByRole('button', { name: 'Approve package', exact: true }).click();
  await expect
    .poll(async () => (await state(page)).packages.find((p) => p.contentId === contentId)?.status)
    .toBe('approved');
  await page.goto(`/#content/${contentId}/publish`);
  const download = page.waitForEvent('download');
  await page.getByRole('button', { name: 'Download prototype handoff', exact: true }).click();
  expect((await download).suggestedFilename()).toMatch(/^prototype-handoff-.*\.json$/);
  await page.getByRole('button', { name: 'Prepare manual handoff', exact: true }).click();
  await expect
    .poll(
      async () => (await state(page)).publications.filter((p) => p.contentId === contentId).length,
    )
    .toBe(1);
  await dismiss(page);
  await page.getByRole('button', { name: 'Record manual post · simulated', exact: true }).click();
  await page.getByLabel('External post reference · example').fill('demo:journey-001');
  await page.getByLabel('Actual post timestamp · simulation').fill('2026-09-09T12:00');
  await page.getByRole('button', { name: 'Confirm simulated post', exact: true }).click();
  await expect
    .poll(
      async () => (await state(page)).publications.find((p) => p.contentId === contentId)?.status,
    )
    .toBe('published');
  const after = await state(page);
  const publication = after.publications.find((p) => p.contentId === contentId)!;
  expect(publication.simulated).toBe(true);
  expect(after.metrics.find((m) => m.publicationId === publication.id)?.views).toBeNull();
  await page.reload();
  await expect(
    page.getByText('Recorded simulated external reference: demo:journey-001', { exact: false }),
  ).toBeVisible();
  await page.getByRole('button', { name: 'View observations', exact: true }).click();
  await expect(page.getByRole('row').filter({ hasText: 'Simulated post recorded' })).toContainText(
    'Unavailable',
  );
});

test('editor changes visible objects, caption timing and scene order without changing saved history', async ({
  page,
}) => {
  await open(page, 'content/content-mug/edit');
  const editor = page.getByRole('region', { name: 'Scene and timeline editor' });
  await editor.getByRole('button', { name: 'Save revision', exact: true }).click();
  await expect
    .poll(
      async () => (await state(page)).revisions.filter((r) => r.contentId === 'content-mug').length,
    )
    .toBe(1);
  const before = (await state(page)).revisions.find((r) => r.contentId === 'content-mug')!;
  await editor.getByRole('button', { name: 'Select Ceramic mug', exact: true }).click();
  await page.getByLabel('X position', { exact: false }).fill('20');
  await expect(editor.locator('.composition-movable[aria-label="Select Ceramic mug"]')).toHaveAttribute('style', /left: 20%;/);
  await expect
    .poll(
      async () =>
        (await state(page)).contents
          .find((c) => c.id === 'content-mug')!
          .draft.scenes[0].instances.find((i) => i.name === 'Ceramic mug')!.x,
    )
    .toBe(0.2);
  await page.getByRole('button', { name: 'Replace object', exact: false }).click();
  const dialog = page.getByRole('dialog');
  await dialog.getByLabel('Ready, eligible replacement').selectOption('rep-coral');
  await expect(
    dialog.getByText('Simulated review · visual identity not evaluated', { exact: true }),
  ).toBeVisible();
  await dialog.getByRole('button', { name: 'Apply to draft', exact: true }).click();
  await expect
    .poll(
      async () =>
        (await state(page)).contents
          .find((c) => c.id === 'content-mug')!
          .draft.scenes[0].instances.find((i) => i.id.endsWith('-subject'))!.representationId,
    )
    .toBe('rep-coral');
  await editor.getByRole('button', { name: 'Select Headline', exact: true }).click();
  await page.getByLabel('Exact on-screen text').fill('A different morning.');
  await expect(editor.locator('.editor-canvas-area .composition-text')).toContainText(
    'A different morning.',
  );
  await page.getByRole('button', { name: 'Show scene settings' }).click();
  await page.getByLabel('Scene duration', { exact: false }).fill('180');
  await expect
    .poll(
      async () =>
        (await state(page)).contents.find((c) => c.id === 'content-mug')!.draft.totalFrames,
    )
    .toBe(660);
  await page.getByRole('button', { name: /Move later/ }).click();
  await expect
    .poll(
      async () =>
        (await state(page)).contents.find((c) => c.id === 'content-mug')!.draft.scenes[0].name,
    )
    .toBe('Development');
  expect((await state(page)).revisions.find((r) => r.id === before.id)).toEqual(before);
  await page.reload();
  await expect(page.getByLabel('Current frame')).toBeVisible();
  await editor.getByRole('button', { name: /Create preview/ }).click();
  await page
    .getByRole('navigation', { name: 'Content workflow' })
    .getByRole('button', { name: /Execution/ })
    .click();
  await page
    .getByRole('button', { name: 'Render saved revision · simulated', exact: true })
    .click();
  await expect
    .poll(async () => (await state(page)).packages.some((p) => p.contentId === 'content-mug'))
    .toBe(true);
  await page.goto('/#content/content-mug/review');
  await page.getByRole('button', { name: 'Compare with parent', exact: true }).click();
  await expect(page.getByText(`PARENT · REVISION ${before.number}`, { exact: true })).toBeVisible();
  expect((await state(page)).revisions.find((r) => r.id === before.id)).toEqual(before);
});

test('pack scope requires authorisation and supports partial fulfilment recovery', async ({
  page,
}) => {
  await open(page, 'packs');
  await page.getByLabel('Pack name', { exact: true }).fill('A focused starter pack');
  await page.getByLabel('Page', { exact: true }).selectOption('page-objects');
  await page.getByLabel('Requested asset count').fill('4');
  await page.getByLabel('Asset mix', { exact: true }).fill('2 product, 1 environment, 1 music');
  await page.getByLabel('Visual style and purpose').fill('Warm, tactile product studies');
  await page.getByRole('button', { name: 'Plan pack · no acquisition yet', exact: true }).click();
  await expect
    .poll(
      async () =>
        (await state(page)).packs.find((p) => p.name === 'A focused starter pack')?.status,
    )
    .toBe('planned');
  await dismiss(page);
  await page.getByRole('button', { name: /Authorise acquisition ·/ }).click();
  await expect
    .poll(
      async () =>
        (await state(page)).packs.find((p) => p.name === 'A focused starter pack')?.status,
    )
    .toBe('authorised');
  await page.getByRole('button', { name: 'Fulfil authorised pack', exact: true }).click();
  await expect
    .poll(async () =>
      ['partial', 'ready'].includes(
        (await state(page)).packs.find((p) => p.name === 'A focused starter pack')?.status ?? '',
      ),
    )
    .toBe(true);
  await page.getByRole('button', { name: /Create from \d+ ready assets/ }).click();
  await expect(page.getByRole('navigation', { name: 'Content workflow' })).toBeVisible();
});

test('execution failures offer retry while unknown outcomes require reconciliation', async ({
  page,
}) => {
  await open(page, 'operations/run-unknown');
  await expect(
    page.getByRole('button', { name: 'Retry execution · simulated', exact: true }),
  ).toHaveCount(0);
  await page.getByRole('button', { name: 'Reconcile outcome · simulated', exact: true }).click();
  await expect
    .poll(async () => (await state(page)).runs.find((r) => r.id === 'run-unknown')?.status)
    .toBe('succeeded');
  await page.goto('/#operations/run-content-failed');
  await page.getByRole('button', { name: 'Retry execution · simulated', exact: true }).click();
  await expect
    .poll(
      async () =>
        (await state(page)).runs.find((r) => r.contentId === 'content-failed' && r.attempt === 2)
          ?.status,
    )
    .toBe('succeeded');
  expect((await state(page)).runs.find((r) => r.id === 'run-content-failed')?.status).toBe(
    'failed',
  );
  await expect(page.getByText('Attempt 2', { exact: false })).toBeVisible();
  await page.getByRole('button', { name: 'Review this output', exact: true }).click();
  await expect(page.getByRole('button', { name: 'Approve package', exact: true })).toBeVisible();
});

test('role limits, loading, outage, empty state and corrupt storage have usable recovery', async ({
  page,
}) => {
  await open(page);
  await page.getByRole('button', { name: 'Open demo controls', exact: true }).click();
  await page.getByLabel('Preview role').selectOption('viewer');
  await expect(page.getByRole('button', { name: 'New content', exact: true })).toBeDisabled();
  await page.goto('/#content/content-mug/edit');
  await expect(
    page
      .getByRole('region', { name: 'Scene and timeline editor' })
      .getByRole('button', { name: 'Save revision', exact: true }),
  ).toBeDisabled();
  await page.getByLabel('Service scenario').selectOption('unavailable');
  await expect(page.getByRole('heading', { name: 'The workspace is unavailable' })).toBeVisible();
  await page.getByRole('button', { name: 'Reconnect simulated service' }).click();
  await page.getByLabel('Service scenario').selectOption('loading');
  await expect(page.getByRole('status', { name: 'Loading workspace' })).toBeVisible();
  await page.getByRole('button', { name: 'Load working portfolio' }).click();
  await page.goto('/#content');
  await page.getByLabel('Service scenario').selectOption('empty');
  await expect(page.getByRole('heading', { name: 'A fresh page. A first idea.' })).toBeVisible();
  await page.evaluate((k) => localStorage.setItem(k, '{broken-json'), key);
  await page.reload();
  await expect(
    page.getByText('Saved prototype data could not be read.', { exact: false }),
  ).toBeVisible();
  await expect(page.locator('.content-card')).toHaveCount(8);
});

test('narrow review has no document overflow and keyboard navigation reaches actions', async ({
  page,
}) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await open(page, 'review');
  await expect(page.getByRole('link', { name: 'Asset Registry', exact: true })).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(
    true,
  );
  await page.keyboard.press('Tab');
  await expect(page.getByRole('link', { name: 'Skip to workspace' })).toBeFocused();
  await page.keyboard.press('Enter');
  await expect(page.locator('#main-workspace')).toBeFocused();
  await expect(page.getByRole('button', { name: 'Approve package' })).toBeVisible();
});

test('immediate draft-to-editor navigation preserves edits and changed revisions block old publication', async ({
  page,
}) => {
  await open(page, 'content/content-approved/brief');
  const before = await state(page);
  const approved = before.packages.find((p) => p.contentId === 'content-approved')!;
  await page
    .getByRole('textbox', { name: 'Publication copy', exact: true })
    .fill('This changed copy requires a fresh approval.');
  await page
    .getByRole('navigation', { name: 'Content workflow' })
    .getByRole('button', { name: /Scene editor/ })
    .click();
  const editor = page.getByRole('region', { name: 'Scene and timeline editor' });
  await editor.getByRole('button', { name: 'Select Headline', exact: true }).click();
  await page.getByLabel('Exact on-screen text').fill('A freshly edited thought.');
  await editor.getByRole('button', { name: 'Save revision', exact: true }).click();
  await expect
    .poll(
      async () =>
        (await state(page)).contents.find((c) => c.id === approved.contentId)?.currentRevisionId,
    )
    .not.toBe(approved.revisionId);
  const after = await state(page);
  const saved = after.revisions.find(
    (r) => r.id === after.contents.find((c) => c.id === approved.contentId)?.currentRevisionId,
  )!;
  expect(saved.composition.caption).toBe('This changed copy requires a fresh approval.');
  expect(saved.composition.scenes[0].instances.find((i) => i.name === 'Headline')?.text).toBe(
    'A freshly edited thought.',
  );
  expect(after.revisions.find((r) => r.id === approved.revisionId)).toEqual(
    before.revisions.find((r) => r.id === approved.revisionId),
  );
  await page.goto('/#content/content-approved/publish');
  await page.getByRole('button', { name: 'Prepare manual handoff', exact: true }).click();
  await expect(page.getByRole('alert').filter({ hasText: 'Action blocked' })).toContainText(
    'earlier content revision',
  );
});

test('operators can capture an original idea and carry its evidence into a brief', async ({
  page,
}) => {
  await open(page, 'ideas');
  await page.getByRole('button', { name: 'New idea', exact: true }).click();
  await page.getByLabel('Idea title', { exact: true }).fill('The first quiet minute');
  await page
    .getByLabel('Premise', { exact: true })
    .fill('An object story about making time for a morning ritual.');
  await page
    .getByLabel('Evidence and source note', { exact: true })
    .fill('Creative hypothesis for the pilot; no audience outcome is claimed.');
  await page
    .getByLabel('Why this page', { exact: true })
    .fill('Everyday rituals and thoughtful objects fit the brand.');
  await page.getByRole('button', { name: 'Save idea', exact: true }).click();
  const ideaCard = page
    .locator('article')
    .filter({ has: page.getByRole('heading', { name: 'The first quiet minute', exact: true }) });
  await ideaCard.getByRole('button', { name: 'Create brief', exact: true }).click();
  await expect(
    page.getByRole('heading', { name: 'The first quiet minute', exact: true }),
  ).toBeVisible();
  await expect(
    page.getByRole('textbox', { name: 'Evidence and source notes', exact: true }),
  ).toHaveValue('Creative hypothesis for the pilot; no audience outcome is claimed.');
});

test('mandatory ingredients and unsupported source intervals expose recoverable validation', async ({
  page,
}) => {
  await open(page, 'content/content-mug/assets');
  const coral = page.locator('.ingredient-row').filter({ hasText: 'Coral ceramic mug' });
  await coral.getByRole('checkbox', { name: 'Selected', exact: true }).check();
  await coral.getByRole('checkbox', { name: 'Mandatory', exact: true }).check();
  await page.getByRole('button', { name: 'Create preview', exact: true }).click();
  await expect(page.getByRole('alert').filter({ hasText: 'Action blocked' })).toContainText(
    'mandatory',
  );
  await page.goto('/#content/content-recipe/edit');
  const editor = page.getByRole('region', { name: 'Scene and timeline editor' });
  await editor.getByRole('button', { name: 'Select Source footage', exact: true }).click();
  await page.getByLabel('Source in frame').fill('350');
  await expect(
    page.getByText('Source footage is too short for this interval.', { exact: false }),
  ).toBeVisible();
  await editor.getByRole('button', { name: /Create preview/ }).click();
  await expect(page.getByRole('alert').filter({ hasText: 'Action blocked' })).toContainText(
    /source/i,
  );
  await page.getByLabel('Source in frame').fill('0');
  await editor.getByRole('button', { name: /Create preview/ }).click();
  await expect
    .poll(
      async () =>
        (await state(page)).contents
          .find((c) => c.id === 'content-recipe')
          ?.draft.scenes[0].instances.find((i) => i.name === 'Source footage')?.sourceInFrame,
    )
    .toBe(0);
});
