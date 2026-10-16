// /analytics on small committed fixture data.
// Run with `npm run test:e2e:analytics` (playwright.analytics.config.ts), which
// starts its own dev server with placeholder Supabase settings. The analytics
// pages never query Supabase; as a guard, every request that leaves the dev
// server is aborted and fails the test, and every data file is served from
// e2e/fixtures/analytics/ instead of public/analytics-data/.
import { readFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { test, expect, type Page } from '@playwright/test';

const FIXTURE_DIRECTORY = path.join(path.dirname(fileURLToPath(import.meta.url)), 'fixtures', 'analytics');
const PNG_SIGNATURE = Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]);
/** Newsletters in the fixture's default window (Feb–Apr 2026): ward 1 sends 3 a month, wards 2 and 3 send 2. */
const DEFAULT_WINDOW_NEWSLETTERS = 21;

let externalRequests: string[] = [];

async function serveFixtures(page: Page, baseURL: string): Promise<void> {
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
    return route.fulfill({ path: path.join(FIXTURE_DIRECTORY, fileName), contentType: 'application/json' });
  });
}

async function openDashboard(page: Page, query = ''): Promise<void> {
  await page.goto(`/analytics${query}`);
  await expect(page.locator('#analytics-dashboard')).toBeVisible();
}

test.beforeEach(async ({ page, baseURL }) => {
  externalRequests = [];
  await serveFixtures(page, baseURL ?? '');
});

test.afterEach(() => {
  expect(externalRequests, 'requests that left the dev server').toEqual([]);
});

test('loads the dashboard from the fixture data', async ({ page }) => {
  await openDashboard(page);
  await expect(page.locator('h1')).toHaveText('Newsletter Analytics');
  await expect(page.locator('#analytics-data-as-of')).toContainText('from 26 newsletters');
  await expect(page.locator('#summary-tiles [data-tile-value]').first()).toHaveText(String(DEFAULT_WINDOW_NEWSLETTERS));
  await expect(page.locator('#civic-calendar svg').first()).toBeVisible();
  await expect(page.locator('#topic-trends button[data-topic]')).toHaveCount(2);
  // Panels that wait for a selection stay out of the way.
  await expect(page.locator('#topic-detail')).toBeHidden();
  await expect(page.locator('#ward-profile')).toBeHidden();
  await expect(page.locator('#term-results')).toBeHidden();
  // The rising terms chart tags a term the data marks as seasonal.
  await expect(page.locator('#rising-terms svg text', { hasText: 'seasonal' })).toHaveCount(1);
  await expect(page.locator('meta[name="robots"]')).toHaveCount(0);
  await expect(page.getByRole('navigation', { name: 'Primary' }).locator('a[href="/analytics"]')).toHaveCount(1);
});

test('summary tiles name the widest-reaching topic of the last full month', async ({ page }) => {
  // Selected wards are never faded, so the fixture's three wards count.
  await openDashboard(page, '?wards=1,2,3');
  const tiles = page.locator('#summary-tiles > div');
  await expect(tiles.nth(1)).toContainText('3 of 3');
  // April is partial (data through Apr 24), so March is the last full month.
  await expect(tiles.nth(2)).toContainText('Most mentioned topic, Mar 2026');
  await expect(tiles.nth(2)).toContainText('Public safety');
  await expect(tiles.nth(2)).toContainText('3 of 3 wards');
});

test('choosing a topic in the overview opens its detail', async ({ page }) => {
  await openDashboard(page, '?wards=1,2,3');
  await page.locator('#topic-trends button[data-topic="budget_taxes"]').click();
  await expect(page).toHaveURL(/[?&]topic=budget_taxes/);
  await expect(page.locator('select[name="lens"]')).toHaveValue('budget_taxes');
  await expect(page.locator('#topic-detail')).toBeVisible();
  await expect(page.locator('#topic-detail-heading')).toHaveText('Budget & taxes');
  await expect(page.locator('#topic-detail-trend svg')).toBeVisible();
  await expect(page.locator('#topic-detail-wards svg')).toBeVisible();
  await expect(page.locator('#topic-detail [data-caption]')).toContainText('Mar 2026: 2 of 3 wards');
});

test('filters change the panels and the URL', async ({ page }) => {
  await openDashboard(page);
  await page.locator('select[name="lens"]').selectOption('public_safety');
  await expect(page.locator('#topic-detail-heading')).toHaveText('Public safety');
  await expect(page).toHaveURL(/[?&]topic=public_safety/);
  await page.locator('select[name="lens"]').selectOption('');
  await expect(page.locator('#topic-detail')).toBeHidden();

  await page.locator('#ward-summary').click();
  await page.locator('input[name="ward"][value="2"]').check();
  await expect(page.locator('#ward-summary')).toHaveText('Ward 2');
  await expect(page).toHaveURL(/[?&]wards=2(&|$)/);
  // A single selected ward opens its profile.
  await expect(page.locator('#profile-heading')).toHaveText('Ward 2 · Bo Example');
  await expect(page).toHaveURL(/[?&]ward=2(&|$)/);
});

