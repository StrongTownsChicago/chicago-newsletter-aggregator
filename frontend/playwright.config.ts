import { defineConfig, devices } from '@playwright/test';
import { readLocalSupabaseEnv } from './e2e/support/local-supabase-env';
import { E2E_UNSUBSCRIBE_SECRET_KEY } from './e2e/support/unsubscribe-token';

/**
 * The end-to-end specs (`npm run test:e2e`), run against the local Supabase
 * stack reset to supabase/seed.sql (e2e/support/global-setup.ts).
 *
 * The Supabase URL and keys come from `supabase status` and pass the
 * local-only guard before the dev server gets them; values set here take
 * precedence over frontend/.env, which points at production, and the global
 * setup proves the server uses them. The server always starts on its own
 * port, never reusing one.
 */
const PORT = 4358;
const BASE_URL = `http://127.0.0.1:${PORT}`;

const supabase = readLocalSupabaseEnv();

export default defineConfig({
  testDir: './e2e',
  globalSetup: './e2e/support/global-setup.ts',
  forbidOnly: !!process.env.CI,
  retries: process.env.CI ? 2 : 0,
  workers: process.env.CI ? 2 : undefined,
  reporter: process.env.CI ? 'list' : [['list'], ['html', { open: 'never' }]],
  use: {
    baseURL: BASE_URL,
    trace: 'on-first-retry',
  },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'] } }],
  webServer: {
    command: `npx astro dev --port ${PORT} --host 127.0.0.1`,
    url: `${BASE_URL}/login`,
    reuseExistingServer: false,
    timeout: 120 * 1000,
    env: {
      PUBLIC_SUPABASE_URL: supabase.apiUrl,
      PUBLIC_SUPABASE_ANON_KEY: supabase.anonKey,
      SUPABASE_SERVICE_KEY: supabase.serviceRoleKey,
      PUBLIC_ENABLE_NOTIFICATIONS: 'true',
      UNSUBSCRIBE_SECRET_KEY: E2E_UNSUBSCRIBE_SECRET_KEY,
      // Otherwise the Cloudflare adapter's dev runtime loads frontend/.env into
      // locals.runtime.env, whose secrets win over these (lib/server/server-env.ts).
      CLOUDFLARE_LOAD_DEV_VARS_FROM_DOT_ENV: 'false',
    },
  },
});
