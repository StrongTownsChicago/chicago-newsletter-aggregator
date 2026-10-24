// For specs that must not leave the dev server: every browser request to another
// origin is aborted and recorded, and the analytics data files are served from
// e2e/fixtures/analytics/ instead of public/analytics-data/. Server-side
// database reads go to the local stack and aren't seen here.
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { test, expect, type Page } from '@playwright/test';

const ANALYTICS_FIXTURE_DIRECTORY = path.join(path.dirname(fileURLToPath(import.meta.url)), 'fixtures', 'analytics');

async function serveFixtures(page: Page, baseURL: string, externalRequests: string[]): Promise<void> {
  const origin = new URL(baseURL).origin;
  await page.route(
    (url) => url.origin !== origin,
    (route) => {
      externalRequests.push(route.request().url());
      return route.abort();
    },
  );
  await page.route('**/analytics-data/*.json', (route) => {
    const fileName = path.basename(new URL(route.request().url()).pathname);
    return route.fulfill({ path: path.join(ANALYTICS_FIXTURE_DIRECTORY, fileName), contentType: 'application/json' });
  });
}

/** Registers hooks that keep each test in the calling spec offline and on fixture data. */
export function useOfflineFixtures(): void {
  let externalRequests: string[] = [];

  test.beforeEach(async ({ page, baseURL }) => {
    externalRequests = [];
    await serveFixtures(page, baseURL ?? '', externalRequests);
  });

  test.afterEach(() => {
    expect(externalRequests, 'requests that left the dev server').toEqual([]);
  });
}