test('restores a shared view from the URL and supports back and forward', async ({ page }) => {
  await openDashboard(page, '?wards=1,3&topic=budget_taxes&window=all&ward=1&term=zoning');
  await expect(page.locator('select[name="lens"]')).toHaveValue('budget_taxes');
  await expect(page.locator('select[name="from"]')).toHaveValue('');
  await expect(page.locator('input[name="ward"][value="1"]')).toBeChecked();
  await expect(page.locator('input[name="ward"][value="3"]')).toBeChecked();
  await expect(page.locator('#profile-ward')).toHaveValue('1');
  await expect(page.locator('#term-input')).toHaveValue('zoning');
  await expect(page.locator('#term-message')).toContainText('"zoning" appears in');
  await expect(page.locator('#term-results svg').first()).toBeVisible();

  await page.reload();
  await expect(page.locator('select[name="lens"]')).toHaveValue('budget_taxes');
  await expect(page.locator('#profile-heading')).toHaveText('Ward 1 · Ada Example');

  await page.locator('select[name="lens"]').selectOption('public_safety');
  await expect(page).toHaveURL(/topic=public_safety/);
  await page.goBack();
  await expect(page.locator('select[name="lens"]')).toHaveValue('budget_taxes');
  await page.goForward();
  await expect(page.locator('select[name="lens"]')).toHaveValue('public_safety');
});

test('a burst of filter clicks is one history entry', async ({ page }) => {
  await openDashboard(page);
  await page.locator('#ward-summary').click();
  await page.locator('input[name="ward"][value="1"]').check();
  await page.locator('input[name="ward"][value="3"]').check();
  await expect(page).toHaveURL(/[?&]wards=1,3(&|$)/);
  await page.goBack();
  await expect(page).toHaveURL(/\/analytics$/);
  await expect(page.locator('#ward-summary')).toHaveText('All wards');
});

test('keeps the date window from ending before it starts', async ({ page }) => {
  await openDashboard(page, '?from=2026-03&to=2026-04');
  await page.locator('select[name="to"]').selectOption('2026-02');
  await expect(page.locator('select[name="from"]')).toHaveValue('2026-02');
  await expect(page).toHaveURL(/[?&]to=2026-02(&|$)/);
  await page.locator('select[name="from"]').selectOption('2026-04');
  await expect(page.locator('select[name="to"]')).toHaveValue('');
  await expect(page).toHaveURL(/[?&]from=2026-04$/);
});

test('ignores invalid URL parameters', async ({ page }) => {
  await openDashboard(page, '?topic=nope&ward=99&from=2030-01&to=bad&wards=x');
  await expect(page.locator('select[name="lens"]')).toHaveValue('');
  await expect(page.locator('select[name="from"]')).toHaveValue('2026-02');
  await expect(page.locator('#ward-profile')).toBeHidden();
  await expect(page).toHaveURL(/\/analytics$/);
});

test('shows a ward with no archived newsletters neutrally', async ({ page }) => {
  await openDashboard(page, '?ward=4');
  await expect(page.locator('#profile-message')).toHaveText('No Ward 4 newsletters in the archive yet.');
  await expect(page.locator('#profile-content')).toBeHidden();
});

test('opens a ward profile from the filter bar', async ({ page }) => {
  await openDashboard(page);
  await page.locator('#profile-ward').selectOption('3');
  await expect(page.locator('#ward-profile')).toBeVisible();
  await expect(page.locator('#profile-heading')).toHaveText('Ward 3 · Cy Example');
  await expect(page.locator('#profile-topics svg').first()).toBeVisible();
  await expect(page).toHaveURL(/[?&]ward=3(&|$)/);
});

test('names wards without newsletters and draws coverage on demand', async ({ page }) => {
  await openDashboard(page);
  await expect(page.locator('#coverage [data-caption]')).toContainText('None yet: Ward 4.');
  await expect(page.locator('#coverage [data-chart] svg')).toHaveCount(0);
  await page.locator('#coverage-details summary').click();
  await expect(page.locator('#coverage [data-chart] svg').first()).toBeVisible();
  await expect(page.getByRole('button', { name: 'Download About the data as PNG' })).toBeEnabled();
});

test('downloads a chart as a PNG', async ({ page }) => {
  await openDashboard(page);
  const button = page.getByRole('button', { name: 'Download Civic calendar as PNG' });
  await expect(button).toBeEnabled();
  const [download] = await Promise.all([page.waitForEvent('download'), button.click()]);
  expect(download.suggestedFilename()).toMatch(/^civic-calendar-\d{4}-\d{2}-\d{2}\.png$/);
  const filePath = await download.path();
  const image = readFileSync(filePath);
  expect(image.subarray(0, PNG_SIGNATURE.length).equals(PNG_SIGNATURE)).toBe(true);
});
