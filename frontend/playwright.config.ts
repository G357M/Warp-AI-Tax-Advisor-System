import { defineConfig } from '@playwright/test';

const isCI = Boolean(process.env.CI);

export default defineConfig({
  testDir: './e2e',
  testMatch: 'visual.spec.ts',
  fullyParallel: false,
  workers: 1,
  forbidOnly: isCI,
  retries: isCI ? 1 : 0,
  timeout: 45_000,
  expect: {
    timeout: 10_000,
    toHaveScreenshot: {
      animations: 'disabled',
      caret: 'hide',
      maxDiffPixelRatio: 0.001,
      threshold: 0.2,
    },
  },
  reporter: isCI
    ? [['line'], ['html', { open: 'never', outputFolder: 'playwright-report' }]]
    : [['line']],
  outputDir: 'test-results',
  snapshotPathTemplate: '{testDir}/__screenshots__/{arg}{ext}',
  use: {
    baseURL: 'http://127.0.0.1:3100',
    colorScheme: 'dark',
    contextOptions: { reducedMotion: 'reduce' },
    deviceScaleFactor: 1,
    locale: 'en-US',
    serviceWorkers: 'block',
    timezoneId: 'UTC',
    trace: 'retain-on-failure',
  },
  projects: [
    {
      name: 'chromium',
      use: { browserName: 'chromium' },
    },
  ],
  webServer: {
    command: 'npm run start -- --hostname 0.0.0.0 --port 3100',
    url: 'http://127.0.0.1:3100',
    reuseExistingServer: !isCI,
    timeout: 120_000,
    stdout: 'pipe',
    stderr: 'pipe',
  },
});
