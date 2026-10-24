import { test, expect } from '@playwright/test';

test('can perform keyword search', async ({ page }) => {
  await page.goto('/search');
  
  const searchInput = page.getByTestId('search-input');
  await searchInput.fill('zoning');
  await page.getByTestId('search-button').click();
  
  await expect(page).toHaveURL(/.*q=zoning/);
});

test('can filter by ward', async ({ page }) => {
  await page.goto('/search');
  
  const wardFilter = page.getByTestId('ward-filter');
  // Check if options exist
  const options = await wardFilter.locator('option').count();
  if (options > 1) {
    const firstWard = await wardFilter.locator('option').nth(1).getAttribute('value');
    if (firstWard) {
        await wardFilter.selectOption(firstWard);
        await page.getByTestId('search-button').click();
        await expect(page).toHaveURL(new RegExp(`.*ward=${firstWard}`));
    }
  }
});

test('can clear filters', async ({ page }) => {
  await page.goto('/search?q=test&ward=1');
  await expect(page.getByTestId('search-input')).toHaveValue('test');
  
  await page.getByTestId('clear-filters-link').click();
  await expect(page).toHaveURL(/\/search$/);
  await expect(page.getByTestId('search-input')).toHaveValue('');
});

test('groups topics by category with readable labels', async ({ page }) => {
  await page.goto('/search');

  const topicFilter = page.getByTestId('topic-filter');
  await expect(topicFilter.locator('optgroup[label="Streets"] option[value="bike_lanes"]')).toHaveText('Bike lanes');
});

test('applies new filters from the form and reflects them back', async ({ page }) => {
  await page.goto('/search');

  await page.getByTestId('sort-select').selectOption('oldest');
  await page.getByTestId('from-date-filter').fill('2026-01-01');
  await page.getByTestId('to-date-filter').fill('2026-06-30');
  await page.getByTestId('search-button').click();

  await expect(page).toHaveURL(/sort=oldest/);
  await expect(page).toHaveURL(/from=2026-01-01/);
  await expect(page).toHaveURL(/to=2026-06-30/);
  await expect(page.getByTestId('sort-select')).toHaveValue('oldest');
  await expect(page.getByTestId('from-date-filter')).toHaveValue('2026-01-01');
  await expect(page.getByTestId('to-date-filter')).toHaveValue('2026-06-30');
});

test('can filter by source', async ({ page }) => {
  await page.goto('/search');

  const sourceFilter = page.getByTestId('source-filter');
  const firstSource = await sourceFilter.locator('option').nth(1).getAttribute('value');
  if (firstSource) {
    await sourceFilter.selectOption(firstSource);
    await page.getByTestId('search-button').click();
    await expect(page).toHaveURL(new RegExp(`source=${firstSource}(&|$)`));
    await expect(sourceFilter).toHaveValue(firstSource);
  }
});

test('preserves filters in pagination links', async ({ page }) => {
  await page.goto('/search?sort=oldest&from=2020-01-01');

  const nextLink = page.getByRole('navigation', { name: 'Pagination' }).getByRole('link', { name: 'Next' });
  if (await nextLink.count()) {
    await expect(nextLink).toHaveAttribute('href', /from=2020-01-01.*sort=oldest.*page=2/);
  }
});

test('ignores invalid filter params instead of failing', async ({ page }) => {
  const response = await page.goto('/search?page=-3&sort=bogus&topic=nope&from=2026-02-31&source=abc');

  expect(response?.status()).toBe(200);
  await expect(page.getByTestId('sort-select')).toHaveValue('newest');
  await expect(page.getByTestId('topic-filter')).toHaveValue('');
  await expect(page.getByTestId('from-date-filter')).toHaveValue('');
});

test('loads old links with removed relevance params and drops them', async ({ page }) => {
  const response = await page.goto('/search?min_relevance=5&sort=relevance');

  expect(response?.status()).toBe(200);
  await expect(page.getByTestId('sort-select')).toHaveValue('newest');

  const nextLink = page.getByRole('navigation', { name: 'Pagination' }).getByRole('link', { name: 'Next' });
  if (await nextLink.count()) {
    await expect(nextLink).toHaveAttribute('href', '/search?page=2');
  }
});

test.describe('search timeline', () => {
  const timelineRoute = '**/api/search-timeline?*';

  test('shows monthly counts that link to each month', async ({ page }) => {
    await page.route(timelineRoute, (route) =>
      route.fulfill({
        json: {
          months: [
            { month: '2026-01', newsletterCount: 3, wardCount: 2 },
            { month: '2026-02', newsletterCount: 0, wardCount: 0 },
          ],
        },
      }),
    );
    await page.goto('/search?q=zoning');
    test.skip((await page.getByTestId('newsletter-card').count()) === 0, 'no results in this database');

    const timeline = page.getByTestId('search-timeline');
    await expect(timeline.getByRole('heading', { name: /zoning/ })).toBeVisible();
    const january = timeline.getByRole('link', { name: 'Jan 2026: 3 newsletters, 2 wards' });
    await expect(january).toHaveAttribute('href', '/search?q=zoning&from=2026-01-01&to=2026-01-31');
    await expect(timeline.getByRole('link', { name: /Feb 2026/ })).toHaveCount(0);
  });

  test('stays hidden when the timeline is unavailable', async ({ page }) => {
    await page.route(timelineRoute, (route) =>
      route.fulfill({ status: 404, json: { error: 'timeline_unavailable' } }),
    );
    await page.goto('/search?q=zoning');

    await expect(page.getByTestId('search-timeline')).toHaveCount(0);
    await expect(page.getByTestId('search-input')).toHaveValue('zoning');
  });
});
