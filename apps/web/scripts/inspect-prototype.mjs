import { chromium } from '@playwright/test';
import { mkdir, writeFile } from 'node:fs/promises';
import { resolve } from 'node:path';
const output = resolve('../../outputs/prototype');
await mkdir(output, { recursive: true });
const browser = await chromium.launch({ channel: 'chrome', headless: true });
const errors = [];
try {
  const page = await browser.newPage({ viewport: { width: 1440, height: 1080 } });
  page.on('pageerror', (error) => errors.push(error.message));
  const requests = [];
  page.on('request', (request) => {
    if (request.url().includes('/api/') || !request.url().startsWith('http://127.0.0.1:3000'))
      requests.push(request.url());
  });
  await page.goto('http://127.0.0.1:3000', { waitUntil: 'networkidle', timeout: 60000 });
  await page.locator('.content-card').first().waitFor();
  for (const [name, hash] of [
    ['content', 'content'],
    ['pages', 'pages'],
    ['ideas', 'ideas'],
    ['editor', 'content/content-mug/edit'],
    ['assets', 'assets'],
    ['packs', 'packs'],
    ['review', 'review'],
    ['publication', 'publication'],
    ['operations', 'operations'],
    ['learning', 'learning'],
  ]) {
    await page.goto(`http://127.0.0.1:3000/#${hash}`);
    await page.waitForTimeout(450);
    await page.evaluate(() => window.scrollTo(0, 0));
    if (name === 'editor')
      await page.locator('.editor-root').screenshot({ path: resolve(output, `${name}.png`) });
    else await page.screenshot({ path: resolve(output, `${name}.png`), fullPage: true });
    await writeFile(resolve(output, `${name}.txt`), await page.locator('body').innerText());
  }
  await page.goto('http://127.0.0.1:3000/#operations/run-content-failed');
  await page.getByRole('button', { name: 'Retry execution · simulated', exact: true }).waitFor();
  await page.screenshot({ path: resolve(output, 'failed-execution.png'), fullPage: true });
  await page.goto('http://127.0.0.1:3000/#content/content-blocked/brief');
  await page.getByRole('button', { name: 'Create preview', exact: true }).click();
  await page.getByRole('alert').filter({ hasText: 'Action blocked' }).waitFor();
  await page.screenshot({ path: resolve(output, 'blocked-preview.png'), fullPage: true });
  await page.getByRole('button', { name: 'Open demo controls', exact: true }).click();
  await page.getByLabel('Preview role').selectOption('viewer');
  await page.goto('http://127.0.0.1:3000/#content/content-mug/edit');
  await page.getByRole('region', { name: 'Scene and timeline editor' }).waitFor();
  await page.screenshot({ path: resolve(output, 'read-only-editor.png'), fullPage: true });
  await page.getByLabel('Preview role').selectOption('owner');
  await page.getByRole('button', { name: 'Open demo controls', exact: true }).click();
  await page.setViewportSize({ width: 390, height: 844 });
  const dismiss = page.getByRole('button', { name: 'Dismiss notification', exact: true });
  if (await dismiss.isVisible()) await dismiss.click();
  await page.goto('http://127.0.0.1:3000/#review');
  await page.waitForTimeout(400);
  await page.screenshot({ path: resolve(output, 'mobile-review.png'), fullPage: true });
  const result = { errors, unexpectedRequests: requests, output };
  await writeFile(resolve(output, 'inspection.json'), JSON.stringify(result, null, 2));
  console.log(JSON.stringify(result, null, 2));
  if (errors.length || requests.length) process.exitCode = 1;
} finally {
  await browser.close();
}
