import { defineConfig } from '@playwright/test';

export default defineConfig({
  testDir: './e2e',
  timeout: 45000,
  expect: { timeout: 10000 },
  fullyParallel: false,
  workers: 1,
  reporter: 'list',
  outputDir: '../../outputs/prototype/test-results',
  use: {
    actionTimeout: 10000,
    baseURL: 'http://127.0.0.1:3000',
    channel: process.env.PROTOTYPE_BROWSER_CHANNEL ?? 'chrome',
    viewport: { width: 1440, height: 1080 },
    screenshot: 'only-on-failure',
    trace: 'retain-on-failure',
  },
});
