import { test, expect } from '@playwright/test';
import type { Page } from '@playwright/test';
import {
  BIKE_LANES_TOPIC,
  NEWSLETTER_COUNT,
  SEARCH_WORD,
  SEARCH_WORD_MATCHES,
  SEARCH_WORD_SECOND_PAGE_MATCHES,
  SEARCH_WORD_TIMELINE,
  WARD_1,
  WARD_40,
  WARD_OPTION_LABELS,
} from './fixtures/db/facts';

const PAGE_SIZE = 20;

const openFilters = (page: Page) => page.getByTestId('search-filters-toggle').click();
const resultCount = (page: Page) => page.getByText(/^Found \d+ newsletters?$/);
const nextPageLink = (page: Page) =>
  page.getByRole('navigation', { name: 'Pagination' }).getByRole('link', { name: 'Next' });

test('finds every newsletter that mentions a word, over two pages', async ({ page }) => {
  await page.goto('/search');

  await page.getByTestId('search-input').fill(SEARCH_WORD);
  await page.getByTestId('search-button').click();

  await expect(page).toHaveURL(new RegExp(`q=${SEARCH_WORD}`));
  await expect(resultCount(page)).toHaveText(`Found ${SEARCH_WORD_MATCHES} newsletters`);
  await expect(page.getByTestId('newsletter-card')).toHaveCount(PAGE_SIZE);

  await nextPageLink(page).click();
  await expect(page).toHaveURL(new RegExp(`q=${SEARCH_WORD}.*page=2`));
  await expect(page.getByTestId('newsletter-card')).toHaveCount(SEARCH_WORD_SECOND_PAGE_MATCHES);
});

test('keeps filters collapsed behind the Filters button', async ({ page }) => {
  await page.goto('/search');

  await expect(page.getByTestId('search-input')).toBeVisible();
  await expect(page.getByTestId('ward-filter')).toBeHidden();

  await openFilters(page);
  await expect(page.getByTestId('ward-filter')).toBeVisible();
  await expect(page.getByTestId('topic-filter')).toBeVisible();
  await expect(page.getByTestId('source-filter')).toHaveCount(0);
});

test('labels each ward with its aldermen, both of them in a ward with two', async ({ page }) => {
  await page.goto('/search');

  await expect(page.getByTestId('ward-filter').locator('option:not([value=""])')).toHaveText(WARD_OPTION_LABELS);
});

test('can filter by ward, merging the ward\'s sources', async ({ page }) => {
  await page.goto('/search');
  await openFilters(page);

  await page.getByTestId('ward-filter').selectOption(String(WARD_40.ward));
  await page.getByTestId('apply-filters-button').click();

  await expect(page).toHaveURL(new RegExp(`ward=${WARD_40.ward}(&|$)`));
  await expect(page.getByTestId('active-filter-count')).toContainText('1');
  await expect(page.getByTestId('active-filter')).toHaveText(`Ward ${WARD_40.ward}`);
  await expect(resultCount(page)).toHaveText(`Found ${WARD_40.newsletters} newsletters`);
  await expect(page.getByTestId('newsletter-card')).toHaveCount(WARD_40.newsletters);
});

test('combines keywords with a ward', async ({ page }) => {
  await page.goto(`/search?q=${SEARCH_WORD}&ward=${WARD_1.ward}`);

  await expect(resultCount(page)).toHaveText(`Found ${WARD_1.zoningNewsletters} newsletters`);
  for (const ward of await page.getByTestId('newsletter-ward-link').allTextContents()) {
    expect(ward.trim()).toBe(`Ward ${WARD_1.ward}`);
  }
});

test('can filter by topic', async ({ page }) => {
  await page.goto(`/search?topic=${BIKE_LANES_TOPIC.id}`);

  await expect(page.getByTestId('active-filter')).toHaveText(BIKE_LANES_TOPIC.label);
  await expect(page.getByTestId('newsletter-card')).toHaveCount(BIKE_LANES_TOPIC.newsletters);
});

test('narrows keywords to a date range', async ({ page }) => {
  const september = SEARCH_WORD_TIMELINE[3];
  await page.goto(`/search?q=${SEARCH_WORD}&from=2026-09-01&to=2026-09-30`);

  await expect(resultCount(page)).toHaveText(`Found ${september.newsletters} newsletters`);
});

test('lists active filters with links that remove each one', async ({ page }) => {
  await page.goto('/search?q=test&ward=1&topic=bike_lanes');

  const activeFilters = page.getByTestId('active-filter');
  await expect(activeFilters).toHaveText(['Bike lanes', 'Ward 1']);
  await expect(page.getByRole('link', { name: 'Remove filter: Ward 1' })).toHaveAttribute(
    'href',
    '/search?q=test&topic=bike_lanes',
  );
});

