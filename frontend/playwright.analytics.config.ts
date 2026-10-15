import { defineConfig, devices } from '@playwright/test';

/**
 * The /analytics end-to-end spec on fixture data (`npm run test:e2e:analytics`).
 *
 * It always starts its own dev server on a dedicated port, never reusing one,
 * with placeholder Supabase settings that take precedence over any .env file,
 * so nothing it runs can reach the production database. The spec also serves
 * fixture data in place of public/analytics-data/ and aborts any request that
 * leaves the dev server.
 */
const PORT = 4358;
const BASE_URL = `http://127.0.0.1:${PORT}`;

export default defineConfig({
  testDir: './e2e',
  testMatch: 'analytics-dashboard.spec.ts',
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  reporter: 'list',
  use: {
    baseURL: BASE_URL,
    trace: 'on-first-retry',
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
  webServer: {
    command: `npx astro dev --port ${PORT} --host 127.0.0.1`,
    url: `${BASE_URL}/analytics`,
    reuseExistingServer: false,
    timeout: 120 * 1000,
    env: {
      PUBLIC_SUPABASE_URL: 'http://127.0.0.1:9',
      PUBLIC_SUPABASE_ANON_KEY: 'placeholder-anon-key',
      PUBLIC_ENABLE_NOTIFICATIONS: 'false',
      SUPABASE_SERVICE_KEY: 'placeholder-service-key',
    },
  },
});
