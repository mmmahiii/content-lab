// Reproducible, local illustration source footage. Not the output of an edited composition.
import { chromium } from '@playwright/test';
import { readFile } from 'node:fs/promises';
import { resolve } from 'node:path';
const browser = await chromium.launch({ channel: 'chrome', headless: true });
try {
  const page = await browser.newPage({ viewport: { width: 540, height: 960 } });
  const svg = await readFile(resolve('public/demo/kitchen.svg'), 'utf8');
  await page.setContent(
    `<style>html,body{margin:0;width:540px;height:960px}svg{width:100%;height:100%;display:block}</style>${svg}`,
  );
  await page.screenshot({ path: resolve('public/demo/kitchen-source.png') });
} finally {
  await browser.close();
}