test('clearing filters keeps the keywords', async ({ page }) => {
  await page.goto('/search?q=test&ward=1');
  await expect(page.getByTestId('search-input')).toHaveValue('test');

  await page.getByTestId('clear-filters-link').click();
  await expect(page).toHaveURL(/\/search\?q=test$/);
  await expect(page.getByTestId('search-input')).toHaveValue('test');
  await expect(page.getByTestId('active-filters')).toHaveCount(0);
});

test('keeps a source filter from the URL when searching again', async ({ page }) => {
  await page.goto('/search?source=1');
  await expect(page.getByTestId('active-filter')).toHaveText(WARD_1.alderman);
  await expect(page.getByTestId('newsletter-card')).toHaveCount(WARD_1.newsletters);

  await page.getByTestId('search-input').fill(SEARCH_WORD);
  await page.getByTestId('search-button').click();
  await expect(page).toHaveURL(/source=1(&|$)/);
  await expect(page).toHaveURL(new RegExp(`q=${SEARCH_WORD}`));
});

test('keeps a ward from the URL selected when it has no listed source', async ({ page }) => {
  await page.goto('/search?ward=99');
  await expect(page.getByTestId('ward-filter')).toHaveValue('99');
});

test('groups topics by category with readable labels', async ({ page }) => {
  await page.goto('/search');

  const topicFilter = page.getByTestId('topic-filter');
  await expect(topicFilter.locator('optgroup[label="Streets"] option[value="bike_lanes"]')).toHaveText('Bike lanes');
});

test('applies new filters from the form and reflects them back', async ({ page }) => {
  await page.goto('/search');
  await openFilters(page);

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

test('preserves filters in pagination links', async ({ page }) => {
  await page.goto('/search?sort=oldest&from=2020-01-01');

  await expect(resultCount(page)).toHaveText(`Found ${NEWSLETTER_COUNT} newsletters`);
  await expect(nextPageLink(page)).toHaveAttribute('href', /from=2020-01-01.*sort=oldest.*page=2/);
});

test('ignores invalid filter params instead of failing', async ({ page }) => {
  const response = await page.goto('/search?page=-3&sort=bogus&topic=nope&from=2026-02-31&source=abc');

  expect(response?.status()).toBe(200);
  await expect(page.getByTestId('sort-select')).toHaveValue('newest');
  await expect(page.getByTestId('topic-filter')).toHaveValue('');
  await expect(page.getByTestId('from-date-filter')).toHaveValue('');
  await expect(page.getByTestId('active-filters')).toHaveCount(0);
});

test('loads old links with removed relevance params and drops them', async ({ page }) => {
  const response = await page.goto('/search?min_relevance=5&sort=relevance');

  expect(response?.status()).toBe(200);
  await expect(page.getByTestId('sort-select')).toHaveValue('newest');
  await expect(nextPageLink(page)).toHaveAttribute('href', '/search?page=2');
});

test.describe('search timeline', () => {
  test('shows monthly counts that link to each month', async ({ page }) => {
    await page.goto(`/search?q=${SEARCH_WORD}`);

    const timeline = page.getByTestId('search-timeline');
    await expect(timeline.getByRole('heading', { name: new RegExp(SEARCH_WORD) })).toBeVisible();
    await expect(timeline).toContainText(`${SEARCH_WORD_MATCHES} newsletters`);
    for (const { month, label, newsletters, wards } of SEARCH_WORD_TIMELINE) {
      const lastDay = new Date(Date.UTC(Number(month.slice(0, 4)), Number(month.slice(5, 7)), 0)).getUTCDate();
      await expect(
        timeline.getByRole('link', { name: `${label}: ${newsletters} newsletters, ${wards} wards` }),
      ).toHaveAttribute('href', `/search?q=${SEARCH_WORD}&from=${month}-01&to=${month}-${lastDay}`);
    }
    // The chart starts in January; months before the first match have no link.
    await expect(timeline.getByRole('link', { name: /May 2026/ })).toHaveCount(0);
  });

  test('clicking a month narrows the search to it', async ({ page }) => {
    const june = SEARCH_WORD_TIMELINE[0];
    await page.goto(`/search?q=${SEARCH_WORD}`);

    await page.getByTestId('search-timeline').getByRole('link', { name: new RegExp(`^${june.label}`) }).click();

    await expect(page).toHaveURL(/from=2026-06-01&to=2026-06-30/);
    await expect(resultCount(page)).toHaveText(`Found ${june.newsletters} newsletters`);
  });

  test('stays hidden when the timeline is unavailable', async ({ page }) => {
    await page.route('**/api/search-timeline?*', (route) =>
      route.fulfill({ status: 404, json: { error: 'timeline_unavailable' } }),
    );
    await page.goto(`/search?q=${SEARCH_WORD}`);

    await expect(page.getByTestId('search-timeline')).toHaveCount(0);
    await expect(page.getByTestId('search-input')).toHaveValue(SEARCH_WORD);
  });
});
