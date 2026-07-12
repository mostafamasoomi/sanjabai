import { defineConfig, devices } from '@playwright/test'

/**
 * Playwright config for the Multiai frontend (Next.js 14 App Router).
 *
 * - baseURL is the dev/standalone server on :3003.
 * - webServer starts `next dev` on :3003 ONLY when no server is already
 *   listening there (reuseExistingServer). When the Docker frontend
 *   container is up it is reused; otherwise a local dev server is spawned.
 * - Two projects: a mobile viewport (iPhone 12, 390px) and a desktop
 *   viewport (1440px) so RTL/mobile behaviour is exercised.
 *
 * Backend-dependent endpoints (/api/*) are mocked inside the specs via
 * page.route, so the suite is deterministic and does not need the API.
 */
export default defineConfig({
  testDir: './tests',
  timeout: 60_000,
  expect: { timeout: 15_000 },
  fullyParallel: true,
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: 1, // single worker keeps the shared dev-server stable
  reporter: [['list']],
  use: {
    baseURL: 'http://localhost:3003',
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
    locale: 'fa-IR',
  },
  projects: [
    {
      name: 'mobile',
      // Force chromium even though the iPhone descriptor defaults to webkit.
      use: { ...devices['iPhone 12'], browserName: 'chromium' },
    },
    {
      name: 'desktop',
      use: {
        ...devices['Desktop Chrome'],
        viewport: { width: 1440, height: 900 },
      },
    },
  ],
  webServer: {
    command: 'npx next dev -p 3003',
    url: 'http://localhost:3003',
    reuseExistingServer: true,
    timeout: 240_000,
    stdout: 'ignore',
    stderr: 'pipe',
  },
})
